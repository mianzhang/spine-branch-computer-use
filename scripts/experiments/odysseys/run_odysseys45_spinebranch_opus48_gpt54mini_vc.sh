#!/usr/bin/env bash
# Spine-and-branch on odysseys45 with gpt-5.4-mini CUA + verify-and-continue.
#   planner/manager : claude-opus-4-8
#   CUA             : gpt-5.4-mini  (--cua-provider openai)
#   verify-continue : ON (checker=gemini-3.1-flash-lite, max 1 continuation/subtask)
# A/B partner of run_odysseys45_spinebranch_opus48_gpt54mini.sh.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spinebranch_opus48mgr_gpt54mini_vc
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export EXTRA_ARGS="--verify-continue --max-continuations 1 --checker-model gemini-3.1-flash-lite --checker-screenshots 3"
exec bash scripts/lib/run_odysseys.sh
