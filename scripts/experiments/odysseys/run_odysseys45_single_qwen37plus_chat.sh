#!/usr/bin/env bash
# Single-agent (nomanager) fireworks_ai/qwen3p7-plus via the general chat-mode harness (--cua-provider chat):
# native tools OFF, tool in system prompt, model-agnostic XML parser. Strict
# all-chat-mode ladder point. max_steps 100 (single-agent).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_single_qwen37plus_chat
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=fireworks_ai/qwen3p7-plus
export CUA_PROVIDER=chat
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=1
export EXTRA_ARGS="--no-manager"
exec bash scripts/lib/run_odysseys.sh
