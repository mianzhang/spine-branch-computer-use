#!/usr/bin/env python3
"""Executor for spine-and-branch plans — additive; subclasses MACU's runner.

Reuses ALL of MACU's machinery (arg parsing, worker loop, VM/init_from, CUA
subprocess, result capture) and only overrides the coordination seams so the run
obeys spine-and-branch semantics:

  1. Graph            — produced by the spine-branch planner
                        (prompts/spine_branch_decompose.yaml), not manager_cua_v2.
  2. Operational state — flows ONLY along the spine's `init_from` edges. MACU's
                         ad-hoc "walk the parents and reuse some VM" is disabled,
                         so a node's VM comes from its explicit init_from or is
                         fresh. (This is the whole point of spines.)
  3. Plan revision     — static by default. With --verify-continue, each finished
                         subtask is checked against its declared goal (branch:
                         artifact file contents; spine: last-K screenshots) and, if
                         it fell short, an init_from continuation is spawned from
                         its checkpoint to finish the delta (bounded, progress-gated).
  4. Input delivery    — a consumer's `{{INPUT_CONTENT}}` placeholder is filled at
                         launch with the CONTENT of its input_files (each
                         producer's captured result), injected as text. Files are
                         NOT staged into the VM — the agent reads the info inline.

Nothing in existing MACU is modified. Run it like run_macu.py:
    python run_spine_branch.py data/odysseys/odysseys45.json \
        --result-dir runs/sb_qwen37plus --osworld-root "$OSWORLD_ROOT" \
        --manager-provider openai --manager-model fireworks_ai/qwen3p7-plus \
        --cua-provider qwen -- --headless --provider_name apptainer ...
(`--manager-model` is the PLANNER model; `--max-replans` is ignored.)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import run_macu
from utils import macu_runtime as _runtime
from utils.file_management_utils import read_filemgmt_downloads
from utils.graph_utils import apply_replan_decision, get_all_subtasks, validate_subtask_ids
from utils.spine_branch.checker import check_node
from utils.spine_branch.legalize import INPUT_PLACEHOLDER
from utils.spine_branch.plan import generate_spine_branch_plan
from utils.utils import extract_last_k_screenshots_from_dir

logger = logging.getLogger("macu.spine_branch")


class SpineBranchRunner(run_macu._RunSingleGraphRunner):
    """MACU runner with spine-and-branch coordination."""

    # --- 1. graph from the spine-branch planner ---------------------------
    def _prepare_graph(self) -> None:
        extra_fields: dict[str, object] = {}
        if self.is_osworld:
            extra_fields.update({"domain": self.osworld_domain, "instruction": self.original_task_text})
        else:
            extra_fields["task_text"] = self.original_task_text
            if self.no_initial_setup:
                extra_fields["no_initial_setup"] = True
            if self.task_website:
                extra_fields["website"] = self.task_website

        no_inherit = getattr(self.args, "no_spine_inherit", False)
        serial_spine = getattr(self.args, "serial_spine", False)
        osworld_decompose = getattr(self.args, "osworld_decompose", False)
        prompt_dir = Path(__file__).resolve().parent / "prompts"
        prompt_path = None
        if no_inherit:
            prompt_path = str(prompt_dir / "branch_only_decompose.yaml")
        elif serial_spine:
            prompt_path = str(prompt_dir / "spine_only_decompose.yaml")
        elif osworld_decompose:
            prompt_path = str(prompt_dir / "spine_branch_decompose_osworld_v2.yaml")
        _mode = "branch-only (no-spine-inherit)" if no_inherit else \
                "spine-only (serial chain)" if serial_spine else \
                "spine-branch (osworld-v2 prompt)" if osworld_decompose else "spine-branch"
        logger.info("Planning %s graph for %s ...", _mode, self.task_id)
        legal_graph, report, usage, gen_errors = generate_spine_branch_plan(
            task_text=self.original_task_text,
            provider=self.args.manager_provider,
            model=self.args.manager_model,
            max_tokens=getattr(self.args, "graph_gen_max_tokens", 16384),
            prompt_path=prompt_path,
        )
        if no_inherit:
            # belt-and-suspenders: guarantee NO VM inheritance regardless of what the
            # planner emitted -> every node runs in a fresh VM (branch-only ablation).
            for st in legal_graph.get("subtasks", []):
                st.pop("init_from", None)
                st["role"] = "branch"
            legal_graph["spines"] = {}
            report["ablation"] = "no_spine_inherit"
        elif serial_spine:
            # belt-and-suspenders: force ONE linear init_from chain in the planner's
            # emitted order -> every node inherits the previous, fully serial, no
            # parallel branches (spine-only ablation).
            subs = legal_graph.get("subtasks", [])
            prev = None
            for st in subs:
                st["role"] = "spine"
                if prev is None:
                    st.pop("init_from", None)
                else:
                    st["init_from"] = prev
                    deps = list(st.get("dependencies") or [])
                    if prev not in deps:
                        deps.append(prev)
                    st["dependencies"] = deps
                prev = st["id"]
            legal_graph["spines"] = {"spine_0": [s["id"] for s in subs]}
            report["ablation"] = "serial_spine"
        if not legal_graph.get("subtasks"):
            raise RuntimeError(
                f"spine-branch planning produced no valid subtasks for {self.task_id}: "
                f"{report.get('errors') or gen_errors}"
            )
        if report.get("errors"):
            logger.warning("[%s] spine-branch legalization errors: %s", self.task_id, report["errors"])
        logger.info(
            "[%s] spine-branch plan: %d subtasks, %d spine / %d branch, cost $%.4f",
            self.task_id, report.get("n_subtasks", 0), report.get("n_spine", 0),
            report.get("n_branch", 0), usage.cost_usd,
        )

        self.graph = {"task_id": self.task_id, **extra_fields,
                      "dependency_graph": legal_graph, "spine_branch_report": report}
        validate_subtask_ids(self.graph)
        self.all_subtasks = get_all_subtasks(self.graph, no_manager=self.no_manager)

        # artifact name -> producer subtask id, for {{INPUT_CONTENT}} injection.
        self._output_owner: dict[str, str] = {}
        self._role_by_sid: dict[str, str] = {}
        for st in legal_graph.get("subtasks", []):
            self._role_by_sid[st["id"]] = st.get("role", "branch")
            for o in st.get("outputs") or []:
                name = o.get("name") if isinstance(o, dict) else o
                if name:
                    self._output_owner[name] = st["id"]
        # verify-and-continue bookkeeping (only used when --verify-continue).
        self._continuations: dict[str, int] = {}   # base sid -> rounds spawned
        self._last_have: dict[str, str] = {}        # base sid -> last checker 'have' (progress gate)
        self._cont_of: dict[str, str] = {}          # continuation sid -> base sid

    # --- 2. operational state ONLY via the spine's init_from --------------
    def _maybe_reuse_dependency_vm(self, launch) -> None:
        # Disabled: no ad-hoc parent-VM reuse. A node inherits a VM only via its
        # explicit init_from (handled by _maybe_clone_from_init_from); otherwise
        # it starts fresh. This confines operational state to the spine.
        return

    # --- 3. verify-and-continue (opt-in) — else static, no global replanning
    def _maybe_replan_after_completion(self, sid: str) -> bool:
        if not getattr(self.args, "verify_continue", False):
            return False  # default: static plan, no dynamic edits
        try:
            return self._verify_and_continue(sid)
        except Exception as exc:  # noqa: BLE001 — verification must never break a run
            logger.warning("[%s] verify-continue raised: %s", sid, exc)
            return False

    def _checker_model(self) -> str:
        return getattr(self.args, "checker_model", None) or self.args.manager_model

    def _record_checker_usage(self, sid: str, usage) -> None:
        try:
            self.manager_usages.append(usage)
            self.cost_tracker[f"__checker_{sid}"] = {
                "agent_type": "manager", "model": usage.model,
                "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                "cost_usd": usage.cost_usd,
                "inference_seconds": round(_runtime._usage_inference_seconds(usage), 3),
            }
        except Exception:  # noqa: BLE001
            pass

    def _verify_and_continue(self, sid: str) -> bool:
        """Check whether a completed subtask met its declared goal; if not (and it
        is not blocked / not out of rounds), spawn an init_from continuation that
        resumes from its checkpoint to finish the missing delta."""
        if sid == "final_aggregation" or sid not in self.completed:
            return False
        st = self.st_by_id.get(sid) or {}
        if st.get("agent_type", "cua") != "cua":
            return False
        base = self._cont_of.get(sid, sid)
        rounds = self._continuations.get(base, 0)
        if rounds >= int(getattr(self.args, "max_continuations", 2) or 0):
            return False
        role = self._role_by_sid.get(base, "branch")
        provider = self.args.manager_provider
        model = self._checker_model()

        # Role-agnostic verification: gather BOTH evidence sources for every node
        # (last-N screenshots of the VM end-state AND any produced artifact text)
        # and judge on whichever exists.
        subdir = self._producer_subtask_dir(sid)
        k = int(getattr(self.args, "checker_screenshots", 3) or 3)
        shots = extract_last_k_screenshots_from_dir(subdir, k) if subdir else []
        arts: list[tuple[str, str]] = []
        for o in st.get("outputs") or []:
            name = o.get("name") if isinstance(o, dict) else o
            if not name:
                continue
            content, _src = self._resolve_artifact_content(name, sid)
            arts.append((name, content))
        verdict = check_node(st, shots, arts, provider, model)
        ev_desc = f"{len(shots)} screenshot(s) + {len(arts)} artifact(s)"

        self._record_checker_usage(sid, verdict.usage)
        logger.info("[%s] checker (role=%s, %s): complete=%s no_progress=%s | missing=%s",
                    sid, role, ev_desc, verdict.complete, verdict.no_progress_possible,
                    (verdict.missing or "").strip()[:120])

        if verdict.complete or verdict.no_progress_possible or not verdict.missing.strip():
            return False
        if verdict.have.strip() and verdict.have.strip() == self._last_have.get(base, ""):
            logger.info("[%s] verify-continue: no new progress vs last round; stopping", sid)
            return False
        return self._spawn_continuation(sid, base, rounds, verdict)

    def _spawn_continuation(self, sid: str, base: str, rounds: int, verdict) -> bool:
        cont_sid = f"{base}_cont{rounds + 1}"
        parent = self.st_by_id[sid]
        delta = (
            "\n\n## Continue from your previous attempt (the VM is exactly where you left off):\n"
            f"Already done: {verdict.have.strip() or '(little or nothing)'}\n"
            f"STILL MISSING — do this now: {verdict.missing.strip()}\n"
            "Resume from the current VM state; do NOT redo work that is already complete."
        )
        cont_node = {
            "id": cont_sid, "agent_type": "cua",
            "description": f"continuation of {sid}",
            "dependencies": [sid], "init_from": sid,
            "instruction": (parent.get("instruction") or "") + delta,
            "outputs": [dict(o) if isinstance(o, dict) else {"name": o, "description": ""}
                        for o in (parent.get("outputs") or [])],
            "input_files": list(parent.get("input_files") or []),
        }
        # Rewire: pending nodes that depend on `sid` must now wait for the
        # continuation (so they read the completed artifact/state, not the partial).
        running = self._running_logical_sids()
        modify: dict[str, dict] = {}
        for node in self.all_subtasks:
            nid = node.get("id")
            if nid in (sid, cont_sid) or nid in self.completed or nid in running:
                continue
            deps = node.get("dependencies") or []
            if sid in deps and cont_sid not in deps:
                modify[nid] = {"dependencies": list(deps) + [cont_sid]}
        decision = {"add": [cont_node]}
        if modify:
            decision["modify"] = modify
        applied, errors, _cancelled = apply_replan_decision(
            decision, self.all_subtasks, self.st_by_id, self.all_subtask_ids,
            self.downstream_counts, self.completed, running, self.task_id,
        )
        if not applied:
            logger.warning("[%s] continuation rejected by validator: %s", sid, errors)
            return False
        # continuation re-owns the parent's outputs; record role / round / progress.
        for o in (parent.get("outputs") or []):
            name = o.get("name") if isinstance(o, dict) else o
            if name:
                self._output_owner[name] = cont_sid
        self._cont_of[cont_sid] = base
        self._role_by_sid[cont_sid] = self._role_by_sid.get(base, "branch")
        self._continuations[base] = rounds + 1
        self._last_have[base] = verdict.have.strip()
        logger.info("[%s] spawned continuation [%s] (round %d/%s, init_from=%s, rewired %d consumer(s))",
                    sid, cont_sid, rounds + 1, getattr(self.args, "max_continuations", 2),
                    sid, len(modify))
        return True

    # --- 4. deliver input artifacts as injected text ----------------------
    def _prepare_launch(self, st: dict):
        launch = super()._prepare_launch(st)
        launch.staged_files = None  # spine-branch injects content as text, not files
        launch.instruction = self._inject_input_content(st, launch.instruction)
        return launch

    def _inject_input_content(self, st: dict, instruction: str) -> str:
        instruction = instruction or ""
        if INPUT_PLACEHOLDER not in instruction:
            return instruction
        owner = getattr(self, "_output_owner", {})
        parts: list[str] = []
        for name in st.get("input_files") or []:
            producer = owner.get(name)
            content, source = self._resolve_artifact_content(name, producer)
            logger.info("[%s] input '%s' <- %s (%s, %d chars)",
                        st.get("id"), name, producer or "?", source, len(content))
            parts.append(f"### {name}\n{content if content else '(no content was produced)'}")
        body = "\n\n".join(parts) if parts else "(no inputs)"
        return instruction.replace(INPUT_PLACEHOLDER, body)

    def _producer_subtask_dir(self, sid: str):
        """Best-effort host dir for a completed producer subtask."""
        if not sid:
            return None
        meta = getattr(self, "meta_by_sid", {}).get(sid) or {}
        proc = meta.get("proc")
        if proc is not None and getattr(proc, "subtask_dir", None):
            return Path(proc.subtask_dir)
        for c_sid, _ts, subdir in getattr(self, "completion_order", []):
            if c_sid == sid:
                return Path(subdir)
        return None

    def _resolve_artifact_content(self, name: str, producer: str) -> tuple[str, str]:
        """Resolve an input artifact's TEXT, preferring the real file the producer
        saved to ``~/Desktop/<name>`` over its free-text response.

        Order: (1) the producer's dumped Desktop file whose basename == name
        (deterministic, from filemgmt_downloads.json); (2) a manager-archived copy
        in archive_pool[name]; (3) the producer's response text (fallback)."""
        # (1) deterministic guest->host dump of the producer's Desktop file
        subdir = self._producer_subtask_dir(producer)
        if subdir is not None:
            try:
                downloads = read_filemgmt_downloads(subdir)
            except Exception:  # noqa: BLE001
                downloads = {}
            for guest_path, host_path in downloads.items():
                if os.path.basename(guest_path) == name:
                    txt = self._read_text_file(host_path)
                    if txt:
                        return txt, "file"
        # (2) manager-archived copy
        entry = getattr(self, "archive_pool", {}).get(name) or {}
        if entry.get("host_path"):
            txt = self._read_text_file(entry["host_path"])
            if txt:
                return txt, "archive"
        # (3) fall back to the producer's response text
        return (self.results.get(producer, "") or "").strip(), "response"

    @staticmethod
    def _read_text_file(path: str) -> str:
        try:
            return Path(path).read_text(errors="replace").strip()
        except OSError:
            return ""


# Swap so run_macu.main()'s own runner-swap picks up ours (see run_macu.py:818).
run_macu._RunSingleGraphRunner = SpineBranchRunner


if __name__ == "__main__":
    run_macu.main()
