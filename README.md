# ATS cover-probability model (NFL + CFB)

Research project; see `CLAUDE.md` for the full spec and `reports/backtest.md`
for the current walk-forward results.

## Setup (Windows, PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env   # then fill in CFBD_API_KEY and ODDS_API_KEY
```
NFL data needs no key. `.env` is gitignored.

## Commands
```powershell
# data (Phase 1)
.\.venv\Scripts\python -m ats fetch nfl --seasons 2012-2026   # schedules, closing lines, pbp, injuries
.\.venv\Scripts\python -m ats fetch cfb --seasons 2014-2026   # games, lines, adv stats, talent, returning prod
.\.venv\Scripts\python -m ats odds --league all               # DraftKings spread snapshot (1 credit per league)
.\.venv\Scripts\python -m ats check                           # data sanity report

# model + backtest (Phase 2)
.\.venv\Scripts\python -m ats backtest                        # -> reports/backtest.md, reports/calibration.png

# weekly operation (Phase 3)
.\.venv\Scripts\python -m ats weekly     # Tuesday: grade last week, refresh data + lines, rank, publish
.\.venv\Scripts\python -m ats refresh    # Wed-Sat: new lines, re-rank, lock kicked-off games
.\.venv\Scripts\python -m ats grade      # grade finished games only

.\.venv\Scripts\python -m pytest
```

## How the model works
1. **Ratings** (`src/ats/model/ratings.py`): opponent-adjusted offense/defense ratings
   for EPA/play, success rate and points, refit every week on games before that
   week's Tuesday. A ridge penalty pulls each team toward a preseason prior (last
   season's rating, regressed; CFB adds returning production and talent), worth
   ~3-4 games, so shrinkage fades as the season goes.
2. **Margin models** (`src/ats/backtest/walkforward.py`): market baseline (−line);
   ratings-only ridge (m2); blend m3 = margin ~ −line + m2, fit on m2's
   out-of-sample predictions. The blend's weight on m2 is the "does the model add
   anything" number.
3. **Cover probability**: NFL uses the empirical margin distribution of games
   with similar lines (key numbers 3/7); CFB uses a normal with σ from past
   residuals. Then per-league logistic calibration on past out-of-sample rows.
4. **Leakage guards**: every fit asserts its data is before the cutoff;
   `tests/test_leakage.py` scrambles all future outcomes and checks past predictions
   are bit-identical; the backtest report includes a placebo run.

## Pickem line
Drop the weekly pool sheet into `data/pickem/` (newest file is used). PDFs are
parsed best-effort (`src/ats/pickem.py`); a CSV with columns
`league,away,home,home_spread` is the exact fallback. Picks are graded against the
pickem line when a game is matched, otherwise the live DraftKings line.

## Outputs
- `data/rankings/<week_start>/<stamp>_<kind>.json|csv` — every published ranking,
  append-only, timestamped before kickoff. Committed to git as the record.
- `data/results/results.csv` — graded picks (headline = Tuesday list, final = last
  pre-kickoff ranking), vs pickem, live and closing lines. Append-only.
- `site/` — static page (GitHub Pages) reading `site/data/latest.json`.

## Data layout
- `data/raw/<source>/<key>.parquet` + `.json` manifest (fetch time, endpoint, rows).
  Completed seasons are immutable; the current season refreshes on a TTL.
- `data/raw/odds_api/<league>/<UTC stamp>.parquet` — append-only live-line snapshots.
- `data/interim/games_{nfl,cfb}.parquet` — canonical games tables (`src/ats/schema.py`).

## Conventions
- `close_home_spread < 0` means the home team is favored; home covers iff
  `margin + close_home_spread > 0`, with `margin = home − away`.
- Football week = Tue–Mon in Pacific time, identified by its Tuesday.
- `line_source`: `nflverse_close`, `nflverse_pregame` (unplayed game, not a close),
  `consensus`, `DraftKings`, `median_of_<n>` (CFB fallback).
