#!/usr/bin/env python3
"""SBP ablation figure: one 1x3 panel (Single-agent | MACU | Spine-Branch).

Each panel is a Pareto arrow plot: x = CUA tokens per task (M, cost),
y = rubric avg. (%, quality); each backbone is an arrow from SBP-off (hollow) ->
SBP-on (filled). Up-and-left = SBP is a Pareto improvement (cheaper AND better).
Numbers are per-task, hardcoded from the odysseys45 SBP ablation runs.
Style matches plot_failure_themes.py.

    python scripts/plot_sbp_pareto.py   # -> reports/sbp_ablation_merged.png
"""
from __future__ import annotations
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

BB = ["Qwen3.6-27B", "gpt-5.4-mini", "Qwen3.7-Plus"]
COLOR = ["#4C78A8", "#E39A3B", "#54A24B"]

# (cost_off, qual_off, cost_on, qual_on) per backbone, order = BB
DATA = {
    "spine":  [(5.27, 72.5, 5.15, 75.1), (8.91, 78.8, 7.60, 83.1), (5.55, 84.5, 4.58, 90.6)],
    "macu":   [(5.63, 67.6, 6.58, 69.8), (10.30, 74.8, 5.16, 79.1), (6.78, 80.2, 6.01, 82.6)],
    "single": [(2.44, 58.5, 2.30, 59.2), (2.58, 59.6, 2.58, 51.9), (2.82, 73.6, 2.67, 76.4)],
}
# backbone-label offsets (pts), tuned for the shared-y merged panels (order = BB)
LOFF = {
    "single": [(8, 6), (8, -13), (8, 6)],
    "macu":   [(8, 4), (4, -15), (6, 9)],
    "spine":  [(8, 6), (-2, 12), (11, -2)],
}

plt.rcParams.update({
    "font.size": 15, "font.family": "sans-serif",
    "axes.titlesize": 17, "axes.labelsize": 16,
    "xtick.labelsize": 13, "ytick.labelsize": 13, "legend.fontsize": 14,
    "axes.spines.top": True, "axes.spines.right": True,
    "axes.linewidth": 0.9, "axes.edgecolor": "#333333",
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def main() -> None:
    order = [("single", "Single-agent"), ("macu", "MACU"), ("spine", "Spine-Branch")]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), sharey=True)
    for ax, (method, title) in zip(axes, order):
        for i, bb in enumerate(BB):
            c = COLOR[i]; xo, yo, xn, yn = DATA[method][i]
            ax.annotate("", xy=(xn, yn), xytext=(xo, yo),
                        arrowprops=dict(arrowstyle="-|>", color=c, lw=2.4, shrinkA=5, shrinkB=5, mutation_scale=15))
            ax.scatter([xo], [yo], s=70, facecolor="white", edgecolor=c, linewidth=1.7, zorder=4)
            ax.scatter([xn], [yn], s=75, color=c, edgecolor="white", linewidth=1.0, zorder=4)
            ax.annotate(bb, xy=(xn, yn), textcoords="offset points", xytext=LOFF[method][i], fontsize=11, color=c)
        ax.grid(color="#dddddd", lw=0.7, zorder=0); ax.set_axisbelow(True)
        ax.margins(x=0.18, y=0.16); ax.set_ylim(48, 96)
        ax.set_title(title, fontsize=13, fontweight="bold", pad=8)
        ax.set_xlabel("CUA tokens per task (M)")
        ax.tick_params(length=3, width=0.8, colors="#333333")
    axes[0].set_ylabel("Rubric avg. (%)")
    leg = [Line2D([0], [0], marker="o", color="#555555", markerfacecolor="white", markeredgecolor="#555555", lw=0, ms=9, label="SBP off"),
           Line2D([0], [0], marker="o", color="#555555", markerfacecolor="#555555", markeredgecolor="white", lw=0, ms=9, label="SBP on")]
    fig.legend(handles=leg, loc="upper center", ncol=2, frameon=False, fontsize=14, bbox_to_anchor=(0.5, 1.06))
    fig.tight_layout()
    fig.savefig("reports/sbp_ablation_merged.png", dpi=160, bbox_inches="tight")
    print("saved: reports/sbp_ablation_merged.png")


if __name__ == "__main__":
    main()
