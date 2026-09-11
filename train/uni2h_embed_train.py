"""Build the UNI2-h conditioning-embedding cache for the 2,185 DGX training patches (E1β pre-step).

Step 3 of the PixCell self-conditioned scoring track. This is INPUT PREPROCESSING,
nothing more. It converts each validation patch into the (16,1536) tensor that the
PixCell DiT expects as `encoder_hidden_states`, and writes it next to the existing
VAE latent caches with a manifest binding every row to its source patch.

It deliberately computes NO error, NO clean-vs-artifact contrast, and NO effect
size. The clean/artifact label is carried in the manifest only because it is part
of a patch's identity (which catalogue it came from); nothing in this file compares
the two groups. The self-conditioned diagnostic that will consume this cache is a
pre-registered experiment and has not been pre-registered yet.

CONTRACT (verified against sources, not assumed -- see recon section 6.3):
  Encoder: MahmoodLab/UNI2-h pinned at revision d517a8dd47902dd7c308b3c36f63bce47e7b9a43,
  built with the model card's exact timm_kwargs.
  Per 1024x1024 patch, the PixCell-1024 card does:
      einops.rearrange(img_hwc, '(d1 h) (d2 w) c -> (d1 d2) h w c', d1=4, d2=4)
  i.e. row-major raster order over the 4x4 grid: token k is the crop at
  row k//4, column k%4. That order is what the transformer's 4x4 2-D sincos
  y_pos_embed assumes (meshgrid reshaped [2,1,H,W], flattened row-major), so it is
  not interchangeable with column-major. einops is not installed in this container,
  so the split is done twice by different means and the two are asserted equal.
  Encoder build: the card's second route -- timm.create_model(pretrained=False,
  **card_kwargs) then load_state_dict(strict=True) on the pytorch_model.bin whose
  sha256 step 1 verified. Binds to bytes, not to a hub lookup.
  Transform: create_transform(**resolve_data_config(pretrained_cfg=...)) where the
  pretrained_cfg is read from the sha-verified config.json, which resolves to
  Resize(224, bilinear) -> CenterCrop(224) -> ToTensor -> ImageNet Normalize. It
  must NOT be read off the model object: built with pretrained=False the model
  carries timm's generic vit_giant defaults, whose mean/std are not ImageNet.

PRE-REGISTERED PREDICTIONS (written before the run):
  V1. The manifest holds exactly 1,427 rows: 1,167 from val_clean.json then 260
      from val_artifact.json, in catalogue order, with no duplicate identity key.
  V2. Every patch splits into exactly 16 subpatches of 256x256, and the two
      independent split implementations agree bit-for-bit on every patch.
  V3. The checkpoint loads strict=True into the card's architecture at
      681,394,176 parameters, and the resolved transform reports input_size
      (3,224,224), ImageNet mean/std, crop_pct 1, bilinear interpolation; each
      transformed crop is (3,224,224) float32.
  V4. The encoder returns (16,1536) per patch; the stacked cache is
      (1427,16,1536) float32 and entirely finite.
  V5. The raw tensor payload is 1427*16*1536*4 = 140,279,808 bytes = 133.8 MiB,
      matching the recon's section 4 estimate.
  Any failure is a stop-and-report condition.
"""
import json
import os
import sys
import time

import numpy as np
import openslide
import torch
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
from common import log_run
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

CATALOG_DIR = DATA_ROOT + "/DiffusionQC/enhanced_version/dgx_catalogs"
OUT_DIR = DATA_ROOT + "/DiffusionQC/dgx_shared/latents/uni2h_emb_train2185_rev-d517a8dd"
OUT_PT = os.path.join(OUT_DIR, "embeddings.pt")
OUT_PARTIAL = os.path.join(OUT_DIR, "embeddings.partial.pt")
OUT_MANIFEST = os.path.join(OUT_DIR, "manifest.json")

UNI_REPO = "MahmoodLab/UNI2-h"
UNI_REVISION = "d517a8dd47902dd7c308b3c36f63bce47e7b9a43"
GRID = 4                      # 4x4 subpatches
SUB = C.PATCH_SIZE // GRID    # 1024 // 4 = 256
N_TOKENS, D_MODEL = 16, 1536
PATCHES_PER_BATCH = 2         # 32 crops per encoder forward; recon section 4 range
SAVE_EVERY = 200              # patches
EXPECT_CLEAN, EXPECT_ARTIFACT = 2185, 0


def build_manifest():
    """Clean catalogue then artifact catalogue, each in its own stored order."""
    rows = []
    for split, name, expected in (("clean", "train_clean.json", EXPECT_CLEAN),):
        cat = json.load(open(os.path.join(CATALOG_DIR, name)))
        patches = cat["patches"]
        assert len(patches) == expected, f"{name}: {len(patches)} rows, expected {expected}"
        for i, p in enumerate(patches):
            rows.append({"index": len(rows), "split": split, "source_catalogue": name,
                         "catalogue_index": i, "slide": p["slide"], "x": p["x"],
                         "y": p["y"], "level": p["level"],
                         "artifact_type": p.get("artifact_type")})
    return rows


