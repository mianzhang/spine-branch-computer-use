#!/usr/bin/env bash
# MANAGER-MODEL ABLATION (weak planner) — qwen3.6-27B CUA.
# Clone of run_odysseys45_spinebranch_opus48_qwen36_sba.sh; ONLY the planner differs.
#   planner/manager : gpt-5.4-mini   (WEAK; baseline used claude-opus-4-8)
#   CUA             : fireworks_ai/deployed/t5cvm6h4 (qwen3.6-27B, --cua-provider qwen) [fixed]
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spinebranch_gpt54minimgr_qwen36_sba
export MANAGER_MODEL=gpt-5.4-mini
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
