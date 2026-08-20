#!/usr/bin/env python3
"""Smoke-boot the OSWorld-V2 guest image via MACU's apptainer provider.

Zero-integration test: boots the v2 qcow2 with the *existing* (v1) DesktopEnv +
apptainer provider, waits for the in-guest server, grabs a screenshot, and runs
one trivial pyautogui action. Proves the v2 disk boots under qemu/apptainer and
the guest HTTP server (screenshot/execute) is reachable — before any v2-specific
Python plumbing. Does NOT touch the v1 image or overlays.

Run:  MACU/.venv/bin/python scripts/smoke_boot_osworld_v2.py
"""
import os
import sys
import time

MACU_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSWORLD_ROOT = os.environ.get("OSWORLD_ROOT", "/home/ec2-user/macu/OSWorld")

# v2 wiring: boot osworld_vms_v2/Ubuntu.qcow2 (symlink -> v2 image); separate
# overlay dir so we never touch v1 overlays. SIF is shared (qemu runtime only).
os.environ.setdefault("OSWORLD_APPTAINER_VMS_DIR", os.path.join(MACU_ROOT, "osworld_vms_v2"))
os.environ.setdefault("OSWORLD_APPTAINER_OVERLAY_DIR", os.path.join(MACU_ROOT, "apptainer", "overlays_v2_smoke"))
os.environ.setdefault("OSWORLD_FILE_BASE_URL", "/home/ec2-user/macu/OSWorld-V2/cache/osworld_v2_assets")
os.environ.setdefault("WEBSITE_HOST_SUFFIX", "web.hku.icu")

sys.path.insert(0, OSWORLD_ROOT)   # desktop_env.*
sys.path.insert(0, MACU_ROOT)      # osworld.patches

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("smoke_v2")

from desktop_env.desktop_env import DesktopEnv          # noqa: E402
from osworld.patches import apply as apply_patches       # noqa: E402
apply_patches()

log.info("VMS_DIR=%s", os.environ["OSWORLD_APPTAINER_VMS_DIR"])
log.info("base image -> %s", os.path.realpath(os.path.join(os.environ["OSWORLD_APPTAINER_VMS_DIR"], "Ubuntu.qcow2")))

t0 = time.time()
env = DesktopEnv(
    path_to_vm=None,
    action_space="pyautogui",
    provider_name="apptainer",
    region=None,
    snapshot_name="init_state",
    screen_size=(1920, 1080),
    headless=True,
    os_type="Ubuntu",
    require_a11y_tree=False,
    enable_proxy=False,
    client_password=os.environ.get("OSWORLD_CLIENT_PASSWORD", "osworld-public-evaluation"),
)
env.is_environment_used = False   # don't revert; just use the freshly-booted overlay
log.info("DesktopEnv constructed in %.1fs; vm_ip=%s server_port=%s path=%s",
         time.time() - t0, getattr(env, "vm_ip", None), getattr(env, "server_port", None),
         getattr(env, "path_to_vm", None))

ok = {"screenshot": False, "os_probe": False, "action": False}
try:
    # give the desktop a moment to settle after boot
    time.sleep(20)

    shot = env.controller.get_screenshot()
    out_png = os.path.join(MACU_ROOT, "osworld_vms_v2", "smoke_screenshot.png")
    if shot:
        with open(out_png, "wb") as f:
            f.write(shot)
        ok["screenshot"] = True
        log.info("SCREENSHOT ok: %d bytes -> %s", len(shot), out_png)

    # probe the guest: what apps/OS? (proves /execute works)
    try:
        res = env.controller.execute_python_command(
            "import subprocess;"
            "print(subprocess.run(['bash','-c',"
            "'echo HOST=$(hostname); echo USER=$(whoami); ls /usr/bin | egrep -i \\'wps|shotcut|zotero|musescore|reaper|gimp|libreoffice|google-chrome\\' | sort -u'"
            "],capture_output=True,text=True).stdout)"
        )
        log.info("GUEST PROBE:\n%s", res)
        ok["os_probe"] = True
    except Exception as e:
        log.warning("guest probe failed: %s", e)

    # one trivial action
    try:
        env.step("pyautogui.moveTo(960, 540)", 1.0)
        ok["action"] = True
        log.info("ACTION ok (moveTo)")
    except Exception as e:
        log.warning("action failed: %s", e)

finally:
    try:
        env.close()
    except Exception as e:
        log.warning("close failed: %s", e)

log.info("SMOKE RESULT: %s   (total %.1fs)", ok, time.time() - t0)
print("SMOKE_JSON", ok)
sys.exit(0 if ok["screenshot"] else 2)
