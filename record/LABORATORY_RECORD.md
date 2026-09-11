# Laboratory record — public curated edition

> This is the curated public edition of the laboratory record of the
> present study (conditioning-noise regularization; paper #2 of the
> project). All scientific entries — pre-registrations, reading rules,
> dated results, verdicts, corrections, and deviations — are verbatim.
> The development record of the companion study (arXiv:2608.30835) is
> not included here; it is documented through that publication and its
> own deposit. Passages concerning submission strategy, funding
> administration, and third-party coordination have been removed; each
> removal is marked inline ("[curated: ...]"). Provenance JSONs
> reference internal development-repository hashes; the Zenodo deposit
> is the public frozen witness of the exact released state.

## 12. HistoArtifacts (Zenodo 10809442) download and structure recon — 29 August 2026

Downloaded and MD5-verified (`a3f0cb9dae5f2bd04cbba707eb69edd4`, matches both the
request and Zenodo's own published checksum) to
`DiffusionQC/external/histoartifacts/`. No model run — pure structure reconnaissance
per the pre-registration rule, ahead of any evaluation-protocol freeze.

**Findings, all verified against the full population (not a sample):**

- 53,496 patches total, all 224×224 px RGBA, no dimension outliers anywhere.
- `fold` and `artifact_free` classes exist at both 20x and 40x; `blood`, `blur`,
  `bubble`, `damage` exist **only at 40x** in this release.
- **No slide ID or (x,y) coordinate encoding anywhere** — filenames are bare
  `{split}_{class}[_20x]_{sequential_index}.png` counters (checked against a
  coordinate regex and a slide-ID regex across every filename in every class: zero
  hits), PNG `tEXt`/`iTXt` metadata is empty on every sampled file, and the zip
  contains no sidecar CSV/JSON/manifest at all.
- **Consequence**: the requested contiguity analysis (same-class contiguous block
  size distribution, count reaching ≥4032×4032 px at 40x) **cannot be computed** —
  there is no coordinate system or slide identifier to key reconstruction on. Any
  evaluation protocol design that assumes recoverable WSI position from this dataset
  is a dead end; must design around isolated 224×224 patches, or find/request a
  metadata release from the authors.

Full report: `DiffusionQC/external/histoartifacts/structure_report_final.md`
(human-readable) and `structure_report.json` (machine-readable, per-class counts,
dimension histograms, metadata samples). Generator script:
`code/histoartifacts_structure_report.py`.

## 13. SlideInspect masks-first reconnaissance — 29 August 2026

Stage 1 downloaded only `manual_artifact/`, `manual_tissue/`, and
`ACTION_TEST.xlsx` from Kaggle `artemis90/slideinspect` (883 files; 138 MB
locally); the 31 GB `image/` tree was deliberately not downloaded. No model run.

- The release has 441 matched triplets (image, tissue mask, artifact mask), plus
  the xlsx. Filenames are `{STAIN}_{ORGAN}_{index}` rather than TCGA/TCIA IDs;
  zero of 441 matched the TCGA barcode regex or a TCIA literal pattern. The xlsx
  matches all 441 names but carries only scan dimensions, tissue area, predicted
  stain quality, and predicted action — no center/origin field.
- Artifact and tissue masks have matched HxW on every slide; their storage varies
  between grayscale and RGB containers, but RGB channels are identical. Artifact
  values are exactly `{0,85,170,255}`; tissue masks `{0,255}`. Critically, no
  legend in this release maps the nonzero artifact values to tissue-fold,
  out-of-focus, and mounting artifact: do not label them without checking the
  paper/authors.
- The H&E-only filter leaves 289/441 slides (152 IHC/PAS/TRIC excluded); the
  TCGA/TCIA exclusion is a no-op. Pixel-mass Kish effective n for values
  85/170/255 is 34.86/10.59/4.94 respectively. Value 255 is highly concentrated:
  the largest slide holds 42.6% and top four 62.9%; any later comparison must be
  paired and slide-level, never pixel-level. There are 55 clean H&E controls.
- Leave-one-slide-out decision table recorded provisionally for the 289 H&E
  survivors, following the project's development-benchmark convention; it is not
  frozen. Full report and machine-readable tables live in
  `DiffusionQC/external/slideinspect/`. Before protocol freezing, resolve the
  value-to-artifact-class mapping and explicitly ratify the fold scheme.

### Correction — 30 August 2026

The preceding LOOCV entry is a misreading of “fold/OOF GT”: it means **tissue-fold
and out-of-focus artifact ground truth**, not cross-validation folds. There is no
LOOCV, tuning, held-out assignment, or other CV procedure in the SlideInspect record;
the erroneous `fold_table_loo` was removed from the JSON and Markdown reports.

Six image/mask overlays (two H&E slides fully dominated by each nonzero label) give
the provisional visual mapping **85 = out-of-focus, 170 = mounting artifact,
255 = tissue fold**. Overlays are saved in
`DiffusionQC/external/slideinspect/class_mapping_review/`; the source release has no
legend, so this remains visual evidence pending author confirmation. The zero-TCGA/TCIA
result is likewise **filename-level evidence pending author confirmation**, not a
provenance claim.

## 14. GrandQC test set (Zenodo 14039591) MPP10 reconnaissance — 30 August 2026

No model run. MPP10 was downloaded, MD5-verified (`09ccbc43e0dafed3def455fb5dba801f`),
extracted, and every one of its 44,355 palette PNG masks was counted. Filenames have
UUID-like case IDs and explicit original-space tile coordinates (`x`, `y`, `w`, `h`),
but zero paths matched the TCGA barcode pattern and there is zero exact overlap with
the 42 active IDs from `train_test_split.json`: no split-leakage red flag.

- MPP10 contains 281 case folders and 44,355 512×512 GT tiles, despite the Zenodo
  description claiming 318 WSIs (78 breast + 80 each colon/kidney/prostate). This
  is an archive-vs-metadata discrepancy to retain in any protocol statement.
- Class mapping is authoritative from Zenodo/publication and already codified in
  `grandqc_eval.py`: 1 tissue, 2 fold, 3 dark spot/foreign, 4 penmark, 5 edge/air
  bubble, 6 out of focus, 7 background, with 0 ignore. At MPP10, class 4
  (penmark) and class 7 (background) have zero pixels across the entire release;
  neither can support an empirical test-set outcome.
- Pixel-mass Kish effective n: fold 48.50 (327,927,710 px); dark spot/foreign
  73.72 (73,085,710 px); edge/air bubble 40.00 (734,805,742 px); OOF 39.46
  (773,633,282 px). Largest-slide shares are 5.0%, 3.1%, 7.6%, and 6.6%,
  respectively. Full per-slide counts and organ-specific class coverage are in
  `DiffusionQC/external/grandqc_test/MPP10_inventory.{md,json}`.

### Provenance and archive-accounting follow-up — 30 August 2026

Every non-empty MPP10 case UUID (281) was queried against both GDC
`/files/{uuid}` and `/cases/{uuid}` endpoints at two requests/s: all 562 requests
returned 404, zero resolved. Together with the absent TCGA barcode strings, this is
strong API-level evidence of non-GDC/non-TCGA case IDs, though it does not positively
identify the originating institutions. Local accounting resolves the earlier 281/318
discrepancy only partially: 286 folders exist (Breast 80, Colon 80, Kidney 69,
Prostate 57) versus Zenodo's stated 78/80/80/80; five are empty placeholders (four
Breast, one Kidney), leaving 281 tile-bearing cases. Thus 32 folders are absent net of
the published total, concentrated in Kidney (-11) and Prostate (-23), while Breast is
+2. Image tiles are RGB JPEG and masks palette PNG, exactly paired (44,355 each);
assembly is not byte-exact because JPEG must be decoded, so later composite outputs
must be written losslessly to avoid adding fresh compression seams.

---

## 2026-08-27 — Colab notebook outputs are archival evidence, never to be stripped

`code/Colab/` was committed to git with every notebook's embedded outputs intact (34 MB,
of which `Module_9_Whole_Slide_Inference_2_1.ipynb` alone is 17 MB). The usual hygiene
argument for stripping outputs before committing does not apply here: those outputs are
the evidence that resolved the latent-cache provenance question, and they exist nowhere
else. Decision (Kostas, this date): commit as-is, never strip. The only exclusion is
`Colab/*.pdf` — a third-party cluster manual, kept on disk but gitignored as it is not
repo content.

Recorded here because the reasoning is invisible from the repository itself: a later
reader seeing 34 MB of output-laden JSON would otherwise be right to "clean it up".

---

## 2026-08-28 — banned numbers enumerated; ρ=0.893 given provenance; three open items

Written while auditing CLAUDE.md's citations against this file. CLAUDE.md is a derived
summary of these notes; where the two conflicted, CLAUDE.md was corrected and this file
was not. Three of its citations were stale or incomplete. Recorded here so the summary
can be rebuilt from the source if it drifts again.

### The banned numbers, all three

Reconstructed from the 24 Aug entries; confirmed by Kostas. §10's preamble refers to
"the third banned number" and the 24 Aug entries to "the two banned numbers", but the set
was never enumerated in one place — and `HANDOFF.md`, which §10's preamble names as
holding that summary, could not be found while this was written (it surfaced the same
day, and confirms the reconstruction; see open items).

They are one family — a statistic entangled with the thing it purports to measure — but
with three distinct defects, in `HANDOFF.md`'s own words: **partly definitional**,
**circular**, **tautological**. None is a doubt about the arithmetic.

1. **Spearman ρ=0.893** — `blur_severity.py:48`, `Spearman(saturation deficit, kept
   fraction)`. *Partly definitional*: the kept fraction is *determined by* the saturation
   gate, so the statistic correlates a quantity with a function of itself.
2. **The `tissue,unannot` row of `sv_profile.py`** — omitted from S3b on 24 Aug with the
   circularity stated. The mechanism survives as a structural property plus the median
   profiles (OOF s-median 26/35 vs Otsu 50/48).
