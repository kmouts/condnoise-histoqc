#!/usr/bin/env python
"""
bootstrap_compare.py -- confidence intervals and paired comparisons for the DGX evaluations.

Reads eval JSONs that carry per-slide counts (produced by evaluate_wsi.py after the
--from-json / counts patches) and answers the question no number in this project has an
answer to yet: how much of a reported difference survives the uncertainty of having
evaluated on 24 slides?

WHY A BOOTSTRAP AND NOT A T-TEST
The reported F1 is *pooled*: TP, FP and FN are summed across slides and the ratio is taken
once. That is not a mean of per-slide F1s, so it has no per-slide standard error to plug
into a t-test. Resampling slides and re-pooling reproduces the estimator exactly, whatever
its distribution.

WHY PAIRED
Slide difficulty dominates everything else here -- per-slide F1 spans 0.03 to 0.95. Two
models evaluated on independently resampled slide sets would be compared mostly on which
slides each happened to draw. Using the SAME resampled indices for every model removes
that variance entirely, which is the whole point: the question is not "how variable is
F1" but "how variable is the DIFFERENCE in F1".

WHY STRATIFIED
13 of 24 slides carry artifacts, 11 are clean. Unstratified resampling produces replicates
with very few clean slides -- sometimes none -- making the clean-slide false-positive rate
undefined or wildly unstable. Resampling within each stratum, preserving 13 and 11, keeps
every replicate interpretable. This narrows the intervals slightly relative to unstratified
resampling; that is correct, since the 13/11 split is a fixed property of the test set and
not something being estimated.

THREE STATISTICS, REPORTED SEPARATELY
Pooled F1 mixes two different mechanisms. In the variantA-vs-variantB comparison the pooled
gap is 0.012, but the artifact-slide gap is only 0.006 -- the other half comes from clean
slides, where variantA raises fewer false alarms (4.15% vs 6.14%). Collapsing those into one
number hides which mechanism is responsible, so pooled F1, artifact-slide F1 and clean FP
rate are each given their own interval.

A CAVEAT THE INTERVALS CANNOT EXPRESS
Ground truth is extremely concentrated: the four largest slides hold ~70% of all annotated
pixels and the single largest holds ~27%. The effective sample size for a pixel-pooled
metric is therefore nearer 4 than 24, and the intervals will be correspondingly wide. That
is a real property of the evaluation, not a defect of the method -- but it means a wide
interval here should be read as "the test set cannot resolve this difference", not as
"the bootstrap is being pessimistic". The GT concentration is printed so the two are not
confused.

USAGE
    bootstrap_compare.py --eval eval_a.json eval_b.json [...] \
                         [--ref TAG] [--n 10000] [--seed 0] [--out results.json]

The reference run defaults to the first file given; every other run is compared against it.
"""

import argparse
import json
import os
import sys

import numpy as np

# ----------------------------------------------------------------- metric definitions
#
# Each takes summed counts and returns a scalar, so the same code path serves the point
# estimate and every bootstrap replicate. Pooling happens before the ratio, never after.


def f1_from(tp, fp, fn):
    denom = 2 * tp + fp + fn
    return np.where(denom > 0, 2 * tp / np.maximum(denom, 1), np.nan)


def sens_from(tp, fn):
    denom = tp + fn
    return np.where(denom > 0, tp / np.maximum(denom, 1), np.nan)


def prec_from(tp, fp):
    denom = tp + fp
    return np.where(denom > 0, tp / np.maximum(denom, 1), np.nan)


# ----------------------------------------------------------------------------- loading


