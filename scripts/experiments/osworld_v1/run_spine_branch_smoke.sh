#!/usr/bin/env bash
# 1-task smoke test of the spine-branch EXECUTOR (opus planner + qwen3.7-plus CUA).
cd "$(dirname "$0")/../../.."
set -a; source .env; set +a
: "${OSWORLD_ROOT:?}"
RESULT_DIR="runs/smoke_spine_branch"; mkdir -p "$RESULT_DIR"
MAX_STEPS=60
.venv/bin/python -u run_spine_branch.py data/odysseys/smoke1.json \
  --result-dir "$RESULT_DIR" \
  --osworld-root "$OSWORLD_ROOT" \
  --manager-provider openai --manager-model claude-opus-4-8 \
  --cua-provider qwen \
  --max-parallelism 4 \
  --max-replans 0 \
  --max_steps "$MAX_STEPS" \
  -- --headless --provider_name apptainer \
     --model fireworks_ai/qwen3p7-plus --max_steps "$MAX_STEPS" --sleep_after_execution 3.0
