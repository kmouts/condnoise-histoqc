"""F3: per-type external sensitivities — the gain lives in OOF; fold collapses."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

EV = DATA_ROOT + "/DiffusionQC/dgx_shared/evaluations"
l1 = json.load(open(os.path.join(EV, "tier1_grandqc_20260903", "tier1_report.json")))
l2 = json.load(open(os.path.join(EV, "tier1_secondlook_20260904", "tier1_report.json")))

types = ["out-of-focus", "air-bubble", "dark-spot-foreign", "fold"]
tlabels = ["out-of-focus", "air-bubble", "dark-spot", "fold"]
def sens(rep, model):
    return [rep[model]["per_type"][t]["sens"] for t in types]

basic = sens(l1, "basic")
selfc = sens(l1, "basic_selfcond")
fresh = sens(l2, "basic_freshcond")

x = np.arange(len(types)); w = 0.26
fig, ax = plt.subplots(figsize=(5.6, 3.4))
ax.bar(x - w, basic, w, label="baseline", color="#9aa5b1")
ax.bar(x,     selfc, w, label="self-cond (look 1)", color="#5b8fc9")
ax.bar(x + w, fresh, w, label="final (look 2)", color="#1f6fb2")
ax.plot([x[-1] - w*1.6, x[-1] + w*1.6], [0.47, 0.47], color="#c33", ls="--", lw=1.2)
ax.annotate("dev fold sens = 0.47", xy=(x[-1], 0.47), xytext=(x[-1] - 1.15, 0.52),
            fontsize=8, color="#c33",
            arrowprops=dict(arrowstyle="->", color="#c33", lw=0.8))
ax.set_xticks(x); ax.set_xticklabels(tlabels, fontsize=9)
ax.set_ylabel("external sensitivity (GrandQC)")
ax.set_ylim(0, 0.78)
ax.legend(fontsize=8)
ax.set_title("External per-type profile: OOF carries the gain; fold does not transfer",
             fontsize=9.5)
fig.tight_layout()
fig.savefig(DATA_ROOT + "/code/paper2/fig_f3_pertype.png", dpi=200)
print("wrote fig_f3_pertype.png")
for lbl, v in (("basic", basic), ("selfcond", selfc), ("freshcond", fresh)):
    print(" ", lbl, [round(s, 3) for s in v])