def load_runs(paths):
    """Load eval JSONs into aligned count matrices.

    Returns a dict of (n_models, n_slides) arrays plus metadata. Slides are ordered
    identically across models -- without that the pairing is meaningless, so a mismatch
    is fatal rather than a warning.
    """
    runs = []
    for p in paths:
        with open(p) as fh:
            j = json.load(fh)
        if not j.get('per_slide'):
            sys.exit(f"ERROR: {os.path.basename(p)} has no per_slide block.")
        if 'tp' not in j['per_slide'][0]:
            sys.exit(f"ERROR: {os.path.basename(p)} predates the counts patch "
                     f"(per_slide has no 'tp'). Re-run evaluate_wsi.py with --from-json.")
        runs.append(j)

    sets = [set(r['slide'] for r in j['per_slide']) for j in runs]
    union = sorted(set().union(*sets))
    shared = sorted(set.intersection(*sets))
    if not shared:
        sys.exit("ERROR: the runs share no slides at all. Cannot pair.")

    if len(shared) < len(union):
        # INTERSECTION: comparing on shared slides only. Announce it loudly -- a silently
        # reduced slide set would change what every number means.
        print(f"\n  NOTE: slide sets differ. Comparing on the {len(shared)} shared "
              f"slides of {len(union)} total.")
        for p, s in zip(paths, sets):
            miss = sorted(set(union) - s)
            if miss:
                print(f"    {os.path.basename(p)} is missing {len(miss)}:")
                for m in miss:
                    print(f"      {m[:46]}")
            if len(s) < 0.8 * len(union):
                print(f"    WARNING: {os.path.basename(p)} covers only "
                      f"{100*len(s)/len(union):.0f}% of slides; the comparison is weak.")
        print()

    slides = shared
    n_m, n_s = len(runs), len(slides)

    tp = np.zeros((n_m, n_s), dtype=np.int64)
    fp = np.zeros_like(tp)
    fn = np.zeros_like(tp)
    tissue = np.zeros_like(tp)

    types = sorted(runs[0]['per_slide'][0].get('per_type', {}).keys())
    ttp = {t: np.zeros((n_m, n_s), dtype=np.int64) for t in types}
    tgt = {t: np.zeros((n_m, n_s), dtype=np.int64) for t in types}

    is_clean = None
    for mi, j in enumerate(runs):
        by_slide = {r['slide']: r for r in j['per_slide']}
        clean_this = []
        for si, sl in enumerate(slides):
            r = by_slide[sl]
            tp[mi, si] = r['tp']
            fp[mi, si] = r['fp']
            fn[mi, si] = r['fn']
            tissue[mi, si] = r['tissue_px']
            clean_this.append(bool(r['is_clean']))
            for t in types:
                ttp[t][mi, si] = r['per_type'][t]['tp']
                tgt[t][mi, si] = r['per_type'][t]['gt_px']
        clean_this = np.array(clean_this)
        # is_clean derives from ground truth, so it must agree across models; if it does
        # not, the runs were evaluated against different annotations.
        if is_clean is None:
            is_clean = clean_this
        elif not np.array_equal(is_clean, clean_this):
            sys.exit("ERROR: runs disagree on which slides are clean -- different ground "
                     "truth. Cannot compare.")

    tags = [j.get('tag', os.path.basename(p)) for j, p in zip(runs, paths)]
    return dict(tags=tags, slides=slides, tp=tp, fp=fp, fn=fn, tissue=tissue,
                is_clean=is_clean, types=types, ttp=ttp, tgt=tgt, raw=runs)


# --------------------------------------------------------------------------- statistics


def statistics(d, W):
    """Apply slide weights W (n_rep, n_slides) and return every statistic.

    W holds how many times each slide was drawn in each replicate, so a weighted matrix
    product performs all replicates at once. The point estimate is just W = all ones.
    """
    art = ~d['is_clean']
    cln = d['is_clean']

    def wsum(mat, sel=None):
        m = mat if sel is None else mat * sel
        return W @ m.T  # (n_rep, n_models)

    TP, FP, FN = wsum(d['tp']), wsum(d['fp']), wsum(d['fn'])
    aTP, aFP, aFN = wsum(d['tp'], art), wsum(d['fp'], art), wsum(d['fn'], art)
    cFP, cTIS = wsum(d['fp'], cln), wsum(d['tissue'], cln)

    out = {
        'pooled_f1': f1_from(TP, FP, FN),
        'pooled_sens': sens_from(TP, FN),
        'pooled_prec': prec_from(TP, FP),
        'artifact_f1': f1_from(aTP, aFP, aFN),
        'clean_fp_rate': np.where(cTIS > 0, cFP / np.maximum(cTIS, 1), np.nan),
    }
    for t in d['types']:
        tt, tg = wsum(d['ttp'][t]), wsum(d['tgt'][t])
        out[f'sens_{t}'] = np.where(tg > 0, tt / np.maximum(tg, 1), np.nan)
    return out


