#!/usr/bin/env bash
# Single-agent (nomanager) gpt-5.4-mini with reasoning_effort=medium, max_steps 100.
# Middle point of the reasoning_effort ablation (low / medium / xhigh), matched
# step budget so only reasoning_effort differs.
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_single_gpt54mini_medium
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=1
export EXTRA_ARGS="--no-manager"
export CUA_EXTRA_ARGS="--reasoning_effort medium"
exec bash scripts/lib/run_odysseys.sh
