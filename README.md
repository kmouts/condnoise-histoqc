# Conditioning-Noise Regularization for Diffusion-Based Artifact Detection

Code, figures, and laboratory record for the paper:

> *Conditioning noise is a free regularizer for LoRA fine-tuning: no
> pathology encoder required for diffusion-based artifact detection in
> histopathology.* K. Moutselos, I. Maglogiannis. [submitted; DOI at
> acceptance]

**Companion study** (benchmark reliability, same corpus):
arXiv:2608.30835.

## The method in ten lines

Fine-tune a latent diffusion backbone (PixCell-1024, frozen) with LoRA
(r=16) on clean tissue patches, exactly as usual -- except that the
conditioning input at every training step is a fresh random draw:

    e = mu + sd * eps,      eps ~ N(0, I),   e in R^{16 x 1536}

where mu, sd are per-position moments of UNI2-h embeddings over the
clean training patches, computed **once, offline** (~200 KB). The
encoder is then discarded. Inference is completely unchanged: one
unconditioned denoising pass at a fixed timestep; the error map is the
artifact score. No pathology foundation model appears at training or
at inference.

Measured effect: clean/artifact separation widens from d = 1.34 to
1.71-1.82 across nine trainings (t = 650), and two pre-registered
external endpoints on the GrandQC MPP10 cohort confirm pooled
dF1 = +0.0073 (95% CI) and +0.0129 (97.5% CI).

## Repository layout

    train/        LoRA fine-tuning with conditioning-noise injection
    score/        unconditioned scoring, heatmaps, recalibration
    eval/         diagnostics, honest LOOCV, external two-look protocol,
                  density baselines, figure/table generation (make_f*.py)
    record/       LABORATORY_RECORD.md -- the curated lab record (see below)
    paper/        figures and tables as submitted

## The laboratory record

record/LABORATORY_RECORD.md is the version-controlled lab notebook
of this study: dated pre-registrations, reading rules declared before
results, verdicts, and corrections documented in place. **It is a
curated edition**: all scientific entries are verbatim; passages
concerning submission strategy and project administration were
removed and are marked inline, and the companion study's development
record is documented through its own publication rather than here.
Provenance JSONs beside each released output reference internal
development-repository hashes; the Zenodo deposit is the public,
frozen witness of the exact released state.

## Data

TCGA whole-slide images (public), AIRAQc artifact annotations
(public; Gautam et al., MIDL 2025), GrandQC MPP10 external cohort
(public; Weng et al., Nat. Commun. 2024). No data are redistributed
here; the deposit contains our derived outputs (checkpoints, score
maps, evaluation JSONs) with provenance.

## Reproducing

Set DIFFQC_ROOT to your data root; each eval/ script then regenerates
its table or figure from the deposited JSONs, and eval/verify_claims.py
re-checks every number in the paper against its primary source.
Training requires 1x A100-80GB (~11 GPU-hours per run).

## Citation / License

Code: MIT (see LICENSE). Laboratory record: CC BY 4.0
(record/LICENSE_RECORD.md). Citation entries will be added when the
paper and deposit DOIs exist.
