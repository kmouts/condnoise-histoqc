"""
common.py -- shared code for the DiffusionQC scripts on the DGX cluster.

Everything that differs from the Colab notebooks is centralised here, so the
differences live in one place instead of being scattered across scripts:

  1. `load_pixcell()` passes `low_cpu_mem_usage=False, device_map=None`.
     Without these, the `y_pos_embed.y_pos_embed` key -- a deterministic
     sinusoidal buffer that is *supposed* to be re-derived rather than loaded --
     raises a fatal ValueError instead of the harmless warning it produced on
     Colab. `trust_remote_code=True` is also required (the pipeline reports it
     as "not expected" but the downloader needs it).

  2. `torchao` is deliberately NOT installed in this container. On Colab it was
     needed to override a broken preinstalled version; here its latest release
     requires torch>=2.11 while the container has 2.5.1, and importing it breaks
     transformers -> peft. Do not add it back without checking torch version.

  3. WSI files live in per-GUID subdirectories under WSIs/. `AIRAQC_flat/images`
     holds symlinks so paths stay flat, matching the Colab layout.
"""

import os
import json
import time
import sys
import socket
import datetime
import subprocess

import numpy as np
import torch
import torch.nn as nn
import openslide
from PIL import Image
from skimage.filters import threshold_otsu
from scipy.ndimage import zoom as nd_zoom
import torchvision.transforms.functional as TF
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

# ---------------------------------------------------------------- paths

# The code repo, located from this file rather than from cwd: experiment scripts
# get launched from anywhere, and provenance must not depend on where from.
REPO_DIR = os.path.dirname(os.path.abspath(__file__))

ROOT = DATA_ROOT
WSI_DIR = os.path.join(ROOT, "AIRAQC_flat/images")
ANN_DIR = os.path.join(ROOT, "AIRAQC_flat/AIRAQc_anns")
DQC = os.path.join(ROOT, "DiffusionQC")
SPLIT_PATH = os.path.join(DQC, "train_test_split.json")

PATCH_SIZE = 1024
TARGET_MAG = 10.0
THUMB_MAX_SIZE = 2000

ARTIFACT_COLOR_PALETTE = {
    'out-of-focus': (255, 0, 0), 'air-bubble': (255, 255, 0), 'fold': (0, 255, 0),
    'penmark': (255, 165, 0), 'dark-spot': (128, 0, 128), 'knife-line': (255, 0, 255),
    'coverslip': (0, 255, 255),
}
# Four types, matching AIRAQC's H&E annotations and the paper's Table 1. 'dark-spot'
# was removed: it is not an AIRAQC class and its palette entry acted as a sink for every
# faint pixel (see 5r in the reproducibility log).
TYPES = ['out-of-focus', 'fold', 'penmark', 'air-bubble']

# Maximum Euclidean RGB distance from a palette colour for a pixel to be attributed to
# that type. Beyond it the pixel is annotation of something else (the blue No-Tissue /
# Missing-Tissue class) or an anti-aliased edge, and is excluded from per-type masks
# rather than force-assigned. 60 removes 100% of the spurious dark-spot mask and
# 0.1-0.8% of the four real types.
MAX_PALETTE_DIST = 60.0

# When True, gt_bin becomes the union of the four typed masks, matching the paper's
# "annotations for pen marking, tissue folding, out-of-focus and air bubbles". When
# False (default) gt_bin stays as any non-black pixel, so binary results are unchanged
# and remain comparable with everything computed before this patch.
RESTRICT_BINARY_TO_TYPES = False


def load_split():
    with open(SPLIT_PATH) as f:
        return json.load(f)


def ann_map():
    """slide filename -> annotation filename."""
    return {f[:-4] + '.svs': f for f in sorted(os.listdir(ANN_DIR))
            if f.lower().endswith('.png')}


# ---------------------------------------------------------------- model

