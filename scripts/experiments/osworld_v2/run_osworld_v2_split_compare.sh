#!/usr/bin/env bash
# OSWorld-V2 real comparison on a decomposability split: single-agent vs
# step-budget-aware spine-branch, gpt-5.6-luna CUA. Runs the two configs
# sequentially into separate result dirs, then prints scores.
#
# Fairness design (global budget ~300):
#   single-agent  : 1 subtask, --max_steps 300
#   spine-branch  : --step_budget_awareness (per-subtask "steps remaining" nudge)
#                   --max-replans 0          (no variant/retry fan-out)
#                   per-subtask --max_steps SB_STEPS (default 150)
#   -> report agent-steps/task for both (analyze_run) to efficiency-normalize;
#      the residual total-budget difference is an explicit measured number.
#
# Usage: SPLIT=branchable bash scripts/experiments/run_osworld_v2_split_compare.sh
set -uo pipefail
cd "$(dirname "$0")/../../.."
set -a; source .env; set +a

export OSWORLD_V2_ROOT="/home/ec2-user/macu/OSWorld-V2"
export OSWORLD_ROOT="$OSWORLD_V2_ROOT"
export OSWORLD_APPTAINER_VMS_DIR="/home/ec2-user/macu/multi-agent-computer-use/osworld_vms_v2"
export OSWORLD_APPTAINER_OVERLAY_DIR="/home/ec2-user/macu/multi-agent-computer-use/apptainer/overlays_v2"
export OSWORLD_FILE_BASE_URL="$OSWORLD_V2_ROOT/cache/osworld_v2_assets"
export WEBSITE_HOST_SUFFIX="web.hku.icu"

SPLIT="${SPLIT:-branchable}"
TASKS_FILE="data/osworld_v2/${SPLIT}.json"
CUA_MODEL="${CUA_MODEL:-gpt-5.6-luna}"
CUA_PROVIDER="${CUA_PROVIDER:-openai}"   # openai (gpt-5.6-*) | qwen (qwen3.x)
RUN_TAG="${RUN_TAG:-luna}"            # goes into result-dir names (model/effort id)
REASONING_EFFORT="${REASONING_EFFORT:-medium}"   # CUA reasoning effort (GPT54Agent)
MANAGER_MODEL="${MANAGER_MODEL:-claude-opus-4-8}"
SINGLE_STEPS="${SINGLE_STEPS:-300}"
SB_STEPS="${SB_STEPS:-200}"          # per-subtask budget for spine-branch (user-set)
MAX_TASK_TIMEOUT="${MAX_TASK_TIMEOUT:-5400}"   # whole-task wall-clock cap (s); default 1.5h
NUM_WORKERS="${NUM_WORKERS:-6}"
CONFIGS="${CONFIGS:-single spinebranch}"

worker_loop () {  # $1=result_dir ; $2.. = command
  local rd="$1"; shift; mkdir -p "$rd"; local pids=()
  for w in $(seq 1 "$NUM_WORKERS"); do
    "$@" > "$rd/worker_${w}.log" 2>&1 & pids+=($!); sleep 3
  done
  for pid in "${pids[@]}"; do wait "$pid" || echo "  worker $pid nonzero"; done
}
report () {
  .venv/bin/python - "$1" <<'PY'
import json,sys,glob,os
rd=sys.argv[1]; v=[]
for fr in sorted(glob.glob(os.path.join(rd,"*","final_results.json"))):
    s=json.load(open(fr)).get('osworld_evaluator_score'); v.append(s if isinstance(s,(int,float)) else 0.0)
n=len(v)
print(f"  {os.path.basename(rd)}: scored={n}  mean={sum(v)/n:.3f}  SR={sum(1 for x in v if x>=1)}/{n}" if n else f"  {rd}: none")
PY
}

for cfg in $CONFIGS; do
  if [ "$cfg" = "single" ]; then
    RD="runs/osworld_v2_${SPLIT}_single_${RUN_TAG}"
    echo "=== [$SPLIT] single-agent  $CUA_MODEL (effort=$REASONING_EFFORT)  max_steps=$SINGLE_STEPS -> $RD ==="
    worker_loop "$RD" \
      .venv/bin/python -u run_macu.py "$TASKS_FILE" --result-dir "$RD" \
        --osworld-version v2 --osworld-root "$OSWORLD_ROOT" \
        --osworld-data-dir "$OSWORLD_ROOT/evaluation_examples" \
        --no-manager --manager-provider openai --manager-model gpt-5.4-mini --max-task-timeout "$MAX_TASK_TIMEOUT" \
        --cua-provider "$CUA_PROVIDER" --max-parallelism 1 --max_steps "$SINGLE_STEPS" \
        --reasoning_effort "$REASONING_EFFORT" \
        -- --headless --provider_name apptainer --model "$CUA_MODEL" \
           --max_steps "$SINGLE_STEPS" \
           --client_password osworld-public-evaluation --sleep_after_execution 3.0
    report "$RD"
  else
    RD="runs/osworld_v2_${SPLIT}_spinebranch_${RUN_TAG}_sba"
    echo "=== [$SPLIT] spine-branch(SBA,replan0)  $CUA_MODEL (effort=$REASONING_EFFORT)  per-subtask=$SB_STEPS -> $RD ==="
    worker_loop "$RD" \
      .venv/bin/python -u run_spine_branch.py "$TASKS_FILE" --result-dir "$RD" \
        --osworld-version v2 --osworld-root "$OSWORLD_ROOT" \
        --osworld-data-dir "$OSWORLD_ROOT/evaluation_examples" \
        --manager-provider openai --manager-model "$MANAGER_MODEL" --max-task-timeout "$MAX_TASK_TIMEOUT" \
        --max-replans 0 --cua-provider "$CUA_PROVIDER" --max-parallelism 4 --max_steps "$SB_STEPS" \
        --reasoning_effort "$REASONING_EFFORT" \
        -- --headless --provider_name apptainer --model "$CUA_MODEL" \
           --max_steps "$SB_STEPS" --step_budget_awareness \
           --client_password osworld-public-evaluation --sleep_after_execution 3.0
    report "$RD"
  fi
done
echo "DONE $(date)" > "runs/osworld_v2_${SPLIT}_compare.flag"
