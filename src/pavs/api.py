"""Search API (FastAPI).

POST /search   {"query": "...", "k": 10, "method": "filter" | "partition"}
               header X-User: <user name>
GET  /users    demo users and their roles
GET  /health

Identity comes from the X-User header. In a real deployment this would be a verified
token from single sign-on (SSO); here it stands in for one, and that is listed as a
limitation in the report. The server, never the client, decides which labels a user gets.

Run:  uvicorn src.pavs.api:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from src.pavs import policy
from src.pavs.search import MAX_K, Searcher

app = FastAPI(title="Permission-Aware Vector Search")
_searcher = None


def searcher() -> Searcher:
    global _searcher
    if _searcher is None:
        _searcher = Searcher()
    return _searcher


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=10, ge=1, le=MAX_K)
    method: str = Field(default="filter", pattern="^(filter|partition)$")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/users")
def users():
    return {u: {"role": r, "labels": policy.ROLES[r]} for u, r in policy.USERS.items()}


@app.post("/search")
def search(req: SearchRequest, x_user: str = Header(default="")):
    if x_user not in policy.USERS:
        # Same response for "no such user" and "no header": do not reveal which users exist.
        raise HTTPException(status_code=403, detail="access denied")
    res = searcher().search(x_user, query=req.query, k=req.k, method=req.method)
    return {"user": x_user, "role": policy.USERS[x_user], "labels_allowed": res.labels_allowed,
            "latency_ms": round(res.latency_ms, 1), "method": res.method,
            "results": res.hits}
