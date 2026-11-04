"""Trigger the pavs_pipeline DAG through Airflow's REST API and follow it until it finishes.

Runs inside the Airflow container (called by checks\\51_run_pipeline.bat), so nothing has to be
installed on Windows. Prints each task as its state changes; exit code 0 only if the run succeeded.

Usage:  python trigger_and_wait.py [--prefix demo100k] [--skip-load] [--queries 200]
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("AIRFLOW_URL", "http://localhost:8080")
DAG = "pavs_pipeline"
ORDER = ["check_services", "ingest", "index", "quality_gate", "leak_tests", "mutation_check", "benchmark", "report"]


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="demo100k")
    ap.add_argument("--skip-load", action="store_true")
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--timeout-min", type=int, default=180)
    a = ap.parse_args()

    for _ in range(60):                       # the API server may still be starting
        try:
            token = call("POST", "/auth/token", {"username": "admin",
                                                 "password": os.environ.get("PAVS_AIRFLOW_PASSWORD", "admin")})["access_token"]
            call("GET", f"/api/v2/dags/{DAG}", token=token)    # 404 until the DAG file is parsed
            break
        except (urllib.error.URLError, KeyError, ConnectionError):
            time.sleep(5)
    else:
        sys.exit("Airflow API or the pavs_pipeline DAG is not ready")

    call("PATCH", f"/api/v2/dags/{DAG}", {"is_paused": False}, token)
    run = call("POST", f"/api/v2/dags/{DAG}/dagRuns",
               {"logical_date": None,
                "conf": {"prefix": a.prefix, "skip_load": a.skip_load, "queries": a.queries}}, token)
    run_id = run["dag_run_id"]
    print(f"triggered {DAG} run {run_id} (prefix={a.prefix}, skip_load={a.skip_load}, queries={a.queries})")
    print(f"watch it at {BASE}/dags/{DAG}/runs/{run_id}", flush=True)

    seen, t0 = {}, time.time()
    while time.time() - t0 < a.timeout_min * 60:
        time.sleep(10)
        try:
            token = call("POST", "/auth/token", {"username": "admin",
                                                 "password": os.environ.get("PAVS_AIRFLOW_PASSWORD", "admin")})["access_token"]
            tis = call("GET", f"/api/v2/dags/{DAG}/dagRuns/{run_id}/taskInstances", token=token)["task_instances"]
            state = call("GET", f"/api/v2/dags/{DAG}/dagRuns/{run_id}", token=token)["state"]
        except urllib.error.URLError as e:
            print(f"  (API not answering: {e}; retrying)", flush=True)
            continue
        for ti in sorted(tis, key=lambda t: ORDER.index(t["task_id"]) if t["task_id"] in ORDER else 99):
            if seen.get(ti["task_id"]) != ti["state"]:
                seen[ti["task_id"]] = ti["state"]
                print(f"  [{time.time() - t0:6.0f}s] {ti['task_id']:<15} {ti['state']}", flush=True)
        if state in ("success", "failed"):
            print(f"RUN {state.upper()} after {time.time() - t0:.0f}s")
            sys.exit(0 if state == "success" else 1)
    sys.exit("timed out waiting for the run")


if __name__ == "__main__":
    main()
