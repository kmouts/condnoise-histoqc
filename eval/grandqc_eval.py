#!/usr/bin/env python
"""
grandqc_eval.py -- score GrandQC on our test slides, in our JSON schema.

5v established that this 24-slide test set cannot support absolute comparisons: pooled F1
carries a 95% interval of about +/-0.19, and the paper's 0.750, GrandQC's published 0.754
and our 0.673 all sit inside each other's intervals. Only PAIRED differences are
resolvable here. So GrandQC cannot simply be quoted alongside our numbers -- it has to be
evaluated on the same slides, restricted the same way, and fed through the same paired
bootstrap.

That means reproducing three choices exactly:

  * the refined coverage mask, saved per slide by evaluate_wsi.py --save-masks. GrandQC is
    scored inside OUR tissue mask, not its own. 5t-A showed the mask is not type-neutral
    (it excludes 41% of out-of-focus annotation), so scoring the baseline under a
    different denominator would reintroduce that bias in the opposite direction and make
    the pairing meaningless.
  * nd_zoom(order=0) to the error-map resolution, matching build_ground_truth.
  * the same confusion counting, so the output drops straight into bootstrap_compare.py.

CLASS MAPPING
Verified against three slides of differing composition rather than assumed. On 33-4538 and
85-8070 (mixed and penmark-dominant) the correspondence is unambiguous; 62-A46P is useless
for this because out-of-focus covers 85% of its tissue and every class "matches" it.

    2 -> fold          (33-4538: covers essentially all of our fold)
    3 -> dark spot & foreign object   (no counterpart in our ground truth; see below)
    4 -> pen marking   (85-8070: 0.64 on a penmark-dominant slide)
    5 -> edge & air bubble   (33-4538: 0.81)
    6 -> out of focus  (33-4538: covers essentially all of our out-of-focus)
    0, 1, 7 -> unclassified / normal tissue / background: not artifacts

CLASS 3
GrandQC's "dark spot & foreign object" has no counterpart in our four-type ground truth,
so its predictions there can only ever be false positives. Excluding it would mean
forgiving the baseline an entire output channel; including it is the honest reading, since
GrandQC declares those pixels artifacts and the task is binary artifact detection. It is
not negligible -- 1.4M px on 62-A46P alone. Both are therefore computed: the primary
figure includes class 3, and --no-class3 produces the sensitivity analysis.

COVERAGE
GrandQC's mask set covers 21 of our 24 slides. The three missing are SP-A6QI, WC-A882 and
XM-A8RB, all frozen sections (TS1/TSA portion codes) rather than diagnostic FFPE (DX). The
GrandQC pipeline appears not to have been run on frozen sections at all. All three are
clean slides, so every artifact slide is present and only clean-slide FP rate loses power.
DX-series masks exist for two of the three cases but are DIFFERENT SLIDES -- different
tissue, different artifacts -- and are not substitutes.

USAGE
    grandqc_eval.py --masks-dir DIR --refined-dir DIR [--no-class3] --out eval.json
"""

import argparse
import json
import os
import sys
from datetime import datetime

import numpy as np
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root
from PIL import Image
from scipy.ndimage import zoom as nd_zoom

Image.MAX_IMAGE_PIXELS = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import common as C
except ImportError:
    sys.exit("ERROR: run from the directory containing common.py")

ARTIFACT_CLASSES = {2: 'fold', 3: 'dark-spot-foreign', 4: 'penmark',
                    5: 'air-bubble', 6: 'out-of-focus'}
