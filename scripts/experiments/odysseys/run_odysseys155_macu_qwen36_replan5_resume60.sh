#!/usr/bin/env bash
# Resume the disk-full-crashed odysseys155 MACU replan5 qwen3.6-27B run.
# Same config as run_odysseys155_macu_qwen36_replan5.sh, but the tasks file lists
# ONLY the 60 unfinished tasks (7 partial dirs were deleted + 53 never started),
# and it reuses the SAME result dir so the 95 completed tasks are untouched.
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys155_macu_qwen36_replan5_resume60.json
export RESULT_DIR=runs/odysseys155_macu_qwen36_replan5
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=5
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
