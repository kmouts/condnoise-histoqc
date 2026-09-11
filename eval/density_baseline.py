"""B1 -- feature-density baseline over UNI2-h embeddings (Gaps B1, 5 Sep 2026).

Reference: 2,185 clean training embeddings. Scored: the 1,427-patch val
pool (1,167 clean + 260 artifact; B1 correction of 5 Sep). Scorers fit on
clean only: kNN(k=5, cosine), Mahalanobis (Ledoit-Wolf), GMM(k=8, diag,
seed 0). Representation: 16-token mean -> 1536-d per patch. Outputs
Cohen's d (artifact-clean, pooled SD -- the diagnostic's convention),
AUROC, and per-type d for air-bubble / out-of-focus. Frozen verdicts in
the B1 entry; anchors printed alongside.
"""
import json
import os

import numpy as np
import torch
DATA_ROOT = os.environ.get("DIFFQC_ROOT", "/nfs1/kmouts")  # set to your data root

LAT = DATA_ROOT + "/DiffusionQC/dgx_shared/latents"
TRAIN = os.path.join(LAT, "uni2h_emb_train2185_rev-d517a8dd")
VAL = os.path.join(LAT, "uni2h_emb_val1427_rev-d517a8dd")


def load_dir(d, n_expect):
    f = [x for x in os.listdir(d) if x.endswith((".pt", ".pth"))]
    assert len(f) == 1, (d, f)
    obj = torch.load(os.path.join(d, f[0]), map_location="cpu")
    emb = obj if torch.is_tensor(obj) else obj[[k for k, v in obj.items()
                                                if torch.is_tensor(v) and v.dim() == 3][0]]
    assert tuple(emb.shape) == (n_expect, 16, 1536), tuple(emb.shape)
    man = json.load(open(os.path.join(d, "manifest.json")))["manifest"]
    assert len(man) == n_expect
    return emb.float().mean(dim=1).numpy(), man   # (N,1536)


def cohens_d(a, c):
    na, nc = len(a), len(c)
    sp = np.sqrt(((na-1)*a.std(ddof=1)**2 + (nc-1)*c.std(ddof=1)**2) / (na+nc-2))
    return float((a.mean() - c.mean()) / sp)


def auroc(pos, neg):
    from sklearn.metrics import roc_auc_score
    y = np.r_[np.ones(len(pos)), np.zeros(len(neg))]
    return float(roc_auc_score(y, np.r_[pos, neg]))


def main():
    ref, _ = load_dir(TRAIN, 2185)
    val, man = load_dir(VAL, 1427)
    lab = [r.get("label", r.get("catalogue", "")) for r in man]
    is_art = np.array([("artifact" in str(l)) for l in lab])
    if is_art.sum() == 0:                      # fall back to catalogue order
        is_art = np.r_[np.zeros(1167, bool), np.ones(260, bool)]
        print("  (labels not in manifest; using catalogue order 1167+260)")
    assert is_art.sum() == 260 and (~is_art).sum() == 1167, is_art.sum()
    typ = np.array([str(r.get("type", r.get("artifact_type", ""))) for r in man])
    print(f"manifest types present: {sorted(set(typ[is_art]))}")

    scores = {}
    # B1a kNN cosine k=5
    rn = ref / np.linalg.norm(ref, axis=1, keepdims=True)
    vn = val / np.linalg.norm(val, axis=1, keepdims=True)
    sim = vn @ rn.T
    top5 = np.sort(sim, axis=1)[:, -5:]
    scores["kNN5_cos"] = 1.0 - top5.mean(axis=1)
    # B1b Mahalanobis, Ledoit-Wolf
    from sklearn.covariance import LedoitWolf
    lw = LedoitWolf().fit(ref)
    scores["mahalanobis_LW"] = lw.mahalanobis(val) ** 0.5
    # B1c GMM diag k=8
    from sklearn.mixture import GaussianMixture
    gm = GaussianMixture(8, covariance_type="diag", random_state=0,
                         max_iter=500).fit(ref)
    scores["GMM8_nll"] = -gm.score_samples(val)

    print("\nanchors: basic d650=1.340 d800=2.416 | freshcond d650=1.762 d800=2.550")
    out = {}
    for name, s in scores.items():
        a, c = s[is_art], s[~is_art]
        d, au = cohens_d(a, c), auroc(a, c)
        row = dict(cohens_d=round(d, 3), auroc=round(au, 4))
        for t, key in (("air-bubble", "d_air-bubble"),
                       ("out-of-focus", "d_out-of-focus")):
            m = is_art & (typ == t)
            if m.sum() >= 30:
                row[key] = round(cohens_d(s[m], c), 3)
        out[name] = row
        print(name, row)
    outp = DATA_ROOT + "/DiffusionQC/dgx_shared/evaluations/density_baseline_b1.json"
    json.dump(out, open(outp, "w"), indent=1)
    print("wrote", outp)


if __name__ == "__main__":
    main()
