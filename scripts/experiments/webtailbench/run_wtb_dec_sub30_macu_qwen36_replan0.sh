#!/usr/bin/env bash
# MACU replan=0 (one-shot decomposition, no retry/restructure) on the same seeded 30-task
# decomposable WebTailBench sample. opus48 mgr + qwen3.6-27B CUA, max_steps=100, NO SBA
# (SBA is a spine-branch component; MACU baselines run as-is). Fair structural control vs
# single-agent (runs/webtailbench_v2_dec_sub30_single_qwen36) and spine-branch
# (runs/webtailbench_v2_dec_sub30_spinebranch_qwen36_s100_sba): all one-shot, all cap 100.
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/webtailbench/webtailbench_test_v2_decomposable_sub30.json
export RESULT_DIR=runs/webtailbench_v2_dec_sub30_macu_qwen36_replan0
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
exec bash scripts/lib/run_odysseys.sh
