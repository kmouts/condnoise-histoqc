"""Tier 1 producer -- the single frozen GrandQC confirmatory evaluation.
(Gaps: frozen protocol + Tier 1 amendments of 2-3 Sep 2026.)

Phase 1 (--model basic|basic_selfcond): assemble 2x2 tile blocks per case
(filename coords, +-2px snap), score uncond at t800 (seed-0 noise), and
accumulate per-cell (=8px) mean-over-covering-blocks score canvases per
case. Masks are canvased once (shared). Resumable per case.
Phase 2 (--finalize): label-free recalibration -- percentile indices
(65,75), FROZEN, converted on the pooled valid-region score distribution --
then evaluate both models with the dev postprocess (sigma=2, morph=5,
imported from evaluate_wsi), and compute the primary endpoint: pooled
DeltaF1(basic_selfcond - basic) with a stratified paired case-level
bootstrap (20,000 replicates, seed 0). No threshold argument exists.

Class mapping (frozen): 2 fold, 6 out-of-focus, 5 air-bubble (edge caveat),
3 dark-spot-foreign (descriptive only); pooled positive = {2,3,5,6};
valid = mask != 0 AND covered. Cell grid: 64x64 per tile; mask cells by
center-pixel sampling (offset 4, stride 8) -- the /8 analogue of the dev
pipeline's order-0 zoom.

Checks: T1 audit match (33,361 blocks; 281 cases with >=1 block);
T2 jpg<->png stem sets identical per case; T3 mask values subset of 0..7;
T4 lattice snap residual <= 2 canvas px; T5 all scores finite;
T6 per-case counts re-pool to the reported aggregates.
"""
import argparse
import json
import os
import re
import time
from collections import defaultdict

import numpy as np
import torch
import torchvision.transforms.functional as TF
from PIL import Image

import common as C
import evaluate_wsi as E
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

BASE = DATA_ROOT + "/DiffusionQC/external/grandqc_test/MPP10/MPP10"
OUT_BASE = os.path.join(C.DQC, "dgx_shared/evaluations")
CKPT = {
    "basic": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic/checkpoints/step_1000",
    "basic_selfcond": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_selfcond/checkpoints/step_1000",
    "basic_freshcond": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_freshcond/checkpoints/step_1000",
}
ADDED_COND = {"resolution": None, "aspect_ratio": None}
PAT = re.compile(r"\[d=([\d.]+),x=(\d+),y=(\d+),w=(\d+),h=(\d+)\]\.(png|jpg)$")
VMIN_PCT, VMAX_PCT = 65, 75          # frozen (Gaps 2026-09-03)
SIGMA, MORPH = 2.0, 5                # dev defaults, not swept
CLASSES = {2: "fold", 6: "out-of-focus", 5: "air-bubble", 3: "dark-spot-foreign"}
POSITIVE = (2, 3, 5, 6)
CELL = 64                            # cells per tile side (512/8)


def list_cases():
    for organ in sorted(os.listdir(BASE)):
        od = os.path.join(BASE, organ)
        for case in sorted(os.listdir(od)):
            yield organ, case, os.path.join(od, case, "ALL")


def parse_case(adir):
    tiles = {}
    if not os.path.isdir(adir):
        return tiles
    for f in os.listdir(adir):
        m = PAT.search(f)
        if not m:
            continue
        x, y, w = int(m.group(2)), int(m.group(3)), int(m.group(4))
        stem = f[: f.rfind(".")]
        tiles.setdefault((x, y, w), {})[m.group(6)] = os.path.join(adir, f)
    return tiles


def grid_of(tiles):
    """Snap WSI coords to the global w-pitch lattice; return {(col,row): key}."""
    if not tiles:
        return {}, 0.0
    keys = list(tiles)
    wbar = float(np.mean([k[2] for k in keys]))
    x0 = min(k[0] for k in keys)
    y0 = min(k[1] for k in keys)
    grid = {}
    for (x, y, w) in keys:
        col = round((x - x0) / wbar)
        row = round((y - y0) / wbar)
        rx = abs(x - (x0 + col * wbar)) / (wbar / 512)
        ry = abs(y - (y0 + row * wbar)) / (wbar / 512)
        assert rx <= 2 and ry <= 2, ("T4", x, y, rx, ry)                  # T4
        grid[(col, row)] = (x, y, w)
    return grid, wbar


