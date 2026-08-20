#!/usr/bin/env bash
# MACU (decompose+replan5), opus48 mgr + qwen3.7-plus CUA, on BrowseComp (50-subset).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/browsecomp/browsecomp_test_sub50.json
export RESULT_DIR=runs/browsecomp_sub50_macu_qwen37plus_replan5
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=5
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
