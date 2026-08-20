#!/usr/bin/env bash
# Spine-branch on odysseys45, gpt-5.4-mini with NATIVE computer use, xhigh reasoning,
# and step-budget-awareness (SBA).
#   planner/manager : claude-opus-4-8
#   CUA             : gpt-5.4-mini  (--cua-provider openai, native computer-use tool)
#   reasoning       : xhigh
#   step_budget_awareness : ON  (now wired into the native GPT54Agent loop)
#   coordination    : spine-branch (run_spine_branch.py)
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spinebranch_gpt54mini_native_sba
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--reasoning_effort xhigh --step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
