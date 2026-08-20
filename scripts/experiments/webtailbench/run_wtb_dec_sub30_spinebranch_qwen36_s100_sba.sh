#!/usr/bin/env bash
# Spine-branch on the same seeded-random 30-task decomposable WebTailBench sample
# as runs/webtailbench_v2_dec_sub30_single_qwen36 (single-agent baseline).
#   planner/manager : claude-opus-4-8   (--manager-provider openai)
#   CUA             : qwen3.6-27B (t5cvm6h4, --cua-provider qwen)
#   coordination    : spine-branch (run_spine_branch.py; --max-replans ignored)
#   max_steps=100 + step-budget-awareness (matches webtailbench_v2_sub55_spinebranch_qwen36_s100_sba)
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/webtailbench/webtailbench_test_v2_decomposable_sub30.json
export RESULT_DIR=runs/webtailbench_v2_dec_sub30_spinebranch_qwen36_s100_sba
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export CUA_EXTRA_ARGS="--step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
