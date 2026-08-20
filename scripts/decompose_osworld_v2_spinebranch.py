#!/usr/bin/env python3
"""Measure OSWorld-V2 decomposability by running the REAL spine-branch planner.

Instead of a bespoke rubric, this runs the actual deployment planner
(``prompts/spine_branch_decompose.yaml`` via generate_spine_branch_plan, manager =
claude-opus-4-8) on every task and measures decomposability from the plans the
manager truly produces:
  * n_cua        = # CUA subtasks the manager split the task into
  * n_spine      = # role=spine nodes (the state-carrying VM lineage)
  * n_branch     = # role=branch nodes (disposable VMs returning text; the PARALLEL width)
  * single_node  = n_cua == 1 (manager kept it atomic)

Decomposability, as the system itself sees it:
  * "decomposed"     = n_cua > 1
  * "has_parallel_width" = n_branch >= 2   (>=2 disposable branches to run concurrently)

Saves per-task metrics + the full graphs to reports/osworld_v2_spinebranch_plans.json.
"""
import os, sys, json, time, collections
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, ".")
sys.path.insert(0, os.environ.get("OSWORLD_V2_ROOT", "/home/ec2-user/macu/OSWorld-V2"))
os.environ.setdefault("OSWORLD_FILE_BASE_URL", "/home/ec2-user/macu/OSWorld-V2/cache/osworld_v2_assets")
os.environ.setdefault("WEBSITE_HOST_SUFFIX", "web.hku.icu")

from utils.osworld_v2 import load_osworld_v2_tasks
from utils.spine_branch.plan import generate_spine_branch_plan

SPLIT = sys.argv[1] if len(sys.argv) > 1 else "data/osworld_v2/test_v2_106.json"
MODEL = os.environ.get("MANAGER_MODEL", "claude-opus-4-8")
tasks = load_osworld_v2_tasks(SPLIT)
print(f"loaded {len(tasks)} tasks; planner model={MODEL}", flush=True)


def plan_one(t):
    for attempt in range(4):
        try:
            graph, report, usage, errs = generate_spine_branch_plan(
                t["instruction"], provider="openai", model=MODEL, temperature=0.0)
            subs = graph.get("subtasks", []) or []
            if not subs:
                raise ValueError(f"empty plan (gen_errors={errs})")
            roles = collections.Counter(s.get("role") for s in subs)
            n_branch = roles.get("branch", 0)
            n_spine = roles.get("spine", 0)
            # branches with no dependency on another CUA subtask = launchable at t0
            sub_ids = {s["id"] for s in subs}
            root_branches = sum(
                1 for s in subs if s.get("role") == "branch"
                and not (set(s.get("dependencies", []) or []) & sub_ids))
            return dict(task_id=t["task_id"], domain=t.get("domain"),
                        related_apps=t.get("related_apps", []),
                        n_cua=len(subs), n_spine=n_spine, n_branch=n_branch,
                        root_branches=root_branches,
                        single_node=len(subs) == 1,
                        graph={"subtasks": [
                            {k: s.get(k) for k in ("id", "role", "init_from", "dependencies")}
                            for s in subs]},
                        gen_errors=errs)
        except Exception as e:
            if attempt == 3:
                return dict(task_id=t["task_id"], domain=t.get("domain"),
                            related_apps=t.get("related_apps", []), n_cua=None,
                            error=str(e)[:120])
            time.sleep(2 * (attempt + 1))
    return None


out = []
with ThreadPoolExecutor(max_workers=4) as ex:
    for i, r in enumerate(ex.map(plan_one, tasks)):
        out.append(r)
        if (i + 1) % 10 == 0:
            print("...", i + 1, flush=True)

os.makedirs("reports", exist_ok=True)
json.dump(out, open("reports/osworld_v2_spinebranch_plans.json", "w"), indent=2)

ok = [o for o in out if o.get("n_cua")]
n = len(ok)
errn = len(out) - n
print(f"\n=== SPINE-BRANCH PLANS (n={n} planned, {errn} errors) ===")
single = sum(1 for o in ok if o["single_node"])
multibr = sum(1 for o in ok if o["n_branch"] >= 2)
anybr = sum(1 for o in ok if o["n_branch"] >= 1)
import statistics as st
print(f"single-node plans (manager kept atomic):        {single}/{n} = {100*single/n:.1f}%")
print(f"decomposed (n_cua>1):                            {n-single}/{n} = {100*(n-single)/n:.1f}%")
print(f"has >=1 branch (any parallel disposable VM):     {anybr}/{n} = {100*anybr/n:.1f}%")
print(f"has >=2 branches (real parallel WIDTH):          {multibr}/{n} = {100*multibr/n:.1f}%")
print(f"mean n_cua={st.mean(o['n_cua'] for o in ok):.2f}  mean n_branch={st.mean(o['n_branch'] for o in ok):.2f}  "
      f"mean n_spine={st.mean(o['n_spine'] for o in ok):.2f}")
dist = collections.Counter(o["n_branch"] for o in ok)
print("n_branch distribution:", dict(sorted(dist.items())))
distc = collections.Counter(o["n_cua"] for o in ok)
print("n_cua   distribution:", dict(sorted(distc.items())))
