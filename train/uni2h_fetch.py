"""Fetch the gated MahmoodLab/UNI2-h encoder and record its identity.

Step 1 of the PixCell self-conditioned scoring track. This is asset acquisition and
provenance capture, NOT an experiment: nothing is scored, compared, or interpreted.

The recon (provenance/pixcell_self_conditioning_recon.md, section 3) established that
UNI2-h is absent from the DGX and gated behind CC-BY-NC-ND 4.0. Access has now been
granted. This script pins the repository revision, downloads the weights into the
standard HF cache, verifies the local bytes against the Hub's own LFS sha256, and
lifts the model card's `timm_kwargs` verbatim so the encoder can be reconstructed
later without re-reading the card.

PRE-REGISTERED EXPECTATIONS (recorded before the run, per the pre-registration rule):
  E1. pytorch_model.bin downloads at exactly 2,725,669,217 bytes (the size the Hub
      metadata already reports) and its sha256 matches the Hub's LFS sha256
      6e077eda234bebc595868d918d3458d9dd32a050199b0ff04443b2f46a0a3b1e.
  E2. The model card contains a `timm_kwargs` dict describing a ViT-H/14 with
      embed_dim 1536, depth 24, num_heads 24, and 8 register tokens -- matching the
      recon's section 2 reading. img_size is expected to be 224.
  E3. config.json is a timm config naming the same architecture.
  Any mismatch is a stop-and-report condition, not something to work around.

The token is taken from the ambient huggingface_hub credential; it is never read,
printed, or written by this script.
"""
import ast
import hashlib
import json
import os
import re
import sys

from huggingface_hub import HfApi, hf_hub_download

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import log_run
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

REPO_ID = "MahmoodLab/UNI2-h"
REVISION = "d517a8dd47902dd7c308b3c36f63bce47e7b9a43"  # pinned; resolved from main
FILES = ["README.md", "config.json", "pytorch_model.bin"]

OUT_DIR = DATA_ROOT + "/DiffusionQC/provenance/uni2h_fetch_MahmoodLab-UNI2-h_rev-d517a8dd"
OUT_JSON = os.path.join(OUT_DIR, "uni2h_fetch.json")

EXPECT_SIZE = 2725669217
EXPECT_SHA256 = "6e077eda234bebc595868d918d3458d9dd32a050199b0ff04443b2f46a0a3b1e"


