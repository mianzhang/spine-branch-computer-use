#!/usr/bin/env bash
# Spine-branch on odysseys45 WITH step-budget-awareness (SBA), qwen3.6-27B CUA.
#   planner/manager : claude-opus-4-8   (--manager-provider openai)
#   CUA             : fireworks_ai/deployed/t5cvm6h4 (qwen3.6-27B, --cua-provider qwen)
#   coordination    : spine-branch (run_spine_branch.py; --max-replans ignored)
#   step_budget_awareness : ON
# A/B partner to the plain spine-branch qwen3.6 run (runs/odysseys45_spinebranch_qwen36,
# SBA off). Generalization check for the qwen3.7-plus SBA result. Identical knobs;
# ONLY difference vs the plain run is the step-budget reminder.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spinebranch_qwen36_sba
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
