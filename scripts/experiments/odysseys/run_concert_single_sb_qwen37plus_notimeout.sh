#!/usr/bin/env bash
# Re-run the single "concert tour" odysseys task (40735c71...) with Spine-Branch,
# qwen3.7-plus CUA, opus-4-8 manager, SBA on — SAME config as
# runs/odysseys45_spinebranch_qwen37plus_sba, but with TIMEOUTS DISABLED so the
# terminal build_spreadsheet branch (which timed out at 5400s before) can complete.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/concert_single.json
export RESULT_DIR=runs/odysseys_concert_single_sb_qwen37plus_notimeout
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=1
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--step_budget_awareness"
export EXTRA_ARGS="--max-task-timeout 1000000000 --max-subtask-timeout 1000000000"
exec bash scripts/lib/run_odysseys.sh
