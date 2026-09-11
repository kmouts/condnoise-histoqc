#!/usr/bin/env python
"""
evaluate_wsi.py -- turn whole-slide heatmaps into pixel-level metrics.

CPU-only by design. The work is Gaussian filtering, Otsu thresholding and binary morphology
over numpy arrays; moving it to the GPU would add a dependency and a class of bugs for a few
minutes' gain. The GPU-bound half of the pipeline is `infer_wsi.py`, which produces the
heatmaps this reads.

Pipeline per slide: error map -> Gaussian smooth -> clip to [v_min, v_max] -> Otsu -> binary
closing -> binary opening -> intersect with refined coverage. Metrics are pooled over slides
rather than averaged per slide, so large slides carry proportionally more weight.

**The evaluation timestep is not incidental.** A timestep sweep found the Colab enhanced model
scored Cohen's d = 0.001 at t=800 (no separation at all) while reaching 0.74 at t=650. Whatever
`t` the heatmaps were produced at is baked into them, so check which directory you are pointing
at before drawing conclusions.

**The hyperparameter sweep must be run per model.** Absolute error scale differs between models
and timesteps, so `v_min`/`v_max` do not transfer. The grid is percentile-based to handle this.

Usage:
    python evaluate_wsi.py --heatmaps heatmaps_dgx_basic_t800
    python evaluate_wsi.py --heatmaps heatmaps_dgx_basic_t800 --tag basic
    python evaluate_wsi.py --compare eval_basic.json eval_variantA.json eval_variantB.json
"""

import os
import sys
import json
import time
import argparse
import datetime

import numpy as np
from PIL import Image
from skimage.filters import threshold_otsu
from scipy.ndimage import zoom as nd_zoom, gaussian_filter, binary_closing, binary_opening

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

Image.MAX_IMAGE_PIXELS = None   # annotation PNGs are legitimately large, not decompression bombs


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--heatmaps', default=None,
                   help='heatmap directory name under DiffusionQC/, or an absolute path')
    p.add_argument('--tag', default=None, help='label for outputs; defaults to the directory name')
    p.add_argument('--compare', nargs='+', default=None,
                   help='paths to result JSONs to tabulate side by side, then exit')
    p.add_argument('--sigma', type=float, nargs='+', default=[2.0],
                   help="Gaussian smoothing sigma. Fixed at 2.0 by default: a sweep over "
                        "{1.0,1.5,2.0,2.5,3.0,4.0} moved F1 by 0.006 from 1.5 upward "
                        "(0.640/0.642/0.642/0.643/0.646), i.e. the curve is essentially flat "
                        "with a negligible upward drift. Earlier sweeps kept selecting the "
                        "grid maximum, which looked like sigma mattered; it does not -- the "
                        "selection was effectively arbitrary. Pass multiple values to re-open.")
    p.add_argument('--morph', type=int, nargs='+', default=[5],
                   help="morphological kernel size. Fixed at 5 by default: an explicit sweep "
                        "over {3,5,7} moved pooled F1 by 0.007 (0.642 -> 0.649) and left the "
                        "per-type profile essentially unchanged (dark-spot 0.111 -> 0.108), "
                        "i.e. within noise, while tripling the grid. Pass multiple values to "
                        "re-open it.")
    # v_min is where the real sensitivity is: at fixed sigma, moving it from p40 to p60
    # changed F1 from 0.470 to 0.646 -- roughly thirty times the effect of sigma and morph
    # combined. The budget freed by pinning those two goes here.
    p.add_argument('--vmin-pct', type=float, nargs='+', default=[50, 55, 60, 65, 70])
    p.add_argument('--vmax-pct', type=float, nargs='+', default=[65, 70, 75, 80, 85])
    p.add_argument('--from-json', default=None,
                   help='reuse best_hyperparameters from an existing eval JSON instead of sweeping; makes re-runs deterministic and ~5x faster')
    p.add_argument('--save-masks', action='store_true')
    return p.parse_args()


# ---------------------------------------------------------------- metrics

