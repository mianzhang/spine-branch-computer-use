#!/usr/bin/env bash
# Spine-Branch on the 19 genuinely-decomposable OSWorld-2.0 tasks (>=2 non-trivial
# parallel branches under the refined prompt). Same config as the terra branchable
# run EXCEPT: refined osworld-v2 decomposition prompt (--osworld-decompose),
# 200 sub-agent steps (user-set), and a generous 3h task cap to remove the timeout
# confound. Compare to the existing single-agent terra scores on these 19 tasks.
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
RD="${RD:-runs/osworld_v2_decomposable19_spinebranch_terra_xhigh}"
MANAGER_MODEL=claude-opus-4-8
CUA_MODEL=gpt-5.6-terra
CUA_PROVIDER=openai
REASONING_EFFORT=xhigh
SB_STEPS=200
MAX_TASK_TIMEOUT=10800
NUM_WORKERS="${NUM_WORKERS:-4}"
mkdir -p "$RD"
echo "Launching $NUM_WORKERS workers -> $RD  (SB_STEPS=$SB_STEPS, cap=${MAX_TASK_TIMEOUT}s, refined prompt)"

pids=()
for w in $(seq 1 "$NUM_WORKERS"); do
  .venv/bin/python -u run_spine_branch.py "$TASKS_FILE" --result-dir "$RD" \
    --osworld-version v2 --osworld-decompose --osworld-root "$OSWORLD_ROOT" \
    --osworld-data-dir "$OSWORLD_ROOT/evaluation_examples" \
    --manager-provider openai --manager-model "$MANAGER_MODEL" --max-task-timeout "$MAX_TASK_TIMEOUT" \
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
