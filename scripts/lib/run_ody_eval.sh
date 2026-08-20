#!/usr/bin/env bash
# Score an odysseys run dir with the standard judge (gemini-3.1-flash-lite via proxy).
# Usage: run_ody_eval.sh <run-dir> [extra args...]
#
# Defaults reflect the 2026-06-22 evaluation fixes (see memory
# odysseys-eval-maxsteps-bias): --max-steps 0 keeps the FULL merged trajectory
# (the old default 100 truncated multi-agent finalize steps and deflated MACU),
# and --oneshot judges all rubrics for a task in ONE prompt (more consistent
# than per-rubric, which scored blocked-site rubrics inconsistently).
set -uo pipefail
cd "$(dirname "$0")/../.."
set -a; source .env; set +a
RD="${1:?usage: run_ody_eval.sh <run-dir> [extra args...]}"; shift || true
# TASK_SOURCE selects the rubric source; default odysseys, override for other
# benchmarks, e.g. TASK_SOURCE=data/webtailbench/webtailbench_test_v2.json
TASK_SOURCE="${TASK_SOURCE:-data/odysseys/odysseys.json}"
.venv/bin/python evals/odysseys_eval.py \
  --runs-dir "$RD" \
  --task-source-json "$TASK_SOURCE" \
  --output "$RD/odysseys_eval.json" \
  --oneshot --max-steps 0 --max-images 200 \
  --num-workers 6 --max-concurrent-rubrics 2 "$@"
