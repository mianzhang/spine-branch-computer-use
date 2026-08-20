#!/usr/bin/env python3
"""Full v2-path validation on OSWorld-V2 task_003.

Exercises the REAL v2 pipeline end-to-end against the apptainer/QEMU VM:
  load task class -> DesktopEnv(v2) -> env.reset(task) runs task.setup()
  (asset download from local cache + app launch) -> screenshot ->
  env.evaluate() runs task.evaluate(env) -> real float score.

We do NOT solve the task, so a correct pipeline returns score 0.0 (no composite
files on the desktop). The point is that loader + setup + programmatic evaluate
all execute without error and produce a real number.

Run: MACU/.venv/bin/python scripts/validate_v2_task003.py
"""
import os
import sys
import time
import traceback

MACU_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSWORLD_V2 = "/home/ec2-user/macu/OSWorld-V2"

# --- v2 env wiring (v1 disk/overlays untouched) ---
os.environ.setdefault("OSWORLD_APPTAINER_VMS_DIR", os.path.join(MACU_ROOT, "osworld_vms_v2"))
os.environ.setdefault("OSWORLD_APPTAINER_OVERLAY_DIR", os.path.join(MACU_ROOT, "apptainer", "overlays_v2"))
os.environ.setdefault("OSWORLD_FILE_BASE_URL", os.path.join(OSWORLD_V2, "cache", "osworld_v2_assets"))
os.environ.setdefault("WEBSITE_HOST_SUFFIX", "web.hku.icu")
os.environ.setdefault("SCREEN_WIDTH", "1920")
os.environ.setdefault("SCREEN_HEIGHT", "1080")

# desktop_env + evaluation_examples resolve to the V2 checkout; osworld.patches from MACU
sys.path.insert(0, OSWORLD_V2)
sys.path.insert(0, MACU_ROOT)

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("v2_val")

def phase(name):
    log.info("========== PHASE: %s ==========", name)

phase("import v2 desktop_env + apply MACU patches")
from desktop_env.desktop_env import DesktopEnv            # v2
from osworld.patches import apply as apply_patches
apply_patches()
log.info("v2 DesktopEnv module: %s", DesktopEnv.__module__)

phase("load task_003 class")
import importlib
mod = importlib.import_module("evaluation_examples.task_class.task_003")
TaskCls = getattr(mod, "TASK_CLASS", None) or getattr(mod, "Task", None)
task = TaskCls()
log.info("task id=%s snapshot=%s related_apps=%s", task.get("id"), task.get("snapshot"), task.get("related_apps"))
log.info("instruction[:120]=%s", (task.get("instruction") or "")[:120])
log.info("has custom setup=%s  has custom evaluate=%s",
         hasattr(task, "setup") and callable(task.setup),
         hasattr(task, "evaluate") and callable(task.evaluate))

env = None
result = {"loaded": True, "env_built": False, "setup_ok": False, "screenshot": False,
          "evaluate_ran": False, "score": None}
t0 = time.time()
try:
    phase("build DesktopEnv(apptainer, v2 image)")
    env = DesktopEnv(
        provider_name="apptainer",
        path_to_vm=None,
        snapshot_name="init_state",
        action_space="pyautogui",
        cache_dir=os.path.join(MACU_ROOT, "osworld_vms_v2", "v2_cache"),
        screen_size=(1920, 1080),
        headless=True,
        require_a11y_tree=False,
        os_type="Ubuntu",
        client_password="osworld-public-evaluation",
    )
    env.is_environment_used = False   # keep freshly-booted overlay; no revert
    result["env_built"] = True
    log.info("env built in %.1fs vm_ip=%s port=%s path=%s",
             time.time() - t0, getattr(env, "vm_ip", None), getattr(env, "server_port", None),
             getattr(env, "path_to_vm", None))

    phase("env.reset(task) -> runs task.setup() (asset download + launch gimp/impress)")
    tr = time.time()
    obs = env.reset(task_config=task)
    result["setup_ok"] = True
    log.info("reset/setup completed in %.1fs; obs keys=%s", time.time() - tr,
             list(obs.keys()) if isinstance(obs, dict) else type(obs).__name__)

    # let the apps finish opening, then screenshot to confirm setup visually
    time.sleep(15)
    try:
        shot = env.controller.get_screenshot()
        if shot:
            out_png = os.path.join(MACU_ROOT, "osworld_vms_v2", "task003_after_setup.png")
            open(out_png, "wb").write(shot)
            result["screenshot"] = True
            log.info("post-setup screenshot: %d bytes -> %s", len(shot), out_png)
    except Exception as e:
        log.warning("screenshot failed: %s", e)

    # confirm setup actually staged the files the task expects
    try:
        chk = env.controller.execute_python_command(
            "import subprocess;print(subprocess.run(['bash','-c',"
            "'ls -la /home/user/Desktop/ 2>/dev/null'],capture_output=True,text=True).stdout)")
        log.info("DESKTOP CONTENTS after setup:\n%s", chk)
    except Exception as e:
        log.warning("desktop listing failed: %s", e)

    phase("env.evaluate() -> task.evaluate(env)  (expect 0.0, agent did nothing)")
    te = time.time()
    score = env.evaluate()
    result["evaluate_ran"] = True
    result["score"] = score
    log.info("evaluate() returned %r  (type=%s) in %.1fs", score, type(score).__name__, time.time() - te)

except Exception:
    log.error("EXCEPTION:\n%s", traceback.format_exc())
finally:
    if env is not None:
        try:
            env.close()
            log.info("env closed")
        except Exception as e:
            log.warning("close failed: %s", e)

phase("RESULT")
log.info("%s   (total %.1fs)", result, time.time() - t0)
print("V2_VALIDATION_JSON", result)
# success = the full path ran end-to-end and produced a numeric score
ok = result["setup_ok"] and result["evaluate_ran"] and isinstance(result["score"], (int, float))
sys.exit(0 if ok else 2)
