#!/usr/bin/env python3
"""Test the wired v2 evaluator SUBPROCESS path end-to-end (task_003).

Mirrors the real MACU flow: a CUA leaves a live VM (overlay + running qemu via
the apptainer sidecar); the orchestrator then invokes scripts/osworld_evaluator.py
against it. Here we boot, run task_003 setup, RELEASE (keep qemu alive), then
subprocess osworld_evaluator.py --osworld-version v2 --task-id 003 and read the
score it writes to result.txt. Expect 0.0 (agent did nothing) — a real score
from the wired evaluator entrypoint.
"""
import os, sys, subprocess, time, json

MACU_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSWORLD_V2 = "/home/ec2-user/macu/OSWorld-V2"
os.environ.setdefault("OSWORLD_APPTAINER_VMS_DIR", os.path.join(MACU_ROOT, "osworld_vms_v2"))
os.environ.setdefault("OSWORLD_APPTAINER_OVERLAY_DIR", os.path.join(MACU_ROOT, "apptainer", "overlays_v2_evaltest"))
os.environ.setdefault("OSWORLD_FILE_BASE_URL", os.path.join(OSWORLD_V2, "cache", "osworld_v2_assets"))
os.environ.setdefault("WEBSITE_HOST_SUFFIX", "web.hku.icu")
os.environ.setdefault("OSWORLD_V2_ROOT", OSWORLD_V2)
sys.path.insert(0, OSWORLD_V2)
sys.path.insert(0, MACU_ROOT)

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("v2_evaltest")

from desktop_env.desktop_env import DesktopEnv
from osworld.patches import apply as apply_patches
apply_patches()
from utils.osworld_v2 import load_v2_task_object

task = load_v2_task_object("003")
env = DesktopEnv(provider_name="apptainer", path_to_vm=None, snapshot_name="init_state",
                 action_space="pyautogui", cache_dir=os.path.join(MACU_ROOT, "osworld_vms_v2", "evaltest_cache"),
                 screen_size=(1920, 1080), headless=True, require_a11y_tree=False, os_type="Ubuntu",
                 client_password="osworld-public-evaluation")
env.is_environment_used = False
log.info("booted; overlay=%s", env.path_to_vm)
env.reset(task_config=task)          # run task.setup()
overlay = os.path.abspath(env.path_to_vm)
time.sleep(8)

# hand off: keep qemu alive for the evaluator to re-attach (do NOT close)
if hasattr(env, "release"):
    env.release()
    log.info("released VM (qemu stays alive); overlay=%s", overlay)
else:
    log.warning("no release(); evaluator may not re-attach")

# invoke the wired evaluator subprocess exactly like the orchestrator would
result_path = os.path.join(MACU_ROOT, "osworld_vms_v2", "evaltest_result.txt")
log_path = os.path.join(MACU_ROOT, "osworld_vms_v2", "evaltest_evaluator.log")
for p in (result_path, log_path):
    if os.path.exists(p):
        os.remove(p)
cmd = [sys.executable, os.path.join(MACU_ROOT, "scripts", "osworld_evaluator.py"),
       "--osworld-version", "v2", "--task-id", "003",
       "--task-config", os.path.join(MACU_ROOT, "osworld_vms_v2", "evaltest_dummy.json"),
       "--final-vm-path", overlay,
       "--result-path", result_path, "--log-path", log_path,
       "--provider-name", "apptainer", "--headless",
       "--client-password", "osworld-public-evaluation"]
# a dummy task-config so the arg is satisfied (v2 path uses --task-id, not the file)
json.dump({"id": "003"}, open(os.path.join(MACU_ROOT, "osworld_vms_v2", "evaltest_dummy.json"), "w"))

log.info("invoking evaluator subprocess (cwd=%s)...", OSWORLD_V2)
env_vars = dict(os.environ)
proc = subprocess.run(cmd, cwd=OSWORLD_V2, env=env_vars, capture_output=True, text=True, timeout=300)
log.info("evaluator rc=%s", proc.returncode)
log.info("evaluator stdout tail:\n%s", "\n".join(proc.stdout.strip().splitlines()[-8:]))

score = None
if os.path.exists(result_path):
    score = open(result_path).read().strip()
log.info("RESULT.TXT score = %r", score)

# cleanup: stop qemu if still alive
try:
    subprocess.run(["pkill", "-f", overlay], capture_output=True)
except Exception:
    pass

ok = score is not None and score != "" and proc.returncode == 0
print("V2_EVALUATOR_SUBPROCESS_JSON", {"score": score, "rc": proc.returncode, "ok": ok})
sys.exit(0 if ok else 2)
