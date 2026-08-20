#!/usr/bin/env bash
# ABLATION 2 (remove the branches): Spine-only (serial chain) on odysseys45, qwen3.7-Plus.
# Identical to run_odysseys45_spinebranch_opus48_qwen37plus_sba.sh EXCEPT --serial-spine:
# plans with spine_only_decompose.yaml (one linear init_from chain, one VM, no parallel
# branches). SBA kept ON so the ONLY change vs full spine-branch+SBA is removing branches.
cd "$(dirname "$0")/../../.."
export RUNNER=run_spine_branch.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_spineonly_qwen37plus_sba
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export EXTRA_ARGS="--serial-spine"
export CUA_EXTRA_ARGS="--step_budget_awareness"
exec bash scripts/lib/run_odysseys.sh
