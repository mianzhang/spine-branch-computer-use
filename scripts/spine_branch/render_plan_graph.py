#!/usr/bin/env python3
"""Render a dependency-graph JSON (MACU or spine-branch) to a figure.

Edge semantics (the whole point of the figure):
  * DATA / dependency edge (thin gray)         : parent -> node ordering + artifact flow
  * VM-INHERITANCE edge (thick red, "VM")       : which parent's LIVE VM this node continues
      - MACU  : a CUA node inherits its FIRST CUA-parent (runtime rule); managers inherit nothing
      - spine : a node inherits `init_from` iff it is non-null

Node styling:
  * manager node  -> light-blue dashed box (pure LLM, no VM)
  * spine node    -> thick black border, gray fill (the one surviving VM chain)
  * branch node   -> dashed border, light fill (disposable VM)
  * MACU CUA node -> plain box

Handles JSON shapes: a bare graph {subtasks,aggregation}; {"graph": {...}};
or {"dependency_graph": {...}} (run dirs).

Usage:
  # single file
  python scripts/spine_branch/render_plan_graph.py path/to/foo_macu.json [--out foo.png] [--mode auto|macu|spine]
  # batch a directory (renders every *_macu.json / *_spine.json / dependency_graph.json)
  python scripts/spine_branch/render_plan_graph.py --dir reports/plan_compare/ody45_sol [--out-dir <dir>]
"""
from __future__ import annotations
import argparse, json, os, glob, textwrap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


def _unwrap(obj: dict) -> dict:
    """Return the graph dict with keys subtasks/aggregation from any wrapper."""
    if "subtasks" in obj:
        return obj
    if isinstance(obj.get("graph"), dict):
        return obj["graph"]
    if isinstance(obj.get("dependency_graph"), dict):
        return obj["dependency_graph"]
    raise ValueError("no subtasks found in JSON")


def _nodes(graph: dict) -> list[dict]:
    subs = [dict(s) for s in (graph.get("subtasks") or []) if isinstance(s, dict) and s.get("id")]
    agg = graph.get("aggregation")
    if isinstance(agg, dict) and agg.get("id"):
        a = dict(agg); a.setdefault("agent_type", "manager"); a.setdefault("role", "branch")
        subs.append(a)
    return subs


def _detect_mode(nodes: list[dict], fname: str) -> str:
    if "_spine" in fname:
        return "spine"
    if "_macu" in fname:
        return "macu"
    if any(n.get("role") in ("spine", "branch") for n in nodes if n.get("agent_type", "cua") != "manager"):
        return "spine"
    return "macu"


def _vm_parent(node: dict, byid: dict, mode: str) -> str | None:
    """Which parent's live VM this node inherits (or None)."""
    if node.get("agent_type", "cua") == "manager":
        return None                       # managers hold no VM
    if mode == "spine":
        inf = node.get("init_from")
        return inf if (isinstance(inf, str) and inf in byid) else None
    # MACU: first CUA parent in dependency order
    for d in (node.get("dependencies") or []):
        p = byid.get(d)
        if p is not None and p.get("agent_type", "cua") != "manager":
            return d
    return None


def _layers(nodes: list[dict], byid: dict) -> dict:
    """Longest-path layer per node over the dependency DAG (cycle-safe)."""
    memo: dict = {}
    def depth(i, seen=()):
        if i in memo:
            return memo[i]
        if i in seen:
            return 0
        ps = [d for d in (byid.get(i, {}).get("dependencies") or []) if d in byid]
        r = 0 if not ps else 1 + max(depth(p, seen + (i,)) for p in ps)
        memo[i] = r
        return r
    return {n["id"]: depth(n["id"]) for n in nodes}


