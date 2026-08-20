#!/usr/bin/env python3
"""Planning-only comparison of the spine-branch planner vs the MACU planner over a
task set (no CUA execution). For each task we generate BOTH dependency graphs and
score their STRUCTURE, to surface tasks where spine-branch decomposes better.

"Better" here = spine-branch avoids MACU's fragile pattern, established in the
Austin case study: a MACU CUA node that depends on >=2 CUA parents becomes a
multi-parent hub that at runtime inherits only ONE parent's live VM and receives
the others only as a manager-rewritten instruction reference (unreliable), and,
being a dependency of downstream nodes, gates a whole subtree. Spine-branch
instead routes such synthesis as a data-only branch (content of >=2 artifacts
injected) under a single state-carrying spine.

Metrics per task:
  MACU:  n_cua, multiparent_hubs (CUA nodes with >=2 CUA-parent deps),
         gating_hubs (multiparent hub that also has downstream CUA dependents),
         max_depth (longest dependency chain).
  Spine: n_cua, n_spines (should be 1), spine_chain_len, n_branch,
         multiinput_branches (branch reading >=2 artifacts), vm_multiparent
         (nodes whose init_from would need >1 parent -- should be 0 by design).
  candidate = MACU multiparent_hubs>=1 AND spine n_spines==1 AND spine
              vm_multiparent==0  (spine handles the same fan-in as data-only).

Usage:
  python scripts/spine_branch/plan_compare_batch.py \
      --task-source data/odysseys/odysseys155.json \
      --provider openai --model claude-opus-4-8 --workers 8 \
      --label ody155
"""
from __future__ import annotations
import argparse, json, os, sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
try:
    from dotenv import load_dotenv; load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

from utils.spine_branch.plan import generate_spine_branch_plan  # noqa: E402
from utils.graph_utils import generate_validated_dependency_graph  # noqa: E402

MACU_PROMPT = PROJECT_ROOT / "prompts" / "manager_cua_v2.yaml"


def _task_text(t: dict) -> str:
    return t.get("confirmed_task") or t.get("task") or t.get("instruction") or ""


def _cua(subs):
    return [s for s in subs if isinstance(s, dict) and s.get("agent_type", "cua") == "cua"]


def _max_depth(subs):
    by = {s["id"]: s for s in subs if s.get("id")}
    memo = {}
    def d(i, seen=()):
        if i in memo: return memo[i]
        if i in seen: return 0
        deps = [x for x in (by.get(i, {}).get("dependencies") or []) if x in by]
        r = 1 + (max((d(x, seen + (i,)) for x in deps), default=0))
        memo[i] = r; return r
    return max((d(i) for i in by), default=0)


def macu_metrics(graph):
    subs = graph.get("subtasks") or []
    cua = _cua(subs)
    cua_ids = {s["id"] for s in cua}
    # downstream count among cua
    downstream = defaultdict(int)
    for s in cua:
        for dep in s.get("dependencies") or []:
            if dep in cua_ids: downstream[dep] += 1
    hubs, gating = [], []
    for s in cua:
        cua_deps = [d for d in (s.get("dependencies") or []) if d in cua_ids]
        if len(cua_deps) >= 2:
            hubs.append(s["id"])
            if downstream.get(s["id"], 0) >= 1:
                gating.append(s["id"])
    return {"n_cua": len(cua), "multiparent_hubs": hubs, "gating_hubs": gating,
            "max_depth": _max_depth(subs + ([graph["aggregation"]] if graph.get("aggregation") else []))}


