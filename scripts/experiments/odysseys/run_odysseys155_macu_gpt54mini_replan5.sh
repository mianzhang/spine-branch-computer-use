#!/usr/bin/env bash
# MACU (decompose + replan5) on the odysseys 155-task complement, gpt-5.4-mini
# native computer-use, xhigh reasoning (NO SBA — SBA is the spine-branch add-on).
# The MACU-replan5 comparison point for run_odysseys155_spinebranch_gpt54mini_sba
# (same manager/CUA/reasoning, MACU coordination instead of spine-branch).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys155.json
export RESULT_DIR=runs/odysseys155_macu_gpt54mini_replan5
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=60
export MAX_REPLANS=5
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--reasoning_effort xhigh"
exec bash scripts/lib/run_odysseys.sh
