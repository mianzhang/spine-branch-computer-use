#!/usr/bin/env python3
"""Classify OSWorld-V2 (test_v2_106) tasks by decomposability.

Mirrors scripts/classify_wtb_decomposability.py, adapted for single-VM DESKTOP
GUI tasks. The gate for "multi-agent width helps": a task must have >=2
INDEPENDENT subgoals whose results merge CHEAPLY (files/text) AND that do NOT
have to mutate the SAME live VM (files/open apps). Desktop tasks usually operate
on one coherent VM, so `shared_vm_state` (the single-parent VM constraint) is the
decisive field: true => decomposable only on paper, hostile to a multi-VM
executor (spine carries it, branches can't).

Model: claude-opus-4-8 via the LiteLLM proxy (same model as the MACU manager).
Output: reports/osworld_v2_decomposability.{json,md-inputs}
"""
import os, sys, json, time, collections
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, ".")
sys.path.insert(0, os.environ.get("OSWORLD_V2_ROOT", "/home/ec2-user/macu/OSWorld-V2"))
os.environ.setdefault("OSWORLD_FILE_BASE_URL", "/home/ec2-user/macu/OSWorld-V2/cache/osworld_v2_assets")
os.environ.setdefault("WEBSITE_HOST_SUFFIX", "web.hku.icu")

import openai
from utils.osworld_v2 import load_osworld_v2_tasks

SPLIT = sys.argv[1] if len(sys.argv) > 1 else "data/osworld_v2/test_v2_106.json"
tasks = load_osworld_v2_tasks(SPLIT)
print(f"loaded {len(tasks)} tasks from {SPLIT}", flush=True)

c = openai.OpenAI(base_url=os.environ["OPENAI_BASE_URL"], api_key=os.environ["OPENAI_API_KEY"])

SYS = (
"You classify a DESKTOP computer-use task (single Ubuntu VM, GUI apps like GIMP, LibreOffice/WPS, "
"Chrome, VS Code, file manager) by whether a MULTI-AGENT system could split it into PARALLEL subtasks "
"with real benefit. These tasks manipulate files and app state inside ONE virtual machine. Apply this "
"strict test. Output JSON only.\n"
"Fields:\n"
"structure: one of\n"
"  'parallel_decomposable' = has >=2 INDEPENDENT subgoals (no subgoal needs another's output) AND each "
"subgoal is self-contained/executable alone AND the merge is CHEAP (assemble files / concatenate results / "
"compare values). Multi-agent WIDTH could help.\n"
"  'sequential_multistep' = multiple steps but CHAINED (a step needs a prior step's result, e.g. download "
"then edit then export; or a pipeline across apps). Width does NOT help; only one coherent VM lineage does.\n"
"  'atomic' = a single tight flow in one app (edit one image, format one sheet, change one setting, fill one form).\n"
"n_independent_subgoals: integer (how many subgoals could run in parallel; 1 if none).\n"
"shared_vm_state: true if the subgoals must act on the SAME live VM state — the same files being edited, the "
"same open app windows, or one final artifact assembled in place — so they CANNOT run on separate machines and "
"be merged. For most single-VM desktop tasks this is true. false only if independent subgoals each produce a "
"separate file/text artifact that a final step assembles (the merge is data-only).\n"
"one_line_reason: string (<=25 words).")

def classify(t):
    apps = ", ".join(t.get("related_apps", []) or []) or "unknown"
    user = f"Apps: {apps}\nTask: {t['instruction']}"
    for attempt in range(5):
        try:
            r = c.chat.completions.create(
                model="claude-opus-4-8",
                messages=[{"role": "system", "content": SYS}, {"role": "user", "content": user}],
                max_tokens=2000, response_format={"type": "json_object"})
            content = (r.choices[0].message.content or "").strip()
            if not content:
                raise ValueError("empty content (proxy rate-limit?)")
            d = json.loads(content)
            return dict(task_id=t["task_id"], domain=t.get("domain"),
                        related_apps=t.get("related_apps", []),
                        structure=d.get("structure"),
                        n_independent_subgoals=d.get("n_independent_subgoals"),
                        shared_vm_state=d.get("shared_vm_state"),
                        reason=d.get("one_line_reason", ""))
        except Exception as e:
            if attempt == 4:
                return dict(task_id=t["task_id"], domain=t.get("domain"),
                            related_apps=t.get("related_apps", []), structure="ERROR",
                            n_independent_subgoals=None, shared_vm_state=None, reason=str(e)[:100])
            time.sleep(1.5 * (attempt + 1))  # backoff on rate-limit / empty content
    return None

out = []
with ThreadPoolExecutor(max_workers=1) as ex:
    for i, res in enumerate(ex.map(classify, tasks)):
        out.append(res)
        if (i + 1) % 20 == 0:
            print("...", i + 1, flush=True)

os.makedirs("reports", exist_ok=True)
json.dump(out, open("reports/osworld_v2_decomposability.json", "w"), indent=2)

struct = collections.Counter(o["structure"] for o in out)
n = len(out)
print(f"\n=== STRUCTURE (n={n}) ===")
for k, v in struct.most_common():
    print(f"  {v:3d}  ({100*v/n:4.1f}%)  {k}")

dec = [o for o in out if o["structure"] == "parallel_decomposable"]
branch_ok = [o for o in dec if o["shared_vm_state"] is False]
print(f"\nparallel_decomposable: {len(dec)}/{n} ({100*len(dec)/n:.1f}%)")
print(f"  ...with shared_vm_state=True  (single-parent VM conflict; spine-only): {len(dec)-len(branch_ok)}")
print(f"  ...with shared_vm_state=False (data-only merge; BRANCH-exploitable):   {len(branch_ok)}")
print(f"\nBRANCH-exploitable (width helps a multi-VM executor): {len(branch_ok)}/{n} = {100*len(branch_ok)/n:.1f}%")
print(f"SPINE-only / atomic (single coherent VM is the right structure): {n-len(branch_ok)}/{n} = {100*(n-len(branch_ok))/n:.1f}%")
