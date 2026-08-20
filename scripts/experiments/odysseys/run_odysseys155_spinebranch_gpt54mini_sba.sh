#!/usr/bin/env bash
# Spine-branch +SBA on the odysseys 155-task complement, gpt-5.4-mini native computer-use, xhigh.
# Matches run_odysseys45_spinebranch_opus48_gpt54mini_native_sba.sh (only TASKS_FILE/RESULT_DIR differ).
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys155.json
export RESULT_DIR=runs/odysseys155_spinebranch_gpt54mini_sba
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--reasoning_effort xhigh --step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
