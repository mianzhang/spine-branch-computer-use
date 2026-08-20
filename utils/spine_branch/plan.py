"""Spine-and-branch planner (offline, additive).

One-pass pipeline:
  1. Decompose+wire — the spine_branch_decompose.yaml prompt emits a dependency
     graph already wired (outputs / input_files / init_from / role) inline.
     Generated with a spine-branch-aware validation/retry loop (NOT MACU's
     validate_dependency_graph, which rejects `init_from: null`).
  2. Legalize — deterministic validation + derivation (spines, init_from edges,
     artifact<->instruction consistency). See legalize.py.

Returns a legalized MACU-format graph (with spine/branch fields) + report + usage.
Touches no existing MACU code.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from utils.llm import UsageInfo, call_llm, load_prompt, parse_json_response, render_prompt
from utils.spine_branch.legalize import legalize_spine_branch, count_spines

logger = logging.getLogger("macu.spine_branch")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DECOMPOSE_PROMPT = PROJECT_ROOT / "prompts" / "spine_branch_decompose.yaml"


def validate_sb_graph(graph: dict) -> list[str]:
    """Lenient, spine-branch-aware validation used during generation retries.

    Unlike MACU's validate_dependency_graph, an ABSENT or null `init_from` is
    fine (most nodes are branches). Only a present, non-null init_from must be a
    real CUA subtask listed in the node's dependencies.
    """
    errors: list[str] = []
    subs = graph.get("subtasks")
    if not isinstance(subs, list) or not subs:
        return ["graph must contain a non-empty 'subtasks' list"]
    ids: set[str] = set()
    for st in subs:
        if not isinstance(st, dict) or not st.get("id"):
            errors.append("a subtask is missing an 'id'")
            continue
        if st["id"] in ids:
            errors.append(f"duplicate subtask id '{st['id']}'")
        ids.add(st["id"])
    agg = graph.get("aggregation")
    if agg and agg.get("agent_type") != "manager":
        errors.append("aggregation must have agent_type 'manager'")
    all_ids = ids | ({agg["id"]} if agg and agg.get("id") else set())
    for st in subs + ([agg] if agg else []):
        if not isinstance(st, dict):
            continue
        for d in st.get("dependencies", []) or []:
            if d not in all_ids:
                errors.append(f"node '{st.get('id')}' depends on unknown id '{d}'")
        initf = st.get("init_from")
        if initf not in (None, "", "null"):  # absent/null is fine
            if not isinstance(initf, str) or initf not in ids:
                errors.append(f"node '{st.get('id')}' init_from '{initf}' is not an existing CUA subtask")
            elif initf not in (st.get("dependencies") or []):
                errors.append(f"node '{st.get('id')}' init_from '{initf}' must also be in its dependencies")
    if not any(isinstance(st, dict) and st.get("agent_type") == "cua" for st in subs):
        errors.append("graph must contain at least one CUA subtask")
    for st in subs:
        if isinstance(st, dict) and st.get("agent_type") == "manager":
            errors.append(f"subtask '{st.get('id')}' is agent_type 'manager'; ONLY the final_aggregation "
                          f"node may be manager. Every other node must be 'cua' — all tools are CUA and even "
                          f"creating a file happens in a VM, so make it a real CUA task.")
    n_spines = count_spines(graph)
    if n_spines > 1:
        errors.append(
            f"the plan has {n_spines} spines, but a task must have EXACTLY ONE spine — only one VM "
            f"can survive as the deliverable. Keep a single spine (one init_from chain of role=spine "
            f"nodes) and turn every other operational node into a branch that hands its URL/result to "
            f"the spine as an artifact (e.g. branches find the URLs; one spine node opens all the tabs)."
        )
    return errors


def _add_usage(a: UsageInfo, b: UsageInfo) -> UsageInfo:
    return UsageInfo(input_tokens=a.input_tokens + b.input_tokens,
                     output_tokens=a.output_tokens + b.output_tokens,
                     model=b.model or a.model, cost_usd=a.cost_usd + b.cost_usd)


def generate_spine_branch_plan(
    task_text: str,
    provider: str = "openai",
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 16384,
    max_attempts: int = 3,
    prompt_path: Optional[str] = None,
) -> tuple[dict, dict, UsageInfo, list[str]]:
    """Plan a task into a legalized spine-and-branch graph.

    ``prompt_path`` selects the decomposition prompt (default: the spine-branch
    prompt). Pass prompts/branch_only_decompose.yaml for the no-spine ablation.
    Returns (legal_graph, report, usage, gen_errors)."""
    cfg = load_prompt(str(prompt_path or DECOMPOSE_PROMPT))
    system_prompt, user_prompt = render_prompt(cfg, task=task_text)
    usage = UsageInfo(input_tokens=0, output_tokens=0, model=model or "", cost_usd=0.0)
    graph: dict = {}
    errors: list[str] = []

    for attempt in range(1, max_attempts + 1):
        up = user_prompt
        if attempt > 1 and errors:
            up += "\n\nYour previous graph had these problems:\n" + "".join(f"- {e}\n" for e in errors)
            up += "\nRegenerate the COMPLETE corrected JSON graph."
        raw, u = call_llm(system_prompt=system_prompt, user_prompt=up, provider=provider,
                          model=model, temperature=temperature, max_tokens=max_tokens)
        usage = _add_usage(usage, u)
        try:
            graph = parse_json_response(raw)
        except json.JSONDecodeError as exc:
            errors = [f"JSON parse error: {exc}"]
            continue
        errors = validate_sb_graph(graph)
        if not errors:
            break
        logger.warning("spine-branch gen attempt %d/%d errors: %s", attempt, max_attempts, errors)

    if "subtasks" not in graph:
        return (graph, {"coordination": "spine_branch", "errors": ["decomposition failed", *errors],
                        "out_of_scope": False}, usage, errors)

    legal_graph, report = legalize_spine_branch(graph)
    report["gen_errors"] = errors
    return legal_graph, report, usage, errors