def load_pixcell(device, dtype=torch.float32):
    """Load VAE + PixCell pipeline with the DGX-specific arguments (see module docstring)."""
    from diffusers import DiffusionPipeline, AutoencoderKL

    vae = AutoencoderKL.from_pretrained(
        "stabilityai/stable-diffusion-3.5-large", subfolder="vae")
    vae.requires_grad_(False)
    vae = vae.to(device, dtype=dtype).eval()

    pipe = DiffusionPipeline.from_pretrained(
        "StonyBrook-CVLab/PixCell-1024", vae=vae,
        custom_pipeline="StonyBrook-CVLab/PixCell-pipeline",
        trust_remote_code=True, torch_dtype=dtype,
        low_cpu_mem_usage=False, device_map=None,   # <-- required on this container
    )
    pipe.to(device)
    return pipe, vae


def attach_lora(pipe, device, r=16, alpha=16, lora_dropout=0.0):
    """Wrap the transformer with a fresh LoRA adapter. Returns the target module list."""
    from peft import LoraConfig, get_peft_model

    targets = [n for n, m in pipe.transformer.named_modules()
               if isinstance(m, torch.nn.Linear)
               and n.endswith(('to_q', 'to_k', 'to_v', 'to_out.0'))]
    assert len(targets) == 224, f"expected 224 attention modules, found {len(targets)}"

    pipe.transformer = get_peft_model(
        pipe.transformer,
        LoraConfig(r=r, lora_alpha=alpha, target_modules=targets,
                   lora_dropout=lora_dropout, bias="none"))
    pipe.transformer = pipe.transformer.to(device)
    return targets


def load_lora_weights(pipe, ckpt_dir):
    """Load a saved LoRA adapter, handling the doubled-prefix quirk, and verify it took."""
    from peft import set_peft_model_state_dict
    from safetensors.torch import load_file

    saved = load_file(os.path.join(ckpt_dir, "adapter_model.safetensors"))
    p = "base_model.model."
    fixed = {(k[len(p):] if k.startswith(p + p) else k): v for k, v in saved.items()}
    res = set_peft_model_state_dict(pipe.transformer, fixed)

    missing = [k for k in res.missing_keys if 'lora_' in k]
    assert not missing, f"{len(missing)} LoRA keys missing -- checkpoint did not load"
    assert not res.unexpected_keys, f"{len(res.unexpected_keys)} unexpected keys"

    probe = dict(pipe.transformer.named_parameters())[
        'base_model.model.transformer_blocks.0.attn1.to_q.lora_B.default.weight']
    norm = probe.norm().item()
    assert norm > 0, "LoRA lora_B is all zeros -- weights did not actually load"
    print(f"  LoRA loaded: {len(fixed)} keys, sample lora_B norm {norm:.4f}")


class ContrastiveAdaptor(nn.Module):
    """f_A -- zero-initialised residual conv, an exact identity at init."""

    def __init__(self, channels=16):
        super().__init__()
        self.conv = nn.Conv2d(channels, channels, kernel_size=3, padding=1)
        nn.init.zeros_(self.conv.weight)
        nn.init.zeros_(self.conv.bias)

    def forward(self, z):
        return z + self.conv(z)


def load_f_A(ckpt_dir, device):
    f_A = ContrastiveAdaptor().to(device, dtype=torch.float32)
    f_A.load_state_dict(torch.load(os.path.join(ckpt_dir, "f_A.pt")))
    f_A.eval()
    norm = f_A.conv.weight.norm().item()
    assert norm > 0, "f_A conv weight is zero -- it never trained, or failed to load"
    print(f"  f_A loaded: conv weight norm {norm:.4f}")
    return f_A


# ---------------------------------------------------------------- slides

