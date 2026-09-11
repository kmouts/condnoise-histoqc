# Figure & table captions (paper #2, v1 — 6 Sep 2026)

**Figure F1 (fig_f1_pipeline.png).** The proposed method as one
change to a standard pipeline. (A) Offline, once: UNI2-h encodes the
2,185 clean training patches; only the per-position first and second
moments (mu, sd — ~200 KB) are kept, and the encoder is discarded.
(B) LoRA fine-tuning of the frozen PixCell DiT, identical to the
baseline recipe except for the dashed red element: at every step the
conditioning input is a fresh synthetic draw e = mu + sd * eps. (C)
Inference is byte-identical for baseline and proposed models — one
unconditioned pass at a fixed timestep, error map, tissue masking,
percentile recalibration, thresholds carried from training slides. No
pathology encoder appears anywhere at deployment.

**Figure F2 (fig_f2_ladder.png).** Patch-level separation (Cohen's d at
the pre-registered t = 650 axis) for the nine content-free conditioned
trainings, against the baseline (dashed, d = 1.34) and the
pre-registered effect bar (red: baseline + 2 x s_seed = 1.59, where
s_seed = 0.126 is the seed-noise floor of Section 3.5). Circles: the
six synthetic-Gaussian trainings of the variance ladder (x0.5 to x4;
the three x1 points are horizontally jittered for visibility). Square:
shuffled real embeddings (content ablation); diamonds: fresh per-step
resampling, the final configuration (two seeds) — both plotted near
x1, slightly offset horizontally, since they share the x1 statistics.
All nine trainings clear the bar; separation is flat across the 8x
intensity range. The LoRA-dropout control (d = 1.23, Section 4.6) is
not part of the conditioning family and is reported in the mechanism
table.

**Figure F3 (fig_f3_pertype.png).** External per-type sensitivity on
the GrandQC MPP10 cohort (281 cases) for the baseline, the look-1
model (self-conditioning), and the look-2 final model (fresh
synthetic conditioning), at matched per-model operating points. The
confirmed gains concentrate in out-of-focus; air-bubble and dark-spot
are ties. Fold sensitivity is near zero for every model including the
baseline — against a development-set fold sensitivity of 0.47 (dashed
red reference; note the development and GrandQC fold populations
differ in annotation taxonomy and morphology, Section 7.2) — a
symmetric transfer failure that bounds single-timestep operation, not
a deficit of the proposed training.

**Table T0 (in-text, Section 4.7).** The ablation chain in one view:
each row removes one property of the conditioning signal and reports
the resulting patch-level separation at the pre-registered t = 650
axis. Every content-free variant preserves the benefit; only the
pathway control (LoRA dropout in place of conditioning noise) loses
it. Ranges span the seeds/redraws of each arm.

**Table T1 (table_t1.md).** The twelve conditioned trainings and the
baseline: patch-level Cohen's d at t = 650 (pre-registered axis) and
t = 800, one row per training, grouped by family (self / shuffled /
synthetic + variance ladder / fresh) with the dropout control listed
separately.

**Table T2 (table_t2.md).** (a) Slide-level honest LOOCV on the
24-slide development test set: pooled F1 against the pre-declared bar
(baseline + 1 x s_slide = 0.6679). (b) The two pre-registered external
endpoints on GrandQC: ΔF1 with bootstrap CI (95% for look 1, 97.5% for
look 2 under the two-look alpha budget), both CONFIRMED.

**Table T3 (table_t3.md).** Feature-density baselines (kNN, Mahalanobis,
GMM over UNI2-h embeddings of the same validation pool) against the
diffusion detector: pooled Cohen's d and AUROC, plus per-type d for
the two classes where the families diverge most — the density family
sees air-bubbles and misses defocus; the diffusion detector shows the
reverse ordering (Section 6.4).
