"""Last task of the Airflow DAG: one short Markdown page that says what this run proved.

Reads   results/quality_<prefix>.json, results/airflow/leak_tests_junit.xml,
        results/bench_<tag>.csv
Writes  results/airflow/pipeline_report_<prefix>.md

Usage:  python -m src.pavs.jobs.pipeline_report --prefix demo100k --tag airflow_demo100k --run-id manual__...
"""
import argparse
import json
import os
import time
import xml.etree.ElementTree as ET

import pandas as pd

OUT = os.environ.get("PAVS_RESULTS", "/app/results")


def junit_summary(path):
    if not os.path.exists(path):
        return None
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    g = lambda k: int(suite.get(k, 0))
    return {"tests": g("tests"), "failures": g("failures"), "errors": g("errors"), "skipped": g("skipped"),
            "seconds": float(suite.get("time", 0))}


def md_table(df, digits):
    """DataFrame -> Markdown table (no extra library needed)."""
    head = "| visible share | " + " | ".join(df.columns) + " |"
    sep = "|---" * (len(df.columns) + 1) + "|"
    rows = [f"| {idx:g} | " + " | ".join(f"{v:.{digits}f}" for v in row) + " |" for idx, row in df.iterrows()]
    return "\n".join([head, sep] + rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", default="demo100k")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--run-id", default="manual")
    a = ap.parse_args()
    tag = a.tag or f"airflow_{a.prefix}"
    os.makedirs(f"{OUT}/airflow", exist_ok=True)

    lines = [f"# Pipeline run report: {a.prefix}", "",
             f"Airflow run `{a.run_id}`, written {time.strftime('%Y-%m-%d %H:%M:%S')}.", ""]

    q_path = f"{OUT}/quality_{a.prefix}.json"
    if os.path.exists(q_path):
        q = json.load(open(q_path))
        lines += ["## 1. Data-quality gate", "",
                  f"**{'PASSED' if q['passed'] else 'FAILED'}** on {q['n_docs']:,} documents.", "",
                  "| Check | Result | Detail |", "|---|---|---|"]
        lines += [f"| {c['check']} | {'pass' if c['ok'] else 'FAIL'} | {c['detail']} |" for c in q["checks"]]
        lines.append("")

    j = junit_summary(f"{OUT}/airflow/leak_tests_junit.xml")
    if j:
        passed = j["tests"] - j["failures"] - j["errors"] - j["skipped"]
        lines += ["## 2. Leakage tests", "",
                  f"{passed} of {j['tests']} passed, {j['failures'] + j['errors']} failed "
                  f"({j['seconds']:.0f} s).", ""]

    b_path = f"{OUT}/bench_{tag}.csv"
    if os.path.exists(b_path):
        df = pd.read_csv(b_path)
        piv = df.pivot_table(index="target", columns="method", values="recall_mean").sort_index(ascending=False)
        lat = df.pivot_table(index="target", columns="method", values="latency_p95_ms").sort_index(ascending=False)
        lines += ["## 3. Benchmark", "", "Recall@10 by share of the corpus the user may see:", "",
                  md_table(piv, 3), "", "p95 latency (ms):", "", md_table(lat, 1), ""]

    path = f"{OUT}/airflow/pipeline_report_{a.prefix}.md"
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"REPORT -> {path}")


if __name__ == "__main__":
    main()
