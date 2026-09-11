"""F1: pipeline schematic — one change in training, none at inference."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import os
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

GREY, DARK, RED, LGREY = "#9aa5b1", "#1f2d3d", "#c0392b", "#e8ecf0"

fig, ax = plt.subplots(figsize=(7.0, 4.6))
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")

def box(x, y, w, h, text, fc="white", ec=DARK, lw=1.0, ls="-", fs=7.2,
        tc=None, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
        boxstyle="round,pad=0.25,rounding_size=0.8",
        fc=fc, ec=ec, lw=lw, linestyle=ls, mutation_scale=1.0))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center",
            fontsize=fs, color=tc or DARK,
            fontweight="bold" if bold else "normal", linespacing=1.25)

def arrow(x1, y1, x2, y2, color=DARK, lw=1.0, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
        arrowstyle="-|>", mutation_scale=9, color=color, lw=lw,
        linestyle=ls, shrinkA=1, shrinkB=1))

def zone(y0, y1, label):
    ax.add_patch(FancyBboxPatch((1, y0), 98, y1 - y0,
        boxstyle="round,pad=0.3,rounding_size=1.2",
        fc=LGREY, ec=GREY, lw=0.8, zorder=0))
    ax.text(3, y1 - 3.2, label, fontsize=8.2, fontweight="bold",
            color=DARK, ha="left", va="top")

# ---- Zone A: offline statistics ----
zone(72, 99, "A. Offline, once")
box(6, 76, 16, 12, "16 training slides\n2,185 clean patches", fs=6.8)
arrow(22.5, 82, 27.5, 82)
box(28, 76, 20, 12, "UNI2-h encoder\nused once, offline —\ndiscarded after this step",
    fc="#f2f2f2", ec=GREY, tc="#6b7683", fs=6.4)
arrow(48.5, 82, 53.5, 82)
box(54, 76, 24, 12, "mu, sd  (16 x 1536)\n~200 KB of statistics", bold=True, fs=7.0)

# ---- Zone B: training ----
zone(34, 70, "B. LoRA fine-tuning — the one change")
box(4, 40, 13, 11, "clean patch\n1024 px", fs=6.8)
arrow(17.5, 45.5, 21.5, 45.5)
box(22, 40, 10, 11, "VAE\nlatent", fs=6.8)
arrow(32.5, 45.5, 36.5, 45.5)
box(37, 40, 14, 11, "add noise\nat random t", fs=6.8)
arrow(51.5, 45.5, 55.5, 45.5)
box(56, 40, 20, 11, "PixCell DiT (frozen)\n+ LoRA r16 (trained)", fs=6.8)
arrow(76.5, 45.5, 80.5, 45.5)
box(81, 40, 14, 11, "eps-hat\nMSE loss", fs=6.8)
# the one change: conditioning injection
box(46.5, 55.5, 39, 11,
    "e = mu + sd * eps,   eps ~ N(0, I)\nresampled every step — no encoder, no cache",
    ec=RED, lw=1.6, ls="--", tc=RED, fs=6.6, bold=True)
arrow(66, 76, 66, 67, color=RED, lw=1.3, ls="--")   # stats -> injection
arrow(66, 55.5, 66, 51.5, color=RED, lw=1.3, ls="--")   # injection -> DiT

# ---- Zone C: inference ----
zone(2, 32, "C. Inference — unchanged; identical for baseline and proposed")
box(4, 8, 12, 11, "patch", fs=6.8)
arrow(16.5, 13.5, 19.5, 13.5)
box(20, 8, 10, 11, "VAE", fs=6.8)
arrow(30.5, 13.5, 33.5, 13.5)
box(34, 8, 13, 11, "noise to\nt=650/800", fs=6.8)
arrow(47.5, 13.5, 50.5, 13.5)
box(51, 8, 15, 11, "one pass,\nunconditioned", fs=6.8)
arrow(66.5, 13.5, 69.5, 13.5)
box(70, 8, 12, 11, "error map\n+ tissue mask", fs=6.4)
arrow(82.5, 13.5, 85.5, 13.5)
box(86, 8, 11, 11, "heatmap →\nthreshold", fs=6.4)
ax.text(50, 3.6, "no encoder anywhere at deployment",
        ha="center", fontsize=7.4, style="italic", color=DARK)

fig.tight_layout()
fig.savefig(DATA_ROOT + "/code/paper2/fig_f1_pipeline.png", dpi=200)
print("wrote fig_f1_pipeline.png")
