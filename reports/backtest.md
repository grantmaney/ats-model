# Walk-forward backtest

Generated 2026-10-12 06:10 UTC. Regenerate with `python -m ats backtest`.

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
| 12.30 | 12.70 | 12.32 |

Blend weights (first -> last week): market 0.84 -> 0.92, ratings model 0.26 -> 0.09. sigma (blend residual SD) averaged 16.0 pts.

**Brier score** (coin flip = 0.2500): calibrated blend 0.2501; ratings-only 0.2584.

**ATS hit rate of top-N picks per week** (pushes excluded)

| Picks | Record |
|---|---|
| Top 5 | 476-471 (50.3%, 95% CI 47.1-53.4, p=0.90) |
| Top 10 | 891-906 (49.6%, 95% CI 47.3-51.9, p=0.74) |
| All games | 3851-3884 (49.8%, 95% CI 48.7-50.9, p=0.72) |

**Hit rate by calibrated edge** (all games)

| Edge | n | Hit rate | 95% CI |
|---|---|---|---|
| (-0.001, 0.01] | 4811 | 49.5% | 48.1-50.9 |
| (0.01, 0.02] | 2191 | 50.0% | 47.9-52.1 |
| (0.02, 0.03] | 548 | 51.5% | 47.3-55.6 |
| (0.03, 0.05] | 167 | 50.3% | 42.8-57.8 |
| (0.05, 1.0] | 18 | 50.0% | 29.0-71.0 |

**Calibration of P(home covers)**

| Bin | n | Mean predicted | Observed |
|---|---|---|---|
| (0.4, 0.45] | 18.0 | 0.434 | 0.500 |
| (0.45, 0.48] | 707.0 | 0.473 | 0.487 |
| (0.48, 0.5] | 6657.0 | 0.492 | 0.502 |
| (0.5, 0.52] | 345.0 | 0.503 | 0.470 |
| (0.52, 0.55] | 8.0 | 0.529 | 0.375 |

## CFB (FBS v FBS) vs opening line

Evaluated seasons 2023-2026 (2026 partial); 2324 games with a line and a final score.

**Margin MAE (points, lower is better)**

| Market line | Ratings only (m2) | Blend (m3) |
|---|---|---|
| 12.25 | 12.34 | 12.19 |

Blend weights (first -> last week): market 0.97 -> 0.69, ratings model 0.05 -> 0.34. sigma (blend residual SD) averaged 15.6 pts.

**Brier score** (coin flip = 0.2500): calibrated blend 0.2492; ratings-only 0.2520.

**ATS hit rate of top-N picks per week** (pushes excluded)

| Picks | Record |
|---|---|
| Top 5 | 156-108 (59.1%, 95% CI 53.1-64.9, p=0.00) |
| Top 10 | 285-209 (57.7%, 95% CI 53.3-62.0, p=0.00) |
| All games | 1218-1075 (53.1%, 95% CI 51.1-55.2, p=0.00) |

**Closing-line value of picks made at the open** (points the line moved toward our side)

| Picks | n | Mean move | % toward us | % away |
|---|---|---|---|---|
| Top 5 | 300 | +2.76 | 59% | 14% |
| Top 10 | 547 | +2.06 | 55% | 16% |
| All | 2423 | +0.81 | 47% | 27% |

Robustness: excluding games whose line moved >7 pts open->close (likely stale or erroneous openers), top 5 = 149-114 (56.7%, 95% CI 50.6-62.5, p=0.04).

**Hit rate by calibrated edge** (all games)

| Edge | n | Hit rate | 95% CI |
|---|---|---|---|
| (-0.001, 0.01] | 533 | 52.9% | 48.7-57.1 |
| (0.01, 0.02] | 425 | 52.2% | 47.5-56.9 |
| (0.02, 0.03] | 358 | 50.0% | 44.8-55.2 |
| (0.03, 0.05] | 442 | 53.8% | 49.2-58.4 |
| (0.05, 1.0] | 535 | 55.5% | 51.3-59.7 |

**Calibration of P(home covers)**

| Bin | n | Mean predicted | Observed |
|---|---|---|---|
| (-0.001, 0.4] | 51.0 | 0.357 | 0.353 |
| (0.4, 0.45] | 202.0 | 0.431 | 0.470 |
| (0.45, 0.48] | 439.0 | 0.467 | 0.456 |
| (0.48, 0.5] | 529.0 | 0.490 | 0.493 |
| (0.5, 0.52] | 429.0 | 0.509 | 0.550 |
| (0.52, 0.55] | 361.0 | 0.532 | 0.493 |
| (0.55, 0.6] | 207.0 | 0.568 | 0.546 |
| (0.6, 1.0] | 75.0 | 0.646 | 0.587 |

## Combined NFL + CFB ranking vs closing line (2016+)

| Picks | Record |
|---|---|
| Top 5 | 534-561 (48.8%, 95% CI 45.8-51.7, p=0.43); 17% CFB |
| Top 10 | 1025-1024 (50.0%, 95% CI 47.9-52.2, p=1.00); 25% CFB |

## Placebo check (market right by construction)

Same pipeline on synthetic outcomes: margin = -line + a residual shuffled across games within each season, and efficiency stats shuffled too. The line is unbiased and outcomes carry no game-specific signal, so anything far from 50% here would mean the pipeline manufactures edge.

| Run | Top 5 | Top 10 |
|---|---|---|
| NFL close (placebo) | 532-556 (48.9%, 95% CI 45.9-51.9, p=0.49) | 1032-1022 (50.2%, 95% CI 48.1-52.4, p=0.84) |
| CFB open (placebo) | 132-131 (50.2%, 95% CI 44.2-56.2, p=1.00) | 255-237 (51.8%, 95% CI 47.4-56.2, p=0.44) |

![Calibration](calibration.png)
