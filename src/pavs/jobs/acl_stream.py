"""Spark Structured Streaming job: permission changes from Kafka -> Milvus + Iceberg.

Event (JSON on Kafka topic "acl-relabel"):
    {"event_id": "...", "doc_id": 123, "new_label": "hr-restricted", "ts_ms": 1790000000000}

For every micro-batch (foreachBatch):
  1. Milvus FIRST: move the documents to their new label (both collections).
     A revocation must reach the index that serves searches as fast as possible.
  2. Iceberg: update lake.pavs.documents (source of truth) and append the events, with the time each
     was applied, to lake.pavs.acl_events (audit history).
If step 2 fails, Spark does not commit the batch offset, so the batch is replayed; both steps are
idempotent (setting a label twice gives the same result), so replay is safe (at-least-once delivery).

Usage:  python -m src.pavs.jobs.acl_stream                 (runs until stopped)
        python -m src.pavs.jobs.acl_stream --trigger 1     (micro-batch every 1 second)
        python -m src.pavs.jobs.acl_stream --split         (fast Milvus path + separate Iceberg path)
"""
import argparse
import json
import os
import time

from pymilvus import MilvusClient

from src.common.spark_packages import get_spark
from src.pavs import milvus_index

TOPIC = "acl-relabel"
SCHEMA = "event_id STRING, doc_id BIGINT, new_label STRING, ts_ms BIGINT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trigger", type=float, default=1.0, help="seconds between micro-batches")
    ap.add_argument("--checkpoint", default="/app/data/stage/ckpt_acl")
    ap.add_argument("--shuffle-partitions", type=int, default=200,
                    help="Spark default is 200; a tiny batch (1-60 events) only needs a few. Fewer partitions "
                         "= shorter micro-batch = shorter leak window. NOTE: Spark saves this value in the "
                         "checkpoint, so a changed value needs a new --checkpoint folder.")
    ap.add_argument("--split", action="store_true",
                    help="separate fast path (Kafka->Milvus) from slow path (Kafka->Iceberg)")
    ap.add_argument("--fast-trigger", type=float, default=0.2, help="seconds between fast-path micro-batches")
    a = ap.parse_args()

    boot = os.environ.get("PAVS_KAFKA", "kafka:9092")
    milvus = MilvusClient(uri=os.environ.get("PAVS_MILVUS_URI", "http://standalone:19530"))
    spark = get_spark("pavs-acl-stream", master="local[2]", driver_memory="2g",
                      extra={"spark.scheduler.mode": "FAIR"})   # fast path is not queued behind the lake path
    spark.conf.set("spark.sql.shuffle.partitions", str(a.shuffle_partitions))
    spark.conf.set("spark.sql.adaptive.enabled", "true")
    spark.sql("""CREATE TABLE IF NOT EXISTS lake.pavs.acl_events (
        event_id STRING, doc_id BIGINT, new_label STRING, ts_ms BIGINT,
        milvus_applied_ms BIGINT, lake_applied_ms BIGINT) USING iceberg""")

    def handle(batch, batch_id):
        rows = batch.collect()
        if not rows:
            return
        changes = {r.doc_id: r.new_label for r in sorted(rows, key=lambda r: r.ts_ms)}   # last event wins
        n = milvus_index.apply_relabels(milvus, changes)
        milvus_ms = int(time.time() * 1000)

        ss = batch.sparkSession          # temp views live in the micro-batch's own session
        batch.createOrReplaceTempView("acl_batch")
        ss.sql("""MERGE INTO lake.pavs.documents t
                     USING (SELECT doc_id, max_by(new_label, ts_ms) AS new_label FROM acl_batch GROUP BY doc_id) s
                     ON t.doc_id = s.doc_id
                     WHEN MATCHED THEN UPDATE SET t.access_label = s.new_label""")
        lake_ms = int(time.time() * 1000)
        ss.sql(f"""INSERT INTO lake.pavs.acl_events
                      SELECT event_id, doc_id, new_label, ts_ms, {milvus_ms}, {lake_ms} FROM acl_batch""")
        print(f"[batch {batch_id}] {len(rows)} events, {n} docs relabelled in Milvus, Iceberg updated", flush=True)

    # --split: two independent streaming queries on the same topic.
    #   fast path  Kafka -> Milvus only (no shuffle, no table write): this is what closes the leak window
    #   slow path  Kafka -> Iceberg MERGE + audit table: can take seconds without delaying revocation
    milvus_log = "/app/logs/acl_milvus_applied.jsonl"

    def handle_milvus(batch, batch_id):
        rows = batch.collect()
        if not rows:
            return
        changes = {r.doc_id: r.new_label for r in sorted(rows, key=lambda r: r.ts_ms)}
        n = milvus_index.apply_relabels(milvus, changes)
        milvus_ms = int(time.time() * 1000)
        with open(milvus_log, "a") as f:
            for r in rows:
                f.write(json.dumps({"event_id": r.event_id, "new_label": r.new_label,
                                    "ts_ms": r.ts_ms, "milvus_applied_ms": milvus_ms}) + "\n")
        print(f"[fast {batch_id}] {len(rows)} events, {n} docs relabelled in Milvus", flush=True)

    def handle_lake(batch, batch_id):
        if batch.isEmpty():
            return
        ss = batch.sparkSession
        batch.createOrReplaceTempView("acl_batch")
        ss.sql("""MERGE INTO lake.pavs.documents t
                     USING (SELECT doc_id, max_by(new_label, ts_ms) AS new_label FROM acl_batch GROUP BY doc_id) s
                     ON t.doc_id = s.doc_id
                     WHEN MATCHED THEN UPDATE SET t.access_label = s.new_label""")
        lake_ms = int(time.time() * 1000)
        ss.sql(f"""INSERT INTO lake.pavs.acl_events
                      SELECT event_id, doc_id, new_label, ts_ms, CAST(NULL AS BIGINT), {lake_ms} FROM acl_batch""")
        print(f"[lake {batch_id}] Iceberg updated", flush=True)

    def events():
        return (spark.readStream.format("kafka")
                .option("kafka.bootstrap.servers", boot)
                .option("subscribe", TOPIC)
                .option("startingOffsets", "latest")
                .load()
                .selectExpr(f"from_json(CAST(value AS STRING), '{SCHEMA}') AS e")
                .select("e.*"))

    if a.split:
        spark.sparkContext.setLocalProperty("spark.scheduler.pool", "fast")
        q1 = (events().writeStream.foreachBatch(handle_milvus)
              .option("checkpointLocation", a.checkpoint + "_fast")
              .trigger(processingTime=f"{a.fast_trigger} seconds").start())
        spark.sparkContext.setLocalProperty("spark.scheduler.pool", "lake")
        q2 = (events().writeStream.foreachBatch(handle_lake)
              .option("checkpointLocation", a.checkpoint + "_lake")
              .trigger(processingTime=f"{a.trigger} seconds").start())
        print(f"ACL stream running (split): fast path every {a.fast_trigger}s, lake path every {a.trigger}s", flush=True)
        spark.streams.awaitAnyTermination()
    else:
        q = (events().writeStream.foreachBatch(handle)
             .option("checkpointLocation", a.checkpoint)
             .trigger(processingTime=f"{a.trigger} seconds")
             .start())
        print(f"ACL stream running: topic {TOPIC}, trigger {a.trigger}s", flush=True)
        q.awaitTermination()


if __name__ == "__main__":
    main()
