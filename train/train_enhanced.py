#!/usr/bin/env python
"""
train_enhanced.py -- enhanced-version training (LoRA + f_A contrastive adaptor).

Reference points for judging the separation gap (clean vs artifact mean error at t*=800,
on the held-out `unused_slides` validation set):

    untrained model      +5.9%
    basic version        +9.7%  (plateau, step 650+)
    enhanced Variant A  +14.6%  (peak at step 550, declining to 12.0% by step 1000)

Variant A vs B -- the paper specifies where f_A sits at TEST time but never says how it is
wired during TRAINING. `L_enhanced = L_basic + lambda*L_con` constrains how the terms combine,
not what L_basic is computed on. Both readings are implementable:

    --fa-in-basic       (A) L_basic on f_A(z)  -- train/test consistent, but L_basic then
                            trains f_A toward "make everything easy to denoise"
    --no-fa-in-basic    (B) L_basic on raw z   -- f_A shaped only by L_con; closer to Eq. 5
                            as literally written, but introduces a train/test mismatch

Two further undocumented choices, both settled empirically (see the project notes):

  * Hinge direction. Eq. 6 reads max(0, ||.||^2 - m), which PULLS pairs together; the prose
    says the model is "penalized when the distance falls below m", which requires
    max(0, m - ||.||^2) and PUSHES them apart. The prose matches contrastive convention and
    matches what the method needs. Default here is the prose reading.
  * Margin. The paper's m=1.2 does not transfer: measured clean/artifact mean-squared latent
    distance at init is ~1.77 (median), so with the corrected sign over half of all pairs
    already exceed m=1.2 and the hinge is nearly dead. 2.7 (~1.5x median) was used for the
    successful Variant A run. Re-measure with --measure-margin if the data changes.

Also note `.mean()` rather than `.sum()` for the pair distance: the paper writes ||.||^2 (a
sum), but summing over 16*128*128 = 262,144 elements gives distances ~1e5-1e6, dwarfing
L_basic (~0.1) by six orders of magnitude and making any sane margin meaningless.

Usage:
    python train_enhanced.py --tag variantB --no-fa-in-basic --steps 1000
    python train_enhanced.py --tag variantB --resume 400 --steps 600
"""

import os
import sys
import json
import time
import random
import argparse

