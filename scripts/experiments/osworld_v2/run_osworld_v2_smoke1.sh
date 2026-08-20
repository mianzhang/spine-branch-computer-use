#!/usr/bin/env bash
# End-to-end single-agent (nomanager) smoke of the OSWorld-V2 integration on ONE
# task (003). Exercises the full wired path: v2 loader -> graph -> run_cua stages
# via task.setup() -> agent acts -> osworld_evaluator.py (v2) scores the task object.
set -uo pipefail
cd "$(dirname "$0")/../../.."

set -a; source .env; set +a   # API keys

# --- v2 overrides (do NOT touch the v1 disk/overlays) ---
export OSWORLD_V2_ROOT="/home/ec2-user/macu/OSWorld-V2"
export OSWORLD_ROOT="$OSWORLD_V2_ROOT"                       # run_cua imports v2 desktop_env
export OSWORLD_APPTAINER_VMS_DIR="/home/ec2-user/macu/multi-agent-computer-use/osworld_vms_v2"
export OSWORLD_APPTAINER_OVERLAY_DIR="/home/ec2-user/macu/multi-agent-computer-use/apptainer/overlays_v2"
export OSWORLD_FILE_BASE_URL="$OSWORLD_V2_ROOT/cache/osworld_v2_assets"
export WEBSITE_HOST_SUFFIX="web.hku.icu"

TASKS_FILE="${TASKS_FILE:-data/osworld_v2/smoke1.json}"
RESULT_DIR="${RESULT_DIR:-runs/osworld_v2_smoke1}"
CUA_MODEL="${CUA_MODEL:-fireworks_ai/qwen3p7-plus}"   # live model (bdzdey2f Qwen3.6 deployment is dead/404)
MAX_STEPS="${MAX_STEPS:-40}"
mkdir -p "$RESULT_DIR"

echo "OSWorld-V2 single-agent smoke: $TASKS_FILE -> $RESULT_DIR (cua=$CUA_MODEL, max_steps=$MAX_STEPS)"

.venv/bin/python -u run_macu.py "$TASKS_FILE" \
  --result-dir "$RESULT_DIR" \
  --osworld-version v2 \
  --osworld-root "$OSWORLD_ROOT" \
  --osworld-data-dir "$OSWORLD_ROOT/evaluation_examples" \
  --no-manager \
  --manager-provider openai --manager-model gpt-5.4-mini \
  --cua-provider qwen \
  --max-parallelism 1 \
  --max_steps "$MAX_STEPS" \
  -- --headless --provider_name apptainer \
     --model "$CUA_MODEL" --max_steps "$MAX_STEPS" \
     --client_password osworld-public-evaluation --sleep_after_execution 3.0 \
  2>&1 | tee "$RESULT_DIR/run.log"

echo "===== score ====="
.venv/bin/python - "$RESULT_DIR" <<'PY'
import json, sys, glob, os
rd = sys.argv[1]
for fr in glob.glob(os.path.join(rd, "*", "final_results.json")):
    tid = os.path.basename(os.path.dirname(fr))
    d = json.load(open(fr))
    print(f"task {tid}: osworld_evaluator_score={d.get('osworld_evaluator_score')}")
PY
