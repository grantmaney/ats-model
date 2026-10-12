# Walk-forward backtest

Generated 2026-10-12 05:15 UTC. Regenerate with `python -m ats backtest`.

Every prediction uses only games that kicked off before that week's Tuesday 00:00 PT cutoff. Ratings, model fits, sigma, the NFL empirical margin distribution and calibration are all refit each week on past data only. Hyperparameters (prior strength, decay, ridge alpha) were fixed before running and not tuned on these results.

Break-even at -110 is 52.4%. A hit rate whose CI includes 50% is not distinguishable from a coin flip.

## NFL vs closing line

Evaluated seasons 2015-2026 (2026 partial); 3106 games with a line and a final score.

**Margin MAE (points, lower is better)**

| Market line | Ratings only (m2) | Blend (m3) |
|---|---|---|
| 9.81 | 10.21 | 9.82 |

Blend weights (first -> last week): market 0.91 -> 1.06, ratings model 0.15 -> -0.03. sigma (blend residual SD) averaged 13.0 pts.

**Brier score** (coin flip = 0.2500): calibrated blend 0.2506; ratings-only 0.2595.

**ATS hit rate of top-N picks per week** (pushes excluded)

| Picks | Record |
|---|---|
| Top 5 | 533-560 (48.8%, 95% CI 45.8-51.7, p=0.43) |
| Top 10 | 1044-1014 (50.7%, 95% CI 48.6-52.9, p=0.52) |
| All games | 1545-1480 (51.1%, 95% CI 49.3-52.9, p=0.24) |

**Hit rate by calibrated edge** (all games)

| Edge | n | Hit rate | 95% CI |
|---|---|---|---|
| (-0.001, 0.01] | 697 | 53.8% | 50.1-57.5 |
| (0.01, 0.02] | 1122 | 50.3% | 47.3-53.2 |
| (0.02, 0.03] | 733 | 51.0% | 47.4-54.6 |
| (0.03, 0.05] | 381 | 48.3% | 43.3-53.3 |
| (0.05, 1.0] | 92 | 52.2% | 42.1-62.1 |

**Calibration of P(home covers)**

| Bin | n | Mean predicted | Observed |
|---|---|---|---|
| (-0.001, 0.4] | 8.0 | 0.364 | 0.625 |
| (0.4, 0.45] | 68.0 | 0.435 | 0.471 |
| (0.45, 0.48] | 1067.0 | 0.471 | 0.497 |
| (0.48, 0.5] | 1601.0 | 0.488 | 0.483 |
| (0.5, 0.52] | 218.0 | 0.507 | 0.514 |
| (0.52, 0.55] | 47.0 | 0.531 | 0.447 |
| (0.55, 0.6] | 16.0 | 0.567 | 0.562 |

## CFB (FBS v FBS) vs closing line

Evaluated seasons 2016-2026 (2026 partial); 7889 games with a line and a final score.

**Margin MAE (points, lower is better)**

| Market line | Ratings only (m2) | Blend (m3) |
|---|---|---|
| 12.30 | 12.74 | 12.32 |

Blend weights (first -> last week): market 0.86 -> 0.93, ratings model 0.26 -> 0.08. sigma (blend residual SD) averaged 16.0 pts.

**Brier score** (coin flip = 0.2500): calibrated blend 0.2501; ratings-only 0.2591.

**ATS hit rate of top-N picks per week** (pushes excluded)

| Picks | Record |
|---|---|
| Top 5 | 464-482 (49.0%, 95% CI 45.9-52.2, p=0.58) |
| Top 10 | 888-911 (49.4%, 95% CI 47.1-51.7, p=0.60) |
| All games | 3855-3880 (49.8%, 95% CI 48.7-51.0, p=0.78) |

**Hit rate by calibrated edge** (all games)

| Edge | n | Hit rate | 95% CI |
|---|---|---|---|
| (-0.001, 0.01] | 4724 | 49.5% | 48.1-51.0 |
| (0.01, 0.02] | 2395 | 50.4% | 48.4-52.4 |
| (0.02, 0.03] | 488 | 48.6% | 44.2-53.0 |
| (0.03, 0.05] | 112 | 55.4% | 46.1-64.2 |
| (0.05, 1.0] | 16 | 50.0% | 28.0-72.0 |

**Calibration of P(home covers)**

