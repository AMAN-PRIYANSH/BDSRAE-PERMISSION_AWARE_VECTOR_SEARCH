"""Where does the revocation leak window come from?  Reads lake.pavs.acl_events (written by the stream job).

For every revocation event (new label 'hr-restricted'):
    to_milvus_ms = milvus_applied_ms - ts_ms   (Kafka + waiting for the micro-batch + Milvus upsert)
    to_lake_ms   = lake_applied_ms   - ts_ms   (the same + Iceberg MERGE)
In --split mode the fast path does not write to Iceberg, so its times come from its JSONL log (--milvus-log).
Run:  python -m src.pavs.revocation_breakdown --since-ms <epoch ms> --tag demo100k
Output: results/revocation_breakdown_<tag>.csv
"""
import argparse
import json
import os

import pandas as pd

from src.common.spark_packages import get_spark

OUT = os.environ.get("PAVS_RESULTS", "/app/results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-ms", type=int, default=0)
    ap.add_argument("--since-file", default="", help="file holding the start time in epoch ms")
    ap.add_argument("--until-ms", type=int, default=2**62)
    ap.add_argument("--milvus-log", default="", help="JSONL written by the --split fast path")
    ap.add_argument("--tag", default="demo100k")
    a = ap.parse_args()
    if a.since_file:
        a.since_ms = int(open(a.since_file).read().strip())
    window = f"ts_ms >= {a.since_ms} AND ts_ms < {a.until_ms} AND new_label = 'hr-restricted'"

    spark = get_spark("pavs-revocation-breakdown", master="local[2]", driver_memory="1g")
    df = spark.sql(f"""SELECT event_id, milvus_applied_ms - ts_ms AS to_milvus_ms, lake_applied_ms - ts_ms AS to_lake_ms
                       FROM lake.pavs.acl_events WHERE {window}""").toPandas()
    spark.stop()

    if a.milvus_log:
        rows = [json.loads(l) for l in open(a.milvus_log) if l.strip()]
        fast = pd.DataFrame(rows)
        fast = fast[(fast.ts_ms >= a.since_ms) & (fast.ts_ms < a.until_ms) & (fast.new_label == "hr-restricted")]
        fast = fast.assign(to_milvus_ms=fast.milvus_applied_ms - fast.ts_ms)[["event_id", "to_milvus_ms"]]
        df = fast.merge(df.drop(columns="to_milvus_ms"), on="event_id", how="left")

    q = df[["to_milvus_ms", "to_lake_ms"]].astype(float).quantile([0.5, 0.95, 0.99]).round(0)
    print(f"{len(df)} revocation events since {a.since_ms}")
    print(q.to_string())
    os.makedirs(OUT, exist_ok=True)
    q.to_csv(f"{OUT}/revocation_breakdown_{a.tag}.csv")


if __name__ == "__main__":
    main()
