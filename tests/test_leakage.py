"""Leakage test suite: try to make the search return documents a user must not see.

Runs against the live Milvus index. Every test that passes is evidence for the report.

  1. Every role x many queries: no result outside the role's labels (raw Milvus output,
     before the second safety check)
  2. Targeted attack: search with the EXACT vector of a restricted document as an
     unauthorised user; it must not appear. The authorised user must find it (proves the
     attack is real, not trivially empty).
  3. Unknown / empty / injected user names are denied (fail closed)
  4. Filter injection text never reaches the Milvus expression
  5. Oversized k is clamped
  6. API: missing or unknown identity -> 403, same message for both

Run:  python -m pytest tests/test_leakage.py -q
"""
import os

import numpy as np
import pandas as pd
import pytest

from src.pavs import policy
from src.pavs.search import COLL_FILTER, MAX_K, Searcher

DATA = os.environ.get("PAVS_DATA", "/app/data")
N_QUERIES = int(os.environ.get("PAVS_LEAK_QUERIES", "200"))
METHODS = os.environ.get("PAVS_TEST_METHODS", "filter,partition").split(",")
RESTRICTED = ["hr-restricted", "board-restricted", "cs-confidential", "physics-confidential"]


@pytest.fixture(scope="session")
def searcher():
    return Searcher(audit_path=None)


@pytest.fixture(scope="session")
def query_vectors():
    path = f"{DATA}/kaggle/queries_emb_f16.npy"
    if os.path.exists(path):
        return np.load(path).astype(np.float32)[:N_QUERIES]
    rng = np.random.default_rng(0)
    v = rng.standard_normal((N_QUERIES, 384)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


@pytest.fixture(scope="session")
def restricted_docs(searcher):
    """Up to 20 documents per restricted label, with their stored vectors."""
    out = []
    searcher._ensure_loaded(COLL_FILTER)
    for label in RESTRICTED:
        rows = searcher.client.query(COLL_FILTER, filter=f'access_label == "{label}"',
                                     output_fields=["doc_id", "access_label", "vec"], limit=20,
                                     consistency_level="Strong")
        out += rows
    assert out, "no restricted documents found in the index"
    return out


# ------------------------------------------------------------------ 1
@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("user", list(policy.USERS))
def test_no_result_outside_role(searcher, query_vectors, user, method):
    allowed = set(policy.allowed_labels(user))
    leaks = 0
    for v in query_vectors:
        res = searcher.search(user, vector=v, k=50, method=method, post_check=False, audit=False)
        leaks += sum(1 for h in res.hits if h["access_label"] not in allowed)
    assert leaks == 0, f"{user}/{method}: {leaks} forbidden results"


# ------------------------------------------------------------------ 2
@pytest.mark.parametrize("method", METHODS)
def test_targeted_restricted_document(searcher, restricted_docs, method):
    checked = found_by_owner = 0
    for doc in restricted_docs:
        label = doc["access_label"]
        for user in policy.USERS:
            res = searcher.search(user, vector=doc["vec"], k=10, method=method, post_check=False, audit=False)
            ids = {h["doc_id"] for h in res.hits}
            if label in policy.allowed_labels(user):
                found_by_owner += doc["doc_id"] in ids
            else:
                checked += 1
                assert doc["doc_id"] not in ids, f"{user} saw {label} doc {doc['doc_id']} via {method}"
    assert checked > 0
    # The attack must be meaningful: authorised users do find these documents.
    assert found_by_owner > 0.9 * sum(1 for d in restricted_docs for u in policy.USERS
                                      if d["access_label"] in policy.allowed_labels(u))


# ------------------------------------------------------------------ 3
@pytest.mark.parametrize("user", ["", "nobody", "ROOT.ADMIN", "root.admin ", "root.admin' OR '1'='1",
                                  "intern", "admin", None])
def test_unknown_users_fail_closed(searcher, query_vectors, user):
    res = searcher.search(user, vector=query_vectors[0], k=10, audit=False)
    assert res.hits == [] and res.extra.get("denied")


# ------------------------------------------------------------------ 4
@pytest.mark.parametrize("payload", [
    'public"] or access_label != "x',
    "public] || true || [",
    'hr-restricted" or 1==1 or "',
    "*", "%", "public OR TRUE",
])
def test_filter_injection_is_rejected(payload):
    assert policy.milvus_filter([payload]) is None
    expr = policy.milvus_filter(["public", payload])
    assert expr == 'access_label in ["public"]'


# ------------------------------------------------------------------ 5
def test_k_is_clamped(searcher, query_vectors):
    res = searcher.search("root.admin", vector=query_vectors[0], k=10**6, audit=False)
    assert len(res.hits) <= MAX_K


# ------------------------------------------------------------------ 6
def test_api_identity_checks(monkeypatch, searcher):
    from fastapi.testclient import TestClient
    import src.pavs.api as api

    class _FixedEmbedder:
        def encode(self, texts, normalize_embeddings=True):
            v = np.ones((len(texts), 384), dtype=np.float32)
            return v / np.linalg.norm(v, axis=1, keepdims=True)

    searcher._embedder = _FixedEmbedder()
    monkeypatch.setattr(api, "_searcher", searcher)
    c = TestClient(api.app)
    body = {"query": "salary bands", "k": 10}
    r_missing = c.post("/search", json=body)
    r_unknown = c.post("/search", json=body, headers={"X-User": "mallory"})
    assert r_missing.status_code == r_unknown.status_code == 403
    assert r_missing.json() == r_unknown.json()          # no hint about which users exist
    assert c.post("/search", json={**body, "method": "drop"}, headers={"X-User": "ananya.intern"}).status_code == 422
    assert c.post("/search", json={**body, "k": 10**6}, headers={"X-User": "ananya.intern"}).status_code == 422
    r = c.post("/search", json=body, headers={"X-User": "ananya.intern"})
    assert r.status_code == 200
    assert {h["access_label"] for h in r.json()["results"]} <= {"public"}
