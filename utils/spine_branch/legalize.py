"""Deterministic validator/deriver for spine-and-branch graphs.

The decomposer emits, per node:
  - outputs:     globally-unique artifact names this node writes to the pool
  - input_files: upstream artifact names this node reads (the informational edges,
                 fixed at planning, read directly at runtime — no LLM)
  - init_from:   the single operational parent (the spine edge), or absent/null

The single-valued `init_from` makes the invariant structural — operational
fan-in is <= 1 by construction, so there is no downgrade/out-of-scope step. This
module just VALIDATES the wiring (globally-unique outputs; every input_file is
produced by some other node; init_from references a CUA dependency; no
operational cycle; aggregation reads-only) and DERIVES role + spine_id.

Pure Python, no LLM, no MACU-code edits. Output is a valid MACU graph plus the
additive derived fields `role`, `spine_id`, and a separate `report`.
"""
from __future__ import annotations

from typing import Any, Optional

# Default location where a producer saves its output file(s).
ARTIFACT_DIR = "~/Desktop"
# Placeholder appended to a CONSUMER node's instruction; the runtime replaces it
# with the actual content of the node's input artifacts (so the agent reads the
# info as text and never opens a file). Each subtask agent is independent and is
# told only what it must do, not the cross-subtask plumbing.
INPUT_PLACEHOLDER = "{{INPUT_CONTENT}}"


def _norm_outputs(raw: Any) -> list[dict]:
    """Normalize a node's `outputs` to a list of {name, description}.

    Accepts either ["name", ...] or [{"name","description"}, ...]."""
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for o in raw:
        if isinstance(o, str) and o.strip():
            out.append({"name": o.strip(), "description": ""})
        elif isinstance(o, dict) and isinstance(o.get("name"), str) and o["name"].strip():
            out.append({"name": o["name"].strip(),
                        "description": str(o.get("description") or "").strip()})
    return out


def count_spines(graph: dict) -> int:
    """Number of spines in a raw graph (role=spine nodes grouped by init_from
    components; a lone role=spine node = one single-node spine). Used to enforce
    'exactly one spine' during generation without mutating the graph."""
    subs = [st for st in (graph.get("subtasks") or []) if isinstance(st, dict) and st.get("id")]
    ids = {st["id"] for st in subs}
    initp: dict[str, str] = {}
    for st in subs:
        if st.get("agent_type") == "manager":
            continue
        f = st.get("init_from")
        if isinstance(f, str) and f in ids and f != st["id"]:
            initp[st["id"]] = f
    has_child = {i: False for i in ids}
    for _, p in initp.items():
        has_child[p] = True
    members = {st["id"] for st in subs
               if st.get("role") == "spine" or st["id"] in initp or has_child.get(st["id"])}
    uf = {i: i for i in ids}

    def find(x):
        while uf[x] != x:
            uf[x] = uf[uf[x]]
            x = uf[x]
        return x

    for c, p in initp.items():
        a, b = find(c), find(p)
        if a != b:
            uf[a] = b
    return len({find(m) for m in members})


