### T2a. Slide level (honest LOOCV, dev; bar = 0.6679)

| model | pooled F1 | vs bar |
|---|---|---|
| baseline (E1δ record) | 0.6567 | — |
| self-cond s42/s7/s123 (E1ε record) | 0.6764 / 0.6661 / 0.6730 | 2/3 clear |
| final s42 | 0.6716 | clears |
| final s7 | 0.6714 | clears |

### T2b. External endpoints (GrandQC MPP10, 281 cases)

| look | pair | ΔF1 | CI | level | verdict |
|---|---|---|---|---|---|
| 1 | self-cond − baseline | +0.0073 | (+0.0042, +0.0110) | 95% | CONFIRMED |
| 2 | final − baseline | +0.0129 | (+0.0068, +0.0201) | 97.5% | CONFIRMED |
