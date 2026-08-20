#!/usr/bin/env bash
# FAIR structural control: MACU with replan=0 (one-shot decomposition, no retry/restructure),
# opus48 mgr + qwen3.6 CUA, WebTailBench-55, max_steps=100. NO step-budget-awareness
# (SBA is a spine-branch component; MACU baselines run as-is). Isolates coordination
# structure (free DAG vs spine-branch), both one-shot, both cap 100.
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/webtailbench/webtailbench_test_v2_sub55.json
export RESULT_DIR=runs/webtailbench_v2_sub55_macu_qwen36_replan0
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
