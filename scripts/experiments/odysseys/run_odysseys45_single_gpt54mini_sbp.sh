#!/usr/bin/env bash
# SBP ablation: single_gpt54mini_sbp (mirrors baseline runs/odysseys45_single_gpt54mini + --step_budget_awareness).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_single_gpt54mini_sbp
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=1
export EXTRA_ARGS="--no-manager"
export CUA_EXTRA_ARGS="--reasoning_effort xhigh --step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
