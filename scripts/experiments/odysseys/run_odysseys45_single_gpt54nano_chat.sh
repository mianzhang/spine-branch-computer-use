#!/usr/bin/env bash
# Single-agent (nomanager) gpt-5.4-nano via the general chat-mode harness (--cua-provider chat):
# tools in system prompt, NO native computer-use tool, model-agnostic XML parser.
# Part of the fair all-chat-mode capability ladder. max_steps 100 (single-agent).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_single_gpt54nano_chat
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-nano
export CUA_PROVIDER=chat
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=1
export EXTRA_ARGS="--no-manager"
exec bash scripts/lib/run_odysseys.sh
