#!/usr/bin/env bash
# Single-agent (nomanager) baseline over OSWorld-V2 test_v2_106 with Qwen3.7-Plus.
# Multi-worker; workers share --result-dir and claim tasks atomically.
set -uo pipefail
cd "$(dirname "$0")/../../.."

set -a; source .env; set +a   # API keys

# --- v2 overrides (v1 disk/overlays untouched) ---
export OSWORLD_V2_ROOT="/home/ec2-user/macu/OSWorld-V2"
export OSWORLD_ROOT="$OSWORLD_V2_ROOT"
export OSWORLD_APPTAINER_VMS_DIR="/home/ec2-user/macu/multi-agent-computer-use/osworld_vms_v2"
export OSWORLD_APPTAINER_OVERLAY_DIR="/home/ec2-user/macu/multi-agent-computer-use/apptainer/overlays_v2"
export OSWORLD_FILE_BASE_URL="$OSWORLD_V2_ROOT/cache/osworld_v2_assets"
export WEBSITE_HOST_SUFFIX="web.hku.icu"

TASKS_FILE="${TASKS_FILE:-data/osworld_v2/test_v2_106.json}"
RESULT_DIR="${RESULT_DIR:-runs/osworld_v2_106_single_qwen37plus}"
CUA_MODEL="${CUA_MODEL:-fireworks_ai/qwen3p7-plus}"
MAX_STEPS="${MAX_STEPS:-100}"          # single-agent convention
NUM_WORKERS="${NUM_WORKERS:-6}"
mkdir -p "$RESULT_DIR"

echo "OSWorld-V2 test_v2_106 single-agent: $NUM_WORKERS workers, cua=$CUA_MODEL, max_steps=$MAX_STEPS -> $RESULT_DIR"

pids=()
for w in $(seq 1 "$NUM_WORKERS"); do
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
    > "$RESULT_DIR/worker_${w}.log" 2>&1 &
  pids+=($!)
  echo "  worker $w -> pid ${pids[-1]}"
  sleep 3
done

echo "Waiting for $NUM_WORKERS worker(s)..."
for pid in "${pids[@]}"; do wait "$pid" || echo "worker $pid exited non-zero"; done

echo "===== RESULTS: $RESULT_DIR ====="
.venv/bin/python - "$RESULT_DIR" <<'PY'
import json, sys, glob, os
rd = sys.argv[1]
scores = {}
for fr in glob.glob(os.path.join(rd, "*", "final_results.json")):
    tid = os.path.basename(os.path.dirname(fr))
    try: scores[tid] = json.load(open(fr)).get("osworld_evaluator_score")
    except Exception as e: scores[tid] = f"ERR {e}"
vals = [v for v in scores.values() if isinstance(v, (int, float))]
succ = sum(1 for v in vals if v >= 1.0)
partial = sum(v for v in vals) if vals else 0.0
print(f"scored: {len(vals)}/106   success(>=1.0): {succ}   SR={succ/len(vals)*100:.1f}%   mean_score={partial/len(vals):.3f}" if vals else "no scored tasks yet")
PY
echo "DONE $(date)" > "$RESULT_DIR/run_done.flag"
