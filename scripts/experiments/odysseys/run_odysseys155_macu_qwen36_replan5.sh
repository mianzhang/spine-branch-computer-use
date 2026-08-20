#!/usr/bin/env bash
# MACU (decompose + replan5) on the odysseys 155-task complement, qwen3.6-27B CUA.
# Matches run_odysseys45_macu_opus48_qwen36_replan5.sh (only TASKS_FILE/RESULT_DIR differ).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys155.json
export RESULT_DIR=runs/odysseys155_macu_qwen36_replan5
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=5
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