def find_magnification_level(slide, target_mag=TARGET_MAG, ref_mpp=0.25):
    op = slide.properties.get('openslide.objective-power')
    mpp = slide.properties.get('openslide.mpp-x')
    if op is not None:
        base = float(op)
    elif mpp is not None:
        base = ref_mpp / float(mpp) * 40.0
    else:
        return None, None
    best_l, best_d = None, float('inf')
    for l, ds in enumerate(slide.level_downsamples):
        d = abs(base / ds - target_mag) / target_mag
        if d < best_d:
            best_d, best_l = d, l
    return best_l, best_d


def clamped_positions(w, h, ps, stride):
    """Grid spanning the full extent -- last row/col clamped to the edge, not dropped."""
    xs = list(range(0, max(w - ps, 0) + 1, stride))
    if not xs or xs[-1] != w - ps:
        xs.append(max(w - ps, 0))
    ys = list(range(0, max(h - ps, 0) + 1, stride))
    if not ys or ys[-1] != h - ps:
        ys.append(max(h - ps, 0))
    return xs, ys


def tissue_mask_from_thumb(thumb):
    """Dual criterion (saturation OR dark value) -- catches dark ink that saturation alone misses."""
    hsv = np.array(thumb.convert('HSV'))
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    return (s > threshold_otsu(s)) | (v < threshold_otsu(v))


def pixel_tissue_mask(thumb, target_shape):
    m = tissue_mask_from_thumb(thumb)
    return nd_zoom(m.astype(np.float32),
                   (target_shape[0] / m.shape[0], target_shape[1] / m.shape[1]),
                   order=0) > 0.5


def build_ground_truth(ann_path, target_shape):
    """Binary + per-type masks in one pass over the annotation image.

    Pixels are attributed to the nearest palette colour, but only if within
    MAX_PALETTE_DIST of it. Unmatched pixels stay in gt_bin (they are annotation of
    something) while appearing in no per-type mask -- previously they were forced onto
    the nearest entry, which meant dark-spot collected every faint pixel on the slide.
    """
    arr = np.array(Image.open(ann_path).convert('RGB'))
    any_mask = arr.sum(axis=-1) > 15
    px = arr.reshape(-1, 3).astype(np.float32)
    names = list(ARTIFACT_COLOR_PALETTE.keys())

    best_d = np.full(len(px), np.inf, dtype=np.float32)
    best_i = np.zeros(len(px), dtype=np.int64)
    for i, nm in enumerate(names):
        d = np.sum((px - np.array(ARTIFACT_COLOR_PALETTE[nm], dtype=np.float32)) ** 2,
                   axis=1)
        better = d < best_d
        best_d = np.where(better, d, best_d)
        best_i = np.where(better, i, best_i)

    nearest = best_i.reshape(arr.shape[:2])
    matched = (best_d <= MAX_PALETTE_DIST ** 2).reshape(arr.shape[:2])
    typed = {t: any_mask & matched & (nearest == names.index(t)) for t in TYPES}

    src_bin = (np.logical_or.reduce(list(typed.values())) if RESTRICT_BINARY_TO_TYPES
               else any_mask)

    zy, zx = target_shape[0] / any_mask.shape[0], target_shape[1] / any_mask.shape[1]
    gt_bin = nd_zoom(src_bin.astype(np.float32), (zy, zx), order=0) > 0.5
    gt_type = {t: nd_zoom(m.astype(np.float32), (zy, zx), order=0) > 0.5
               for t, m in typed.items()}
    return gt_bin, gt_type


