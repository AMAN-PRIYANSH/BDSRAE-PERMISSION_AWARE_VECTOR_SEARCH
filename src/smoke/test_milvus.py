"""Smoke test 1: Milvus.

Checks the four Milvus features the project depends on:
  1. HNSW index + metadata filter search (pre-filtering)
  2. Manual partitions, one per access label (partition method)
  3. Delete, then search again with Strong consistency (revocation)
  4. Filter "injection": a label is only ever taken from an allowlist

Run inside the app container:  python -m src.smoke.test_milvus
"""
import os
import time

import numpy as np
from pymilvus import DataType, MilvusClient

URI = os.environ.get("PAVS_MILVUS_URI", "http://standalone:19530")
LITE = not URI.startswith("http")          # Milvus Lite: FLAT only, no partitions
DIM = 384
N = int(os.environ.get("SMOKE_N", "20000"))
LABELS = ["public", "cs-internal", "physics-internal", "cs-confidential", "hr-restricted"]
# Share of documents per label, so the filters have very different selectivity.
LABEL_P = [0.50, 0.25, 0.20, 0.04, 0.01]

rng = np.random.default_rng(42)


def unit(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def ok(msg):
    print(f"[PASS] {msg}", flush=True)


def fail(msg):
    print(f"[FAIL] {msg}", flush=True)
    raise SystemExit(1)


def safe_label_filter(labels):
    """Build a Milvus filter only from allowlisted labels (fail closed)."""
    clean = [l for l in labels if l in LABELS]
    if not clean:
        return None
    return "access_label in [" + ", ".join(f'"{l}"' for l in clean) + "]"


def main():
    print(f"Milvus URI: {URI}  (lite={LITE})  N={N}")
    c = MilvusClient(uri=URI)
    try:
        print("Server version:", c.get_server_version())
    except Exception as e:  # Milvus Lite may not report one
        print("Server version: n/a", e)

    vecs = unit(rng.standard_normal((N, DIM)).astype("float32"))
    labels = rng.choice(LABELS, size=N, p=LABEL_P)
    rows = [{"id": i, "access_label": str(labels[i]), "vec": vecs[i].tolist()} for i in range(N)]

    # ---------- 1. HNSW + filtered search ----------
    name = "smoke_filter"
    if c.has_collection(name):
        c.drop_collection(name)
    schema = MilvusClient.create_schema(auto_id=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("access_label", DataType.VARCHAR, max_length=32)
    schema.add_field("vec", DataType.FLOAT_VECTOR, dim=DIM)
    idx = c.prepare_index_params()
    if LITE:
        idx.add_index(field_name="vec", index_type="FLAT", metric_type="COSINE")
    else:
        idx.add_index(field_name="vec", index_type="HNSW", metric_type="COSINE",
                      params={"M": 16, "efConstruction": 200})
        idx.add_index(field_name="access_label", index_type="INVERTED")
    c.create_collection(name, schema=schema, index_params=idx, consistency_level="Strong")

    t = time.time()
    for s in range(0, N, 5000):
        c.insert(name, rows[s:s + 5000])
    print(f"Inserted {N} rows in {time.time() - t:.1f}s")
    c.load_collection(name)

    q = unit(rng.standard_normal((50, DIM)).astype("float32"))
    for allowed in (["public", "cs-internal"], ["hr-restricted"]):
        flt = safe_label_filter(allowed)
        t = time.time()
        res = c.search(name, data=q.tolist(), limit=10, filter=flt,
                       output_fields=["access_label"],
                       search_params={"params": {"ef": 64}} if not LITE else {})
        ms = (time.time() - t) * 1000 / len(q)
        bad = [h for r in res for h in r if h["entity"]["access_label"] not in allowed]
        got = sum(len(r) for r in res) / len(res)
        if bad:
            fail(f"filter {allowed}: {len(bad)} forbidden documents returned (LEAK)")
        ok(f"filter {allowed}: 0 leaks, avg {got:.1f} results/query, {ms:.1f} ms/query")

    # ---------- 4. fail-closed allowlist ----------
    if safe_label_filter(['public"] or id >= 0 or access_label in ["x']) is not None:
        fail("injected label text was accepted into the filter")
    if safe_label_filter([]) is not None or safe_label_filter(["admin-typo"]) is not None:
        fail("unknown/empty role did not fail closed")
    ok("filter builder rejects injected text and unknown roles (fail-closed)")

    # ---------- 3. delete + Strong consistency ----------
    hr_ids = [i for i in range(N) if labels[i] == "hr-restricted"]
    victim = hr_ids[0]
    c.delete(name, ids=[victim])
    after = c.query(name, filter=f"id == {victim}", output_fields=["id"], consistency_level="Strong")
    if after:
        fail("deleted document is still visible with Strong consistency")
    ok("deleted document is gone immediately with Strong consistency")

    # ---------- 2. partitions per access label ----------
    if LITE:
        print("[SKIP] partitions (Milvus Lite does not support them)")
    else:
        pname = "smoke_partitions"
        if c.has_collection(pname):
            c.drop_collection(pname)
        idx2 = c.prepare_index_params()
        idx2.add_index(field_name="vec", index_type="HNSW", metric_type="COSINE",
                       params={"M": 16, "efConstruction": 200})
        c.create_collection(pname, schema=schema, index_params=idx2, consistency_level="Strong")
        for lab in LABELS:
            c.create_partition(pname, partition_name=lab.replace("-", "_"))
            part_rows = [r for r in rows if r["access_label"] == lab]
            c.insert(pname, part_rows, partition_name=lab.replace("-", "_"))
        c.load_collection(pname)
        allowed = ["public", "cs-internal"]
        res = c.search(pname, data=q.tolist(), limit=10, output_fields=["access_label"],
                       partition_names=[a.replace("-", "_") for a in allowed],
                       search_params={"params": {"ef": 64}})
        bad = [h for r in res for h in r if h["entity"]["access_label"] not in allowed]
        if bad:
            fail(f"partition search leaked {len(bad)} documents")
        ok(f"partition search over {allowed}: 0 leaks")
        c.drop_collection(pname)

    c.drop_collection(name)
    print("MILVUS SMOKE TEST: ALL PASSED")


if __name__ == "__main__":
    main()
