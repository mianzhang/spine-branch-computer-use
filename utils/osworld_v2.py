"""OSWorld-V2 task loading helpers for MACU.

OSWorld-V2's official tasks are gated Python classes (``task_<id>.py`` subclassing
``desktop_env.task_base.BaseTask``) with imperative ``setup()`` / ``evaluate()`` —
unlike v1's declarative JSON ``config`` + ``evaluator``. This module bridges them:

* :func:`load_osworld_v2_tasks` / :func:`extract_v2_task_meta` read task metadata
  (id, snapshot, instruction, related_apps) by **AST-parsing** the task file, so the
  MACU manager process can enumerate tasks WITHOUT importing v2 ``desktop_env``
  (which is heavy and would collide with a v1 ``desktop_env`` in the same process).
* :func:`load_v2_task_object` actually imports and instantiates the task class —
  used only inside the evaluator subprocess (where v2 ``desktop_env`` is loaded
  anyway) to drive ``setup()`` / ``evaluate()``.

Env:
  OSWORLD_V2_ROOT  -> the OSWorld-V2 checkout (default /home/ec2-user/macu/OSWorld-V2)
"""
from __future__ import annotations

import ast
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("macu")

DEFAULT_OSWORLD_V2_ROOT = "/home/ec2-user/macu/OSWorld-V2"


def osworld_v2_root() -> Path:
    return Path(os.environ.get("OSWORLD_V2_ROOT", DEFAULT_OSWORLD_V2_ROOT))


def task_class_dir() -> Path:
    return osworld_v2_root() / "evaluation_examples" / "task_class"


def resolve_v2_task_class_path(task_id: str) -> Path:
    """Return the path to ``task_<id>.py`` for a v2 task id (e.g. ``"003"``)."""
    p = task_class_dir() / f"task_{task_id}.py"
    if not p.exists():
        raise FileNotFoundError(
            f"OSWorld-V2 task class not found: {p}. Set OSWORLD_V2_ROOT and ensure the "
            f"gated task classes are downloaded (xlangai/osworld_v2_tasks)."
        )
    return p


# --- metadata extraction (AST, no desktop_env import) -----------------------

_META_FIELDS = ("id", "snapshot", "instruction", "related_apps", "proxy")


def _literal(node: ast.AST) -> Any:
    """Best-effort constant eval of a class-attribute value node."""
    try:
        return ast.literal_eval(node)
    except Exception:
        # implicit/explicit string concatenation ("a" "b" or "a" + "b")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = _literal(node.left), _literal(node.right)
            if isinstance(left, str) and isinstance(right, str):
                return left + right
        return None


def extract_v2_task_meta(task_id: str) -> dict:
    """AST-parse ``task_<id>.py`` and return its class-level metadata.

    Returns ``{id, snapshot, instruction, related_apps, proxy}``. Does not import
    the module (so no ``desktop_env`` dependency). Raises if the file/instruction
    can't be resolved statically (caller may fall back to :func:`load_v2_task_object`).
    """
    path = resolve_v2_task_class_path(task_id)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    # pick the BaseTask subclass (prefer one named Task<id> / referenced by TASK_CLASS)
    class_defs = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    if not class_defs:
        raise ValueError(f"No class definition in {path}")
    target = class_defs[0]
    for cd in class_defs:
        if any(getattr(b, "id", "") == "BaseTask" or getattr(b, "attr", "") == "BaseTask"
               for b in cd.bases):
            target = cd
            break

    meta: dict[str, Any] = {"id": task_id}
    # Only override a field when the value resolves to a literal; a non-literal
    # (e.g. ``id = TASK_ID``, ``instruction = INSTRUCTION``) must NOT clobber the
    # default with None (that's what the import fallback is for).
    for stmt in target.body:
        if isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                if isinstance(tgt, ast.Name) and tgt.id in _META_FIELDS:
                    val = _literal(stmt.value)
                    if val is not None:
                        meta[tgt.id] = val
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            if stmt.target.id in _META_FIELDS and stmt.value is not None:
                val = _literal(stmt.value)
                if val is not None:
                    meta[stmt.target.id] = val

    if not meta.get("instruction"):
        raise ValueError(
            f"Could not statically extract 'instruction' from {path}; "
            f"the task may build it dynamically. Fall back to load_v2_task_object()."
        )
    meta.setdefault("id", task_id)
    meta.setdefault("snapshot", "osworld_v2")
    meta.setdefault("related_apps", [])
    meta.setdefault("proxy", False)
    return meta