| Bin | n | Mean predicted | Observed |
|---|---|---|---|
| (0.4, 0.45] | 16.0 | 0.432 | 0.500 |
| (0.45, 0.48] | 593.0 | 0.474 | 0.503 |
| (0.48, 0.5] | 6935.0 | 0.491 | 0.500 |
| (0.5, 0.52] | 184.0 | 0.503 | 0.446 |
| (0.52, 0.55] | 7.0 | 0.526 | 0.571 |

## CFB (FBS v FBS) vs opening line

Evaluated seasons 2023-2026 (2026 partial); 2324 games with a line and a final score.

**Margin MAE (points, lower is better)**

| Market line | Ratings only (m2) | Blend (m3) |
|---|---|---|
| 12.25 | 12.36 | 12.20 |

Blend weights (first -> last week): market 0.95 -> 0.71, ratings model 0.06 -> 0.32. sigma (blend residual SD) averaged 15.6 pts.

**Brier score** (coin flip = 0.2500): calibrated blend 0.2494; ratings-only 0.2526.

**ATS hit rate of top-N picks per week** (pushes excluded)

| Picks | Record |
|---|---|
| Top 5 | 155-109 (58.7%, 95% CI 52.7-64.5, p=0.01) |
| Top 10 | 288-206 (58.3%, 95% CI 53.9-62.6, p=0.00) |
| All games | 1220-1073 (53.2%, 95% CI 51.2-55.2, p=0.00) |

**Closing-line value of picks made at the open** (points the line moved toward our side)

| Picks | n | Mean move | % toward us | % away |
|---|---|---|---|---|
| Top 5 | 300 | +2.70 | 59% | 13% |
| Top 10 | 547 | +2.01 | 55% | 16% |
| All | 2423 | +0.82 | 47% | 27% |

Robustness: excluding games whose line moved >7 pts open->close (likely stale or erroneous openers), top 5 = 147-116 (55.9%, 95% CI 49.9-61.8, p=0.06).

**Hit rate by calibrated edge** (all games)

| Edge | n | Hit rate | 95% CI |
|---|---|---|---|
| (-0.001, 0.01] | 559 | 54.2% | 50.1-58.3 |
| (0.01, 0.02] | 458 | 52.0% | 47.4-56.5 |
| (0.02, 0.03] | 353 | 50.4% | 45.2-55.6 |
| (0.03, 0.05] | 474 | 53.0% | 48.5-57.4 |
| (0.05, 1.0] | 449 | 55.7% | 51.1-60.2 |

**Calibration of P(home covers)**

| Bin | n | Mean predicted | Observed |
|---|---|---|---|
| (-0.001, 0.4] | 40.0 | 0.359 | 0.350 |
| (0.4, 0.45] | 175.0 | 0.432 | 0.469 |
| (0.45, 0.48] | 448.0 | 0.467 | 0.467 |
| (0.48, 0.5] | 588.0 | 0.490 | 0.481 |
| (0.5, 0.52] | 429.0 | 0.509 | 0.550 |
| (0.52, 0.55] | 379.0 | 0.533 | 0.501 |
| (0.55, 0.6] | 175.0 | 0.568 | 0.566 |
| (0.6, 1.0] | 59.0 | 0.646 | 0.542 |

## Combined NFL + CFB ranking vs closing line (2016+)

| Picks | Record |
|---|---|
| Top 5 | 536-559 (48.9%, 95% CI 46.0-51.9, p=0.51); 15% CFB |
| Top 10 | 1025-1024 (50.0%, 95% CI 47.9-52.2, p=1.00); 23% CFB |

## Placebo check (market right by construction)

Same pipeline on synthetic outcomes: margin = -line + a residual shuffled across games within each season, and efficiency stats shuffled too. The line is unbiased and outcomes carry no game-specific signal, so anything far from 50% here would mean the pipeline manufactures edge.

| Run | Top 5 | Top 10 |
|---|---|---|
| NFL close (placebo) | 532-556 (48.9%, 95% CI 45.9-51.9, p=0.49) | 1032-1022 (50.2%, 95% CI 48.1-52.4, p=0.84) |
| CFB open (placebo) | 130-133 (49.4%, 95% CI 43.4-55.4, p=0.90) | 242-253 (48.9%, 95% CI 44.5-53.3, p=0.65) |

![Calibration](calibration.png)
