#!/usr/bin/env bash
# Spine-and-branch on odysseys45 with gpt-5.4-mini as the CUA (subagents).
#   planner/manager : claude-opus-4-8
#   CUA             : gpt-5.4-mini  (--cua-provider openai)
#   verify-continue : OFF (plain)
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spinebranch_opus48mgr_gpt54mini
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