# --- split file reading -----------------------------------------------------

def _read_task_ids(split_path: str | Path) -> list[str]:
    """Accept several split shapes and return an ordered, de-duped id list.

    Supported: ``{"tasks": [...]}``, a flat ``[...]`` list, or a category map
    ``{"<category>": [...], ...}`` (ids merged across categories, order-stable).
    """
    with open(split_path) as f:
        data = json.load(f)
    ids: list[str] = []
    if isinstance(data, list):
        ids = [str(x) for x in data]
    elif isinstance(data, dict) and "tasks" in data and isinstance(data["tasks"], list):
        ids = [str(x) for x in data["tasks"]]
    elif isinstance(data, dict):
        for _cat, vals in data.items():
            if isinstance(vals, list):
                ids.extend(str(x) for x in vals)
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def load_osworld_v2_tasks(split_path: str | Path) -> list[dict]:
    """Load OSWorld-V2 tasks from a split file into MACU's task-record shape.

    Each record: ``{task_id, domain, instruction, related_apps, osworld_version,
    raw}``. ``domain`` is the task's ``snapshot`` label (kept for parity with the
    v1 ``osworld_domain`` gate; under the single v2 image it's informational).
    """
    tasks: list[dict] = []
    for tid in _read_task_ids(split_path):
        try:
            meta = extract_v2_task_meta(tid)          # fast path: AST, no imports
        except Exception as ast_exc:
            # dynamic instruction (f-string host, module-level INSTRUCTION,
            # base_instruction built at runtime) -> import + instantiate.
            try:
                obj = load_v2_task_object(tid)
                meta = {
                    "id": obj.get("id") or tid,
                    "snapshot": obj.get("snapshot") or "osworld_v2",
                    "instruction": obj.get("instruction") or getattr(obj, "instruction", None),
                    "related_apps": obj.get("related_apps", []) or [],
                    "proxy": obj.get("proxy", False),
                }
                if not meta["instruction"]:
                    raise ValueError("empty instruction after import")
            except Exception as imp_exc:
                logger.warning(
                    "Skipping OSWorld-V2 task %s: AST failed (%s) and import failed (%s). "
                    "GitLab-backed tasks (026, 041) need `pip install python-gitlab` + a "
                    "self-hosted GitLab; exclude them or install the dep.",
                    tid, ast_exc, imp_exc,
                )
                continue
        tasks.append(
            {
                "task_id": meta["id"],
                "domain": meta.get("snapshot") or "osworld_v2",
                "instruction": meta["instruction"],
                "related_apps": meta.get("related_apps", []),
                "osworld_version": "v2",
                "raw": {
                    "id": meta["id"],
                    "snapshot": meta.get("snapshot"),
                    "instruction": meta["instruction"],
                    "related_apps": meta.get("related_apps", []),
                    "proxy": meta.get("proxy", False),
                    "osworld_version": "v2",
                },
            }
        )
    return tasks


# --- object loading (evaluator subprocess only) -----------------------------

def _ensure_v2_importable() -> None:
    root = str(osworld_v2_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def load_v2_task_object(task_id: str) -> Any:
    """Import ``task_<id>.py`` and instantiate its task class (a ``BaseTask``).

    Requires v2 ``desktop_env`` importable (OSWORLD_V2_ROOT on sys.path). Use this
    only where v2 ``desktop_env`` is already loaded (the evaluator subprocess), NOT
    in the manager process — use :func:`extract_v2_task_meta` there instead.
    """
    resolve_v2_task_class_path(task_id)  # existence check
    _ensure_v2_importable()
    import importlib

    mod = importlib.import_module(f"evaluation_examples.task_class.task_{task_id}")
    cls = getattr(mod, "TASK_CLASS", None) or getattr(mod, "Task", None)
    if cls is None:
        # fall back: first BaseTask subclass defined in the module
        from desktop_env.task_base import BaseTask  # type: ignore
        for val in vars(mod).values():
            if isinstance(val, type) and issubclass(val, BaseTask) and val is not BaseTask:
                cls = val
                break
    if cls is None:
        raise ValueError(f"No task class (TASK_CLASS/Task/BaseTask subclass) in task_{task_id}.py")
    return cls()
