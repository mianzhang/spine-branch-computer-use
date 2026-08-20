#!/usr/bin/env bash
# Single-agent (no-manager) qwen3.6-27B on WebTailBench test_v2 (seeded-random 55-subset).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/webtailbench/webtailbench_test_v2_sub55.json
export RESULT_DIR=runs/webtailbench_v2_sub55_single_qwen36
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=1
export EXTRA_ARGS="--no-manager"
exec bash scripts/lib/run_odysseys.sh
