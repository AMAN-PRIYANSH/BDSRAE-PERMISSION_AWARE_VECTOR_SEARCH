"""Permission-aware search core, used by the API, the UI, the leakage tests and the benchmark.

Two layers of protection:
  1. The permission filter is applied INSIDE Milvus (filter expression or partition list),
     so forbidden documents are never even candidates.
  2. Every returned hit is checked again against the user's labels before it leaves
     this module (defence in depth). Any hit dropped here is counted as a violation:
     it means layer 1 failed, and the leakage tests treat that as a failure.
"""
import json
import os
import threading
import time
from dataclasses import dataclass, field

import numpy as np
from pymilvus import MilvusClient

from src.pavs import policy

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
COLL_FILTER = "docs_filter"        # one collection, metadata filter on access_label
COLL_PART = "docs_part"            # same data, one partition per access label
MAX_K = 100
OUTPUT_FIELDS = ["doc_id", "arxiv_id", "title", "access_label"]
AUDIT_PATH = os.environ.get("PAVS_AUDIT_LOG", "/app/logs/audit/search_audit.jsonl")


@dataclass
class SearchResult:
    hits: list
    latency_ms: float
    labels_allowed: list
    violations_blocked: int = 0
    method: str = "filter"
    extra: dict = field(default_factory=dict)


class Searcher:
    def __init__(self, uri=None, embedder=None, ef=64, audit_path=AUDIT_PATH):
        self.uri = uri or os.environ.get("PAVS_MILVUS_URI", "http://standalone:19530")
        self.client = MilvusClient(uri=self.uri)
        self._embedder = embedder
        self.ef = ef
        self.audit_path = audit_path
        self._lock = threading.Lock()
        self._loaded = set()

    def _ensure_loaded(self, name: str):
        """After a Milvus restart a collection can be 'released' (not in memory). Load it once."""
        if name in self._loaded:
            return
        state = str(self.client.get_load_state(name).get("state", ""))
        if "Loaded" not in state:
            self.client.load_collection(name)
        self._loaded.add(name)

    # ------------------------------------------------------------ embeddings
    def embed(self, text: str) -> np.ndarray:
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(MODEL_NAME, device="cpu")
        v = self._embedder.encode([text], normalize_embeddings=True)
        return np.asarray(v, dtype=np.float32)[0]

    # ------------------------------------------------------------ search
    def search(self, user: str, query: str | None = None, vector=None, k: int = 10,
               method: str = "filter", post_check: bool = True, audit: bool = True,
               consistency: str | None = None) -> SearchResult:
        t0 = time.perf_counter()
        labels = policy.allowed_labels(user)
        k = max(1, min(int(k), MAX_K))
        if not labels:                                   # unknown user / empty role: fail closed
            res = SearchResult([], (time.perf_counter() - t0) * 1000, [], method=method,
                               extra={"denied": True})
            if audit:
                self._audit(user, query, res)
            return res

        vec = np.asarray(vector, dtype=np.float32) if vector is not None else self.embed(query or "")
        kwargs = dict(data=[vec.tolist()], limit=k, output_fields=OUTPUT_FIELDS,
                      search_params={"params": {"ef": max(self.ef, k)}})
        if consistency:
            kwargs["consistency_level"] = consistency

        self._ensure_loaded(COLL_FILTER if method == "filter" else COLL_PART)
        if method == "filter":
            raw = self.client.search(COLL_FILTER, filter=policy.milvus_filter(labels), **kwargs)
        elif method == "partition":
            raw = self.client.search(COLL_PART, partition_names=[policy.partition_name(l) for l in labels],
                                     **kwargs)
        else:
            raise ValueError(f"unknown method {method}")

        hits, blocked = [], 0
        for h in raw[0]:
            e = h["entity"]
            if post_check and e.get("access_label") not in labels:
                blocked += 1
                continue
            hits.append({"doc_id": int(h.id), "arxiv_id": e.get("arxiv_id"),
                         "title": e.get("title"), "access_label": e.get("access_label"),
                         "score": float(h["distance"])})
        res = SearchResult(hits, (time.perf_counter() - t0) * 1000, labels, blocked, method)
        if audit:
            self._audit(user, query, res)
        return res

    # ------------------------------------------------------------ audit log
    def _audit(self, user, query, res: SearchResult):
        """Append one line per search. Stores counts and labels, not result titles."""
        if not self.audit_path:
            return
        rec = {"ts": time.time(), "user": user, "role": policy.USERS.get(user),
               "query_chars": len(query or ""), "method": res.method,
               "n_results": len(res.hits), "latency_ms": round(res.latency_ms, 2),
               "violations_blocked": res.violations_blocked,
               "denied": bool(res.extra.get("denied")),
               "result_labels": sorted({h["access_label"] for h in res.hits})}
        try:
            os.makedirs(os.path.dirname(self.audit_path), exist_ok=True)
            with self._lock, open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except OSError:
            pass
