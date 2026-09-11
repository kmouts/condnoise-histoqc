"""E3 producer -- union-mask LOOCV (Gaps §16/E3 + design note, 1 Sep 2026).

Wrapper over evaluate_wsi's verified primitives (build_ground_truth,
postprocess) -- imported, never reimplemented. Two-pass architecture:
pass 1 computes fold-independent per-slide counts for every menu config
(masks depend on config, never on fold); the LOOCV is then pure arithmetic
over counts. sigma=2.0, morph=5 fixed (submitted defaults, not swept).

Rule U (frozen): union = M800 | {components of M650 with area < 10,000 px}.
Baseline arm: M800 alone. Both thresholds selected per-fold by pooled F1
over the 23 in-fold slides; ties broken deterministically (first index).

Pre-registered predictions (Gaps §16/E3):
 P1: the partition-honest per-fold-retuned t800 baseline comes out BELOW the
     submitted grid-max (reference 0.673 for basic_nofa); the drop is the
     value of the grid-maximum practice.
 P2: air-bubble and fold held-out sensitivity rise under U (by construction
     they cannot fall); the risk is precision, tracked as clean-slide FP px.
 P3: pooled ΔF1 small, sign uncertain; judged only as a paired difference
     with a stratified bootstrap CI (20,000 replicates, seed 0). Dark-spot
     excluded from claims (5t Finding C).

Mechanical checks:
 S1 expected slide count loaded for both timesteps, both models.
 S2 per-slide shape and refined-mask agreement across t (intersection used
    and any disagreement recorded).
 S3 menu: 25 baseline configs and 625 union pairs per model, degenerate
    (v_max <= v_min) pairs skipped and counted.
 S4 fold-menu drift: per-fold 23-slide percentiles (from 2048-bin
    histograms) vs the fixed menu absolutes; expected max drift < 1%.
 S5 full-24 grid-max baseline F1 reproduced from counts; for basic_nofa
    compared against the 0.673 reference (report, not assert).
"""
import argparse
import json
import os
import time

import numpy as np
from scipy.ndimage import label as cc_label

import common as C
import evaluate_wsi as E
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

HM = DATA_ROOT + "/DiffusionQC/heatmaps_dgx_{model}_t{t}"
OUT_BASE = os.path.join(C.DQC, "dgx_shared/evaluations")
VMIN_PCT = [50, 55, 60, 65, 70]
VMAX_PCT = [65, 70, 75, 80, 85]
SIGMA, MORPH, CUTOFF = 2.0, 5, 10000
REF_GRIDMAX = {"basic_nofa": 0.673}   # P1 reference (submitted grid-max)
NBINS = 2048


def f1_from(tp, fp, fn):
    sens = tp / (tp + fn) if tp + fn else float("nan")
    prec = tp / (tp + fp) if tp + fp else float("nan")
    return (2 * prec * sens / (prec + sens) if (prec + sens) and
            prec == prec and sens == sens else float("nan"))


def small_components(mask, cutoff):
    lab, n = cc_label(mask)
    if n == 0:
        return np.zeros_like(mask)
    sizes = np.bincount(lab.ravel())
    keep = np.flatnonzero(sizes < cutoff)
    keep = keep[keep > 0]
    return np.isin(lab, keep)


def count_mask(m, valid_px, gt_idx, type_idx):
    flat = m.reshape(-1)
    pred = int(flat.sum())
    tp = int(flat[gt_idx].sum())
    fp = pred - tp
    fn = len(gt_idx) - tp
    tn = valid_px - pred - fn
    ptp = {ty: int(flat[ix].sum()) for ty, ix in type_idx.items()}
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, per_type_tp=ptp)


def slide_counts(model, fn, menus, has650, do_union):
    """Pass 1 for one slide: counts for every baseline config and union pair."""
    d = {}
    ts = (650, 800) if has650 else (800,)
    for t in ts:
        hm = HM.format(model=model, t=t)
        em = np.load(os.path.join(hm, f"{fn}_error_map.npy"))
        cov = np.load(os.path.join(hm, f"{fn}_coverage_mask.npy"))
        pix = np.load(os.path.join(hm, f"{fn}_pixel_tissue_mask.npy"))
        d[t] = dict(em=em, refined=cov & pix)
    if has650:
        assert d[650]["em"].shape == d[800]["em"].shape, ("S2 shape", fn)
        agree = bool((d[650]["refined"] == d[800]["refined"]).all())
        valid = d[650]["refined"] & d[800]["refined"]
    else:
        agree = True
        valid = d[800]["refined"]
    valid_px = int(valid.sum())

    amap = C.ann_map()
    gt_cache = os.path.join(C.DQC, "dgx_shared/gt_masks")
    gt, gt_type = E.build_ground_truth(os.path.join(C.ANN_DIR, amap[fn]),
                                       d[800]["em"].shape,
                                       cache_dir=gt_cache, slide=fn)
    gt_idx = np.flatnonzero((gt & valid).reshape(-1))
    type_idx = {ty: np.flatnonzero((gt_type[ty] & valid).reshape(-1))
                for ty in C.TYPES}
    gt_px_type = {ty: len(ix) for ty, ix in type_idx.items()}

    hists = {}
    masks = {t: [] for t in ts}
    for t in ts:
        ev = d[t]["em"][valid]
        hists[t] = dict(edges=[float(ev.min()), float(ev.max())],
                        counts=np.histogram(ev, bins=NBINS,
                                            range=(ev.min(), ev.max()))[0].tolist())
        for (vmin, vmax) in menus[t]:
            masks[t].append(E.postprocess(d[t]["em"], valid, vmin, vmax,
                                          SIGMA, MORPH))
    base = [count_mask(m, valid_px, gt_idx, type_idx) for m in masks[800]]
    base650 = ([count_mask(m, valid_px, gt_idx, type_idx) for m in masks[650]]
               if has650 else [])
    union = []
    if do_union and has650:
        small650 = [small_components(m, CUTOFF) for m in masks[650]]
        for i8, m8 in enumerate(masks[800]):
            for i6, s6 in enumerate(small650):
                union.append(dict(i800=i8, i650=i6,
                                  **count_mask(m8 | s6, valid_px, gt_idx, type_idx)))
    return dict(slide=fn, valid_px=valid_px, refined_agree=agree,
                gt_px=len(gt_idx), gt_px_type=gt_px_type,
                is_clean=bool(len(gt_idx) == 0),
                baseline=base, baseline650=base650, union=union, hists=hists)