def build_ground_truth(ann_path, shape, cache_dir=None, slide=None):
    """Ground truth depends only on the annotation PNG and the target shape, neither of
    which changes between runs -- so cache it. Rebuilding costs ~90s per evaluation, paid
    again for every model and timestep evaluated.

    The cached file records the shape it was built for; a mismatch (different heatmap
    resolution) rebuilds rather than silently returning masks of the wrong size."""
    if cache_dir is None or slide is None:
        return C.build_ground_truth(ann_path, shape)

    path = os.path.join(cache_dir, f"{slide}_gt.npz")
    if os.path.exists(path):
        z = np.load(path)
        if tuple(z['shape']) == tuple(shape):
            return z['binary'], {t: z[f"type_{t}"] for t in C.TYPES}
        # shape differs -> fall through and rebuild

    gt_bin, gt_type = C.build_ground_truth(ann_path, shape)
    os.makedirs(cache_dir, exist_ok=True)
    np.savez_compressed(path, binary=gt_bin, shape=np.array(shape),
                        **{f"type_{t}": gt_type[t] for t in C.TYPES})
    return gt_bin, gt_type


def postprocess(error_map, coverage, v_min, v_max, sigma, morph):
    filled = np.where(coverage, error_map, v_min)
    clipped = np.clip(gaussian_filter(filled, sigma=sigma), v_min, v_max)
    vals = clipped[coverage]
    if vals.size == 0:
        return np.zeros_like(coverage)
    thr = threshold_otsu(vals) if vals.min() != vals.max() else vals.min()
    raw = (clipped > thr) & coverage
    st = np.ones((morph, morph), dtype=bool)
    return binary_opening(binary_closing(raw, structure=st), structure=st) & coverage


def confusion(mask, gt, valid):
    tp = int((mask & gt & valid).sum())
    fp = int((mask & ~gt & valid).sum())
    fn = int((~mask & gt & valid).sum())
    tn = int((~mask & ~gt & valid).sum())
    sens = tp / (tp + fn) if tp + fn else float('nan')
    prec = tp / (tp + fp) if tp + fp else float('nan')
    f1 = 2 * prec * sens / (prec + sens) if (prec + sens) else float('nan')
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, sensitivity=sens, precision=prec, f1=f1)


def native(v):
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.integer):
        return int(v)
    return v


# ---------------------------------------------------------------- comparison mode

def do_compare(paths):
    runs = []
    for p in paths:
        with open(p) as f:
            runs.append(json.load(f))

    print(f"\n{'run':<22}{'sens':>8}{'prec':>8}{'F1':>8}   {'sigma':>6}{'morph':>6}"
          f"{'v_min':>9}{'v_max':>9}")
    print("-" * 80)
    flagged = []
    for r in runs:
        b, a = r['best_hyperparameters'], r['aggregate']
        warn = ' (!)' if r.get('grid_edge_warning') else ''
        print(f"{r['tag']:<22}{a['sensitivity']:>8.3f}{a['precision']:>8.3f}{a['f1']:>8.3f}   "
              f"{b['sigma']:>6.1f}{b['morph']:>6d}{b['v_min']:>9.4f}{b['v_max']:>9.4f}{warn}")
        if r.get('grid_edge_warning'):
            flagged.append((r['tag'], r['grid_edge_warning']))
    if flagged:
        print("\n  (!) these runs hit a grid boundary and their F1 is probably not the model's best:")
        for tag_, e in flagged:
            print(f"      {tag_}: {', '.join(e)}")

    types = list(runs[0]['per_type'].keys())
    print(f"\n{'run':<22}" + "".join(f"{t[:11]:>13}" for t in types))
    print("-" * (22 + 13 * len(types)))
    for r in runs:
        print(f"{r['tag']:<22}" + "".join(f"{r['per_type'][t]:>13.3f}" for t in types))

    print(f"\n{'run':<22}{'artifact-slide F1':>20}{'clean FP rate':>16}{'pixel-refine gain':>20}")
    print("-" * 80)
    for r in runs:
        s = r['stratified']
        ab = r['ablation']
        gain = ab['pixel_refined']['f1'] - ab['patch_level']['f1']
        print(f"{r['tag']:<22}{s['artifact_f1']:>20.3f}{s['clean_fp_rate']*100:>15.2f}%"
              f"{gain:>+20.3f}")

    print("\nReminders: metrics are pooled over slides, so large slides dominate. Per-type")
    print("sensitivity is where a balanced-sampling run would show its effect, if any --")
    print("the pooled F1 is driven by the largest category and can hide it.")


# ---------------------------------------------------------------- main