def catalog_patches(slide_files, mode, stride=512, min_overlap=0.05,
                    tissue_threshold=0.5, verbose=True, cache_path=None):
    """Build a patch catalogue.

    mode='clean'    -> patches with NO annotation overlap AND >= tissue_threshold tissue
    mode='artifact' -> patches with >= min_overlap annotation, tagged with dominant type

    The tissue requirement matters for 'clean' and is easy to forget: annotation overlap
    alone does not exclude pure background, since blank slide area carries no annotation.
    Without it this returned 9,485 clean patches instead of the expected ~2,187, i.e. the
    training set would have been dominated by white background rather than tissue.

    Tissue detection here is saturation-only (not the dual saturation-OR-dark criterion used
    for inference coverage). Dark pixels are deliberately NOT counted as tissue when curating
    *training* patches: dark ink and shadow would otherwise be treated as clean tissue.
    """
    # The catalogue depends only on the slide list and these parameters, none of which
    # change between runs -- so cache it. Recomputing costs a couple of minutes per run
    # for an identical result. The key records every parameter that affects the output,
    # so changing any of them produces a different file rather than a stale hit.
    if cache_path is not None:
        key = {'mode': mode, 'stride': stride, 'min_overlap': min_overlap,
               'tissue_threshold': tissue_threshold, 'slides': sorted(slide_files)}
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                cached = json.load(f)
            if cached.get('key') == key:
                if verbose:
                    print(f"  loaded {len(cached['patches'])} {mode} patches from cache")
                return cached['patches']
            elif verbose:
                print(f"  catalogue cache exists but parameters differ -- rebuilding")

    amap = ann_map()
    out = []
    t0 = time.time()

    for si, fname in enumerate(slide_files):
        path = os.path.join(WSI_DIR, fname)
        slide = openslide.OpenSlide(path)
        level, _ = find_magnification_level(slide)
        if level is None:
            slide.close()
            if verbose:
                print(f"  SKIP {fname}: no magnification level")
            continue
        lw, lh = slide.level_dimensions[level]
        l0w, l0h = slide.dimensions

        thumb = slide.get_thumbnail((THUMB_MAX_SIZE, THUMB_MAX_SIZE))
        hsv = np.array(thumb.convert('HSV'))
        sat = hsv[:, :, 1]
        tmask = sat > threshold_otsu(sat)          # saturation-only, see docstring
        tsx, tsy = thumb.size[0] / lw, thumb.size[1] / lh
        slide.close()
        ds = l0w / lw

        ann_name = amap.get(fname)
        if ann_name is None:
            any_mask = nearest = None
        else:
            arr = np.array(Image.open(os.path.join(ANN_DIR, ann_name)).convert('RGB'))
            any_mask = arr.sum(axis=-1) > 15
            if mode == 'artifact':
                px = arr.reshape(-1, 3).astype(np.float32)
                names = list(ARTIFACT_COLOR_PALETTE.keys())
                bd = bi = None
                for i, nm in enumerate(names):
                    d = np.sum((px - np.array(ARTIFACT_COLOR_PALETTE[nm], dtype=np.float32)) ** 2, axis=1)
                    if bd is None:
                        bd, bi = d, np.zeros(len(px), dtype=np.int64)
                    else:
                        b = d < bd
                        bd = np.where(b, d, bd)
                        bi = np.where(b, i, bi)
                nearest = bi.reshape(arr.shape[:2])
            else:
                nearest = None
            asx, asy = arr.shape[1] / l0w, arr.shape[0] / l0h

        found = 0
        for y in range(0, lh - PATCH_SIZE + 1, stride):
            for x in range(0, lw - PATCH_SIZE + 1, stride):
                # Tissue gate, applied to clean patches only. Artifact patches are annotated
                # regions and therefore on tissue by construction; gating them too would
                # change the artifact counts, which currently match the reference exactly.
                if mode == 'clean':
                    ta, tb = int(x * tsx), int(y * tsy)
                    tc = max(int((x + PATCH_SIZE) * tsx), ta + 1)
                    td = max(int((y + PATCH_SIZE) * tsy), tb + 1)
                    if tmask[tb:td, ta:tc].mean() < tissue_threshold:
                        continue

                if any_mask is None:
                    if mode == 'clean':
                        out.append({'slide': fname, 'x': x, 'y': y, 'level': level})
                        found += 1
                    continue

                x0, y0 = x * ds, y * ds
                a, b = int(x0 * asx), int(y0 * asy)
                c = max(int((x0 + PATCH_SIZE * ds) * asx), a + 1)
                d_ = max(int((y0 + PATCH_SIZE * ds) * asy), b + 1)
                region = any_mask[b:d_, a:c]
                if region.size == 0:
                    continue
                frac = region.mean()

                if mode == 'clean' and not region.any():
                    out.append({'slide': fname, 'x': x, 'y': y, 'level': level})
                    found += 1
                elif mode == 'artifact' and frac >= min_overlap:
                    rt = nearest[b:d_, a:c][region]
                    if len(rt) == 0:
                        continue
                    names = list(ARTIFACT_COLOR_PALETTE.keys())
                    dom = names[np.bincount(rt, minlength=len(names)).argmax()]
                    out.append({'slide': fname, 'x': x, 'y': y, 'level': level,
                                'artifact_type': dom})
                    found += 1

        if verbose:
            print(f"  [{si+1}/{len(slide_files)}] {fname}: {found} {mode} patches "
                  f"({time.time()-t0:.0f}s)")

    if cache_path is not None:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, 'w') as f:
            json.dump({'key': key, 'patches': out}, f)
        if verbose:
            print(f"  saved catalogue -> {os.path.basename(cache_path)}")

    return out


