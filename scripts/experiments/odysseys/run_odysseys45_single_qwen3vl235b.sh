#!/usr/bin/env bash
# Single-agent (nomanager) baseline with bedrock Qwen3-VL-235B-A22B as the CUA.
#   CUA : bedrock/qwen.qwen3-vl-235b-a22b via the Qwen vision->pyautogui agent
#   mode: --no-manager (one CUA subtask per task), max_steps 100 (single-agent)
# High-end capability point for the CUA gradient (235B VL MoE).
cd "$(dirname "$0")/../../.."
export RUNNER=run_macu.py
export TASKS_FILE=data/odysseys/odysseys45.json
export RESULT_DIR=runs/odysseys45_single_qwen3vl235b
export MANAGER_MODEL=claude-opus-4-8
export CUA_MODEL=bedrock/qwen.qwen3-vl-235b-a22b
export CUA_PROVIDER=qwen
export MAX_STEPS=100
export MAX_REPLANS=0
export NUM_WORKERS=6
export MAX_PARALLELISM=1
export EXTRA_ARGS="--no-manager"
# Bedrock + LiteLLM rejects requests whose history has tool-use blocks unless
# tools= is passed on every turn ("Bedrock doesn't support tool calling without
# tools="). Disabling native tool-calling removes tool-history entirely (actions
# are parsed from the model's XML text instead), sidestepping the error.
#   (2) Bedrock also caps request body size ("Failed to buffer the request body:
#       length limit exceeded") — the multi-screenshot history blows it after
#       ~6-8 steps. Cap image_max low so only the last few screenshots are sent
#       full-size (older folded to text), keeping the request under Bedrock's cap.
export CUA_EXTRA_ARGS="--disable_native_tool_calling --image_max 3 --fold_size 2"
exec bash scripts/lib/run_odysseys.sh