def split_reshape(arr):
    """einops '(d1 h) (d2 w) c -> (d1 d2) h w c' written with numpy only."""
    out = arr.reshape(GRID, SUB, GRID, SUB, 3).transpose(0, 2, 1, 3, 4)
    return np.ascontiguousarray(out.reshape(GRID * GRID, SUB, SUB, 3))


def split_loop(arr):
    """The same split written as an explicit row-major crop loop, as a cross-check."""
    return np.stack([arr[r * SUB:(r + 1) * SUB, c * SUB:(c + 1) * SUB, :]
                     for r in range(GRID) for c in range(GRID)])


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    log_run(OUT_DIR, {"uni_repo": UNI_REPO, "uni_revision": UNI_REVISION,
                      "catalog_dir": CATALOG_DIR,
                      "patches_per_batch": PATCHES_PER_BATCH},
            inputs={"train_clean_catalogue": os.path.join(CATALOG_DIR, "train_clean.json")})

    import timm
    from huggingface_hub import hf_hub_download
    from timm.data import resolve_data_config
    from timm.data.transforms_factory import create_transform

    device = "cuda:0"
    checks = {}

    manifest = build_manifest()
    keys = {(r["split"], r["slide"], r["x"], r["y"], r["level"]) for r in manifest}
    checks["V1_total_2185"] = len(manifest) == 2185
    checks["V1_clean_then_artifact"] = (
        [r["split"] for r in manifest] == ["clean"] * EXPECT_CLEAN + ["artifact"] * EXPECT_ARTIFACT)
    checks["V1_no_duplicate_identity"] = len(keys) == len(manifest)

    # --- encoder ------------------------------------------------------------------
    # The card's *second* route: build the architecture with pretrained=False and load
    # the weight file explicitly. Preferred here over `hf-hub:...`, pretrained=True
    # because it binds the encoder to the exact bytes step 1 sha-verified rather than
    # to whatever the hub resolves at run time. strict=True is the card's own call and
    # is what proves the kwargs above describe this checkpoint and not a near-miss.
    cfg_path = hf_hub_download(UNI_REPO, "config.json", revision=UNI_REVISION)
    bin_path = hf_hub_download(UNI_REPO, "pytorch_model.bin", revision=UNI_REVISION)
    pretrained_cfg = json.load(open(cfg_path))["pretrained_cfg"]

    timm_kwargs = {
        'model_name': 'vit_giant_patch14_224',
        'img_size': 224, 'patch_size': 14, 'depth': 24, 'num_heads': 24,
        'init_values': 1e-5, 'embed_dim': 1536, 'mlp_ratio': 2.66667 * 2,
        'num_classes': 0, 'no_embed_class': True,
        'mlp_layer': timm.layers.SwiGLUPacked, 'act_layer': torch.nn.SiLU,
        'reg_tokens': 8, 'dynamic_img_size': True,
    }
    model = timm.create_model(pretrained=False, **timm_kwargs)
    state = torch.load(bin_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)   # raises on any mismatch
    model.eval().to(device)
    n_params = sum(p.numel() for p in model.parameters())
    checks["V3_param_count_681394176"] = n_params == 681394176

    # The transform comes from the sha-verified config.json, not from the model object:
    # built with pretrained=False the model carries timm's generic vit_giant defaults,
    # whose mean/std are NOT ImageNet. Reading the shipped pretrained_cfg is what keeps
    # the normalization the encoder was trained with.
    data_config = resolve_data_config(pretrained_cfg=pretrained_cfg)
    transform = create_transform(**data_config)
    checks["V3_input_size_224"] = tuple(data_config["input_size"]) == (3, 224, 224)
    checks["V3_mean_imagenet"] = tuple(data_config["mean"]) == (0.485, 0.456, 0.406)
    checks["V3_std_imagenet"] = tuple(data_config["std"]) == (0.229, 0.224, 0.225)
    checks["V3_crop_pct_1"] = float(data_config["crop_pct"]) == 1.0
    checks["V3_bilinear"] = data_config["interpolation"] == "bilinear"
    print(f"UNI2-h loaded: {n_params} params, strict=True")
    print("resolved data config:", data_config)
    print("transform:", transform)

    # --- resume support ----------------------------------------------------------
    done, start = [], 0
    if os.path.exists(OUT_PARTIAL):
        blob = torch.load(OUT_PARTIAL)
        done, start = [blob["emb"]], blob["emb"].shape[0]
        print(f"  resuming from partial: {start}/{len(manifest)}")

    handles, splits_agree, crop_shapes_ok = {}, True, True
    t0 = time.time()
    with torch.inference_mode():
        for s in range(start, len(manifest), PATCHES_PER_BATCH):
            chunk = manifest[s:s + PATCHES_PER_BATCH]
            crops = []
            for row in chunk:
                if row["slide"] not in handles:
                    handles[row["slide"]] = openslide.OpenSlide(
                        os.path.join(C.WSI_DIR, row["slide"]))
                sl = handles[row["slide"]]
                ds = sl.level_downsamples[row["level"]]
                img = sl.read_region((int(row["x"] * ds), int(row["y"] * ds)),
                                     row["level"],
                                     (C.PATCH_SIZE, C.PATCH_SIZE)).convert("RGB")
                arr = np.array(img)
                a, b = split_reshape(arr), split_loop(arr)
                if not np.array_equal(a, b):
                    splits_agree = False
                if a.shape != (16, SUB, SUB, 3):
                    crop_shapes_ok = False
                for sub in a:
                    t = transform(Image.fromarray(sub))
                    if tuple(t.shape) != (3, 224, 224) or t.dtype != torch.float32:
                        crop_shapes_ok = False
                    crops.append(t)

            batch = torch.stack(crops).to(device, dtype=torch.float32)
            feats = model(batch).float().cpu()               # (n*16, 1536)
            done.append(feats.reshape(len(chunk), N_TOKENS, D_MODEL))

            n_done = s + len(chunk)
            if n_done % SAVE_EVERY < PATCHES_PER_BATCH:
                torch.save({"emb": torch.cat(done)}, OUT_PARTIAL)
                print(f"  {n_done}/{len(manifest)} ({time.time()-t0:.0f}s, saved)")

    for h in handles.values():
        h.close()

    emb = torch.cat(done)
    elapsed = time.time() - t0
    payload_bytes = emb.numel() * emb.element_size()

    checks["V2_splits_agree"] = splits_agree
    checks["V2_crop_shapes"] = crop_shapes_ok
    checks["V4_shape_2185_16_1536"] = list(emb.shape) == [2185, N_TOKENS, D_MODEL]
    checks["V4_dtype_fp32"] = emb.dtype == torch.float32
    checks["V4_all_finite"] = bool(torch.isfinite(emb).all())
    checks["V5_payload_bytes"] = payload_bytes == 214794240

    meta = {
        "step": "E1β pre-step -- UNI2-h training-patch embedding cache (input preprocessing)",
        "encoder": {"repo_id": UNI_REPO, "revision": UNI_REVISION,
                    "weights_file": bin_path, "param_count": n_params,
                    "load": "timm.create_model(pretrained=False, **card_kwargs) + "
                            "load_state_dict(strict=True) on the sha-verified bytes",
                    "weights_sha256": "6e077eda234bebc595868d918d3458d9dd32a050199b0ff04443b2f46a0a3b1e",
                    "timm_kwargs_note": "model card verbatim; mlp_ratio = 2.66667*2 = 5.33334",
                    "license": "CC-BY-NC-ND 4.0 -- non-commercial academic research, "
                               "attribution, no redistribution of the model"},
        "patch_contract": {
            "patch_px": C.PATCH_SIZE, "grid": [GRID, GRID], "subpatch_px": SUB,
            "order": "row-major: token k = crop at row k//4, column k%4",
            "order_source": "PixCell-1024 card rearrange '(d1 h) (d2 w) c -> (d1 d2) h w c'; "
                            "matches the transformer's 4x4 sincos y_pos_embed",
            "read_region": "openslide read_region((x*level_downsample, y*level_downsample), "
                           "level, (1024,1024)).convert('RGB') -- identical to common.py",
        },
        "transform_resolved": {k: (list(v) if isinstance(v, (tuple, list)) else v)
                               for k, v in data_config.items()},
        "cache": {"shape": list(emb.shape), "dtype": "float32",
                  "payload_bytes": payload_bytes,
                  "payload_mib": round(payload_bytes / 1024 / 1024, 1),
                  "path": OUT_PT},
        "counts": {"clean": EXPECT_CLEAN, "artifact": EXPECT_ARTIFACT, "total": len(manifest)},
        "elapsed_seconds": round(elapsed, 1),
        "peak_vram_bytes": torch.cuda.max_memory_allocated(device),
        "computes_error_or_effect_size": False,
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }

    torch.save({"emb": emb, "manifest": manifest, "meta": meta}, OUT_PT)
    with open(OUT_MANIFEST, "w") as fh:
        json.dump({"meta": meta, "manifest": manifest}, fh, indent=1)
    if os.path.exists(OUT_PARTIAL):
        os.remove(OUT_PARTIAL)

    print("\n--- checks ---")
    for key, value in checks.items():
        print(f"  {'PASS' if value else 'FAIL'}  {key}")
    print(f"\n{emb.shape} float32, {meta['cache']['payload_mib']} MiB payload, "
          f"{elapsed:.0f}s")
    print(f"wrote {OUT_PT}\nwrote {OUT_MANIFEST}")
    if not meta["all_checks_passed"]:
        print("STOP: at least one pre-registered prediction failed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
