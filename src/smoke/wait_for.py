"""Wait until every service answers, before running smoke tests.

Milvus can take 1-2 minutes to become healthy on first start.
"""
import socket
import sys
import time
import urllib.request

CHECKS = {
    "milvus (health)": ("http", "http://standalone:9091/healthz"),
    "minio": ("http", "http://minio:9000/minio/health/live"),
    "kafka": ("tcp", ("kafka", 9092)),
    "postgres": ("tcp", ("postgres", 5432)),
}


def up(kind, target):
    try:
        if kind == "http":
            with urllib.request.urlopen(target, timeout=3) as r:
                return r.status == 200
        with socket.create_connection(target, timeout=3):
            return True
    except Exception:
        return False


def main(timeout_s=300):
    start = time.time()
    pending = dict(CHECKS)
    while pending and time.time() - start < timeout_s:
        for name, (kind, target) in list(pending.items()):
            if up(kind, target):
                print(f"[READY] {name} after {time.time() - start:.0f}s", flush=True)
                pending.pop(name)
        if pending:
            time.sleep(5)
    if pending:
        print(f"[FAIL] not ready after {timeout_s}s: {', '.join(pending)}")
        sys.exit(1)
    print("ALL SERVICES READY")


if __name__ == "__main__":
    main()