3. **Any aggregate saturation∧value "both branches" share of the exclusion** — the gate
   is a disjunction, so exclusion ≡ failing both branches, making the "statistic" a
   tautology whose value is simply the full mask-attributable 40.7 points. The subtlety
   that makes this one easy to reintroduce by accident: **18.9 in that role is banned;
   18.9 as footprint∧pixel-mask (mask_decompose's own legend) is fine.** The 24 Aug entry
   "18.9 attribution resolved" turns on exactly this distinction.

### ρ=0.893 provenance

Until now the first banned number had no record in this file — the value appears nowhere
in these notes, only in CLAUDE.md, which is a summary and not a source. Its origin is
`blur_severity.py:48` and its ban rests on the circularity above. Recorded so the ban is
traceable to the source of truth rather than resting on a derived document.

### Open items

- **`HANDOFF.md` located** — absent when this audit ran, added to `docs/` the same day.
  §10's preamble is correct: it holds the rounding registry, the basis map and the
  banned-numbers list, and **its formulation of the three is authoritative**. The
  reconstruction above was written before it surfaced and then confirmed against it,
  third item included. Its characterisations are the ones adopted here: ρ=0.893 *partly
  definitional*, `tissue,unannot` *circular*, the both-branches share *tautological*.
- **One 24 Aug item is in `HANDOFF.md` but not in §10**: the "full end-to-end read —
  four findings, all closed; the 642-word condensation left no missing content". The
  source file it cites, `notes_2026-08-24_kish_reconciliation.md`, exists nowhere under
  `/nfs1/kmouts`, so the finding itself is unrecoverable from here. Every other bullet of
  HANDOFF's 24 Aug list maps to a §10 entry.
- **§10 carries a near-duplicate entry**: two blocks headed "2026-08-24 — 18.9
  attribution resolved; S3b filled", differing only in the wording of four lines. Left in
  place — this is an append-only log and neither copy is wrong.
- **13 vs 14 artifact slides is not an inconsistency.** 5o's survey counts at annotation
  resolution (14); the evaluation counts after coverage restriction (13), because
  `56-8628`'s 88 annotated px do not survive the mask. Established in the S1 entry of
  24 Aug. Noted again here because the two figures sit far apart in the file and read as
  a contradiction on a straight search.
- **The ~10k px fixture stands**, but its attribution is corrected inline at 8y: the
  convergence table is 5t Finding B, not 5u.

## §15. Dataset regime for the optimization phase — decided 30 August 2026

(Reconnaissance details and full inventories live in §§12–14; this section records
the decision layer built on them.)

Written after a three-day verification campaign over the candidate external datasets
(guide document: "Οδηγός Datasets Τεχνουργημάτων"). Every load-bearing claim below was
verified at source (Zenodo/Kaggle records, the papers themselves, or direct inspection
of downloaded data); the guide proved unreliable in two places (see corrections). All
reconnaissance was model-free: structure, metadata, and mask statistics only.

### The disqualifying fact: PixCell's pretraining corpus

Our backbone (PixCell-1024) is trained on PanCan-30M, which includes **TCGA diagnostic
11,766 + TCGA frozen 18,310 WSIs (~13M patches)**, plus CPTAC, GTEx, NLST, an ovarian
proteogenomic cohort, and SBU internal data (verified in the PixCell paper). Therefore
no TCGA/CPTAC/GTEx-derived dataset can serve as an unseen confirmatory set for any
detector built on this backbone. This disqualifies: TGCA@Focus, Kumar/CPM-17, the
TCGA-PRAD artifact subset, and any TCGA/TCIA portion of mixed cohorts. It also means
the AIRAQC development benchmark itself carries an inherited backbone-saw-the-slides
caveat (present in the original DiffusionQC design too; paired comparisons on the dev
benchmark are unaffected since both arms share it).

### Corrections to the guide (verified at source)

- **HistoArtifacts has no marker/pen class.** Zenodo 10809442 lists exactly five
  artifact classes (blur, blood, air bubbles, folded tissue, damaged tissue) plus
  artifact-free. The guide's "Marker" entry is wrong.
- **The TCGA-PRAD artifact subset is slide-level only**: 240 WSIs labeled by category
  (120 artifact-free; 40 each staining / OOF / "usability", the last lumping folds,
  dark spots, pen marks, bubbles, contaminations). No pixel or patch labels. Doubly
  unusable for us (TCGA + wrong annotation granularity).

### The penmark finding (tri-source, negative)

No public pixel-level dataset contains usable penmark ground truth:
HistoArtifacts — class absent; SlideInspect — merged into "mounting artifacts"
(paper states this explicitly in its limitations); GrandQC test set — class defined
in the schema (value 4) but **0 annotated pixels** across all 281 cases. Penmark
confirmatory claims therefore depend entirely on new annotation (PRODIGY route).
Given penmark is our largest reproduction divergence (0.526 vs 0.866), this is a
planning-critical fact and a citable observation in its own right.

### The adopted regime

Training/validation and the development benchmark are **unchanged** (AIRAQC/TCGA
16+2 train/val, 24-slide dev benchmark under the §8y regime): comparability with the
original and with our submitted paper wins; experiment 8d operates within the 16
training slides.

Confirmatory tiers are frozen-on-arrival: md5-verified, read-only, untouched by a model
before the corresponding protocol is pre-registered, then evaluated once.

**Tier 1 — GrandQC test set (Zenodo 14039591) = primary confirmatory.**
Weng/Tolkach, Nat Commun 2024; CC-BY-NC-SA 4.0; 5.4GB in three renders (MPP 1.0 /
1.5 / 2.0 µm/px). MPP10 inventory (measured, not as advertised): **281 non-empty
cases** — the record claims 318 (286 folders: Breast 80, Colon 80, Kidney 69,
Prostate 57; 5 empty) — 44,355 paired 512×512 RGB-JPEG tiles + palette PNG masks.
Kish effective n: fold **48.5** (149 slides, top share 5.0%), edge-air-bubble **40.0**
(94), OOF **39.5** (185), dark-spot-foreign **73.7** (188), versus 6.2 on the dev
benchmark. Native MPP 1.0 is approximately the 10× operating point; no resampling
protocol is needed. Tile filenames encode WSI-space x,y,w,h, so genuine adjacency exists
(2×2 assembly to 1024px possible; outputs must be lossless since sources are JPEG).
Provenance: 0 TCGA barcodes, 0 overlap with the 42 AIRAQC IDs, and all 281 UUIDs return
404 from both GDC `/files` and `/cases`: strong API-level evidence of institutional
(non-GDC) origin, pending author/Methods confirmation. Value 0 is IGNORE (3.0B px);
clean is positive tissue (1), the inverse of AIRAQC's implicit-clean convention.

**Tier 2 — SlideInspect public test set (Kaggle artemis90/slideinspect) =
cross-domain confirmatory for OOF + clean-FP control + 5× scale probe.**
441 flat 5× PNG renders (31GB) plus pixel masks (142MB, downloaded) and output xlsx.
After filters: 289 clinical H&E slides (TCGA/TCIA patterns: 0 filename-level hits;
non-H&E: -152), with 89% in prostate/breast/liver/colon. Provisional visual mapping:
85=OOF, 170=mounting, 255=fold, pending author confirmation. OOF n_eff **34.9**
(153 slides) is strong; mounting-merged **10.6** (36) is secondary; fold **4.9** with
one slide at 42.6% is not quantitatively confirmable. There are 55 clean controls.
Because 5× is 2× coarser than native, use is gated on scale calibration.

**Tier 3 — HistoArtifacts (Zenodo 10809442) = patch-level supplementary.**
53,496 md5-verified 224×224 RGBA patches from the EMC bladder cohort: 40× blood 26,925,
blur 7,552, bubble 4,520, damage 3,922, fold 1,243, artifact-free 7,805, plus 1,529
20× fold/artifact-free patches. There are no slide IDs, coordinates, or metadata; use
isolated-patch classification only at 40×, gated on the same scale calibration.

**Tier 4 — PRODIGY clinical annotation = penmark + truly-clinical OoD.**
This is the only route to penmark confirmatory GT and pixel-level WSI evaluation on
never-public clinical material. NBPC access is the strategic option to explore.

Rejected: NCT-CRC (debris/stroma taxonomy), FocusPath (OOF-only), and all TCGA-family
sets (leakage). Fırat tissue-fold teaching-slide dataset (Zenodo 21493260;
pixel-level fold masks at 10×, CC-BY, slide mapping provided) — examined 31 Aug,
not adopted: veterinary/teaching-slide domain and fold-only coverage add nothing over
Tier 1's fold n_eff 48.5 on human clinical material; retained as a possible
fold-specialist OoD probe if generalization-limit questions arise later.

### Cross-cutting protocol obligations

1. Scale-calibration pre-experiment on dev data: render the 24 slides at 5× and extract
   40× patches from annotated regions; decide Tier 2/3 protocols before confirmation.
2. GrandQC handling: exclude value 0; clean := tissue.
3. Confirmatory sets are evaluated once with pre-registered predictions per set/type;
   no LOOCV or tuning ever runs on them.
4. Licenses: GrandQC CC-BY-NC-SA; HistoArtifacts CC-BY; SlideInspect pending reply.

### Open items

- Salvi reply (mapping/provenance/license); GrandQC Methods provenance line; optional
  Kanwal coordinate-manifest query.
- The 32-folder shortfall versus Zenodo's stated count.
- Dark-spot palette lead: test AIRAQC annotations at exact RGB `(255,0,255)`, distinct
  from the `(128,0,128)` 5r decoder entry.
- MPP15/MPP20 remain archived for the scale axis; low-priority class-presence sanity
  check across renders.
- **Self-conditioned scoring blocker (31 Aug):** PixCell's conditional route is
  mechanically defined and compatible with the current LoRA architecture: a 1024px
  patch becomes 16 UNI2-h subpatch embeddings of 1536 dimensions, projected to 1152
  cross-attention states. However, `MahmoodLab/UNI2-h` weights are absent from every
  DGX/host/container/deposit cache searched. The required repo is HF-gated under
  CC-BY-NC-ND 4.0 and requires individual institutional-email access/term acceptance;
  no synthetic conditional dry run was run because its stated availability precondition
  failed. Full model-free recon: `DiffusionQC/provenance/pixcell_self_conditioning_recon.{md,json}`.

### Dark-spot palette result — 30 August 2026

The exact-value audit was run over all 42 active AIRAQC annotation PNGs (16 training,
24 development-test, 2 unused), after RGB conversion and with no nearest-colour
assignment: **zero pixels on every slide equal `(255,0,255)`**, hence zero total. The
GrandQC dark-spot/foreign palette does not recover a dark-spot class in our AIRAQC GT;
the 5r/5m conclusion remains unchanged. Per-slide zero counts and method details are in
`DiffusionQC/provenance/airaqc_darkspot_exact_255_0_255.{md,json}`.

## 2026-08-31 — UNI2-h acquired; conditional path dry-run; validation embedding cache built

Resolves the "Self-conditioned scoring blocker (31 Aug)" bullet in §15's Open items,
which is left in place per the append-only rule and is superseded by this entry.
Section 6 of `DiffusionQC/provenance/pixcell_self_conditioning_recon.md` carries the
same supersession note for the recon's own §3 and §5.

Three steps ran, in order, each committed before it ran. **All three are input
preprocessing and mechanical verification. No error was computed, no clean-vs-artifact
contrast was formed, and no effect size was produced.** The self-conditioned diagnostic
that will consume this cache is a pre-registered experiment and is *not yet
pre-registered*; nothing below may be read as evidence about it.

### Step 1 — encoder acquired and pinned

Producer `uni2h_fetch.py`; output
`DiffusionQC/provenance/uni2h_fetch_MahmoodLab-UNI2-h_rev-d517a8dd/uni2h_fetch.json`.
15/15 pre-registered checks passed.

Individual gated access to `MahmoodLab/UNI2-h` was granted to HF account `kmouts`. The
repository is pinned at revision `d517a8dd47902dd7c308b3c36f63bce47e7b9a43`, not at
`main`, so every embedding below binds to a fixed encoder.

| file | bytes | sha256 |
|---|---|---|
| `pytorch_model.bin` | 2,725,669,217 | `6e077eda234bebc595868d918d3458d9dd32a050199b0ff04443b2f46a0a3b1e` |
| `config.json` | 587 | `8b207fbff3e34884fd225b2d52e8ff51b728a1d0ac2fe8bb2b8db8011308ac98` |
| `README.md` | 12,253 | `d0c283892c0fddc0b5571c02d37ff7c923647b6381c3f2fcd970a3484322b244` |

The locally computed sha256 of the weight file agrees with the Hub's own published LFS
sha256 for that revision. Weights live only in
`/nfs1/kmouts/.cache/huggingface/hub/models--MahmoodLab--UNI2-h`; they are not in git
and not in the Zenodo deposit.

**Licence.** UNI2-h is **CC-BY-NC-ND 4.0**: non-commercial academic research only, with
attribution; commercial use requires prior approval; distributing, publishing, or
reproducing a copy of the model is prohibited; each organisational user registers
individually. PixCell carries the same licence and states that it is itself subject to
the UNI2 terms, being conditioned on UNI2-h embeddings. Any manuscript using this path
must attribute both and must not redistribute either.

**Correction made before anything downstream used it.** The first version of the
`timm_kwargs` extractor grabbed the leading number of each field, recording
`init_values: 1` (the value is `1e-5`) and `mlp_ratio: 2.66667` (the value is the
**product** `2.66667*2 = 5.33334`). A record like that rebuilds a *different* encoder
without complaining. The extractor now keeps only fields that parse as exact literals
and holds the rest as source text plus a resolved value. Verbatim kwargs are in recon
§6.2. **`mlp_ratio` is 5.33334 and must never be transcribed as 2.66667.**

### Step 2 — synthetic conditional-path dry run (the one deferred in recon §5)

Producer `pixcell_cond_dryrun.py`; output
`DiffusionQC/provenance/dryrun_dgx_basic_step1000_B2/pixcell_cond_dryrun.json`.
13/13 pre-registered predictions passed. UNI2-h is deliberately *not* used here: the
point was to check the DiT side alone, with a random tensor standing in for a real
embedding. No slide, no dataset patch.

Under `dgx_basic/checkpoints/step_1000` (448 LoRA keys loaded), a random FP32
`(2,16,1536)` condition plus a synthetic `(2,16,128,128)` latent at t=800 gives a
finite FP32 `(2,32,128,128)` output that chunks to `(2,16,128,128)` — the split
`infer_wsi.py` relies on. Peak VRAM 3.07 GiB. `get_unconditional_embedding(2)` returns
`(2,16,1536)` FP32, so a cache row is drop-in for the learned null.

Two conditions differing only in their random values gave different outputs (max abs
delta 0.436), which establishes only that the condition reaches cross-attention rather
than being silently dropped. **That number is synthetic-vs-synthetic noise. It is not an
error, not a score, not a comparison of anything real, and must never be cited.**

**Caveat worth recording.** A wrong token count *is* rejected, but incidentally: it
surfaces as a broadcast `RuntimeError` inside `y_pos_embed` ("size of tensor a (8) must
match tensor b (16)"), not as a validation. The pipeline's real `check_inputs()` guard
on `(B,N,D)` lives on the `__call__` path, which our scoring code does not use — it
calls `pipe.transformer(...)` directly. So a malformed condition that happens to
broadcast would pass unremarked. Our contract is exactly 16x1536, so this does not bite
now, but it is not a safety net.

### Step 3 — UNI2-h embedding cache for the 1,427 validation patches

Producer `uni2h_embed_val.py`; output directory
`DiffusionQC/dgx_shared/latents/uni2h_emb_val1427_rev-d517a8dd/`
(`embeddings.pt`, `manifest.json`, `run.json`). 15/15 pre-registered checks passed.

`(1427, 16, 1536)` FP32 = 140,279,808 payload bytes = **133.8 MiB**, exactly the recon
§4 estimate; 140,458,795 bytes on disk with the manifest and metadata embedded. Built
from `dgx_catalogs/val_clean.json` (1,167) then `dgx_catalogs/val_artifact.json` (260),
each in catalogue order; every row carries `(slide, x, y, level)` plus its split and
catalogue index. The `(slide,x,y,level)` key is unique across *both* catalogues — zero
cross-split collisions — so a triple identifies a patch unambiguously.

Contract, verified against the assets themselves rather than the recon's transcription:
patches are read exactly as `common.py` reads them
(`read_region((x*level_downsample, y*level_downsample), level, (1024,1024))`), split
**row-major** into a 4x4 grid of 256px subpatches — token *k* is the crop at row `k//4`,
column `k%4` — then transformed to 224px with ImageNet normalization and encoded
independently.

- The row-major order is the PixCell-1024 card's
  `rearrange('(d1 h) (d2 w) c -> (d1 d2) h w c', d1=4, d2=4)`, and it is the order the
  transformer's 4x4 2-D sincos `y_pos_embed` assumes (`meshgrid` reshaped `[2,1,H,W]`,
  flattened row-major). **It is not interchangeable with column-major.** `einops` is not
  installed in the container, so the split is implemented twice by different means
  (numpy reshape/transpose, and an explicit crop loop) and asserted equal on all 1,427
  patches; they agreed everywhere.
- The encoder is built by the card's `pretrained=False` route and loaded
  `strict=True` from the step-1 sha-verified bytes — 681,394,176 parameters — so it
  binds to verified bytes rather than to a hub re-resolution.
- The transform is resolved from the shipped `pretrained_cfg` in `config.json`, **not**
  from the model object: built with `pretrained=False` the model carries timm's generic
  `vit_giant_patch14_224` defaults, whose mean/std are not ImageNet. Resolved config is
  `input_size [3,224,224]`, `bilinear`, `crop_pct 1`, mean `(0.485,0.456,0.406)`, std
  `(0.229,0.224,0.225)` — identical to the card's hand-written transform, and with
  `crop_pct 1` the added `CenterCrop(224)` is a no-op on an already-square subpatch.

**No discrepancy against the recon in shapes or normalization**; nothing triggered the
stop-and-report condition.

### Corrected measurement: the recon's throughput estimate was optimistic

Recon §4 offered "about 1--5 minutes on one A100 at crop batch 16--32" as an explicitly
non-measured planning figure, to be replaced by a timed run. The measurement:
**940.5 s (15.7 min)** for 1,427 patches = 22,832 crops at 2 patches (32 crops) per
forward, i.e. **~24.3 crops/s**, peak VRAM 3.30 GiB. That is **3--15x longer than the
planning range**, which stands as a caution against carrying unmeasured estimates
forward. The cost is dominated by per-patch WSI `read_region` and CPU-side transforms,
not by the encoder; VRAM is a non-issue on a 40GB A100.

### Two caveats about the cached set itself, which constrain any future diagnostic

1. **The 1,427 patches come from two slides, not many.** Both catalogues draw on
   `TCGA-34-5232-01Z-00-DX1...` and `TCGA-BH-A0H5-01Z-00-DX1...` only (clean 417 / 750;
   artifact 123 / 137). Effective n at the slide level is 2. This is the *validation*
   pool used for model selection during training (Gaps 5x), not the 24-slide development
   benchmark, and the §8y regime applies to it no differently.
2. **The artifact side is two types plus a singleton**: air-bubble 134, out-of-focus
   125, **penmark 1**. No fold, no dark-spot, no knife-line, no coverslip. Any per-type
   reading of this pool is impossible for five of the seven types and meaningless for
   penmark.

### Protocol nit

All three runs were launched with `singularity exec` directly rather than through
`run.sh`/`runbg.sh`, so `git` was unavailable inside the container and `log_run` fell
back to its heuristic: `run.json` records `dirty: null`, `dirty_check: "heuristic"`,
`sources_newer_than_index: []`. The tree genuinely was clean — each script was committed
before it ran, and `git status` was empty before and after — but the run records state
that only as "unknown", not as a positive host-side assertion. Use the launchers next
time so the host-side clean statement is captured.

## §16. Pre-registration — experimental battery of 1 September 2026

Written before any experiment in the battery runs. Basis: the §8y evaluation regime,
the §15 dataset regime, and 5w as the template (predictions recorded before running,
controls named as controls). **Execution is selective**: which experiments actually run,
and in what order, is decided along the way. What this section fixes is that any
experiment below that *does* run, runs exactly as its block specifies; any deviation is
a new dated pre-registered decision logged here, not a silent adjustment. Predictions
bind per experiment at the moment it launches, and are additionally embedded in each
producer script before it runs. All launches go through `run.sh`/`runbg.sh` — the §15
protocol nit is hereby a rule, so host-side clean-tree assertions are always captured.

### E1. Self-conditioned scoring diagnostic (GPU, hours)

**Question.** Does conditioning PixCell on the patch's own UNI2-h embedding (cache
`uni2h_emb_val1427_rev-d517a8dd`, 2026-08-31 entry) change the clean-vs-artifact
separation of noise-prediction error, relative to the learned null embedding?

