#!/usr/bin/env bash
# Small OSWorld-V2 test: single-agent vs spine-branch on 5 diverse tasks
# (003/087 pure-spine, 009/017 parallel-branch, 049 mixed), step budget 300,
# Qwen3.7-Plus CUA. For eyeballing trajectories + the spine-branch fan-out before
# the full 106. Runs the two configs sequentially.
set -uo pipefail
cd "$(dirname "$0")/../../.."

set -a; source .env; set +a

# --- v2 overrides (v1 disk/overlays untouched) ---
export OSWORLD_V2_ROOT="/home/ec2-user/macu/OSWorld-V2"
export OSWORLD_ROOT="$OSWORLD_V2_ROOT"
export OSWORLD_APPTAINER_VMS_DIR="/home/ec2-user/macu/multi-agent-computer-use/osworld_vms_v2"
export OSWORLD_APPTAINER_OVERLAY_DIR="/home/ec2-user/macu/multi-agent-computer-use/apptainer/overlays_v2"
export OSWORLD_FILE_BASE_URL="$OSWORLD_V2_ROOT/cache/osworld_v2_assets"
export WEBSITE_HOST_SUFFIX="web.hku.icu"

TASKS_FILE="${TASKS_FILE:-data/osworld_v2/mini5.json}"
CUA_MODEL="${CUA_MODEL:-fireworks_ai/qwen3p7-plus}"
MANAGER_MODEL="${MANAGER_MODEL:-claude-opus-4-8}"
MAX_STEPS="${MAX_STEPS:-300}"
NUM_WORKERS="${NUM_WORKERS:-5}"
CONFIGS="${CONFIGS:-single spinebranch}"

run_config () {
  local cfg="$1" rd="$2"; shift 2
  echo "=========== CONFIG=$cfg  ->  $rd  (max_steps=$MAX_STEPS, cua=$CUA_MODEL) ==========="
  mkdir -p "$rd"
  local pids=()
  for w in $(seq 1 "$NUM_WORKERS"); do
    "$@" > "$rd/worker_${w}.log" 2>&1 &
    pids+=($!); sleep 3
  done
  for pid in "${pids[@]}"; do wait "$pid" || echo "  worker $pid exited non-zero"; done
  echo "----- scores ($rd) -----"
  .venv/bin/python - "$rd" <<'PY'
import json,sys,glob,os
rd=sys.argv[1]
for fr in sorted(glob.glob(os.path.join(rd,"*","final_results.json"))):
    tid=os.path.basename(os.path.dirname(fr))
    print(f"  {tid}: osworld_evaluator_score={json.load(open(fr)).get('osworld_evaluator_score')}")
PY
}

COMMON=( --result-dir "" --osworld-version v2 --osworld-root "$OSWORLD_ROOT"
         --osworld-data-dir "$OSWORLD_ROOT/evaluation_examples"
         --cua-provider qwen --max-parallelism 1 --max_steps "$MAX_STEPS" )
CUA_TAIL=( -- --headless --provider_name apptainer --model "$CUA_MODEL"
           --max_steps "$MAX_STEPS" --client_password osworld-public-evaluation
           --sleep_after_execution 3.0 )

for cfg in $CONFIGS; do
  if [ "$cfg" = "single" ]; then
    RD="runs/osworld_v2_mini_single"
    run_config single "$RD" \
      .venv/bin/python -u run_macu.py "$TASKS_FILE" --result-dir "$RD" \
        --osworld-version v2 --osworld-root "$OSWORLD_ROOT" \
        --osworld-data-dir "$OSWORLD_ROOT/evaluation_examples" \
        --no-manager --manager-provider openai --manager-model "$MANAGER_MODEL" \
        --cua-provider qwen --max-parallelism 1 --max_steps "$MAX_STEPS" \
        "${CUA_TAIL[@]}"
  else
    RD="runs/osworld_v2_mini_spinebranch"
    run_config spinebranch "$RD" \
      .venv/bin/python -u run_spine_branch.py "$TASKS_FILE" --result-dir "$RD" \
        --osworld-version v2 --osworld-root "$OSWORLD_ROOT" \
        --osworld-data-dir "$OSWORLD_ROOT/evaluation_examples" \
        --manager-provider openai --manager-model "$MANAGER_MODEL" \
        --cua-provider qwen --max-parallelism 4 --max_steps "$MAX_STEPS" \
        "${CUA_TAIL[@]}"
  fi
done
echo "DONE $(date)" > runs/osworld_v2_mini_test.flag