def pooled_f1(rows, arm, cfg):
    tp = fp = fn = 0
    for r in rows:
        c = r[arm][cfg]
        tp += c["tp"]; fp += c["fp"]; fn += c["fn"]
    return f1_from(tp, fp, fn)


def loocv(rows, arm, n_cfg):
    held = []
    for i in range(len(rows)):
        infold = rows[:i] + rows[i + 1:]
        scores = [pooled_f1(infold, arm, k) for k in range(n_cfg)]
        best = int(np.nanargmax(scores))
        held.append(dict(slide=rows[i]["slide"], cfg=best,
                         counts=rows[i][arm][best]))
    return held


def pooled_from_held(held):
    tp = sum(h["counts"]["tp"] for h in held)
    fp = sum(h["counts"]["fp"] for h in held)
    fn = sum(h["counts"]["fn"] for h in held)
    return f1_from(tp, fp, fn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="basic_nofa,variantA")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--recompute", action="store_true")
    ap.add_argument("--no-union", action="store_true",
                    help="E1delta: baseline arms only (rule U rejected in E3)")
    ap.add_argument("--bootstrap", type=int, default=20000)
    args = ap.parse_args()

    suffix = "_smoke" if args.smoke else ""
    out_dir = os.path.join(OUT_BASE, "loocv_union" + suffix)
    os.makedirs(out_dir, exist_ok=True)
    C.log_run(out_dir, vars(args),
              inputs={f"{m}_t{t}": HM.format(model=m, t=t)
                      for m in args.models.split(",") for t in (650, 800)
                      if os.path.isdir(HM.format(model=m, t=t))})

    slides = C.load_split()["test_slides"]
    if args.smoke:
        slides = slides[:4]
    vmin_pct = [50, 70] if args.smoke else VMIN_PCT
    vmax_pct = [70, 85] if args.smoke else VMAX_PCT
    n_boot = 500 if args.smoke else args.bootstrap

    full_report = {}
    for model in args.models.split(","):
        print(f"\n=== {model} ===")
        has650 = os.path.isdir(HM.format(model=model, t=650))
        do_union = not args.no_union
        ts_model = (650, 800) if has650 else (800,)
        cache = os.path.join(out_dir, f"counts_{model}.json")
        # menu: absolutes from pooled refined error, fixed once (design note)
        menus, menu_meta = {}, {}
        for t in ts_model:
            hm = HM.format(model=model, t=t)
            vals = []
            for fn in slides:
                em = np.load(os.path.join(hm, f"{fn}_error_map.npy"))
                cov = np.load(os.path.join(hm, f"{fn}_coverage_mask.npy"))
                pix = np.load(os.path.join(hm, f"{fn}_pixel_tissue_mask.npy"))
                vals.append(em[cov & pix])
            vals = np.concatenate(vals)
            vmins = [float(np.percentile(vals, p)) for p in vmin_pct]
            vmaxs = [float(np.percentile(vals, p)) for p in vmax_pct]
            pairs, skipped = [], 0
            for vmin in vmins:
                for vmax in vmaxs:
                    if vmax <= vmin:
                        skipped += 1
                        continue
                    pairs.append((vmin, vmax))
            menus[t] = pairs
            menu_meta[t] = dict(vmin_pct=vmin_pct, vmax_pct=vmax_pct,
                                vmins=vmins, vmaxs=vmaxs,
                                n_configs=len(pairs), skipped_degenerate=skipped)
            print(f"  t{t} menu: {len(pairs)} configs ({skipped} degenerate skipped)")

        if os.path.exists(cache) and not args.recompute:
            rows = json.load(open(cache))
            print(f"  counts cache loaded: {len(rows)} slides")
        else:
            rows, t0 = [], time.time()
            for i, fn in enumerate(slides):
                rows.append(slide_counts(model, fn, menus, has650, do_union))
                print(f"  [{i+1}/{len(slides)}] {fn[:40]} ({time.time()-t0:.0f}s)")
            json.dump(rows, open(cache, "w"))
        assert len(rows) == len(slides), ("S1", len(rows))                    # S1
        n_base = len(menus[800])
        n_base650 = len(menus[650]) if has650 else 0
        n_union = (len(menus[800]) * len(menus[650])) if (do_union and has650) else 0
        for r in rows:                                                        # S3
            assert len(r["baseline"]) == n_base
            assert len(r.get("baseline650", [])) == n_base650
            assert len(r["union"]) == n_union

        # S4: fold-menu drift from histograms
        drift = 0.0
        for t in ts_model:
            for i in range(len(rows)):
                cnt = np.zeros(NBINS)
                lo = min(r["hists"][str(t) if isinstance(list(rows[0]["hists"])[0], str) else t]["edges"][0] for r in rows)
                # histograms share no common edges across slides; approximate
                # fold percentiles by concatenating per-slide bin centers
                centers, weights = [], []
                for j, r in enumerate(rows):
                    if j == i:
                        continue
                    h = r["hists"][str(t)] if str(t) in r["hists"] else r["hists"][t]
                    e0, e1 = h["edges"]
                    c = np.linspace(e0, e1, NBINS + 1)
                    centers.append((c[:-1] + c[1:]) / 2)
                    weights.append(np.asarray(h["counts"], dtype=float))
                centers = np.concatenate(centers)
                weights = np.concatenate(weights)
                order = np.argsort(centers)
                cw = np.cumsum(weights[order]) / weights.sum()
                for p, ref in zip(vmin_pct + vmax_pct,
                                  menu_meta[t]["vmins"] + menu_meta[t]["vmaxs"]):
                    v = float(np.interp(p / 100, cw, centers[order]))
                    if ref != 0:
                        drift = max(drift, abs(v - ref) / abs(ref))
        print(f"  S4 max fold-menu drift: {drift*100:.3f}%")

        # S5: full-24 grid max, baseline arm
        grid = [pooled_f1(rows, "baseline", k) for k in range(n_base)]
        gridmax = float(np.nanmax(grid))
        ref = REF_GRIDMAX.get(model)
        print(f"  S5 full-set grid-max baseline F1: {gridmax:.4f}"
              + (f" (reference {ref})" if ref else ""))

        arms = {"baseline": n_base}
        if has650:
            arms["baseline650"] = n_base650
        if do_union and has650:
            arms["union"] = n_union
        held = {a: loocv(rows, a, n) for a, n in arms.items()}
        f1 = {a: pooled_from_held(h) for a, h in held.items()}

        boot = None
        if "union" in held:
            rng = np.random.default_rng(0)
            idx_clean = [i for i, r in enumerate(rows) if r["is_clean"]]
            idx_art = [i for i, r in enumerate(rows) if not r["is_clean"]]
            deltas = []
            for _ in range(n_boot):
                pick = (list(rng.choice(idx_clean, len(idx_clean))) if idx_clean else []) + \
                       (list(rng.choice(idx_art, len(idx_art))) if idx_art else [])
                fb = pooled_from_held([held["baseline"][i] for i in pick])
                fu = pooled_from_held([held["union"][i] for i in pick])
                if fb == fb and fu == fu:
                    deltas.append(fu - fb)
            deltas = np.array(deltas)
            boot = dict(n=int(len(deltas)), seed=0,
                        ci95=(float(np.percentile(deltas, 2.5)),
                              float(np.percentile(deltas, 97.5))),
                        mean=float(deltas.mean()))

        per_type = {}
        for ty in C.TYPES:
            den = sum(r["gt_px_type"][ty] for r in rows)
            per_type[ty] = dict(gt_px=den)
            for a, h in held.items():
                num = sum(x["counts"]["per_type_tp"][ty] for x in h)
                per_type[ty][f"sens_{a}"] = (num / den if den else None)
        clean_fp = {a: int(sum(x["counts"]["fp"] for x, r in zip(h, rows)
                               if r["is_clean"])) for a, h in held.items()}

        full_report[model] = dict(
            menu=menu_meta, refined_disagreements=[r["slide"] for r in rows
                                                  if not r["refined_agree"]],
            s4_max_drift=drift, s5_gridmax_baseline=gridmax, s5_reference=ref,
            loocv_pooled_f1={a: f1[a] for a in held},
            bootstrap=boot,
            per_type=per_type,
            clean_slide_fp_px=clean_fp,
            folds={a: [x["cfg"] for x in h] for a, h in held.items()},
            per_slide_heldout=[
                dict(slide=rows[i]["slide"], is_clean=rows[i]["is_clean"],
                     **{a: held[a][i]["counts"] for a in held})
                for i in range(len(rows))],
        )
        print("  LOOCV pooled F1: " + "  ".join(f"{a}={f1[a]:.4f}" for a in held))

    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(full_report, f, indent=1, default=float)
    print(f"\nwrote {os.path.join(out_dir, 'report.json')}")
    print("done")


if __name__ == "__main__":
    main()
