#!/usr/bin/env bash
# CUA sanity check: single-agent on the mini5 OSWorld-V2 tasks with gpt-5.6-luna,
# step budget 300. Are these tasks off the floor with a stronger executor?
set -uo pipefail
cd "$(dirname "$0")/../../.."
set -a; source .env; set +a

export OSWORLD_V2_ROOT="/home/ec2-user/macu/OSWorld-V2"
export OSWORLD_ROOT="$OSWORLD_V2_ROOT"
export OSWORLD_APPTAINER_VMS_DIR="/home/ec2-user/macu/multi-agent-computer-use/osworld_vms_v2"
export OSWORLD_APPTAINER_OVERLAY_DIR="/home/ec2-user/macu/multi-agent-computer-use/apptainer/overlays_v2"
export OSWORLD_FILE_BASE_URL="$OSWORLD_V2_ROOT/cache/osworld_v2_assets"
export WEBSITE_HOST_SUFFIX="web.hku.icu"

TASKS_FILE="${TASKS_FILE:-data/osworld_v2/mini5.json}"
RD="${RD:-runs/osworld_v2_mini_single_luna}"
CUA_MODEL="${CUA_MODEL:-gpt-5.6-luna}"
MAX_STEPS="${MAX_STEPS:-300}"
NUM_WORKERS="${NUM_WORKERS:-5}"
mkdir -p "$RD"
echo "single-agent gpt-5.6-luna: $TASKS_FILE -> $RD (max_steps=$MAX_STEPS, $NUM_WORKERS workers)"

pids=()
for w in $(seq 1 "$NUM_WORKERS"); do
  .venv/bin/python -u run_macu.py "$TASKS_FILE" --result-dir "$RD" \
    --osworld-version v2 --osworld-root "$OSWORLD_ROOT" \
    --osworld-data-dir "$OSWORLD_ROOT/evaluation_examples" \
    --no-manager --manager-provider openai --manager-model gpt-5.4-mini \
    --cua-provider openai --max-parallelism 1 --max_steps "$MAX_STEPS" \
    -- --headless --provider_name apptainer --model "$CUA_MODEL" \
       --max_steps "$MAX_STEPS" --client_password osworld-public-evaluation \
       --sleep_after_execution 3.0 \
    > "$RD/worker_${w}.log" 2>&1 &
  pids+=($!); sleep 3
done
for pid in "${pids[@]}"; do wait "$pid" || echo "worker $pid nonzero"; done

echo "===== scores ($RD) ====="
.venv/bin/python - "$RD" <<'PY'
import json,sys,glob,os
rd=sys.argv[1]; v=[]
for fr in sorted(glob.glob(os.path.join(rd,"*","final_results.json"))):
    tid=os.path.basename(os.path.dirname(fr)); s=json.load(open(fr)).get('osworld_evaluator_score')
    print(f"  {tid}: {s}"); v.append(s if isinstance(s,(int,float)) else 0.0)
if v: print(f"mean={sum(v)/len(v):.3f}  SR={sum(1 for x in v if x>=1)}/{len(v)}")
PY
echo "DONE $(date)" > "$RD/run_done.flag"