def make_weights(rng, is_clean, n_rep):
    """Stratified bootstrap weights.

    A bootstrap resample of n items is exactly a multinomial draw of n trials over those
    n items, so the multiplicities can be generated directly -- no index shuffling, and
    all replicates in one call.
    """
    n_s = len(is_clean)
    art_idx = np.where(~is_clean)[0]
    cln_idx = np.where(is_clean)[0]
    W = np.zeros((n_rep, n_s))
    for idx in (art_idx, cln_idx):
        k = len(idx)
        if k == 0:
            continue
        W[:, idx] = rng.multinomial(k, np.full(k, 1.0 / k), size=n_rep)
    return W


def permutation_null(rng, d, i, j, n_perm):
    """Paired permutation test on pooled F1 for models i and j.

    Under the null the two models are interchangeable, so swapping their counts on a
    randomly chosen subset of slides should not change the difference systematically.
    This is a distribution-free companion to the bootstrap interval; the two answering
    the same way is reassuring, and them disagreeing is worth investigating.
    """
    n_s = len(d['slides'])
    swap = rng.random((n_perm, n_s)) < 0.5
    keep = ~swap

    def mix(mat):
        a = keep * mat[i] + swap * mat[j]
        b = keep * mat[j] + swap * mat[i]
        return a.sum(axis=1), b.sum(axis=1)

    tpa, tpb = mix(d['tp'])
    fpa, fpb = mix(d['fp'])
    fna, fnb = mix(d['fn'])
    return f1_from(tpa, fpa, fna) - f1_from(tpb, fpb, fnb)


