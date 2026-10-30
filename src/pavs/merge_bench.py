"""Merge benchmark CSVs from separate runs into one table and redraw the plots.

At 1M documents the laptop cannot hold Milvus (about 5.4 GB) and both FAISS indexes (about 3.2 GB) in
memory at the same time without swapping, and swapping makes every latency meaningless. So the 1M
benchmark runs twice on the same queries and the same ground truth: once for the Milvus methods
(FAISS HNSW not built) and once for the FAISS methods (Milvus collections released).

Run:  python -m src.pavs.merge_bench corpus1m results/bench_corpus1m_milvus.csv results/bench_corpus1m_faiss.csv
"""
import os
import sys

import pandas as pd

from src.pavs.plots import plot_bench

OUT = os.environ.get("PAVS_RESULTS", "/app/results")


def main():
    tag, paths = sys.argv[1], sys.argv[2:]
    df = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    df["tag"] = tag
    df = df.sort_values(["target", "method"], ascending=[False, True])
    out = f"{OUT}/bench_{tag}.csv"
    df.to_csv(out, index=False)
    print("saved", out, len(df), "rows")
    for p in plot_bench(df, OUT, tag):
        print("saved", p)


if __name__ == "__main__":
    main()