def sha256_of(path, chunk=64 * 1024 * 1024):
    """Streamed sha256 -- the weight file is 2.5 GiB and must not be slurped."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def extract_timm_kwargs(card_text):
    """Lift the `timm_kwargs = {...}` block from the model card verbatim.

    Kept as text rather than parsed: the dict holds live references
    (torch.nn.SiLU, timm.layers.SwiGLUPacked) that no literal parser accepts, and
    the point of recording it is that the exact call can be reproduced.
    """
    start = card_text.find("timm_kwargs = {")
    if start == -1:
        return None, {}, {}
    depth, i = 0, card_text.index("{", start)
    for j in range(i, len(card_text)):
        if card_text[j] == "{":
            depth += 1
        elif card_text[j] == "}":
            depth -= 1
            if depth == 0:
                block = card_text[start:j + 1]
                break
    else:
        return None, {}, {}

    # Scalar fields are worth having as data for later assertions, but only where the
    # source text is an exact literal. `init_values: 1e-5` and `mlp_ratio: 2.66667*2`
    # are an exponent and a product; a naive number-grab records them as 1 and 2.66667,
    # which would silently rebuild a different encoder. Anything ast cannot evaluate as
    # a literal is left out of the scalars dict -- the verbatim block is the record.
    scalars, non_literal = {}, {}
    for key, value in re.findall(r"'([a-z_]+)'\s*:\s*([^,\n]+)", block):
        text = value.strip().rstrip(",")
        try:
            scalars[key] = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            non_literal[key] = text
    return block, scalars, non_literal


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    log_run(OUT_DIR, {"repo_id": REPO_ID, "revision": REVISION, "files": ",".join(FILES)})

    api = HfApi()
    info = api.model_info(REPO_ID, revision=REVISION, files_metadata=True)
    remote = {s.rfilename: {"size": s.size,
                            "lfs_sha256": (s.lfs or {}).get("sha256") if s.lfs else None}
              for s in info.siblings}

    local = {}
    for name in FILES:
        path = hf_hub_download(REPO_ID, name, revision=REVISION)
        size = os.path.getsize(path)
        entry = {"cache_path": path, "size_bytes": size,
                 "remote_size_bytes": remote.get(name, {}).get("size"),
                 "remote_lfs_sha256": remote.get(name, {}).get("lfs_sha256")}
        entry["sha256"] = sha256_of(path)
        entry["sha256_matches_remote_lfs"] = (
            entry["remote_lfs_sha256"] is None or entry["sha256"] == entry["remote_lfs_sha256"])
        local[name] = entry
        print(f"{name}: {size} bytes  sha256={entry['sha256']}")

    weights = local["pytorch_model.bin"]
    checks = {
        "E1_size_matches_expected": weights["size_bytes"] == EXPECT_SIZE,
        "E1_sha256_matches_expected": weights["sha256"] == EXPECT_SHA256,
        "E1_sha256_matches_remote_lfs": weights["sha256_matches_remote_lfs"],
    }

    card = open(local["README.md"]["cache_path"], encoding="utf-8").read()
    timm_block, timm_scalars, timm_non_literal = extract_timm_kwargs(card)
    config = json.load(open(local["config.json"]["cache_path"], encoding="utf-8"))

    checks.update({
        "E2_timm_kwargs_found": timm_block is not None,
        "E2_embed_dim_1536": timm_scalars.get("embed_dim") == 1536,
        "E2_depth_24": timm_scalars.get("depth") == 24,
        "E2_num_heads_24": timm_scalars.get("num_heads") == 24,
        "E2_reg_tokens_8": timm_scalars.get("reg_tokens") == 8,
        "E2_img_size_224": timm_scalars.get("img_size") == 224,
        # init_values is exponent notation, which is still a literal -- it parses.
        # mlp_ratio is a product, the one field no literal parser can take.
        "E2_init_values_1e-5": timm_scalars.get("init_values") == 1e-5,
        "E2_mlp_ratio_is_expression": timm_non_literal.get("mlp_ratio") == "2.66667*2",
        "E3_config_present": bool(config),
        "E3_config_mean_imagenet": config.get("pretrained_cfg", {}).get("mean") == [0.485, 0.456, 0.406],
        "E3_config_std_imagenet": config.get("pretrained_cfg", {}).get("std") == [0.229, 0.224, 0.225],
        "E3_config_input_224": config.get("pretrained_cfg", {}).get("input_size") == [3, 224, 224],
    })

    report = {
        "step": "1 -- UNI2-h acquisition and identity capture",
        "repo_id": REPO_ID,
        "revision": REVISION,
        "gated": str(info.gated),
        "license": "CC-BY-NC-ND 4.0 (non-commercial academic research, attribution, "
                   "no redistribution or publication of a model copy; individual registration)",
        "hf_cache_root": os.path.dirname(os.path.dirname(weights["cache_path"])),
        "files": local,
        "timm_kwargs_verbatim": timm_block,
        "timm_kwargs_scalars": timm_scalars,
        "timm_kwargs_non_literal": timm_non_literal,
        # 2.66667*2; recorded resolved so the encoder can be rebuilt from this file
        # alone, without re-evaluating the card's expression.
        "timm_kwargs_mlp_ratio_resolved": 2.66667 * 2,
        "config_json": config,
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(report, fh, indent=1)

    print("\n--- checks ---")
    for key, value in checks.items():
        print(f"  {'PASS' if value else 'FAIL'}  {key}")
    print(f"\nwrote {OUT_JSON}")
    if not report["all_checks_passed"]:
        print("STOP: at least one pre-registered expectation failed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
