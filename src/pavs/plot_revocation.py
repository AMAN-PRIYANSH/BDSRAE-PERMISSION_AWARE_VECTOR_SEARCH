"""One figure comparing the revocation leak window of the three stream-job versions.

Run:  python -m src.pavs.plot_revocation            (reads results/revocation_demo100k*.csv)
Output: results/revocation_comparison.png
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

OUT = os.environ.get("PAVS_RESULTS", "/app/results")
RUNS = [("demo100k", "Default\n(1 batch, 200 partitions)", "#d62728"),
        ("demo100k_tuned", "Tuned\n(4 partitions)", "#ff7f0e"),
        ("demo100k_split", "Split\n(fast Milvus path)", "#2ca02c")]
LEVELS = ["Strong", "Bounded", "Eventually"]


def main():
    fig, ax = plt.subplots(figsize=(8, 4.6))
    width = 0.25
    for i, (tag, name, color) in enumerate(RUNS):
        p = f"{OUT}/revocation_{tag}.csv"
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p)
        data = [d[d.consistency == l].leak_window_s.dropna() for l in LEVELS]
        pos = [j + (i - 1) * width for j in range(len(LEVELS))]
        bp = ax.boxplot(data, positions=pos, widths=width * 0.85, patch_artist=True, showfliers=True)
        for box in bp["boxes"]:
            box.set_facecolor(color)
            box.set_alpha(0.85)
        for med in bp["medians"]:
            med.set_color("black")
        ax.plot([], [], color=color, linewidth=8, label=name.replace("\n", " "))
    ax.set_xticks(range(len(LEVELS)))
    ax.set_xticklabels(LEVELS)
    ax.set_xlabel("Milvus consistency level used by the search")
    ax.set_ylabel("Leak window after revocation (seconds)")
    ax.set_title("How long a revoked document stays visible: three versions of the stream job")
    ax.set_ylim(bottom=0)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(title="Stream job version", fontsize=8, title_fontsize=8, loc="upper right")
    fig.tight_layout()
    p = f"{OUT}/revocation_comparison.png"
    fig.savefig(p, dpi=150)
    print("saved", p)


if __name__ == "__main__":
    main()
