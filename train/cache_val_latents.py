"""Pre-step for E1 (Gaps §16/E1 pre-step note, 1 September 2026).

Rebuilds the two validation latent caches with an explicit per-row key manifest,
so the E1 producer can join latents to UNI2-h embeddings by key equality, never
by order convention. Input preparation only: no noise-prediction error is
computed and no clean-vs-artifact contrast is formed here.

Pre-registered checks (all must pass; any failure is stop-and-report):
 C1  val_clean.json has 1,167 patches; val_artifact.json has 260.
 C2  embedding manifest has 1,427 rows; rows 0-1166 are split 'clean' from
     val_clean.json, rows 1167-1426 are split 'artifact' from val_artifact.json.
 C3  per-row (slide, x, y, level) equality between the embedding manifest and
     the catalogues, with catalogue_index equal to catalogue position.
 C4  artifact_type counts over the manifest are {134, 125, 1} as a multiset
     (air-bubble / out-of-focus / penmark; names recorded, not assumed).
 C5  output tensors are FP32, shapes (N,16,128,128) matching the input counts.
 C6  the newly encoded artifact means agree with the legacy val_artifact.pt on
     the compared rows (max abs diff < 1e-3) -- retroactively validating that
     cache's order convention. Recorded either way.
"""
import argparse
import json
import os
from collections import Counter

import torch

import common as C
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

LAT = DATA_ROOT + "/DiffusionQC/dgx_shared/latents"
CATS = DATA_ROOT + "/DiffusionQC/dgx_shared/catalogs"
EMB_DIR = os.path.join(LAT, "uni2h_emb_val1427_rev-d517a8dd")


def key_of(p):
    return (p["slide"], p["x"], p["y"], p["level"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="encode only 8+8 patches into a _smoke directory")
    args = ap.parse_args()

    out_dir = os.path.join(LAT, "val_latents_keyed" + ("_smoke" if args.smoke else ""))
    os.makedirs(out_dir, exist_ok=True)

    clean = json.load(open(os.path.join(CATS, "val_clean.json")))["patches"]
    art = json.load(open(os.path.join(CATS, "val_artifact.json")))["patches"]
    man = json.load(open(os.path.join(EMB_DIR, "manifest.json")))["manifest"]

    # C1
    assert len(clean) == 1167 and len(art) == 260, (len(clean), len(art))
    # C2 + C3
    assert len(man) == 1427, len(man)
    for i, row in enumerate(man):
        expect_split = "clean" if i < 1167 else "artifact"
        assert row["split"] == expect_split, ("C2 split", i, row["split"])
        ci = row["catalogue_index"]
        assert ci == (i if i < 1167 else i - 1167), ("C2 catalogue_index", i, ci)
        src = clean if expect_split == "clean" else art
        assert key_of(row) == key_of(src[ci]), ("C3 key mismatch", i)
    # C4
    counts = Counter(r["artifact_type"] for r in man if r["split"] == "artifact")
    assert sorted(counts.values()) == [1, 125, 134], dict(counts)
    print("C1-C4 passed; artifact_type counts:", dict(counts))

    n_c, n_a = (8, 8) if args.smoke else (len(clean), len(art))

    device = "cuda:0"
    pipe, vae = C.load_pixcell(device)

    cc = C.cache_latents(clean[:n_c], os.path.join(out_dir, "val_clean_full.pt"),
                         vae, device)
    ca = C.cache_latents(art[:n_a], os.path.join(out_dir, "val_artifact_full.pt"),
                         vae, device)

    # C5
    for name, cache, n in (("clean", cc, n_c), ("artifact", ca, n_a)):
        for field in ("means", "stds"):
            t = cache[field]
            assert t.dtype == torch.float32, ("C5 dtype", name, field, t.dtype)
            assert tuple(t.shape) == (n, 16, 128, 128), ("C5 shape", name, field,
                                                         tuple(t.shape))
    print("C5 passed")

    # C6
    old = torch.load(os.path.join(LAT, "val_artifact.pt"), map_location="cpu")
    diff = (ca["means"] - old["means"][:n_a]).abs().max().item()
    print("C6 max abs diff vs legacy val_artifact.pt (first %d rows): %.3e"
          % (n_a, diff))
    assert diff < 1e-3, ("C6", diff)

    out_manifest = {
        "note": "keys copied from the C3-validated embedding manifest; latent row "
                "order equals manifest order within each split",
        "embedding_cache": EMB_DIR,
        "smoke": args.smoke,
        "clean_rows": man[:n_c],
        "artifact_rows": man[1167:1167 + n_a],
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(out_manifest, f, indent=1)
    print("wrote", os.path.join(out_dir, "manifest.json"))

    C.log_run(out_dir, vars(args), inputs={
        "val_clean_catalogue": os.path.join(CATS, "val_clean.json"),
        "val_artifact_catalogue": os.path.join(CATS, "val_artifact.json"),
        "embedding_manifest": os.path.join(EMB_DIR, "manifest.json"),
        "legacy_val_artifact_pt": os.path.join(LAT, "val_artifact.pt"),
    })
    print("done")


if __name__ == "__main__":
    main()
