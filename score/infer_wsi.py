#!/usr/bin/env python
"""
infer_wsi.py -- whole-slide inference producing error-map heatmaps.

Computes multiple timesteps in a single pass: reading a patch and VAE-encoding it are
shared costs, only noise addition and the transformer forward differ per t. N timesteps
therefore cost far less than N separate runs.

Timestep matters more than it looks. A sweep of the separation gap across t (see project
notes) found:

    basic model         Cohen's d peaks at t=950 (1.391); t=800 gives 1.243
    enhanced + f_A      Cohen's d peaks at t=650 (0.740); t=800 gives 0.001 -- i.e. NO
                        separation at all at the timestep originally used

Relative gap and Cohen's d disagree (gap peaks at t=700 for basic, d at t=950): absolute
error grows steeply with t, so a small *relative* gap can still be highly separable. Since
the post-processing thresholds operate on raw error values, d is the more relevant criterion.

Usage:
    python infer_wsi.py --model basic --timesteps 800 950
    python infer_wsi.py --model enhanced --ckpt .../step_600 --timesteps 650 550
    python infer_wsi.py --model enhanced --ckpt .../step_600 --no-fa --timesteps 700
"""

import os
import sys
import json
import time
import argparse

import numpy as np
import torch
import openslide
import torchvision.transforms.functional as TF

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

# added_cond_kwargs must contain resolution/aspect_ratio explicitly.
    # In diffusers 0.31 PixArtAlphaCombinedTimestepSizeEmbeddings.forward has the signature
    #   (timestep, resolution, aspect_ratio, batch_size, hidden_dtype)
    # with NO defaults on resolution/aspect_ratio, so they are required even though
    # PixCell sets use_additional_conditions=False and ignores them. An empty dict fails
    # ("missing 2 required positional arguments"); None fails earlier at `**added_cond_kwargs`.
    # PixCell's own pipeline passes {} and works only because the diffusers version it was
    # written against defaulted these to None.
ADDED_COND = {'resolution': None, 'aspect_ratio': None}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--model', choices=['basic', 'enhanced'], required=True)
    p.add_argument('--ckpt', default=None,
                   help='checkpoint dir. WARNING: the --model basic default points at '
                        'checkpoints/clean_split_val_v3/step_1000, an early run that '
                        'predates the current patch catalogues and produced NO result in '
                        'the paper. Every reported run passes --ckpt explicitly; the '
                        'basic condition is enhanced_version/dgx_basic/checkpoints/step_850, '
                        'trained by train_enhanced.py with --lam 0.')
    p.add_argument('--timesteps', type=int, nargs='+', required=True)
    p.add_argument('--tag', default=None, help='output dir suffix; defaults to the model name')
    p.add_argument('--no-fa', dest='use_fa', action='store_false',
                   help='bypass f_A even for an enhanced checkpoint (ablation)')
    p.set_defaults(use_fa=True)
    p.add_argument('--stride', type=int, default=C.PATCH_SIZE,
                   help='default = patch size (non-overlapping). 512 = 50%% overlap, ~4x cost '
                        'for +0.008 F1 in earlier tests -- rarely worth it')
    p.add_argument('--batch-size', type=int, default=4,
                   help='4 is safe on 40GB; 16 OOMed on 40GB previously')
    p.add_argument('--tissue-threshold', type=float, default=0.1,
                   help='0.1, not 0.01: a more permissive value lets the model score tissue '
                        'slivers inside mostly-background patches, which measurably hurt precision')
    p.add_argument('--slides', choices=['test', 'train', 'unused'], default='test')
    p.add_argument('--seed', type=int, default=42)
    return p.parse_args()


