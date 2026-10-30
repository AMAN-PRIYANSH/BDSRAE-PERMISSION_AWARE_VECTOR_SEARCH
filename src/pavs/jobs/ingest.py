"""Spark job 1: raw files -> Iceberg lakehouse.

Input  (data/kaggle/, produced by notebooks/01_kaggle_embed_arxiv.ipynb):
    <prefix>_meta.parquet     doc_id, arxiv_id, title, abstract, categories, update_date
    <prefix>_emb_f16.npy      (n, 384) float16 embeddings, same row order
Output (Iceberg, catalog "lake", namespace "pavs"):
    documents       one row per document + department + access label (partitioned by dept)
    doc_embeddings  doc_id -> embedding (float array), model name
    role_grants     role -> label   (the permission policy, versioned like any table)
    users           user -> role

Usage:  python -m src.pavs.jobs.ingest --prefix demo100k
        python -m src.pavs.jobs.ingest --prefix corpus --replace
"""
import argparse
import os
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from src.common.spark_packages import ensure_bucket, get_spark
from src.pavs import policy

DATA = os.environ.get("PAVS_DATA", "/app/data")
MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def label_sql():
    """Spark SQL that reproduces policy.department() and policy.access_label() exactly."""
    primary = "split(categories, ' ')[0]"
    phys = " OR ".join(f"startswith({primary}, '{p}')" for p in policy.PHYSICS_PREFIXES)
    dept = (f"CASE WHEN startswith({primary}, 'cs.') THEN 'cs' "
            f"WHEN startswith({primary}, 'math.') OR {primary} = 'math' THEN 'math' "
            f"WHEN {phys} THEN 'physics' ELSE 'other' END")
    b = f"pmod(crc32(cast(arxiv_id AS binary)), {policy.BUCKETS})"
    label = (f"CASE WHEN {b} < 10 THEN 'board-restricted' "
             f"WHEN {b} < 100 THEN 'hr-restricted' "
             f"WHEN {b} < 1000 THEN concat(dept, '-confidential') "
             f"WHEN {b} < 5000 THEN concat(dept, '-internal') "
             f"ELSE 'public' END")
    return dept, label