**Design.** Three model arms × {uncond, self-cond}, **paired per patch**: identical
cached latent and identical noise ε (fixed seed, recorded) in both conditions, so the
per-patch difference is a pure conditioning effect. Arms: `dgx_basic/step_1000`,
`dgx_variantA/step_1000`, and **PixCell base without LoRA**. The third arm isolates the
known caveat that the LoRA adapters were trained only under the null embedding: LoRA
arms measure conditioning + adapter mismatch jointly; the base arm measures conditioning
alone. Timesteps: t ∈ {500, 650, 800}. Metrics: relative separation gap and Cohen's d
on the validation pool (1,167 clean / 260 artifact); per-type only air-bubble (n=134)
and out-of-focus (n=125). **Penmark (n=1) is excluded by rule.** The pool spans 2 slides
(slide-level n_eff = 2): no slide-generalization claim of any kind. Per §8y(2) this is a
patch-level **filter** on what earns a slide-level evaluation, never a verdict (5y
Finding 4 standing caveat applies).

**Predictions.**
- P1 (control): paired Δerror ≠ 0 for essentially all patches — the condition reaches
  cross-attention (mechanically established by the 31-Aug dry run; magnitude unknown,
  and the dry run's 0.436 remains never-citable).
- P2 (hypothesis): self-conditioning lowers clean error more than artifact error, so gap
  and d increase, at the model's informative timesteps.
- P3 (discriminator): if adapter mismatch dominates, LoRA arms show Δd < 0 while the
  base arm shows Δd > 0. This pattern separates the two hypotheses; that separation is
  the point of the three-arm design.

**Decision rule (frozen).** Advance to step (β) — LoRA retraining with self-conditioning
— only if Δd ≥ +0.2 for at least one (arm, t) AND neither per-type d falls by more than
0.1. Otherwise: log and stop.

**Obligations.** UNI2-h and PixCell are CC-BY-NC-ND: any manuscript using this path
attributes both and redistributes neither.

**Amendment, 1 September 2026 (pre-launch, before the producer script exists).**
AUROC (rank-based, Mann-Whitney-equivalent, no density estimation) is added as a
pre-registered *secondary* metric, reported per (arm, t, condition) alongside gap and
d — pooled and for the two admissible types. Rationale: d assumes roughly symmetric,
comparable-variance distributions; reconstruction errors are expected right-skewed,
and AUROC is exactly threshold-achievable separability. KL/JS were considered and
rejected: they require density estimation (binning/bandwidth = an undeclared degree
of freedom) and KL is asymmetric and unbounded on disjoint supports. **The decision
rule is unchanged and remains on Δd**; any sharp d-vs-AUROC disagreement is logged as
a finding, not used to revisit the decision.

**Pre-step note, 1 September 2026 (pre-launch).** The pre-registration assumed all
inputs cached. Inventory before writing the producer found: no full clean validation
latent cache exists (only 96-patch subsamples), and `val_artifact.pt` (260) carries
`means/stds` with no per-row keys, so its correspondence to the embedding manifest
would rest on catalogue-order convention. Decision: a preprocessing step rebuilds both
validation latent caches (1,167 + 260) with an explicit `(slide, x, y, level)` manifest,
and the E1 producer joins latents to embeddings by key equality assertions, never by
order. This is input preparation, not scoring; no error is computed and no
clean-vs-artifact contrast is formed by the pre-step.

### E1β. Conditioning-aligned LoRA retraining (added 1 September 2026, post-E1)

Pre-registered after E1's results and before any E1β code exists. Motivation:
E1's gate opened at the boundary (variantA t=650, Δd = +0.2024, single seed)
with the P3 signature inverted — benefit appears only as a conditioning × LoRA
interaction, on adapters that never saw a real embedding during training. E1β
asks the question E1 could not: does aligning the adapter with the scoring
regime enlarge that signal?

**Training arm.** One new run, `basic_selfcond`: identical to the existing
basic run in every respect — same trainer, same 2,185 gated clean patches,
same seed, same 1000 steps, batch 4, λ=0 — with a single change: during
training each patch is conditioned on its own UNI2-h embedding instead of the
learned null. Any difference against basic is attributable to conditioning
alone.

**Pre-step (input preparation, not scoring).** No embedding cache exists for
the 2,185 training patches. `uni2h_embed_train.py` builds it on the validation
producer's template: same pinned encoder revision `d517a8dd`, same row-major
4×4 grid contract, keyed manifest, C-style checks (catalogue count, key
uniqueness, shape/dtype, transform config). Estimated ~205 MiB, ~20–25 min at
the measured 24.3 crops/s.

**Evaluation.** The full 2×2 at patch level: {basic, basic_selfcond} ×
{uncond, self-cond scoring}, t ∈ {500, 650, 800}, noise seed 0, the E1 paired
protocol unchanged (`selfcond_diag.py` extended with the new checkpoint; the
basic row of the table is already measured by E1 and is not re-run). Cell (a),
deployment: basic_selfcond scored self-cond vs basic scored uncond — each
model in its natural regime. Cell (b), mechanistic: basic_selfcond scored
uncond vs basic scored uncond — whether conditioned training helps even
without conditioning at inference (regularizer effect).

**Predictions.**
- Q1 (from E1's reading): the deployment benefit, if any, appears at mid-t
  (650), not at 500 where conditioning hurt every arm.
- Q2: alignment enlarges the interaction — the deployment Δd at its best t
  exceeds E1's misaligned +0.2024.
- Q3 (mechanistic null): scored uncond, basic_selfcond ≈ basic (|Δd| < 0.1);
  a violation means conditioned training changed the backbone's clean model
  itself, not just its conditioning response.

**Decision rule (frozen, E1 thresholds carried over).** basic_selfcond earns
a slide-level evaluation only if the deployment comparison shows Δd ≥ +0.2 at
some t AND neither admissible type (air-bubble, out-of-focus) drops its d by
more than 0.1. Penmark (n=1) excluded; AUROC remains the secondary metric;
§8y(2) filter status and the 2-slide pool caveat apply unchanged.

**Cost.** One training run of the existing scale, ~25 min of embedding
extraction, one diagnostic run smaller than E1. Whether E1β actually runs
remains a selection decision under §16's status paragraph.

### E1γ. Seed-robustness of the Q3 violation (added 1 September 2026, post-E1β)

Pre-registered before either run starts. Target claim under test: E1β's Q3
violation — scored uncond at t650, basic_selfcond exceeds basic by Δd = +0.325.
Both sides of that comparison are single training seeds; the seed variance of
patch-level d has never been measured. Two runs, in parallel:

**R1 (noise scale, no training).** Uncond-only diagnostic on variantA and
variantA_seed7 (same recipe, seeds 42/7), t ∈ {500, 650, 800}, noise seed 0,
the E1 paired protocol. The per-t |d(variantA) − d(variantA_seed7)| is the
first empirical estimate of seed-induced d dispersion, denoted s_seed(t).
Recorded per-type as well (admissible types only).

**R2 (independent replication, one training).** `basic_selfcond_seed7`:
identical to basic_selfcond except `--seed 7` (which also selects the seed-7
artifact sample, as in variantA_seed7 — inert under λ=0 but kept for exact
recipe symmetry). Then the uncond-only diagnostic on its step_1000.

**Predictions.**
- R1-P: s_seed(650) < 0.16 pooled — i.e. the +0.325 exceeds twice the seed
  noise. If s_seed(650) ≥ 0.16, the Q3 violation is declared unresolved at
  patch level regardless of R2's outcome.
- R2-P: basic_selfcond_seed7 scored uncond at t650 exceeds basic's 1.340 by
  more than s_seed(650); direction alone (any positive excess) is necessary
  but not sufficient.
- Decision (frozen): the train-conditioned/score-uncond candidate earns
  slide-level evaluation only if BOTH R1-P and R2-P hold. Otherwise: log,
  and the candidate waits for more seeds or dies here.

Caveats carried: single comparison pool (2 slides), §8y(2) filter status,
basic itself remains one seed (the check bounds seed noise, it does not
average it away).

### E1δ. Slide-level evaluation of basic_selfcond (added 2 September 2026, post-E1γ/E3)

Pre-registered before the evaluation runs; heatmaps (24 slides × t650/t800)
already produced by `infer_wsi` (uncond scoring — the deployment regime E1γ
earned). Protocol: **partition-honest LOOCV only** — the E3 baseline arm; the
grid-max sweep is not consulted (its ≈0.016 optimism was quantified the same
day). Producer: `loocv_union.py` extended with a `baseline650` arm (masks from
t650, same menu construction) and a `--no-union` mode; rule U is not run
(rejected in E3).

**Noise scale.** `variantA_seed7` (t800 heatmaps exist) is evaluated
baseline-only under the identical protocol; s_slide := |honest F1(variantA) −
honest F1(variantA_seed7)| at t800 is the first slide-level honest-LOOCV seed
dispersion measurement. variantA t800 honest = 0.684 from E3.

**Decision rule (frozen).** The train-conditioned/score-uncond candidate is
declared slide-level-successful iff honest LOOCV pooled F1 of basic_selfcond
at t650 or t800 exceeds basic_nofa's 0.657 by more than s_slide. Per-type
held-out sensitivities and clean-slide FP are reported alongside; penmark is
reported but any claim defers to the known GT caveats.

**Predictions.**
- D1: at t800, basic_selfcond ≈ basic within s_slide (patch-level t800 deltas
  sat inside seed noise).
- D2: the candidate's chance lives at t650; no honest t650 pooled number has
  ever been measured, so its absolute level is genuinely unknown — recorded
  as such before looking.
- D3 (risk): the 5× patch→slide discount (5y) applies; a +0.26 patch-level d
  excess may not survive pooling at all.

Caveats: n_eff ≈ 6.2 over 13 artifact slides — all comparisons exploratory on
the development benchmark; §8y in force.

**E1γ addendum, 2 September 2026 (pre-launch).** A third training seed of
basic_selfcond (`--seed 123`) is added to the E1γ line, motivated by the
paper-#2 roadmap (three seeds give a rudimentary interval for the uncond-t650
excess: s42 +0.325, s7 +0.259, s123 pending). Identical recipe otherwise; the
seed-123 artifact sample cache will be built by the trainer (inert under λ=0,
kept for recipe symmetry). Evaluation: uncond-only diagnostic at step_1000,
same protocol; the number joins the E1γ record without changing its verdict
rule (already resolved).

### E1ε. Slide-level seed spread of basic_selfcond (added 2 September 2026)

Pre-registered before any run. Extends E1δ (one seed, s42, honest t800 =
0.6764) across the two remaining trained seeds — heatmap production
(`infer_wsi`, t800 only; t650 was shown unusable at slide level in E1δ) for
`basic_selfcond_seed7` and `basic_selfcond_seed123`, then the E1δ protocol
verbatim: honest LOOCV baseline arm, no union, same menu construction.

**Measurement, not a new gate.** The E1δ verdict stands on its own rule;
this entry measures its seed robustness. Declared reading: the finding is
**seed-robust** if all three seeds' honest t800 F1 exceed basic's 0.657 by
more than s_slide = 0.0112; **mixed** if some do; **fragile** if only s42
does. Prediction (recorded): the three-point spread is of order s_slide
itself, and all three clear the bar — the patch-level excess was
seed-stable (E1γ), and D1's favorable violation suggested the effect
survives pooling.

### E1ζ. Shuffled-conditioning ablation (added 3 September 2026)

Pre-registered before any code exists. Question: is the E1β regularizer
effect driven by the *content* of the conditioning (each patch seeing its
own UNI2-h summary) or merely by non-null conditioning *variance*?

**Arm.** One training run, `basic_shufcond`: identical to basic_selfcond
in every respect (same 2,185 patches, seed, 1000 steps, λ=0, same
embedding cache) except the patch→embedding assignment is a fixed random
permutation of the training set (derangement not enforced; permutation
seed 0, recorded) — each patch trains under a *wrong but real* embedding,
preserving the marginal embedding distribution while destroying content
correspondence. Trainer change: a `--selfcond-shuffle` flag applying the
permutation at load, after the key-equality assertion (so the join proof
still runs against the unpermuted manifest).

**Evaluation.** Uncond-only diagnostic at step_1000, t ∈ {500, 650, 800},
noise seed 0 — the E1γ instrument verbatim.

**Predictions.**
- Z1 (content hypothesis, favored): the uncond-t650 excess over basic
  vanishes or shrinks below s_seed(650)=0.126 — shuffled conditioning is
  noise the model learns to ignore, ≈ basic.
- Z2 (variance alternative): the excess persists ≥ 2× s_seed, i.e.
  conditioning acted as an unstructured regularizer; the UNI2-h encoder
  is then replaceable by far cheaper randomness — deployment-relevant.
- Either outcome sharpens the paper-#2 mechanism section; neither gates
  Tier 1 (already independently scheduled).

**Cost.** One training (~2 h) + minutes of diagnostic.

### E1η. Synthetic-variance conditioning (added 3 September 2026; opens the paper-#2 line β)

Pre-registered before any code. E1ζ established that conditioning benefit
is variance- not content-driven (shufcond ≥ selfcond). Question: does the
*encoder itself* matter, or only the statistical shape of the conditioning
signal? If synthetic embeddings suffice, UNI2-h leaves the training
pipeline entirely — the strongest deployment form of the finding.

**Arm.** `basic_synthcond`: identical recipe to basic_selfcond except the
embedding tensor is replaced by synthetic samples — per-token-position
diagonal Gaussian (mean, var over the 2,185 real embeddings at each of the
16 token positions), 2,185 draws, sampling seed 0, saved as a cache with
the same interface. Simplest-hypothesis-first: no covariance, no PCA; if
it fails, structured variants are the next rung (their own entries).

**Evaluation.** Uncond diagnostic at step_1000, t ∈ {500,650,800}, noise
seed 0 — the E1γ/E1ζ instrument verbatim.

**Reading (frozen).** H1 (encoder-free): uncond-t650 excess over basic
≥ 2× s_seed(650) — the line advances on synthetic conditioning. H0: excess
< s_seed — real-embedding structure matters; synthetic line closes, and
the deployment claim stays at "content-free, encoder still required".
Between: recorded as inconclusive, one more seed before any call.

**Confirmatory discipline (declared now).** Any second look at GrandQC for
this line is reserved for its FINAL configuration vs basic, under a new
protocol entry with a two-look multiplicity correction (97.5% CI).
Intermediate rungs are dev-tier only. Hypotheses motivated by Tier 1's own
findings (e.g. per-type operating points for the fold collapse) are
excluded from GrandQC confirmation and directed to Tier 2 or fresh sets.

**E1η addendum, 3 September 2026 (pre-launch, before the seed-42 diagnostic
has run).** A second training seed of basic_synthcond (`--seed 7`) is
launched on the idle GPU while seed 42 trains: it is required under H1
(seed robustness before any confirmatory consideration) and under the
intermediate outcome (explicitly, per the E1η reading rule), and is wasted
only under a clean H0 — a favorable expected cost for otherwise-idle
hardware. Identical recipe; same synthetic cache (the perturbation is the
cache's content, so seeds vary training stochasticity, not the synthetic
draw — recorded as a design note: a *fully* independent replicate would
also redraw the Gaussian sample; if the line advances, one such redraw
joins the ladder under its own note). Evaluation joins the E1η record.

### E1θ. Synthetic-conditioning ladder: redraw control + variance scale (added 3 September 2026, pre-launch)

Pre-registered before any code change. Two questions on the E1η line, run
overnight one-per-GPU; remaining ladder points follow by day.

**Arm 1 — independent redraw (control).** `basic_synthcond_draw1`: recipe
identical to basic_synthcond (training seed 42) except the Gaussian cache
is redrawn with sampling seed 1. Closes the one random element the two
E1η seeds shared. Reading: excess within the E1η band (+0.37…+0.44 ±
s_seed) → the draw is not special, control passes; materially outside →
the shared-draw caveat becomes a finding and the line pauses for a third
draw.

**Arm 2 — variance scale ×2 (first ladder point).**
`basic_synthcond_var2`: same, but synthetic std doubled (sd multiplier
2.0, draw seed 0). Hypothesis: if the mechanism is
perturbation-as-regularizer, effect strength has an intensity optimum the
UNI2-h statistics hit only by accident; a larger effect — line β's
declared goal — would surface here. Frozen reading per arm: uncond-t650
excess over basic ≥ 2× s_seed = the arm is live; the ladder itself
(×0.5, ×4 to follow) is read descriptively for a peak, with any
elevation decided after the full ladder under its own note.

**Deferred, recorded as chosen-not-run:** PCA/structured synthetics — the
measured content tendency (self +0.28 < shuf/synth +0.42) predicts
structured variants land between two already-measured points; no
mechanistic gain expected. Fresh-per-step noise (vs fixed pseudo-identity)
is the next distinct fork and gets its own entry.

**Builder change.** `build_synth_emb.py` gains `--draw-seed` and
`--var-scale` flags (defaults reproduce E1η exactly); output dirs
`uni2h_emb_synth2185_gauss_seed{S}` and `..._var{V}`; Y-checks unchanged
except Y4's std target scales by the multiplier.

### E1ι. Mechanism pair: fresh-vs-fixed conditioning noise + LoRA-dropout probe (added 4 September 2026, pre-launch)

Pre-registered before any code change. The β-line configuration is frozen
(×1); this pair now separates the candidate theories recorded on 3 Sep
(T1 perturbation-as-regularizer vs T2 pseudo-identity keying) and tests
channel-generality. Two arms, one per GPU, overnight.

**Arm 1 — fresh-per-step conditioning noise** (`basic_freshcond`): same
Gaussian statistics as E1η (per-token-position mu/sd of the 2,185 real
embeddings) but a **new draw at every training step** for every patch in
the batch — no patch keeps an identity across steps (dedicated generator,
seed 0, recorded). Frozen reading: uncond-t650 excess over basic ≥ 2×
s_seed(650) → **T1** (pure perturbation suffices; the noise-injection ≈
Jacobian-penalty literature applies almost directly); excess < s_seed →
**T2** (consistent pseudo-identities are the mechanism); between → one
more seed before any call.

**Arm 2 — LoRA-dropout probe** (`basic_dropout01`): the plain basic
recipe (NO conditioning of any kind) with LoRA dropout 0.1 — the cheapest
member of perturbation channel #3 (weight-space; MLAE note of 4 Sep).
Frozen reading: excess ≥ 2× s_seed → training perturbation regularizes
through *any* channel (conditioning was merely convenient); < s_seed →
the conditioning channel is special; between → one more seed. Dropout is
train-time only; inference identical to basic by construction.

Both arms: 1000 steps, λ=0, training seed 42, uncond diagnostic at
step_1000 (t 500/650/800, noise seed 0) — the standing instrument.
Reference band: synthetic family excess +0.37…+0.48.

### E1κ. Final-configuration amendment + slide-level pre-registration (added 4 September 2026, pre-launch)

**Amendment to the β-line final configuration (supersedes the ×1-synthcond
declaration of E1θ part 2, before any slide-level run).** Final
configuration := **basic_freshcond** — fresh per-step Gaussian conditioning
from the per-token mu/sd statistics (~200 KB), no cache, no encoder, no
fixed identities. Rationale: functionally equivalent to synthcond on every
measured axis (d in-band, per-type fingerprint identical) and strictly
simpler — the mechanism's own ablations (ζ/η/θ/ι) say the removed parts
were irrelevant; the paper's face is "one randn per step". Condition
attached: **seed robustness first** — `basic_freshcond_seed7` (identical
recipe, training seed 7) must land within the family band (excess ≥ 2×
s_seed at t650) before any slide-level number is produced; if it misses,
the amendment is void and ×1 synthcond (triply seeded) resumes as final.

**E1κ slide-level protocol (the E1δ/E1ε instrument verbatim).** Heatmaps
via `infer_wsi` (t800 only — t650 slide-level was shown unusable in E1δ)
for `basic_freshcond` and `basic_freshcond_seed7`; honest LOOCV baseline
arm, no union, same menu construction (`loocv_union.py --no-union`, fresh
run dir per the standing lesson). **Frozen reading** (both seeds, against
basic honest t800 = 0.6567, bar = +s_slide = 0.6679): both clear → the
final configuration carries dev slide-level standing into the reserved
GrandQC second look (97.5% CI, per the declared two-look discipline);
one clears → "mixed", matching E1ε's grade — proceed to the second look
regardless (the confirmatory tier exists precisely because dev slide
level is noise-order), recording the grade; neither clears → pause and
reassess before spending the look. Reference: selfcond E1ε table
0.6764/0.6661/0.6730.

Execution order: (1) seed-7 training + diagnostic (gate); (2) two infer
runs (~50 min each, one per GPU); (3) LOOCV (CPU); (4) dated results
entry; (5) only then, the GrandQC second-look pre-registration as its own
entry.

### E2. Clean-scaling — experiment 8d via the tissue gate (GPU, 5 trainings)

**Question.** Is clean-patch volume the bottleneck (the 8d null), or does the
composition change that comes with relaxing the gate dominate (the 5c-bis concern)?
The ladder deliberately decouples the two:

- **Arm 1, composition-fixed volume:** random subsamples of the gated catalogue
  (seed recorded), N ∈ {546, 1092, 2185}. N=2185 is the existing basic run — not
  retrained.
- **Arm 2, gate relaxation:** `tissue_threshold` ∈ {0.25, 0.10, 0.0}; N recorded at
  cataloguing time (0.0 recovers the full 9,485-position grid of Finding 2, 2026-09-01
  entry).

Five new trainings, all basic (λ=0), 1000 steps, batch 4, seed matched to the existing
basic run. **Judgment is training-side only**, per §8y(2): separation gap and Cohen's d
on the *unchanged* gated validation pool at t ∈ {650, 700, 800, 950}, plus each
catalogue's median clean/artifact latent distance as the composition probe (calibrated
signature: ~0.83 clean-tissue vs ~1.8–2.0 background-contaminated, 5c-bis).