# ---------------------------------------------------------------- latents

def cache_latents(patch_list, cache_path, vae, device, batch_size=8, save_every=20):
    """Encode patches to VAE latents, saving partial progress so an interruption
    costs only the batches since the last checkpoint."""
    partial_path = cache_path.replace('.pt', '_partial.pt')

    if os.path.exists(cache_path):
        print(f"  loading complete cache: {os.path.basename(cache_path)}")
        return torch.load(cache_path)

    means, stds, start_idx = [], [], 0
    if os.path.exists(partial_path):
        pt = torch.load(partial_path)
        means, stds = [pt['means']], [pt['stds']]
        start_idx = pt['means'].shape[0]
        print(f"  resuming from partial: {start_idx}/{len(patch_list)}")

    handles = {}
    t0 = time.time()
    with torch.no_grad():
        for s in range(start_idx, len(patch_list), batch_size):
            chunk = patch_list[s:s + batch_size]
            imgs = []
            for p in chunk:
                if p['slide'] not in handles:
                    handles[p['slide']] = openslide.OpenSlide(
                        os.path.join(WSI_DIR, p['slide']))
                sl = handles[p['slide']]
                ds = sl.level_downsamples[p['level']]
                r = sl.read_region((int(p['x'] * ds), int(p['y'] * ds)),
                                   p['level'], (PATCH_SIZE, PATCH_SIZE)).convert('RGB')
                imgs.append(TF.to_tensor(r) * 2.0 - 1.0)
            batch = torch.stack(imgs).to(device, dtype=torch.float32)
            dist = vae.encode(batch).latent_dist
            means.append((dist.mean * vae.config.scaling_factor).cpu())
            stds.append((dist.std * vae.config.scaling_factor).cpu())

            n_done = (s - start_idx) // batch_size + 1
            if n_done % save_every == 0:
                torch.save({'means': torch.cat(means), 'stds': torch.cat(stds)}, partial_path)
                print(f"  {s+len(chunk)}/{len(patch_list)} ({time.time()-t0:.0f}s, saved)")

    for h in handles.values():
        h.close()

    out = {'means': torch.cat(means), 'stds': torch.cat(stds)}
    torch.save(out, cache_path)
    if os.path.exists(partial_path):
        os.remove(partial_path)
    print(f"  cached {out['means'].shape[0]} patches in {time.time()-t0:.0f}s")
    return out


def sample_from_cache(cache, idx, device):
    m = cache['means'][idx].to(device)
    s = cache['stds'][idx].to(device)
    return m + s * torch.randn_like(m)


# ---------------------------------------------------------------- provenance

