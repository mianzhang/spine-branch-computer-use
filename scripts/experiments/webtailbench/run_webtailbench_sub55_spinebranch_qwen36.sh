#!/usr/bin/env bash
# Spine-branch, opus48 mgr + qwen3.6-27B CUA, on WebTailBench test_v2 (55-subset).
# Plain (SBA off) to match the single-agent + MACU-replan5 WebTailBench runs.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/webtailbench/webtailbench_test_v2_sub55.json
export RESULT_DIR=runs/webtailbench_v2_sub55_spinebranch_qwen36
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