import numpy as np
import torch

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
    p.add_argument('--tag', required=True, help='run name; determines output directory')
    p.add_argument('--steps', type=int, default=1000)
    p.add_argument('--resume', type=int, default=0,
                   help='cumulative steps already done; loads that checkpoint and continues')
    p.add_argument('--batch-size', type=int, default=4,
                   help='4 is safe on a 40GB A100; 16 OOMed on 40GB in earlier runs')
    p.add_argument('--lr', type=float, default=1e-5)
    p.add_argument('--margin', type=float, default=2.7)
    p.add_argument('--lam', type=float, default=0.5)
    p.add_argument('--fa-in-basic', dest='fa_in_basic', action='store_true',
                   help='Variant A: L_basic computed on f_A(z)')
    p.add_argument('--no-fa-in-basic', dest='fa_in_basic', action='store_false',
                   help='Variant B: L_basic computed on raw z')
    p.set_defaults(fa_in_basic=False)
    p.add_argument('--hinge-apart', dest='hinge_apart', action='store_true',
                   help="max(0, m - d): push pairs apart (the paper's PROSE)")
    p.add_argument('--hinge-together', dest='hinge_apart', action='store_false',
                   help="max(0, d - m): pull pairs together (the paper's EQUATION as written)")
    p.set_defaults(hinge_apart=True)
    p.add_argument('--val-every', type=int, default=50)
    # Checkpoint cadence matches validation by default: in an earlier run these differed
    # (100 vs 50) and the best-scoring step_550 was measured but never saved to disk.
    p.add_argument('--ckpt-every', type=int, default=50)
    p.add_argument('--clean-subsample', type=int, default=None,
                   help='E2 arm 1: subsample the gated clean catalogue to N (seeded, '
                        'index-based on the cached latents; no re-encoding)')
    p.add_argument('--clean-tissue-threshold', type=float, default=0.5,
                   help='E2 arm 2: tissue gate for the clean catalogue; non-default '
                        'values get their own catalogue and latent cache files')
    p.add_argument('--fresh-cond', action='store_true',
                   help='E1ι arm 1: ignore --selfcond-emb content; draw a NEW '
                        'Gaussian embedding (per-token mu/sd of the real cache) for '
                        'every patch at EVERY step — no fixed pseudo-identity')
    p.add_argument('--grad-checkpoint', action='store_true',
                   help='trade activation memory for recompute (identical updates; '
                        'needed for lora-dropout, whose masks+copies on 224 modules '
                        'exceed the 40GB card)')
    p.add_argument('--lora-dropout', type=float, default=0.0,
                   help='E1ι arm 2: LoRA dropout (weight-channel perturbation probe)')
    p.add_argument('--selfcond-shuffle', action='store_true',
                   help='E1ζ: apply a fixed random permutation (seed 0) to the '
                        'patch→embedding assignment AFTER the key-equality assertion '
                        '— each patch trains under a wrong but real embedding')
    p.add_argument('--selfcond-emb', default=None,
                   help='E1\u03b2: path to a UNI2-h embedding cache dir (embeddings.pt + '
                        'manifest.json) built on train_clean.json; when given, each clean '
                        'patch trains under its own embedding instead of the learned null. '
                        'The in-training eval_error monitor deliberately stays on the null '
                        'path so separation history remains comparable across runs.')
    p.add_argument('--log-every', type=int, default=10)
    p.add_argument('--n-artifact', type=int, default=400,
                   help='artifact patches for the contrastive term (paper says 400)')
    p.add_argument('--train-min-overlap', type=float, default=0.05,
                   help="minimum annotated fraction for a patch to be an artifact TRAINING "
                        "exemplar. The paper says only '400 artifact-region patches, covering "
                        "diverse artifact types' and never specifies this, so any value is our "
                        "assumption. 0.05 reproduces the earlier Colab count of 4,965 candidates; "
                        "0.5 is symmetric with the validation threshold and has a theoretical "
                        "argument behind it -- a patch that is 95%% clean tissue asks the "
                        "contrastive loss to push clean tissue away from clean tissue, which is "
                        "noise in the objective rather than signal. Worth running both.")
    p.add_argument('--sampling', choices=['proportional', 'balanced'], default='proportional',
                   help="how to allocate the artifact budget across types. 'proportional' "
                        "follows natural frequency, which leaves fold at ~5%% (21 of 400) "
                        "even though the paper names folding as a motivating hard case. "
                        "'balanced' gives each type an equal share, capped by availability "
                        "(dark-spot has only 32 candidates, so it cannot reach a full share).")
    p.add_argument('--measure-margin', action='store_true',
                   help='report the real clean/artifact latent distance and exit')
    p.add_argument('--seed', type=int, default=42)
    return p.parse_args()


