#!/usr/bin/env python
"""
per_slide_diagnostics.py -- why does per-slide F1 range from 0.04 to 0.95?

The pooled F1 of 0.673-0.688 hides enormous heterogeneity, and 5v showed this is not a
curiosity but the reason every confidence interval is +/-0.19: four slides hold 70% of the
ground truth and the Kish effective sample size is 6.2 of 13 artifact slides. Before any
write-up, we need to know whether the failures share a property.

Three candidate explanations, which this script separates:

  SIZE       small annotated area -> few pixels to hit, and boundary error dominates
  FRAGMENTATION  many small connected components rather than a few large ones; a method
                 tuned with Gaussian smoothing (sigma=2) and morphological closing
                 (size=5) will systematically erase small components
  TYPE       slides dominated by the types the method handles badly (dark-spot, fold)
             score badly for reasons already documented per-type in 5y/5z

They make different predictions and are distinguishable: SIZE predicts F1 correlates with
gt_px; FRAGMENTATION predicts it correlates with median component size even after
controlling for total area; TYPE predicts the residual is explained by composition.

CAVEAT ON THE GEOMETRY NUMBERS
Component analysis runs on the cached GT masks in dgx_shared/gt_masks/, which are NOT
restricted to refined tissue coverage, whereas the counts in the eval JSONs are. Component
sizes are therefore slight overestimates relative to what the metrics saw. The discrepancy
affects components straddling a tissue boundary and does not change the ranking, which is
what the correlations use.

USAGE
    per_slide_diagnostics.py --eval <counts JSONs...> [--gt-cache DIR] [--no-geometry]
                             [--out table.csv]
"""

import argparse
import json
import os
import sys

import numpy as np
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

try:
    from scipy import ndimage
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False


