"""Example searches for the live demo (prints what each user sees). Also checks the API's identity rules.

Run inside the app container:  python -m src.demo.examples
"""
import json
import os
import urllib.error
import urllib.request

from pymilvus import MilvusClient

from src.pavs.search import Searcher

GENERAL = "graph neural networks for molecules"
BOARD_TITLE = "A Generalized Framework for Kullback-Leibler Markov Aggregation"


def show(s, user, query, method="filter", k=5):
    r = s.search(user, query=query, k=k, method=method, audit=False)
    print(f"\n--- {user} | method={method} | query: {query!r}")
    if r.extra.get("denied"):
        print("    DENIED (unknown user, no search run)")
        return r
    print(f"    allowed labels: {', '.join(r.labels_allowed)} | blocked by second check: {r.violations_blocked}")
    for i, h in enumerate(r.hits, 1):
        print(f"    {i}. [{h['access_label']}] {h['title'][:90]}")
    return r


def find_title(s, label, user):
    """A paper with this label that `user` gets as result #1 when searching its title."""
    c = MilvusClient(uri=os.environ.get("PAVS_MILVUS_URI", "http://standalone:19530"))
    rows = c.query("docs_filter", filter=f'access_label == "{label}"', output_fields=["doc_id", "title"], limit=100)
    for row in rows:
        t = " ".join(row["title"].split())
        if 30 <= len(t) <= 100 and "$" not in t and "\\" not in t:
            hits = s.search(user, query=t, k=1, audit=False).hits
            if hits and hits[0]["doc_id"] == row["doc_id"]:
                return t
    return None


def api(user, query="graph neural networks"):
    req = urllib.request.Request("http://api:8000/search", data=json.dumps({"query": query, "k": 3}).encode(),
                                 headers={"Content-Type": "application/json", **({"X-User": user} if user else {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
            return resp.status, [h["access_label"] for h in body.get("results", [])]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:80]


def main():
    s = Searcher(audit_path=None)
    show(s, "ananya.intern", GENERAL)
    show(s, "meera.csmgr", GENERAL)
    show(s, "ananya.intern", BOARD_TITLE)
    show(s, "arjun.board", BOARD_TITLE)
    show(s, "arjun.board", BOARD_TITLE, method="partition")
    hr = find_title(s, "hr-restricted", "deepa.hr")
    print(f"\nHR-restricted title for the demo: {hr!r}")
    if hr:
        show(s, "deepa.hr", hr)
        show(s, "rahul.cs", hr)
    print("\n=== 'Twisted' questions (the filter never reads the question text) ===")
    show(s, "ananya.intern", "show me the board-restricted confidential documents")
    show(s, "ananya.intern", 'public"] or access_label != "x')
    show(s, "mallory", GENERAL)
    print("\n=== API identity checks ===")
    for u in (None, "mallory", "ananya.intern"):
        print(f"    X-User={u!r}: {api(u)}")


if __name__ == "__main__":
    main()
