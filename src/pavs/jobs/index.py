"""Spark job 2: Iceberg lakehouse -> Milvus (both collections).

Step 1 (Spark): join documents + doc_embeddings in Iceberg ONCE and write the result to a
                staging folder as parquet files.
Step 2 (Python): stream those files batch by batch into Milvus.

The lakehouse is the source of truth; Milvus is a derived index that can be rebuilt from
it at any time. The join is done once (not once per batch), so the 1.5 GB embedding table
is scanned a single time even at 1M documents.

The Spark step runs in a child process: when it exits, its Java VM (up to 3 GB) is gone before the
Milvus load starts. (spark.stop() alone leaves the JVM running; at 1M documents that ran the container
out of memory.)

Usage:  python -m src.pavs.jobs.index                 (all documents)
        python -m src.pavs.jobs.index --limit 100000  (doc_id < 100000)
        python -m src.pavs.jobs.index --skip-stage    (reuse the staged parquet files)
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import time

import numpy as np
import pyarrow.parquet as pq
from pymilvus import MilvusClient

from src.common.spark_packages import get_spark
from src.pavs import milvus_index
from src.pavs.search import COLL_FILTER

DATA = os.environ.get("PAVS_DATA", "/app/data")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=5_000)
    ap.add_argument("--master", default="local[4]")
    ap.add_argument("--stage-only", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--skip-stage", action="store_true")
    a = ap.parse_args()

    stage = f"{DATA}/stage/milvus_load"
    if a.stage_only:
        stage_with_spark(a, stage)
        return
    if not a.skip_stage:
        cmd = [sys.executable, "-m", "src.pavs.jobs.index", "--stage-only", "--master", a.master]
        if a.limit:
            cmd += ["--limit", str(a.limit)]
        subprocess.run(cmd, check=True)
    load_into_milvus(a, stage)


def stage_with_spark(a, stage):
    shutil.rmtree(stage, ignore_errors=True)
    t = time.time()
    spark = get_spark("pavs-index", master=a.master, driver_memory="3g")
    q = """SELECT d.doc_id, d.arxiv_id, d.title, d.access_label, d.dept, e.embedding
           FROM lake.pavs.documents d JOIN lake.pavs.doc_embeddings e ON d.doc_id = e.doc_id"""
    if a.limit:
        q += f" WHERE d.doc_id < {a.limit}"
    spark.sql(q).repartition(16).write.mode("overwrite").parquet(stage)
    spark.stop()
    print(f"[spark] joined Iceberg tables -> {stage} in {time.time() - t:.0f}s", flush=True)


def load_into_milvus(a, stage):
    uri = os.environ.get("PAVS_MILVUS_URI", "http://standalone:19530")
    client = MilvusClient(uri=uri)
    milvus_index.create_collections(client)

    total = 0
    t = time.time()
    for path in sorted(glob.glob(f"{stage}/*.parquet")):
        for rb in pq.ParquetFile(path).iter_batches(batch_size=a.batch):
            emb = rb.column(rb.schema.get_field_index("embedding"))
            vecs = np.array(emb.flatten(), dtype=np.float32).reshape(-1, milvus_index.DIM)  # copy: Arrow memory is read-only
            vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
            col = lambda n: rb.column(rb.schema.get_field_index(n)).to_pylist()
            total += milvus_index.insert_batch(client, col("doc_id"), col("arxiv_id"), col("title"),
                                               col("access_label"), col("dept"), vecs)
        print(f"  inserted {total:,} rows ({total / (time.time() - t):,.0f} rows/s)", flush=True)
    insert_s = time.time() - t
    load_s = milvus_index.finish(client)
    print(f"INDEX DONE: {total:,} rows | insert {insert_s:.0f}s | flush+index+load {load_s:.0f}s | "
          f"stats {client.get_collection_stats(COLL_FILTER)}")


if __name__ == "__main__":
    main()