def main():
    args = parse_args()

    if args.compare:
        do_compare(args.compare)
        return

    if not args.heatmaps:
        sys.exit("provide --heatmaps or --compare")

    hm_dir = args.heatmaps if os.path.isabs(args.heatmaps) else os.path.join(C.DQC, args.heatmaps)
    if not os.path.isdir(hm_dir):
        sys.exit(f"not a directory: {hm_dir}")
    tag = args.tag or os.path.basename(hm_dir.rstrip('/'))

    out_dir = os.path.join(C.DQC, "dgx_shared/evaluations")
    os.makedirs(out_dir, exist_ok=True)

    test_slides = C.load_split()['test_slides']
    amap = C.ann_map()
    gt_cache = os.path.join(C.DQC, "dgx_shared/gt_masks")

    print("=" * 70)
    print(f"tag       : {tag}")
    print(f"heatmaps  : {hm_dir}")
    print("=" * 70)

    print("\n[1/5] Loading heatmaps and building ground truth...")
    data = {}
    t0 = time.time()
    for i, fn in enumerate(test_slides):
        paths = {k: os.path.join(hm_dir, f"{fn}_{k}.npy")
                 for k in ('error_map', 'coverage_mask', 'pixel_tissue_mask')}
        if not all(os.path.exists(p) for p in paths.values()):
            print(f"  SKIP {fn}: heatmap files missing")
            continue
        if fn not in amap:
            print(f"  SKIP {fn}: no annotation")
            continue
        em = np.load(paths['error_map'])
        cov = np.load(paths['coverage_mask'])
        pix = np.load(paths['pixel_tissue_mask'])
        gt_bin, gt_type = build_ground_truth(os.path.join(C.ANN_DIR, amap[fn]), em.shape,
                                             cache_dir=gt_cache, slide=fn)
        data[fn] = dict(error_map=em, coverage=cov, refined=cov & pix,
                        gt=gt_bin, gt_type=gt_type)
        cached = os.path.exists(os.path.join(gt_cache, f"{fn}_gt.npz"))
        print(f"  [{i+1}/{len(test_slides)}] {fn[:45]} ({time.time()-t0:.0f}s"
              f"{', gt cached' if cached else ', gt built'})")

    if not data:
        sys.exit("no slides loaded")
    print(f"\n  {len(data)}/{len(test_slides)} slides loaded")

    all_err = np.concatenate([d['error_map'][d['refined']] for d in data.values()])
    print("\n  pooled error percentiles (these set the sweep grid):")
    for p in (25, 40, 50, 60, 75, 90):
        print(f"    p{p}: {np.percentile(all_err, p):.4f}")

    print("\n[2/5] Hyperparameter sweep...")

    def pooled(v_min, v_max, sigma, morph, mask_key='refined'):
        tp = fp = fn_ = tn = 0
        for d in data.values():
            valid = d[mask_key]
            m = postprocess(d['error_map'], valid, v_min, v_max, sigma, morph)
            c = confusion(m, d['gt'], valid)
            tp += c['tp']; fp += c['fp']; fn_ += c['fn']; tn += c['tn']
        sens = tp / (tp + fn_) if tp + fn_ else float('nan')
        prec = tp / (tp + fp) if tp + fp else float('nan')
        f1 = 2 * prec * sens / (prec + sens) if (prec + sens) else float('nan')
        return dict(v_min=v_min, v_max=v_max, sigma=sigma, morph=morph,
                    tp=tp, fp=fp, fn=fn_, tn=tn, sensitivity=sens, precision=prec, f1=f1)

    if args.from_json:
        with open(args.from_json) as fh:
            hp = json.load(fh)['best_hyperparameters']
        print(f"  reusing thresholds from {os.path.basename(args.from_json)} (no sweep): "
              f"sigma={hp['sigma']} morph={hp['morph']} "
              f"v_min={hp['v_min']:.4f} v_max={hp['v_max']:.4f}")
        best = pooled(hp['v_min'], hp['v_max'], hp['sigma'], hp['morph'])
        sweep = [best]
        edge = []  # no grid in this mode, so no boundary to sit on
        print(f"  -> sens={best['sensitivity']:.3f} prec={best['precision']:.3f} "
              f"F1={best['f1']:.3f}")
    else:
        vmins = [float(np.percentile(all_err, p)) for p in args.vmin_pct]
        vmaxs = [float(np.percentile(all_err, p)) for p in args.vmax_pct]

        sweep, t0 = [], time.time()
        for s in args.sigma:
            for mo in args.morph:
                for vn in vmins:
                    for vx in vmaxs:
                        if vx <= vn:
                            continue
                        r = pooled(vn, vx, s, mo)
                        sweep.append(r)
                        print(f"  sigma={s:.1f} morph={mo} v_min={vn:.4f} v_max={vx:.4f} -> "
                              f"sens={r['sensitivity']:.3f} prec={r['precision']:.3f} "
                              f"F1={r['f1']:.3f}", flush=True)
        best = max(sweep, key=lambda r: r['f1'])
        print(f"\n  best: sigma={best['sigma']:.1f} morph={best['morph']} "
              f"v_min={best['v_min']:.4f} v_max={best['v_max']:.4f} -> F1={best['f1']:.3f} "
              f"({time.time()-t0:.0f}s, {len(sweep)} combos)")

        edge = []
        if len(args.sigma) > 1 and best['sigma'] in (min(args.sigma), max(args.sigma)):
            edge.append('sigma')
        if len(args.morph) > 1 and best['morph'] in (min(args.morph), max(args.morph)):
            edge.append('morph')
        # v_min/v_max matter far more than sigma/morph, so check them too -- an earlier version
        # omitted this and reported a t=650 result whose optimum sat on the lower corner in both,
        # i.e. the true optimum was outside the grid and the number was not characteristic.
        if best['v_min'] in (min(vmins), max(vmins)):
            which = 'lower' if best['v_min'] == min(vmins) else 'upper'
            edge.append(f'v_min ({which} bound)')
        if best['v_max'] in (min(vmaxs), max(vmaxs)):
            which = 'lower' if best['v_max'] == min(vmaxs) else 'upper'
            edge.append(f'v_max ({which} bound)')
        if edge:
            print(f"\n  *** WARNING: best {', '.join(edge)} at the grid boundary. The true optimum")
            print(f"      probably lies outside the grid, so this F1 understates the model.")
            print(f"      Re-run with --vmin-pct / --vmax-pct extended in that direction.")
            print(f"      Percentile ranges searched: v_min {args.vmin_pct}, v_max {args.vmax_pct}")

    print("\n[3/5] Per-artifact-type sensitivity...")
    per_type = {}
    for t in C.TYPES:
        tp = fn_ = 0
        for d in data.values():
            m = postprocess(d['error_map'], d['refined'], best['v_min'], best['v_max'],
                            best['sigma'], best['morph'])
            g, v = d['gt_type'][t], d['refined']
            tp += int((m & g & v).sum())
            fn_ += int((~m & g & v).sum())
        per_type[t] = tp / (tp + fn_) if tp + fn_ else float('nan')
        print(f"  {t:<15} {per_type[t]:.3f}   ({tp+fn_} annotated pixels)")

    print("\n[4/5] Stratified and ablation...")
    art = [f for f, d in data.items() if d['gt'][d['refined']].sum() > 0]
    cln = [f for f, d in data.items() if d['gt'][d['refined']].sum() == 0]

    tp = fp = fn_ = 0
    for f in art:
        d = data[f]
        m = postprocess(d['error_map'], d['refined'], best['v_min'], best['v_max'],
                        best['sigma'], best['morph'])
        c = confusion(m, d['gt'], d['refined'])
        tp += c['tp']; fp += c['fp']; fn_ += c['fn']
    a_sens = tp / (tp + fn_) if tp + fn_ else float('nan')
    a_prec = tp / (tp + fp) if tp + fp else float('nan')
    a_f1 = 2 * a_prec * a_sens / (a_prec + a_sens) if (a_prec + a_sens) else float('nan')
    print(f"  artifact slides (n={len(art)}): sens={a_sens:.3f} prec={a_prec:.3f} F1={a_f1:.3f}")

    fpc = covc = 0
    for f in cln:
        d = data[f]
        m = postprocess(d['error_map'], d['refined'], best['v_min'], best['v_max'],
                        best['sigma'], best['morph'])
        fpc += int((m & d['refined']).sum())
        covc += int(d['refined'].sum())
    fp_rate = fpc / covc if covc else float('nan')
    print(f"  clean slides (n={len(cln)}): FP rate = {fp_rate*100:.2f}%")

    abl_patch = pooled(best['v_min'], best['v_max'], best['sigma'], best['morph'],
                       mask_key='coverage')
    abl_pixel = {k: best[k] for k in ('sensitivity', 'precision', 'f1', 'fp')}
    red = (1 - abl_pixel['fp'] / abl_patch['fp']) * 100 if abl_patch['fp'] else float('nan')
    print(f"  pixel-refinement: F1 {abl_patch['f1']:.3f} -> {abl_pixel['f1']:.3f}, "
          f"FP {abl_patch['fp']:,} -> {abl_pixel['fp']:,} ({red:.1f}% reduction)")

    print("\n[5/5] Per-slide and save...")
    per_slide = []
    for f, d in data.items():
        m = postprocess(d['error_map'], d['refined'], best['v_min'], best['v_max'],
                        best['sigma'], best['morph'])
        c = confusion(m, d['gt'], d['refined'])
        pt = {}
        for t in C.TYPES:
            g = d['gt_type'][t]
            pt[t] = dict(tp=int((m & g & d['refined']).sum()),
                         gt_px=int((g & d['refined']).sum()))
        gt_px = int(d['gt'][d['refined']].sum())
        per_slide.append(dict(slide=f, sensitivity=c['sensitivity'], precision=c['precision'],
                              f1=c['f1'], gt_px=gt_px,
                              tp=c['tp'], fp=c['fp'], fn=c['fn'], tn=c['tn'],
                              tissue_px=int(d['refined'].sum()),
                              pred_px=int((m & d['refined']).sum()),
                              is_clean=bool(gt_px == 0),
                              per_type=pt))
        if args.save_masks:
            md = os.path.join(C.DQC, f"binary_masks_dgx_{tag}")
            os.makedirs(md, exist_ok=True)
            np.save(os.path.join(md, f"{f}_final_mask.npy"), m)
            # the coverage mask the metrics were computed against; component analysis
            # must apply the same restriction or it scores unreachable ground truth
            np.save(os.path.join(md, f"{f}_refined.npy"), d['refined'])

    per_slide.sort(key=lambda r: (r['f1'] if r['f1'] == r['f1'] else -1))
    print(f"  {'slide':<50}{'sens':>7}{'prec':>7}{'F1':>7}{'GT px':>10}")
    for r in per_slide:
        fmt = lambda x: f"{x:.3f}" if x == x else "  nan"
        print(f"  {r['slide'][:48]:<50}{fmt(r['sensitivity']):>7}{fmt(r['precision']):>7}"
              f"{fmt(r['f1']):>7}{r['gt_px']:>10}")

    result = dict(
        tag=tag, heatmap_dir=hm_dir, timestamp=datetime.datetime.now().isoformat(),
        n_slides=len(data), grid_edge_warning=edge if edge else None,
        searched=dict(sigma=args.sigma, morph=args.morph,
                      vmin_pct=args.vmin_pct, vmax_pct=args.vmax_pct),
        best_hyperparameters={k: native(best[k]) for k in ('sigma', 'morph', 'v_min', 'v_max')},
        aggregate={k: native(best[k]) for k in
                   ('sensitivity', 'precision', 'f1', 'tp', 'fp', 'fn', 'tn')},
        per_type={k: native(v) for k, v in per_type.items()},
        stratified=dict(n_artifact_slides=len(art), n_clean_slides=len(cln),
                        artifact_sens=native(a_sens), artifact_prec=native(a_prec),
                        artifact_f1=native(a_f1), clean_fp_rate=native(fp_rate)),
        ablation=dict(patch_level={k: native(v) for k, v in abl_patch.items()},
                      pixel_refined={k: native(v) for k, v in abl_pixel.items()}),
        per_slide=[{k: native(v) for k, v in r.items()} for r in per_slide],
        sweep=[{k: native(v) for k, v in r.items()} for r in sweep],
    )
    out = os.path.join(out_dir, f"eval_{tag}.json")
    with open(out, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved -> {out}")
    print(f"\nHEADLINE  sens={best['sensitivity']:.3f}  prec={best['precision']:.3f}  "
          f"F1={best['f1']:.3f}")


if __name__ == '__main__':
    main()
