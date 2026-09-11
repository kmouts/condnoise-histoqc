"""F2 (ladder flat-line) + T1 (patch family table) from primary reports.
Reuses the verified paths of verify_claims.py; matplotlib Agg."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

EV = DATA_ROOT + "/DiffusionQC/dgx_shared/evaluations"
FAM = [  # (label, run, arm, group)
    ("baseline", "selfcond_diag", "basic", "baseline"),
    ("self s42", "selfcond_diag_e1b", "basic_selfcond", "self"),
    ("self s7", "selfcond_diag_e1c_r2", "basic_selfcond_seed7", "self"),
    ("self s123", "selfcond_diag_seed123", "basic_selfcond_seed123", "self"),
    ("shuffled", "selfcond_diag_shufcond", "basic_shufcond", "contentfree"),
    ("synth s42", "selfcond_diag_synthcond", "basic_synthcond", "contentfree"),
    ("synth s7", "selfcond_diag_synthcond_s7", "basic_synthcond_seed7", "contentfree"),
    ("synth redraw", "selfcond_diag_draw1", "basic_synthcond_draw1", "contentfree"),
    ("var x0.5", "selfcond_diag_var05", "basic_synthcond_var05", "ladder"),
    ("var x2", "selfcond_diag_var2", "basic_synthcond_var2", "ladder"),
    ("var x4", "selfcond_diag_var4", "basic_synthcond_var4", "ladder"),
    ("fresh s42", "selfcond_diag_freshcond", "basic_freshcond", "final"),
    ("fresh s7", "selfcond_diag_freshcond_s7", "basic_freshcond_seed7", "final"),
    ("dropout ctrl", "selfcond_diag_dropout01", "basic_dropout01", "control"),
]
rows = []
for label, run, arm, grp in FAM:
    r = json.load(open(os.path.join(EV, run, "report.json")))
    rows.append((label, grp, r[f"{arm}_t650_un"]["cohens_d"],
                 r[f"{arm}_t800_un"]["cohens_d"]))

# ---- T1 markdown ----
with open(DATA_ROOT + "/code/paper2/table_t1.md", "w") as f:
    f.write("| arm | group | d (t650) | d (t800) |\n|---|---|---|---|\n")
    for label, grp, d6, d8 in rows:
        f.write(f"| {label} | {grp} | {d6:.3f} | {d8:.3f} |\n")

# ---- F2: variance ladder flat line ----
S_SEED = 0.126
BASE = rows[0][2]
lad = {"x0.5": None, "x1 (3 runs)": [], "x2": None, "x4": None}
for label, grp, d6, _ in rows:
    if label == "var x0.5": lad["x0.5"] = [d6]
    elif label in ("synth s42", "synth s7", "synth redraw"): lad["x1 (3 runs)"].append(d6)
    elif label == "var x2": lad["x2"] = [d6]
    elif label == "var x4": lad["x4"] = [d6]
xs, xlabels = [0.5, 1, 2, 4], ["x0.5", "x1", "x2", "x4"]
fig, ax = plt.subplots(figsize=(5.6, 3.9))
d_by = {label: d6 for label, grp, d6, d8 in rows}
print("F2 points plotted:", {k: [round(v,3) for v in vv] for k, vv in lad.items()})
jit = {0: 1.0, 1: 0.90, 2: 1.11}
for x, key in zip(xs, ["x0.5", "x1 (3 runs)", "x2", "x4"]):
    for i, d in enumerate(sorted(lad[key])):
        ax.plot(x * jit.get(i if len(lad[key]) > 1 else 0, 1.0), d,
                "o", color="#1f6fb2", ms=6, zorder=3,
                label="synthetic Gaussian" if (key, i) == ("x0.5", 0) else None)
# the rest of the content-free family, at its x1 statistics
ax.plot(0.80, d_by["shuffled"], "s", color="#7bb0d9", ms=6, zorder=3,
        label="shuffled real")
for i, lbl in enumerate(["fresh s42", "fresh s7"]):
    ax.plot(1.24 + 0.12*i, d_by[lbl], "D", color="#134d7a", ms=6, zorder=3,
            label="fresh per-step (final)" if i == 0 else None)
ax.axhline(BASE, color="#888", ls="--", lw=1, label="baseline")
ax.axhline(BASE + 2*S_SEED, color="#c33", lw=1.4,
           label="pre-registered bar")
from matplotlib.ticker import NullFormatter, NullLocator
ax.set_xscale("log"); ax.set_xticks(xs); ax.set_xticklabels(xlabels)
ax.xaxis.set_minor_locator(NullLocator())
ax.xaxis.set_minor_formatter(NullFormatter())
ax.set_xlabel("synthetic conditioning std multiplier")
ax.set_ylabel("Cohen's d (t = 650)")
ax.set_ylim(1.25, 1.95)
ax.legend(fontsize=8, loc="upper center",
          bbox_to_anchor=(0.5, -0.20), ncol=2, frameon=False,
          columnspacing=1.4, handletextpad=0.5)
ax.set_title("The content-free conditioning family: flat across an 8x "
             "intensity range", fontsize=9.5)
fig.tight_layout()
fig.subplots_adjust(bottom=0.34, left=0.11, right=0.97)
fig.savefig(DATA_ROOT + "/code/paper2/fig_f2_ladder.png", dpi=200)
print("wrote table_t1.md + fig_f2_ladder.png")
for label, grp, d6, d8 in rows:
    print(f"  {label:14s} {grp:11s} {d6:.3f} {d8:.3f}")