def npy_to_parquet(npy_path, out_path, doc_ids, chunk=100_000):
    """Write embeddings as parquet (doc_id, embedding list<float>) so Spark can read them in parallel."""
    emb = np.load(npy_path, mmap_mode="r")
    assert emb.shape[0] == len(doc_ids), (emb.shape, len(doc_ids))
    schema = pa.schema([("doc_id", pa.int64()), ("embedding", pa.list_(pa.float32()))])
    with pq.ParquetWriter(out_path, schema, compression="zstd") as w:
        for s in range(0, emb.shape[0], chunk):
            block = np.asarray(emb[s:s + chunk], dtype=np.float32)
            arr = pa.FixedSizeListArray.from_arrays(pa.array(block.reshape(-1)), emb.shape[1])
            w.write_table(pa.table({"doc_id": pa.array(doc_ids[s:s + chunk], pa.int64()),
                                    "embedding": arr.cast(pa.list_(pa.float32()))}))
    return emb.shape


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="demo100k")
    ap.add_argument("--replace", action="store_true", help="drop and recreate the tables")
    ap.add_argument("--master", default="local[4]")
    a = ap.parse_args()

    src_meta = f"{DATA}/kaggle/{a.prefix}_meta.parquet"
    src_emb = f"{DATA}/kaggle/{a.prefix}_emb_f16.npy"
    stage = f"{DATA}/stage"
    os.makedirs(stage, exist_ok=True)
    t_all = time.time()

    doc_ids = pq.read_table(src_meta, columns=["doc_id"]).column(0).to_numpy()
    emb_parquet = f"{stage}/{a.prefix}_emb.parquet"
    t = time.time()
    shape = npy_to_parquet(src_emb, emb_parquet, doc_ids)
    print(f"[stage] embeddings {shape} -> parquet in {time.time() - t:.1f}s", flush=True)

    ensure_bucket("lakehouse")
    spark = get_spark("pavs-ingest", master=a.master, driver_memory="3g")
    spark.sql("CREATE NAMESPACE IF NOT EXISTS lake.pavs")
    if a.replace:
        for tbl in ("documents", "doc_embeddings", "role_grants", "users"):
            spark.sql(f"DROP TABLE IF EXISTS lake.pavs.{tbl} PURGE")

    spark.sql("""CREATE TABLE IF NOT EXISTS lake.pavs.documents (
        doc_id BIGINT, arxiv_id STRING, title STRING, abstract STRING, categories STRING,
        dept STRING, access_label STRING, update_date STRING, ingested_at TIMESTAMP)
        USING iceberg PARTITIONED BY (dept)""")
    spark.sql("""CREATE TABLE IF NOT EXISTS lake.pavs.doc_embeddings (
        doc_id BIGINT, embedding ARRAY<FLOAT>, model STRING) USING iceberg""")

    dept_sql, label_expr = label_sql()
    t = time.time()
    meta = spark.read.parquet(src_meta)
    docs = (meta.selectExpr("*", f"{dept_sql} AS dept")
                .selectExpr("doc_id", "arxiv_id", "title", "abstract", "categories", "dept",
                            f"{label_expr} AS access_label", "update_date",
                            "current_timestamp() AS ingested_at"))
    docs.createOrReplaceTempView("incoming_docs")
    if a.replace:      # fresh tables: a plain append avoids a full join (important at 1M rows)
        docs.writeTo("lake.pavs.documents").append()
    else:              # incremental load: upsert by doc_id
        spark.sql("""MERGE INTO lake.pavs.documents t USING incoming_docs s ON t.doc_id = s.doc_id
                     WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *""")
    n_docs = spark.table("lake.pavs.documents").count()
    print(f"[iceberg] documents: {n_docs:,} rows in {time.time() - t:.1f}s", flush=True)

    # Verify Spark labels == Python policy labels on a sample (single source of truth check).
    sample = spark.sql("SELECT arxiv_id, categories, dept, access_label FROM lake.pavs.documents "
                       "TABLESAMPLE (2 PERCENT)").limit(5000).collect()
    bad = [r for r in sample if r.access_label != policy.access_label(r.arxiv_id, r.categories)
           or r.dept != policy.department(r.categories)]
    assert not bad, f"Spark/Python label mismatch, e.g. {bad[:3]}"
    print(f"[check] Spark labels match Python policy on {len(sample)} sampled rows", flush=True)

    t = time.time()
    emb = spark.read.parquet(emb_parquet).selectExpr("doc_id", "embedding", f"'{MODEL}' AS model")
    emb.createOrReplaceTempView("incoming_emb")
    if a.replace:
        emb.writeTo("lake.pavs.doc_embeddings").append()
    else:
        spark.sql("""MERGE INTO lake.pavs.doc_embeddings t USING incoming_emb s ON t.doc_id = s.doc_id
                     WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *""")
    n_emb = spark.table("lake.pavs.doc_embeddings").count()
    print(f"[iceberg] doc_embeddings: {n_emb:,} rows in {time.time() - t:.1f}s", flush=True)

    grants = [(r, l) for r, ls in policy.ROLES.items() for l in ls]
    spark.createDataFrame(grants, "role STRING, label STRING").writeTo("lake.pavs.role_grants").createOrReplace()
    spark.createDataFrame(list(policy.USERS.items()), "user STRING, role STRING").writeTo("lake.pavs.users").createOrReplace()

    print("[summary] documents per access label:")
    spark.sql("""SELECT access_label, count(*) AS n, round(100 * count(*) / sum(count(*)) OVER (), 2) AS pct
                 FROM lake.pavs.documents GROUP BY access_label ORDER BY n DESC""").show(20, False)
    spark.sql("SELECT snapshot_id, committed_at, operation FROM lake.pavs.documents.snapshots "
              "ORDER BY committed_at").show(10, False)
    spark.stop()
    print(f"INGEST DONE in {time.time() - t_all:.0f}s")


if __name__ == "__main__":
    main()