def main():
    args = parse_args()
    device = torch.device('cuda')
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)

    out_dir = os.path.join(C.DQC, f"enhanced_version/dgx_{args.tag}")
    ckpt_dir = os.path.join(out_dir, "checkpoints")
    # Catalogues and latents are shared across runs, not per-tag: both depend only on the
    # slide list, the cataloguing parameters and the (frozen) VAE -- never on the training
    # configuration. Keeping them per-tag meant re-encoding ~2,600 patches (~13 min) for
    # every new run.
    #
    # The artifact latents cover the 400 patches selected by `random.sample` after
    # `random.seed(args.seed)`; with the same seed and the same catalogue that selection is
    # identical across runs, so the cache is safe to share. A different --seed would select
    # a different 400, so the seed is part of the cache filename below.
    # Deliberately NOT under enhanced_version/: these are shared by basic and enhanced
    # training alike. L_basic is the same noise-prediction loss on the same clean patches
    # in both; the enhanced version only adds the contrastive term. Sharing the cache also
    # structurally guarantees the two are trained on identical data -- the confound that
    # invalidated the earlier Colab basic-vs-enhanced comparison was precisely that they
    # were not (see notes 5c-bis).
    cat_dir = os.path.join(C.DQC, "dgx_shared/catalogs")
    cache_dir = os.path.join(C.DQC, "dgx_shared/latents")
    for d in (ckpt_dir, cache_dir, cat_dir):
        os.makedirs(d, exist_ok=True)

    print("=" * 70)
    print(f"tag={args.tag}  variant={'A (f_A in L_basic)' if args.fa_in_basic else 'B (raw z in L_basic)'}")
    print(f"hinge={'max(0, m-d) push apart' if args.hinge_apart else 'max(0, d-m) pull together'}"
          f"  margin={args.margin}  lambda={args.lam}")
    print(f"steps={args.steps} (resume from {args.resume})  batch={args.batch_size}  lr={args.lr}")
    print(f"artifact sampling={args.sampling}  n={args.n_artifact}  "
          f"train_min_overlap={args.train_min_overlap}")
    print(f"output -> {out_dir}")
    print("=" * 70)

    split = C.load_split()
    train_slides = split['train_slides']
    unused_slides = split['unused_slides']

    print("\n[1/5] Loading PixCell...")
    pipe, vae = C.load_pixcell(device)
    C.attach_lora(pipe, device, lora_dropout=args.lora_dropout)
    if args.lora_dropout > 0:
        print(f"  E1ι arm 2: lora_dropout={args.lora_dropout}")
    if args.grad_checkpoint:
        pipe.transformer.get_base_model().enable_gradient_checkpointing()
        print("  gradient checkpointing: ON (identical updates, ~1.4x time)")
    n_lora = sum(p.numel() for p in pipe.transformer.parameters() if p.requires_grad)
    print(f"  LoRA trainable params: {n_lora:,}")

    f_A = C.ContrastiveAdaptor().to(device, dtype=torch.float32)
    test_z = torch.randn(2, 16, 32, 32, device=device)
    assert torch.allclose(f_A(test_z), test_z), "f_A must be identity at init"
    n_fa = sum(p.numel() for p in f_A.parameters())
    print(f"  f_A params: {n_fa:,} (identity at init, verified)")

    if args.resume > 0:
        rc = os.path.join(ckpt_dir, f"step_{args.resume}")
        print(f"\n  resuming from {rc}")
        C.load_lora_weights(pipe, rc)
        f_A.load_state_dict(torch.load(os.path.join(rc, "f_A.pt")))
        print("  NOTE: optimizer state is not checkpointed -- expect a brief transient")

    print("\n[2/5] Cataloguing patches...")
    thr = args.clean_tissue_threshold
    clean_cat_name = "train_clean.json" if thr == 0.5 else f"train_clean_thr{thr}.json"
    clean_patches = C.catalog_patches(train_slides, 'clean', stride=512, tissue_threshold=thr,
                                      cache_path=os.path.join(cat_dir, clean_cat_name))
    print(f"  {len(clean_patches)} clean patches from {len(train_slides)} training slides "
          f"(tissue_threshold={thr})")
    print(f"    (Colab reference: 2,187. A count several times larger usually means the "
          f"tissue gate is not being applied and background is being included.)")

    artifact_all = C.catalog_patches(
        train_slides, 'artifact', stride=512, min_overlap=args.train_min_overlap,
        cache_path=os.path.join(cat_dir, f"train_artifact_ov{args.train_min_overlap}.json"))
    ref = "  (matches the earlier Colab count of 4,965)" if args.train_min_overlap == 0.05 else ""
    print(f"  {len(artifact_all)} candidate artifact patches at "
          f"min_overlap={args.train_min_overlap}{ref}")

    # Proportional sampling across types. Note this leaves `fold` thinly represented
    # (~5% of candidates) even though the paper names folding as a motivating hard case --
    # a balanced variant is worth trying as a follow-up.
    from collections import Counter
    counts = Counter(p['artifact_type'] for p in artifact_all)
    print("  natural type distribution:")
    for t, c in counts.most_common():
        print(f"    {t:<15} {c:>5} ({c/len(artifact_all)*100:.1f}%)")

    if args.sampling == 'proportional':
        raw = {t: c / len(artifact_all) * args.n_artifact for t, c in counts.items()}
        alloc = {t: int(v) for t, v in raw.items()}
        # largest-remainder, so the allocation sums to exactly n_artifact
        for t, _ in sorted(raw.items(), key=lambda kv: kv[1] - int(kv[1]), reverse=True)[
                :args.n_artifact - sum(alloc.values())]:
            alloc[t] += 1
    else:
        # Equal share per type, redistributing whatever scarce types cannot supply.
        # Iterative because capping one type frees budget for the others: dark-spot has
        # only 32 candidates, so a naive n/5 = 80 share would silently under-fill.
        remaining, types = args.n_artifact, list(counts.keys())
        alloc = {}
        while types:
            share = remaining // len(types)
            capped = [t for t in types if counts[t] <= share]
            if not capped:
                for i, t in enumerate(types):
                    alloc[t] = share + (1 if i < remaining - share * len(types) else 0)
                break
            for t in capped:
                alloc[t] = counts[t]
                remaining -= counts[t]
                types.remove(t)

    print(f"  allocation ({args.sampling}):")
    for t, n in sorted(alloc.items(), key=lambda kv: -kv[1]):
        print(f"    {t:<15} {n:>4} of {counts[t]} available")

    by_type = {}
    for p in artifact_all:
        by_type.setdefault(p['artifact_type'], []).append(p)
    artifact_patches = []
    for t, n in alloc.items():
        pool = by_type.get(t, [])
        artifact_patches.extend(pool if len(pool) < n else random.sample(pool, n))
    print(f"  selected {len(artifact_patches)} artifact patches ({args.sampling})")

    print("\n[3/5] Caching latents...")
    selfcond_emb = None
    if args.selfcond_emb:
        import json as _json
        _man = _json.load(open(os.path.join(args.selfcond_emb, "manifest.json")))["manifest"]
        assert len(_man) == len(clean_patches), (len(_man), len(clean_patches))
        for _r, _p in zip(_man, clean_patches):
            assert (_r["slide"], _r["x"], _r["y"], _r["level"]) == \
                   (_p["slide"], _p["x"], _p["y"], _p["level"]), ("selfcond key mismatch", _r, _p)
        _blob = torch.load(os.path.join(args.selfcond_emb, "embeddings.pt"),
                           map_location="cpu", weights_only=False)
        selfcond_emb = _blob["emb"] if isinstance(_blob, dict) else _blob
        assert tuple(selfcond_emb.shape) == (len(clean_patches), 16, 1536), selfcond_emb.shape
        assert selfcond_emb.dtype == torch.float32
        print(f"  selfcond embeddings: {tuple(selfcond_emb.shape)} from {args.selfcond_emb}")
        if args.fresh_cond:
            fresh_mu = selfcond_emb.mean(dim=0, keepdim=True).to(device)
            fresh_sd = selfcond_emb.std(dim=0, unbiased=True, keepdim=True).to(device)
            fresh_gen = torch.Generator(device=device).manual_seed(0)
            print(f"  E1ι arm 1: fresh per-step Gaussian conditioning "
                  f"(mu/sd from cache, generator seed 0)")
        if args.selfcond_shuffle:
            g = torch.Generator().manual_seed(0)
            perm = torch.randperm(selfcond_emb.shape[0], generator=g)
            n_fixed = int((perm == torch.arange(len(perm))).sum())
            selfcond_emb = selfcond_emb[perm]
            print(f"  E1ζ shuffle applied: permutation seed 0, "
                  f"{n_fixed}/{len(perm)} fixed points")
    clean_pt_name = "clean.pt" if thr == 0.5 else f"clean_thr{thr}.pt"
    clean_cache = C.cache_latents(clean_patches, os.path.join(cache_dir, clean_pt_name),
                                  vae, device, batch_size=args.batch_size)
    if args.clean_subsample:
        assert selfcond_emb is None, "clean-subsample not supported with --selfcond-emb"
        n_full = clean_cache['means'].shape[0]
        assert n_full == len(clean_patches), (n_full, len(clean_patches))
        assert args.clean_subsample < n_full, (args.clean_subsample, n_full)
        g = torch.Generator().manual_seed(args.seed)
        keep = torch.randperm(n_full, generator=g)[:args.clean_subsample].sort().values
        clean_cache = {'means': clean_cache['means'][keep],
                       'stds': clean_cache['stds'][keep]}
        clean_patches = [clean_patches[i] for i in keep.tolist()]
        print(f"  clean subsample: {len(clean_patches)}/{n_full} (seed {args.seed})")
    artifact_cache = C.cache_latents(artifact_patches, os.path.join(cache_dir, f"artifact_ov{args.train_min_overlap}_{args.sampling}_n{args.n_artifact}_seed{args.seed}.pt"),
                                     vae, device, batch_size=args.batch_size)

    if args.measure_margin:
        print("\n[margin diagnostic] real clean/artifact latent distances at current f_A state:")
        with torch.no_grad():
            n = min(200, clean_cache['means'].shape[0], artifact_cache['means'].shape[0])
            ci = torch.randperm(clean_cache['means'].shape[0])[:n]
            ai = torch.randperm(artifact_cache['means'].shape[0])[:n]
            ds = []
            for s in range(0, n, 8):
                zc = C.sample_from_cache(clean_cache, ci[s:s+8], device)
                za = C.sample_from_cache(artifact_cache, ai[s:s+8], device)
                ds.append(((f_A(zc) - f_A(za)) ** 2).flatten(1).mean(dim=1).cpu())
            ds = torch.cat(ds)
        print(f"  min={ds.min():.3f} p25={ds.quantile(0.25):.3f} median={ds.median():.3f} "
              f"p75={ds.quantile(0.75):.3f} max={ds.max():.3f}")
        print(f"  suggested margin (1.5x median): {ds.median()*1.5:.1f}")
        return

    print("\n[4/5] Building validation set from held-out slides...")
    print(f"  unused_slides: {unused_slides}")
    val_clean = C.catalog_patches(unused_slides, 'clean', stride=512, verbose=False,
                                  cache_path=os.path.join(cat_dir, "val_clean.json"))
    val_artifact = C.catalog_patches(unused_slides, 'artifact', stride=512,
                                     min_overlap=0.5, verbose=False,
                                     cache_path=os.path.join(cat_dir, "val_artifact.json"))
    # min_overlap=0.5, deliberately strict. An earlier run used 0.05 here, which labelled
    # patches that were 95% clean tissue as "artifact"; the artifact set was then dominated
    # by near-clean tissue and its mean error fell BELOW the clean set's, inverting the
    # measured gap and invalidating three training runs before the cause was found.
    random.seed(args.seed)
    val_clean = random.sample(val_clean, min(96, len(val_clean)))
    print(f"  validation: {len(val_clean)} clean, {len(val_artifact)} artifact")
    if len(val_artifact) < 20:
        print("  WARNING: very few artifact validation patches -- separation will be noisy")

    val_clean_cache = C.cache_latents(val_clean, os.path.join(cache_dir, f"val_clean_seed{args.seed}.pt"),
                                      vae, device, batch_size=args.batch_size)
    val_artifact_cache = C.cache_latents(val_artifact, os.path.join(cache_dir, "val_artifact.pt"),
                                         vae, device, batch_size=args.batch_size)

    def eval_error(cache, t_star=800, bs=2):
        """Mean noise-prediction error, batched to avoid OOM on 40GB."""
        pipe.transformer.eval(); f_A.eval()
        total = count = 0
        with torch.no_grad():
            n = cache['means'].shape[0]
            for s in range(0, n, bs):
                z = cache['means'][s:s+bs].to(device)
                z = f_A(z)
                b = z.shape[0]
                noise = torch.randn_like(z)
                t = torch.full((b,), t_star, device=device, dtype=torch.long)
                zt = pipe.scheduler.add_noise(z, noise, t)
                emb = pipe.get_unconditional_embedding(b).to(device)
                o = pipe.transformer(hidden_states=zt, encoder_hidden_states=emb,
                                     timestep=t, added_cond_kwargs=ADDED_COND, return_dict=True)
                pr = o.sample if hasattr(o, 'sample') else o
                eps, _ = pr.chunk(2, dim=1)
                total += ((eps - noise) ** 2).mean().item() * b
                count += b
                del z, noise, zt, o, pr, eps
        torch.cuda.empty_cache()
        pipe.transformer.train(); f_A.train()
        return total / count

    print("\n[5/5] Training...")
    opt = torch.optim.AdamW(list(pipe.transformer.parameters()) + list(f_A.parameters()),
                            lr=args.lr)
    pipe.transformer.train(); f_A.train()

    hist_path = os.path.join(ckpt_dir, "history.json")
    if args.resume > 0 and os.path.exists(hist_path):
        with open(hist_path) as f:
            hist = json.load(f)
        print(f"  restored history: {len(hist['loss'])} steps")
    else:
        hist = {'loss': [], 'basic': [], 'con': [], 'dist': [], 'separation': []}

    n_clean, n_art = clean_cache['means'].shape[0], artifact_cache['means'].shape[0]
    cperm, aperm = torch.randperm(n_clean), torch.randperm(n_art)
    cptr = aptr = 0
    t_start = time.time()

    for local in range(1, args.steps + 1):
        step = args.resume + local

        if cptr + args.batch_size > n_clean:
            cperm, cptr = torch.randperm(n_clean), 0
        if aptr + args.batch_size > n_art:
            aperm, aptr = torch.randperm(n_art), 0
        ci = cperm[cptr:cptr + args.batch_size]; cptr += args.batch_size
        ai = aperm[aptr:aptr + args.batch_size]; aptr += args.batch_size

        z_clean_raw = C.sample_from_cache(clean_cache, ci, device)
        z_art_raw = C.sample_from_cache(artifact_cache, ai, device)

        opt.zero_grad()
        z_clean_fa = f_A(z_clean_raw)
        z_art_fa = f_A(z_art_raw)
        z_basic = z_clean_fa if args.fa_in_basic else z_clean_raw

        noise = torch.randn_like(z_basic)
        t = torch.randint(1, 1000, (z_basic.shape[0],), device=device).long()
        zt = pipe.scheduler.add_noise(z_basic, noise, t)
        if selfcond_emb is not None:
            if args.fresh_cond:
                emb = fresh_mu + fresh_sd * torch.randn(
                    (len(ci),) + tuple(selfcond_emb.shape[1:]),
                    generator=fresh_gen, device=device)
            else:
                emb = selfcond_emb[ci].to(device)
        else:
            emb = pipe.get_unconditional_embedding(z_basic.shape[0]).to(device)
        o = pipe.transformer(hidden_states=zt, encoder_hidden_states=emb,
                             timestep=t, added_cond_kwargs=ADDED_COND, return_dict=True)
        pr = o.sample if hasattr(o, 'sample') else o
        eps, _ = pr.chunk(2, dim=1)
        loss_basic = ((eps - noise) ** 2).mean()

        d = ((z_clean_fa - z_art_fa) ** 2).flatten(1).mean(dim=1)
        loss_con = (torch.clamp(args.margin - d, min=0).mean() if args.hinge_apart
                    else torch.clamp(d - args.margin, min=0).mean())

        loss = loss_basic + args.lam * loss_con
        if torch.isnan(loss) or torch.isinf(loss):
            print(f"STOP at step {step}: loss is {loss.item()}")
            break
        loss.backward()
        opt.step()

        hist['loss'].append(loss.item())
        hist['basic'].append(loss_basic.item())
        hist['con'].append(loss_con.item())
        hist['dist'].append(d.mean().item())

        if step % args.log_every == 0:
            print(f"step {step:>5}/{args.resume + args.steps}  loss={loss.item():.4f}  "
                  f"basic={loss_basic.item():.4f}  con={loss_con.item():.4f}  "
                  f"dist={d.mean().item():.3f}  {time.time()-t_start:.0f}s  "
                  f"peak={torch.cuda.max_memory_allocated()/1e9:.1f}GB", flush=True)

        if step % args.val_every == 0:
            ec = eval_error(val_clean_cache)
            ea = eval_error(val_artifact_cache)
            gap = (ea - ec) / ec * 100 if ec > 0 else float('nan')
            hist['separation'].append({'step': step, 'clean': ec, 'artifact': ea, 'gap_pct': gap})
            # No reference values printed here on purpose: the +5.9%/+9.7% figures from the
            # Colab runs were measured on a different validation set (59 artifact patches
            # under a different overlap threshold) and are not comparable to these numbers.
            # Compare against a `basic` run measured on THIS validation set instead.
            print(f"  [sep @ {step}] clean={ec:.4f} artifact={ea:.4f} gap={gap:+.1f}%",
                  flush=True)

        if step % args.ckpt_every == 0:
            cp = os.path.join(ckpt_dir, f"step_{step}")
            os.makedirs(cp, exist_ok=True)
            pipe.transformer.save_pretrained(cp)
            torch.save(f_A.state_dict(), os.path.join(cp, "f_A.pt"))
            fa_file = os.path.join(cp, "f_A.pt")
            ok = os.path.exists(fa_file) and os.path.getsize(fa_file) > 0
            print(f"  {'saved' if ok else 'WARNING: SAVE MAY HAVE FAILED at'} {cp}", flush=True)
            with open(hist_path, 'w') as f:
                json.dump(hist, f)

    with open(hist_path, 'w') as f:
        json.dump(hist, f)

    print(f"\nDone. {args.steps} steps in {(time.time()-t_start)/60:.1f} min")
    if hist['separation']:
        best = max(hist['separation'], key=lambda s: s['gap_pct'])
        print(f"Best separation: {best['gap_pct']:+.1f}% at step {best['step']}")
        print(f"Final:           {hist['separation'][-1]['gap_pct']:+.1f}% "
              f"at step {hist['separation'][-1]['step']}")
    print(f"To continue: --resume {args.resume + args.steps} --steps N")


if __name__ == '__main__':
    main()
