#!/usr/bin/env bash
# Single-agent gpt-5.6-luna @ xhigh over the FULL OSWorld-2.0 set (106 runnable tasks;
# 2 GitLab tasks excluded). 500-step budget, TIMEOUTS DISABLED (both task and subtask
# caps set to ~infinite), healthy site.hku.icu mock-web infra. Uses the API key in .env.
set -uo pipefail
cd "$(dirname "$0")/../../.."
set -a; source .env; set +a

export OSWORLD_V2_ROOT="/home/ec2-user/macu/OSWorld-V2"
export OSWORLD_ROOT="$OSWORLD_V2_ROOT"
export OSWORLD_APPTAINER_VMS_DIR="/home/ec2-user/macu/multi-agent-computer-use/osworld_vms_v2"
export OSWORLD_APPTAINER_OVERLAY_DIR="/home/ec2-user/macu/multi-agent-computer-use/apptainer/overlays_v2"
export OSWORLD_FILE_BASE_URL="$OSWORLD_V2_ROOT/cache/osworld_v2_assets"
export WEBSITE_HOST_SUFFIX="${WEBSITE_HOST_SUFFIX:-site.hku.icu}"

TASKS_FILE=data/osworld_v2/test_v2_106.json
RD="${RD:-runs/osworld_v2_full106_single_luna_xhigh_500}"
CUA_MODEL=gpt-5.6-luna
CUA_PROVIDER=openai
REASONING_EFFORT=xhigh
STEPS=500
NOTIMEOUT=1000000000    # effectively no timeout (task and subtask)
NUM_WORKERS="${NUM_WORKERS:-6}"
mkdir -p "$RD"
echo "Launching $NUM_WORKERS single-agent workers -> $RD"
echo "  cua=$CUA_MODEL effort=$REASONING_EFFORT steps=$STEPS timeout=DISABLED host=$WEBSITE_HOST_SUFFIX"

pids=()
for w in $(seq 1 "$NUM_WORKERS"); do
  .venv/bin/python -u run_macu.py "$TASKS_FILE" --result-dir "$RD" \
    --osworld-version v2 --osworld-root "$OSWORLD_ROOT" \
    --osworld-data-dir "$OSWORLD_ROOT/evaluation_examples" \
    --no-manager --manager-provider openai --manager-model gpt-5.4-mini \
    --max-task-timeout "$NOTIMEOUT" --max-subtask-timeout "$NOTIMEOUT" \
    --cua-provider "$CUA_PROVIDER" --max-parallelism 1 --max_steps "$STEPS" \
    --reasoning_effort "$REASONING_EFFORT" \
    -- --headless --provider_name apptainer --model "$CUA_MODEL" \
       --max_steps "$STEPS" \
       --client_password osworld-public-evaluation --sleep_after_execution 3.0 \
    > "$RD/worker_${w}.log" 2>&1 &
  pids+=($!); sleep 3
done
for pid in "${pids[@]}"; do wait "$pid" || echo "worker $pid nonzero"; done
echo "DONE $(date)" > "$RD/complete.flag"
echo "[$RD] complete: $(ls "$RD"/*/final_results.json 2>/dev/null | wc -l) tasks"
