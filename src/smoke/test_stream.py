"""Smoke test 4: Kafka -> Spark Structured Streaming -> Iceberg.

Sends 500 fake "document relabelled" events to Kafka, then a Spark streaming
job reads them and appends them to an Iceberg table. This is the path that
permission changes will take in the real project.

Run:  python -m src.smoke.test_stream
"""
import json
import os
import time
import uuid

from confluent_kafka import Producer

from src.common.spark_packages import ensure_bucket, get_spark

BOOT = os.environ.get("PAVS_KAFKA", "kafka:9092")
TOPIC = f"smoke-acl-{uuid.uuid4().hex[:6]}"
N = 500


def ok(msg):
    print(f"[PASS] {msg}", flush=True)


def main():
    ensure_bucket("lakehouse")

    p = Producer({"bootstrap.servers": BOOT})
    t = time.time()
    for i in range(N):
        evt = {"doc_id": i, "new_label": "cs-confidential", "ts_ms": int(time.time() * 1000)}
        p.produce(TOPIC, key=str(i), value=json.dumps(evt))
    left = p.flush(30)
    assert left == 0, f"{left} messages not delivered"
    ok(f"{N} events produced to Kafka topic {TOPIC} in {time.time() - t:.2f}s")

    spark = get_spark("smoke-stream")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS lake.smoke")
    spark.sql("DROP TABLE IF EXISTS lake.smoke.acl_events PURGE")
    spark.sql("""
        CREATE TABLE lake.smoke.acl_events (
            doc_id BIGINT, new_label STRING, ts_ms BIGINT
        ) USING iceberg
    """)

    schema = "doc_id BIGINT, new_label STRING, ts_ms BIGINT"
    stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", BOOT)
        .option("subscribe", TOPIC)
        .option("startingOffsets", "earliest")
        .load()
        .selectExpr(f"from_json(CAST(value AS STRING), '{schema}') AS e")
        .select("e.*")
    )
    t = time.time()
    q = (
        stream.writeStream.format("iceberg")
        .outputMode("append")
        .option("checkpointLocation", f"/tmp/ckpt/{TOPIC}")
        .trigger(availableNow=True)
        .toTable("lake.smoke.acl_events")
    )
    q.awaitTermination(300)
    n = spark.table("lake.smoke.acl_events").count()
    assert n == N, f"expected {N}, got {n}"
    ok(f"Spark streaming read {n} events from Kafka into Iceberg in {time.time() - t:.1f}s")

    spark.sql("DROP TABLE lake.smoke.acl_events PURGE")
    spark.stop()
    print("STREAM SMOKE TEST: ALL PASSED")


if __name__ == "__main__":
    main()