**Predictions (discriminating pattern, not a point forecast).** If volume is the
bottleneck: d rises with N in both arms. If composition dominates: d rises along Arm 1
and flattens or falls along Arm 2. Either outcome resolves 8d's null.

**Decision rule (frozen).** Only a configuration with Δd ≥ +0.15 over the N=2185
baseline at its own best t earns slide-level inference and a LOOCV evaluation on the
development benchmark.

### E3. Union-mask LOOCV (zero-GPU queue)

Models: basic and variantA (the only two with cached heatmaps at both t=650 and t=800).

**Rule U (frozen).** Final mask = M₈₀₀ ∪ {connected components of M₆₅₀ with area
< 10,000 px}. The cutoff is the a-priori fixture of §8y (sourced to 5t Finding B) and
is not swept. M₈₀₀ is untouched, protecting OOF and penmark; t=650 contributes only the
small components where it demonstrably carries signal (5w). Both thresholds θ₈₀₀, θ₆₅₀
are tuned inside the §8y nested LOOCV; the baseline arm is M₈₀₀ alone, re-tuned per
fold under the same regime.

**Predictions.**
- P1: the partition-honest per-fold-retuned t=800 baseline comes out **below** 0.673;
  the size of the drop is the value of the grid-maximum practice (the §8y side
  product).
- P2: air-bubble and fold sensitivity rise (by construction they cannot fall); the risk
  is precision, concentrated on clean-slide FPs — tracked explicitly.
- P3: pooled ΔF1 is small, sign uncertain; judged only as a paired difference with CI,
  never as levels. Dark-spot is excluded from claims (5t Finding C: speckle).

**Check before any bootstrap:** per-slide counts must re-pool to the saved aggregate.
All submitted-paper rules carry over (bases, rounding, banned numbers, air-bubble n=1).

**Design note, 1 September 2026 (pre-launch, before the E3 producer exists).**
Threshold *menu* (absolute v_min/v_max values) is fixed once from pooled-24
percentiles, exactly as the existing sweep defines its grid; the *selection*
from the menu is per-fold inside the LOOCV. Strict per-fold percentile
conversion would make masks fold-dependent (24× the postprocessing cost) for
a discretization difference the S4 check quantifies (expected <1% drift).
Degenerate menu pairs (v_max ≤ v_min) are skipped and recorded. σ=2.0 and
morph=5 stay at their defaults in both arms and are not swept, matching the
submitted pipeline. Implementation is a wrapper over `evaluate_wsi`'s
`build_ground_truth`/`postprocess`/`confusion` (imported, not reimplemented),
two-pass: (1) fold-independent per-slide counts for every menu config on both
arms, LOOCV as arithmetic over counts; (2) mask rebuild only at each fold's
chosen config for per-type and clean-slide-FP detail. Paired stratified
bootstrap (clean vs artifact slides, 20,000 replicates, seed 0) on the
held-out pooled ΔF1.

### E4. Scale calibration (zero-GPU queue)

**Stage (i), model-free:** render the 24 development slides at 5×, overlay ground
truth, and record per-type annotated-region size distributions at 5×; extract 224px
level-40× patches from annotated regions for HistoArtifacts-protocol compatibility.
Deliverable: the Tier 2 / Tier 3 protocol decisions (§15 cross-cutting obligation 1)
written **before** any confirmatory data is touched.

**Stage (ii), optional, gated on (i):** one inference pass at the 5×-equivalent scale
on the **2 validation slides only** — their §8y smoke-test role — never on the 24, so
the development benchmark's adaptivity budget is not consumed.

**Stage (i) pre-registration detail, 2 September 2026 (pre-launch).** Slide
inventory (recorded): 22/24 test slides are 40× native (mpp ≈ 0.246–0.253),
**2/24 are 20× native** (TCGA-HU-A4GC, TCGA-HU-A4GF; mpp 0.494) — "40×
patches" are undefined there, so the Tier 3 (HistoArtifacts, 224px@40×)
protocol must either exclude both or declare upsampling; stage (i) records
the counts under exclusion. No slide carries a native 5× pyramid level
(downsamples are [1,4,16,32/64]), so "5×" is defined by target mpp ≈ 2.0
μm/px: read the ds-4 level and resample by the per-slide residual factor
(×2 for 40×-native; identity for 20×-native). Producer `scale_calib.py`,
CPU-only: per slide, (a) 5× render geometry; (b) GT rasterised at the 5×
shape via the verified palette code called directly WITHOUT the evaluate_wsi
npz cache (cache keys carry no shape; existing entries are heatmap-grid) —
E4 uses its own cache directory `gt_masks_5x/`; (c) per-type connected-
component size distributions at 5× and the count of components that would
survive at SlideInspect's working scale; (d) per-type counts of 224px@40×
patch positions fully inside annotated regions (level-0 geometry, 40×-native
slides only) for HistoArtifacts feasibility. No model is loaded; no error is
computed; no threshold is chosen. Deliverable: the Tier 2/3 protocol
decisions written from these tables.

### Queue

GPU: E1 first (hours), then E2's five trainings. CPU, in parallel: E3 and E4(i).
Selection among these along the way is at the researcher's discretion, per the status
paragraph above.

## 2026-09-01 — E1 self-conditioned scoring diagnostic — results

Producer `selfcond_diag.py` at commit `aafce74`, noise seed 0, launched via
`runbg.sh`; outputs in `dgx_shared/evaluations/selfcond_diag/` (`errors.pt`,
`report.json`, `run.json`). Checks S1–S5 passed; P1 held exactly: paired
per-patch delta-error nonzero on 1427/1427 in all nine (arm, t) pairs.

**P2 (hypothesis) — partial.** Self-conditioning is not uniformly helpful: at
t=500 it hurts in every arm (Δd −0.17 to −0.26); at t=650 it helps the LoRA
arms (basic +0.08, variantA +0.20); at t=800 it is essentially neutral
(−0.04 to +0.13).

**P3 (discriminator) — the predicted signature came out inverted.** The
prediction was "if LoRA-null mismatch dominates: LoRA arms negative, base arm
positive". Observed: the base arm is negative at every t (−0.17 / −0.15 /
−0.04) while every positive cell is a LoRA cell. The mismatch hypothesis is
rejected — but with a twist the pre-registration did not anticipate:
conditioning alone does not help the bare backbone; whatever benefit exists
appears only in combination with the LoRA, and only at mid-t.

**Decision rule.** One cell triggers it: **variantA t=650, Δd = +0.2024 ≥
+0.2**, with neither admissible type falling (air-bubble +0.10, OOF +0.35).
The gate to step (β) — LoRA retraining with self-conditioning — is formally
open. Recorded plainly: the margin is 0.0024 under a single noise seed, i.e. a
boundary pass. Per the frozen discipline this does not reopen the rule; any
seed-robustness check is a new dated pre-registered addition, not a silent
rerun. AUROC (pre-registered secondary) agrees directionally in the same cell
(+0.036) and disagrees nowhere sharply — no d-vs-AUROC finding to log.
Whether (β) actually runs remains a selection decision under §16's status
paragraph.

**Caveats binding any reading.** Patch-level filter only (§8y(2)); the pool
spans 2 slides; per-type claims limited to air-bubble (134) and OOF (125),
penmark (n=1) excluded. The unconditioned *levels* here are not comparable to
8e-pre: different validation pool (1,167/260 DGX-era vs 287/59 basic-era) and
different noise realisation; only the paired Δ columns carry the experiment's
meaning.

## 2026-09-01 — E1β conditioning-aligned retraining — results

Training arm `basic_selfcond` completed per pre-registration (1000 steps, 120 min,
λ=0, seed matched to basic; join key-asserted at load). In-training separation
monitor (deliberately uncond) tracked basic essentially point-for-point through
step 450 and ended +34.8% vs basic's +32.8%. Diagnostic: `selfcond_diag.py`
`--arms basic_selfcond --run-name selfcond_diag_e1b`, noise seed 0, same paired
protocol as E1; outputs in `dgx_shared/evaluations/selfcond_diag_e1b/`.

**Q1 confirmed.** Deployment comparison (selfcond-sc vs basic-un): t500 −0.22,
t650 **+0.288**, t800 +0.09 — the benefit lives at mid-t.

**Q2 confirmed.** +0.288 exceeds the misaligned +0.2024, and passes the frozen
rule with margin: air-bubble +0.36, OOF +0.21, no type drops. **The gate to a
slide-level evaluation is open — cleanly this time, not at the boundary.**

**Q3 violated — the substantive finding.** Scored uncond, basic_selfcond ≠
basic: t650 Δd **+0.325** (1.665 vs 1.340), 3× the pre-registered |Δd|<0.1
null band (t500 −0.17, t800 +0.17). Conditioned training changed the model
itself. Complementarily, *within* basic_selfcond the sc-vs-un deltas are ≈0
(−0.05/−0.04/−0.07): alignment absorbed the conditioning benefit into the
weights. If this stands, the deployment implication is train-conditioned /
score-unconditioned — no UNI2-h encoder at inference.

**Caveats before any weight is put on this.** One training seed per arm; the
seed variance of patch-level d has never been measured (a cheap estimate
exists: variantA vs variantA_seed7, uncond-only diagnostic — a candidate
pre-registrable robustness check before committing GPU-hours to slide-level
inference). Patch-level filter status and the 2-slide pool caveat (§8y(2))
apply unchanged. AUROC (secondary) agrees directionally at the deployment cell
(t650 +0.077 vs basic-un) and disagrees nowhere sharply.

## 2026-09-01 — E1γ seed-robustness — results: the Q3 finding survives

