#!/usr/bin/env python3
"""Evaluation-variance + significance analysis for the odysseys-200 main table.

For each of the 9 configs (3 methods x 3 backbones) we have K judge samples
(canonical odysseys_eval.json + odysseys_eval_var*.json). Trajectories are fixed;
only the LLM judge re-runs, so the spread across samples is EVALUATION variance.

Outputs:
  (1) per-config Rubric-Average (macro) and SR as mean +/- std over the K samples;
  (2) per-backbone pairwise significance (Spine-Branch vs Single, vs MACU; MACU vs
      Single) using paired tests over the 200 tasks on per-task scores averaged
      across the K judge samples (denoised): Wilcoxon signed-rank + paired t-test
      for Rubric; Wilcoxon + McNemar (majority-vote perfect) for SR.
"""
import json, glob, os, sys
from pathlib import Path
import numpy as np
from scipy import stats

METHODS = ["single", "macu", "spinebranch"]
BACKBONES = ["gpt54mini", "qwen36", "qwen37plus"]
DIR = {
    ("single", "gpt54mini"): "odysseys200_single_gpt54mini",
    ("single", "qwen36"): "odysseys200_single_qwen36",
    ("single", "qwen37plus"): "odysseys200_single_qwen37plus",
    ("macu", "gpt54mini"): "odysseys200_macu_gpt54mini_replan5",
    ("macu", "qwen36"): "odysseys200_macu_qwen36_replan5",
    ("macu", "qwen37plus"): "odysseys200_macu_qwen37plus_replan5",
    ("spinebranch", "gpt54mini"): "odysseys200_spinebranch_gpt54mini_sba",
    ("spinebranch", "qwen36"): "odysseys200_spinebranch_qwen36_sba",
    ("spinebranch", "qwen37plus"): "odysseys200_spinebranch_qwen37plus_sba",
}
PRETTY = {"single": "Single", "macu": "MACU", "spinebranch": "Spine-Branch"}
RUNS = Path("runs")


def load_samples(dirname):
    """Return list of {task_id: (rubric, perfect)} dicts, one per HOMOGENEOUS judge
    sample. We use only the fresh direct-200 re-evals (odysseys_eval_var*.json); the
    canonical odysseys_eval.json is a 'merged 45+155' artifact scored by a different
    procedure and sits systematically above the fresh runs, so it is NOT pooled."""
    base = RUNS / dirname
    files = sorted(base.glob("odysseys_eval_var*.json"))
    samples = []
    for f in files:
        if not f.exists():
            continue
        tasks = json.load(open(f))["tasks"]
        d = {t["task_id"]: (float(t["average_rubric_score"]), 1.0 if t["perfect"] else 0.0)
             for t in tasks}
        samples.append((f.name, d))
    return samples


def load_canonical(dirname):
    p = RUNS / dirname / "odysseys_eval.json"
    if not p.exists():
        return None
    t = json.load(open(p))["tasks"]
    import numpy as _np
    return (_np.mean([x["average_rubric_score"] for x in t]),
            _np.mean([1.0 if x["perfect"] else 0.0 for x in t]))


def config_metrics(samples):
    """Per-sample RubricAvg and SR; plus per-task denoised means aligned by task_id."""
    ras, srs = [], []
    for _, d in samples:
        vals = list(d.values())
        ras.append(np.mean([r for r, _ in vals]))
        srs.append(np.mean([p for _, p in vals]))
    return np.array(ras), np.array(srs)


def per_task_denoised(samples):
    """task_id -> (mean_rubric, mean_perfect) over samples."""
    ids = set.intersection(*[set(d) for _, d in samples])
    ids = sorted(ids)
    rub = {tid: np.mean([d[tid][0] for _, d in samples]) for tid in ids}
    per = {tid: np.mean([d[tid][1] for _, d in samples]) for tid in ids}
    return ids, rub, per