def run_slide(slide_path, pipe, vae, f_A, device, timesteps, args):
    slide = openslide.OpenSlide(slide_path)
    level, mag_err = C.find_magnification_level(slide)
    if level is None:
        slide.close()
        raise RuntimeError(f"no magnification level for {slide_path}")
    lw, lh = slide.level_dimensions[level]
    ds = slide.level_downsamples[level]
    print(f"    level {level}, mag err {mag_err*100:.2f}%")

    thumb = slide.get_thumbnail((C.THUMB_MAX_SIZE, C.THUMB_MAX_SIZE))
    tmask = C.tissue_mask_from_thumb(thumb)
    sx, sy = thumb.size[0] / lw, thumb.size[1] / lh

    xs, ys = C.clamped_positions(lw, lh, C.PATCH_SIZE, args.stride)
    positions = []
    for y in ys:
        for x in xs:
            a, b = int(x * sx), int(y * sy)
            c = max(int((x + C.PATCH_SIZE) * sx), a + 1)
            d = max(int((y + C.PATCH_SIZE) * sy), b + 1)
            if tmask[b:d, a:c].mean() >= args.tissue_threshold:
                positions.append((x, y))
    print(f"    {len(positions)} patches x {len(timesteps)} timesteps")

    mh, mw = lh // 8, lw // 8
    esum = {t: np.zeros((mh, mw), dtype=np.float32) for t in timesteps}
    ecnt = np.zeros((mh, mw), dtype=np.int32)
    emb_cache = {}

    torch.manual_seed(args.seed)
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    with torch.no_grad():
        for s in range(0, len(positions), args.batch_size):
            chunk = positions[s:s + args.batch_size]
            imgs = []
            for (x, y) in chunk:
                r = slide.read_region((int(x * ds), int(y * ds)), level,
                                      (C.PATCH_SIZE, C.PATCH_SIZE)).convert('RGB')
                imgs.append(TF.to_tensor(r) * 2.0 - 1.0)
            batch = torch.stack(imgs).to(device, dtype=torch.float32)
            b = batch.shape[0]

            z0 = vae.encode(batch).latent_dist.sample() * vae.config.scaling_factor
            if f_A is not None:
                z0 = f_A(z0)
            if b not in emb_cache:
                emb_cache[b] = pipe.get_unconditional_embedding(b).to(device)
            emb = emb_cache[b]

            for t_val in timesteps:
                noise = torch.randn_like(z0)
                tt = torch.full((b,), t_val, device=device, dtype=torch.long)
                zt = pipe.scheduler.add_noise(z0, noise, tt)
                o = pipe.transformer(hidden_states=zt, encoder_hidden_states=emb,
                                     timestep=tt, added_cond_kwargs=ADDED_COND, return_dict=True)
                pr = o.sample if hasattr(o, 'sample') else o
                eps, _ = pr.chunk(2, dim=1)
                err = ((eps - noise) ** 2).mean(dim=1).cpu().numpy()
                for i, (x, y) in enumerate(chunk):
                    by, bx = y // 8, x // 8
                    esum[t_val][by:by + 128, bx:bx + 128] += err[i]
                del noise, zt, o, pr, eps

            for (x, y) in chunk:
                by, bx = y // 8, x // 8
                ecnt[by:by + 128, bx:bx + 128] += 1
            del batch, z0

            done = s + len(chunk)
            if (s // args.batch_size + 1) % 20 == 0 or done == len(positions):
                print(f"      {done}/{len(positions)} ({time.time()-t0:.0f}s, "
                      f"peak {torch.cuda.max_memory_allocated()/1e9:.1f}GB)", flush=True)

    slide.close()
    cov = ecnt > 0
    maps = {}
    for t_val in timesteps:
        em = np.zeros((mh, mw), dtype=np.float32)
        em[cov] = esum[t_val][cov] / ecnt[cov]
        maps[t_val] = em
    return maps, cov, C.pixel_tissue_mask(thumb, (mh, mw)), len(positions)


def main():
    args = parse_args()
    device = torch.device('cuda')

    ckpt = args.ckpt
    if ckpt is None:
        if args.model != 'basic':
            sys.exit("--ckpt is required for --model enhanced")
        ckpt = os.path.join(C.DQC, "checkpoints/clean_split_val_v3/step_1000")

    tag = args.tag or args.model
    if args.model == 'enhanced' and not args.use_fa:
        tag += "_nofa"

    out_dirs = {t: os.path.join(C.DQC, f"heatmaps_dgx_{tag}_t{t}") for t in args.timesteps}
    for d in out_dirs.values():
        os.makedirs(d, exist_ok=True)

    split = C.load_split()
    slides = split[f"{args.slides}_slides"]

    print("=" * 70)
    print(f"model={args.model}  ckpt={ckpt}")
    print(f"f_A: {'APPLIED' if (args.model == 'enhanced' and args.use_fa) else 'not used'}")
    print(f"timesteps={args.timesteps}  stride={args.stride}  "
          f"tissue_threshold={args.tissue_threshold}")
    print(f"{len(slides)} {args.slides} slides")
    for t, d in out_dirs.items():
        print(f"  t={t} -> {d}")
    print("=" * 70)

    print("\nLoading model...")
    pipe, vae = C.load_pixcell(device)
    C.attach_lora(pipe, device)
    C.load_lora_weights(pipe, ckpt)
    pipe.transformer.eval()

    f_A = None
    if args.model == 'enhanced' and args.use_fa:
        f_A = C.load_f_A(ckpt, device)

    timing_path = os.path.join(list(out_dirs.values())[0], "_timing.json")
    timing = json.load(open(timing_path)) if os.path.exists(timing_path) else {}

    t_all = time.time()
    for i, fname in enumerate(slides):
        if all(os.path.exists(os.path.join(out_dirs[t], f"{fname}_{s}.npy"))
               for t in args.timesteps
               for s in ('error_map', 'coverage_mask', 'pixel_tissue_mask')):
            print(f"[{i+1}/{len(slides)}] {fname}: done, skipping")
            continue

        print(f"[{i+1}/{len(slides)}] {fname}")
        t0 = time.time()
        maps, cov, pix, npatch = run_slide(
            os.path.join(C.WSI_DIR, fname), pipe, vae, f_A, device, args.timesteps, args)
        dt = time.time() - t0

        for t_val in args.timesteps:
            d = out_dirs[t_val]
            np.save(os.path.join(d, f"{fname}_error_map.npy"), maps[t_val])
            np.save(os.path.join(d, f"{fname}_coverage_mask.npy"), cov)
            np.save(os.path.join(d, f"{fname}_pixel_tissue_mask.npy"), pix)

        timing[fname] = {'n_patches': npatch, 'seconds': dt,
                         'n_timesteps': len(args.timesteps)}
        with open(timing_path, 'w') as f:
            json.dump(timing, f, indent=2)
        print(f"    {npatch} patches, {dt:.0f}s (total {(time.time()-t_all)/60:.1f} min)",
              flush=True)

    print(f"\nDone. {(time.time()-t_all)/60:.1f} min this session.")
    if timing:
        ts = np.array([v['seconds'] for v in timing.values()])
        ps = np.array([v['n_patches'] for v in timing.values()])
        print(f"n={len(ts)} slides | per-slide {ts.mean():.0f}s +- {ts.std():.0f}s "
              f"| patches {ps.mean():.0f} +- {ps.std():.0f} | total {ts.sum()/3600:.2f}h")


if __name__ == '__main__':
    main()
