#!/usr/bin/env bash
# Single-agent (--no-manager) run over a seeded-random 30-task sample of the 128
# decomposable WebTailBench test_v2 tasks. CUA = qwen3.6-27B (t5cvm6h4).
# Matches the config of runs/webtailbench_v2_sub55_single_qwen36 (single-agent
# max_steps=100) so results are comparable to the other webtailbench qwen36 runs.
set -uo pipefail
cd "$(dirname "$0")/../../.."

export TASKS_FILE="data/webtailbench/webtailbench_test_v2_decomposable_sub30.json"
export RESULT_DIR="runs/webtailbench_v2_dec_sub30_single_qwen36"
export CUA_MODEL="fireworks_ai/deployed/t5cvm6h4"   # qwen3.6-27B
export CUA_PROVIDER="qwen"
export MAX_STEPS="100"                                # single-agent convention
export MAX_REPLANS="0"                                # ignored under --no-manager
export EXTRA_ARGS="--no-manager"
export NUM_WORKERS="6"
export MAX_PARALLELISM="1"                            # one VM per task (single agent)

exec bash scripts/lib/run_odysseys.sh