# Set by run.sh / runbg.sh on the host, before entering the singularity container.
# The container has no git binary, so in-container runs -- which is all the heavy ones --
# cannot query git themselves and depend on these being handed in.
GIT_STATUS_ENV = 'DQC_GIT_STATUS'      # `git status --porcelain` output; '' means clean
GIT_PATCH_ENV = 'DQC_GIT_PATCH'        # path to a `git diff HEAD` written on the host
GIT_UNTRACKED_ENV = 'DQC_GIT_UNTRACKED'   # path to a tarball of untracked files

# Above this, the untracked archive is big enough to be an accident rather than context,
# and it is about to be copied into the output directory of every run.
UNTRACKED_WARN_BYTES = 50 * 1024 * 1024


def _git(*cmd):
    """Run a git command in the code repo, or return None if git is unavailable."""
    try:
        r = subprocess.run(('git', '-C', REPO_DIR) + cmd,
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _head_commit():
    """HEAD's hash read straight from .git, without the git binary.

    Necessary, not defensive: the GPU scripts run inside the singularity container,
    which has no git executable. Shelling out there returns nothing, which would leave
    every run.json from every GPU experiment carrying a null commit -- exactly the runs
    whose provenance matters most. Returns (sha, branch_name).
    """
    head = os.path.join(REPO_DIR, '.git', 'HEAD')
    if not os.path.exists(head):
        return None, None
    with open(head) as f:
        txt = f.read().strip()
    if not txt.startswith('ref: '):
        return txt, None                                  # detached HEAD
    ref = txt[5:]
    branch = ref.rsplit('/', 1)[-1]
    loose = os.path.join(REPO_DIR, '.git', ref)
    if os.path.exists(loose):                             # the normal case
        with open(loose) as f:
            return f.read().strip(), branch
    packed = os.path.join(REPO_DIR, '.git', 'packed-refs')
    if os.path.exists(packed):                            # after a `git gc`
        with open(packed) as f:
            for line in f:
                if line.rstrip('\n').endswith(' ' + ref):
                    return line.split()[0], branch
    return None, branch


def _sources_newer_than_index():
    """Cheap dirty-tree proxy for when neither git nor the launcher env is available.

    A source newer than .git/index means something was edited after the last `git add`.
    False positives are possible (a bare touch, a fresh checkout); false negatives are
    not, for a real edit. Never present it as git's own answer.
    """
    idx = os.path.join(REPO_DIR, '.git', 'index')
    if not os.path.exists(idx):
        return None
    cutoff = os.path.getmtime(idx)
    return sorted(f for f in os.listdir(REPO_DIR) if f.endswith('.py')
                  and os.path.getmtime(os.path.join(REPO_DIR, f)) > cutoff)


def _describe_path(p):
    """Identity of an input path: enough to notice it changed between two runs.

    Deliberately mtime+size, not a content hash -- a heatmap set is 749M and there are
    14 of them; hashing at startup would cost more than some of the runs do.
    """
    if not os.path.exists(p):
        return {'path': p, 'exists': False}
    st = os.stat(p)
    d = {'path': p, 'exists': True,
         'mtime': datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec='seconds')}
    if os.path.isdir(p):
        d['kind'], d['n_entries'] = 'dir', len(os.listdir(p))
    else:
        d['kind'], d['bytes'] = 'file', st.st_size
    return d


def _jsonable(v):
    """argparse values are not all JSON-serialisable (Path, numpy scalars, devices)."""
    if isinstance(v, (str, int, float, bool, type(None))):
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    return str(v)


def _copy_binary(src, dst):
    with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
        for chunk in iter(lambda: fsrc.read(1 << 20), b''):
            fdst.write(chunk)


def _consume_staged(staged, dest):
    """Delete a launcher-staged file once it is safely copied into the output dir.

    Staging is a hand-off point, not an archive: the copy sitting next to the results
    is the record, so leaving the original behind only fills provenance/ with
    duplicates. The byte-count check comes first -- a half-finished relay must never
    delete the only other copy.

    Not a complete cleanup: a run that dies between the launcher staging its files and
    log_run copying them leaves those files behind, and nothing collects them. The
    staging directory therefore accumulates orphans over time and deserves an
    occasional manual sweep.
    """
    if os.path.getsize(staged) != os.path.getsize(dest):
        return False
    try:
        os.remove(staged)
    except OSError:
        return False
    return True


