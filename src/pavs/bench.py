"""Benchmark: latency and recall@k of permission-aware search vs. selectivity.

Selectivity = share of the corpus a user may see (100% = admin, 0.1% = very restricted).

Methods compared (same vectors, same queries, same k):
  milvus_filter     Milvus HNSW, metadata filter applied inside the search
  milvus_partition  Milvus HNSW, search only the partitions of allowed labels
  faiss_prefilter   FAISS HNSW with an IDSelector (filter inside the graph search)
  faiss_postfilter  FAISS HNSW without filter, take top-k, then drop forbidden ids (naive)
  faiss_post_10x    same, but fetch 10*k candidates before dropping (common workaround)

Ground truth = exact search (FAISS flat, inner product) over ONLY the allowed documents.
recall@k = |method's top-k  intersect  exact top-k| / k   (averaged over queries)

Output: results/bench_<tag>.csv  and plots in results/
Run:    python -m src.pavs.bench --prefix demo100k --queries 500
"""
import argparse
import os
import time

import faiss
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pymilvus import MilvusClient

from src.pavs import policy
from src.pavs.search import COLL_FILTER, COLL_PART

DATA = os.environ.get("PAVS_DATA", "/app/data")
OUT = os.environ.get("PAVS_RESULTS", "/app/results")
TARGETS = [1.0, 0.5, 0.2, 0.05, 0.01, 0.001]


def label_sets_for_targets(counts: dict, total: int):
    """For each target selectivity pick a set of labels whose share is closest to it."""
    labels = sorted(counts, key=counts.get, reverse=True)
    out = []
    for target in TARGETS:
        best, best_err = None, 9.0
        # all subsets of up to 3 labels + the full set: small search space, exact enough
        cands = [tuple(labels)] + [(a,) for a in labels]
        cands += [(a, b) for i, a in enumerate(labels) for b in labels[i + 1:]]
        cands += [(a, b, c) for i, a in enumerate(labels) for j, b in enumerate(labels[i + 1:], i + 1)
                  for c in labels[j + 1:]]
        for s in cands:
            share = sum(counts[l] for l in s) / total
            err = abs(np.log(share / target))
            if err < best_err:
                best, best_err = s, err
        out.append((target, list(best), sum(counts[l] for l in best) / total))
    return out


