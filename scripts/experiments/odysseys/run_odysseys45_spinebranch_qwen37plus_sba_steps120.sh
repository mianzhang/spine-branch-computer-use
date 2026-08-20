#!/usr/bin/env bash
# Spine-and-branch on odysseys45 WITH step-budget-awareness (SBA).
#   planner/manager : claude-opus-4-8   (--manager-provider openai)
#   CUA             : fireworks_ai/qwen3p7-plus (--cua-provider qwen)
#   coordination    : spine-branch (run_spine_branch.py; --max-replans ignored)
#   step_budget_awareness : ON  (--step_budget_awareness, appended via CUA_EXTRA_ARGS)
# A/B partner to run_odysseys45_spinebranch_opus48_qwen37plus.sh (SBA OFF).
# Same models/knobs; the ONLY difference is the step-budget reminder appended to
# each CUA step. Tests whether the nudge reduces max_steps stalls / lifts SR.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spinebranch_qwen37plus_sba_steps120
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=qwen
export MAX_STEPS=120
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
