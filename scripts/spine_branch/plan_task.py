#!/usr/bin/env python3
"""Offline spine-and-branch planner harness — plan ONE task, no executor, no VMs.

Runs decompose -> type -> legalize and writes the legalized graph + legalization
report, then prints a summary (spines, branches, downgrades, out-of-scope).

Usage:
    python scripts/spine_branch/plan_task.py --task-id <odysseys_id>
    python scripts/spine_branch/plan_task.py --task-text "book a table and ..."
    python scripts/spine_branch/plan_task.py --task-id <id> --provider openai \
        --model fireworks_ai/qwen3p7-plus --out reports/spine_branch/<id>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# best-effort .env load so call_llm sees the proxy creds when run standalone
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

from utils.spine_branch.plan import generate_spine_branch_plan  # noqa: E402


def _resolve_task_text(args) -> tuple[str, str]:
    """Return (task_id, task_text)."""
    if args.task_text:
        return (args.task_id or "adhoc", args.task_text)
    if not args.task_id:
        raise SystemExit("provide --task-id or --task-text")
    src = Path(args.task_source or PROJECT_ROOT / "data/odysseys/odysseys.json")
    tasks = json.load(open(src))
    for t in tasks:
        if t.get("task_id", "").startswith(args.task_id):
            text = t.get("confirmed_task") or t.get("task") or t.get("instruction")
            if not text:
                raise SystemExit(f"task {args.task_id} has no task text field")
            return (t["task_id"], text)
    raise SystemExit(f"task id '{args.task_id}' not found in {src}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Offline spine-and-branch planner for one task.")
    ap.add_argument("--task-id", help="Odysseys task id (prefix ok)")
    ap.add_argument("--task-text", help="Raw task text (overrides --task-id lookup)")
    ap.add_argument("--task-source", help="Tasks JSON (default data/odysseys/odysseys.json)")
    ap.add_argument("--provider", default=os.environ.get("MACU_PLAN_PROVIDER", "openai"))
    ap.add_argument("--model", default=os.environ.get("MACU_PLAN_MODEL", "fireworks_ai/qwen3p7-plus"))
    ap.add_argument("--out", help="Output dir (default reports/spine_branch/<task_id>)")
    args = ap.parse_args()

    task_id, task_text = _resolve_task_text(args)
    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "reports" / "spine_branch" / task_id[:16]
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"planning task {task_id[:16]} via {args.provider}/{args.model} ...")
    legal_graph, report, usage, dec_errors = generate_spine_branch_plan(
        task_text=task_text, provider=args.provider, model=args.model
    )

    (out_dir / "dependency_graph.json").write_text(
        json.dumps({"task_id": task_id, "coordination": "spine_branch",
                    "dependency_graph": legal_graph}, indent=2), encoding="utf-8")
    (out_dir / "spine_branch_plan.json").write_text(
        json.dumps({"task_id": task_id, "task_text": task_text, "report": report,
                    "usage": {"input_tokens": usage.input_tokens,
                              "output_tokens": usage.output_tokens,
                              "cost_usd": round(usage.cost_usd, 5)}}, indent=2), encoding="utf-8")

    # ---- summary ----
    subs = legal_graph.get("subtasks", [])
    print(f"\n=== plan for {task_id[:16]} ===")
    print(f"  subtasks: {report.get('n_subtasks')}  | spine: {report.get('n_spine')}  branch: {report.get('n_branch')}  | distinct spines: {report.get('n_spines')}")
    print(f"  artifacts: {report.get('n_outputs')} produced | {report.get('n_artifact_edges')} read-edges")
    spines = report.get("spines") or {}
    if spines:
        print(f"  SPINES ({len(spines)} — operational; multi-node = init_from VM chain, single-node = standalone):")
        for lbl, chain in spines.items():
            print(f"    {lbl}: " + ("  ⇒(init_from)  ".join(chain) if len(chain) > 1 else chain[0] + " (single-node)"))
    else:
        print("  SPINES: none (all branches — every node opens a fresh VM)")
    if report.get("errors"):
        for e in report["errors"]:
            print(f"     ERROR: {e}")
    if report.get("warnings"):
        for w in report["warnings"]:
            print(f"     warn: {w}")
    print("  nodes:")
    for st in subs:
        role = st.get("role"); sp = st.get("spine_id")
        initf = st.get("init_from"); infs = st.get("input_files") or []
        outs = [o.get("name") if isinstance(o, dict) else o for o in (st.get("outputs") or [])]
        tag = f"spine[{sp}] init_from={initf}" if role == "spine" else "branch"
        print(f"    [{st['id']}] {tag}  outputs={outs}  reads={infs}")
    agg = legal_graph.get("aggregation")
    if agg:
        print(f"    [{agg['id']}] aggregation(reads-only) reads={agg.get('input_files') or []}")
    print(f"\n  wrote {out_dir}/dependency_graph.json + spine_branch_plan.json")
    print(f"  tokens: in={usage.input_tokens} out={usage.output_tokens} cost=${usage.cost_usd:.4f}")


if __name__ == "__main__":
    main()
