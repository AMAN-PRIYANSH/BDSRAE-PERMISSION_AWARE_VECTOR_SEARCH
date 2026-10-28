"""Smoke test 2: FAISS baselines.

  - Exact ground truth: IndexFlatIP + IDSelector restricted to allowed ids
  - Post-filter baseline: HNSW search without filter, then drop forbidden ids
  - Pre-filter baseline: HNSW search with IDSelector (filter inside the search)

Prints recall@10 of both HNSW methods against exact ground truth at two
selectivity levels, so we can see the effect we are going to study.

Run:  python -m src.smoke.test_faiss
"""
import os
import time

import faiss
import numpy as np

DIM = 384
N = int(os.environ.get("SMOKE_N", "20000"))
K = 10
rng = np.random.default_rng(7)


def unit(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def recall(found, truth):
    hits = sum(len(set(f[f >= 0]) & set(t[t >= 0])) for f, t in zip(found, truth))
    return hits / max(1, sum((t >= 0).sum() for t in truth))


def main():
    xb = unit(rng.standard_normal((N, DIM)).astype("float32"))
    xq = unit(rng.standard_normal((100, DIM)).astype("float32"))
    flat = faiss.IndexFlatIP(DIM)
    flat.add(xb)
    hnsw = faiss.IndexHNSWFlat(DIM, 16, faiss.METRIC_INNER_PRODUCT)
    hnsw.hnsw.efConstruction = 200
    t = time.time()
    hnsw.add(xb)
    print(f"FAISS {faiss.__version__}: HNSW built on {N} vectors in {time.time() - t:.1f}s")

    for share in (0.20, 0.01):
        allowed = np.sort(rng.choice(N, size=int(N * share), replace=False)).astype("int64")
        sel = faiss.IDSelectorBatch(allowed)
        _, truth = flat.search(xq, K, params=faiss.SearchParameters(sel=sel))

        _, pre = hnsw.search(xq, K, params=faiss.SearchParametersHNSW(sel=sel, efSearch=64))

        allowed_set = set(allowed.tolist())
        _, raw = hnsw.search(xq, K, params=faiss.SearchParametersHNSW(efSearch=64))
        post = np.array([[i if i in allowed_set else -1 for i in row] for row in raw])

        leaks = sum(1 for row in pre for i in row if i >= 0 and i not in allowed_set)
        if leaks:
            print(f"[FAIL] IDSelector returned {leaks} forbidden ids")
            raise SystemExit(1)
        print(f"[PASS] {share:>5.0%} visible | pre-filter recall@10 = {recall(pre, truth):.3f} "
              f"| post-filter recall@10 = {recall(post, truth):.3f} | leaks = 0")
    print("FAISS SMOKE TEST: ALL PASSED")


if __name__ == "__main__":
    main()
