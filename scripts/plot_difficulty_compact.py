#!/usr/bin/env python3
"""Compact SINGLE-panel version of the SR-vs-difficulty figure, for a half-textwidth
slot in a 1x2 paper grid (pairs with plot_sba_ablation.py).

Collapses the 3 backbone panels into ONE axes by averaging Success Rate across the
three backbones (equal weight per backbone) → 3 lines (Single / MACU / Spine-Branch)
vs Easy/Medium/Hard. Shows the headline result: the coordination advantage widens
as tasks get harder.

Uses the MEASURED Spine-Branch+SBA numbers for every backbone (no counterfactual in
the average). Numbers hardcoded from the Odysseys-200 merged runs.

Usage:
    python scripts/plot_difficulty_compact.py     # -> reports/odysseys200_difficulty_compact.png
"""
from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LEVELS = ["Easy", "Medium", "Hard"]
COLOR = {"single": "#2a78d6", "MACU": "#eb6834", "Spine": "#1baf7a"}
MARKER = {"single": "o", "MACU": "s", "Spine": "D"}
LABEL = {"single": "Single-agent", "MACU": "MACU", "Spine": "Spine-Branch"}

# Per-backbone SR by level (measured Odysseys-200; gpt Spine = measured +SBA, not counterfactual)
SR = {
    "qwen3.6-27B":  {"single": [51.1, 26.1, 11.9], "MACU": [51.1, 41.3, 13.8], "Spine": [68.9, 60.9, 26.6]},
    "gpt-5.4-mini": {"single": [73.3, 65.2, 19.3], "MACU": [84.4, 69.6, 43.1], "Spine": [80.0, 63.0, 45.0]},
    "qwen3.7-Plus": {"single": [75.6, 56.5, 45.9], "MACU": [66.7, 54.3, 42.2], "Spine": [77.8, 60.9, 65.1]},
}
BB = list(SR)


def avg(method):
    return [sum(SR[b][method][i] for b in BB) / len(BB) for i in range(3)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/odysseys200_difficulty_compact.png")
    args = ap.parse_args()

    plt.rcParams.update({
        "font.family": "serif", "font.serif": ["DejaVu Serif", "Times New Roman", "Times"],
        "font.size": 9, "axes.edgecolor": "#555555", "axes.linewidth": 0.6,
        "text.color": "#111111", "axes.labelcolor": "#111111",
        "xtick.color": "#333333", "ytick.color": "#333333",
        "figure.facecolor": "white", "axes.facecolor": "white",
    })

    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    x = range(3)
    for m in ["single", "MACU", "Spine"]:
        ys = avg(m)
        ax.plot(x, ys, "-", color=COLOR[m], lw=2.0, marker=MARKER[m], ms=6.5,
                markerfacecolor=COLOR[m], markeredgecolor="white", markeredgewidth=1.0,
                zorder=3, label=LABEL[m])
        ax.annotate(f"{ys[-1]:.0f}", (2, ys[-1]), textcoords="offset points",
                    xytext=(6, 0), fontsize=8.5, color=COLOR[m], fontweight="bold", va="center", clip_on=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#ebebeb", lw=0.7, zorder=0)
    ax.set_axisbelow(True)
    ax.set_xticks(list(x)); ax.set_xticklabels(LEVELS)
    ax.set_xlim(-0.2, 2.4); ax.set_ylim(0, 90)
    ax.set_xlabel("Task difficulty  →", fontweight="bold")
    ax.set_ylabel("Success rate  [%]  (mean over 3 backbones)", fontweight="bold")
    ax.tick_params(length=2, width=0.5)
    ax.legend(loc="upper right", frameon=False, fontsize=8.5, handlelength=1.5, labelspacing=0.3)
    fig.tight_layout(pad=0.3)
    fig.savefig(args.out, dpi=300, bbox_inches="tight")
    print("saved:", args.out)
    print("averaged SR:", {m: [round(v, 1) for v in avg(m)] for m in ["single", "MACU", "Spine"]})


if __name__ == "__main__":
    main()