# GrandQC class -> our type name, for per-type sensitivity. class 3 has no counterpart.
TO_OURS = {2: 'fold', 4: 'penmark', 5: 'air-bubble', 6: 'out-of-focus'}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--masks-dir',
                    default=DATA_ROOT + '/DiffusionQC/grandqc_test_slides_masks')
    ap.add_argument('--refined-dir', required=True,
                    help='directory of {slide}_refined.npy from evaluate_wsi.py '
                         '--save-masks')
    ap.add_argument('--gt-cache',
                    default=DATA_ROOT + '/DiffusionQC/dgx_shared/gt_masks')
    ap.add_argument('--no-class3', action='store_true',
                    help='exclude GrandQC class 3 (dark spot & foreign object) from the '
                         'binary artifact prediction')
    ap.add_argument('--tag', default=None)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    classes = {k: v for k, v in ARTIFACT_CLASSES.items()
               if not (args.no_class3 and k == 3)}
    tag = args.tag or ('grandqc_no_class3' if args.no_class3 else 'grandqc')

    slides = C.load_split()['test_slides']
    per_slide, missing = [], []
    tp = fp = fn = tn = 0
    atp = afp = afn = 0
    cfp = ctis = 0
    ptp = {t: 0 for t in C.TYPES}
    pgt = {t: 0 for t in C.TYPES}

    print(f"tag: {tag}   class 3 "
          f"{'EXCLUDED' if args.no_class3 else 'included'}\n")

    for i, sl in enumerate(slides):
        mp = os.path.join(args.masks_dir, f"{sl}_mask.png")
        rp = os.path.join(args.refined_dir, f"{sl}_refined.npy")
        gp = os.path.join(args.gt_cache, f"{sl}_gt.npz")

        if not os.path.exists(mp):
            missing.append(sl)
            print(f"  [{i+1}/{len(slides)}] {sl[5:28]:<26} NO GRANDQC MASK -- skipped")
            continue
        if not os.path.exists(rp):
            sys.exit(f"ERROR: no refined mask for {sl}. Run evaluate_wsi.py with "
                     f"--save-masks first.")
        if not os.path.exists(gp):
            sys.exit(f"ERROR: no cached GT for {sl}.")

        refined = np.load(rp).astype(bool)
        z = np.load(gp)
        gt = z['binary'].astype(bool)

        gq = np.array(Image.open(mp))
        zy, zx = refined.shape[0] / gq.shape[0], refined.shape[1] / gq.shape[1]
        pred = np.zeros(refined.shape, dtype=bool)
        for cls in classes:
            m = gq == cls
            if not m.any():
                continue
            pred |= nd_zoom(m.astype(np.float32), (zy, zx), order=0)[
                :refined.shape[0], :refined.shape[1]] > 0.5
        pred &= refined

        g = gt & refined
        s_tp = int((pred & g).sum())
        s_fp = int((pred & ~g).sum())
        s_fn = int((~pred & g).sum())
        s_tn = int((~pred & ~g).sum())
        gt_px = int(g.sum())
        is_clean = gt_px == 0

        pt = {}
        for t in C.TYPES:
            gtt = z[f'type_{t}'].astype(bool) & refined
            pt[t] = dict(tp=int((pred & gtt).sum()), gt_px=int(gtt.sum()))
            ptp[t] += pt[t]['tp']
            pgt[t] += pt[t]['gt_px']

        sens = s_tp / (s_tp + s_fn) if s_tp + s_fn else float('nan')
        prec = s_tp / (s_tp + s_fp) if s_tp + s_fp else float('nan')
        f1 = 2 * prec * sens / (prec + sens) if (prec + sens) else float('nan')

        per_slide.append(dict(slide=sl, sensitivity=sens, precision=prec, f1=f1,
                              gt_px=gt_px, tp=s_tp, fp=s_fp, fn=s_fn, tn=s_tn,
                              tissue_px=int(refined.sum()),
                              pred_px=int((pred & refined).sum()),
                              is_clean=is_clean, per_type=pt))

        tp += s_tp; fp += s_fp; fn += s_fn; tn += s_tn
        if is_clean:
            cfp += s_fp; ctis += int(refined.sum())
        else:
            atp += s_tp; afp += s_fp; afn += s_fn

        detail = f"clean, FP={s_fp:,}" if is_clean else f"F1={f1:.3f}"
        print(f"  [{i+1}/{len(slides)}] {sl[5:28]:<26} {detail}")

    def agg(a, b, c):
        se = a / (a + c) if a + c else float('nan')
        pr = a / (a + b) if a + b else float('nan')
        return se, pr, (2 * pr * se / (pr + se) if (pr + se) else float('nan'))

    se, pr, f1 = agg(tp, fp, fn)
    ase, apr, af1 = agg(atp, afp, afn)

    print(f"\n  slides scored: {len(per_slide)}   missing: {len(missing)}")
    for m in missing:
        print(f"    {m[:44]}")
    print(f"\n  POOLED      sens={se:.3f} prec={pr:.3f} F1={f1:.3f}")
    print(f"  artifact    sens={ase:.3f} prec={apr:.3f} F1={af1:.3f}  "
          f"(n={sum(1 for r in per_slide if not r['is_clean'])})")
    print(f"  clean FP    {100*cfp/ctis if ctis else float('nan'):.2f}%  "
          f"(n={sum(1 for r in per_slide if r['is_clean'])})")
    print("\n  per-type sensitivity")
    for t in C.TYPES:
        v = ptp[t] / pgt[t] if pgt[t] else float('nan')
        print(f"    {t:<15} {v:.3f}   ({pgt[t]:,} annotated px)")

    result = dict(
        tag=tag, method='GrandQC', timestamp=datetime.now().isoformat(timespec='seconds'),
        grandqc_classes_used=sorted(classes), class3_included=not args.no_class3,
        n_slides=len(per_slide), missing_slides=missing,
        best_hyperparameters=None,
        aggregate=dict(tp=tp, fp=fp, fn=fn, tn=tn, sensitivity=se, precision=pr, f1=f1),
        per_type={t: (ptp[t] / pgt[t] if pgt[t] else float('nan')) for t in C.TYPES},
        stratified=dict(artifact=dict(sensitivity=ase, precision=apr, f1=af1),
                        clean_fp_rate=(cfp / ctis if ctis else float('nan'))),
        per_slide=per_slide)
    with open(args.out, 'w') as fh:
        json.dump(result, fh, indent=2)
    print(f"\nSaved -> {args.out}")


if __name__ == '__main__':
    main()
