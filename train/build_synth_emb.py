"""E1eta -- build the synthetic conditioning cache (Gaps §16/E1eta, 3 Sep 2026).

Per-token-position diagonal Gaussian: for each of the 16 token positions,
mean and std over the 2,185 real UNI2-h embeddings; 2,185 draws, sampling
seed 0. Everything else in the cache object (keys, manifest, metadata) is
copied verbatim so the trainer's key-equality join assertion runs against
the unchanged manifest.

Checks (stop-and-report):
 Y1 source structure recognized (tensor located, (2185,16,1536) fp32).
 Y2 keys/metadata copied byte-identical (same object minus the tensor).
 Y3 synthetic per-position mean within 3 sampling-SEs of the real mean.
 Y4 (amended after first run, 3 Sep 2026): per-dimension std ratios --
    99.5% of the 16x1536 dimensions within [0.95, 1.05] and all within
    [0.90, 1.10]. The original all-dims-in-±5% bound ignored multiplicity:
    with 24,576 simultaneous std estimates at SE ≈ 1.5%, the expected
    extreme is ~4.5σ ≈ ±6.7%; the first run's extremes (−6.0%, +6.4%) were
    textbook sampling behavior, not a data problem.
 Y5 all finite; dtype fp32; same shape.
Descriptive (printed, not gated): token-norm distribution real vs synthetic
-- diagonal Gaussian does not preserve norms; recorded, per the
simplest-hypothesis-first design.
"""
import os

import torch

import argparse
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

SRC = DATA_ROOT + "/DiffusionQC/dgx_shared/latents/uni2h_emb_train2185_rev-d517a8dd"
_ap = argparse.ArgumentParser()
_ap.add_argument("--draw-seed", type=int, default=0)
_ap.add_argument("--var-scale", type=float, default=1.0)
ARGS = _ap.parse_args()
_tag = f"uni2h_emb_synth2185_gauss_seed{ARGS.draw_seed}" + (
    "" if ARGS.var_scale == 1.0 else f"_var{ARGS.var_scale:g}")
DST = os.path.join(DATA_ROOT + "/DiffusionQC/dgx_shared/latents", _tag)


def locate(path):
    if os.path.isdir(path):
        cands = [f for f in os.listdir(path) if f.endswith((".pt", ".pth"))]
        assert len(cands) == 1, ("Y1: expected one tensor file in dir", cands)
        return os.path.join(path, cands[0]), True
    return path, False


def main():
    src_file, is_dir = locate(SRC)
    obj = torch.load(src_file, map_location="cpu")
    if torch.is_tensor(obj):
        emb, container, key = obj, None, None
    else:
        assert isinstance(obj, dict), ("Y1: unexpected object", type(obj))
        tkeys = [k for k, v in obj.items()
                 if torch.is_tensor(v) and v.dim() == 3]
        assert len(tkeys) == 1, ("Y1: expected one 3-d tensor entry", tkeys)
        key = tkeys[0]
        emb, container = obj[key], obj
    assert tuple(emb.shape) == (2185, 16, 1536), ("Y1", tuple(emb.shape))
    assert emb.dtype == torch.float32, ("Y1", emb.dtype)

    mu = emb.mean(dim=0, keepdim=True)               # (1,16,1536)
    sd = emb.std(dim=0, unbiased=True, keepdim=True)
    g = torch.Generator().manual_seed(ARGS.draw_seed)
    synth = mu + ARGS.var_scale * sd * torch.randn(emb.shape, generator=g)
    print(f"draw seed {ARGS.draw_seed}, var scale {ARGS.var_scale}")
    synth = synth.to(torch.float32)

    # Y3 amended with E1θ (3 Sep, second builder run): the synthetic mean's
    # sampling SE scales with the applied std multiplier; the original fixed
    # 3*se bound was written for var_scale=1 (at x2 it silently became 1.5σ).
    se = ARGS.var_scale * sd / (emb.shape[0] ** 0.5)
    dmu = (synth.mean(dim=0, keepdim=True) - mu).abs()
    assert (dmu <= 3 * se + 1e-8).float().mean() > 0.995, "Y3"            # Y3
    ratio = synth.std(dim=0, unbiased=True, keepdim=True) / (ARGS.var_scale * sd + 1e-12)
    frac_in = ((ratio > 0.95) & (ratio < 1.05)).float().mean()
    assert frac_in > 0.995, ("Y4 population", float(frac_in))
    assert ratio.min() > 0.90 and ratio.max() < 1.10, ("Y4 hard", float(ratio.min()),
                                                       float(ratio.max()))
    print(f"Y4: {float(frac_in)*100:.2f}% of dims in ±5%; "
          f"extremes ({float(ratio.min()):.4f}, {float(ratio.max()):.4f}) in ±10%")
    assert torch.isfinite(synth).all(), "Y5"                              # Y5

    rn = emb.norm(dim=-1).mean(dim=0)                # (16,) mean token norms
    sn = synth.norm(dim=-1).mean(dim=0)
    print("token-norm means real:     ", [round(float(x), 1) for x in rn])
    print("token-norm means synthetic:", [round(float(x), 1) for x in sn])
    print(f"norm ratio synth/real: {float((sn/rn).mean()):.4f} "
          "(diagonal Gaussian does not preserve norms; recorded)")

    if container is None:
        out_obj = synth
    else:
        out_obj = {k: (synth if k == key else v) for k, v in container.items()}  # Y2
    if is_dir:
        os.makedirs(DST, exist_ok=True)
        out_file = os.path.join(DST, os.path.basename(src_file))
    else:
        out_file = DST
    torch.save(out_obj, out_file)
    if is_dir:                                       # inherit sidecar files
        import shutil
        for f in os.listdir(SRC):
            if f != os.path.basename(src_file):
                shutil.copy2(os.path.join(SRC, f), os.path.join(DST, f))
                print("  copied sidecar:", f)
    src_mb = os.path.getsize(src_file) / 2**20
    dst_mb = os.path.getsize(out_file) / 2**20
    print(f"wrote {out_file}  ({dst_mb:.1f} MiB vs source {src_mb:.1f} MiB)")
    print("Y1-Y5 PASS")


if __name__ == "__main__":
    main()
