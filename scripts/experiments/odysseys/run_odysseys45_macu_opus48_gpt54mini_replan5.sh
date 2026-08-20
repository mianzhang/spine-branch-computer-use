#!/usr/bin/env bash
# Original MACU (decompose + replan) on odysseys45.
#   manager : claude-opus-4-8
#   CUA     : gpt-5.4-mini  (--cua-provider openai, native computer-use)
#   replans : 5
# The MACU-replan5 comparison point for the spine-branch gpt-5.4-mini run
# (runs/odysseys45_spinebranch_opus48mgr_gpt54mini). Same models/knobs, MACU
# coordination instead of spine-branch. Uses run_macu.py (RUNNER default).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_macu_opus48mgr_gpt54mini_replan5
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=openai
export MAX_STEPS=60
export MAX_REPLANS=5
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
