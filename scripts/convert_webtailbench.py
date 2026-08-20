#!/usr/bin/env python3
"""Convert microsoft/WebTailBench into the odysseys task-file format so it runs
through the same runner (run_macu.py / run_spine_branch.py) and the same
rubric-judge eval (evals/odysseys_eval.py) unchanged.

WebTailBench rows have: benchmark, id, task_summary, precomputed_rubric
(a JSON string {"items": [{criterion, description, max_points, ...}]}).

Mapping to odysseys:
  task_id       <- id
  confirmed_task<- task_summary
  website       <- start URL (default https://www.google.com; WebTailBench has none)
  level         <- benchmark   (so the eval's by-level breakdown groups by category)
  benchmark     <- benchmark   (kept explicitly too)
  rubrics       <- {"R{i}": {requirement: criterion, verification: description,
                             max_points: <kept for optional weighting>}}

Note on scoring: our eval judges each rubric item as equal-weight binary (pass/
fail), matching the odysseys protocol — NOT WebTailBench's native max_points
weighting. We keep max_points in each rubric so a weighted variant is possible
later. Using one protocol across both benchmarks keeps method comparisons
consistent.

Usage:
  python scripts/convert_webtailbench.py \
      --split test_v2 --out data/webtailbench/webtailbench_test_v2.json
  # optional stratified subset (N per category):
  python scripts/convert_webtailbench.py --split test_v2 --per-category 5 \
      --out data/webtailbench/webtailbench_test_v2_sub.json
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

# split -> TSV file in the HF dataset repo
SPLIT_FILES = {
    "test_v2": "WebTailBench-v2-rubrics.tsv",
    "test_v1": "WebTailBench-v1-rubrics.tsv",
    "test": "WebTailBench.tsv",
    "refusals": "WebTailBench-Refusals.tsv",
}
DEFAULT_WEBSITE = "https://www.google.com"


def _load_rows(split: str) -> tuple[list[dict], str]:
    from huggingface_hub import hf_hub_download

    fname = SPLIT_FILES[split]
    path = hf_hub_download("microsoft/WebTailBench", fname, repo_type="dataset")
    csv.field_size_limit(10 * 1024 * 1024)
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return rows, path


def _to_task(row: dict) -> dict | None:
    tid = (row.get("id") or "").strip()
    instr = (row.get("task_summary") or "").strip()
    raw_rubric = row.get("precomputed_rubric") or ""
    if not tid or not instr or not raw_rubric.strip():
        return None
    try:
        items = json.loads(raw_rubric).get("items", [])
    except Exception:
        return None
    rubrics = {}
    for i, it in enumerate(items, 1):
        crit = str(it.get("criterion") or "").strip()
        desc = str(it.get("description") or "").strip()
        if not crit and not desc:
            continue
        rubrics[f"R{i}"] = {
            "requirement": crit or desc,
            "verification": desc or crit,
            "max_points": it.get("max_points"),
        }
    if not rubrics:
        return None
    bench = (row.get("benchmark") or "unknown").strip()
    return {
        "task_id": tid,
        "confirmed_task": instr,
        "website": DEFAULT_WEBSITE,
        "level": bench,          # eval groups by-level -> per-category breakdown
        "benchmark": bench,
        "rubrics": rubrics,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test_v2", choices=list(SPLIT_FILES))
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--per-category", type=int, default=0,
                    help="If >0, keep N tasks per benchmark category (stratified subset).")
    ap.add_argument("--seed", type=int, default=0,
                    help="RNG seed for random within-category sampling (reproducible).")
    args = ap.parse_args()

    rows, src = _load_rows(args.split)
    tasks = [t for t in (_to_task(r) for r in rows) if t]
    dropped = len(rows) - len(tasks)

    if args.per_category > 0:
        # Stratified by category, RANDOM within each category (seeded => reproducible),
        # so the subset covers each category's site/task-type diversity rather than
        # clustering on the alphabetically-first ids.
        rng = random.Random(args.seed)
        by_cat: dict[str, list[dict]] = defaultdict(list)
        for t in tasks:
            by_cat[t["benchmark"]].append(t)
        tasks = [
            t
            for cat in sorted(by_cat)
            for t in rng.sample(by_cat[cat], min(args.per_category, len(by_cat[cat])))
        ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")

    cats = Counter(t["benchmark"] for t in tasks)
    rub = sum(len(t["rubrics"]) for t in tasks)
    print(f"source: {src}")
    print(f"wrote {len(tasks)} task(s) ({dropped} dropped) -> {args.out}")
    print(f"total rubric items: {rub} (mean {rub/max(len(tasks),1):.1f}/task)")
    print("categories: " + ", ".join(f"{k}={v}" for k, v in sorted(cats.items())))


if __name__ == "__main__":
    main()