# --------------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--eval', nargs='+', required=True, help='eval JSONs with per-slide counts')
    ap.add_argument('--ref', default=None, help='tag of the reference run (default: first file)')
    ap.add_argument('--n', type=int, default=10000, help='bootstrap replicates (default 10000)')
    ap.add_argument('--n-perm', type=int, default=10000, help='permutations (default 10000)')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', default=None, help='write results as JSON')
    args = ap.parse_args()

    d = load_runs(args.eval)
    tags, n_m = d['tags'], len(d['tags'])
    rng = np.random.default_rng(args.seed)

    print("=" * 78)
    print(f"{len(d['slides'])} slides  ({int((~d['is_clean']).sum())} artifact, "
          f"{int(d['is_clean'].sum())} clean)   {n_m} runs   {args.n} replicates   "
          f"seed {args.seed}")

    # ---- ground-truth concentration: the reason the intervals are as wide as they are
    gt = (d['tp'] + d['fn'])[0]
    order = np.argsort(gt)[::-1]
    tot = gt.sum()
    print(f"\nGround-truth concentration (total {tot:,} px):")
    for k in order[:4]:
        print(f"  {d['slides'][k][:44]:<46} {gt[k]:>12,}  {100*gt[k]/tot:5.1f}%")
    print(f"  {'top 4 combined':<46} {gt[order[:4]].sum():>12,}  "
          f"{100*gt[order[:4]].sum()/tot:5.1f}%")
    eff = tot ** 2 / (gt ** 2).sum()          # Kish effective sample size
    print(f"  effective n (Kish) = {eff:.1f} of {int((~d['is_clean']).sum())} artifact slides")

    # ---- point estimates, and a check against what evaluate_wsi.py reported
    ones = np.ones((1, len(d['slides'])))
    point = {k: v[0] for k, v in statistics(d, ones).items()}

    # Each run is checked against its OWN slide set: do its per-slide counts re-pool to
    # its own saved aggregate? Using the intersection here would compare a 21-slide sum
    # against a 24-slide aggregate and report a mismatch that does not exist.
    print("\nConsistency with the saved aggregate (each run on its own slides):")
    ok = True
    for mi, j in enumerate(d['raw']):
        a = b = c = 0
        for r in j['per_slide']:
            a += r['tp']; b += r['fp']; c += r['fn']
        den = 2 * a + b + c
        own = (2 * a / den) if den else float('nan')
        rep = j['aggregate']['f1']
        flag = '' if abs(rep - own) < 5e-4 else '   <-- MISMATCH'
        ok &= (flag == '')
        n_own = len(j['per_slide'])
        shared_note = ''
        if n_own != len(d['slides']):
            shared_note = (f"   [on the {len(d['slides'])} shared: "
                           f"{point['pooled_f1'][mi]:.4f}]")
        print(f"  {tags[mi]:<34} saved {rep:.4f}   from counts {own:.4f}"
              f"  (n={n_own}){flag}{shared_note}")
    if not ok:
        sys.exit("\nERROR: per-slide counts do not re-pool to the saved aggregate. The "
                 "counts are wrong or the JSONs are stale; refusing to bootstrap.")

    # ---- bootstrap
    W = make_weights(rng, d['is_clean'], args.n)
    boot = statistics(d, W)

    def ci(a):
        return np.nanpercentile(a, [2.5, 97.5], axis=0)

    keys = ['pooled_f1', 'artifact_f1', 'clean_fp_rate'] + \
           [f'sens_{t}' for t in d['types']]

    print("\n" + "=" * 78)
    print("POINT ESTIMATES WITH 95% INTERVALS")
    for k in keys:
        lo, hi = ci(boot[k])
        print(f"\n  {k}")
        for mi in range(n_m):
            print(f"    {tags[mi]:<34} {point[k][mi]:.4f}  [{lo[mi]:.4f}, {hi[mi]:.4f}]"
                  f"   +/-{(hi[mi]-lo[mi])/2:.4f}")

    # ---- paired differences against the reference
    ri = 0 if args.ref is None else next(
        (i for i, t in enumerate(tags) if t == args.ref), None)
    if ri is None:
        sys.exit(f"ERROR: --ref {args.ref!r} matches no tag. Available: {tags}")

    print("\n" + "=" * 78)
    print(f"PAIRED DIFFERENCES vs {tags[ri]}   (positive = the other run is higher)")
    results = {}
    for mi in range(n_m):
        if mi == ri:
            continue
        print(f"\n  {tags[mi]}")
        entry = {}
        for k in keys:
            delta = boot[k][:, mi] - boot[k][:, ri]
            lo, hi = np.nanpercentile(delta, [2.5, 97.5])
            obs = point[k][mi] - point[k][ri]
            frac = float(np.nanmean(delta > 0))
            crosses = 'crosses zero' if lo < 0 < hi else 'excludes zero'
            print(f"    {k:<22} {obs:+.4f}  [{lo:+.4f}, {hi:+.4f}]  "
                  f"P(>0)={frac:.3f}  {crosses}")
            entry[k] = dict(observed=float(obs), ci_low=float(lo), ci_high=float(hi),
                            p_gt_zero=frac, excludes_zero=not (lo < 0 < hi))

        null = permutation_null(rng, d, mi, ri, args.n_perm)
        obs_f1 = point['pooled_f1'][mi] - point['pooled_f1'][ri]
        pval = float((np.abs(null) >= abs(obs_f1)).mean())
        print(f"    {'permutation (pooled F1)':<22} two-sided p = {pval:.4f}")
        entry['permutation_p_pooled_f1'] = pval
        results[tags[mi]] = entry

    if args.out:
        payload = dict(
            reference=tags[ri], tags=tags, n_replicates=args.n, n_permutations=args.n_perm,
            seed=args.seed, slides=d['slides'],
            n_artifact=int((~d['is_clean']).sum()), n_clean=int(d['is_clean'].sum()),
            effective_n_kish=float(eff),
            point={k: {tags[i]: float(point[k][i]) for i in range(n_m)} for k in keys},
            intervals={k: {tags[i]: [float(ci(boot[k])[0][i]), float(ci(boot[k])[1][i])]
                           for i in range(n_m)} for k in keys},
            differences=results,
        )
        with open(args.out, 'w') as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nSaved -> {args.out}")


if __name__ == '__main__':
    main()
