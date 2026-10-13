# Walk-forward backtest

Generated 2026-10-13 19:15 UTC. Regenerate with `python -m ats backtest`.

Every prediction uses only games that kicked off before that week's Tuesday 00:00 PT cutoff. Ratings, model fits, sigma, the NFL empirical margin distribution and calibration are all refit each week on past data only. Hyperparameters (prior strength, decay, ridge alpha) were fixed before running and not tuned on these results.

Break-even at -110 is 52.4%. A hit rate whose CI includes 50% is not distinguishable from a coin flip.

## NFL vs closing line

Evaluated seasons 2015-2026 (2026 partial); 3107 games with a line and a final score.

**Margin MAE (points, lower is better)**

| Market line | Ratings only (m2) | Blend (m3) |
|---|---|---|
| 9.81 | 10.21 | 9.82 |

Blend weights (first -> last week): market 0.91 -> 1.06, ratings model 0.15 -> -0.03. sigma (blend residual SD) averaged 13.0 pts.

**Brier score** (coin flip = 0.2500): calibrated blend 0.2500; ratings-only 0.2595.

**ATS hit rate of top-N picks per week** (pushes excluded)

| Picks | Record |
|---|---|
| Top 5 | 543-537 (50.3%, 95% CI 47.3-53.3, p=0.88) |
| Top 6 | 633-644 (49.6%, 95% CI 46.8-52.3, p=0.78) |
| Top 10 | 998-1042 (48.9%, 95% CI 46.8-51.1, p=0.34) |
| All games | 1482-1544 (49.0%, 95% CI 47.2-50.8, p=0.27) |