def spearman(x, y):
    """Rank correlation, computed directly to avoid a scipy.stats dependency.

    Rank correlation rather than Pearson because gt_px spans three orders of magnitude
    and a single 2.4M-pixel slide would otherwise determine the answer -- the same
    concentration problem that produced the wide intervals in 5v.
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 3:
        return float('nan'), 0

    def rank(a):
        order = a.argsort()
        r = np.empty(len(a), float)
        r[order] = np.arange(len(a), dtype=float)
        # average ties so repeated values do not create spurious ordering
        _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
        for i in np.where(cnt > 1)[0]:
            m = inv == i
            r[m] = r[m].mean()
        return r

    rx, ry = rank(x), rank(y)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    return (float((rx * ry).sum() / denom) if denom else float('nan')), len(x)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--eval', nargs='+', required=True)
    ap.add_argument('--gt-cache',
                    default=DATA_ROOT + '/DiffusionQC/dgx_shared/gt_masks')
    ap.add_argument('--no-geometry', action='store_true',
                    help='skip connected-component analysis')
    ap.add_argument('--out', default=None, help='write the table as CSV')
    args = ap.parse_args()

    runs = []
    for p in args.eval:
        with open(p) as fh:
            j = json.load(fh)
        if 'tp' not in j['per_slide'][0]:
            sys.exit(f"ERROR: {os.path.basename(p)} predates the counts patch.")
        runs.append(j)
    tags = [j.get('tag', os.path.basename(p)) for j, p in zip(runs, args.eval)]

    ref = {r['slide']: r for r in runs[0]['per_slide']}
    slides = sorted(ref)
    types = sorted(ref[slides[0]].get('per_type', {}).keys())

    rows = []
    for sl in slides:
        r = ref[sl]
        row = dict(slide=sl, gt_px=r['gt_px'], tissue_px=r['tissue_px'],
                   is_clean=r['is_clean'])
        row['artifact_frac'] = r['gt_px'] / r['tissue_px'] if r['tissue_px'] else float('nan')
        comp = {t: r['per_type'][t]['gt_px'] for t in types}
        tot = sum(comp.values())
        row['dominant_type'] = max(comp, key=comp.get) if tot else '-'
        row['dominant_frac'] = comp[row['dominant_type']] / tot if tot else float('nan')
        row['n_types'] = sum(1 for v in comp.values() if v > 0)
        for j, tg in zip(runs, tags):
            m = {x['slide']: x for x in j['per_slide']}[sl]
            # recompute from counts rather than reading the stored ratio, so this agrees
            # with bootstrap_compare.py by construction and behaves on clean slides
            den = 2 * m['tp'] + m['fp'] + m['fn']
            row[f'f1__{tg}'] = (2 * m['tp'] / den) if den else float('nan')
        rows.append(row)

    # ---------------------------------------------------------------- geometry
    do_geom = not args.no_geometry
    if do_geom and not HAVE_SCIPY:
        print("scipy unavailable -- skipping geometry\n")
        do_geom = False
    if do_geom and not os.path.isdir(args.gt_cache):
        print(f"gt cache not found at {args.gt_cache} -- skipping geometry\n")
        do_geom = False

    if do_geom:
        print("Connected-component analysis on cached GT masks...")
        for row in rows:
            path = os.path.join(args.gt_cache, f"{row['slide']}_gt.npz")
            if not os.path.exists(path) or row['gt_px'] == 0:
                row.update(n_comp=0, median_comp=float('nan'), max_comp=float('nan'),
                           frac_small=float('nan'))
                continue
            z = np.load(path)
            lab, n = ndimage.label(z['binary'])
            if n == 0:
                row.update(n_comp=0, median_comp=float('nan'), max_comp=float('nan'),
                           frac_small=float('nan'))
                continue
            sizes = np.bincount(lab.ravel())[1:]
            row['n_comp'] = int(n)
            row['median_comp'] = float(np.median(sizes))
            row['max_comp'] = int(sizes.max())
            # "small" = below the area a sigma=2 Gaussian plus a size-5 closing can be
            # expected to survive; ~100 px is a generous floor at this resolution
            row['frac_small'] = float((sizes < 100).sum() / n)

    # ---------------------------------------------------------------- print
    def short(s):
        s = s[5:] if s.startswith('TCGA-') else s
        return s[:19]

    art = [r for r in rows if not r['is_clean']]
    art.sort(key=lambda r: r[f'f1__{tags[0]}'])
    total_gt = sum(r['gt_px'] for r in art)

    print("\n" + "=" * 118)
    print(f"ARTIFACT SLIDES (n={len(art)}), sorted by F1 of {tags[0]}")
    hdr = (f"{'slide':<20}{'F1':>7}{'GT px':>11}{'%GT':>6}{'art frac':>9}"
           f"{'dominant type':>16}{'dom%':>6}")
    if do_geom:
        hdr += f"{'n comp':>8}{'med comp':>10}{'max comp':>11}{'%small':>8}"
    print(hdr)
    for r in art:
        line = (f"{short(r['slide']):<20}{r[f'f1__{tags[0]}']:>7.3f}{r['gt_px']:>11,}"
                f"{100*r['gt_px']/total_gt:>6.1f}{r['artifact_frac']:>9.4f}"
                f"{r['dominant_type']:>16}{100*r['dominant_frac']:>6.0f}")
        if do_geom:
            line += (f"{r['n_comp']:>8,}{r['median_comp']:>10,.0f}"
                     f"{r['max_comp']:>11,}{100*r['frac_small']:>8.1f}")
        print(line)

    # ---------------------------------------------------------------- correlations
    print("\n" + "=" * 118)
    print(f"SPEARMAN CORRELATION WITH PER-SLIDE F1  (artifact slides only, n={len(art)})")
    print("Rank correlation, not Pearson: gt_px spans three orders of magnitude.\n")
    preds = [('gt_px', 'total annotated area'),
             ('artifact_frac', 'annotated fraction of tissue'),
             ('n_types', 'number of artifact types present'),
             ('dominant_frac', 'concentration in one type')]
    if do_geom:
        preds += [('median_comp', 'median component size'),
                  ('max_comp', 'largest component'),
                  ('n_comp', 'number of components'),
                  ('frac_small', 'fraction of components <100 px')]

    for tg in tags:
        f1 = [r[f'f1__{tg}'] for r in art]
        print(f"  {tg}")
        for key, desc in preds:
            rho, n = spearman([r.get(key, np.nan) for r in art], f1)
            bar = ''
            if np.isfinite(rho):
                # |rho| > 0.55 at n=13 is roughly the 5% two-sided threshold
                bar = '  <-- strong' if abs(rho) > 0.55 else ''
            print(f"    {desc:<36} rho = {rho:+.3f}{bar}")
        print()

    # ---------------------------------------------------------------- per type
    print("=" * 118)
    print("PER-TYPE COMPOSITION BY SLIDE (GT px)")
    print(f"{'slide':<20}" + ''.join(f"{t[:11]:>13}" for t in types))
    for r in art:
        m = {x['slide']: x for x in runs[0]['per_slide']}[r['slide']]
        print(f"{short(r['slide']):<20}" +
              ''.join(f"{m['per_type'][t]['gt_px']:>13,}" for t in types))
    print(f"{'TOTAL':<20}" + ''.join(
        f"{sum({x['slide']: x for x in runs[0]['per_slide']}[r['slide']]['per_type'][t]['gt_px'] for r in art):>13,}"
        for t in types))

    # how concentrated is each type -- the air-bubble problem from 5v, generalised
    print("\nSlides holding >50% of each type's ground truth:")
    by_slide = {x['slide']: x for x in runs[0]['per_slide']}
    for t in types:
        vals = sorted(((by_slide[r['slide']]['per_type'][t]['gt_px'], r['slide'])
                       for r in art), reverse=True)
        tot = sum(v for v, _ in vals)
        if tot == 0:
            continue
        cum, names = 0, []
        for v, s in vals:
            cum += v
            names.append(f"{short(s)[:12]} ({100*v/tot:.0f}%)")
            if cum / tot > 0.5:
                break
        flag = '   <-- effectively single-slide' if len(names) == 1 else ''
        print(f"  {t:<15} {', '.join(names)}{flag}")

    if args.out:
        keys = list(rows[0].keys())
        with open(args.out, 'w') as fh:
            fh.write(','.join(keys) + '\n')
            for r in rows:
                fh.write(','.join(str(r.get(k, '')) for k in keys) + '\n')
        print(f"\nSaved -> {args.out}")


if __name__ == '__main__':
    main()
