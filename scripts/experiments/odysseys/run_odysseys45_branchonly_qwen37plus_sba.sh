#!/usr/bin/env bash
# ABLATION 1 (remove the spine): Branch-only on odysseys45, qwen3.7-Plus.
# Identical to run_odysseys45_spinebranch_opus48_qwen37plus_sba.sh EXCEPT
# --no-spine-inherit: plans with branch_only_decompose.yaml (no init_from; every
# node a fresh-VM branch; final live state reconstructed from URLs). SBA kept ON so
# the ONLY change vs the full spine-branch+SBA run is removal of the state channel.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_branchonly_qwen37plus_sba
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export EXTRA_ARGS="--no-spine-inherit"
export CUA_EXTRA_ARGS="--step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
