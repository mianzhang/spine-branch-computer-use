#!/usr/bin/env python3
"""Success Rate (and macro) vs Odysseys task difficulty (easy/medium/hard),
one panel per CUA backbone, one line per coordination method.

Ultra-compact layout for ICLR / LaTeX templates (5.5" width, 1.6" height, clean x-ticks).

Usage:
    python scripts/plot_sr_vs_difficulty.py        # -> reports/odysseys200_{sr,macro}_vs_difficulty.{pdf,png}
"""
from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

LEVELS = ["Easy", "Medium", "Hard"]
ORDER = ["qwen3.6-27B", "gpt-5.4-mini", "qwen3.7-Plus"]

# Clean display titles for subplots
TITLE_MAP = {
    "qwen3.6-27B": "Qwen3.6-27B",
    "gpt-5.4-mini": "GPT-5.4-mini",
    "qwen3.7-Plus": "Qwen3.7-Plus",
}

# CVD-safe color palette
COLOR = {"single": "#2a78d6", "MACU": "#eb6834", "Spine": "#1baf7a"}
MARKER = {"single": "o", "MACU": "s", "Spine": "D"}
LABEL = {"single": "Single-agent", "MACU": "MACU", "Spine": "Spine-Branch"}

SR = {
    "qwen3.6-27B":  {"single": [51.1, 26.1, 11.9], "MACU": [51.1, 41.3, 13.8], "Spine": [68.9, 60.9, 26.6]},
    "gpt-5.4-mini": {"single": [73.3, 65.2, 19.3], "MACU": [84.4, 69.6, 43.1], "Spine": [82.2, 71.7, 54.1]},
    "qwen3.7-Plus": {"single": [75.6, 56.5, 45.9], "MACU": [66.7, 54.3, 42.2], "Spine": [77.8, 60.9, 65.1]},
}
MACRO = {  # fractions, plotted x100
    "qwen3.6-27B":  {"single": [.764, .562, .304], "MACU": [.743, .745, .367], "Spine": [.895, .871, .485]},
    "gpt-5.4-mini": {"single": [.892, .827, .346], "MACU": [.928, .852, .552], "Spine": [.917, .865, .638]},
    "qwen3.7-Plus": {"single": [.883, .757, .674], "MACU": [.885, .857, .616], "Spine": [.926, .858, .834]},
}


def _style():
    """Set compact Matplotlib parameters tailored for ICLR standard textwidth (5.5in)."""
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["DejaVu Serif", "Times New Roman", "Times"],
        "font.size": 8.0,
        "axes.titlesize": 8.5,
        "axes.labelsize": 8.0,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 8.0,
        "axes.edgecolor": "#555555",
        "axes.linewidth": 0.6,
        "axes.labelcolor": "#111111",
        "text.color": "#111111",
        "xtick.color": "#333333",
        "ytick.color": "#333333",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-prefix", default="reports/odysseys200")
    args = ap.parse_args()
    _style()

    x = list(range(3))

    metrics = [
        ("SR", SR, "Success Rate (%)", "sr"),
        ("macro", MACRO, "Macro Score (%)", "macro"),
    ]

    for metric_name, table, ylab, tag in metrics:
        # Ultra-compact height (1.6 inches) to conserve paper vertical space
        fig, axes = plt.subplots(1, 3, figsize=(5.5, 1.6), sharey=True)

        handles, labels = [], []

        for i, (ax, bb) in enumerate(zip(axes, ORDER)):
            for m in ["single", "MACU", "Spine"]:
                ys = table[bb][m]
                if metric_name == "macro":
                    ys = [v * 100 for v in ys]

                line, = ax.plot(
                    x, ys, "-",
                    color=COLOR[m],
                    lw=1.5,
                    zorder=3,
                    alpha=0.95,
                    marker=MARKER[m],
                    ms=4.5,
                    markerfacecolor=COLOR[m],
                    markeredgecolor="white",
                    markeredgewidth=0.8,
                    label=LABEL[m],
                )

                if i == 0 and m not in labels:
                    handles.append(line)
                    labels.append(LABEL[m])

                # Annotate final value on the hard-task point
                ax.annotate(
                    f"{ys[-1]:.0f}",
                    (2, ys[-1]),
                    textcoords="offset points",
                    xytext=(4, 0),
                    fontsize=7.0,
                    color=COLOR[m],
                    fontweight="bold",
                    va="center",
                    clip_on=False,
                )

            # Styling individual subplots
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
            ax.grid(axis="y", color="#eaeaea", lw=0.6, zorder=0)
            ax.set_axisbelow(True)
            ax.set_title(TITLE_MAP.get(bb, bb), fontweight="bold", pad=4)
            ax.set_xticks(x)
            ax.set_xticklabels(LEVELS)  # Clean labels: Easy, Medium, Hard
            ax.set_xlim(-0.25, 2.35)
            ax.set_ylim(0, 102)
            ax.tick_params(length=2, width=0.5)

        axes[0].set_ylabel(ylab, fontweight="bold")

        # Top legend tightly anchored above figure
        fig.legend(
            handles,
            labels,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.15),
            ncol=3,
            frameon=False,
            handlelength=1.4,
            columnspacing=1.5,
        )

        fig.tight_layout(pad=0.2)

        # Save both PDF and high-res PNG
        # out_pdf = f"{args.out_prefix}_{tag}_vs_difficulty.pdf"
        out_png = f"{args.out_prefix}_{tag}_vs_difficulty.png"

        # fig.savefig(out_pdf, format="pdf", bbox_inches="tight")
        fig.savefig(out_png, dpi=300, bbox_inches="tight")
        plt.close(fig)

        # print(f"Saved: {out_pdf} and {out_png}")


if __name__ == "__main__":
    main()