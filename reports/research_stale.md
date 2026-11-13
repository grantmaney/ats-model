# Stale-line research

Generated 2026-11-13 23:54 UTC. Regenerate with `python -m ats research`.

Protocol, fixed before any results were looked at:
- Walk-forward by season: to predict season S, models are fit only on
  seasons < S (at least 3 for NFL, 2 for CFB).
- Candidate models: baseline (today's p_cal), logistic regressions on
  small/full feature sets, gradient boosting.
- Model choice uses only the selection seasons (NFL 2016-2021, CFB 2023).
  The holdout (NFL 2022-2025, CFB 2024-2025) is scored once, for the
  chosen model and the baseline, and that is the reported result.
- A model is adopted only if, on the holdout, top-6 hit rate is higher and
  Brier score no worse than the baseline.

## NFL

**Selection seasons 2016-2021** (1265 games, 86 weeks)

| Model | Top 6 | Top 10 | All games | Brier | Log loss |
|---|---|---|---|---|---|
| baseline (current) | 57.9% (299-217; CI 54-62) | 55.5% (477-383; CI 52-59) | 54.2% (685-580; CI 51-57) | 0.2457 | 0.6844 |
| logit small | 57.6% (297-219; CI 53-62) | 56.2% (483-377; CI 53-60) | 54.4% (688-577; CI 52-57) | 0.2465 | 0.6860 |
| logit market | 57.8% (298-218; CI 53-62) | 55.8% (480-380; CI 52-59) | 53.8% (680-585; CI 51-57) | 0.2471 | 0.6872 |
| logit full | 54.5% (281-235; CI 50-59) | 53.1% (457-403; CI 50-57) | 53.5% (677-588; CI 51-56) | 0.2498 | 0.6928 |
| boost full | 51.6% (266-250; CI 47-56) | 51.9% (446-414; CI 48-55) | 51.4% (650-615; CI 49-54) | 0.2547 | 0.7031 |

**Holdout seasons 2022-2025** (1056 games, 71 weeks)

| Model | Top 6 | Top 10 | All games | Brier | Log loss |
|---|---|---|---|---|---|
| baseline (current) | 62.4% (266-160; CI 58-67) | 59.0% (419-291; CI 55-63) | 56.6% (598-458; CI 54-60) | 0.2421 | 0.6772 |
| logit small | 63.4% (270-156; CI 59-68) | 57.9% (411-299; CI 54-62) | 54.8% (579-477; CI 52-58) | 0.2427 | 0.6783 |
| logit market | 62.2% (265-161; CI 57-67) | 57.6% (409-301; CI 54-61) | 56.1% (592-464; CI 53-59) | 0.2425 | 0.6780 |
| logit full | 60.6% (258-168; CI 56-65) | 58.7% (417-293; CI 55-62) | 57.5% (607-449; CI 54-60) | 0.2426 | 0.6783 |
| boost full | 58.5% (249-177; CI 54-63) | 55.1% (391-319; CI 51-59) | 54.3% (573-483; CI 51-57) | 0.2464 | 0.6862 |

## CFB

**Selection seasons 2023-2023** (777 games, 20 weeks)

| Model | Top 6 | Top 10 | All games | Brier | Log loss |
|---|---|---|---|---|---|
| baseline (current) | 70.0% (77-33; CI 61-78) | 64.2% (113-63; CI 57-71) | 52.5% (408-369; CI 49-56) | 0.2462 | 0.6852 |
| logit small | 63.6% (70-40; CI 54-73) | 59.7% (105-71; CI 52-67) | 51.0% (396-381; CI 47-55) | 0.2461 | 0.6849 |
| logit market | 63.6% (70-40; CI 54-73) | 60.2% (106-70; CI 53-68) | 50.5% (392-385; CI 47-54) | 0.2461 | 0.6850 |
| logit full | 62.7% (69-41; CI 53-72) | 58.5% (103-73; CI 51-66) | 51.6% (401-376; CI 48-55) | 0.2479 | 0.6887 |
| boost full | 60.9% (67-43; CI 51-70) | 61.4% (108-68; CI 54-69) | 53.5% (416-361; CI 50-57) | 0.2490 | 0.6913 |

**Holdout seasons 2024-2025** (1590 games, 44 weeks)

| Model | Top 6 | Top 10 | All games | Brier | Log loss |
|---|---|---|---|---|---|
| baseline (current) | 59.5% (138-94; CI 53-66) | 58.3% (218-156; CI 53-63) | 54.5% (867-723; CI 52-57) | 0.2447 | 0.6819 |
| logit small | 59.1% (137-95; CI 52-65) | 59.1% (221-153; CI 54-64) | 54.3% (863-727; CI 52-57) | 0.2449 | 0.6821 |
| logit market | 59.9% (139-93; CI 53-66) | 58.6% (219-155; CI 53-64) | 54.7% (870-720; CI 52-57) | 0.2449 | 0.6821 |
| logit full | 59.9% (139-93; CI 53-66) | 59.1% (221-153; CI 54-64) | 53.4% (849-741; CI 51-56) | 0.2460 | 0.6843 |
| boost full | 54.7% (127-105; CI 48-61) | 56.7% (212-162; CI 51-62) | 53.3% (847-743; CI 51-56) | 0.2505 | 0.6945 |

## Part 2: trusting the ratings at Friday-lock timing

Picks lock while the line is still near the sheet (proxy: opener + the measured share of the open->close move by the lock: NFL 0.67, CFB 0.26). Both versions centre on the lock-time line and add w x (ratings' disagreement with it). They differ only in how w is learned (walk-forward, past seasons only):

- **A (current method):** w from residuals against the closing line.
- **B (timing-matched):** w from residuals against the lock-time line proxy.

Same adoption rule as Part 1 (choose on selection seasons, confirm on holdout).

### NFL

| Seasons | Version | w (mean) | Top 6 | Top 10 | All games | Brier |
|---|---|---|---|---|---|---|
| selection 2016-2021 | A | 0.00 | 57.6% (121-89; CI 51-64) | 54.3% (190-160; CI 49-60) | 53.4% (275-240; CI 49-58) | 0.2472 |
| selection 2016-2021 | B | 0.00 | 56.2% (118-92; CI 49-63) | 53.1% (186-164; CI 48-58) | 53.4% (275-240; CI 49-58) | 0.2472 |
| holdout 2022-2025 | A | 0.00 | 61.0% (260-166; CI 56-66) | 57.5% (408-302; CI 54-61) | 56.6% (598-458; CI 54-60) | 0.2435 |
| holdout 2022-2025 | B | 0.00 | 61.5% (262-164; CI 57-66) | 57.7% (410-300; CI 54-61) | 56.6% (598-458; CI 54-60) | 0.2435 |

### CFB

| Seasons | Version | w (mean) | Top 6 | Top 10 | All games | Brier |
|---|---|---|---|---|---|---|
| selection 2023-2023 | A | nan | - | - | - | nan |
| selection 2023-2023 | B | nan | - | - | - | nan |
| holdout 2024-2025 | A | 0.07 | 64.1% (75-42; CI 55-73) | 60.6% (114-74; CI 53-68) | 54.2% (435-367; CI 51-58) | 0.2481 |
| holdout 2024-2025 | B | 0.23 | 59.0% (69-48; CI 50-68) | 58.0% (109-79; CI 51-65) | 52.6% (422-380; CI 49-56) | 0.2482 |

### Combined NFL + CFB ranking (the product: one top 6 per week)

| Seasons | Version | Top 6 | Top 10 |
|---|---|---|---|
| 2023 | A | 60.2% (65-43; CI 50-69) | 61.1% (110-70; CI 54-68) |
| 2023 | B | 59.3% (64-44; CI 49-69) | 61.1% (110-70; CI 54-68) |
| holdout 2024-2025 | A | 61.1% (140-89; CI 54-67) | 58.1% (219-158; CI 53-63) |
| holdout 2024-2025 | B | 60.7% (139-90; CI 54-67) | 57.0% (215-162; CI 52-62) |
| 2026 to date | A | 59.1% (39-27; CI 46-71) | 59.0% (62-43; CI 49-69) |
| 2026 to date | B | 56.1% (37-29; CI 43-68) | 58.1% (61-44; CI 48-68) |
