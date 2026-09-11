"""E1 producer -- self-conditioned scoring diagnostic (Gaps §16/E1).

Scoring follows eval_checkpoints.mean_error line-for-line (means, add_noise,
uncond path), except noise is deterministic and shared: the generator is
re-seeded per (arm, t), so every patch sees the identical eps in both
conditions and in every arm. No f_A in any arm (pure conditioning question).

Pre-registered predictions (frozen in Gaps §16/E1 before this file existed):
 P1 (control): paired per-patch delta-error != 0 essentially everywhere.
 P2 (hypothesis): self-conditioning lowers clean error more than artifact
    error, so gap and Cohen's d increase at the model's informative timesteps.
 P3 (discriminator): if LoRA-null mismatch dominates, LoRA arms show dd < 0
    while the base (no-LoRA) arm shows dd > 0.
 Decision rule (frozen): advance to step (beta) only if dd >= +0.2 for at
 least one (arm, t) AND neither admissible type (air-bubble, out-of-focus)
 drops its d by more than 0.1. Penmark (n=1) excluded. AUROC is the
 pre-registered secondary metric (amendment, 1 Sep 2026); the decision rule
 remains on dd.

Mechanical checks (stop-and-report on failure):
 S1 embeddings tensor is (1427,16,1536) FP32.
 S2 keyed-latent manifest rows equal embedding manifest rows (slide,x,y,level,
    split, artifact_type), both splits.
 S3 get_unconditional_embedding(b) is (b,16,1536).
 S4 eps after chunk matches zt shape.
 S5 every recorded error is finite.
"""
import argparse
import json
import os

import numpy as np
import torch

import common as C
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

LAT = DATA_ROOT + "/DiffusionQC/dgx_shared/latents"
KEYED = os.path.join(LAT, "val_latents_keyed")
EMB_DIR = os.path.join(LAT, "uni2h_emb_val1427_rev-d517a8dd")
CKPT = {
    "basic": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic/checkpoints/step_1000",
    "variantA": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_variantA/checkpoints/step_1000",
    "basic_selfcond": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_selfcond/checkpoints/step_1000",
    "variantA_seed7": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_variantA_seed7/checkpoints/step_1000",
    "basic_selfcond_seed7": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_selfcond_seed7/checkpoints/step_1000",
    "basic_selfcond_seed123": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_selfcond_seed123/checkpoints/step_1000",
    "e2_sub546": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_e2_sub546/checkpoints/step_1000",
    "e2_sub1092": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_e2_sub1092/checkpoints/step_1000",
    "e2_thr025": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_e2_thr025/checkpoints/step_1000",
    "e2_thr010": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_e2_thr010/checkpoints/step_1000",
    "e2_thr000": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_e2_thr000/checkpoints/step_1000",
    "basic_shufcond": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_shufcond/checkpoints/step_1000",
    "basic_synthcond": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_synthcond/checkpoints/step_1000",
    "basic_synthcond_seed7": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_synthcond_seed7/checkpoints/step_1000",
    "basic_synthcond_draw1": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_synthcond_draw1/checkpoints/step_1000",
    "basic_synthcond_var2": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_synthcond_var2/checkpoints/step_1000",
    "basic_synthcond_var05": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_synthcond_var05/checkpoints/step_1000",
    "basic_synthcond_var4": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_synthcond_var4/checkpoints/step_1000",
    "basic_freshcond": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_freshcond/checkpoints/step_1000",
    "basic_dropout01": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_dropout01/checkpoints/step_1000",
    "basic_freshcond_seed7": DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic_freshcond_seed7/checkpoints/step_1000",
}
OUT_BASE = DATA_ROOT + "/DiffusionQC/dgx_shared/evaluations"
ADDED_COND = {"resolution": None, "aspect_ratio": None}
ADMISSIBLE = ("air-bubble", "out-of-focus")


def key_of(r):
    return (r["slide"], r["x"], r["y"], r["level"], r.get("split"),
            r.get("artifact_type"))


def cohens_d(a, c):
    na, nc = len(a), len(c)
    sp = np.sqrt(((na - 1) * a.std(ddof=1) ** 2 + (nc - 1) * c.std(ddof=1) ** 2)
                 / (na + nc - 2))
    return float((a.mean() - c.mean()) / sp)


def auroc(a, c):
    x = np.concatenate([a, c])
    r = np.empty(len(x))
    order = np.argsort(x, kind="mergesort")
    r[order] = np.arange(1, len(x) + 1)
    u = r[: len(a)].sum() - len(a) * (len(a) + 1) / 2
    return float(u / (len(a) * len(c)))


