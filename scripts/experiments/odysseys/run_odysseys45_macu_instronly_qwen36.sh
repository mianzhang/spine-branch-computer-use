#!/usr/bin/env bash
# Instruction-only MACU ablation on odysseys45 (manager may only rewrite pending
# instructions; no graph-structure edits). Same config as the MACU-R5 baseline
# (run_odysseys45_macu_opus48_qwen36_replan5.sh) + --replan-instruction-only.
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_macu_instronly_qwen36_replan5
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/deployed/t5cvm6h4
export CUA_PROVIDER=qwen
export MAX_STEPS=60
export MAX_REPLANS=5
export NUM_WORKERS=6
export MAX_PARALLELISM=4
export EXTRA_ARGS="--replan-instruction-only"
exec bash scripts/lib/run_odysseys.sh
