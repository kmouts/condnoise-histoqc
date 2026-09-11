"""Synthetic dry run of the PixCell DiT conditional path under a LoRA checkpoint.

Step 2 of the PixCell self-conditioned scoring track, deferred from the 31 August
recon (section 5, "Dry-run disposition: not run") because UNI2-h was then absent.
It is now present, but this script deliberately does NOT use it: the point is to
check the *DiT side* of the contract in isolation, with a random conditioning
tensor standing in for a real embedding.

Nothing here touches a dataset patch, a slide, or a ground-truth mask. No error is
computed against anything, no clean/artifact split exists in this file, and no
effect size is produced. The self-conditioned diagnostic itself is a
pre-registered experiment that has not been pre-registered yet; this is only the
mechanical check that the wiring accepts a (B,16,1536) condition.

PRE-REGISTERED PREDICTIONS (written before the run):
  P1. pipe.get_unconditional_embedding(B) returns (B,16,1536) float32 -- the shape
      a UNI2-h cache must match, per recon section 1.
  P2. Substituting a random float32 (B,16,1536) tensor for that embedding runs the
      transformer to completion with no shape error.
  P3. The latent side is unchanged by conditioning: input (B,16,128,128) gives an
      output whose channel count is 2x the input (eps and variance concatenated,
      as infer_wsi.py's `pr.chunk(2, dim=1)` assumes), spatial dims preserved,
      dtype float32.
  P4. Wiring check, not a measurement: two *different* random conditions produce
      different outputs from otherwise identical inputs. If they were identical the
      condition would be silently dropped and every downstream self-conditioned
      number would be the unconditional one. Reported as a boolean plus a max-abs
      delta on synthetic noise; it is not an error, a score, or a comparison of
      anything real.
  P5. A wrong token count (B,8,1536) is rejected rather than silently accepted.
  Any failure is a stop-and-report condition.
"""
import json
import os
import sys

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
from common import log_run
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

CKPT = DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_basic/checkpoints/step_1000"
OUT_DIR = DATA_ROOT + "/DiffusionQC/provenance/dryrun_dgx_basic_step1000_B2"
OUT_JSON = os.path.join(OUT_DIR, "pixcell_cond_dryrun.json")

ADDED_COND = {'resolution': None, 'aspect_ratio': None}
BATCH = 2
TIMESTEP = 800          # the evaluation timestep in use; irrelevant to shapes
SEED = 0
LATENT_HW = C.PATCH_SIZE // 8   # 1024 -> 128, the VAE's spatial downsampling


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    log_run(OUT_DIR, {"checkpoint": CKPT, "batch": BATCH, "timestep": TIMESTEP,
                      "seed": SEED}, inputs={"lora_checkpoint": CKPT})

    device = "cuda:0"
    torch.manual_seed(SEED)

    pipe, vae = C.load_pixcell(device, dtype=torch.float32)
    C.attach_lora(pipe, device)
    C.load_lora_weights(pipe, CKPT)

    cfg = pipe.transformer.config if hasattr(pipe.transformer, "config") else \
        pipe.transformer.base_model.model.config
    n_tokens = cfg.caption_num_tokens
    d_model = cfg.caption_channels
    latent_ch = vae.config.latent_channels

    checks, notes = {}, {}

    # --- P1: the shape a UNI2-h cache has to match -------------------------------
    uncond = pipe.get_unconditional_embedding(BATCH).to(device)
    notes["uncond_shape"] = list(uncond.shape)
    notes["uncond_dtype"] = str(uncond.dtype)
    notes["caption_num_tokens"] = n_tokens
    notes["caption_channels"] = d_model
    notes["latent_channels"] = latent_ch
    checks["P1_uncond_shape"] = list(uncond.shape) == [BATCH, 16, 1536]
    checks["P1_uncond_dtype_fp32"] = uncond.dtype == torch.float32
    checks["P1_config_tokens_16"] = n_tokens == 16
    checks["P1_config_channels_1536"] = d_model == 1536

    # --- synthetic inputs: pure noise, no slide, no dataset ----------------------
    zt = torch.randn(BATCH, latent_ch, LATENT_HW, LATENT_HW,
                     device=device, dtype=torch.float32)
    tt = torch.full((BATCH,), TIMESTEP, device=device, dtype=torch.long)
    cond_a = torch.randn(BATCH, n_tokens, d_model, device=device, dtype=torch.float32)
    cond_b = torch.randn(BATCH, n_tokens, d_model, device=device, dtype=torch.float32)

    def forward(cond):
        with torch.no_grad():
            o = pipe.transformer(hidden_states=zt, encoder_hidden_states=cond,
                                 timestep=tt, added_cond_kwargs=ADDED_COND,
                                 return_dict=True)
        return o.sample if hasattr(o, "sample") else o

    # --- P2 / P3: the conditional path runs, and the latent side is unchanged -----
    out_a = forward(cond_a)
    notes["synthetic_cond_shape"] = list(cond_a.shape)
    notes["latent_in_shape"] = list(zt.shape)
    notes["transformer_out_shape"] = list(out_a.shape)
    notes["transformer_out_dtype"] = str(out_a.dtype)
    checks["P2_conditional_forward_ran"] = True
    checks["P3_out_batch_preserved"] = out_a.shape[0] == BATCH
    checks["P3_out_channels_doubled"] = out_a.shape[1] == 2 * latent_ch
    checks["P3_out_spatial_preserved"] = list(out_a.shape[2:]) == [LATENT_HW, LATENT_HW]
    checks["P3_out_dtype_fp32"] = out_a.dtype == torch.float32
    checks["P3_out_finite"] = bool(torch.isfinite(out_a).all())

    eps, _var = out_a.chunk(2, dim=1)
    notes["eps_shape_after_chunk"] = list(eps.shape)
    checks["P3_chunk_matches_latent"] = list(eps.shape) == list(zt.shape)

    # --- P4: wiring check. Not a measurement of anything. ------------------------
    out_b = forward(cond_b)
    delta = (out_a - out_b).abs().max().item()
    notes["max_abs_delta_between_two_random_conditions"] = delta
    notes["P4_disclaimer"] = ("synthetic-vs-synthetic on random tensors; establishes "
                              "only that the condition reaches cross-attention. Not an "
                              "error, not a score, not a clean/artifact comparison.")
    checks["P4_condition_affects_output"] = delta > 0.0

    # --- P5: a wrong token count must be rejected --------------------------------
    bad = torch.randn(BATCH, 8, d_model, device=device, dtype=torch.float32)
    try:
        forward(bad)
        checks["P5_wrong_token_count_rejected"] = False
        notes["P5_outcome"] = "ACCEPTED -- the wrapper did not validate token count"
    except Exception as exc:
        checks["P5_wrong_token_count_rejected"] = True
        notes["P5_outcome"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    notes["peak_vram_bytes"] = torch.cuda.max_memory_allocated(device)

    report = {
        "step": "2 -- synthetic conditional-path dry run (deferred from recon section 5)",
        "uses_uni2h": False,
        "uses_dataset_patches": False,
        "computes_error_or_effect_size": False,
        "checkpoint": CKPT,
        "batch": BATCH,
        "timestep": TIMESTEP,
        "seed": SEED,
        "observations": notes,
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(report, fh, indent=1)

    print("\n--- observations ---")
    for key, value in notes.items():
        print(f"  {key}: {value}")
    print("\n--- checks ---")
    for key, value in checks.items():
        print(f"  {'PASS' if value else 'FAIL'}  {key}")
    print(f"\nwrote {OUT_JSON}")
    if not report["all_checks_passed"]:
        print("STOP: at least one pre-registered prediction failed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
