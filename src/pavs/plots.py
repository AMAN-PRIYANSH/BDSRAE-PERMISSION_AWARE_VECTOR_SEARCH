"""Plots for the benchmark. Every plot has a title, labelled axes and one colour per method."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

COLORS = {
    "milvus_filter": "#1f77b4",
    "milvus_partition": "#2ca02c",
    "faiss_prefilter": "#9467bd",
    "faiss_postfilter": "#d62728",
    "faiss_post_10x": "#ff7f0e",
}
LABELS = {
    "milvus_filter": "Milvus: filter inside search",
    "milvus_partition": "Milvus: partition per label",
    "faiss_prefilter": "FAISS: ID filter inside search",
    "faiss_postfilter": "FAISS: search, then filter (naive)",
    "faiss_post_10x": "FAISS: fetch 10x, then filter",
}


def _axes(ax, ylabel, title):
    ax.set_xscale("log")
    ax.invert_xaxis()                      # left = sees everything, right = very restricted
    ax.set_xlabel("Selectivity: share of documents the user may see (log scale)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, which="both", alpha=0.3)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.1%}".replace(".0%", "%")))
    ax.legend(fontsize=8)


def plot_bench(df, out_dir, tag):
    n = int(df.n_docs.iloc[0])
    k = int(df.k.iloc[0])
    paths = []

    fig, ax = plt.subplots(figsize=(8, 5))
    for m, g in df.groupby("method"):
        g = g.sort_values("selectivity")
        ax.plot(g.selectivity, g.recall_mean, marker="o", color=COLORS.get(m), label=LABELS.get(m, m))
    ax.set_ylim(0, 1.05)
    _axes(ax, f"Recall@{k} (vs. exact search over allowed docs)",
          f"Recall vs. permission selectivity ({n:,} arXiv docs)")
    p = f"{out_dir}/recall_vs_selectivity_{tag}.png"
    fig.tight_layout(); fig.savefig(p, dpi=150); plt.close(fig); paths.append(p)

    fig, ax = plt.subplots(figsize=(8, 5))
    for m, g in df.groupby("method"):
        g = g.sort_values("selectivity")
        ax.plot(g.selectivity, g.latency_p95_ms, marker="o", color=COLORS.get(m), label=LABELS.get(m, m))
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(matplotlib.ticker.FixedLocator([0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500]))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    _axes(ax, "Latency p95 per query (ms, log scale)",
          f"Search latency vs. permission selectivity ({n:,} arXiv docs)")
    p = f"{out_dir}/latency_vs_selectivity_{tag}.png"
    fig.tight_layout(); fig.savefig(p, dpi=150); plt.close(fig); paths.append(p)
    return paths


if __name__ == "__main__":
    # Re-draw plots from a saved CSV:  python -m src.pavs.plots results/bench_demo100k.csv demo100k
    import sys
    import pandas as pd
    df = pd.read_csv(sys.argv[1])
    for p in plot_bench(df, sys.argv[1].rsplit("/", 1)[0], sys.argv[2]):
        print("saved", p)
