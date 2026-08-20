"""Completion checker for spine-branch subtasks + continuation seeding.

A subtask's declared goal is its ``instruction`` plus its ``outputs[].description``.
The checker asks a small LLM whether the EVIDENCE the subtask produced actually
meets that goal. Verification is ROLE-AGNOSTIC: for any node (spine or branch) we
use BOTH evidence sources it has —

  - the last K screenshots of the VM end-state, and
  - the text contents of any artifact file(s) the subtask produced,

— because either source can expose a shortfall the other hides (a screenshot
catches a block/wrong-state page; an artifact's text catches a partial/fabricated
deliverable). Whichever evidence exists is used; if neither exists the node is
accepted rather than stranded.

Returns a ``Verdict`` {complete, have, missing, no_progress_possible}. On an
incomplete verdict the executor spawns an ``init_from`` continuation seeded with
``have``/``missing`` so it resumes from the checkpoint instead of restarting.

Design principles: judge against the subtask's OWN declared goal (not the global
rubric); prefer the real artifact over self-report (guards fabrication); emit a
concrete delta; bias to "incomplete" when unsure (bounded by the caller's cap);
never crash the run (parse failures degrade to a safe verdict).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from utils.llm import UsageInfo, call_llm, parse_json_response

logger = logging.getLogger("macu.spine_branch")

CHECK_SYSTEM = (
    "You verify whether a computer-use subtask ACHIEVED its declared goal. You are "
    "given the goal and the EVIDENCE the subtask produced. The evidence may include "
    "the final screenshots of the VM and/or the text of artifact file(s) the subtask "
    "produced; use ALL evidence provided. Judge strictly:\n"
    "- complete: true ONLY if all required information/outcome is present and genuine. "
    "Placeholder values ('not shown', 'N/A', 'TODO'), fabricated/guessed data, or any "
    "missing required piece => false.\n"
    "- have: a concise summary of what IS present/done (this is fed to a continuation "
    "so it does not redo finished work — be specific: name the items/fields already obtained).\n"
    "- missing: a concise, SPECIFIC list of what is still needed (this drives the continuation).\n"
    "- no_progress_possible: true only if the evidence shows a HARD external block "
    "(site blocked, captcha/human-verification wall, login required, resource permanently "
    "unavailable) that simply continuing cannot overcome.\n"
    'Return ONLY a JSON object: {"complete": bool, "have": str, "missing": str, '
    '"no_progress_possible": bool}'
)


@dataclass
class Verdict:
    complete: bool
    have: str
    missing: str
    no_progress_possible: bool
    usage: UsageInfo


def _goal_text(subtask: dict) -> str:
    outs = subtask.get("outputs") or []
    req_lines = [
        f"- {o.get('name')}: {o.get('description', '')}"
        for o in outs
        if isinstance(o, dict) and o.get("name")
    ]
    req = "\n".join(req_lines) if req_lines else "(no explicit output files declared)"
    return (
        f"GOAL (subtask instruction):\n{str(subtask.get('instruction') or '').strip()}\n\n"
        f"REQUIRED OUTPUTS:\n{req}"
    )


def _parse(raw: str, usage: UsageInfo) -> Verdict:
    try:
        d = parse_json_response(raw)
    except Exception:  # noqa: BLE001 — unparseable => conservative incomplete, no false "done"
        logger.warning("checker: could not parse verdict JSON; treating as incomplete")
        return Verdict(False, "", "checker response was unparseable", False, usage)
    return Verdict(
        complete=bool(d.get("complete")),
        have=str(d.get("have") or ""),
        missing=str(d.get("missing") or ""),
        no_progress_possible=bool(d.get("no_progress_possible")),
        usage=usage,
    )


def check_node(
    subtask: dict,
    screenshot_paths: Sequence[Path],
    artifact_texts: Sequence[tuple[str, str]],
    provider: str,
    model: Optional[str],
    max_tokens: int = 1024,
) -> Verdict:
    """Verify ANY node (spine or branch) from BOTH evidence sources it has: the
    last-N screenshots of its VM end-state AND the text of any artifact file(s)
    it produced. Role-agnostic — whichever evidence exists is used; if neither
    exists the node is accepted rather than stranded."""
    paths = [Path(p) for p in (screenshot_paths or []) if Path(p).exists()]
    arts = [(n, t) for (n, t) in (artifact_texts or [])]

    if not paths and not arts:
        # No evidence at all to judge — accept rather than strand the deliverable
        # (a later verifier / the aggregation still sees it).
        return Verdict(True, "(no evidence available to verify)", "", False,
                       UsageInfo(model=model or ""))

    parts = [_goal_text(subtask), ""]
    if arts:
        ev = "\n\n".join(
            f"### {name}\n{(txt or '').strip() or '(file is empty)'}"
            for name, txt in arts
        )
        parts.append("EVIDENCE A -- contents of the produced artifact file(s):\n" + ev)
    if paths:
        parts.append(
            f"EVIDENCE B -- the final {len(paths)} screenshot(s) of the VM end-state "
            "are attached (oldest first)."
        )
    parts.append("Using ALL evidence above, judge whether the declared goal is met.")
    user = "\n\n".join(parts)

    raw, usage = call_llm(
        system_prompt=CHECK_SYSTEM, user_prompt=user, provider=provider,
        model=model, temperature=0.0, max_tokens=max_tokens,
        image_path=(paths if paths else None),
    )
    return _parse(raw, usage)
