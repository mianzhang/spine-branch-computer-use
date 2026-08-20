#!/usr/bin/env bash
# MACU (decompose+replan5), opus48 mgr + qwen3.6-27B CUA, on WebTailBench test_v2 (55-subset).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/webtailbench/webtailbench_test_v2_sub55.json
export RESULT_DIR=runs/webtailbench_v2_sub55_macu_qwen36_replan5
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=5
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
