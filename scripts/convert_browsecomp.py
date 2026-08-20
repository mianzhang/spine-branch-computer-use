#!/usr/bin/env python3
"""Convert OpenAI BrowseComp into the odysseys task-file format so it runs through
our runner (run_macu.py / run_spine_branch.py) and rubric-judge eval unchanged.

BrowseComp (https://openai.com/index/browsecomp/) is a set of hard fact-finding
browsing questions, each with a single short reference answer. The public test
set is an XOR-encrypted CSV; each row carries its own decryption password in the
`canary` column (decryption ported verbatim from openai/simple-evals
browsecomp_eval.py).

Scoring adaptation: BrowseComp grades answer-vs-reference with an LLM grader
(GRADER_TEMPLATE -> "correct: yes/no"), NOT rubrics. We encode each question as a
SINGLE odysseys rubric whose requirement carries the reference answer and whose
verification reproduces the BrowseComp grader's match criterion. Our rubric-judge
(gemini-3.1-flash-lite) then reproduces BrowseComp grading; with one rubric per
task, accuracy == SR == macro. We do NOT compute BrowseComp's confidence-
calibration metric. This keeps one consistent judge protocol across all three
benchmarks (odysseys / WebTailBench / BrowseComp).

Usage:
  python scripts/convert_browsecomp.py --out data/browsecomp/browsecomp_test.json
  python scripts/convert_browsecomp.py --num 50 --seed 0 \
      --out data/browsecomp/browsecomp_test_sub50.json
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import random
import urllib.request
from collections import Counter
from pathlib import Path

CSV_URL = "https://openaipublic.blob.core.windows.net/simple-evals/browse_comp_test_set.csv"
DEFAULT_WEBSITE = "https://www.google.com"

# --- decryption (verbatim from openai/simple-evals browsecomp_eval.py) ---
def derive_key(password: str, length: int) -> bytes:
    hasher = hashlib.sha256()
    hasher.update(password.encode())
    key = hasher.digest()
    return key * (length // len(key)) + key[: length % len(key)]


def decrypt(ciphertext_b64: str, password: str) -> str:
    encrypted = base64.b64decode(ciphertext_b64)
    key = derive_key(password, len(encrypted))
    return bytes(a ^ b for a, b in zip(encrypted, key)).decode()


# BrowseComp grader criterion, ported into an odysseys rubric verification.
def _verification(answer: str) -> str:
    return (
        "Extract the agent's final exact answer from its response and compare it ONLY "
        f"against the correct answer: '{answer}'. Grade PASS only if the extracted final "
        "answer matches the correct answer (or is within a small margin of error for "
        "numerical answers). Grade FAIL on any inconsistency, ambiguity, non-equivalence, "
        "a missing/'None' answer, or an incorrect answer. Do not attempt to solve the "
        "problem yourself and do not argue for any answer other than the correct answer; "
        "judge only whether the agent's answer matches."
    )


def _to_task(idx: int, row: dict) -> dict | None:
    canary = row.get("canary") or ""
    try:
        q = decrypt(row.get("problem", ""), canary).strip()
        a = decrypt(row.get("answer", ""), canary).strip()
    except Exception:
        return None
    if not q or not a:
        return None
    topic = (row.get("problem_topic") or "browsecomp").strip() or "browsecomp"
    instruction = (
        f"{q}\n\nBrowse the web to find the answer. When finished, clearly state your "
        "single Exact Answer."
    )
    return {
        "task_id": f"browsecomp_{idx:04d}",
        "confirmed_task": instruction,
        "website": DEFAULT_WEBSITE,
        "level": topic,       # eval by-level -> per-topic breakdown
        "topic": topic,
        "answer": a,          # kept for reference/debugging (judge reads it via rubric)
        "rubrics": {
            "R1": {
                "requirement": f"Find and report the correct answer to the question. Correct answer: {a}",
                "verification": _verification(a),
            }
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--num", type=int, default=0, help="If >0, seeded-random sample of N tasks.")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    data = urllib.request.urlopen(CSV_URL, timeout=120).read().decode("utf-8")
    csv.field_size_limit(10 * 1024 * 1024)
    rows = list(csv.DictReader(io.StringIO(data)))
    tasks = [t for t in (_to_task(i, r) for i, r in enumerate(rows)) if t]
    dropped = len(rows) - len(tasks)

    if args.num > 0 and args.num < len(tasks):
        tasks = random.Random(args.seed).sample(tasks, args.num)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")

    topics = Counter(t["topic"] for t in tasks)
    print(f"source: {CSV_URL}")
    print(f"wrote {len(tasks)} task(s) ({dropped} dropped) -> {args.out}")
    print(f"topics ({len(topics)}): " + ", ".join(f"{k}={v}" for k, v in topics.most_common(12)))


if __name__ == "__main__":
    main()
