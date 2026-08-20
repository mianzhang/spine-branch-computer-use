#!/usr/bin/env bash
# SBP ablation: macu_gpt54mini_replan5_sbp (mirrors baseline runs/odysseys45_macu_gpt54mini_replan5 + --step_budget_awareness).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_macu_gpt54mini_replan5_sbp
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=60
export MAX_REPLANS=5
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export EXTRA_ARGS=""
export CUA_EXTRA_ARGS="--step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