def _write_uncommitted_patch(out_dir):
    """Persist the working-tree diff, so commit + patch reconstruct the code exactly.

    A warning alone loses the provenance it warns about. Falls back to the patch the
    launcher wrote on the host, since `git diff` is no more available in the container
    than `git status` is. Returns (filename_or_None, source_description).

    Caveat, deliberate: `git diff HEAD` covers tracked files only. Untracked files are
    named in run.json but their contents are not captured -- capturing them would mean
    mutating the index (`git add -N`), which a provenance call must never do.
    """
    dest = os.path.join(out_dir, 'uncommitted.patch')
    diff = _git('diff', 'HEAD')
    if diff is not None:
        with open(dest, 'w') as f:
            f.write(diff)
        return 'uncommitted.patch', 'git diff HEAD'
    handed = os.environ.get(GIT_PATCH_ENV)
    if handed:
        if not os.path.exists(handed):
            return None, ('UNAVAILABLE -- staged patch %s is gone; already consumed by '
                          'an earlier log_run in this launch?' % handed)
        _copy_binary(handed, dest)
        gone = _consume_staged(handed, dest)
        return 'uncommitted.patch', 'launcher: %s%s' % (
            handed, ' [staged copy removed]' if gone else ' [staged copy KEPT]')
    return None, 'UNAVAILABLE -- code state is NOT reconstructible from this record'


