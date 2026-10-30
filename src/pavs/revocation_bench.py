"""Measure the leak window after a document is moved to a more restricted label.

For each trial:
  1. pick a 'public' document; check the intern can find it (search with its own vector)
  2. send a Kafka event relabelling it to 'hr-restricted' (time t0)
  3. search as the intern every 50 ms until the document disappears (time t1)
  leak window = t1 - t0
Run separately for each Milvus consistency level used by the SEARCH:
  Strong     - search waits until all writes before it are visible (slowest search, no stale reads)
  Bounded    - search may miss writes from the last few seconds (Milvus default)
  Eventually - search never waits (fastest, can be stale the longest)

The ACL stream job (src/pavs/jobs/acl_stream.py) must be running.
Run:  python -m src.pavs.revocation_bench --trials 30
Output: results/revocation_<tag>.csv and results/revocation_window_<tag>.png
"""
import argparse
import json
import os
import time
import uuid

import numpy as np
import pandas as pd
from confluent_kafka import Producer
from pymilvus import MilvusClient

from src.pavs.jobs.acl_stream import TOPIC
from src.pavs.search import COLL_FILTER, Searcher

OUT = os.environ.get("PAVS_RESULTS", "/app/results")
INTERN = "ananya.intern"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--levels", default="Strong,Bounded,Eventually")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--tag", default="demo100k")
    a = ap.parse_args()

    client = MilvusClient(uri=os.environ.get("PAVS_MILVUS_URI", "http://standalone:19530"))
    s = Searcher(audit_path=None)
    s._ensure_loaded(COLL_FILTER)
    prod = Producer({"bootstrap.servers": os.environ.get("PAVS_KAFKA", "kafka:9092"), "linger.ms": 0})
    levels = a.levels.split(",")
    candidates = client.query(COLL_FILTER, filter='access_label == "public"', output_fields=["doc_id", "vec"],
                              limit=a.trials * len(levels) * 3, consistency_level="Strong")
    rows = []
    it = iter(candidates)
    for level in levels:
        done = 0
        while done < a.trials:
            doc = next(it)
            vec = np.asarray(doc["vec"], dtype=np.float32)
            before = s.search(INTERN, vector=vec, k=5, audit=False, consistency="Strong")
            if doc["doc_id"] not in {h["doc_id"] for h in before.hits}:
                continue                      # not findable by vector even before; skip this candidate
            t0 = time.time()
            evt = {"event_id": uuid.uuid4().hex, "doc_id": int(doc["doc_id"]),
                   "new_label": "hr-restricted", "ts_ms": int(t0 * 1000)}
            prod.produce(TOPIC, key=str(doc["doc_id"]), value=json.dumps(evt))
            prod.flush(5)
            polls, gone_at, search_ms = 0, None, []
            while time.time() - t0 < a.timeout:
                r = s.search(INTERN, vector=vec, k=5, audit=False, consistency=level)
                polls += 1
                search_ms.append(r.latency_ms)
                if doc["doc_id"] not in {h["doc_id"] for h in r.hits}:
                    gone_at = time.time()
                    break
                time.sleep(0.05)
            rows.append({"consistency": level, "doc_id": int(doc["doc_id"]),
                         "leak_window_s": (gone_at - t0) if gone_at else None, "polls": polls,
                         "search_ms_median": float(np.median(search_ms)), "timed_out": gone_at is None})
            done += 1
            print(f"{level:10s} trial {done:3d}: leak window "
                  f"{rows[-1]['leak_window_s'] if gone_at else 'TIMEOUT'} s", flush=True)

    # Restore: put every relabelled document back to 'public', so later experiments see the original data.
    for r in rows:
        prod.produce(TOPIC, key=str(r["doc_id"]), value=json.dumps(
            {"event_id": uuid.uuid4().hex, "doc_id": r["doc_id"], "new_label": "public",
             "ts_ms": int(time.time() * 1000)}))
    prod.flush(10)
    print(f"restore events sent for {len(rows)} documents", flush=True)

    df = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    df.to_csv(f"{OUT}/revocation_{a.tag}.csv", index=False)
    print(df.groupby("consistency").agg(leak_p50=("leak_window_s", "median"),
                                        leak_p95=("leak_window_s", lambda x: x.quantile(0.95)),
                                        search_ms=("search_ms_median", "median"),
                                        timeouts=("timed_out", "sum")))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = {"Strong": "#2ca02c", "Bounded": "#1f77b4", "Eventually": "#d62728"}
    data = [df[df.consistency == l].leak_window_s.dropna() for l in levels]
    bp = ax.boxplot(data, tick_labels=levels, patch_artist=True)
    for patch, l in zip(bp["boxes"], levels):
        patch.set_facecolor(colors.get(l, "#999999"))
    ax.set_xlabel("Milvus consistency level used by the search")
    ax.set_ylabel("Leak window after revocation (seconds)")
    ax.set_title(f"How long a revoked document stays visible ({a.trials} trials per level)")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    p = f"{OUT}/revocation_window_{a.tag}.png"
    fig.savefig(p, dpi=150)
    print("saved", p)


if __name__ == "__main__":
    main()
