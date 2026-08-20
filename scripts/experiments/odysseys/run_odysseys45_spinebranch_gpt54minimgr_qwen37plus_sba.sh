#!/usr/bin/env bash
# MANAGER-MODEL ABLATION for Spine-Branch (reviewer: does a weak planner degrade it?).
# Identical to run_odysseys45_spinebranch_opus48_qwen37plus_sba.sh EXCEPT the planner:
#   planner/manager : gpt-5.4-mini   (WEAK planner; baseline used claude-opus-4-8)
#   CUA             : fireworks_ai/qwen3p7-plus (--cua-provider qwen)  [held fixed]
#   coordination    : spine-branch, SBA on, max_steps 60, replans 0    [held fixed]
# Compare against baseline runs/odysseys45_spinebranch_qwen37plus_sba (opus planner).
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spinebranch_gpt54minimgr_qwen37plus_sba
export MANAGER_MODEL=gpt-5.4-mini
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
