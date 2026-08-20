#!/usr/bin/env bash
# PLAIN spine-branch (NO SBA) on odysseys155, gpt-5.4-mini native computer-use, xhigh.
# The decisive cell to disentangle coordination from SBA: matches
# run_odysseys155_spinebranch_gpt54mini_sba.sh exactly EXCEPT --step_budget_awareness
# is removed. Compare vs runs/odysseys155_macu_gpt54mini_replan5 (also xhigh) to see
# spine-branch's coordination effect on gpt-5.4-mini once SBA (separately harmful to
# gpt) is off.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys155.json
export RESULT_DIR=runs/odysseys155_spinebranch_gpt54mini
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--reasoning_effort xhigh"
exec bash scripts/lib/run_odysseys.sh
