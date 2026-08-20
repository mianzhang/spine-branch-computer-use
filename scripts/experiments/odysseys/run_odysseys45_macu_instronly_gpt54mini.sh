#!/usr/bin/env bash
# Instruction-only MACU ablation on odysseys45 (gpt-5.4-mini, native computer-use).
# Same config as run_odysseys45_macu_opus48_gpt54mini_replan5.sh + --replan-instruction-only.
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_macu_instronly_gpt54mini_replan5
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=60
export MAX_REPLANS=5
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export EXTRA_ARGS="--replan-instruction-only"
exec bash scripts/lib/run_odysseys.sh