def spine_metrics(graph, report):
    subs = graph.get("subtasks") or []
    cua = _cua(subs)
    spine_ids = {s["id"] for s in cua if s.get("role") == "spine"}
    branch = [s for s in cua if s.get("role") == "branch"]
    # spine chain length via init_from
    byid = {s["id"]: s for s in cua}
    memo = {}
    def depth(i):
        if i in memo: return memo[i]
        inf = byid.get(i, {}).get("init_from")
        r = 1 + (depth(inf) if inf in spine_ids else 0); memo[i] = r; return r
    chain = max((depth(i) for i in spine_ids), default=0)
    multiinput_branches = sum(1 for b in branch if len(b.get("input_files") or []) >= 2)
    # a node "needing" >1 live parent would be a design violation; count nodes with >=2 cua deps AND role spine (should be 0)
    vm_multiparent = sum(1 for s in cua
                         if s.get("role") == "spine"
                         and len([d for d in (s.get("dependencies") or []) if d in byid]) >= 2
                         and s.get("init_from"))
    return {"n_cua": len(cua), "n_spines": report.get("n_spines", len(spine_ids and [1] or [])),
            "spine_chain_len": chain, "n_branch": len(branch),
            "multiinput_branches": multiinput_branches, "vm_multiparent": vm_multiparent}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-source", default=str(PROJECT_ROOT / "data/odysseys/odysseys155.json"))
    ap.add_argument("--provider", default="openai")
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--label", default="ody155")
    args = ap.parse_args()

    tasks = json.load(open(args.task_source))
    outbase = PROJECT_ROOT / "reports" / "plan_compare" / args.label
    outbase.mkdir(parents=True, exist_ok=True)
    print(f"planning {len(tasks)} tasks x2 planners via {args.provider}/{args.model}, {args.workers} workers", flush=True)

    def do(t):
        tid = t["task_id"]; txt = _task_text(t)
        row = {"task_id": tid, "level": t.get("level")}
        # spine-branch
        try:
            lg, rep, usage, errs = generate_spine_branch_plan(txt, provider=args.provider, model=args.model)
            row["spine"] = spine_metrics(lg, rep); row["spine_cost"] = round(usage.cost_usd, 4)
            (outbase / f"{tid[:16]}_spine.json").write_text(json.dumps({"graph": lg, "report": rep}, indent=2))
        except Exception as e:
            row["spine_err"] = str(e)[:120]
        # MACU
        try:
            g, usage2, errs2 = generate_validated_dependency_graph(txt, MACU_PROMPT, provider=args.provider, model=args.model)
            row["macu"] = macu_metrics(g); row["macu_cost"] = round(usage2.cost_usd, 4)
            (outbase / f"{tid[:16]}_macu.json").write_text(json.dumps(g, indent=2))
        except Exception as e:
            row["macu_err"] = str(e)[:120]
        # candidate flag
        m, s = row.get("macu"), row.get("spine")
        row["candidate"] = bool(m and s and len(m["multiparent_hubs"]) >= 1
                                and s["n_spines"] == 1 and s["vm_multiparent"] == 0)
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(do, t): t for t in tasks}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result(); rows.append(r)
            if i % 20 == 0: print(f"... {i}/{len(tasks)}", flush=True)

    json.dump(rows, open(outbase / "rows.json", "w"), indent=2)

    ok = [r for r in rows if "macu" in r and "spine" in r]
    cands = [r for r in ok if r["candidate"]]
    cands.sort(key=lambda r: (len(r["macu"]["multiparent_hubs"]), len(r["macu"]["gating_hubs"]), r["macu"]["max_depth"]), reverse=True)
    L = [f"# Planning-only structural comparison: spine-branch vs MACU ({args.label})\n",
         f"- model `{args.model}` | tasks {len(rows)} (both-ok {len(ok)}) | "
         f"total cost ${sum(r.get('spine_cost',0)+r.get('macu_cost',0) for r in rows):.2f}\n",
         f"- **candidate 'spine-branch decomposes better' tasks: {len(cands)}/{len(ok)}**",
         "  (MACU builds a multi-parent CUA hub -> inherits 1 VM + instruction-refs the rest;",
         "   spine-branch keeps 1 spine and no multi-parent VM node)\n",
         "## MACU fragility distribution\n",
         f"- tasks with >=1 multi-parent CUA hub: {sum(1 for r in ok if r['macu']['multiparent_hubs'])}/{len(ok)}",
         f"- tasks with a GATING hub (hub feeds a downstream subtree): {sum(1 for r in ok if r['macu']['gating_hubs'])}/{len(ok)}",
         f"- mean MACU max dependency depth: {sum(r['macu']['max_depth'] for r in ok)/max(1,len(ok)):.1f}",
         f"- mean spine chain length: {sum(r['spine']['spine_chain_len'] for r in ok)/max(1,len(ok)):.1f}\n",
         "## Top candidate tasks (spine-branch structurally safer)\n",
         "| task | level | MACU hubs | gating | MACU depth | spine chain | spine branches |",
         "|---|---|---|---|---|---|---|"]
    for r in cands[:40]:
        L.append(f"| `{r['task_id'][:12]}` | {r['level']} | {len(r['macu']['multiparent_hubs'])} | "
                 f"{len(r['macu']['gating_hubs'])} | {r['macu']['max_depth']} | "
                 f"{r['spine']['spine_chain_len']} | {r['spine']['n_branch']} |")
    (outbase / f"{args.label}_summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L[:14]))
    print(f"\nwrote {outbase}/{args.label}_summary.md and rows.json")


if __name__ == "__main__":
    main()
