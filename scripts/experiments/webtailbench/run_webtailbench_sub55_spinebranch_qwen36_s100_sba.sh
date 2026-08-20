#!/usr/bin/env bash
# Spine-branch, opus48 mgr + qwen3.6-27B CUA, WebTailBench-55, max_steps=100 + step-budget-awareness.
# De-starves single-flow spine nodes (analysis: 27% of successes need >60 steps) and adds the SBA nudge.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/webtailbench/webtailbench_test_v2_sub55.json
export RESULT_DIR=runs/webtailbench_v2_sub55_spinebranch_qwen36_s100_sba
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