def blocks_of(grid):
    out = []
    for (c, r) in grid:
        if (c + 1, r) in grid and (c, r + 1) in grid and (c + 1, r + 1) in grid:
            out.append((c, r))
    return sorted(out)


def score_phase(model, run_dir, smoke, batch_size):
    device = "cuda:0"
    mdir = os.path.join(run_dir, f"cells_{model}")
    maskdir = os.path.join(run_dir, "cells_mask")
    os.makedirs(mdir, exist_ok=True)
    os.makedirs(maskdir, exist_ok=True)
    pipe, vae = C.load_pixcell(device)
    C.attach_lora(pipe, device)
    C.load_lora_weights(pipe, CKPT[model])

    cases = list(list_cases())
    if smoke:
        picked, seen = [], set()
        for organ, case, adir in cases:
            if organ not in seen and parse_case(adir):
                picked.append((organ, case, adir)); seen.add(organ)
            if len(picked) == 3:
                break
        cases = picked
    total_blocks = cases_with = 0
    t0 = time.time()
    for ci, (organ, case, adir) in enumerate(cases):
        tiles = parse_case(adir)
        if not tiles:
            continue
        for k, d in tiles.items():                                        # T2
            assert "jpg" in d and "png" in d, ("T2", organ, case, k)
        grid, _ = grid_of(tiles)
        blocks = blocks_of(grid)
        if not blocks:
            continue
        cases_with += 1
        total_blocks += len(blocks)
        out_npz = os.path.join(mdir, f"{organ}__{case}.npz")
        mask_npz = os.path.join(maskdir, f"{organ}__{case}.npz")
        if os.path.exists(out_npz) and os.path.exists(mask_npz):
            continue
        ncol = max(c for c, _ in grid) + 1
        nrow = max(r for _, r in grid) + 1
        ssum = np.zeros((nrow * CELL, ncol * CELL), np.float32)
        scnt = np.zeros_like(ssum, np.uint8)
        mcell = np.zeros_like(scnt)
        covered = np.zeros_like(ssum, bool)
        gen = torch.Generator(device=device).manual_seed(0)
        img_cache = {}

        def load_pair(cr):
            if cr not in img_cache:
                jp = np.array(Image.open(tiles[grid[cr]]["jpg"]).convert("RGB"))
                pg = np.array(Image.open(tiles[grid[cr]]["png"]))
                assert pg.max() <= 7, ("T3", organ, case, cr, int(pg.max()))  # T3
                img_cache[cr] = (jp, pg)
            return img_cache[cr]

        for s in range(0, len(blocks), batch_size):
            chunk = blocks[s:s + batch_size]
            imgs = []
            for (c, r) in chunk:
                q = [load_pair((c + dc, r + dr))[0]
                     for dr in (0, 1) for dc in (0, 1)]
                big = np.vstack([np.hstack(q[0:2]), np.hstack(q[2:4])])
                imgs.append(TF.to_tensor(big) * 2.0 - 1.0)
            batch = torch.stack(imgs).to(device, dtype=torch.float32)
            with torch.no_grad():
                dist = vae.encode(batch).latent_dist
                z = dist.mean * vae.config.scaling_factor
                noise = torch.randn(z.shape, generator=gen, device=device)
                t = torch.full((z.shape[0],), 800, device=device, dtype=torch.long)
                zt = pipe.scheduler.add_noise(z, noise, t)
                emb = pipe.get_unconditional_embedding(z.shape[0]).to(device)
                o = pipe.transformer(hidden_states=zt, encoder_hidden_states=emb,
                                     timestep=t, added_cond_kwargs=ADDED_COND,
                                     return_dict=True)
                pr = o.sample if hasattr(o, "sample") else o
                eps, _ = pr.chunk(2, dim=1)
                errm = ((eps - noise) ** 2).mean(dim=1).cpu().numpy()     # (b,128,128)
            assert np.isfinite(errm).all(), ("T5", organ, case)           # T5
            for bi, (c, r) in enumerate(chunk):
                y0, x0 = r * CELL, c * CELL
                ssum[y0:y0 + 2 * CELL, x0:x0 + 2 * CELL] += errm[bi]
                scnt[y0:y0 + 2 * CELL, x0:x0 + 2 * CELL] += 1
        for (c, r) in grid:
            _, pg = load_pair((c, r))
            mcell[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL] = pg[4::8, 4::8]
            covered[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL] = True
        covered &= scnt > 0
        smean = np.where(scnt > 0, ssum / np.maximum(scnt, 1), 0).astype(np.float32)
        np.savez_compressed(out_npz, score=smean, covered=covered)
        if not os.path.exists(mask_npz):
            np.savez_compressed(mask_npz, mask=mcell)
        if (ci + 1) % 10 == 0 or smoke:
            print(f"  [{ci+1}/{len(cases)}] {organ}/{case[:16]} "
                  f"blocks={len(blocks)} ({time.time()-t0:.0f}s)")
    print(f"phase-1 done: cases_with_blocks={cases_with} blocks={total_blocks}")
    if not smoke:
        assert (cases_with, total_blocks) == (281, 33361), ("T1", cases_with, total_blocks)
    json.dump({"model": model, "cases": cases_with, "blocks": total_blocks},
              open(os.path.join(run_dir, f"phase1_{model}.json"), "w"))