def pct(a, q):
    return float(np.percentile(a, q))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="demo100k")
    ap.add_argument("--queries", type=int, default=500)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--ef", type=int, default=64)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--skip-faiss", action="store_true")
    ap.add_argument("--methods", default="milvus_filter,milvus_partition,faiss_prefilter,faiss_postfilter,faiss_post_10x")
    a = ap.parse_args()
    tag = a.tag or a.prefix
    methods = set(a.methods.split(","))
    os.makedirs(OUT, exist_ok=True)

    # ---------------- data (same vectors that were indexed)
    meta = pq.read_table(f"{DATA}/kaggle/{a.prefix}_meta.parquet", columns=["doc_id", "arxiv_id", "categories"]).to_pandas()
    meta["access_label"] = [policy.access_label(x, c) for x, c in zip(meta.arxiv_id, meta.categories)]
    # float16 file is memory-mapped and converted in chunks, so a float32 copy of the whole corpus
    # (1.5 GB at 1M) never exists next to the two FAISS indexes (each keeps its own 1.5 GB copy).
    X = np.load(f"{DATA}/kaggle/{a.prefix}_emb_f16.npy", mmap_mode="r")
    Q = np.load(f"{DATA}/kaggle/queries_emb_f16.npy").astype(np.float32)[:a.queries]
    Q /= np.linalg.norm(Q, axis=1, keepdims=True)
    doc_ids = meta.doc_id.to_numpy()
    assert (doc_ids == np.arange(len(doc_ids))).all(), "doc_id must equal row number"
    n, k = len(X), a.k
    counts = meta.access_label.value_counts().to_dict()
    print(f"corpus {n:,} x {X.shape[1]} | queries {len(Q)} | k={k} | ef={a.ef}")

    # ---------------- indexes
    flat = faiss.IndexFlatIP(X.shape[1])
    hnsw = None
    if not a.skip_faiss:
        hnsw = faiss.IndexHNSWFlat(X.shape[1], 16, faiss.METRIC_INNER_PRODUCT)
        hnsw.hnsw.efConstruction = 200
    t = time.time()
    for s in range(0, n, 100_000):
        chunk = np.asarray(X[s:s + 100_000], dtype=np.float32)
        chunk /= np.linalg.norm(chunk, axis=1, keepdims=True)
        flat.add(chunk)
        if hnsw is not None:
            hnsw.add(chunk)
    if hnsw is not None:
        print(f"FAISS HNSW built in {time.time() - t:.0f}s")
    del X
    import gc
    gc.collect()
    mc = MilvusClient(uri=os.environ.get("PAVS_MILVUS_URI", "http://standalone:19530"))
    for c, m in ((COLL_FILTER, "milvus_filter"), (COLL_PART, "milvus_partition")):
        if m in methods:
            mc.load_collection(c)
        else:
            mc.release_collection(c)        # not measured in this run: free Milvus memory for FAISS
    # warm-up (not measured): the first searches after loading pay one-off costs (cold caches)
    for c, m in ((COLL_FILTER, "milvus_filter"), (COLL_PART, "milvus_partition")):
        if m in methods:
            for q in Q[:100]:
                mc.search(c, data=[q.tolist()], limit=k, search_params={"params": {"ef": max(a.ef, k)}})
    if not a.skip_faiss:
        for q in Q[:100]:
            hnsw.search(q[None], k)

    label_arr = meta.access_label.to_numpy()
    rows = []
    for target, labels, sel in label_sets_for_targets(counts, n):
        allowed_ids = doc_ids[np.isin(label_arr, labels)].astype("int64")
        allowed_set = set(allowed_ids.tolist())
        sel_obj = faiss.IDSelectorBatch(allowed_ids)
        _, truth = flat.search(Q, k, params=faiss.SearchParameters(sel=sel_obj))
        print(f"\n== target {target:.1%} -> labels {labels} (actual {sel:.3%}, {len(allowed_ids):,} docs)")

        def run(name, fn):
            if name not in methods:
                return
            lat, rec = [], []
            for i, q in enumerate(Q):
                t0 = time.perf_counter()
                found = fn(q)
                lat.append((time.perf_counter() - t0) * 1000)
                tr = set(truth[i][truth[i] >= 0].tolist())
                rec.append(len(set(found) & tr) / max(1, len(tr)))
                leak = [d for d in found if d not in allowed_set]
                assert not leak, f"{name} leaked {leak[:3]}"
            r = dict(tag=tag, n_docs=n, target=target, selectivity=sel, labels="|".join(labels),
                     method=name, k=k, ef=a.ef, queries=len(Q),
                     recall_mean=float(np.mean(rec)), latency_p50_ms=pct(lat, 50),
                     latency_p95_ms=pct(lat, 95), latency_p99_ms=pct(lat, 99), qps=1000 / np.mean(lat))
            rows.append(r)
            print(f"  {name:18s} recall@{k}={r['recall_mean']:.3f}  p50={r['latency_p50_ms']:.1f}ms  "
                  f"p95={r['latency_p95_ms']:.1f}ms")

        flt = policy.milvus_filter(labels)
        parts = [policy.partition_name(l) for l in labels]
        sp = {"params": {"ef": max(a.ef, k)}}

        def milvus_filter(q):
            res = mc.search(COLL_FILTER, data=[q.tolist()], limit=k, filter=flt, search_params=sp,
                            output_fields=["doc_id"])
            return [int(h.id) for h in res[0]]

        def milvus_partition(q):
            res = mc.search(COLL_PART, data=[q.tolist()], limit=k, partition_names=parts, search_params=sp,
                            output_fields=["doc_id"])
            return [int(h.id) for h in res[0]]

        run("milvus_filter", milvus_filter)
        run("milvus_partition", milvus_partition)

        if not a.skip_faiss:
            pre_params = faiss.SearchParametersHNSW(sel=sel_obj, efSearch=max(a.ef, k))

            def faiss_pre(q):
                _, I = hnsw.search(q[None], k, params=pre_params)
                return [int(i) for i in I[0] if i >= 0]

            def make_post(mult):
                p = faiss.SearchParametersHNSW(efSearch=max(a.ef, k * mult))

                def f(q):
                    _, I = hnsw.search(q[None], k * mult, params=p)
                    return [int(i) for i in I[0] if i >= 0 and int(i) in allowed_set][:k]
                return f

            run("faiss_prefilter", faiss_pre)
            run("faiss_postfilter", make_post(1))
            run("faiss_post_10x", make_post(10))

    df = pd.DataFrame(rows)
    path = f"{OUT}/bench_{tag}.csv"
    df.to_csv(path, index=False)
    print(f"\nsaved {path}")
    from src.pavs.plots import plot_bench
    for p in plot_bench(df, OUT, tag):
        print("saved", p)


if __name__ == "__main__":
    main()
