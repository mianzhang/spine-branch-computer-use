#!/usr/bin/env bash
# MANAGER-MODEL ABLATION (weak planner) — gpt-5.4-mini CUA.
# Clone of run_odysseys45_spinebranch_opus48_gpt54mini_native_sba.sh; ONLY planner differs.
#   planner/manager : gpt-5.4-mini   (WEAK; baseline used claude-opus-4-8)
#   CUA             : gpt-5.4-mini (--cua-provider openai, --reasoning_effort xhigh) [fixed]
# Note: with this CUA both roles use gpt-5.4-mini; that is the intended weak-planner point.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spinebranch_gpt54minimgr_gpt54mini_sba
export MANAGER_MODEL=gpt-5.4-mini
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--reasoning_effort xhigh --step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
