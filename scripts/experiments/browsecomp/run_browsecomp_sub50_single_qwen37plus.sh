#!/usr/bin/env bash
# Single-agent (no-manager) qwen3.7-plus on BrowseComp (seeded-random 50-subset).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/browsecomp/browsecomp_test_sub50.json
export RESULT_DIR=runs/browsecomp_sub50_single_qwen37plus
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=qwen
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=1
export EXTRA_ARGS="--no-manager"
exec bash scripts/lib/run_odysseys.sh
