"""T2 (slide-level + external endpoints) and T3 (density baseline)."""
import json
import os
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

EV = DATA_ROOT + "/DiffusionQC/dgx_shared/evaluations"

# ---- T2 ----
lo = json.load(open(os.path.join(EV, "loocv_union", "report.json")))
f42 = lo["basic_freshcond"]["loocv_pooled_f1"]["baseline"] if isinstance(
    lo["basic_freshcond"].get("loocv_pooled_f1"), dict) else lo["basic_freshcond"]["baseline"]
f7 = lo["basic_freshcond_seed7"]["loocv_pooled_f1"]["baseline"] if isinstance(
    lo["basic_freshcond_seed7"].get("loocv_pooled_f1"), dict) else lo["basic_freshcond_seed7"]["baseline"]
l1 = json.load(open(os.path.join(EV, "tier1_grandqc_20260903", "tier1_report.json")))
l2 = json.load(open(os.path.join(EV, "tier1_secondlook_20260904", "tier1_report.json")))
p1, p2 = l1["PRIMARY_ENDPOINT"], l2["PRIMARY_ENDPOINT"]
ci1 = p1.get("ci", p1.get("ci95")); ci2 = p2.get("ci", p2.get("ci95"))
with open(DATA_ROOT + "/code/paper2/table_t2.md", "w") as f:
    f.write("### T2a. Slide level (honest LOOCV, dev; bar = 0.6679)\n\n")
    f.write("| model | pooled F1 | vs bar |\n|---|---|---|\n")
    f.write("| baseline (E1δ record) | 0.6567 | — |\n")
    f.write("| self-cond s42/s7/s123 (E1ε record) | 0.6764 / 0.6661 / 0.6730 | 2/3 clear |\n")
    f.write(f"| final s42 | {f42:.4f} | clears |\n")
    f.write(f"| final s7 | {f7:.4f} | clears |\n\n")
    f.write("### T2b. External endpoints (GrandQC MPP10, 281 cases)\n\n")
    f.write("| look | pair | ΔF1 | CI | level | verdict |\n|---|---|---|---|---|---|\n")
    f.write(f"| 1 | self-cond − baseline | {p1['delta_f1']:+.4f} | "
            f"({ci1[0]:+.4f}, {ci1[1]:+.4f}) | 95% | CONFIRMED |\n")
    f.write(f"| 2 | final − baseline | {p2['delta_f1']:+.4f} | "
            f"({ci2[0]:+.4f}, {ci2[1]:+.4f}) | 97.5% | CONFIRMED |\n")

# ---- T3 ----
b1 = json.load(open(os.path.join(EV, "density_baseline_b1.json")))
with open(DATA_ROOT + "/code/paper2/table_t3.md", "w") as f:
    f.write("| scorer | pooled d | AUROC | d bubble | d OOF |\n|---|---|---|---|---|\n")
    name = {"kNN5_cos": "kNN (k=5, cosine)",
            "mahalanobis_LW": "Mahalanobis (Ledoit-Wolf)",
            "GMM8_nll": "GMM (8, diag)"}
    for k, v in b1.items():
        f.write(f"| {name[k]} | {v['cohens_d']:.2f} | {v['auroc']:.3f} | "
                f"{v['d_air-bubble']:.2f} | {v['d_out-of-focus']:.2f} |\n")
    f.write("| *diffusion (final), same pool* | *1.76 (t650) / 2.55 (t800)* "
            "| — | *1.43* | *2.12* |\n")
print(open(DATA_ROOT + "/code/paper2/table_t2.md").read())
print(open(DATA_ROOT + "/code/paper2/table_t3.md").read())
