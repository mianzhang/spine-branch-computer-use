#!/usr/bin/env bash
# Original MACU (decompose + replan5) on odysseys45.
#   manager : claude-opus-4-8
#   CUA     : fireworks_ai/qwen3p7-plus  (--cua-provider qwen, native tools)
#   replans : 5
# Re-run of the qwen3.7-plus MACU-replan5 comparison point WITH full CUA token
# recording (the prior run predated token capture). MACU comparison for the
# spine-branch qwen3.7-plus run. Uses run_macu.py.
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_macu_qwen37plus_replan5
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=5
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
