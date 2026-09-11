"""Claim-level verification for paper #2 v1 (5 Sep 2026).
Reads ONLY primary sources (evaluation report.json files) and prints
every number the draft cites, next to the draft's claimed value.
Any MISMATCH line is a stop-and-fix condition."""
import json
import os
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

EV = DATA_ROOT + "/DiffusionQC/dgx_shared/evaluations"

def d650(run, arm):
    r = json.load(open(os.path.join(EV, run, "report.json")))
    return r[f"{arm}_t650_un"]["cohens_d"], r[f"{arm}_t800_un"]["cohens_d"]

CLAIMS = []  # (label, source_value, draft_value)

# --- Section 4 / 6.1: the family at t650 (and t800 range) ---
fam = {
    "basic (E1γ report)":        ("selfcond_diag", "basic"),
    "selfcond s42":              ("selfcond_diag_e1b", "basic_selfcond"),
    "selfcond s7":               ("selfcond_diag_e1c_r2", "basic_selfcond_seed7"),
    "selfcond s123":             ("selfcond_diag_seed123", "basic_selfcond_seed123"),
    "shufcond":                  ("selfcond_diag_shufcond", "basic_shufcond"),
    "synthcond s42":             ("selfcond_diag_synthcond", "basic_synthcond"),
    "synthcond s7":              ("selfcond_diag_synthcond_s7", "basic_synthcond_seed7"),
    "draw1":                     ("selfcond_diag_draw1", "basic_synthcond_draw1"),
    "var05":                     ("selfcond_diag_var05", "basic_synthcond_var05"),
    "var2":                      ("selfcond_diag_var2", "basic_synthcond_var2"),
    "var4":                      ("selfcond_diag_var4", "basic_synthcond_var4"),
    "freshcond s42":             ("selfcond_diag_freshcond", "basic_freshcond"),
    "freshcond s7":              ("selfcond_diag_freshcond_s7", "basic_freshcond_seed7"),
    "dropout01":                 ("selfcond_diag_dropout01", "basic_dropout01"),
}
vals = {}
print("=== patch-level d (t650, t800) from primary reports ===")
for label, (run, arm) in fam.items():
    try:
        a, b = d650(run, arm)
        vals[label] = (a, b)
        print(f"  {label:22s} t650={a:.3f}  t800={b:.3f}")
    except FileNotFoundError as e:
        print(f"  {label:22s} REPORT MISSING: {e}")

cond650 = [v[0] for k, v in vals.items()
           if k not in ("basic (E1γ report)", "dropout01")]
cond800 = [v[1] for k, v in vals.items()
           if k not in ("basic (E1γ report)", "dropout01")]
print("\n=== draft claims vs sources ===")
def check(label, src, draft, tol=5e-4):
    ok = abs(src - draft) <= tol
    print(f"  {'OK ' if ok else 'MISMATCH'} {label}: source {src:.4f} vs draft {draft}")
CLAIMS_SIMPLE = [
    ("baseline d650 = 1.34", vals["basic (E1γ report)"][0], 1.34, 5e-3),
    ("baseline d800 = 2.42", vals["basic (E1γ report)"][1], 2.42, 5e-3),
    ("final d650 = 1.76 (s42)", vals["freshcond s42"][0], 1.76, 5e-3),
    ("family min d650 = 1.59", min(cond650), 1.59, 5e-3),
    ("family max d650 = 1.82", max(cond650), 1.82, 5e-3),
    ("family min d800 = 2.41", min(cond800), 2.41, 5e-3),
    ("family max d800 = 2.76", max(cond800), 2.76, 5e-3),
    ("dropout d650 = 1.23", vals["dropout01"][0], 1.23, 5e-3),
    ("fresh seed pair gap = 0.007",
     abs(vals["freshcond s42"][0] - vals["freshcond s7"][0]), 0.007, 1e-3),
]
for c in CLAIMS_SIMPLE:
    check(*c)

# excesses band +0.25..+0.48
b = vals["basic (E1γ report)"][0]
exc = [v - b for v in cond650]
check("excess min = +0.25", min(exc), 0.25, 5e-3)
check("excess max = +0.48", max(exc), 0.48, 5e-3)

# --- 6.2 slide level ---
lo = json.load(open(os.path.join(EV, "loocv_union", "report.json")))
print("\n=== slide level (loocv_union/report.json — NOTE: overwritten by "
      "E1κ run; contains freshcond pair) ===")
for m in lo:
    if isinstance(lo[m], dict) and "loocv_pooled_f1" in lo[m]:
        print(f"  {m}: {lo[m]['loocv_pooled_f1']}")

# --- 6.3 external ---
for run, lbl in (("tier1_grandqc_20260903", "look one"),
                 ("tier1_secondlook_20260904", "look two")):
    r = json.load(open(os.path.join(EV, run, "tier1_report.json")))
    pe = r["PRIMARY_ENDPOINT"]
    ci = pe.get("ci", pe.get("ci95"))
    print(f"\n=== {lbl} === dF1={pe['delta_f1']:+.4f} CI={tuple(round(x,4) for x in ci)} "
          f"level={pe.get('ci_level', 95.0)}")
    for m in [k for k in r if isinstance(r[k], dict) and "pooled_f1" in r[k]]:
        row = r[m]
        oof = row["per_type"].get("out-of-focus", {}).get("sens")
        fold = row["per_type"].get("fold", {}).get("sens")
        print(f"  {m}: F1={row['pooled_f1']:.4f} OOF={oof:.3f} fold={fold:.3f}")

# --- 6.4 density ---
b1 = json.load(open(os.path.join(EV, "density_baseline_b1.json")))
print("\n=== B1 ===")
for k, v in b1.items():
    print(f"  {k}: {v}")
