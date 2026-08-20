#!/usr/bin/env bash
# Single-agent (no-manager) gpt-5.4-mini over the 155-task odysseys complement.
# Matches the odysseys45 single-agent gpt-5.4-mini config: native computer-use
# (openai provider), reasoning_effort=medium, max_steps=100, replan=0.
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys155.json
export RESULT_DIR=runs/odysseys155_single_gpt54mini
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
