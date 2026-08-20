#!/usr/bin/env python3
"""Render spine-branch plan JSONs into ONE human-readable markdown doc.

Reads <plans-dir>/<task_id>/dependency_graph.json (+ spine_branch_plan.json) and
the task text, and emits a doc you can scroll through: per task — the task text,
the spines (VM-inheritance chains), and each node's role / init_from / outputs /
reads / full (augmented) instruction.

Usage:
    python scripts/spine_branch/render_plans.py --plans-dir reports/spine_branch/opus48
    python scripts/spine_branch/render_plans.py --plans-dir reports/spine_branch/qwen37plus \
        --out reports/spine_branch_plans_qwen37plus.md
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _task_text_map(src: str) -> dict:
    try:
        tasks = json.load(open(src))
    except Exception:
        return {}
    return {t["task_id"]: (t.get("confirmed_task") or t.get("task") or t.get("instruction") or "")
            for t in tasks if t.get("task_id")}
    # (level handled separately)


def main() -> None:
    ap = argparse.ArgumentParser(description="Render spine-branch plans to readable markdown.")
    ap.add_argument("--plans-dir", required=True, help="dir with <task_id>/dependency_graph.json")
    ap.add_argument("--task-source", default=str(PROJECT_ROOT / "data/odysseys/odysseys.json"))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    plans_dir = Path(args.plans_dir)
    texts = _task_text_map(args.task_source)
    levels = {}
    try:
        levels = {t["task_id"]: t.get("level") for t in json.load(open(args.task_source))}
    except Exception:
        pass

    plan_files = sorted(glob.glob(str(plans_dir / "*" / "dependency_graph.json")))
    if not plan_files:
        sys.exit(f"no plans found under {plans_dir}")

    rows = []
    for pf in plan_files:
        d = json.load(open(pf))
        tid = d.get("task_id") or Path(pf).parent.name
        g = d.get("dependency_graph", {})
        rep_path = Path(pf).parent / "spine_branch_plan.json"
        report = json.load(open(rep_path)).get("report", {}) if rep_path.exists() else {}
        rows.append((tid, g, report))

    rows.sort(key=lambda r: (levels.get(r[0]) or "z", r[0]))

    L = [f"# Spine-branch plans — `{plans_dir.name}`\n",
         f"{len(rows)} tasks. Each: task text, spines (VM-inheritance chains), then every node "
         f"(role · init_from · outputs · reads) with its full instruction.\n"]
    # contents table
    L.append("| task | level | subs | spine/branch | #spines | errs/warns |")
    L.append("|---|---|---|---|---|---|")
    for tid, g, rep in rows:
        L.append(f"| [`{tid[:10]}`](#{tid[:10]}) | {levels.get(tid)} | {rep.get('n_subtasks','?')} | "
                 f"{rep.get('n_spine','?')}/{rep.get('n_branch','?')} | {rep.get('n_spines','?')} | "
                 f"{len(rep.get('errors',[]))}/{len(rep.get('warnings',[]))} |")
    L.append("")

    for tid, g, rep in rows:
        subs = g.get("subtasks", [])
        agg = g.get("aggregation")
        spines = g.get("spines") or rep.get("spines") or {}
        L.append(f"\n---\n\n<a id='{tid[:10]}'></a>\n## `{tid[:13]}` ({levels.get(tid)})\n")
        txt = texts.get(tid, "")
        L.append("> " + (txt[:700] + ("…" if len(txt) > 700 else "")).replace("\n", " ") + "\n")
        if spines:
            L.append("**Spines (VM-inheritance chains):**")
            for lbl, chain in spines.items():
                L.append(f"- `{lbl}`: " + " → ".join(f"`{c}`" for c in chain))
        else:
            L.append("**Spines:** none — every node is an independent branch (fresh VM).")
        if rep.get("errors"):
            L.append("\n**errors:** " + "; ".join(rep["errors"]))
        if rep.get("warnings"):
            L.append("**warnings:** " + "; ".join(rep["warnings"][:6]))
        L.append("")
        for st in subs + ([agg] if agg else []):
            role = st.get("role", "?")
            sp = st.get("spine_id")
            initf = st.get("init_from")
            outs = [f"`{o.get('name')}` ({o.get('description','')})" if isinstance(o, dict) else f"`{o}`"
                    for o in (st.get("outputs") or [])]
            reads = [f"`{x}`" for x in (st.get("input_files") or [])]
            kind = "AGG" if st.get("agent_type") == "manager" else role
            meta = [f"role=**{kind}**"]
            if sp:
                meta.append(f"spine={sp}")
            if initf:
                meta.append(f"init_from=`{initf}`")
            L.append(f"### `{st['id']}` — {' · '.join(meta)}")
            if outs:
                L.append(f"- **writes:** {', '.join(outs)}")
            if reads:
                L.append(f"- **reads:** {', '.join(reads)}")
            instr = str(st.get("instruction") or "").strip()
            L.append("- **instruction:**")
            L.append("  > " + instr.replace("\n", "\n  > "))
            L.append("")

    out = args.out or str(PROJECT_ROOT / "reports" / f"spine_branch_plans_{plans_dir.name}.md")
    Path(out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows)} tasks)")


if __name__ == "__main__":
    main()
