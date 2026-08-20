#!/usr/bin/env bash
# Spine-and-branch on odysseys45.
#   planner/manager : claude-opus-4-8   (--manager-provider openai)
#   CUA             : fireworks_ai/qwen3p7-plus (--cua-provider qwen)
#   coordination    : spine-branch (run_spine_branch.py; --max-replans ignored)
#   step_budget_awareness : OFF
# Direct analog of run_odysseys_opus48_qwen37plus_replan5.sh (same models/knobs),
# swapping replan-MACU for spine-branch. Reuses scripts/lib/run_odysseys.sh.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spinebranch_opus48mgr_qwen37plus
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
