#!/usr/bin/env bash
# Spine-and-branch on odysseys45 WITH verify-and-continue (the A/B arm).
#   planner/manager : claude-opus-4-8
#   CUA             : fireworks_ai/deployed/t5cvm6h4  (qwen3.6-27B)
#   verify-continue : ON  (checker=gemini-3.1-flash-lite, max 1 continuation/subtask)
# Identical to run_odysseys45_spinebranch_opus48_qwen36.sh except --verify-continue,
# so it A/Bs the checkpoint-resume mechanism against that run (SR 46.7% corrected).
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spinebranch_opus48mgr_qwen36_vc
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export EXTRA_ARGS="--verify-continue --max-continuations 1 --checker-model gemini-3.1-flash-lite --checker-screenshots 3"
exec bash scripts/lib/run_odysseys.sh