**R1 (noise scale).** First-ever measurement of seed-induced patch-level d
dispersion (variantA s42 vs s7, uncond, `selfcond_diag_e1c_r1/`): s_seed(500)
= 0.001, s_seed(650) = 0.126, s_seed(800) = 0.186. R1-P holds (0.126 < 0.16).
Side consequence, binding on today's other numbers: t800 deltas of order ±0.19
are within seed noise and unreadable — including E1β's t800 cells; only the
t650 cell of the Q3 violation stands above the line.

**R2 (independent replication).** `basic_selfcond_seed7` (identical recipe,
seed 7, 120 min; monitor not comparable to s42 by design — different 96-clean
subsample) scored uncond at t650: d = 1.599 vs the 1.466 threshold
(basic 1.340 + s_seed 0.126). R2-P holds. The excess (+0.259) reproduces
s42's (+0.325) within seed noise; per-type agrees (bubble 1.156 vs 0.932,
OOF 2.123 vs 1.781). Secondary, recorded not claimed: at t800 seed7 shows
+0.375 over basic (above s_seed(800)) where s42 showed +0.17 (below) —
unstable across seeds.

**Verdict (frozen rule): R1-P ∧ R2-P → the train-conditioned /
score-unconditioned candidate earns a slide-level evaluation.** The first
gate today opened with a replication behind it. All §8y(2) caveats carry:
patch-level filter, 2-slide pool, basic itself still one seed (bounded, not
averaged). Outputs: `selfcond_diag_e1c_r1/`, `selfcond_diag_e1c_r2/`.

## 2026-09-02 — E3 union-mask LOOCV — results: rule U rejected at pooled level

Producer `loocv_union.py`, full 24 slides, menus 22 configs per t (3 degenerate
skipped), 20,000-replicate stratified paired bootstrap, seed 0; outputs in
`dgx_shared/evaluations/loocv_union/` (counts cached per model).

**Mechanical.** S5: baseline grid-max reproduced from counts at 0.6725 vs the
submitted 0.673 — the counts→F1 chain is validated on a known number. S1–S3
passed; refined masks agree across t on all slides. **S4 FAILED as predicted:**
measured max fold-menu drift 4.7–4.8% vs the pre-registered <1% expectation.
The estimate runs through a 2048-bin histogram approximation that inflates it,
but the prediction was written and missed; recorded as a failed mechanical
check. Scope: menu discretization only — selection remains per-fold.

**P1 holds.** Partition-honest per-fold-retuned baseline: basic 0.657 vs
grid-max 0.6725 → **the grid-maximum practice is worth ≈ 0.016 F1** — real
but small; the submitted 0.673 was not seriously inflated. (variantA: 0.684
honest vs 0.688 grid-max.)

**P2 holds.** Held-out sensitivity rises everywhere, concentrated where
predicted: basic air-bubble 0.361→0.485, fold 0.451→0.538, penmark
0.447→0.544, OOF 0.898→0.919. The cost lands exactly on the predicted
channel: clean-slide FP ×2.5 (486k→1,234k px; variantA 469k→1,055k).

**P3 resolved negative: rule U loses at pooled level.** basic ΔF1 −0.035,
CI95 (−0.102, +0.015) — includes zero; variantA −0.036, CI95 (−0.087,
−0.006) — significantly negative. The precision cost of admitting small t650
components exceeds the sensitivity gain. **Rule U with the a-priori 10k px
cutoff, as frozen, is rejected as a pooled improvement.** What survives: the
first slide-level quantification of the per-type timestep profile, and the
localisation of the cost to clean slides. Any revised rule (e.g. different
cutoff, clean-aware gating) is a new pre-registration, not a tweak; the
cutoff was deliberately not swept and stays that way in this record.

## 2026-09-02 — E1δ slide-level evaluation — results: success at t800 by the frozen rule

Producer `loocv_union.py --models basic_selfcond,variantA_seed7_s1000
--no-union`; honest-LOOCV protocol throughout; outputs in
`dgx_shared/evaluations/loocv_union/` (fresh run dir).

**Noise gauge.** s_slide = |0.6950 (variantA_seed7 honest t800) − 0.6838
(variantA, E3)| = **0.0112** — first slide-level honest-LOOCV seed dispersion
measurement.

