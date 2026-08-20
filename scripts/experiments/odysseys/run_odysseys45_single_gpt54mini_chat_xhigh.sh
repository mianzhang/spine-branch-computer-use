#!/usr/bin/env bash
# Single-agent (nomanager) gpt-5.4-mini via the general chat-mode harness (--cua-provider chat)
# at reasoning_effort=xhigh: tools in system prompt, NO native computer-use tool,
# model-agnostic XML parser. Companion to run_odysseys45_single_gpt54mini_chat.sh
# (which uses the default medium effort). max_steps 100 (single-agent).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_single_gpt54mini_chat_xhigh
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=gpt-5.4-mini
export CUA_PROVIDER=chat
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=1
export EXTRA_ARGS="--no-manager"
export CUA_EXTRA_ARGS="--reasoning_effort xhigh"
exec bash scripts/lib/run_odysseys.sh