def metrics(err, split, types):
    clean = err[split == "clean"]
    art = err[split == "artifact"]
    out = {
        "gap_pct": float((art.mean() - clean.mean()) / clean.mean() * 100),
        "cohens_d": cohens_d(art, clean),
        "auroc": auroc(art, clean),
    }
    for ty in ADMISSIBLE:
        sub = err[types == ty]
        out[f"d_{ty}"] = cohens_d(sub, clean)
        out[f"auroc_{ty}"] = auroc(sub, clean)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--batch-size", type=int, default=10)
    ap.add_argument("--noise-seed", type=int, default=0)
    ap.add_argument("--arms", default=None,
                    help="comma list; default: base,basic,variantA (the E1 set)")
    ap.add_argument("--run-name", default="selfcond_diag",
                    help="output subdirectory under evaluations/")
    ap.add_argument("--conditions", default="un,sc",
                    help="comma subset of un,sc; E1γ R1 uses un only")
    ap.add_argument("--ts", default=None,
                    help="comma list of timesteps; default 500,650,800 (E2 uses 650,700,800,950)")
    args = ap.parse_args()

    if args.smoke:
        arms = ["basic"]
    elif args.arms:
        arms = args.arms.split(",")
        assert all(a == "base" or a in CKPT for a in arms), arms
    else:
        arms = ["base", "basic", "variantA"]
    if args.smoke:
        ts = [800]
    elif args.ts:
        ts = [int(x) for x in args.ts.split(",")]
        assert all(0 < t < 1000 for t in ts), ts
    else:
        ts = [500, 650, 800]
    conditions = args.conditions.split(",")
    assert conditions and all(c in ("un", "sc") for c in conditions), conditions
    out_dir = os.path.join(OUT_BASE, args.run_name + ("_smoke" if args.smoke else ""))
    os.makedirs(out_dir, exist_ok=True)
    device = "cuda:0"

    kman = json.load(open(os.path.join(KEYED, "manifest.json")))
    rows = kman["clean_rows"] + kman["artifact_rows"]
    eman = json.load(open(os.path.join(EMB_DIR, "manifest.json")))["manifest"]
    emb_obj = torch.load(os.path.join(EMB_DIR, "embeddings.pt"), map_location="cpu")
    emb = emb_obj if torch.is_tensor(emb_obj) else next(
        v for v in emb_obj.values() if torch.is_tensor(v) and v.dim() == 3)
    assert tuple(emb.shape) == (1427, 16, 1536) and emb.dtype == torch.float32, \
        ("S1", tuple(emb.shape), emb.dtype)                             # S1
    assert len(rows) == len(eman) == 1427
    for a, b in zip(rows, eman):                                        # S2
        assert key_of(a) == key_of(b), ("S2", a, b)

    lc = torch.load(os.path.join(KEYED, "val_clean_full.pt"), map_location="cpu")
    la = torch.load(os.path.join(KEYED, "val_artifact_full.pt"), map_location="cpu")
    means = torch.cat([lc["means"], la["means"]])
    split = np.array([r["split"] for r in rows])
    types = np.array([str(r["artifact_type"]) for r in rows])

    if args.smoke:
        idx = list(range(8)) + list(range(1167, 1175))
        means, emb = means[idx], emb[idx]
        split, types = split[idx], types[idx]

    n = means.shape[0]
    print(f"{n} patches | arms {arms} | t {ts}")

    pipe, _vae = C.load_pixcell(device)
    lora_on = False
    errors = {}

    for arm in arms:
        if arm != "base" and not lora_on:
            C.attach_lora(pipe, device)
            lora_on = True
        if arm != "base":
            C.load_lora_weights(pipe, CKPT[arm])
        for t_val in ts:
            gen = torch.Generator(device=device).manual_seed(args.noise_seed)
            e_un = torch.empty(n)
            e_sc = torch.empty(n)
            with torch.no_grad():
                for s in range(0, n, args.batch_size):
                    z = means[s:s + args.batch_size].to(device)
                    b = z.shape[0]
                    noise = torch.randn(z.shape, generator=gen, device=device)
                    t = torch.full((b,), t_val, device=device, dtype=torch.long)
                    zt = pipe.scheduler.add_noise(z, noise, t)
                    un = pipe.get_unconditional_embedding(b).to(device)
                    assert tuple(un.shape) == (b, 16, 1536), ("S3", un.shape)  # S3
                    sc = emb[s:s + b].to(device)
                    for tag, cond, sink in [(g, c, k) for g, c, k in
                                            (("un", un, e_un), ("sc", sc, e_sc))
                                            if g in conditions]:
                        o = pipe.transformer(hidden_states=zt,
                                             encoder_hidden_states=cond,
                                             timestep=t,
                                             added_cond_kwargs=ADDED_COND,
                                             return_dict=True)
                        pr = o.sample if hasattr(o, "sample") else o
                        eps, _ = pr.chunk(2, dim=1)
                        assert eps.shape == zt.shape, ("S4", eps.shape)        # S4
                        sink[s:s + b] = ((eps - noise) ** 2).mean(
                            dim=[1, 2, 3]).cpu()
            for tag, sink in [(g, k) for g, k in (("un", e_un), ("sc", e_sc))
                              if g in conditions]:
                assert torch.isfinite(sink).all(), ("S5", arm, t_val, tag)     # S5
                errors[f"{arm}_t{t_val}_{tag}"] = sink
            if "un" in conditions and "sc" in conditions:
                paired_nonzero = int(((e_sc - e_un) != 0).sum())
                print(f"{arm} t={t_val}: paired delta != 0 on {paired_nonzero}/{n} (P1)")

    torch.save({"rows_smoke_idx": idx if args.smoke else None,
                "noise_seed": args.noise_seed,
                "errors": errors}, os.path.join(out_dir, "errors.pt"))

    report = {}
    for key, sink in errors.items():
        report[key] = metrics(sink.numpy(), split, types)
    for arm in arms:
        for t_val in ts:
            if not ("un" in conditions and "sc" in conditions):
                continue
            m_un = report[f"{arm}_t{t_val}_un"]
            m_sc = report[f"{arm}_t{t_val}_sc"]
            report[f"{arm}_t{t_val}_DELTA"] = {
                k: round(m_sc[k] - m_un[k], 4) for k in m_un}
    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(report, indent=1))

    C.log_run(out_dir, vars(args), inputs={
        "keyed_latents_manifest": os.path.join(KEYED, "manifest.json"),
        "embeddings": os.path.join(EMB_DIR, "embeddings.pt"),
        "basic_ckpt": CKPT["basic"],
        "variantA_ckpt": CKPT["variantA"],
    })
    print("done")


if __name__ == "__main__":
    main()
