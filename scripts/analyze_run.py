#!/usr/bin/env python3
"""Aggregate analysis across all tasks in an Odysseys MACU run directory.

Odysseys-specific: scores come from the rubric eval (odysseys_eval.json, or the
corrected odysseys_eval_fulltext.json when present); tasks are grouped by
difficulty level (easy/medium/hard) rather than OSWorld domain.

Input: a run root, e.g. runs/odysseys45_qwen37plus_replan5 (one folder per task).

Produces:
  1. A terminal report: overall success rate, per-domain breakdown, cost,
     wall-clock, replanning stats, and the per-task scoreboard. Also flags
     tasks that are stuck (claimed, no result) or not started.
  2. (optional) A markdown doc (--md [PATH]) mirroring the report as tables.
     Default path: reports/<run_name>_run_summary.md

Usage:
    python scripts/analyze_run.py runs/subset36_replan5
    python scripts/analyze_run.py runs/subset36_replan5 --md
    python scripts/analyze_run.py runs/subset36_replan5 --md /tmp/run.md
    python scripts/analyze_run.py runs/subset36_replan5 --tasks-file data/osworld/subset36.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_task import node_taxonomy, replan_effects, load_eval_record  # noqa: E402


C = {"reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
     "green": "\033[32m", "red": "\033[31m", "yellow": "\033[33m", "cyan": "\033[36m"}


def _c(s: str, color: str, use: bool) -> str:
    return f"{C[color]}{s}{C['reset']}" if use else s


def _load(path: Path) -> Optional[Any]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _count_steps_actions(task_dir: Path, cua_ids: set) -> tuple[int, int]:
    """Total agent steps and actions across ALL CUA subtasks in a task dir
    (failed or succeeded — every CUA that ran wrote a traj.jsonl).

    Only counts trajectories under a real CUA subtask dir (``cua_ids``). This
    EXCLUDES ``final_traj/`` — the eval's merged/renumbered trajectory, which is
    a concatenation of every subtask and would double-count everything.

    traj.jsonl has one line per executed action; `step_num` is the predict
    iteration and is shared by multiple actions in the same step, so:
      - actions = number of real action lines
      - steps   = number of distinct (subtask, step_num) pairs
                  (step_num resets per subtask, so it must be namespaced)
    The trailing synthetic 'SUMMARY' entry (a post-hoc text extraction, no
    screenshot / no environment action) is excluded from both."""
    steps: set = set()
    actions = 0
    for tj in task_dir.rglob("traj.jsonl"):
        try:
            sub = tj.relative_to(task_dir).parts[0]
        except ValueError:
            sub = str(tj)
        if sub not in cua_ids:
            continue
        try:
            with open(tj, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if str(e.get("action")) == "SUMMARY":
                        continue
                    actions += 1
                    steps.add((sub, e.get("step_num")))
        except OSError:
            continue
    return len(steps), actions


def _final_traj_steps(task_dir: Path) -> int:
    """Steps in the FINAL (merged) trajectory that the judge actually scored
    (<task>/final_traj/traj.jsonl) — distinct step_num, excluding any SUMMARY.
    This is the deliverable path, not the sum of all exploratory subtasks."""
    ftj = task_dir / "final_traj" / "traj.jsonl"
    if not ftj.is_file():
        return 0
    steps: set = set()
    try:
        with open(ftj, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if str(e.get("action")) == "SUMMARY":
                    continue
                steps.add(e.get("step_num"))
    except OSError:
        return 0
    return len(steps)


def collect(run_dir: Path, eval_json: Optional[str] = None) -> list[dict]:
    """One record per task folder under run_dir.

    `eval_json` selects which rubric-eval file to read scores from (passed to
    load_eval_record); None uses its default search (odysseys_eval.json)."""
    recs: list[dict] = []
    for d in sorted(run_dir.iterdir()):
        if not d.is_dir():
            continue
        fr = _load(d / "final_results.json")
        claimed = (d / ".claimed").exists()
        if fr is None:
            # stuck (claimed but crashed) or in-progress, no result
            recs.append({
                "task_id": d.name, "state": "stuck" if claimed else "incomplete",
                "domain": None, "score": None, "cost": None, "duration": None,
                "replans_applied": None, "replans_calls": None, "n_subtasks": None,
            })
            continue
        rp = fr.get("replanning", {}) or {}
        sub = fr.get("subtask_results", {}) or {}
        n_cua = sum(1 for k in sub if k != "final_aggregation")
        # Odysseys score = rubric eval's average pass-fraction (read-only;
        # produced by odysseys_eval.py). Fall back to the programmatic OSWorld
        # score only if no rubric record exists (keeps generate_report working).
        score = None
        score_kind = "rubric"
        n_rubrics = n_rubrics_passed = None
        ev = load_eval_record(d, eval_json)
        if ev is not None:
            score = ev.get("average_rubric_score")
            rubs = ev.get("rubric_results") or []
            n_rubrics = len(rubs)
            n_rubrics_passed = sum(1 for r in rubs if r.get("score"))
        if score is None:
            score = fr.get("osworld_evaluator_score")
            score_kind = "osworld"
        tax = node_taxonomy(d)["counts"]
        reff = replan_effects(d)["counts"]
        cua_ids = {k for k in sub if k != "final_aggregation"}
        agent_steps, agent_actions = _count_steps_actions(d, cua_ids)
        final_traj_steps = _final_traj_steps(d)
        # manager-vs-CUA cost/token split from summary.json (authoritative
        # totals + per-node breakdown). manager_calls is the complete manager
        # LLM-call list (planning + file-mgmt + replan + aggregation), so it is
        # the manager token source; CUA tokens come from cua-typed subtask_costs.
        summ = _load(d / "summary.json") or {}
        mgr_calls = summ.get("manager_calls") or []
        sub_costs = (summ.get("subtask_costs") or {}).values()
        recs.append({
            "task_id": d.name,
            "state": "done",
            "domain": fr.get("domain"),
            "score": score,
            "score_kind": score_kind,
            "n_rubrics": n_rubrics,
            "n_rubrics_passed": n_rubrics_passed,
            "success": isinstance(score, (int, float)) and score >= 1.0,
            "cost": fr.get("total_cost_usd"),
            "mgr_cost": summ.get("total_manager_cost_usd"),
            "cua_cost": summ.get("total_cua_cost_usd"),
            # Manager tokens = planning/replan calls (manager_calls) PLUS any
            # non-CUA subtask (aggregator / filemgmt / manager-typed), all of
            # which are manager-model calls counted in total_manager_cost_usd.
            "mgr_in": (sum(c.get("input_tokens", 0) or 0 for c in mgr_calls)
                       + sum(c.get("input_tokens", 0) or 0 for c in sub_costs if c.get("agent_type") != "cua")),
            "mgr_out": (sum(c.get("output_tokens", 0) or 0 for c in mgr_calls)
                        + sum(c.get("output_tokens", 0) or 0 for c in sub_costs if c.get("agent_type") != "cua")),
            "cua_in": sum(c.get("input_tokens", 0) or 0 for c in sub_costs if c.get("agent_type") == "cua"),
            "cua_out": sum(c.get("output_tokens", 0) or 0 for c in sub_costs if c.get("agent_type") == "cua"),
            "duration": fr.get("total_duration_seconds"),
            "inference": fr.get("total_inference_seconds"),
            "replans_applied": rp.get("num_applied"),
            "replans_calls": rp.get("num_calls"),
            "n_subtasks": n_cua,
            "agent_steps": agent_steps,
            "agent_actions": agent_actions,
            "final_traj_steps": final_traj_steps,
            # trajectory efficiency: rubric average earned per step of the FINAL
            # (judged) trajectory. None when no score or no final-traj steps.
            "traj_eff": ((score / final_traj_steps) if isinstance(score, (int, float)) and final_traj_steps
                         else None),
            "infeasible": fr.get("osworld_infeasible_verdict"),
            "initial_cua": tax["initial_cua"],
            "added_total": tax["added_total"],
            "added_retry": tax["added_retry"],
            "added_init_from": tax["added_init_from"],
            "added_variant": tax["added_variant"],
            "final_nodes": tax["final_total"],
            "replan_calls": reff["calls"],
            "replan_no_change": reff["no_change"],
            "replan_instr_only": reff["instruction_only"],
            "replan_structural": reff["structural"],
        })
    return recs


def _expected_from_tasks_file(tasks_file: Optional[str]) -> Optional[int]:
    if not tasks_file or not os.path.exists(tasks_file):
        return None
    try:
        d = json.load(open(tasks_file))
        if isinstance(d, dict):
            return sum(len(v) for v in d.values())
        if isinstance(d, list):
            return len(d)
    except Exception:
        pass
    return None


def _real_elapsed_seconds(run_dir: Path, done: list[dict]) -> Optional[float]:
    """Batch real end-to-end wall-clock: manifest write (first worker start) to
    the latest final_results.json (last task finished). Distinct from the SUM of
    per-task durations, which overlaps under multiple workers. Computed from file
    mtimes so it works even for a run that recorded no explicit end time."""
    mtimes = []
    for r in done:
        fp = run_dir / r["task_id"] / "final_results.json"
        try:
            mtimes.append(fp.stat().st_mtime)
        except OSError:
            continue
    if not mtimes:
        return None
    man = run_dir / "run_manifest.json"
    try:
        start = man.stat().st_mtime if man.exists() else min(mtimes)
    except OSError:
        start = min(mtimes)
    return max(0.0, max(mtimes) - start)


def _fmt_pct(num: int, den: int) -> str:
    return f"{num}/{den} ({num/den*100:.1f}%)" if den else f"{num}/0"


_LEVEL_ORDER = {"easy": 0, "medium": 1, "hard": 2}


def _lvl_key(level: Optional[str]):
    """Sort key: easy < medium < hard < anything else (alphabetical)."""
    return (_LEVEL_ORDER.get(level, 9), level or "")


def _level_map(tasks_file: Optional[str]) -> dict:
    """task_id -> difficulty level, for odysseys runs that have no domain."""
    if not tasks_file or not os.path.exists(tasks_file):
        return {}
    try:
        data = json.load(open(tasks_file))
        items = data if isinstance(data, list) else [v for vs in data.values() for v in vs]
        return {t["task_id"]: t.get("level") for t in items if isinstance(t, dict) and t.get("task_id")}
    except Exception:
        return {}


def report(run_dir: Path, tasks_file: Optional[str], use_color: bool,
           eval_json: Optional[str] = None) -> list[dict]:
    recs = collect(run_dir, eval_json)
    # Odysseys tasks have no domain; group them by difficulty level instead.
    # (The record key stays "domain" for generate_report.py compatibility, but
    # it holds the difficulty level for odysseys runs.)
    lvl = _level_map(tasks_file)
    for r in recs:
        if not r.get("domain"):
            r["domain"] = lvl.get(r["task_id"]) or "?"
    done = [r for r in recs if r["state"] == "done"]
    stuck = [r for r in recs if r["state"] == "stuck"]
    incomplete = [r for r in recs if r["state"] == "incomplete"]
    scored = [r for r in done if isinstance(r["score"], (int, float))]
    succ = [r for r in scored if r["success"]]

    def h(s):
        return _c(s, "bold", use_color)

    print()
    print(h("═" * 74))
    print(h(f" MACU Run Summary: {run_dir.name}"))
    print(h("═" * 74))

    man = _load(run_dir / "run_manifest.json")
    if man:
        m = man[0] if isinstance(man, list) else man
        kn = m.get("knobs") or {}
        passthrough = m.get("cua_passthrough_args") or []
        sba = any("step_budget_awareness" in a for a in passthrough)
        print(f"  Config      : {_c(m.get('coordination_mode','?'), 'cyan', use_color)}  |  "
              f"mgr={(m.get('manager') or {}).get('model','?')}  |  "
              f"cua={(m.get('cua') or {}).get('model','?')}")
        vc = f"  verify_continue=ON(max={kn.get('max_continuations')},checker={kn.get('checker_model')})" if kn.get("verify_continue") else ""
        print(f"  Knobs       : max_steps={kn.get('max_steps')} par={kn.get('max_parallelism')} "
              f"replans={kn.get('max_replans')} no_manager={kn.get('no_manager')}"
              + ("  step_budget_awareness=ON" if sba else "") + vc)
        print(f"  Launched    : {m.get('started_at','?')} on {m.get('host','?')}  |  "
              f"tasks={m.get('n_tasks')} (ids-sha {m.get('task_ids_sha1')})")

    expected = _expected_from_tasks_file(tasks_file)
    total_line = f"{len(recs)} task folder(s)"
    if expected:
        total_line += f"  (expected {expected})"
    print(f"  Folders     : {total_line}")
    print(f"  Done/scored : {len(done)} done, {len(scored)} scored")
    if stuck:
        print(f"  {_c('Stuck', 'red', use_color)}       : {len(stuck)} (claimed, crashed, no result)")
    if incomplete:
        print(f"  Incomplete  : {len(incomplete)} (no result, not claimed)")

    # --- overall SR ---
    print()
    print(h("─" * 74))
    print(h(" OVERALL"))
    print(h("─" * 74))
    if scored:
        sr = len(succ) / len(scored) * 100
        partial = sum(r["score"] for r in scored) / len(scored) * 100
        sr_col = "green" if sr >= 50 else ("yellow" if sr > 0 else "red")
        print(f"  Success rate (score≥1.0) : {_c(f'{len(succ)}/{len(scored)} = {sr:.1f}%', sr_col, use_color)}")
        print(f"  Partial-credit mean      : {partial:.1f}%  (macro: mean of per-task pass-fractions, equal weight/task)")
        tot_pass = sum(r["n_rubrics_passed"] or 0 for r in scored if r.get("n_rubrics") is not None)
        tot_rub = sum(r["n_rubrics"] or 0 for r in scored if r.get("n_rubrics") is not None)
        if tot_rub:
            print(f"  Rubrics passed (micro)   : {tot_pass}/{tot_rub} = {tot_pass/tot_rub*100:.1f}%  "
                  f"(fraction of ALL rubrics across tasks)")
        if expected and len(scored) < expected:
            proj = len(succ) / expected * 100
            print(f"  {_c('NOTE', 'yellow', use_color)}: only {len(scored)}/{expected} tasks scored; "
                  f"SR over the full set is incomplete (≥{proj:.0f}% lower-bound).")
    else:
        print("  (no scored tasks)")

    total_cost = sum(r["cost"] or 0 for r in done)
    total_dur = sum(r["duration"] or 0 for r in done)
    total_inf = sum(r.get("inference") or 0 for r in done)
    tot_replan = sum(r["replans_applied"] or 0 for r in done)
    if done:
        print(f"  Total cost               : ${total_cost:.2f}  (mean ${total_cost/len(done):.3f}/task)")
        print(f"  Compute-time (sum tasks) : {total_dur/60:.0f} min  (mean {total_dur/len(done):.0f}s/task, "
              f"{total_inf/max(1,total_dur)*100:.0f}% in inference)")
        elapsed = _real_elapsed_seconds(run_dir, done)
        if elapsed:
            print(f"  Real wall-clock (elapsed): {elapsed/60:.0f} min  (batch start→last result; "
                  f"{total_dur/max(1.0,elapsed):.1f}× parallel speedup over serial)")
        print(f"  Replans applied          : {tot_replan} across {len(done)} tasks "
              f"(mean {tot_replan/len(done):.1f}/task)")
        tot_steps = sum(r.get("agent_steps") or 0 for r in done)
        tot_actions = sum(r.get("agent_actions") or 0 for r in done)
        tot_subs = sum(r.get("n_subtasks") or 0 for r in done)
        print(f"  Agent steps (all CUAs)   : {tot_steps} total (mean {tot_steps/len(done):.1f}/task"
              + (f", {tot_steps/tot_subs:.1f}/subtask)" if tot_subs else ")"))
        print(f"  Agent actions (all CUAs) : {tot_actions} total (mean {tot_actions/len(done):.1f}/task)")
        effs = [r["traj_eff"] for r in done if r.get("traj_eff") is not None]
        if effs:
            mean_eff = sum(effs) / len(effs)
            ft = [r.get("final_traj_steps") or 0 for r in done if r.get("traj_eff") is not None]
            print(f"  Traj efficiency          : {mean_eff*1000:.2f} rubric-avg / 1k final-traj steps  "
                  f"(mean over {len(effs)} task(s); mean final-traj steps={sum(ft)/len(ft):.0f})")

    # --- cost & tokens: manager vs CUA ---
    if done:
        n = len(done)
        mgr_cost = sum(r.get("mgr_cost") or 0 for r in done)
        cua_cost = sum(r.get("cua_cost") or 0 for r in done)
        mgr_in = sum(r.get("mgr_in") or 0 for r in done)
        mgr_out = sum(r.get("mgr_out") or 0 for r in done)
        cua_in = sum(r.get("cua_in") or 0 for r in done)
        cua_out = sum(r.get("cua_out") or 0 for r in done)
        tot = mgr_cost + cua_cost
        print()
        print(h("─" * 74))
        print(h(" COST & TOKENS  (manager vs CUA)"))
        print(h("─" * 74))
        print(f"  {'agent':<9}{'cost':>10}{'share':>7}{'in tok':>13}{'out tok':>11}{'$/task':>10}")

        def _cost_row(name, cost, i, o, color):
            share = f"{cost/tot*100:.0f}%" if tot else "—"
            print(f"  {_c(name.ljust(9), color, use_color)}{('$'+format(cost,'.3f')):>10}{share:>7}"
                  f"{i:>13,}{o:>11,}{cost/n:>10.4f}")
        _cost_row("manager", mgr_cost, mgr_in, mgr_out, "cyan")
        _cost_row("CUA", cua_cost, cua_in, cua_out, "yellow")
        _cost_row("total", tot, mgr_in + cua_in, mgr_out + cua_out, "bold")
        mgr_tok = mgr_in + mgr_out
        cua_tok = cua_in + cua_out
        print(f"  avg tokens/task (mgr+CUA): {(mgr_tok + cua_tok)/n:,.0f}"
              f"   (mgr {mgr_tok/n:,.0f} + CUA {cua_tok/n:,.0f})")
        if tot:
            print(f"  manager:CUA cost ratio   : {mgr_cost/tot*100:.0f}% : {cua_cost/tot*100:.0f}%")
        if cua_cost == 0 and cua_in == 0:
            print(f"  {_c('NOTE', 'yellow', use_color)}: CUA tokens/cost are 0 — this run predates "
                  f"CUA token capture (only new runs record it).")

    # --- node dynamics: how the graphs grew ---
    if done:
        print()
        print(h("─" * 74))
        print(h(" NODE DYNAMICS  (graph structure across the run)"))
        print(h("─" * 74))
        si = sum(r.get("initial_cua") or 0 for r in done)
        sa = sum(r.get("added_total") or 0 for r in done)
        sr_ = sum(r.get("added_retry") or 0 for r in done)
        sif = sum(r.get("added_init_from") or 0 for r in done)
        sv = sum(r.get("added_variant") or 0 for r in done)
        n = len(done)
        grew = sum(1 for r in done if (r.get("added_total") or 0) > 0)
        print(f"  Initial CUA subtasks     : {si} total (mean {si/n:.1f}/task)")
        print(f"  Dynamically added nodes  : {sa} total (mean {sa/n:.1f}/task) "
              f"— {grew}/{n} tasks grew their graph")
        print(f"      ├─ retry (fresh)     : {sr_}")
        print(f"      ├─ init_from (inherit state) : {sif}")
        print(f"      └─ variant (alt strategy)    : {sv}")
        # tasks that grew the most
        top = sorted(done, key=lambda r: -(r.get("added_total") or 0))[:5]
        top = [r for r in top if (r.get("added_total") or 0) > 0]
        if top:
            print(f"  Most-grown tasks:")
            for r in top:
                print(f"      +{r['added_total']:>2} (retry={r['added_retry']},"
                      f" init_from={r['added_init_from']}, variant={r['added_variant']})"
                      f"  {(r['domain'] or '?'):<16} {r['task_id'][:16]}")

    # --- replan effect: applied vs actually-structural ---
    if done:
        rc = sum(r.get("replan_calls") or 0 for r in done)
        rn = sum(r.get("replan_no_change") or 0 for r in done)
        ri = sum(r.get("replan_instr_only") or 0 for r in done)
        rs = sum(r.get("replan_structural") or 0 for r in done)
        applied = ri + rs
        print()
        print(h("─" * 74))
        print(h(" REPLAN EFFECT  (did replanning actually change graph structure?)"))
        print(h("─" * 74))
        print(f"  Replan calls             : {rc}")
        print(f"  ├─ no change (confirmed as-is) : {rn}  ({rn/rc*100:.0f}%)" if rc else "")
        print(f"  └─ applied               : {applied}  ({applied/rc*100:.0f}%)" if rc else "")
        if applied:
            print(f"       ├─ instruction-only : {ri}  ({ri/applied*100:.0f}% of applied — topology UNCHANGED)")
            print(f"       └─ structural       : {rs}  ({rs/applied*100:.0f}% of applied — nodes/edges changed)")
        tasks_structural = sum(1 for r in done if (r.get("replan_structural") or 0) > 0)
        print(f"  Tasks with ≥1 structural replan: {tasks_structural}/{len(done)}")

    # --- by difficulty level ---
    print()
    print(h("─" * 74))
    print(h(" BY LEVEL"))
    print(h("─" * 74))
    bydom: dict[str, list[dict]] = defaultdict(list)
    for r in scored:
        bydom[r["domain"]].append(r)
    print(f"  {'level':<20} {'perfect SR':>14} {'mean$':>8} {'meanS':>7} {'replan':>7}")
    for dom in sorted(bydom, key=_lvl_key):
        rs = bydom[dom]
        ok = sum(1 for r in rs if r["success"])
        mc = sum(r["cost"] or 0 for r in rs) / len(rs)
        md = sum(r["duration"] or 0 for r in rs) / len(rs)
        mr = sum(r["replans_applied"] or 0 for r in rs) / len(rs)
        col = "green" if ok == len(rs) else ("red" if ok == 0 else "yellow")
        print(f"  {dom:<20} {_c(_fmt_pct(ok,len(rs)).rjust(14), col, use_color)} "
              f"{mc:>8.3f} {md:>6.0f}s {mr:>7.1f}")

    # --- per-task scoreboard ---
    print()
    print(h("─" * 74))
    print(h(" PER-TASK"))
    print(h("─" * 74))
    print(f"  {'score':>5} {'level':<18} {'$':>6} {'sec':>5} {'rpl':>4} {'subs':>4} {'steps':>6} {'acts':>6}  task_id")
    for r in sorted(done, key=lambda x: (_lvl_key(x["domain"]), -(x["score"] or 0))):
        sc = r["score"]
        sc_col = "green" if r["success"] else ("yellow" if isinstance(sc, (int, float)) and sc > 0 else "red")
        sc_s = f"{sc:.2f}" if isinstance(sc, (int, float)) else str(sc)
        print(f"  {_c(sc_s.rjust(5), sc_col, use_color)} {(r['domain'] or '?'):<18} "
              f"{(r['cost'] or 0):>6.3f} {(r['duration'] or 0):>4.0f}s "
              f"{str(r['replans_applied'] or 0):>4} {str(r['n_subtasks'] or 0):>4} "
              f"{str(r.get('agent_steps') or 0):>6} {str(r.get('agent_actions') or 0):>6}  {r['task_id'][:18]}")
    for r in stuck + incomplete:
        tag = _c(r["state"], "red" if r["state"] == "stuck" else "dim", use_color)
        print(f"  {tag:>5} {'—':<18} {'—':>6} {'—':>5} {'—':>4} {'—':>4} {'—':>6} {'—':>6}  {r['task_id'][:18]}")

    print()
    print(h("═" * 74))
    return recs


def write_md(recs: list[dict], run_dir: Path, path: str, tasks_file: Optional[str]) -> None:
    """Write the run analysis as a markdown document (tables mirroring the report)."""
    done = [r for r in recs if r["state"] == "done"]
    stuck = [r for r in recs if r["state"] == "stuck"]
    incomplete = [r for r in recs if r["state"] == "incomplete"]
    scored = [r for r in done if isinstance(r["score"], (int, float))]
    succ = [r for r in scored if r["success"]]
    n = len(done)

    L: list[str] = []
    L.append(f"# MACU Run Summary — `{run_dir.name}`\n")
    L.append(f"- **Run dir:** `{run_dir}/`")
    L.append(f"- **Generated by:** `scripts/analyze_run.py`")
    man = _load(run_dir / "run_manifest.json")
    if man:
        m = man[0] if isinstance(man, list) else man
        kn = m.get("knobs") or {}
        sba = any("step_budget_awareness" in a for a in (m.get("cua_passthrough_args") or []))
        L.append(f"- **Config:** `{m.get('coordination_mode','?')}` — "
                 f"mgr `{(m.get('manager') or {}).get('model','?')}`, "
                 f"cua `{(m.get('cua') or {}).get('model','?')}`")
        L.append(f"- **Knobs:** max_steps={kn.get('max_steps')}, par={kn.get('max_parallelism')}, "
                 f"replans={kn.get('max_replans')}, no_manager={kn.get('no_manager')}"
                 + (", **step_budget_awareness=ON**" if sba else ""))
        L.append(f"- **Launched:** {m.get('started_at','?')} on `{m.get('host','?')}`; "
                 f"tasks={m.get('n_tasks')} (ids-sha `{m.get('task_ids_sha1')}`)")
    expected = _expected_from_tasks_file(tasks_file)
    folders = f"{len(recs)} task folder(s)" + (f" (expected {expected})" if expected else "")
    L.append(f"- **Folders:** {folders}")
    L.append(f"- **Done / scored:** {len(done)} done, {len(scored)} scored"
             + (f"; **{len(stuck)} stuck**" if stuck else "")
             + (f"; {len(incomplete)} incomplete" if incomplete else ""))
    L.append("")

    # --- Overall ---
    L.append("## Overall\n")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    if scored:
        sr = len(succ) / len(scored) * 100
        partial = sum(r["score"] for r in scored) / len(scored) * 100
        L.append(f"| Success rate (score ≥ 1.0) | {len(succ)}/{len(scored)} = {sr:.1f}% |")
        L.append(f"| Partial-credit mean (macro, equal weight/task) | {partial:.1f}% |")
        tot_pass = sum(r["n_rubrics_passed"] or 0 for r in scored if r.get("n_rubrics") is not None)
        tot_rub = sum(r["n_rubrics"] or 0 for r in scored if r.get("n_rubrics") is not None)
        if tot_rub:
            L.append(f"| Rubrics passed (micro, all rubrics) | {tot_pass}/{tot_rub} = {tot_pass/tot_rub*100:.1f}% |")
    else:
        L.append("| Success rate | (no scored tasks) |")
    if done:
        total_cost = sum(r["cost"] or 0 for r in done)
        total_dur = sum(r["duration"] or 0 for r in done)
        total_inf = sum(r.get("inference") or 0 for r in done)
        tot_replan = sum(r["replans_applied"] or 0 for r in done)
        L.append(f"| Total cost | ${total_cost:.2f} (mean ${total_cost/n:.3f}/task) |")
        L.append(f"| Compute-time (sum of per-task) | {total_dur/60:.0f} min (mean {total_dur/n:.0f}s/task, "
                 f"{total_inf/max(1,total_dur)*100:.0f}% inference) |")
        elapsed = _real_elapsed_seconds(run_dir, done)
        if elapsed:
            L.append(f"| Real wall-clock (elapsed) | {elapsed/60:.0f} min "
                     f"({total_dur/max(1.0,elapsed):.1f}× parallel speedup over serial) |")
        L.append(f"| Replans applied | {tot_replan} (mean {tot_replan/n:.1f}/task) |")
        tot_steps = sum(r.get("agent_steps") or 0 for r in done)
        tot_actions = sum(r.get("agent_actions") or 0 for r in done)
        tot_subs = sum(r.get("n_subtasks") or 0 for r in done)
        per_sub = f", {tot_steps/tot_subs:.1f}/subtask" if tot_subs else ""
        L.append(f"| Agent steps (all CUAs) | {tot_steps} (mean {tot_steps/n:.1f}/task{per_sub}) |")
        L.append(f"| Agent actions (all CUAs) | {tot_actions} (mean {tot_actions/n:.1f}/task) |")
        effs = [r["traj_eff"] for r in done if r.get("traj_eff") is not None]
        if effs:
            ft = [r.get("final_traj_steps") or 0 for r in done if r.get("traj_eff") is not None]
            L.append(f"| Traj efficiency (rubric-avg / 1k final-traj steps) | {sum(effs)/len(effs)*1000:.2f} "
                     f"(mean over {len(effs)} task(s); mean final-traj steps={sum(ft)/len(ft):.0f}) |")
    L.append("")

    # --- Cost & tokens: manager vs CUA ---
    if done:
        mgr_cost = sum(r.get("mgr_cost") or 0 for r in done)
        cua_cost = sum(r.get("cua_cost") or 0 for r in done)
        mgr_in = sum(r.get("mgr_in") or 0 for r in done)
        mgr_out = sum(r.get("mgr_out") or 0 for r in done)
        cua_in = sum(r.get("cua_in") or 0 for r in done)
        cua_out = sum(r.get("cua_out") or 0 for r in done)
        tot = mgr_cost + cua_cost
        L.append("## Cost & tokens (manager vs CUA)\n")
        L.append("| Agent | Cost | Share | Input tokens | Output tokens | Mean $/task |")
        L.append("|---|---|---|---|---|---|")

        def _md_cost_row(name, cost, i, o):
            share = f"{cost/tot*100:.0f}%" if tot else "—"
            return f"| {name} | ${cost:.3f} | {share} | {i:,} | {o:,} | {cost/n:.4f} |"
        L.append(_md_cost_row("Manager", mgr_cost, mgr_in, mgr_out))
        L.append(_md_cost_row("CUA", cua_cost, cua_in, cua_out))
        L.append(_md_cost_row("**Total**", tot, mgr_in + cua_in, mgr_out + cua_out))
        mgr_tok = mgr_in + mgr_out
        cua_tok = cua_in + cua_out
        L.append(f"\n**Avg tokens/task (mgr+CUA):** {(mgr_tok + cua_tok)/n:,.0f} "
                 f"(manager {mgr_tok/n:,.0f} + CUA {cua_tok/n:,.0f})")
        if cua_cost == 0 and cua_in == 0:
            L.append("\n> **Note:** CUA tokens/cost are 0 — this run predates CUA token capture "
                     "(only new runs record it).")
        L.append("")

    # --- Node dynamics ---
    if done:
        si = sum(r.get("initial_cua") or 0 for r in done)
        sa = sum(r.get("added_total") or 0 for r in done)
        sr_ = sum(r.get("added_retry") or 0 for r in done)
        sif = sum(r.get("added_init_from") or 0 for r in done)
        sv = sum(r.get("added_variant") or 0 for r in done)
        grew = sum(1 for r in done if (r.get("added_total") or 0) > 0)
        L.append("## Node dynamics\n")
        L.append("| Metric | Value |")
        L.append("|---|---|")
        L.append(f"| Initial CUA subtasks | {si} (mean {si/n:.1f}/task) |")
        L.append(f"| Dynamically added nodes | {sa} (mean {sa/n:.1f}/task) — {grew}/{n} tasks grew |")
        L.append(f"| ├─ retry (fresh) | {sr_} |")
        L.append(f"| ├─ init_from (inherit state) | {sif} |")
        L.append(f"| └─ variant (alt strategy) | {sv} |")
        L.append("")

    # --- Replan effect ---
    if done:
        rc = sum(r.get("replan_calls") or 0 for r in done)
        rn = sum(r.get("replan_no_change") or 0 for r in done)
        ri = sum(r.get("replan_instr_only") or 0 for r in done)
        rs = sum(r.get("replan_structural") or 0 for r in done)
        applied = ri + rs
        tasks_structural = sum(1 for r in done if (r.get("replan_structural") or 0) > 0)
        L.append("## Replan effect\n")
        L.append("| Metric | Value |")
        L.append("|---|---|")
        L.append(f"| Replan calls | {rc} |")
        if rc:
            L.append(f"| ├─ no change (confirmed as-is) | {rn} ({rn/rc*100:.0f}%) |")
            L.append(f"| └─ applied | {applied} ({applied/rc*100:.0f}%) |")
        if applied:
            L.append(f"| &nbsp;&nbsp;&nbsp;├─ instruction-only (topology unchanged) | {ri} ({ri/applied*100:.0f}%) |")
            L.append(f"| &nbsp;&nbsp;&nbsp;└─ structural (nodes/edges changed) | {rs} ({rs/applied*100:.0f}%) |")
        L.append(f"| Tasks with ≥1 structural replan | {tasks_structural}/{n} |")
        L.append("")

    # --- Per-domain ---
    bydom: dict[str, list[dict]] = defaultdict(list)
    for r in scored:
        bydom[r["domain"]].append(r)
    if bydom:
        L.append("## By level\n")
        L.append("| Level | Perfect SR | mean $ | mean sec | mean replan |")
        L.append("|---|---|---|---|---|")
        for dom in sorted(bydom, key=_lvl_key):
            rs = bydom[dom]
            ok = sum(1 for r in rs if r["success"])
            mc = sum(r["cost"] or 0 for r in rs) / len(rs)
            md = sum(r["duration"] or 0 for r in rs) / len(rs)
            mr = sum(r["replans_applied"] or 0 for r in rs) / len(rs)
            L.append(f"| {dom} | {_fmt_pct(ok, len(rs))} | {mc:.3f} | {md:.0f}s | {mr:.1f} |")
        L.append("")

    # --- Per-task ---
    L.append("## Per-task\n")
    L.append("| Score | Level | $ | sec | Replans | Subtasks | Steps | Actions | Init nodes | Final nodes | Task ID |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(done, key=lambda x: (_lvl_key(x["domain"]), -(x["score"] or 0))):
        sc = r["score"]
        mark = "✅" if r["success"] else ("⚠️" if isinstance(sc, (int, float)) and sc > 0 else "❌")
        sc_s = f"{sc:.2f}" if isinstance(sc, (int, float)) else str(sc)
        L.append(f"| {mark} {sc_s} | {r['domain'] or '?'} | {(r['cost'] or 0):.3f} | "
                 f"{(r['duration'] or 0):.0f}s | {r['replans_applied'] or 0} | {r['n_subtasks'] or 0} | "
                 f"{r.get('agent_steps') or 0} | {r.get('agent_actions') or 0} | "
                 f"{r.get('initial_cua') or 0} | {r.get('final_nodes') or 0} | `{r['task_id']}` |")
    for r in stuck + incomplete:
        L.append(f"| {r['state']} | — | — | — | — | — | — | — | — | — | `{r['task_id']}` |")
    L.append("")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Aggregate analysis over an Odysseys MACU run dir.")
    ap.add_argument("run_dir", help="Run root, e.g. runs/odysseys45_qwen37plus_replan5")
    ap.add_argument("--tasks-file", help="Odysseys tasks JSON (levels + expected total). "
                                         "Default: data/odysseys/odysseys45.json")
    ap.add_argument("--eval-json", help="Rubric-eval JSON to read scores from. "
                                        "Default: odysseys_eval_fulltext.json if present, "
                                        "else odysseys_eval.json in the run dir.")
    ap.add_argument("--md", nargs="?", const="__DEFAULT__",
                    help="Write the analysis as a markdown doc. With no path, "
                         "defaults to reports/<run_name>_run_summary.md")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Not a directory: {run_dir}")
    # guard: make sure this is a run root, not a single task dir
    if (run_dir / "final_results.json").exists():
        raise SystemExit(
            f"{run_dir} looks like a single task dir (has final_results.json). "
            "Use scripts/analyze_task.py for one task, or pass the run root here.")

    # Odysseys defaults: levels file + prefer the corrected full-text eval.
    tasks_file = args.tasks_file
    if not tasks_file:
        default_tf = Path(__file__).resolve().parent.parent / "data/odysseys/odysseys45.json"
        if default_tf.exists():
            tasks_file = str(default_tf)
    eval_json = args.eval_json
    if not eval_json:
        ft = run_dir / "odysseys_eval_fulltext.json"
        if ft.exists():
            eval_json = str(ft)
            print(f"  (scores from {ft.name} — corrected full-text eval)")

    recs = report(run_dir, tasks_file, use_color=not args.no_color, eval_json=eval_json)
    if args.md is not None:
        if args.md == "__DEFAULT__":
            reports_dir = Path(__file__).resolve().parent.parent / "reports"
            md_path = str(reports_dir / f"{run_dir.name}_run_summary.md")
        else:
            md_path = args.md
        write_md(recs, run_dir, md_path, tasks_file)
        print(f"  markdown → {md_path}\n")


if __name__ == "__main__":
    main()
