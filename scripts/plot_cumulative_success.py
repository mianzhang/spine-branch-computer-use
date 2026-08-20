#!/usr/bin/env python3
"""Plot cumulative success rate (all-rubric-pass) vs agent steps — one or more runs.

For each task we take (a) the agent-step count it used and (b) whether it was a
FULL success (all rubrics passed, i.e. average_rubric_score >= 1.0). The curve
answers: "if agents were capped at S steps, what fraction of the whole task set
would have fully succeeded?" — i.e.

    cumulative_SR(S) = #{tasks: full-success AND steps_used <= S} / N_total

It rises monotonically with S and plateaus at the run's overall perfect rate.
Each fully-successful task is credited at the step count it actually used.

"Agent steps" = CUA decision steps, counted from the "<n> in trajectory" markers
the runner logs per step, summed across ALL subtasks of the task (so it's the
system's TOTAL steps for single- and multi-agent alike — a fair effort axis).

Pass several run dirs to overlay their curves on one axis (e.g. single-agent vs
MACU-replan vs spine-branch for the same CUA).

Usage:
    python scripts/plot_cumulative_success.py runs/<run>
    python scripts/plot_cumulative_success.py runs/A runs/B runs/C \
        --labels "single-agent,MACU replan5,spine-branch" --out reports/compare.png
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

_PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf"]


def _smooth_curve(xs, ys, x_max, n=600, frac=0.03):
    """Resample the cumulative step-curve onto a dense grid and Gaussian-smooth it.

    The cumulative curve is monotone non-decreasing; convolving with a
    non-negative kernel keeps it monotone, and edge-padding preserves both the
    start (0) and the plateau. Returns (grid_x, smoothed_y)."""
    # collapse duplicate x (multiple tasks at the same step count) to the last
    # cumulative value so the x-grid is strictly increasing for np.interp.
    xu, yu = [], []
    for x, y in zip(xs, ys):
        if xu and x == xu[-1]:
            yu[-1] = max(yu[-1], y)
        else:
            xu.append(float(x)); yu.append(float(y))
    xu, yu = np.asarray(xu), np.asarray(yu)
    grid = np.linspace(0, max(x_max, 1), n)
    ylin = np.interp(grid, xu, yu, left=yu[0], right=yu[-1])
    sigma = max(1.0, frac * n)
    r = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    ysm = np.convolve(np.pad(ylin, (r, r), mode="edge"), k, mode="valid")
    return grid, ysm


def resolve_eval_json(run_dir: Path, override: str | None) -> Path:
    if override:
        return Path(override)
    ft = run_dir / "odysseys_eval_fulltext.json"
    return ft if ft.exists() else run_dir / "odysseys_eval.json"


def count_agent_steps(task_dir: Path) -> int:
    """CUA decision steps across all of this task's subtasks (via subprocess.log
    markers — final_traj has no subprocess.log, so it is not double-counted)."""
    n = 0
    for log in glob.glob(str(task_dir / "**" / "subprocess.log"), recursive=True):
        try:
            n += open(log, errors="ignore").read().count(" in trajectory")
        except OSError:
            pass
    return n


def _task_credit(task: dict, metric: str) -> float:
    """Per-task contribution to the cumulative curve.

    - success: 1.0 if the task passed ALL rubrics (avg >= 1), else 0.
    - macro  : the task's average_rubric_score (pass-fraction) in [0, 1].
    """
    avg = task.get("average_rubric_score")
    avg = float(avg) if isinstance(avg, (int, float)) else 0.0
    if metric == "macro":
        return max(0.0, min(1.0, avg))
    is_perfect = task.get("perfect") in (True, "True", "true") or avg >= 1.0
    return 1.0 if is_perfect else 0.0


def compute_curve(run_dir: Path, eval_override: str | None, metric: str):
    """Return (xs, ys, n_total, plateau_pct, median_steps, skipped) for one run."""
    ev_path = resolve_eval_json(run_dir, eval_override)
    if not ev_path.exists():
        raise SystemExit(f"No eval json for {run_dir.name} ({ev_path}). Score the run first.")
    data = json.load(open(ev_path))
    tasks = data.get("tasks") if isinstance(data, dict) else data
    # Keep the FULL task-set denominator: every task with an eval record + a run
    # dir counts (so the plateau equals the run's true rate). Tasks that logged no
    # steps (crashed early) are credited at 0 steps — they count toward the
    # denominator with whatever partial credit they earned (0 for full crashes).
    pts: list[tuple[int, float]] = []
    skipped = 0
    for t in tasks:
        td = run_dir / t["task_id"]
        if not td.is_dir():
            skipped += 1
            continue
        pts.append((count_agent_steps(td), _task_credit(t, metric)))
    if not pts:
        raise SystemExit(f"{run_dir.name}: no tasks with an eval record and a run dir.")
    n_total = len(pts)
    pts.sort(key=lambda p: p[0])
    xs, ys, cum = [0], [0.0], 0.0
    for steps, credit in pts:
        cum += credit
        xs.append(steps)
        ys.append(cum / n_total * 100.0)
    plateau_pct = sum(c for _, c in pts) / n_total * 100.0
    median_steps = pts[len(pts) // 2][0]
    return xs, ys, n_total, plateau_pct, median_steps, skipped


def main() -> None:
    ap = argparse.ArgumentParser(description="Cumulative success rate vs agent steps (one or more runs).")
    ap.add_argument("run_dirs", nargs="+", help="One or more run directories to overlay")
    ap.add_argument("--labels", help="Comma-separated legend labels (match run order; "
                                     "default: dir name minus 'odysseys45_')")
    ap.add_argument("--eval-json", help="Override eval json (single-run only)")
    ap.add_argument("--metric", choices=["success", "macro"], default="success",
                    help="success = cumulative all-rubric-pass rate (default); "
                         "macro = cumulative mean per-task rubric pass-fraction")
    ap.add_argument("--out", help="Output PNG (default: reports/cumulative_<metric>[_compare].png)")
    ap.add_argument("--title", help="Plot title")
    ap.add_argument("--smooth", type=float, default=0.03,
                    help="Gaussian smoothing strength as a fraction of the x-range "
                         "(0 = raw staircase step plot; default 0.03).")
    args = ap.parse_args()

    run_dirs = [Path(d).resolve() for d in args.run_dirs]
    labels = ([s.strip() for s in args.labels.split(",")] if args.labels
              else [d.name.replace("odysseys45_", "") for d in run_dirs])
    if len(labels) != len(run_dirs):
        raise SystemExit(f"--labels count ({len(labels)}) != run count ({len(run_dirs)})")

    metric = args.metric
    ylab = ("cumulative success rate  (all rubrics pass)  [%]" if metric == "success"
            else "cumulative macro rubric accuracy  (mean pass-fraction)  [%]")
    default_title = ("Cumulative full-success vs agent steps" if metric == "success"
                     else "Cumulative macro rubric accuracy vs agent steps")
    plat_word = "perfect" if metric == "success" else "macro"

    fig, ax = plt.subplots(figsize=(9, 5.5))
    max_y = 5.0
    # compute every curve first so smoothing can share one global x-grid
    ev_override = args.eval_json if len(run_dirs) == 1 else None
    curves = [compute_curve(rd, ev_override, metric) for rd in run_dirs]
    x_max = max((c[0][-1] for c in curves if c[0]), default=1)
    print(f"{'label':<44} {'tasks':>5} {plat_word:>14} {'median_steps':>13}")
    for i, (lbl, (xs, ys, n_total, plateau, median_steps, skipped)) in enumerate(zip(labels, curves)):
        max_y = max(max_y, plateau)
        color = _PALETTE[i % len(_PALETTE)]
        if args.smooth > 0:
            gx, gy = _smooth_curve(xs, ys, x_max, frac=args.smooth)
            ax.plot(gx, gy, lw=2.2, color=color, label=f"{lbl}  ({plateau:.1f}%)")
        else:
            ax.step(xs, ys, where="post", lw=2, color=color, label=f"{lbl}  ({plateau:.1f}%)")
        ax.axhline(plateau, ls="--", lw=0.8, color=color, alpha=0.4)
        print(f"{lbl:<44} {n_total:>5} {f'{plateau:.1f}%':>14} {median_steps:>13}"
              + (f"   [skipped {skipped}]" if skipped else ""))

    ax.set_xlabel("agent step budget  (CUA decision steps, summed over subtasks)")
    ax.set_ylabel(ylab)
    ax.set_title(args.title or default_title)
    ax.set_xlim(left=0)
    ax.set_ylim(0, max(5, max_y * 1.15))
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()

    tag = "success" if metric == "success" else "macro"
    if args.out:
        out = args.out
    elif len(run_dirs) == 1:
        out = str(Path(__file__).resolve().parent.parent / "reports" / f"{run_dirs[0].name}_cumulative_{tag}.png")
    else:
        out = str(Path(__file__).resolve().parent.parent / "reports" / f"cumulative_{tag}_compare.png")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
