"""Smoke test 3: Spark + Iceberg lakehouse on MinIO, catalog in Postgres.

Checks the lakehouse features the project relies on:
  1. Create an Iceberg table stored in MinIO
  2. Row-level UPDATE (relabel a document = permission change)
  3. Snapshots + time travel (audit: "what label did doc X have before?")

Run:  python -m src.smoke.test_lakehouse
"""
import time

from src.common.spark_packages import ensure_bucket, get_spark


def ok(msg):
    print(f"[PASS] {msg}", flush=True)


def main():
    ensure_bucket("lakehouse")
    ok("MinIO bucket 'lakehouse' exists")

    t = time.time()
    spark = get_spark("smoke-lakehouse")
    print(f"Spark {spark.version} started in {time.time() - t:.1f}s")

    spark.sql("CREATE NAMESPACE IF NOT EXISTS lake.smoke")
    spark.sql("DROP TABLE IF EXISTS lake.smoke.docs PURGE")
    spark.sql("""
        CREATE TABLE lake.smoke.docs (
            doc_id BIGINT, title STRING, access_label STRING
        ) USING iceberg
    """)
    spark.sql("""
        INSERT INTO lake.smoke.docs VALUES
          (1, 'Graph neural networks', 'public'),
          (2, 'Quantum error correction', 'physics-internal'),
          (3, 'Salary bands 2026', 'hr-restricted')
    """)
    n = spark.table("lake.smoke.docs").count()
    assert n == 3, n
    ok("Iceberg table created in MinIO and 3 rows written")

    first_snap = spark.sql(
        "SELECT snapshot_id FROM lake.smoke.docs.snapshots ORDER BY committed_at LIMIT 1"
    ).collect()[0][0]

    spark.sql("UPDATE lake.smoke.docs SET access_label = 'cs-confidential' WHERE doc_id = 1")
    now = spark.sql("SELECT access_label FROM lake.smoke.docs WHERE doc_id = 1").collect()[0][0]
    assert now == "cs-confidential", now
    ok("row-level UPDATE works (doc 1 relabelled to cs-confidential)")

    before = spark.sql(
        f"SELECT access_label FROM lake.smoke.docs VERSION AS OF {first_snap} WHERE doc_id = 1"
    ).collect()[0][0]
    assert before == "public", before
    snaps = spark.sql("SELECT count(*) FROM lake.smoke.docs.snapshots").collect()[0][0]
    ok(f"time travel works: doc 1 was '{before}' in snapshot {first_snap} ({snaps} snapshots kept)")

    spark.sql("DROP TABLE lake.smoke.docs PURGE")
    spark.stop()
    print("LAKEHOUSE SMOKE TEST: ALL PASSED")


if __name__ == "__main__":
    main()
