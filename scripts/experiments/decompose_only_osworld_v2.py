#!/usr/bin/env python3
"""Decompose-ONLY dry run for OSWorld-V2: run the spine-branch planner over every
task with a given prompt and dump the graphs + a review summary. NO CUA execution.

Usage:
  python scripts/experiments/decompose_only_osworld_v2.py \
      --tasks data/osworld_v2/test_v2_106.json \
      --prompt prompts/spine_branch_decompose_osworld_v2.yaml \
      --out runs/osworld_v2_decompose_review --workers 4
"""
import argparse, json, os, sys, concurrent.futures as cf
from pathlib import Path

sys.path.insert(0, os.getcwd())
from utils.osworld_v2 import load_osworld_v2_tasks
from utils.spine_branch.plan import generate_spine_branch_plan


def decompose_one(task, prompt_path, provider, model):
    tid = task["task_id"]
    instr = task.get("instruction") or ""
    try:
        graph, report, usage, warns = generate_spine_branch_plan(
            instr, provider=provider, model=model, prompt_path=prompt_path)
    except Exception as e:  # noqa: BLE001
        return {"task_id": tid, "instruction": instr, "error": repr(e)}
    subs = graph.get("subtasks", []) or []
    n_spine = sum(1 for s in subs if s.get("role") == "spine")
    n_branch = sum(1 for s in subs if s.get("role") == "branch")
    return {
        "task_id": tid,
        "instruction": instr,
        "n_subtasks": len(subs),
        "n_spine": n_spine,
        "n_branch": n_branch,
        "task_analysis": graph.get("task_analysis") or "",
        "nodes": [
            {"id": s.get("id"), "role": s.get("role"), "agent_type": s.get("agent_type"),
             "init_from": s.get("init_from"),
             "dependencies": s.get("dependencies") or [],
             "outputs": [o.get("name") for o in (s.get("outputs") or [])],
             "input_files": s.get("input_files") or [],
             "description": s.get("description") or "",
             "instruction": s.get("instruction") or ""}
            for s in subs
        ],
        "graph": graph,
        "legalizer_warnings": warns,
        "legalizer_errors": (report or {}).get("errors", []),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="data/osworld_v2/test_v2_106.json")
    ap.add_argument("--prompt", default="prompts/spine_branch_decompose_osworld_v2.yaml")
    ap.add_argument("--out", default="runs/osworld_v2_decompose_review")
    ap.add_argument("--provider", default="openai")
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    tasks = load_osworld_v2_tasks(args.tasks)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "graphs").mkdir(exist_ok=True)
    print(f"Decomposing {len(tasks)} tasks with {args.prompt} -> {out}", flush=True)

    results = {}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(decompose_one, t, args.prompt, args.provider, args.model): t["task_id"]
                for t in tasks}
        done = 0
        for fut in cf.as_completed(futs):
            r = fut.result(); tid = r["task_id"]; results[tid] = r
            (out / "graphs" / f"{tid}.json").write_text(json.dumps(r.get("graph", {}), indent=2))
            done += 1
            if "error" in r:
                print(f"  [{done}/{len(tasks)}] {tid}: ERROR {r['error'][:120]}", flush=True)
            else:
                print(f"  [{done}/{len(tasks)}] {tid}: subtasks={r['n_subtasks']} "
                      f"spine={r['n_spine']} branch={r['n_branch']}", flush=True)

    ordered = [results[t["task_id"]] for t in tasks]
    (out / "summary.json").write_text(json.dumps(ordered, indent=2))

    # markdown review, sorted by branch count desc then id
    ok = [r for r in ordered if "error" not in r]
    errs = [r for r in ordered if "error" in r]
    n_multi = sum(1 for r in ok if r["n_subtasks"] > 1)
    n_branch_any = sum(1 for r in ok if r["n_branch"] > 0)
    lines = []
    lines.append("# OSWorld-V2 decomposition review (dry run, no CUA)\n")
    lines.append(f"- prompt: `{args.prompt}`")
    lines.append(f"- planner: {args.provider}/{args.model}")
    lines.append(f"- tasks: {len(ordered)} ({len(ok)} ok, {len(errs)} errored)")
    lines.append(f"- single spine node (1 subtask): {len(ok)-n_multi}/{len(ok)}")
    lines.append(f"- has >1 subtask: {n_multi}/{len(ok)}   has >=1 branch: {n_branch_any}/{len(ok)}\n")
    dist = {}
    for r in ok:
        dist[r["n_branch"]] = dist.get(r["n_branch"], 0) + 1
    lines.append("branch-count distribution: " + ", ".join(f"{k}br:{v}" for k, v in sorted(dist.items())) + "\n")
    lines.append("| task | subtasks | spine | branch | shape |")
    lines.append("|---|---:|---:|---:|---|")
    for r in sorted(ok, key=lambda x: (-x["n_branch"], -x["n_subtasks"], x["task_id"])):
        shape = " ".join(f"{n['id']}({n['role'][0]}{'<-'+str(n['init_from']) if n['init_from'] else ''})"
                         for n in r["nodes"])
        lines.append(f"| {r['task_id']} | {r['n_subtasks']} | {r['n_spine']} | {r['n_branch']} | {shape} |")
    if errs:
        lines.append("\n## errored\n")
        for r in errs:
            lines.append(f"- {r['task_id']}: {r['error'][:160]}")
    (out / "review.md").write_text("\n".join(lines) + "\n")
    print(f"\nWrote {out}/review.md, summary.json, graphs/*.json", flush=True)
    print(f"single-node: {len(ok)-n_multi}/{len(ok)}  multi: {n_multi}  with-branch: {n_branch_any}  errors: {len(errs)}", flush=True)


if __name__ == "__main__":
    main()
