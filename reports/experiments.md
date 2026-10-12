# Experiments: development vs holdout

Feature / setting experiments with a development-holdout split.

Decision rule (fixed before running anything):
  ADOPT a change only if, versus the baseline,
    1. development ratings-model MAE (m2) improves by >= 0.02 points, and
    2. development Brier (calibrated) does not get worse, and
    3. holdout m2 MAE does not get worse.
  Hit rates are reported but never used to decide: they are too noisy.

Development = NFL 2015-2021, CFB 2016-2021. Holdout = 2022 onward.

| League | Change | Dev m2 MAE | Dev m3 MAE | Dev Brier | Dev top-5 | Hold m2 MAE | Hold m3 MAE | Hold Brier | Hold top-5 | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| NFL | baseline | 10.355 | 9.992 | 0.2506 | 50.1% | 9.993 | 9.566 | 0.2506 | 45.5% | - |
| NFL | garbage-time filter wp 0.05-0.95 | 10.355 | 10.000 | 0.2508 | 50.2% | 9.991 | 9.568 | 0.2507 | 46.7% | reject |
| NFL | garbage-time filter wp 0.10-0.90 | 10.360 | 9.997 | 0.2509 | 49.2% | 9.998 | 9.567 | 0.2506 | 45.3% | reject |
| NFL | prior strength 2 games | 10.435 | 9.982 | 0.2507 | 50.4% | 10.046 | 9.564 | 0.2508 | 46.5% | reject |
| NFL | prior strength 8 games | 10.311 | 9.995 | 0.2505 | 50.5% | 10.000 | 9.573 | 0.2504 | 48.2% | reject |
| NFL | recency half-life 5 wks | 10.360 | 9.989 | 0.2507 | 49.5% | 9.990 | 9.566 | 0.2506 | 46.9% | reject |
| NFL | recency half-life 20 wks | 10.361 | 9.992 | 0.2506 | 50.6% | 10.005 | 9.566 | 0.2506 | 45.6% | reject |
| NFL | starting QB Out/Doubtful | 10.347 | 9.993 | 0.2507 | 50.4% | 9.988 | 9.566 | 0.2506 | 46.5% | reject |
| CFB | baseline | 13.004 | 12.581 | 0.2501 | 50.6% | 12.416 | 11.987 | 0.2501 | 46.9% | - |
| CFB | prior strength 1.5 games | 13.000 | 12.579 | 0.2500 | 51.8% | 12.470 | 11.987 | 0.2501 | 52.9% | reject |
| CFB | prior strength 6 games | 13.249 | 12.586 | 0.2501 | 49.4% | 12.559 | 11.982 | 0.2501 | 47.0% | reject |
| CFB | recency half-life 5 wks | 13.204 | 12.585 | 0.2501 | 50.7% | 12.514 | 11.985 | 0.2501 | 46.8% | reject |
| CFB | recency half-life 20 wks | 12.941 | 12.578 | 0.2501 | 51.3% | 12.401 | 11.987 | 0.2501 | 48.9% | ADOPT |
| CFB | holdover: last year's top 10, first game | 13.003 | 12.582 | 0.2502 | 50.2% | 12.411 | 11.987 | 0.2501 | 46.7% | reject |

Market MAE for reference: NFL dev 9.971, holdout 9.554; CFB dev 12.556, holdout 11.970