**Verdict (frozen rule: exceed basic's 0.657 by > s_slide at some t):**
basic_selfcond honest t800 = **0.6764**, excess **+0.0197 ≈ 1.8 × s_slide →
slide-level success declared.** t650: 0.2716 — collapse (clean-slide FP 5.7M
px; Otsu floods clean slides at t650) — not a viable operating point.

**Against predictions.** D1 violated in the favorable direction: t800 was
predicted ≈ basic (patch-level t800 deltas sat inside seed noise) yet the
slide level cleared the gauge — the second time the conditioning effect
surfaces where patch-level did not clearly predict it. D2 answered harshly
(t650 unusable pooled). D3's 5× discount applied and still left a positive
residual. Per-type at t800, uniformly favorable: air-bubble 0.361→0.583,
fold 0.451→0.473, penmark 0.447→0.501, OOF unchanged, clean-slide FP lower
(486k→395k px) — a profile improvement, not a trade-off.

**Brackets.** s_slide from a single pair, measured on the variantA recipe,
not basic; margin 1.8× noise — real, not overwhelming; all exploratory on the
development benchmark (n_eff ≈ 6.2, §8y). Confirmatory standing of the
train-conditioned/score-uncond result awaits the frozen external tier
(GrandQC first). Grid-max numbers recorded for reference only:
basic_selfcond 0.690, variantA_seed7 0.6974.

## 2026-09-02 — E1γ addendum — third seed lands on the line

`basic_selfcond_seed123` (identical recipe, seed 123, 120 min) scored uncond
at t650: d = **1.590**, excess over basic **+0.250**. The three-seed picture:
s42 +0.325, s7 +0.259, s123 +0.250 — range 0.075, mean +0.278, every point
≥ 2× s_seed(650) = 0.126. Per-type consistent (bubble 1.19 / OOF 2.04 vs
s7's 1.16 / 2.12). The uncond-t650 patch-level excess of conditioned training
now rests on three independent trainings. Diagnostic outputs in
`selfcond_diag_seed123/`. (Slide-level standing: E1δ, one seed — extending
E1δ to the other seeds would need infer runs and is not pre-registered here.)

## 2026-09-02 — E4 stage (i) — results: tables in hand; a 14th artifact slide at 5×

Producer `scale_calib.py` (two runs: first tripped G3 as designed, amended,
second clean); outputs in `dgx_shared/evaluations/scale_calib_stage1/`,
GT@5× cached in `gt_masks_5x/` (isolated from the heatmap-grid cache).

**Finding: a genuine micro-annotation invisible to the evaluation grid.**
TCGA-56-8628 carries one 356-px air-bubble component at 5× (bbox 16×36,
palette-matched 352/356) — erased entirely at the coarser evaluation grid,
where the slide has always counted as clean. G3 amended to encode 13 + this
recorded micro; evaluation-grid truth (13 artifact slides) unchanged, no
retroactive effect on any E1δ/E3 number. It is a concrete instance of the
E4 premise (the evaluation scale defines which artifacts exist) and one more
air-bubble object no metric of ours has ever seen.

**Tier 3 feasibility (224px@40×, 22 native-40× slides; HU-A4GC/A4GF
excluded as 20×-native).** Feasible in-annotation patch positions:
out-of-focus 158,750; penmark 71,381; fold 3,920; air-bubble 1,222.
Comfortable for OOF/penmark; thin but non-zero for fold/bubble — adequate
for patch-level confirmation, not for rich stratification. Consistent with
HistoArtifacts' assigned role (air-bubble gap, patch level).

**Tier 2 profile (5×).** Strong dichotomy: OOF/penmark concentrate in few
huge components (114 comps / 129.1M px and 85 / 62.2M px) that survive any
reasonable scale; fold is the sensitive class — 1,452 components averaging
~3.6k px at 5×. Air-bubble: 99 comps / 1.58M px. Per-slide quantiles are in
the report for the protocol text.

**Stage (i) deliverable status.** Tables complete; the written Tier 2/3
protocol decisions are the remaining step and will be drafted from these
numbers as a separate dated entry (they gate any confirmatory touch, per
§15).

## 2026-09-02 — SlideInspect unblocked: Salvi reply (email, 10:39)

M. Salvi (Politecnico di Torino) confirmed by email: (1) mask encoding as
interpreted — 0 background, 85 out-of-focus, 170 mounting artifact, 255
tissue fold; (2) **released test slides contain no TCGA/TCIA material**
(proprietary sources) — SlideInspect is therefore eligible as a frozen
confirmatory set under §15, unlike anything TCGA-derived (PanCan-30M);
(3) academic non-commercial use permitted, citation = the IJIST 2026 paper;
(4) **only the 5× versions were ever stored** — full-resolution files no
longer exist.

**Protocol implications (Tier 2).** Evaluation will necessarily run at 5×,
exactly the scale E4(i) characterised: fold is the scale-sensitive class
there (1,452 components, median ~3.6k px), OOF concentrates in few large
components. Class mapping decision, recorded with its caveat: SlideInspect
85 → our out-of-focus; 255 → our fold; **170 "mounting artifact" is a
broader category than air-bubble** (bubbles plus other mounting defects) —
any air-bubble comparison through it carries a category-mismatch caveat and
will be labelled "mounting artifact" not "air-bubble" in all reporting. No
penmark class exists (consistent with the no-public-penmark-GT survey).
The written Tier 2 protocol (still the gating deliverable before any
confirmatory touch) now has every input it was waiting for.

## 2026-09-02 — Confirmatory tier protocol (freeze-on-commit; gating deliverable of §15/E4)

Written from the E4(i) tables and the Salvi reply, before any confirmatory
data is touched. This entry governs the first confirmatory pass; deviations
require a new dated entry before execution.

**General discipline (all tiers).** One evaluation per (model, tier). No
threshold, hyperparameter, or timestep selection on confirmatory data.
Models: exactly two — `basic` (reference) and `basic_selfcond` (the E1δ
candidate) — both scored **unconditioned at t=800**, the E1δ-validated
deployment regime. Post-processing frozen to the submitted defaults
(σ=2.0, morph=5) with v_min/v_max defined as *percentile indices* (the
config selected by pooled F1 on the full 24-slide dev benchmark — dev is
the tuning set; that is its job), converted to absolutes **label-free** on
each confirmatory set's own pooled error distribution. This label-free
recalibration is declared here as part of the protocol, not tuning.
Metrics: pixel-level pooled F1/sensitivity/precision plus per-mapped-type
sensitivity; paired per-case differences with a 20,000-replicate case-level
bootstrap, seed 0. **Primary confirmatory endpoint, declared once:
ΔF1(basic_selfcond − basic) pooled on the GrandQC test set.** CI excluding
zero upward = confirmed; crossing zero = unresolved; excluding downward =
disconfirmed. Everything else in all tiers is secondary/descriptive.

**Tier 1 — GrandQC test set (first, largest n_eff: fold 48.5, OOF 39.5,
bubble 40.0).** Native 10× — direct compatibility with the operating point;
no scale adaptation. Class mapping recorded at ingestion (a docs-level
recon, not an evaluation); no penmark class exists in any tier (survey
confirmed). Zero TCGA overlap already established.

**Tier 2 — SlideInspect (5×-only, per Salvi).** Ingestion: ×2 bilinear
upsample of the released 5× images to the 10× operating scale — an
approximation recorded here: focus information destroyed by 5× storage is
not recoverable, so **out-of-focus results on Tier 2 carry a permanent
scale caveat** and are reported as such. Class mapping (from the confirmed
encoding): 85 → out-of-focus (caveated), 255 → fold, **170 reported as
"mounting artifact", never as "air-bubble"** (broader category; category-
mismatch caveat). Fold — the E4(i) scale-sensitive class — is Tier 2's
descriptive focus. Role: cross-dataset generalization at adverse scale;
secondary throughout.

**Tier 3 — HistoArtifacts (last; patch-level; the air-bubble gap).**
Frozen now: patch-level protocol, primary class air-bubble, metric AUROC of
the per-patch score (no threshold selection), same two models, same regime.
One geometric decision cannot be frozen blind: a 224px@40× patch spans
56px at the model's 10× operating scale, far below the 1024px input — the
ingestion geometry (context embedding vs. dataset-provided source regions)
depends on the dataset's actual structure. A **docs/structure-level recon**
(reading documentation and file layout only, no scoring) is authorized as
a pre-step; the ingestion decision becomes a dated amendment before any
evaluation runs. This is the single open slot in the protocol, named here.

**Order.** Tier 1 → Tier 2 → Tier 3. The E2 verdict does not gate Tier 1
(the two frozen models are E1-line, not E2-line); if E2 later produces a
superior configuration, its confirmatory standing requires a new protocol
entry — it does not inherit this one.

## 2026-09-02 — Addendum to the confirmatory tier protocol: contrastive-line designation

Recorded after the protocol froze at commit b3f6e8a (same day), before any
confirmatory data is touched, and without modifying the frozen entry. No
contrastive configuration is in the frozen protocol (models: basic,
basic_selfcond only). Should a contrastive line later be elevated to
confirmatory standing — which requires its own dated entry — the designated
representative is the **balanced artifact sampling** recipe (equal count per
type, the `variantB_bal` line), not proportional: proportional's mix (190
air-bubble / 114 penmark of 400) underrepresents fold and dark-spot, and the
researcher's recorded preference is equal per-type exposure. This addendum
pre-decides the *which*, not the *whether*.

## 2026-09-02 — Idea recorded (8b-level): selective forgetting of artifact denoising

Direction sketched while the E2 ladder runs; NOT pre-registered — a §16-style
entry is required if/when any of it is scheduled. The inverse of the E1β
finding: keep clean denoising intact, degrade artifact denoising, widening
the detector's gap from the artifact side.

**Candidate approaches, cheapest first.**
1. **Task-vector negation (first candidate).** Train an artifact-LoRA (same
   recipe, λ=0) on artifact patches — balanced per-type sampling per the
   recorded designation — then negate: θ = θ_base − α·τ_artifact (task
   arithmetic; in LoRA space the negation is weight arithmetic, α sweeps
   free). One training + the existing diagnostic answers whether the
   direction is useful at all; gates the costlier options.
2. **Bounded anti-training.** L = L_clean + λ·hinge in *error* space
   (maximize e_art − e_clean with margin) — optimizes the detector's metric
   directly; risk of non-generalizing trivial failure modes; unbounded
   ascent destroys the model (NPO-style bounding required).
3. **Unlearning with preservation** (Selective-Amnesia-style: ascent on
   artifacts + Fisher/replay on clean) — theoretically cleanest, heaviest.
4. **Masked/local variant** (applies to 2/3): annotation masks projected to
   the 128×128 latent grid restrict the forgetting loss to artifact cells,
   preservation on the rest — turning the min_overlap=0.05 contamination of
   artifact patches from confound into feature.

**Honest risks, recorded with the idea.** (a) Abandons the clean-only
training narrative — supervised exposure to our 5 types makes unknown-
artifact generalization the central question (answerable only at the
confirmatory tier, under its own future entry). (b) The detector lives on a
thin asymmetry; thresholds calibrated on an artificially widened gap may
meet a different distribution at deployment. (c) Any comparison against the
E1-line results inherits the E1γ noise gauges (s_seed, s_slide) — already
measured.

Literature anchors to verify at write-up time (from memory, unverified):
task arithmetic (Ilharco et al.), ESD / Selective Amnesia / SalUn for
diffusion concept erasure, NPO for bounded ascent. Related-work adjacency:
MSLoRA-CR (verified 1 Sep, arXiv:2508.11673) for geometry-in-adapter-space.

## 2026-09-02 — 8b addendum: clean-only gradation, and an asymmetric contrastive variant

Two clarifications and one recorded idea, from discussion while the E2
ladder runs. NOT pre-registered; scheduling any of it requires a §16-style
entry.

**(a) The "clean-only training" narrative is a gradation, not a binary.**
Strictly clean-only holds for the basic line (λ=0) and basic_selfcond only.
The contrastive variants already break it — but the exposure is confined:
artifact gradients reach the 2,320-parameter f_A exclusively (L_con is
computed outside the transformer path; no artifact-derived gradient ever
reaches the LoRA matrices). Unlearning/negation schemes (this file, entry
of earlier today) put artifact signal **inside the deployed LoRA matrices**
themselves — either as ascent gradients or as weight arithmetic. Honest
wording for any write-up: f_A-only exposure (peripheral module, unused at
inference in the basic line) vs objective-level exposure (the denoiser's
correction itself sculpted by artifacts). The anomaly-detection
generalization argument weakens at the first level and becomes hard to
sustain at the second.

**(b) Asymmetric contrastive variant (researcher's proposal, recorded).**
Observation: L_con's gradient is symmetric (∂d/∂clean = −∂d/∂art), so the
current scheme pushes clean_fa too; variant A restrains them only
*indirectly* — L_basic anchors f_A(clean) to denoisability, an equilibrium
that depends on λ and anchors position nowhere (many equally-denoisable
locations exist, and the co-adapting LoRA follows f_A's output). Proposal:
make the asymmetry constructive — stop-gradient on the clean branch of
L_con, plus an explicit identity anchor ‖f_A(z_clean) − z_clean‖². Clean
latents are then pinned in place (not merely to denoisability), only
artifacts are displaced, the LoRA need not co-adapt — plausibly removing
the need for f_A at inference (variant A's practical burden). In one line:
variant A's intent with variant B's cleanliness.

**Cheap first measurement (existing checkpoint, minutes, no training):**
‖f_A(z_clean) − z_clean‖ on the variantA step_1000 f_A — quantifies how far
the indirect anchor actually let clean latents drift; never measured.

**Standing caveat (8e), attached to the idea:** the f_A failure was
capacity/venue (2,320 params in VAE-latent space; separation-gap
overselling ~5×), not symmetry. The asymmetric variant fixes a design flaw,
not necessarily the fundamental one.

## 2026-09-02 — Evaluation of externally-suggested directions (recorded to 8b level)

An external AI summary (over the project's own sources) proposed four
directions; evaluated against this file's empirical record. Verified today:
GLAD (Yao et al., arXiv:2406.07487; ATP = synthetic anomalies with a
modified target so the denoiser learns to generate the normal counterpart)
and DeCo-Diff (Beizaee et al., CVPR 2025, arXiv:2503.19357; anomalies
modeled as latent noise, selective alteration of anomalous regions only).
Unverified names, flagged: COFT-AD, "ProtoFocus (2026)".

1. **f_A + contrastive (m=1.2, λ=0.5): rejected — already run.** This is
   the enhanced recipe this project reproduced and dissected: f_A
   structurally weak (8e), m=1.2 measured non-transferable (2.7 used),
   separation-gap criterion oversells ~5×. Recorded as a demonstration of
   why the Gaps file exists: literature without the empirical record
   recommends the already-falsified.
2. **Asymmetric adapter block (zero-init, L_id, masked bypass): converges
   with the 8b asymmetric-variant entry.** Zero-init identity already
   present in our f_A; L_id = the recorded anchor. Genuinely new nuance
   adopted into that idea: **masked spatial bypass during training**
   (f_A applied only on GT-masked latent cells, identity elsewhere) — a
   mathematical guarantee replacing the soft anchor; carries a train/test
   mismatch note (no mask exists at inference; specificity must have
   generalized into the weights).
3. **GLAD-style ATP: the one substantively new direction — recorded as the
   principled alternative to ascent in the selective-forgetting entry.**
   Synthetic (clean, corrupted) pairs with a modified target teach the
   model to *remove* the anomaly; large, localized residuals arise by
   construction, avoiding ascent's trivial-failure risk, and generic
   synthetic corruption preserves the generalization narrative better than
   exposure to our 5 real types. Central risk: synthetic realism for
   histopathology (OOF/bubble overlays feasible; realistic fold hard).
4. **DeCo-Diff: strong but radical** — a reformulated diffusion objective,
   i.e. a new research line, not an increment; kept as a literature anchor
   for future design, no action in the current battery.

Priorities unchanged: E2 verdict, E1ε, then the frozen confirmatory tier
come first; everything above is paper-#2 future-work material.

## 2026-09-02 — E1ε results: verdict "mixed" — real but noise-order at slide level

Heatmaps (t800, `infer_wsi`) and honest-LOOCV baseline runs for seeds 7 and
123 (seed-7 counts cached from an aborted first pass launched before its
heatmaps existed — operator-sequencing slip, no data harm; rerun clean).
Three-seed table, honest t800 F1 vs basic 0.6567, bar = 0.6567 + s_slide
(0.0112) = 0.6679: s42 0.6764 (+0.0197, clears), s7 0.6661 (+0.0094, misses
by 0.0018), s123 0.6730 (+0.0163, clears).

**Verdict (pre-declared reading): mixed** — 2 of 3 clear. The "all three"
prediction failed; its spread clause held exactly: three-seed range 0.0103
vs the variantA-pair estimate 0.0112 — two independent measurements of
slide-level seed dispersion agreeing in magnitude.

**Honest summary.** All three seeds sit above basic (mean excess +0.015),
but the excess is of the same order as seed noise: real, small, and not
settleable on 24 slides (n_eff ≈ 6.2). This is precisely the finding
profile the frozen confirmatory tier exists for; the E1δ "success" headline
now carries this spread as its permanent context. Grid-max values recorded
for reference only: s7 0.6872, s123 0.6901.

## 2026-09-02 — E2 results: the 8d null is rejected — composition, not volume

Verdict run `selfcond_diag.py --arms basic,e2_sub546,e2_sub1092,e2_thr025,
e2_thr010,e2_thr000 --conditions un --ts 650,700,800,950` (outputs in
`e2_verdict/`); ladder Ns recorded at cataloguing: 546/1092/2185 |
3111/3738/9485. Full d(N,t) table in the report; headline rows: at t800,
composition-fixed arm reads 2.512/2.470/2.416 (flat within s_seed) while
gate relaxation reads 2.523/1.290/**0.066** (thr000: AUROC 0.48 — total
signal loss).

**Arm 1 (composition-fixed) is flat at every t**: 546 → 2185 patches
changes nothing beyond seed noise — d saturates by N=546. Stronger than
the pre-registered "volume" branch predicted (which expected a rise).
**Arm 2 collapses monotonically**, and at the 9,485 extreme produces an
inversion finding: air-bubble d = **−1.31** (AUROC 0.14) at t800 — a model
trained on background reconstructs background-like bubbles *better* than
tissue. The detector does not merely weaken under contaminated curation;
it can invert for artifact types resembling the contamination. (Monitor
trajectories told the same story qualitatively; the diagnostic quantifies
it on the full pool at the pre-registered timesteps.)

**Decision rule outcome: no configuration reaches Δd ≥ +0.15 at its own
best t** (closest: thr025@t800 +0.11, sub1092@t950 +0.06 — both within
noise) → no slide-level evaluation is earned; zero further GPU on this
line.

**Consequence for the reproduction's leading anomaly candidate.** The
"2,185 vs 63,000 clean patches" volume explanation for the penmark
0.526-vs-0.866 gap loses its main support: within the accessible range,
volume is irrelevant. Any residual volume claim lives only in the untested
30× extrapolation and is now recorded as unsupported conjecture. Positive
reading for the paper line: clean-data *curation* (the tissue gate) is a
first-order design choice — quantified here across a 17× volume range —
and the dev benchmark's 2,185-patch regime is not a handicap.

## 2026-09-02 — §16 battery: closing summary

Every question the battery posed is answered; pointers to the dated entries:
- **E1** (self-cond scoring): no free win; mismatch hypothesis rejected with
  an inverted signature — benefit only as conditioning × LoRA interaction.
- **E1β** (aligned retraining): the finding — train-conditioned /
  score-unconditioned; Q3 violated (+0.325 uncond-t650 over basic).
- **E1γ** (+addendum): three seeds, excess +0.250/+0.259/+0.325, all ≥ 2×
  s_seed(650)=0.126; first seed-noise measurements (patch level).
- **E1δ/E1ε** (slide level): honest t800 0.6764/0.6661/0.6730 vs basic
  0.657; verdict *mixed* (2/3 clear the +s_slide bar; s_slide ≈ 0.011 twice
  independently). Real, small, confirmatory-tier question. t650 unusable
  pooled.
- **E2** (8d): null rejected — volume saturated by N=546 (flat arm 1);
  composition dominates (arm 2 collapses to d=0.066 at 9,485, with
  air-bubble inversion d=−1.31). No config earns slide level.
- **E3**: rule U rejected pooled (variantA CI excludes zero downward);
  grid-max priced at ≈0.016 F1; per-type slide-level profile quantified.
- **E4** (stage i): feasibility tables; fold = the scale-sensitive class;
  the 356-px micro-annotation finding; Tier 2/3 protocol frozen (with the
  Salvi-reply entry) — one named open slot (Tier 3 ingestion geometry).

Standing next step: Tier 1 (GrandQC) ingestion recon per the frozen
protocol — docs/structure level only, no scoring. [curated: non-scientific passage removed]  Ideas parked at 8b level: selective
forgetting (+ATP), asymmetric contrastive, external-proposal evaluation.

## 2026-09-02 — Tier 1 amendment: ingestion geometry (pre-launch)

Structure-level recon of the downloaded GrandQC test set (MPP10 tier; the
prior inventory/provenance docs were found complete and are adopted)
surfaced a geometry the frozen protocol's "direct compatibility" assumption
did not cover: tiles are 512×512 at MPP 1.0 and **sparse** — filename-grid
analysis over 12 sampled cases shows steps equal to tile width where
neighbors exist, but only 6–16% of tiles have a full 2×2 neighborhood.
Mosaic assembly would discard ~85% of data; rejected as the primary route.
(One sampled Breast case has no parseable tiles — presumed one of the
record's empty cases; to be counted at ingestion.)

**Decision (amendment, frozen now).** Tier selection: **MPP10** (matches
the 10× operating point; carries the completed provenance screen). Class
mapping: 2→fold, 6→out-of-focus, 5→air-bubble (name caveat: "edge-air-
bubble" may include edge artifacts), 3→dark-spot-foreign (descriptive
reporting only, per the 5t non-class finding); penmark absent (0 px —
independent confirmation of the no-public-penmark-GT survey). Pooled
positive = {2,3,5,6}; valid region = mask ≠ 0.

**Geometry: option A first, B as fallback, C rejected.**
- A (native-512 scoring): VAE handles 512 natively (64×64 latent); whether
  the DiT's positional handling tolerates 64×64 is unknown and will NOT be
  assumed. Gate A1: mechanical probe on synthetic latents (forward runs,
  shapes correct, finite outputs). Gate A2: regime validation on the
  development tier — 512-crop scoring of the existing validation pool;
  adopt A only if clean/artifact d at native-512 is commensurate with the
  1024 regime (declared bar: pooled d within s_seed of the 1024 value at
  the same t). Both gates run before any GrandQC image is touched.
- B (per-case canvas, score only fully-tile-covered 1024 patches): safe,
  ~15% utilization; adopted if A fails either gate, with the utilization
  and its n_eff cost recorded.
- C (×2 upsample to 20×-equivalent): rejected — permanent scale caveat on
  the primary endpoint.

The primary endpoint, models, scoring regime, and statistics of the frozen
protocol are unchanged by this amendment; it settles geometry only.

## 2026-09-03 — Tier 1 Gate A2 result: FAILED → option B (canvas) locks in

Gate A1 passed mechanically (64×64 forwards run, finite, shapes correct;
synthetic-latent err ≈ scale-independent). Gate A2 on the full validation
pool (5,708 quadrant crops, seed-0 paired noise, caches in
`val_latents_512_keyed/`, report in `gate_a2_512/`): native-512 pooled d is
**systematically below the 1024 reference in every cell** — basic t650
1.167 vs 1.340 (Δ−0.173), t800 2.194 vs 2.416 (Δ−0.222); both outside the
frozen ±s_seed bars → **Gate A2 FAILED; option B (per-case canvas,
score only fully-tile-covered 1024 patches) is the Tier 1 geometry**, as
pre-decided. Reading: a mild (~10%) uniform regime shift from reduced
spatial context — the 512 regime is different, not broken; the bar
correctly refused to equate them. (The smoke run's dramatic t-dependent
pattern did not persist; smoke numbers were not findings, as declared.)

**Descriptive finding worth carrying:** the conditioning excess survives
the scale change — basic_selfcond − basic at 512: +0.304 (t650) / +0.123
(t800), beside the 1024 values +0.325 / +0.167. The E1-line effect is not
an artifact of the 1024 geometry.

Next: option-B canvas ingestion design (per-case tile assembly from
filename coordinates; utilization and its n_eff cost recorded at
ingestion), then the single frozen Tier 1 evaluation.

## 2026-09-03 — Tier 1 option-B geometry: full-set audit — utilization is 99.4%, not ~15%

Filename-level audit of all 286 case folders (`/tmp/tier1_b_geometry.json`;
tolerance ±2 px for the 1944/1945 width oscillation): **33,361 fully-covered
1024-blocks** (Breast 5,197 / Colon 7,887 / Kidney 12,638 / Prostate 7,639),
covering **44,077 of 44,355 tiles (99.4%)** — the 12-case sample's "6–16%"
measured top-left-corner incidence, not coverage; blocks overlap, and the
tile grid is contiguous-with-holes, not sparse islands. **All 281 non-empty
cases retain ≥1 block** — the case-level bootstrap loses no units. The 5
tile-less folders equal the record's empty cases (286−281 reconciles
exactly). The utilization cost the amendment reserved for recording is,
in fact, negligible.

**Frozen design point for the canvas scorer:** overlapping blocks score
each tile pixel up to 4×; per-pixel score := mean over covering blocks
(symmetric; consistent with the dev pipeline's per-stride averaging).
Block assembly is by filename coordinates with the ±2 px snap; masks are
assembled identically alongside images.

With geometry settled, the single frozen Tier 1 evaluation (basic vs
basic_selfcond, uncond t800, label-free percentile recalibration, primary
endpoint pooled ΔF1 with case-level bootstrap) is fully specified and
awaits only its producer.

## 2026-09-03 — Tier 1: recalibration indices recovered and frozen

The E3 report holding the dev-best baseline configs was overwritten by the
later E1δ/E1ε runs sharing the same output directory (counts caches
survived; lesson recorded — producers get per-run output dirs from here
on). The menus were rebuilt deterministically from the dev heatmaps'
pooled percentiles (a dev-side metadata recovery, no confirmatory data
touched) and verified against known values: basic_nofa best-config F1
reproduces **0.6725** (= the E3 S5 number) and basic_selfcond reproduces
**0.6900** (= the E1δ grid-max). Both models independently select the same
pair — **(vmin_pct, vmax_pct) = (65, 75)** — a coincidence of selection,
not an imposed common config. These two indices are the frozen per-model
recalibration parameters for Tier 1: on GrandQC they convert to absolute
thresholds on the confirmatory set's own pooled valid-region error
distribution, label-free, exactly as the protocol declared.

## 2026-09-03 — E1ζ results: Z2 — variance, not content

`basic_shufcond` (permutation seed 0, 2/2185 fixed points) scored uncond:
t650 d = **1.789** (excess over basic +0.449 ≈ 3.6× s_seed), t800 2.528
(+0.11, within noise), t500 1.000. Against the three genuine selfcond seeds
(1.665/1.599/1.590), shuffled conditioning is **at least as large**
(+0.17 above their mean, ~1.4× s_seed — read as ≥, not >).

**Verdict (pre-declared): Z2.** The E1β effect is not driven by content
correspondence — patches trained under *wrong but real* embeddings receive
the full benefit. The mechanism is conditioning-as-structured-perturbation
(a training regularizer), not self-description; the "self" in
self-conditioning was incidental. Deployment consequence: per-patch UNI2-h
correspondence is unnecessary at training time. Parked next question (8b
level, not pre-registered): whether *synthetic* embeddings drawn from the
empirical marginal suffice — if yes, the encoder leaves the training
pipeline entirely. Single shufcond seed; any elevation of this arm follows
the usual seed discipline. [curated: non-scientific passage removed]  Tier 1 is unaffected (its two frozen models stand; this finding
sharpens the paper-#2 mechanism section).

## 2026-09-03 — TIER 1 RESULT: primary endpoint CONFIRMED — ΔF1 +0.0073, CI95 (+0.0042, +0.0110)

The single frozen GrandQC evaluation ran to completion
(`tier1_grandqc_20260903/`; both phase-1 passes reproduced the audit
exactly — 281 cases, 33,361 blocks; recalibration at the frozen (65,75) on
134.4M valid cells per model; no threshold was ever exposed to choice).

**Primary endpoint (declared once, read once): pooled
ΔF1(basic_selfcond − basic) = +0.0073, case-level paired bootstrap CI95
(+0.0042, +0.0110), 20,000 replicates, seed 0 → CI excludes zero upward →
CONFIRMED.** The conditioning-as-regularizer effect — born in E1,
replicated across three seeds, "mixed" at dev slide level — survives a
frozen external set under a no-tuning protocol. Magnitude is small and
was honestly forecast by the dev slide-level excess (+0.015, noise-order);
dev→confirmatory consistency is itself a finding. Bootstrap note: all 281
cases carry ≥1 positive cell, so the clean stratum is empty and the
stratified design degenerates to a single paired stratum (recorded).

**Composition of the effect.** The gain concentrates in out-of-focus
(sens 0.653 → 0.672, the largest class at 12.0M gt cells), matching the
dev per-type profile; fold/bubble/dark-spot are ties.

**Second headline (outside the endpoint): the per-type profile does not
transfer.** Pooled F1 ≈ 0.35 for both models (dev: ≈ 0.68) under real
domain shift, and **fold collapses to sens 0.04–0.05** (dev: 0.47) — the
GrandQC fold population (149 slides, much smaller components) is nearly
invisible to the t800 operating point. Air-bubble 0.25 (against the
"edge-air-bubble" category caveat), dark-spot-foreign 0.24 (descriptive
class). These are generalization findings for the paper, not endpoint
qualifiers — both models face them identically.

Tier 1 is spent for this model pair; any future configuration requires
its own protocol entry. Tiers 2–3 remain available per the frozen order.

## 2026-09-03 — E1η results: H1 on both seeds — the encoder leaves the training pipeline

Builder `build_synth_emb.py` (Y1–Y5 pass; Y4 amended after its first run —
the ±5% all-dims bound ignored 24,576-way multiplicity; population form
adopted, 99.91% in ±5%, extremes ±6.4% ≈ the expected 4.5σ; norms
preserved at ratio 1.009, recorded). Sidecar-inheritance gap found and
fixed on first launch (manifest.json lives beside the tensor; PROVENANCE
note added to the synthetic dir). Training seeds 42 and 7, same synthetic
cache (shared-draw design note stands).

**Verdict: H1, replicated.** Uncond t650 d = **1.783 (s42)** and **1.714
(s7)** — excesses +0.443 / +0.374 (≈3.5× / 3.0× s_seed), both clearing the
frozen 2× bar. Purely synthetic per-token Gaussian conditioning matches
shufcond (1.789) and sits at-or-above the three genuine selfcond seeds
(1.665/1.599/1.590); per-type fingerprints coincide (bubble ≈1.35–1.47,
OOF ≈2.13). Control tightness note: with identical data seed and λ=0, the
synthcond-s42 and shufcond runs share byte-identical batch sequences
(con/dist traces match digit-for-digit) — the conditioning tensor is the
only difference between those two trainings.

**Consequences.** (1) **UNI2-h is unnecessary at training time**: the full
benefit is available from a 205-MiB Gaussian cache built in seconds — no
foundation model anywhere in the pipeline, training or inference. (2) The
mechanism sharpens: correct content ≤ contentless perturbation (self mean
+0.28 vs shuf/synth mean +0.42; ~1.1× s_seed per pair — recorded as a
tendency, not a claim): informative conditioning lets the model *use* the
signal; uncorrelated conditioning is pure regularization. (3) Line-β next
rungs, in order: independent Gaussian redraw (the one shared random
element; draw seed 1, its own note), then perturbation-scale ladder
(variance multiplier) — where a larger effect, the declared goal of line
β, would live. Slide-level and any GrandQC second look wait for the
ladder's final configuration, per the declared two-look discipline.

## 2026-09-04 — Idea recorded (8b-level): adaptive/multi-timestep scoring (GLAD-inspired)

Prompted by GLAD's global adaptive denoising (arXiv:2406.07487, verified 2
Sep): there, an anomaly-degree estimate picks the *reconstruction starting
step* per sample in an iterative pipeline. Our scoring is single-pass
ε-error at fixed t, so the honest translation is per-patch *query
selection/combination* over a small t set — squarely on top of our own
measured facts: inverted per-type t profiles, E3's rejection of mask-level
union, z-norm fusion killing penmark, per-type weighting named as the path.

Honest-variant space (all fitted on dev only, frozen before any
confirmatory look): (a) fixed small t set + per-type decomposition where
type is predicted from per-t signature vectors (the same object as PRODIGY
Direction III.ii's type cue — scoring and segmentation views of one idea);
(b) label-free per-patch selector from image statistics; (c) selector
trained on synthetic artifacts (ties to the ATP thread). **Recorded risk:**
any scheme reading the sample's own error to pick its t is covert test-time
tuning; any label-trained selector breaks the annotation-free narrative.
Cost ~2–3× inference. Queue position: line γ, after the β ladder resolves;
requires its own pre-registration with the fitting/freezing protocol
spelled out.

## 2026-09-04 — Idea recorded (8b-level): perturbation channel #3 — weight-space (MLAE-inspired), with LoRA-dropout as its cheap probe

MLAE verified (Wang et al., arXiv:2405.18897): LoRA decomposed into rank-1
"experts" with stochastic expert-level masking during training — SOTA on
supervised PEFT benchmarks (VTAB-1k/FGVC). Its selling point (accuracy per
parameter) is not our bottleneck (E2: curation dominates; capacity was
never the constraint). The real relevance: expert masking is a
**training-time perturbation on the weight/architecture channel** — a
third member of the family we are mapping (channel #1: conditioning input,
E1ζ/E1η, proven; channel #2: fresh-per-step conditioning noise, declared
fork, untested; channel #3: this).

**Mechanism-section ordering (recorded as the working plan).**
1. E1θ ladder resolves first (redraw control + variance scale — running).
2. Then the two mechanism discriminators, as a pair serving one question
   (is the regularizer channel-specific or general?): **fresh-vs-fixed**
   conditioning noise (separates T1 pure-perturbation from T2
   pseudo-identity keying) and the **LoRA-dropout probe** (one config
   line, `lora_dropout≈0.1`, one training + diagnostic): if plain weight
   dropout reproduces the excess, *any* training perturbation regularizes
   and the conditioning channel is merely convenient; if it fails, the
   conditioning channel is special — either answer sharpens the paper.
3. **Full MLAE (cellular decomposition + expert masking): parked** behind
   the probe — more invasive, validated only on supervised
   classification, and unnecessary unless the weight channel proves live.

No pre-registration here; each item gets its §16 entry when scheduled.

## 2026-09-04 — Idea recorded (8b-level): feature-density baseline gap (FSGM-Net-prompted)

FSGM-Net verified (IEEE; UltraChip C-scan benchmark + FFT-spatial filtering
of ViT patch features + adaptive GMM density). Not a method to adopt — a
reminder that paper #2 currently lacks a **density-over-features baseline**
(PaDiM/PatchCore/GMM family), the reviewer-obvious alternative to
reconstruction-based scoring. Cheap closure: GMM (or kNN/Mahalanobis) over
UNI2-h embeddings of the 2,185 clean patches, scored on the existing
validation pool (needs only a val-pool embedding pass; ~half a day total).
Either outcome serves: a weak baseline arms the "why diffusion" answer
with a table row; a strong one is knowledge we need before submission,
not after. Narrative bonus: the baseline *requires* a foundation model at
inference — exactly what line β's finding removes. Frequency-filtering
thread noted and deliberately not pursued (hand-crafted-feature road).
Priority: before manuscript submission, after the E1θ/mechanism pair.

## 2026-09-04 — E1θ results (part 1): redraw control passes; intensity is flat at ×2

Builder episodes first, for the record: Y3 bound was var-scale-specific
(amended — SE now scales with the multiplier; second occurrence of the
"parametric bounds" lesson), and the sidecar-inheritance patch from E1η
had never actually been applied (caught by the second launch failure;
applied and committed — lesson: a patch without its confirming print never
ran).

**Redraw control (draw1, sampling seed 1): PASSES.** t650 d = 1.775,
excess +0.435 — inside the declared band, on top of draw0 (1.783). The
synthetic family now spans three runs (1.783 / 1.714 / 1.775; range 0.069
≈ ½ s_seed) varying training seed and Gaussian draw: neither is special.

**Variance ×2: FLAT.** t650 d = 1.731 (+0.391) — inside the ×1 band; t800
2.510 likewise. Per-type: bubble 1.485 ≈ family (no per-type lever at ×2);
OOF 1.995, marginally below the family's 2.13 (order of per-type seed
noise; recorded without claim). Reading: the perturbation-intensity curve
has a **plateau over [×1, ×2]** — no gain, no collapse. Line β's
larger-effect hope did not materialize at ×2; the plateau itself is the
finding: the method's one hyperparameter barely matters, a stronger
no-tuning deployment property than a sharp optimum would be. T1's
inverted-U prediction is not contradicted — the peak is wide; the edges
(×0.5, ×4) run next to complete the curve (declared in the E1θ entry).

## 2026-09-04 — Note recorded (8b-level): VAE-latent GP few-shot segmentation (Zhou et al., TIP 2026)

Verified: IEEE TIP vol. 35, pp. 2771–2786 (2026) — few-shot strip-steel
defect segmentation; pre-trained VAE latent space + Gaussian Process
regression from support masks (the Deep-GP FSS line). Triple weighing:
(1) **Different problem** — few-shot supervised; no comparison or adoption
in paper #2. (2) **Useful citation for 8e**: they succeed *in the VAE
latent space* where our f_A failed — with supervision extracting what
unsupervised contrastive pressure could not; sharpens 8e's wording
("capacity/venue problem *for unsupervised separation*"). (3) **Seed for a
future line δ — few-shot per-type calibration**: a GP head (calibrated
uncertainty; ties to Direction I's conformal thread) over our per-t error
signatures, trained from 5–10 annotated examples per type, as the middle
road between annotation-free and GrandQC-scale annotation — natural
clients: the per-type timestep weighting problem (E3) and the fold
transfer collapse (Tier-1-motivated → confirmation on Tier 2, never
GrandQC, per the standing discipline); dovetails with the PRODIGY penmark
annotation ask. [curated: non-scientific passage removed] 

## 2026-09-04 — Note recorded (8b-level): Diffuse-to-Detect (arXiv:2605.26468) — related-work ammunition

Verified: Yin et al., 2026 — unsupervised IC latent-defect screening on
tabular parametric test data; AE compression → DiT → ε-prediction error
over **mid-range timesteps**, wafer-position conditioning embeddings, wide
PyOD/DTE baseline table. Three-line weighing: (1) independent cross-domain
convergence on our design choices — latent DiT + ε-error scoring + mid-t
operating window (our t650/t800 story rediscovered in silicon); citable as
"mid-t emerges cross-domain". (2) Conditioning counterpoint for the
Mechanism section: theirs is *informative* conditioning kept at inference;
ours works content-free and inference-free — two points on one map,
sharpening our claim's wording. (3) Baseline-table template, and a pointer
to DTE (diffusion-time estimation as score) — a second cheap
diffusion-native baseline family beside the feature-density gap; low
priority, kin to line γ's adaptive-t thread. No experiment implied.

## 2026-09-04 — Note recorded (8b-level): DACLIP / VLM-ZSAD family (Ma et al., TIP 2026)

Verified: IEEE TIP vol. 35, pp. 2843–2856 (2026) — CLIP-based zero-shot
anomaly detection with domain-expert routing and learnable prompts
injected into both encoders; industrial+medical benchmarks. Weighing:
(1) **Related-work positioning sentence earned:** ZSAD's "zero-shot"
transfers anomaly knowledge from *auxiliary annotated corpora* to unseen
categories; our setting assumes no anomaly annotations exist anywhere —
different promise to the user, one clean sentence in the map.
(2) **Baseline candidate #3 (below the density baseline in priority):**
training-free VLM probe (WinCLIP-style prompts + similarity) with a
pathology VLM (PLIP/CONCH) — half-a-day; the reviewer-plausible "why not
text prompts?" question, sharpest for penmark ("pen marking" is
linguistically obvious). Risk declared up front: if a training-free VLM
catches penmark well, we want that knowledge pre-submission, with the
answer ready (ours needs no VLM, no prompts, no auxiliary data, and
covers the non-linguistic types). (3) Echoes: expert routing ↔ the
MLAE/channel-#3 thread; injected prompts = informative-direction
conditioning — same Mechanism counterpoint as Diffuse-to-Detect. No
experiment scheduled; pre-registration required if the probe runs.

## 2026-09-04 — Note recorded (8b-level): LoRACLR (CVPR 2025, arXiv:2412.09622)

Verified: Simsar et al. — post-hoc merging of multiple pre-trained
concept-LoRAs into one ΔW via a contrastive objective on input-output
pairs (same-concept attract, cross-concept repel); no retraining, ~12
LoRAs in minutes. Two roles here: (1) **feasibility citation for the
parked task-vector negation** (unlearning entry, option 1): demonstrates
that post-hoc weight-space operations on LoRAs with a targeted objective
preserve function and steer behavior — our negation is the simpler
(arithmetic) member of that family. (2) **Third member of the
adapter-space map** for any channel-#3 write-up: MSLoRA-CR = geometry
*during* training; MLAE = stochasticity *during* training; LoRACLR =
geometry *after* training. Distant extra: if per-type adapters ever exist
(line-δ conversations), LoRACLR-style merging is their composition
mechanism. No experiment implied.

## 2026-09-04 — E1θ results (part 2): the intensity curve is FLAT across 8× — no tunable there, and that is the finding

Ladder complete at t650 (excess over basic 1.340): ×0.5 → 1.809 (+0.469);
×1 → 1.714–1.783 (three runs); ×2 → 1.731; ×4 → **1.822** (+0.482). Total
spread ~0.11 < s_seed(650)=0.126; every point clears the 2× bar; t800
likewise flat (2.50–2.56). The var2 OOF dip (1.99) is resolved as noise
(×4 returns to 2.11 — no monotonic trend); no per-type lever anywhere on
the ladder (bubble 1.44–1.55 throughout).

**Timestamped conjecture disconfirmed, favorably:** ×4 keys carry token
norms ~58 vs ~16 at pretraining (3.6× off-scale) and the mechanism
delivers its full benefit regardless — the cross-attention pathway is
robust far outside its training statistics. T1's inverted-U was not
observed in [×0.5, ×4]; the plateau is wide.

**Line-β resolution.** No larger effect is available through intensity;
what the ladder bought instead is the rarer property: **no sensitive
hyperparameter at all** — content (E1ζ), provenance (E1η), and intensity
over 8× (E1θ) all irrelevant. One figure, seven runs, one flat line.
**Final line-β configuration declared: ×1** (canonical — matches the real
embeddings' statistics; triply measured). The line's remaining road:
mechanism pair (fresh-vs-fixed + LoRA-dropout probe), then honest
slide-level LOOCV of the final configuration, then the reserved GrandQC
second look at 97.5% CI — [curated: non-scientific passage removed] 

## 2026-09-04 — E1ι results: T1 × channel-specific — perturbation suffices, but only through the conditioning pathway

(Operational note first: arm 2 OOM'd at launch — lora_dropout's mask+copy
activations on 224 modules exceed the 40GB card; --grad-checkpoint added
(identical updates, peak 33.4→7.2GB, 147 min) and the run completed.)

**Arm 1 (fresh-per-step Gaussian, no fixed identities): T1 confirmed.**
t650 d = **1.762** (excess +0.422 ≈ 3.4× s_seed), inside the synthetic
band; per-type fingerprint matches (bubble 1.43, OOF 2.12). Consistent
pseudo-identities are unnecessary → T2 (keying) is dead; the mechanism is
perturbation-as-regularization, and the noise-injection ≈ Jacobian-penalty
line (Bishop) applies to the conditioning input near-directly.
**Deployment corollary — the strongest yet:** no cache is needed at all;
the entire mechanism is the per-token mu/sd (2×16×1536 floats, ~200 KB)
plus one randn per step.

**Arm 2 (LoRA dropout 0.1, no conditioning): channel-specific.** t650
d = 1.231, excess **−0.109** (|excess| < s_seed → null per the frozen
reading; marginally negative); t800 2.406 ≈ basic. Weight-space
perturbation at this probe does not reproduce the effect — the
regularization acts through the conditioning/cross-attention pathway
specifically. One probe, one rate; the channel-#3 question is answered at
the probe level, full MLAE stays parked. Descriptive, no claim: dropout
shifts the t-profile low (t500 d 1.20 vs the conditioning family's flat
~1.00) — a different fingerprint, recorded.

**Mechanism section quadrant: T1 × specific.** The paper's story: input
perturbation on the conditioning pathway regularizes the denoiser
(content-, provenance-, intensity-, and identity-free — E1ζ/η/θ/ι), and
the pathway matters (dropout control). Final β configuration stands as
declared (×1 synthcond); freshcond is functionally equivalent and even
simpler — elevating it to final config would need a dated amendment plus
seed robustness (it has one seed), decided at slide-level pre-registration
time.

## 2026-09-04 — E1κ results: freshcond locked as final; slide-level grade FULL (2/2 clear)

Gate: `basic_freshcond_seed7` t650 d = 1.755 (excess +0.415 ≈ 3.3× s_seed),
0.007 from s42's 1.762 — the tightest patch-level seed pair the line has
produced; the amendment's condition is met and **fresh-per-step Gaussian
conditioning is the β-line final configuration** (~200 KB of per-token
statistics, one randn per step, no cache, no encoder).

Slide level (honest LOOCV, t800, the E1δ instrument): basic_freshcond
**0.6716**, basic_freshcond_seed7 **0.6714** — both above the 0.6679 bar
(basic 0.6567 + s_slide 0.0112); excesses +0.0149/+0.0147 ≈ 1.3× s_slide.
Seed spread 0.0002 — the tightest slide-level pair on record (selfcond
triple spanned 0.0103). **Grade: FULL — 2/2 clear**, strictly better than
selfcond's E1ε "mixed" (2/3); the line proceeds to the reserved GrandQC
second look carrying this grade. Grid-max reference only: 0.6923/0.6930.

Deviation noted honestly: the LOOCV producer still writes report.json to
the shared loocv_union/ dir (the per-run-dir lesson is implemented in
tier1 but not retrofitted here); the previous report was overwritten
again. No loss: per-model counts caches persist, and menu metadata is
deterministically recoverable (proven on 3 Sep).

Operational notes: (a) the seed-7 gate training first launched into a
card already hosting the freshcond infer (OOM before step 10; zero loss;
relaunched after a gpustat check — mixed-job hours get a gpustat before
every launch); (b) infer_wsi prints mag err 50.01% on the two 20×-native
HU slides (E4 finding) — identical across all models since the first
inference, both slides clean, symmetric in every comparison; recorded at
the point of use.

### Tier 1 second look (the reserved one): freshcond vs basic — pre-registration (4 September 2026, pre-launch)

The look reserved on 3 Sep (E1η entry) is now spent on the β-line final
configuration, which arrives with full dev standing (E1κ: patch gate
3.3× s_seed; slide level 2/2 above bar, spread 0.0002).

**Endpoint (declared once): pooled ΔF1(basic_freshcond − basic) on the
GrandQC MPP10 set, same frozen machinery as the first look** — option-B
canvases, uncond t800 seed-0, label-free recalibration at (65,75) on each
model's own pooled valid-cell distribution, evaluate_wsi postprocess
(σ=2, morph=5), stratified paired case bootstrap 20,000/seed 0. **Two-look
multiplicity correction, as declared: 97.5% CI** (percentiles 1.25/98.75).
CI > 0 → CONFIRMED at the corrected level; crossing → UNRESOLVED;
< 0 → DISCONFIRMED. Everything else descriptive.

**Efficiency declaration (part of the protocol, not a shortcut):** the
`basic` arm's cell canvases from `tier1_grandqc_20260903/` are REUSED —
basic scoring is deterministic (same checkpoint, per-case seed-0
generator, same block set), so a re-run would reproduce identical cells;
recomputing them would spend ~4.7 GPU-hours to re-derive known bytes. The
freshcond arm is scored fresh into the same (new) run dir. The finalize
step recomputes basic's recalibration thresholds on this run's pooled
distribution from the reused canvases — bit-identical inputs, so any
difference from the first look's thresholds would itself be a red flag
(checked and reported).

**Producer changes (pre-declared):** tier1_grandqc.py gains (a) the
`basic_freshcond` checkpoint in CKPT; (b) a `--ci` parameter (default
95.0; this run uses 97.5) replacing the hard-coded 2.5/97.5 percentiles;
(c) a `--reuse-cells FROM_RUN MODEL` option that symlinks an existing
cells_{MODEL} directory into the new run dir after verifying its
phase1_{MODEL}.json matches the audit (281/33,361). No threshold
parameter exists, as before.

**Prediction (recorded, honest):** dev slide-level excess of freshcond
(+0.0149) sits between selfcond's mean (+0.015) and its own tight pair;
the first look mapped +0.015 dev → +0.0073 GrandQC. Expectation: ΔF1 in
the +0.005…+0.010 band; the corrected CI makes CONFIRMED harder than in
look one — an UNRESOLVED outcome at 97.5% with a positive point estimate
is a live possibility and will be reported exactly as such.

## 2026-09-05 — SECOND LOOK RESULT: CONFIRMED at 97.5% — ΔF1 +0.0129, CI (+0.0068, +0.0201)

Both declared checks passed before the endpoint was read: basic
recalibration thresholds from the reused canvases are identical to look
one (0.26978/0.31806 — bit-faithful reuse), and both models pool the same
134,365,568 valid cells. freshcond recalibrates at 0.29452/0.34440;
pooled F1 0.3637 vs basic 0.3508.

**Primary endpoint: ΔF1(basic_freshcond − basic) = +0.0129, stratified
paired bootstrap CI at the two-look-corrected 97.5% level = (+0.0068,
+0.0201) → CONFIRMED.** The recorded prediction (+0.005…+0.010, with
positive-but-UNRESOLVED flagged as live) was exceeded: the effect nearly
doubles look one's +0.0073 and clears a stricter bar. The β line's final
configuration — per-token mu/sd (~200 KB) + one randn per step, no
encoder, no cache, zero inference cost — now holds its own pre-registered
external confirmation, independent of look one's.

Cosmetic, recorded: the finalize print labels the interval "CI95="
regardless of level (hard-coded string); the JSON's ci_level field
carries the true 97.5. Fix folded into any future producer edit, not
worth its own commit.

**Both reserved GrandQC looks are now spent.** The set is closed for this
model family; any further hypothesis (per-type operating points, fold
transfer fixes, new configurations) confirms on Tier 2/Tier 3 or new
sets, per the standing discipline.  [curated: non-scientific passage removed] 

**Second-look per-type composition (addendum, same date).** The gain is
again carried entirely by out-of-focus: sens 0.653 → **0.698** (+0.045,
more than double look one's +0.019); fold (0.04), air-bubble (0.25), and
dark-spot-foreign (0.24) are ties. The effect's per-type identity is
consistent across both looks and both configurations — a training-time
regularizer that, out of domain, buys focus-artifact sensitivity
specifically. The fold collapse stands untouched in both models, exactly
as recorded in look one.

### B1. Feature-density baseline: GMM/kNN over UNI2-h embeddings (added 5 September 2026, pre-launch)

Pre-registered before any code.  [curated: non-scientific passage removed]  Purpose is a table row that
answers "why diffusion", whichever way it falls.

**Features.** UNI2-h embeddings, the project's standard extraction
(16×1536 per 1024-px patch). Reference set: the 2,185 clean training
patches (the cache behind E1η's statistics). Scored set: the standing
validation pool (96 clean + 260 artifact patches from the two held-out
slides) — embedded once with the same pipeline (val-pool embedding pass;
new script adapted from uni2h_embed_train.py, ~minutes of GPU).

**Scorers (all fit on the 2,185 clean only; no artifact touches any
fit):**
- B1a kNN: score = mean cosine distance to the k=5 nearest clean
  neighbors, on the 16-token-mean embedding (1536-d per patch).
- B1b Mahalanobis: score = Mahalanobis distance to the clean Gaussian
  (Ledoit-Wolf shrinkage covariance), same 1536-d representation.
- B1c GMM: k=8 diagonal-covariance components on the same representation,
  score = negative log-likelihood. (k fixed a priori at 8 — no selection;
  recorded as arbitrary-but-frozen.)

**Reading (frozen).** Report Cohen's d and AUROC per scorer on the pool,
plus per-type d for bubble/OOF (the diagnostic's convention). Comparison
anchors: basic t650 d=1.340 / t800 d=2.416; freshcond t650 1.762 / t800
2.550. Verdicts, pre-declared: any baseline d(pooled) ≥ 2.0 →
"feature-density is competitive; the paper must argue diffusion on other
grounds (localization, zero-inference-cost gain, per-type profile)";
all < 1.5 → "density family materially behind; one table row settles the
question"; between → reported as-is, no massaging. Narrative footnote
either way: every scorer here REQUIRES the foundation model at inference
— the very dependency the β line removes.

**Not in scope:** patch-level fusion with diffusion scores, tuning k or
components, pixel-level maps — this is a baseline, not a method.

**B1 correction (5 September 2026, before any B1 code ran).** The
pre-registration misstated the scored pool as "96 clean + 260 artifact":
96 is the training monitor's clean subsample. The diagnostic pool — and
B1's scored set — is the standing **1,167 clean + 260 artifact = 1,427
patches**, whose UNI2-h embeddings already exist on disk
(`uni2h_emb_val1427_rev-d517a8dd`, built for E1β and consumed by every
selfcond_diag run since). Consequently no embedding pass is needed; B1
runs entirely on existing caches. The frozen verdict thresholds are in
d/AUROC terms and are unaffected; the reference-set definition (2,185
clean training patches) is unaffected. Recorded before execution.

## 2026-09-05 — B1 results: density family materially behind (all pooled d < 1.5) — and inversely specialized

Run on existing caches only (no GPU; sklearn user-installed in the
container). Manifest carried no explicit labels → catalogue-order split
(1,167+260) per the correction; types present bubble/OOF/penmark.

| scorer | pooled d | AUROC | d bubble | d OOF |
|---|---|---|---|---|
| kNN5 cosine | **1.29** | 0.770 | 2.42 | 0.34 |
| Mahalanobis (LW) | 0.39 | 0.608 | 0.79 | −0.03 |
| GMM8 diag NLL | 0.80 | 0.760 | 0.77 | 0.81 |

**Frozen verdict: all < 1.5 → "density family materially behind; one
table row settles the question."** Anchors: basic 1.340/2.416, freshcond
1.762/2.550.

**The finding inside the finding: inverse specialization.** kNN sees
air-bubble at diffusion-t800 level (2.42) yet is near-blind to
out-of-focus (0.34; Mahalanobis slightly negative) — exactly the mirror
of the diffusion detector, whose external gain lives entirely in OOF
(both GrandQC looks). Consistent explanation, recorded as interpretation:
UNI2-h features are trained toward photometric invariance (blur
augmentation) — defocus barely moves the embedding, while structurally
foreign content (bubble) leaves the clean manifold; the ε-predictor works
where blur IS the signal. The paper's "why diffusion" answer thus
upgrades from "it wins" to "**it sees what foundation-feature density
cannot, by construction**" — with the complementarity noted in Discussion
as future work, not pursued (B1 scope stands). Narrative footnote stands:
every B1 scorer requires the foundation model at inference; the β-line
detector requires none anywhere.

 [curated: non-scientific passage removed] ** Writing begins.

## 2026-09-05 — Idea recorded (8b-level): line ε — cross-family score fusion (B1-prompted, explicitly outside paper #2)

B1's inverse specialization (kNN-cosine bubble d=2.42 / OOF 0.34; the
diffusion detector the mirror image) is the textbook setup for score-level
ensembling — two detectors with decorrelated errors. **Prediction,
timestamped:** a patch-level fusion (fit frozen on dev, patch level only —
Kish n_eff 6.2 forbids slide-level weight fitting) inherits the better arm
per type: bubble ~1.5 → ~2.4 while OOF holds ~2.1; pooled d plausibly
> 2.8, above anything measured in the project.

**Why it is line ε and not paper #2 material — three recorded reasons:**
(1) it reintroduces the foundation model at inference, negating the
"~200 KB, no encoder anywhere" atom that both confirmed endpoints belong
to — a different point in the trade-off space, not an upgrade of the same
claim; (2) no confirmatory arena remains — both GrandQC looks are spent,
so any fusion claim needs its own protocol on Tier 2/Tier 3 or a fresh
set, with its own pre-registration; (3) E3's standing lesson — obvious
fusions fail in non-obvious ways (union rejected; z-norm killed penmark)
— demands a designed scheme, not an afternoon's weighted sum.

Paper #2 carries exactly one sentence in Discussion: the inverse
specialization suggests a complementary ensemble, deliberately left to
future work because it reintroduces the encoder at inference. Line ε
activates only with its own pre-registration entry.

**Correction (5 September 2026, figure-preparation stage).** The E1θ
part-2 phrase "one figure, seven runs, one flat line" miscounts: the
variance ladder comprises **six** trainings (×0.5; ×1 as three runs —
synth s42/s7/redraw; ×2; ×4). Shufcond belongs to the content ablation,
not the ladder. Caught by K.M. reading figure F2; the figure itself was
correct.

**Slide-disjointness assertion (5 September 2026, paper-#2 Data section).**
Manifest/heatmap-derived slide sets verified programmatically: 16 train,
2 validation, 24 test; all pairwise intersections empty; union 42 — the
Data subsection's disjointness sentence now rests on this check.