Model weight w (share of the model's disagreement with the market that is used): first 0.00, last 0.00, mean 0.00.

**Hit rate by calibrated edge** (all games)

| Edge | n | Hit rate | 95% CI |
|---|---|---|---|
| (-0.001, 0.01] | 3026 | 49.0% | 47.2-50.8 |

**Calibration of P(home covers)**

| Bin | n | Mean predicted | Observed |
|---|---|---|---|
| (0.48, 0.5] | 3026.0 | 0.500 | 0.490 |

## CFB (FBS v FBS) vs closing line

Evaluated seasons 2016-2026 (2026 partial); 7889 games with a line and a final score.

**Margin MAE (points, lower is better)**

| Market line | Ratings only (m2) | Blend (m3) |
|---|---|---|
| 12.30 | 12.70 | 12.32 |

Blend weights (first -> last week): market 0.84 -> 0.92, ratings model 0.26 -> 0.09. sigma (blend residual SD) averaged 16.0 pts.

**Brier score** (coin flip = 0.2500): calibrated blend 0.2500; ratings-only 0.2584.

**ATS hit rate of top-N picks per week** (pushes excluded)

| Picks | Record |
|---|---|
| Top 5 | 467-478 (49.4%, 95% CI 46.2-52.6, p=0.74) |
| Top 6 | 560-564 (49.8%, 95% CI 46.9-52.7, p=0.93) |
| Top 10 | 896-905 (49.8%, 95% CI 47.4-52.1, p=0.85) |
| All games | 3910-3825 (50.5%, 95% CI 49.4-51.7, p=0.34) |

Model weight w (share of the model's disagreement with the market that is used): first 0.00, last 0.29, mean 0.30.

**Hit rate by calibrated edge** (all games)

| Edge | n | Hit rate | 95% CI |
|---|---|---|---|
| (-0.001, 0.01] | 6797 | 50.6% | 49.4-51.8 |
| (0.01, 0.02] | 709 | 49.6% | 46.0-53.3 |
| (0.02, 0.03] | 164 | 53.0% | 45.4-60.5 |
| (0.03, 0.05] | 58 | 53.4% | 40.8-65.7 |
| (0.05, 1.0] | 7 | 42.9% | 15.8-75.0 |

**Calibration of P(home covers)**

| Bin | n | Mean predicted | Observed |
|---|---|---|---|
| (0.4, 0.45] | 1.0 | 0.450 | 1.000 |
| (0.45, 0.48] | 122.0 | 0.472 | 0.443 |
| (0.48, 0.5] | 3136.0 | 0.496 | 0.494 |
| (0.5, 0.52] | 4370.0 | 0.504 | 0.504 |
| (0.52, 0.55] | 100.0 | 0.527 | 0.500 |
| (0.55, 0.6] | 6.0 | 0.555 | 0.500 |

## CFB (FBS v FBS) vs opening line

Evaluated seasons 2023-2026 (2026 partial); 2324 games with a line and a final score.

**Margin MAE (points, lower is better)**

| Market line | Ratings only (m2) | Blend (m3) |
|---|---|---|
| 12.25 | 12.34 | 12.19 |

Blend weights (first -> last week): market 0.97 -> 0.69, ratings model 0.05 -> 0.34. sigma (blend residual SD) averaged 15.6 pts.

**Brier score** (coin flip = 0.2500): calibrated blend 0.2485; ratings-only 0.2520.

**ATS hit rate of top-N picks per week** (pushes excluded)

| Picks | Record |
|---|---|
| Top 5 | 152-112 (57.6%, 95% CI 51.5-63.4, p=0.02) |
| Top 6 | 181-132 (57.8%, 95% CI 52.3-63.2, p=0.01) |
| Top 10 | 278-216 (56.3%, 95% CI 51.9-60.6, p=0.01) |
| All games | 1217-1076 (53.1%, 95% CI 51.0-55.1, p=0.00) |

Model weight w (share of the model's disagreement with the market that is used): first 0.00, last 0.93, mean 0.78.

**Closing-line value of picks made at the open** (points the line moved toward our side)

| Picks | n | Mean move | % toward us | % away |
|---|---|---|---|---|
| Top 5 | 300 | +2.46 | 55% | 16% |
| Top 10 | 547 | +1.86 | 53% | 18% |
| All | 2423 | +0.75 | 46% | 28% |

Robustness: excluding games whose line moved >7 pts open->close (likely stale or erroneous openers), top 5 = 143-120 (54.4%, 95% CI 48.3-60.3, p=0.17).

**Hit rate by calibrated edge** (all games)

| Edge | n | Hit rate | 95% CI |
|---|---|---|---|
| (-0.001, 0.01] | 830 | 51.1% | 47.7-54.5 |
| (0.01, 0.02] | 423 | 54.4% | 49.6-59.1 |
| (0.02, 0.03] | 363 | 50.1% | 45.0-55.3 |
| (0.03, 0.05] | 361 | 54.3% | 49.1-59.4 |
| (0.05, 1.0] | 316 | 58.5% | 53.0-63.8 |

**Calibration of P(home covers)**

| Bin | n | Mean predicted | Observed |
|---|---|---|---|
| (-0.001, 0.4] | 14.0 | 0.373 | 0.286 |
| (0.4, 0.45] | 101.0 | 0.434 | 0.416 |
| (0.45, 0.48] | 295.0 | 0.469 | 0.458 |
| (0.48, 0.5] | 742.0 | 0.495 | 0.472 |
| (0.5, 0.52] | 511.0 | 0.510 | 0.548 |
| (0.52, 0.55] | 429.0 | 0.532 | 0.508 |
| (0.55, 0.6] | 178.0 | 0.567 | 0.567 |
| (0.6, 1.0] | 23.0 | 0.617 | 0.652 |

## CFB stale line: model sees the close, graded against the opener

Stand-in for the pickem sheet: a fixed line set early in the week, while the model sees a later market line. This is optimistic, because the close is the latest possible line and the live line at Friday's deadline has moved less. Only seasons with openers (2023+) are graded.

Evaluated seasons 2021-2026 (2026 partial); 2524 games with a line and a final score.

**Margin MAE (points, lower is better)**

| Market line | Ratings only (m2) | Blend (m3) |
|---|---|---|
| 11.93 | 12.29 | 11.94 |

Blend weights (first -> last week): market 0.85 -> 0.92, ratings model 0.18 -> 0.09. sigma (blend residual SD) averaged 15.1 pts.

**Brier score** (coin flip = 0.2500): calibrated blend 0.2448; ratings-only 0.2594.

**ATS hit rate of top-N picks per week** (pushes excluded)

| Picks | Record |
|---|---|
| Top 5 | 175-118 (59.7%, 95% CI 54.0-65.2, p=0.00) |
| Top 6 | 209-137 (60.4%, 95% CI 55.2-65.4, p=0.00) |
| Top 10 | 324-222 (59.3%, 95% CI 55.2-63.4, p=0.00) |
| All games | 1367-1123 (54.9%, 95% CI 52.9-56.8, p=0.00) |

Model weight w (share of the model's disagreement with the market that is used): first 0.00, last 0.56, mean 0.48.

**Hit rate by calibrated edge** (all games)

| Edge | n | Hit rate | 95% CI |
|---|---|---|---|
| (-0.001, 0.01] | 618 | 52.3% | 48.3-56.2 |
| (0.01, 0.02] | 386 | 50.0% | 45.0-55.0 |
| (0.02, 0.03] | 274 | 49.6% | 43.8-55.5 |
| (0.03, 0.05] | 375 | 53.1% | 48.0-58.1 |
| (0.05, 1.0] | 837 | 61.6% | 58.3-64.9 |

**Calibration of P(home covers)**

| Bin | n | Mean predicted | Observed |
|---|---|---|---|
| (-0.001, 0.4] | 155.0 | 0.348 | 0.342 |
| (0.4, 0.45] | 268.0 | 0.431 | 0.407 |
| (0.45, 0.48] | 310.0 | 0.467 | 0.474 |
| (0.48, 0.5] | 536.0 | 0.493 | 0.485 |
| (0.5, 0.52] | 468.0 | 0.508 | 0.524 |
| (0.52, 0.55] | 339.0 | 0.533 | 0.507 |
| (0.55, 0.6] | 285.0 | 0.570 | 0.632 |
| (0.6, 1.0] | 129.0 | 0.646 | 0.581 |

## Combined NFL + CFB ranking vs closing line (2016+)

| Picks | Record |
|---|---|
| Top 5 | 544-549 (49.8%, 95% CI 46.8-52.7, p=0.90); 87% CFB |
| Top 10 | 1025-1027 (50.0%, 95% CI 47.8-52.1, p=0.98); 88% CFB |

## Placebo check (market right by construction)

Same pipeline on synthetic outcomes: margin = -line + a residual shuffled across games within each season, and efficiency stats shuffled too. The line is unbiased and outcomes carry no game-specific signal, so anything far from 50% here would mean the pipeline manufactures edge.

| Run | Top 5 | Top 10 |
|---|---|---|
| NFL close (placebo) | 531-549 (49.2%, 95% CI 46.2-52.1, p=0.60) | 992-1050 (48.6%, 95% CI 46.4-50.7, p=0.21) |
| CFB open (placebo) | 130-135 (49.1%, 95% CI 43.1-55.0, p=0.81) | 246-249 (49.7%, 95% CI 45.3-54.1, p=0.93) |

![Calibration](calibration.png)