def mcnemar(b, c):
    """Exact-ish McNemar (binomial) on discordant pairs b, c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    # two-sided exact binomial p
    p = 2 * sum(stats.binom.pmf(i, n, 0.5) for i in range(0, k + 1))
    return min(1.0, p)


def paired_pvals(idsA, rubA, perA, idsB, rubB, perB):
    ids = sorted(set(idsA) & set(idsB))
    ra = np.array([rubA[t] for t in ids]); rb = np.array([rubB[t] for t in ids])
    pa = np.array([perA[t] for t in ids]); pb = np.array([perB[t] for t in ids])
    # Rubric: Wilcoxon signed-rank + paired t
    dr = ra - rb
    try:
        w_r = stats.wilcoxon(ra, rb, zero_method="wilcox").pvalue if np.any(dr != 0) else 1.0
    except ValueError:
        w_r = 1.0
    t_r = stats.ttest_rel(ra, rb).pvalue
    # SR: Wilcoxon on per-task mean-perfect + McNemar on majority-vote binary
    dp = pa - pb
    try:
        w_s = stats.wilcoxon(pa, pb, zero_method="wilcox").pvalue if np.any(dp != 0) else 1.0
    except ValueError:
        w_s = 1.0
    binA = (pa >= 0.5).astype(int); binB = (pb >= 0.5).astype(int)
    b = int(np.sum((binA == 1) & (binB == 0)))  # A perfect, B not
    c = int(np.sum((binA == 0) & (binB == 1)))
    mc_s = mcnemar(b, c)
    return dict(n=len(ids), d_rub=ra.mean() - rb.mean(), w_rub=w_r, t_rub=t_r,
                d_sr=pa.mean() - pb.mean(), w_sr=w_s, mcnemar_sr=mc_s, disc=(b, c))


def main():
    # load all
    data = {}
    ncfg_ok = 0
    for m in METHODS:
        for b in BACKBONES:
            s = load_samples(DIR[(m, b)])
            data[(m, b)] = s
            ncfg_ok += 1
    ks = {k: len(v) for k, v in data.items()}
    print(f"Loaded samples per config (canonical + var*): "
          f"{min(ks.values())}..{max(ks.values())}")
    for k, n in ks.items():
        print(f"  {DIR[k]:42s} samples={n}")
    print()

    # (1) mean +/- std table
    print("=" * 78)
    print("TABLE 1 — Rubric-Average (macro) and SR, mean +/- std over judge samples")
    print("=" * 78)
    print(f"{'Backbone':11s} {'Method':13s} {'RubricAvg (mean±std)':24s} {'SR (mean±std)':22s} {'K'}")
    cfg_stats = {}
    for b in BACKBONES:
        for m in METHODS:
            ras, srs = config_metrics(data[(m, b)])
            cfg_stats[(m, b)] = (ras, srs)
            can = load_canonical(DIR[(m, b)])
            cstr = f"  [canon {can[0]:.3f}/{can[1]:.3f}]" if can else ""
            print(f"{b:11s} {PRETTY[m]:13s} "
                  f"{ras.mean():.4f} ± {ras.std(ddof=1):.4f}       "
                  f"{srs.mean():.4f} ± {srs.std(ddof=1):.4f}     {len(ras)}{cstr}")
        print()

    # (2) pairwise significance per backbone
    print("=" * 78)
    print("TABLE 2 — Paired significance over 200 tasks (denoised per-task scores)")
    print("  Rubric: Wilcoxon signed-rank (w) & paired t (t);  SR: Wilcoxon (w) & McNemar")
    print("=" * 78)
    denoised = {(m, b): per_task_denoised(data[(m, b)]) for m in METHODS for b in BACKBONES}
    pairs = [("spinebranch", "single"), ("spinebranch", "macu"), ("macu", "single")]
    for b in BACKBONES:
        print(f"\n### backbone = {b}")
        print(f"{'comparison':26s} {'ΔRubric':>9s} {'p(Wil)':>9s} {'p(t)':>9s} "
              f"{'ΔSR':>8s} {'p(Wil)':>9s} {'p(McN)':>9s}")
        for A, B in pairs:
            ia, ra, pa = denoised[(A, b)]
            ib, rb, pb = denoised[(B, b)]
            r = paired_pvals(ia, ra, pa, ib, rb, pb)
            def star(p):
                return "***" if p < 1e-3 else "**" if p < 1e-2 else "*" if p < 0.05 else ""
            print(f"{PRETTY[A]+' vs '+PRETTY[B]:26s} "
                  f"{r['d_rub']:+9.4f} {r['w_rub']:9.2e}{star(r['w_rub']):3s} {r['t_rub']:9.2e} "
                  f"{r['d_sr']:+8.4f} {r['w_sr']:9.2e}{star(r['w_sr']):3s} {r['mcnemar_sr']:9.2e}")
    print("\n(* p<.05, ** p<.01, *** p<.001; Δ = A−B on per-task means averaged over judge samples)")


if __name__ == "__main__":
    main()
