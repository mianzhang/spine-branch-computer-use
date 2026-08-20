#!/usr/bin/env bash
# Spine-Branch on the 19 decomposable OSWorld-2.0 tasks, gpt-5.6-sol @ xhigh,
# 500 steps per sub-agent, TIMEOUTS DISABLED (task + subtask ~infinite),
# refined osworld-v2 decomposition prompt (--osworld-decompose), site.hku.icu.
set -uo pipefail
cd "$(dirname "$0")/../../.."
set -a; source .env; set +a

export OSWORLD_V2_ROOT="/home/ec2-user/macu/OSWorld-V2"
export OSWORLD_ROOT="$OSWORLD_V2_ROOT"
export OSWORLD_APPTAINER_VMS_DIR="/home/ec2-user/macu/multi-agent-computer-use/osworld_vms_v2"
export OSWORLD_APPTAINER_OVERLAY_DIR="/home/ec2-user/macu/multi-agent-computer-use/apptainer/overlays_v2"
export OSWORLD_FILE_BASE_URL="$OSWORLD_V2_ROOT/cache/osworld_v2_assets"
export WEBSITE_HOST_SUFFIX="${WEBSITE_HOST_SUFFIX:-site.hku.icu}"

TASKS_FILE=data/osworld_v2/decomposable19.json
RD="${RD:-runs/osworld_v2_decomposable19_spinebranch_sol_xhigh_500}"
MANAGER_MODEL=claude-opus-4-8
CUA_MODEL="${CUA_MODEL:-gpt-5.6-sol}"
CUA_PROVIDER=openai
REASONING_EFFORT=xhigh
SB_STEPS=500
NOTIMEOUT=1000000000
NUM_WORKERS="${NUM_WORKERS:-2}"
mkdir -p "$RD"
echo "Launching $NUM_WORKERS workers -> $RD"
echo "  cua=$CUA_MODEL effort=$REASONING_EFFORT steps=$SB_STEPS timeout=DISABLED host=$WEBSITE_HOST_SUFFIX prompt=osworld-v2(refined)"

pids=()
for w in $(seq 1 "$NUM_WORKERS"); do
  .venv/bin/python -u run_spine_branch.py "$TASKS_FILE" --result-dir "$RD" \
    --osworld-version v2 --osworld-decompose --osworld-root "$OSWORLD_ROOT" \
    --osworld-data-dir "$OSWORLD_ROOT/evaluation_examples" \
    --manager-provider openai --manager-model "$MANAGER_MODEL" \
    --max-task-timeout "$NOTIMEOUT" --max-subtask-timeout "$NOTIMEOUT" \
    --max-replans 0 --cua-provider "$CUA_PROVIDER" --max-parallelism 4 --max_steps "$SB_STEPS" \
    --reasoning_effort "$REASONING_EFFORT" \
    -- --headless --provider_name apptainer --model "$CUA_MODEL" \
       --max_steps "$SB_STEPS" --step_budget_awareness \
       --client_password osworld-public-evaluation --sleep_after_execution 3.0 \
    > "$RD/worker_${w}.log" 2>&1 &
  pids+=($!); sleep 3
done
for pid in "${pids[@]}"; do wait "$pid" || echo "worker $pid nonzero"; done
echo "DONE $(date)" > "$RD/complete.flag"
echo "[$RD] complete: $(ls "$RD"/*/final_results.json 2>/dev/null | wc -l) tasks"
