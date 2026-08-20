#!/usr/bin/env bash
# SBP ablation: single_qwen37plus_sbp (mirrors baseline runs/odysseys45_single_qwen37plus + --step_budget_awareness).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_single_qwen37plus_sbp
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=qwen
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=1
export EXTRA_ARGS="--no-manager"
export CUA_EXTRA_ARGS="--step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
