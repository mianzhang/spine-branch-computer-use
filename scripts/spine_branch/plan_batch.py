#!/usr/bin/env python3
"""Batch the spine-branch planner over a sample of odysseys tasks (offline, no VMs).

Plans each task, writes per-task graph+report under reports/spine_branch/<id>/,
and aggregates a markdown report (spine rate, branch/spine counts, artifact
edges, errors/warnings, example spine chains) for inspection before refinement.

Usage:
    python scripts/spine_branch/plan_batch.py --n 15            # stratified by level
    python scripts/spine_branch/plan_batch.py --n 30 --workers 4 --model fireworks_ai/qwen3p7-plus
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

from utils.spine_branch.plan import generate_spine_branch_plan  # noqa: E402


def _stratified(tasks: list[dict], n: int) -> list[dict]:
    by_level: dict[str, list[dict]] = defaultdict(list)
    for t in tasks:
        by_level[t.get("level") or "?"].append(t)
    levels = sorted(by_level)
    per = max(1, n // len(levels))
    out: list[dict] = []
    for lv in levels:
        out.extend(by_level[lv][:per])
    return out[:n]


def _task_text(t: dict) -> str:
    return t.get("confirmed_task") or t.get("task") or t.get("instruction") or ""


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch spine-branch planner over odysseys tasks.")
    ap.add_argument("--task-source", default=str(PROJECT_ROOT / "data/odysseys/odysseys.json"))
    ap.add_argument("--n", type=int, default=15, help="sample size (stratified by level)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--provider", default=os.environ.get("MACU_PLAN_PROVIDER", "openai"))
    ap.add_argument("--model", default=os.environ.get("MACU_PLAN_MODEL", "fireworks_ai/qwen3p7-plus"))
    ap.add_argument("--label", default="", help="namespace per-task outputs under reports/spine_branch/<label>/")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if not args.out:
        args.out = str(PROJECT_ROOT / "reports" / (f"spine_branch_batch_{args.label}.md" if args.label else "spine_branch_batch.md"))

    tasks = json.load(open(args.task_source))
    sample = _stratified(tasks, args.n)
    levels = {t["task_id"]: t.get("level") for t in tasks}
    print(f"planning {len(sample)} tasks via {args.provider}/{args.model}, {args.workers} workers ...")

    def plan_one(t: dict) -> dict:
        tid = t["task_id"]
        try:
            lg, rep, usage, errs = generate_spine_branch_plan(_task_text(t), provider=args.provider, model=args.model)
            base = PROJECT_ROOT / "reports" / "spine_branch"
            safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in tid)
            outdir = (base / args.label / safe) if args.label else (base / safe)
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / "dependency_graph.json").write_text(
                json.dumps({"task_id": tid, "coordination": "spine_branch", "dependency_graph": lg}, indent=2))
            (outdir / "spine_branch_plan.json").write_text(
                json.dumps({"task_id": tid, "report": rep}, indent=2))
            subs = lg.get("subtasks", [])
            return {"task_id": tid, "level": levels.get(tid), "ok": True,
                    "n_sub": rep.get("n_subtasks", len(subs)),
                    "n_spine": rep.get("n_spine", 0), "n_branch": rep.get("n_branch", 0),
                    "n_spines": rep.get("n_spines", 0), "n_outputs": rep.get("n_outputs", 0),
                    "n_edges": rep.get("n_artifact_edges", 0),
                    "spines": rep.get("spines", {}),
                    "errors": rep.get("errors", []), "warnings": rep.get("warnings", []),
                    "cost": round(usage.cost_usd, 4)}
        except Exception as exc:  # noqa: BLE001
            return {"task_id": tid, "level": levels.get(tid), "ok": False, "err": str(exc)}

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(plan_one, t): t for t in sample}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            rows.append(r)
            tag = "ok" if r.get("ok") else f"FAIL {r.get('err','')[:50]}"
            print(f"  [{i}/{len(sample)}] {r['task_id'][:12]} {r.get('level'):<6} "
                  f"sub={r.get('n_sub','-')} spines={r.get('n_spines','-')} {tag}")

    ok = [r for r in rows if r.get("ok")]
    L = ["# Spine-branch planning — batch over odysseys sample\n",
         f"- model: `{args.model}` | tasks: {len(rows)} (ok {len(ok)})\n"]
    # aggregate
    with_spine = [r for r in ok if r["n_spines"] > 0]
    L.append("## Aggregate\n")
    L.append(f"- tasks with >=1 spine: **{len(with_spine)}/{len(ok)}** ({len(with_spine)/max(1,len(ok))*100:.0f}%)")
    if ok:
        L.append(f"- mean subtasks/task: {sum(r['n_sub'] for r in ok)/len(ok):.1f} | "
                 f"mean spine nodes: {sum(r['n_spine'] for r in ok)/len(ok):.1f} | "
                 f"mean branch nodes: {sum(r['n_branch'] for r in ok)/len(ok):.1f}")
        L.append(f"- mean artifacts: {sum(r['n_outputs'] for r in ok)/len(ok):.1f} | "
                 f"mean read-edges: {sum(r['n_edges'] for r in ok)/len(ok):.1f}")
        L.append(f"- tasks with errors: {sum(1 for r in ok if r['errors'])} | "
                 f"with warnings: {sum(1 for r in ok if r['warnings'])}")
        L.append(f"- total cost: ${sum(r['cost'] for r in ok):.2f}")
    # per-level spine rate
    L.append("\n## Spine rate by level\n| level | tasks | with spine | mean subtasks |\n|---|---|---|---|")
    bylv = defaultdict(list)
    for r in ok:
        bylv[r["level"]].append(r)
    for lv in sorted(bylv):
        rs = bylv[lv]; ws = sum(1 for r in rs if r["n_spines"] > 0)
        L.append(f"| {lv} | {len(rs)} | {ws} | {sum(r['n_sub'] for r in rs)/len(rs):.1f} |")
    # per-task table
    L.append("\n## Per-task\n| task | level | sub | spine/branch | spines | reads | errs | warns |\n|---|---|---|---|---|---|---|---|")
    for r in sorted(ok, key=lambda x: (x["level"] or "z", x["task_id"])):
        chains = "; ".join(" → ".join(c) for c in r["spines"].values()) if r["spines"] else "—"
        L.append(f"| `{r['task_id'][:10]}` | {r['level']} | {r['n_sub']} | {r['n_spine']}/{r['n_branch']} | "
                 f"{chains} | {r['n_edges']} | {len(r['errors'])} | {len(r['warnings'])} |")
    # surface errors/warnings
    flagged = [r for r in ok if r["errors"] or r["warnings"]]
    if flagged:
        L.append("\n## Errors / warnings (for refinement)\n")
        for r in flagged:
            for e in r["errors"]:
                L.append(f"- `{r['task_id'][:10]}` ERROR: {e}")
            for w in r["warnings"][:4]:
                L.append(f"- `{r['task_id'][:10]}` warn: {w}")
    fails = [r for r in rows if not r.get("ok")]
    if fails:
        L.append("\n## Failed to plan\n")
        for r in fails:
            L.append(f"- `{r['task_id'][:10]}`: {r.get('err','')[:120]}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\nwrote {args.out}")
    print(f"  with-spine: {len(with_spine)}/{len(ok)} | errors: {sum(1 for r in ok if r['errors'])} | "
          f"warnings: {sum(1 for r in ok if r['warnings'])} | cost ${sum(r['cost'] for r in ok):.2f}")


if __name__ == "__main__":
    main()