def legalize_spine_branch(graph: dict) -> tuple[dict, dict]:
    """Validate + derive a spine-and-branch graph. Returns (legal_graph, report).

    graph: {"subtasks": [...], "aggregation": {...}} (MACU format) where nodes
    carry `outputs`, `input_files`, and optional `init_from`.
    """
    subtasks: list[dict] = [dict(st) for st in graph.get("subtasks", [])]
    agg_in = graph.get("aggregation")
    agg: Optional[dict] = dict(agg_in) if agg_in else None
    all_nodes = subtasks + ([agg] if agg else [])
    subtask_ids = {st["id"] for st in subtasks}

    report: dict[str, Any] = {
        "coordination": "spine_branch",
        "errors": [],
        "warnings": [],
    }

    # ---- 0. only the aggregation may be a manager node; all subtasks are CUA
    # (there are only CUA tools — even creating a file happens inside a VM).
    for st in subtasks:
        if st.get("agent_type") == "manager":
            report["warnings"].append(
                f"node '{st['id']}' had agent_type 'manager'; forcing 'cua' "
                f"(only final_aggregation may be a manager node)"
            )
            st["agent_type"] = "cua"

    # ---- 1. outputs: normalize to {name,description}; global-uniqueness ----
    output_owner: dict[str, str] = {}   # artifact name -> producer id
    output_desc: dict[str, str] = {}    # artifact name -> description
    for st in all_nodes:
        norm = _norm_outputs(st.get("outputs"))
        kept: list[dict] = []
        for o in norm:
            name = o["name"]
            if name in output_owner:
                report["errors"].append(
                    f"duplicate output name '{name}' (declared by '{output_owner[name]}' and '{st['id']}')"
                )
            else:
                output_owner[name] = st["id"]
                output_desc[name] = o["description"]
            kept.append(o)
        st["outputs"] = kept
    consumed: set[str] = set()

    # ---- 2. input_files: must reference some OTHER node's output ----------
    for st in all_nodes:
        ins = st.get("input_files") or []
        if not isinstance(ins, list):
            ins = []
        deps = list(st.get("dependencies") or [])
        clean_ins: list[str] = []
        for f in ins:
            if not isinstance(f, str) or not f.strip():
                continue
            f = f.strip()
            owner = output_owner.get(f)
            if owner is None:
                report["errors"].append(
                    f"node '{st['id']}' reads input_file '{f}' that no node produces"
                )
            elif owner == st["id"]:
                report["errors"].append(f"node '{st['id']}' reads its own output '{f}'")
            else:
                clean_ins.append(f)
                consumed.add(f)
                if owner not in deps:  # informational edge implies ordering
                    deps.append(owner)
                    report["warnings"].append(
                        f"added dependency '{owner}' to '{st['id']}' (it reads that node's artifact '{f}')"
                    )
        st["input_files"] = clean_ins
        st["dependencies"] = deps

    # ---- 3. init_from: single operational (spine) parent ------------------
    for st in all_nodes:
        is_manager = st.get("agent_type") == "manager"
        initf = None if is_manager else st.get("init_from")
        if is_manager and st.get("init_from"):
            report["warnings"].append(f"cleared init_from on manager node '{st['id']}' (managers read artifacts only)")
        if initf:
            if initf == st["id"]:
                report["errors"].append(f"node '{st['id']}' has init_from referencing itself; cleared")
                initf = None
            elif not isinstance(initf, str) or initf not in subtask_ids:
                report["errors"].append(
                    f"node '{st['id']}' init_from '{initf}' is not an existing CUA subtask"
                )
                initf = None
            else:
                if initf not in st["dependencies"]:
                    st["dependencies"].append(initf)
                    report["warnings"].append(
                        f"added dependency '{initf}' to '{st['id']}' (its operational/init_from parent)"
                    )
        if initf:
            st["init_from"] = initf
        else:
            st.pop("init_from", None)

    # ---- 4. role: trust the DECLARED label; only the structural rule is forced
    # role is semantic (verification medium / what the node is for) and is NOT
    # derivable from init_from — a branch may have an init_from, and a terminal
    # spine has no operational child. The ONE structural rule: if a node is some
    # other node's init_from, its operational state is used downstream, so it
    # MUST be a spine.
    init_parent = {st["id"]: st.get("init_from") for st in all_nodes}
    has_op_child = {sid: False for sid in subtask_ids}
    for child, par in init_parent.items():
        if par in has_op_child:
            has_op_child[par] = True

    for st in all_nodes:
        is_manager = st.get("agent_type") == "manager"
        declared = st.get("role")
        role = declared if declared in ("spine", "branch") else None
        if is_manager:
            if declared == "spine":
                report["warnings"].append(f"manager node '{st['id']}' declared spine; forcing branch (reads artifacts only)")
            role = "branch"
        elif has_op_child.get(st["id"], False):
            if role == "branch":
                report["warnings"].append(
                    f"node '{st['id']}' is another node's init_from but declared 'branch'; forcing 'spine' (its operational state is used downstream)"
                )
            role = "spine"
        elif role is None:
            report["warnings"].append(f"node '{st['id']}' missing role; defaulting to 'branch'")
            role = "branch"
        st["role"] = role

    # spine_id: operational-lineage component (any node touching an init_from edge)
    parent_uf = {sid: sid for sid in subtask_ids}

    def find(x):
        while parent_uf[x] != x:
            parent_uf[x] = parent_uf[parent_uf[x]]
            x = parent_uf[x]
        return x

    in_op_edge = {sid: has_op_child[sid] for sid in subtask_ids}
    for child, par in init_parent.items():
        if child in parent_uf and par in parent_uf:
            in_op_edge[child] = True
            ra, rb = find(child), find(par)
            if ra != rb:
                parent_uf[ra] = rb

    comp_label: dict[str, str] = {}
    spine_counter = 0

    def _spine_depth(sid: str) -> int:  # distance from the spine head (the node with no init_from)
        d, cur, guard = 0, sid, 0
        while init_parent.get(cur) and guard < len(subtask_ids) + 1:
            cur = init_parent[cur]
            d += 1
            guard += 1
        return d

    # A node belongs to a spine if it is role=spine (its deliverable is an
    # operational state — a single-node spine if it has no init_from chain) OR
    # it sits on an init_from VM-lineage (e.g. a branch tail of a spine).
    for st in subtasks:
        sid = st["id"]
        is_spine_member = (st.get("role") == "spine") or in_op_edge.get(sid, False)
        if not is_spine_member:
            st["spine_id"] = None
            continue
        root = find(sid)
        if root not in comp_label:
            comp_label[root] = f"spine_{spine_counter}"
            spine_counter += 1
        st["spine_id"] = comp_label[root]
        st["spine_pos"] = _spine_depth(sid)  # 0 = spine head (single-node spine => 0)

    # ordered spine chains (head -> tail); single-node spines are length-1 chains
    spines_ordered: dict[str, list[str]] = {}
    for lbl in sorted(comp_label.values()):
        members = [st["id"] for st in subtasks if st.get("spine_id") == lbl]
        spines_ordered[lbl] = sorted(members, key=_spine_depth)

    # ---- 5. structural checks --------------------------------------------
    for st in subtasks:  # operational cycle via init_from chain
        seen, cur = set(), st["id"]
        while True:
            nxt = init_parent.get(cur)
            if not nxt:
                break
            if nxt in seen or nxt == st["id"]:
                report["errors"].append(f"operational cycle detected through '{st['id']}'")
                break
            seen.add(nxt)
            cur = nxt

    # ---- 6. artifact <-> instruction wiring (content injected at runtime) ----
    # Producers: declare the outputs to state in their final result (captured and
    # passed downstream). Consumers: their inputs' CONTENT is injected at runtime,
    # so we add a labeled "provided inputs" note (using each producer's own
    # description, no repetitive "open the file") and a single placeholder at the
    # END that the runtime replaces with the actual content — the agent never
    # opens a file (saves steps; avoids screenshot-OCR errors).
    for st in all_nodes:
        outs = st.get("outputs") or []
        ins = st.get("input_files") or []
        base = str(st.get("instruction") or "").rstrip()
        blocks: list[str] = []
        if outs:
            lines = ["## Files to create:"]
            for o in outs:
                tail = f" containing {o['description']}" if o.get("description") else ""
                lines.append(f"- Create a file `{ARTIFACT_DIR}/{o['name']}`{tail}.")
            blocks.append("\n".join(lines))
        instr = base + ("\n\n" + "\n\n".join(blocks) if blocks else "")
        if ins:
            instr += "\n\n## Information provided to you (use it to complete your task):\n" + INPUT_PLACEHOLDER
        st["instruction"] = instr

    # dead outputs: declared but never read (warn only)
    for name, owner in output_owner.items():
        if name not in consumed:
            report["warnings"].append(f"output '{name}' (from '{owner}') is declared but read by no node")

    # ---- summary ----------------------------------------------------------
    report["n_subtasks"] = len(subtasks)
    report["n_spine"] = sum(1 for st in subtasks if st["role"] == "spine")
    report["n_branch"] = sum(1 for st in subtasks if st["role"] == "branch")
    report["n_spines"] = spine_counter
    report["n_outputs"] = len(output_owner)
    report["n_artifact_edges"] = sum(len(st.get("input_files") or []) for st in all_nodes)
    report["spines"] = spines_ordered  # {spine_id: [head, ..., tail]}
    if spine_counter > 1:
        report["errors"].append(
            f"{spine_counter} spines found; a task must have exactly ONE spine "
            f"(only one VM survives as the deliverable). Parallel operational nodes "
            f"should be branches feeding URLs/artifacts to the single spine."
        )

    legal_graph = {"subtasks": subtasks, "spines": spines_ordered}
    if agg:
        legal_graph["aggregation"] = agg
    return legal_graph, report