def finalize(run_dir, n_boot, ci=95.0, endpoint_models=("basic_selfcond", "basic")):
    treat, ctrl = endpoint_models
    for m in (treat, ctrl):
        assert os.path.isdir(os.path.join(run_dir, f"cells_{m}")), (
            "endpoint model cells missing", m)
    maskdir = os.path.join(run_dir, "cells_mask")
    names = sorted(os.listdir(maskdir))
    per_model = {}
    for model in (treat, ctrl):
        mdir = os.path.join(run_dir, f"cells_{model}")
        vals = []
        for nm in names:
            z = np.load(os.path.join(mdir, nm))
            m = np.load(os.path.join(maskdir, nm))["mask"]
            valid = z["covered"] & (m != 0)
            vals.append(z["score"][valid])
        pooled = np.concatenate(vals)
        vmin = float(np.percentile(pooled, VMIN_PCT))
        vmax = float(np.percentile(pooled, VMAX_PCT))
        print(f"{model}: recalibrated v_min={vmin:.5f} v_max={vmax:.5f} "
              f"(indices {VMIN_PCT}/{VMAX_PCT}, {pooled.size} valid cells)")
        per_case = []
        for nm in names:
            z = np.load(os.path.join(mdir, nm))
            m = np.load(os.path.join(maskdir, nm))["mask"]
            valid = z["covered"] & (m != 0)
            gt = np.isin(m, POSITIVE) & valid
            pred = E.postprocess(z["score"], valid, vmin, vmax, SIGMA, MORPH)
            c = E.confusion(pred, gt, valid)
            pt = {v: dict(tp=int((pred & (m == v) & valid).sum()),
                          gt=int(((m == v) & valid).sum())) for v in CLASSES}
            per_case.append(dict(case=nm[:-4], has_art=bool(gt.any()),
                                 tp=c["tp"], fp=c["fp"], fn=c["fn"], tn=c["tn"],
                                 per_type=pt))
        per_model[model] = dict(v_min=vmin, v_max=vmax, per_case=per_case)

    def pooled_f1(cases):
        tp = sum(c["tp"] for c in cases); fp = sum(c["fp"] for c in cases)
        fn = sum(c["fn"] for c in cases)
        s = tp / (tp + fn) if tp + fn else float("nan")
        p = tp / (tp + fp) if tp + fp else float("nan")
        return 2 * p * s / (p + s) if (p + s) else float("nan")

    rep = {}
    for model, d in per_model.items():
        cases = d["per_case"]
        f1 = pooled_f1(cases)
        pt = {}
        for v, name in CLASSES.items():
            num = sum(c["per_type"][v]["tp"] for c in cases)
            den = sum(c["per_type"][v]["gt"] for c in cases)
            pt[name] = dict(gt_cells=den, sens=(num / den if den else None))
        rep[model] = dict(v_min=d["v_min"], v_max=d["v_max"],
                          pooled_f1=f1, per_type=pt)
        print(f"{model}: pooled F1 = {f1:.4f}")

    ca, cb = per_model[ctrl]["per_case"], per_model[treat]["per_case"]
    assert [c["case"] for c in ca] == [c["case"] for c in cb], "case order mismatch"
    delta = pooled_f1(cb) - pooled_f1(ca)
    rng = np.random.default_rng(0)
    idx_a = [i for i, c in enumerate(ca) if c["has_art"]]
    idx_c = [i for i, c in enumerate(ca) if not c["has_art"]]
    deltas = []
    for _ in range(n_boot):
        pick = (list(rng.choice(idx_a, len(idx_a))) if idx_a else []) + \
               (list(rng.choice(idx_c, len(idx_c))) if idx_c else [])
        fa = pooled_f1([ca[i] for i in pick])
        fb = pooled_f1([cb[i] for i in pick])
        if fa == fa and fb == fb:
            deltas.append(fb - fa)
    deltas = np.array(deltas)
    lo, hi = (100 - ci) / 2, 100 - (100 - ci) / 2
    ci95 = (float(np.percentile(deltas, lo)), float(np.percentile(deltas, hi)))
    verdict = ("CONFIRMED" if ci95[0] > 0 else
               "DISCONFIRMED" if ci95[1] < 0 else "UNRESOLVED")
    rep["PRIMARY_ENDPOINT"] = dict(endpoint=f"{treat} - {ctrl}",
                                   delta_f1=delta, ci_level=ci, ci=ci95,
                                   n_boot=int(len(deltas)), seed=0,
                                   strata=dict(artifact=len(idx_a), clean=len(idx_c)),
                                   verdict=verdict)
    rep["per_case"] = {m: per_model[m]["per_case"] for m in per_model}
    with open(os.path.join(run_dir, "tier1_report.json"), "w") as f:
        json.dump(rep, f, indent=1, default=float)
    print(f"\nPRIMARY ENDPOINT: dF1={delta:+.4f} CI95=({ci95[0]:+.4f},{ci95[1]:+.4f})"
          f" -> {verdict}")
    print("wrote", os.path.join(run_dir, "tier1_report.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(CKPT))
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--bootstrap", type=int, default=20000)
    ap.add_argument("--endpoint-models", nargs=2, metavar=("TREAT", "CTRL"),
                    default=["basic_selfcond", "basic"],
                    help="the declared endpoint pair (second look: basic_freshcond basic)")
    ap.add_argument("--ci", type=float, default=95.0,
                    help="CI level for the primary endpoint (second look: 97.5)")
    ap.add_argument("--reuse-cells", nargs=2, metavar=("FROM_RUN", "MODEL"),
                    help="symlink cells_{MODEL} (and cells_mask) from an "
                         "existing run dir after verifying its phase1 audit")
    args = ap.parse_args()
    run_dir = os.path.join(OUT_BASE, args.run_name)
    os.makedirs(run_dir, exist_ok=True)
    C.log_run(run_dir, vars(args), inputs={"grandqc_mpp10": BASE})
    if args.reuse_cells:
        from_run, model = args.reuse_cells
        src_dir = os.path.join(OUT_BASE, from_run)
        ph = json.load(open(os.path.join(src_dir, f"phase1_{model}.json")))
        assert (ph["cases"], ph["blocks"]) == (281, 33361), ("reuse audit", ph)
        for d in (f"cells_{model}", "cells_mask"):
            dst = os.path.join(run_dir, d)
            if not os.path.exists(dst):
                os.symlink(os.path.join(src_dir, d), dst)
                print(f"  reused {d} <- {from_run}")
        import shutil
        shutil.copy2(os.path.join(src_dir, f"phase1_{model}.json"), run_dir)
    if args.finalize:
        finalize(run_dir, 500 if args.smoke else args.bootstrap, ci=args.ci,
                 endpoint_models=tuple(args.endpoint_models))
    else:
        assert args.model, "--model or --finalize required"
        score_phase(args.model, run_dir, args.smoke, args.batch_size)


if __name__ == "__main__":
    main()
