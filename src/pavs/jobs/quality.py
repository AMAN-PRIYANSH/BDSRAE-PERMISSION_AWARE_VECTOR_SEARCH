"""Data-quality gate: run after ingest + index, before anything is trusted.

The Airflow DAG stops here if a check fails, so a broken load never reaches the
tests, the benchmark or a user. Checks:

  1. counts      source parquet rows == Iceberg documents == Iceberg doc_embeddings
  2. no nulls    every document has a department and an access label
  3. vocabulary  every access label is one the policy knows (an unknown label is a leak risk:
                 no role grants it, but admin tooling might treat it as "public")
  4. shares      board / hr / confidential / internal / public shares are what the labelling
                 rule promises (z-score test, so it works at 100k and at 1M)
  5. embeddings  every vector has 384 numbers and no NaN
  6. index sync  Milvus docs_filter and docs_part hold exactly the lake's rows, label by label
                 (the index is derived from the lake; any difference means a stale or partial load)

Output: results/quality_<prefix>.json  (exit code 1 if any check fails)
Usage:  python -m src.pavs.jobs.quality --prefix demo100k
"""
import argparse
import json
import math
import os
import sys
import time

import pyarrow.parquet as pq
from pymilvus import MilvusClient

from src.common.spark_packages import get_spark
from src.pavs import policy
from src.pavs.search import COLL_FILTER, COLL_PART

DATA = os.environ.get("PAVS_DATA", "/app/data")
OUT = os.environ.get("PAVS_RESULTS", "/app/results")
DIM = 384

# Share of documents per tier, from the labelling rule in policy.py (bucket = crc32 % 10000).
EXPECTED_SHARE = {"board": 0.001, "hr": 0.009, "confidential": 0.09, "internal": 0.40, "public": 0.50}
MAX_Z = 5.0


def tier(label: str) -> str:
    if label == "board-restricted":
        return "board"
    if label == "hr-restricted":
        return "hr"
    if label.endswith("-confidential"):
        return "confidential"
    if label.endswith("-internal"):
        return "internal"
    return "public"


class Report:
    def __init__(self):
        self.checks = []

    def add(self, name, ok, detail):
        self.checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    @property
    def ok(self):
        return all(c["ok"] for c in self.checks)


def lake_checks(rep, prefix, master):
    spark = get_spark("pavs-quality", master=master, driver_memory="2g")
    try:
        src_rows = pq.ParquetFile(f"{DATA}/kaggle/{prefix}_meta.parquet").metadata.num_rows
        n_docs = spark.table("lake.pavs.documents").count()
        n_emb = spark.table("lake.pavs.doc_embeddings").count()
        rep.add("counts", src_rows == n_docs == n_emb,
                f"source {src_rows:,} | documents {n_docs:,} | doc_embeddings {n_emb:,}")

        nulls = spark.sql("""SELECT count(*) AS n FROM lake.pavs.documents
                             WHERE access_label IS NULL OR dept IS NULL OR doc_id IS NULL""").first().n
        rep.add("no_nulls", nulls == 0, f"{nulls} rows with a missing id, department or label")

        per_label = {r.access_label: r.n for r in spark.sql(
            "SELECT access_label, count(*) AS n FROM lake.pavs.documents GROUP BY access_label").collect()}
        unknown = sorted(set(per_label) - set(policy.LABELS))
        rep.add("label_vocabulary", not unknown,
                f"unknown labels: {unknown}" if unknown else f"{len(per_label)} labels, all known to the policy")

        tiers = {}
        for label, n in per_label.items():
            tiers[tier(label)] = tiers.get(tier(label), 0) + n
        worst = 0.0
        shares = {}
        for t, p in EXPECTED_SHARE.items():
            obs = tiers.get(t, 0)
            z = abs(obs - n_docs * p) / math.sqrt(n_docs * p * (1 - p)) if n_docs else float("inf")
            worst = max(worst, z)
            shares[t] = {"observed": round(obs / max(n_docs, 1), 5), "expected": p, "z": round(z, 2)}
        rep.add("label_shares", worst <= MAX_Z, f"largest deviation z={worst:.2f} (limit {MAX_Z})")

        bad_emb = spark.sql(f"""SELECT count(*) AS n FROM lake.pavs.doc_embeddings
                                WHERE embedding IS NULL OR size(embedding) != {DIM}
                                   OR exists(embedding, x -> isnan(x))""").first().n
        rep.add("embeddings", bad_emb == 0, f"{bad_emb} vectors missing, wrong length or NaN")

        sample = spark.sql("SELECT arxiv_id, categories, access_label FROM lake.pavs.documents "
                           "TABLESAMPLE (2 PERCENT)").limit(5000).collect()
        mism = sum(r.access_label != policy.access_label(r.arxiv_id, r.categories) for r in sample)
        rep.add("label_rule", mism == 0, f"{mism} of {len(sample)} sampled labels differ from policy.py")
        return n_docs, per_label, shares
    finally:
        spark.stop()


def milvus_count(client, coll, flt="", partitions=None):
    kw = {"partition_names": partitions} if partitions else {}
    return client.query(coll, filter=flt, output_fields=["count(*)"], consistency_level="Strong", **kw)[0]["count(*)"]


def index_checks(rep, n_docs, per_label):
    client = MilvusClient(uri=os.environ.get("PAVS_MILVUS_URI", "http://standalone:19530"))
    for c in (COLL_FILTER, COLL_PART):
        if not client.has_collection(c):
            rep.add(f"milvus_{c}", False, "collection missing")
            return
        client.load_collection(c)
    nf, np_ = milvus_count(client, COLL_FILTER), milvus_count(client, COLL_PART)
    rep.add("milvus_row_count", nf == np_ == n_docs,
            f"lake {n_docs:,} | {COLL_FILTER} {nf:,} | {COLL_PART} {np_:,}")
    diffs = []
    for label in policy.LABELS:
        lake = per_label.get(label, 0)
        f = milvus_count(client, COLL_FILTER, f'access_label == "{label}"')
        p = milvus_count(client, COLL_PART, partitions=[policy.partition_name(label)])
        if not lake == f == p:
            diffs.append(f"{label}: lake {lake} filter {f} partition {p}")
    rep.add("milvus_per_label", not diffs,
            "; ".join(diffs) if diffs else f"all {len(policy.LABELS)} labels match in both collections")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="demo100k")
    ap.add_argument("--master", default="local[2]")
    a = ap.parse_args()
    t = time.time()
    rep = Report()
    n_docs, per_label, shares = lake_checks(rep, a.prefix, a.master)
    index_checks(rep, n_docs, per_label)

    os.makedirs(OUT, exist_ok=True)
    path = f"{OUT}/quality_{a.prefix}.json"
    with open(path, "w") as f:
        json.dump({"prefix": a.prefix, "passed": rep.ok, "n_docs": n_docs, "per_label": per_label,
                   "tier_shares": shares, "checks": rep.checks, "seconds": round(time.time() - t, 1),
                   "finished_at": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=2)
    print(f"QUALITY {'PASSED' if rep.ok else 'FAILED'}: "
          f"{sum(c['ok'] for c in rep.checks)}/{len(rep.checks)} checks -> {path}")
    sys.exit(0 if rep.ok else 1)


if __name__ == "__main__":
    main()