def _write_untracked_archive(out_dir):
    """Persist untracked files, which `git diff HEAD` cannot represent.

    Without this, commit + patch reconstruct only the tracked half of the tree. The
    index is deliberately never touched: `git add -N` would fold untracked files into
    the diff, but a provenance call must not mutate the repo it is recording.
    Returns (filename_or_None, source_description).
    """
    dest = os.path.join(out_dir, 'uncommitted_untracked.tar.gz')
    handed = os.environ.get(GIT_UNTRACKED_ENV)
    if handed:
        if not os.path.exists(handed):
            return None, ('UNAVAILABLE -- staged archive %s is gone; already consumed '
                          'by an earlier log_run in this launch?' % handed)
        _copy_binary(handed, dest)
        gone = _consume_staged(handed, dest)
        return os.path.basename(dest), 'launcher: %s%s' % (
            handed, ' [staged copy removed]' if gone else ' [staged copy KEPT]')
    listing = _git('ls-files', '--others', '--exclude-standard')
    if listing is None:
        return None, 'UNAVAILABLE -- no git binary and no launcher archive'
    names = [n for n in listing.splitlines() if n]
    if not names:
        return None, 'none -- no untracked files'
    try:
        r = subprocess.run(['tar', 'czf', dest, '-C', REPO_DIR, '-T', '-'],
                           input='\n'.join(names) + '\n', text=True,
                           capture_output=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return None, 'UNAVAILABLE -- tar could not be run'
    if r.returncode != 0:
        return None, 'UNAVAILABLE -- tar exited %d' % r.returncode
    return os.path.basename(dest), 'git ls-files --others | tar'


def log_run(out_dir, args, inputs=None):
    """Write run.json into out_dir: what code, what arguments, what inputs.

    Data under /nfs1/kmouts/DiffusionQC is never committed, so this file is the entire
    link between a directory of results and the code that produced it. Call it at
    startup, before the work -- an interrupted run still leaves a record of what it was.

    `args` is an argparse.Namespace or a dict. Any value in it that names an existing
    path (checkpoint, catalogue, heatmap dir) is stamped with mtime and size, so a
    catalogue quietly rebuilt between two runs is visible afterwards. `inputs` is a
    {name: path} dict for inputs that do not appear in args.

    The protocol is to commit before an experiment, so the run binds to a hash. A dirty
    tree warns rather than aborts -- killing a queued multi-hour GPU run over an edited
    .bak file would cost more than it protects -- but the diff is written alongside, so
    commit + uncommitted.patch still reconstruct the code that actually ran.
    """
    argd = _jsonable(vars(args) if hasattr(args, '__dict__') else dict(args or {}))

    # A value must contain a separator to count as a path, so that a mode string like
    # 'clean' cannot get stamped just because a file of that name sits in cwd.
    paths = {k: v for k, v in argd.items()
             if isinstance(v, str) and os.path.sep in v and os.path.exists(v)}
    paths.update(inputs or {})

    sha, branch = _head_commit()

    # Precedence: real git, else what the launcher captured on the host, else a guess.
    # Unset env is unknown; empty env is a positive statement that the tree was clean.
    porcelain, check = _git('status', '--porcelain'), 'git'
    if porcelain is None:
        porcelain = os.environ.get(GIT_STATUS_ENV)
        check = 'host env via launcher' if porcelain is not None else 'heuristic'

    dirty = None if porcelain is None else bool(porcelain.strip())
    lines = porcelain.splitlines() if porcelain else []
    heuristic = _sources_newer_than_index()

    os.makedirs(out_dir, exist_ok=True)
    patch_name, patch_source = (_write_uncommitted_patch(out_dir) if dirty
                                else (None, 'not needed -- tree clean'))
    untracked_name, untracked_source = (_write_untracked_archive(out_dir) if dirty
                                        else (None, 'not needed -- tree clean'))

    rec = {
        'date': datetime.datetime.now().isoformat(timespec='seconds'),
        'commit': sha,
        'branch': branch,
        'dirty': dirty,
        'dirty_check': check,
        'dirty_files': lines,
        'untracked_files': [l[3:] for l in lines if l.startswith('??')],
        'uncommitted_patch': patch_name,
        'uncommitted_patch_source': patch_source,
        'untracked_archive': untracked_name,
        'untracked_archive_source': untracked_source,
        'sources_newer_than_index': heuristic,
        'script': os.path.abspath(sys.argv[0]),
        'argv': sys.argv,
        'cwd': os.getcwd(),
        'host': socket.gethostname(),
        'out_dir': os.path.abspath(out_dir),
        'args': argd,
        'inputs': {k: _describe_path(v) for k, v in sorted(paths.items())},
    }

    if dirty:
        print("  WARNING: %d uncommitted change(s) [%s] -- commit %s does not describe "
              "this code" % (len(lines), check, (sha or '???')[:7]))
        print("           patch: %s (%s)" % (patch_name or 'NONE', patch_source))
        print("           untracked: %s (%s)" % (untracked_name or 'NONE', untracked_source))
        if untracked_name:
            n = os.path.getsize(os.path.join(out_dir, untracked_name))
            if n >= UNTRACKED_WARN_BYTES:
                print("           WARNING: untracked archive is %dMB -- check .gitignore"
                      % (n // 1048576))
    elif dirty is None and heuristic:
        print("  WARNING: no git and no launcher env; %d .py file(s) newer than the "
              "index -- tree may be dirty" % len(heuristic))
    if sha is None:
        print("  WARNING: could not read HEAD -- run.json will carry no commit hash")

    dest = os.path.join(out_dir, 'run.json')
    # Never silently discard an earlier run's provenance for the same directory.
    if os.path.exists(dest):
        stamp = datetime.datetime.fromtimestamp(
            os.path.getmtime(dest)).strftime('%Y%m%dT%H%M%S')
        os.rename(dest, os.path.join(out_dir, 'run_%s.json' % stamp))
    with open(dest, 'w') as f:
        json.dump(rec, f, indent=2)
    print("  run.json -> %s (commit %s)" % (dest, (sha or 'unknown')[:7]))
    return rec