def render(graph: dict, out_path: str, mode: str, title: str) -> dict:
    nodes = _nodes(graph)
    byid = {n["id"]: n for n in nodes}
    layer = _layers(nodes, byid)
    # positions: x = layer, y = spread within layer (stable by id)
    by_layer: dict = {}
    for n in nodes:
        by_layer.setdefault(layer[n["id"]], []).append(n["id"])
    pos = {}
    max_w = max((len(v) for v in by_layer.values()), default=1)
    for L, ids in by_layer.items():
        ids = sorted(ids)
        for k, nid in enumerate(ids):
            y = (k - (len(ids) - 1) / 2.0)
            pos[nid] = (L * 3.2, -y * 1.7)

    nlayers = (max(by_layer) + 1) if by_layer else 1
    fig_w = max(6, nlayers * 3.2)
    fig_h = max(3.5, max_w * 1.7 + 1.2)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_axis_off()

    NBW, NBH = 2.5, 1.05  # node box half-extents handled via boxstyle
    # ---- edges first (under nodes) ----
    n_multiparent = 0
    for n in nodes:
        deps = [d for d in (n.get("dependencies") or []) if d in byid]
        cua_deps = [d for d in deps if byid[d].get("agent_type", "cua") != "manager"]
        if n.get("agent_type", "cua") != "manager" and len(cua_deps) >= 2:
            n_multiparent += 1
        vmp = _vm_parent(n, byid, mode)
        for d in deps:
            if d not in pos:
                continue
            x0, y0 = pos[d]; x1, y1 = pos[n["id"]]
            is_vm = (d == vmp)
            style = dict(arrowstyle="-|>", mutation_scale=12,
                         connectionstyle="arc3,rad=0.06")
            if is_vm:
                style.update(color="#c0392b", lw=2.2, zorder=2)
            else:
                style.update(color="#b0b0b0", lw=0.9, zorder=1)
            ax.add_patch(FancyArrowPatch((x0 + 1.15, y0), (x1 - 1.15, y1), **style))

    # ---- nodes ----
    for n in nodes:
        x, y = pos[n["id"]]
        at = n.get("agent_type", "cua")
        role = n.get("role")
        if at == "manager":
            fc, ec, ls, lw = "#dbe9ff", "#3b6fb0", "--", 1.4
        elif role == "spine":
            fc, ec, ls, lw = "#d9d9d9", "#000000", "-", 2.4
        elif role == "branch":
            fc, ec, ls, lw = "#f4f4f4", "#666666", "--", 1.1
        else:  # macu cua
            fc, ec, ls, lw = "#eef3ee", "#333333", "-", 1.2
        box = FancyBboxPatch((x - 1.15, y - 0.42), 2.3, 0.84,
                             boxstyle="round,pad=0.02,rounding_size=0.12",
                             fc=fc, ec=ec, ls=ls, lw=lw, zorder=3)
        ax.add_patch(box)
        lbl = "\n".join(textwrap.wrap(n["id"], 18)) or n["id"]
        tag = {"spine": "SPINE ", "branch": ""}.get(role, "")
        if at == "manager":
            tag = "mgr "
        ax.text(x, y, (tag + lbl) if tag else lbl, ha="center", va="center",
                fontsize=7, zorder=4, family="monospace")

    xs = [p[0] for p in pos.values()] or [0]
    ys = [p[1] for p in pos.values()] or [0]
    ax.set_xlim(min(xs) - 1.6, max(xs) + 1.6)
    ax.set_ylim(min(ys) - 1.0, max(ys) + 1.4)
    # legend
    ax.plot([], [], color="#c0392b", lw=2.2, label="VM inheritance")
    ax.plot([], [], color="#b0b0b0", lw=0.9, label="data / dependency")
    ax.legend(loc="upper left", fontsize=6, framealpha=0.8)
    ax.set_title(f"{title}  [{mode}]  |  nodes={len(nodes)}  multi-parent hubs={n_multiparent}",
                 fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return {"nodes": len(nodes), "layers": nlayers, "multiparent_hubs": n_multiparent}


def _render_file(path: str, out: str | None, mode: str) -> str:
    obj = json.load(open(path))
    graph = _unwrap(obj)
    nodes = _nodes(graph)
    m = mode if mode != "auto" else _detect_mode(nodes, os.path.basename(path))
    title = obj.get("task_id") or graph.get("task_id") or os.path.basename(path).rsplit(".", 1)[0]
    if out is None:
        out = os.path.splitext(path)[0] + ".png"
    render(graph, out, m, title)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", help="a graph .json file")
    ap.add_argument("--out", default=None)
    ap.add_argument("--mode", default="auto", choices=["auto", "macu", "spine"])
    ap.add_argument("--dir", default=None, help="batch: render every graph json in this dir")
    ap.add_argument("--out-dir", default=None, help="output dir for batch (default: <dir>/figs)")
    a = ap.parse_args()

    if a.dir:
        files = sorted(glob.glob(os.path.join(a.dir, "*_macu.json")) +
                       glob.glob(os.path.join(a.dir, "*_spine.json")) +
                       glob.glob(os.path.join(a.dir, "**", "dependency_graph.json"), recursive=True))
        outdir = a.out_dir or os.path.join(a.dir, "figs")
        os.makedirs(outdir, exist_ok=True)
        ok = 0
        for f in files:
            base = os.path.splitext(os.path.basename(f))[0]
            if base == "dependency_graph":
                base = os.path.basename(os.path.dirname(f)) + "_dg"
            out = os.path.join(outdir, base + ".png")
            try:
                _render_file(f, out, a.mode); ok += 1
            except Exception as e:
                print(f"  FAIL {f}: {str(e)[:100]}")
        print(f"rendered {ok}/{len(files)} -> {outdir}")
    elif a.input:
        out = _render_file(a.input, a.out, a.mode)
        print(f"wrote {out}")
    else:
        ap.error("provide an input file or --dir")


if __name__ == "__main__":
    main()
