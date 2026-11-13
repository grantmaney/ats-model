"""Stale-line research: can anything beat the current market-centred model
at picking covers against an early-week line?

Setting (the pool-sheet situation): a line fixed early in the week (the
opener stands in for the pool sheet) and a later market line (the close
stands in for Friday's live line). Target: did the home team cover the
early line. One row per game, every feature known before kickoff.

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

`python -m ats research` writes reports/research_stale.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import binomtest, norm

from ..config import DATA, RAW, ROOT

log = logging.getLogger(__name__)
BT = DATA / "backtest"
REPORTS = ROOT / "reports"

SELECT = {"NFL": range(2016, 2022), "CFB": range(2023, 2024)}
HOLDOUT = {"NFL": range(2022, 2026), "CFB": range(2024, 2026)}
MIN_TRAIN = {"NFL": 3, "CFB": 2}


# ------------------------------------------------------------------ data
def _implied(dec_home: pd.Series, dec_away: pd.Series) -> pd.Series:
    """Vig-free probability of the home side from decimal odds, minus 0.5."""
    h, a = 1 / dec_home.astype(float), 1 / dec_away.astype(float)
    return h / (h + a) - 0.5


def _american_to_dec(x: pd.Series) -> pd.Series:
    x = pd.to_numeric(x, errors="coerce")
    return np.where(x > 0, 1 + x / 100, 1 + 100 / x.abs())


def nfl_extras() -> pd.DataFrame:
    """Market detail from the aussportsbetting.com sheet, per (date, pair)."""
    from ..loaders.nfl import MANUAL_LINES
    from ..teams import to_canonical
    x = pd.read_excel(MANUAL_LINES, sheet_name="Data", header=0)
    h, _ = to_canonical("NFL", x["Home Team"], fuzzy=True)
    a, _ = to_canonical("NFL", x["Away Team"], fuzzy=True)
    out = pd.DataFrame({
        "date": pd.to_datetime(x["Date"], errors="coerce").dt.normalize().values,
        "xh": h.values, "xa": a.values,
        "x_open": x["Home Line Open"].astype(float).values,
        "x_close": pd.to_numeric(x["Home Line Close"], errors="coerce").values,
        "juice_open": _implied(x["Home Line Odds Open"], x["Away Line Odds Open"]).values,
        "juice_close": _implied(x["Home Line Odds Close"], x["Away Line Odds Close"]).values,
        "ml_open": _implied(x["Home Odds Open"], x["Away Odds Open"]).values,
        "ml_close": _implied(x["Home Odds Close"], x["Away Odds Close"]).values,
        "total_open": pd.to_numeric(x["Total Score Open"], errors="coerce").values,
        "total_close": pd.to_numeric(x["Total Score Close"], errors="coerce").values,
    })
    return out.dropna(subset=["xh", "xa", "date"])


def nfl_frame() -> pd.DataFrame:
    d = pd.read_parquet(BT / "nfl_stale.parquet")
    d = d[d["season_type"] == "regular"].copy()
    ex = nfl_extras()
    date = pd.to_datetime(d["kickoff_utc"]).dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    look = {}
    for r in ex.itertuples(index=False):
        for dd in (-1, 0, 1):
            look[(r.date + pd.Timedelta(days=dd), frozenset((r.xh, r.xa)))] = r
    rows = []
    for dt, hm, aw in zip(date, d["home"], d["away"]):
        r = look.get((dt, frozenset((hm, aw))))
        if r is None:
            rows.append({})
            continue
        s = 1 if r.xh == hm else -1  # flip home-perspective fields if the sheet has the teams swapped
        rows.append({"juice_open": s * r.juice_open, "juice_close": s * r.juice_close,
                     "ml_open": s * r.ml_open, "ml_close": s * r.ml_close,
                     "total_open": r.total_open, "total_close": r.total_close})
    d = pd.concat([d.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
    d["dome"] = d["roof"].isin(["dome", "closed"]).astype(float)
    d["wind"] = pd.to_numeric(d["wind"], errors="coerce").fillna(0).where(d["dome"] == 0, 0)
    d["div_game"] = pd.to_numeric(d["div_game"], errors="coerce").fillna(0)
    d["conference_game"] = 0.0
    return d


def cfb_frame() -> pd.DataFrame:
    """CFB stale rows; openers widened with Bovada/ESPN Bet where the
    production loader only kept DraftKings (same-provider open and close)."""
    # The close run has the model's centre for every game (the stale run only
    # kept it where a DraftKings opener existed); centre doesn't depend on the
    # grading line.
    d = pd.read_parquet(BT / "cfb_close.parquet")
    d = d[d["eval"] & d["centre"].notna()].copy()
    d["game_id"] = d["game_id"].astype(str)
    prov = []
    for s in sorted(d["season"].unique()):
        p = RAW / "cfbd" / f"lines_{s}.parquet"
        if p.exists():
            x = pd.read_parquet(p)
            x = x[x["spreadOpen"].notna() & x["spread"].notna()]
            prov.append(x.assign(game_id=x["game_id"].astype(str)))
    x = pd.concat(prov)
    rank = {"DraftKings": 0, "Bovada": 1, "ESPN Bet": 2}
    x = x[x["provider"].isin(rank)].assign(r=lambda t: t["provider"].map(rank)).sort_values("r")
    x = x.drop_duplicates("game_id")
    x = x.rename(columns={"spreadOpen": "p_open", "spread": "p_close", "overUnderOpen": "total_open",
                          "overUnder": "total_close"})[["game_id", "provider", "p_open", "p_close",
                                                        "total_open", "total_close", "homeMoneyline",
                                                        "awayMoneyline"]]
    d = d.merge(x, on="game_id", how="left")
    # same-provider pair: grade on that provider's opener, market = its close
    d = d[d["p_open"].notna()].copy()   # only games with an opener can be graded on one
    use = d["p_open"].notna()
    d.loc[use, "grade_line"] = d.loc[use, "p_open"].astype(float)
    d.loc[use, "line"] = d.loc[use, "p_close"].astype(float)
    hm, am = _american_to_dec(d["homeMoneyline"]), _american_to_dec(d["awayMoneyline"])
    d["ml_close"] = _implied(pd.Series(hm), pd.Series(am)).values
    for c in ("juice_open", "juice_close", "ml_open"):
        d[c] = np.nan
    d["dome"] = d["wind"] = d["div_game"] = 0.0
    d["conference_game"] = d["conference_game"].astype(float)
    return d


def prepare(d: pd.DataFrame, league: str) -> pd.DataFrame:
    """Home-perspective features; target = home covers the early line."""
    d = d.copy()
    for c in ("line", "grade_line", "margin_f", "pred3", "sigma", "centre"):
        d[c] = pd.to_numeric(d[c], errors="coerce").astype(float)
    d = d.dropna(subset=["line", "grade_line", "margin_f", "centre", "sigma"])
    cov = d["margin_f"] + d["grade_line"]
    d = d[cov != 0].copy()
    d["y"] = (cov[cov != 0] > 0).astype(float)
    if league == "NFL":
        base = d["p_cal"].astype(float)
    else:  # recompute: provider pairs changed the lines; centre is market + w*disagreement
        shift = d["centre"] + d["close_home_spread"].astype(float)   # model's lean vs our close
        base = pd.Series(norm.cdf((-d["line"] + shift + d["grade_line"]) / d["sigma"]), index=d.index)
    d["p_base"] = base.clip(0.01, 0.99)
    d["base_logit"] = np.log(d["p_base"] / (1 - d["p_base"]))
    d["move"] = d["grade_line"] - d["line"]                     # + = market moved toward home
    d["amove"] = d["move"].abs()
    d["spread_abs"] = d["line"].abs()
    d["home_fav"] = (d["line"] < 0).astype(float)
    d["model_dis"] = d["pred3"] + d["line"]                      # ratings+market blend vs market
    d["juice_move"] = d["juice_close"] - d["juice_open"]
    d["ml_move"] = d["ml_close"] - d["ml_open"]
    d["total_move"] = pd.to_numeric(d["total_close"], errors="coerce") - pd.to_numeric(d["total_open"], errors="coerce")
    d["rest_diff"] = pd.to_numeric(d.get("rest_diff"), errors="coerce")
    d["neutral"] = d["neutral_site"].astype(float)
    d["wk"] = d["week"].astype(float)
    if league == "NFL":
        keys = [3, 7]
        lo, hi = np.minimum(d["grade_line"].abs(), d["line"].abs()), np.maximum(d["grade_line"].abs(), d["line"].abs())
        d["cross_key"] = sum(((lo < k) & (hi > k)) | ((lo == k) ^ (hi == k)) for k in keys).astype(float) \
            * np.sign(d["move"])
    else:
        d["cross_key"] = 0.0
    return d


FEATS_SMALL = ["base_logit", "move", "cross_key"]
FEATS_MARKET = FEATS_SMALL + ["juice_close", "juice_move", "ml_move", "total_move"]
FEATS_FULL = FEATS_MARKET + ["model_dis", "spread_abs", "home_fav", "rest_diff", "neutral", "div_game",
                             "conference_game", "wind", "dome", "wk"]


# ------------------------------------------------------------------ models
def _fit_predict(kind: str, feats: list[str], train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    feats = [f for f in feats if train[f].notna().mean() > 0.5]
    Xtr, Xte = train[feats].astype(float), test[feats].astype(float)
    med = Xtr.median()
    Xtr, Xte = Xtr.fillna(med).fillna(0), Xte.fillna(med).fillna(0)
    if kind == "logit":
        m = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000))
    else:
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.03, max_iter=200, min_samples_leaf=80,
                                           l2_regularization=1.0, random_state=0)
    m.fit(Xtr, train["y"])
    return m.predict_proba(Xte)[:, 1]


MODELS = {
    "baseline (current)": None,
    "logit small": ("logit", FEATS_SMALL),
    "logit market": ("logit", FEATS_MARKET),
    "logit full": ("logit", FEATS_FULL),
    "boost full": ("boost", FEATS_FULL),
}


def walk_forward(d: pd.DataFrame, league: str) -> pd.DataFrame:
    seasons = sorted(d["season"].unique())
    out = []
    for s in seasons:
        train = d[d["season"] < s]
        if train["season"].nunique() < MIN_TRAIN[league]:
            continue
        test = d[d["season"] == s].copy()
        for name, spec in MODELS.items():
            test[name] = test["p_base"] if spec is None else _fit_predict(spec[0], spec[1], train, test)
        out.append(test)
    return pd.concat(out, ignore_index=True)


# ------------------------------------------------------------------ scoring
def _top(d: pd.DataFrame, col: str, n: int) -> pd.Series:
    t = d.assign(conf=(d[col] - 0.5).abs(), hit=np.where(d[col] >= 0.5, d["y"], 1 - d["y"]))
    t = t.sort_values("conf", ascending=False).groupby("football_week_start").head(n)
    return t["hit"]


def _fmt(h: pd.Series) -> str:
    k, n = int(h.sum()), len(h)
    if n == 0:
        return "-"
    ci = binomtest(k, n).proportion_ci()
    return f"{100 * k / n:.1f}% ({k}-{n - k}; CI {100 * ci.low:.0f}-{100 * ci.high:.0f})"


def score(d: pd.DataFrame, col: str) -> dict:
    p = d[col].clip(0.001, 0.999)
    return {"top6": _top(d, col, 6), "top10": _top(d, col, 10), "all": _top(d, col, 10_000),
            "brier": float(((p - d["y"]) ** 2).mean()),
            "logloss": float(-(d["y"] * np.log(p) + (1 - d["y"]) * np.log(1 - p)).mean())}


def table(d: pd.DataFrame, title: str) -> list[str]:
    L = [f"**{title}** ({len(d)} games, {d['football_week_start'].nunique()} weeks)", "",
         "| Model | Top 6 | Top 10 | All games | Brier | Log loss |", "|---|---|---|---|---|---|"]
    for name in MODELS:
        s = score(d, name)
        L.append(f"| {name} | {_fmt(s['top6'])} | {_fmt(s['top10'])} | {_fmt(s['all'])} | "
                 f"{s['brier']:.4f} | {s['logloss']:.4f} |")
    return L + [""]


def run() -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)
    res = {}
    res["NFL"] = walk_forward(prepare(nfl_frame(), "NFL"), "NFL")
    res["CFB"] = walk_forward(prepare(cfb_frame(), "CFB"), "CFB")
    for lg, d in res.items():
        d.to_parquet(BT / f"research_{lg.lower()}.parquet", index=False)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = ["# Stale-line research", "", f"Generated {now}. Regenerate with `python -m ats research`.", "",
         "Protocol" + (__doc__ or "").split("Protocol", 1)[1].split("`python")[0].rstrip(), ""]
    for lg, d in res.items():
        L += [f"## {lg}", ""]
        L += table(d[d["season"].isin(SELECT[lg])], f"Selection seasons {min(SELECT[lg])}-{max(SELECT[lg])}")
        L += table(d[d["season"].isin(HOLDOUT[lg])], f"Holdout seasons {min(HOLDOUT[lg])}-{max(HOLDOUT[lg])}")
    L += timing_test(res)
    text = "\n".join(L)
    (REPORTS / "research_stale.md").write_text(text, encoding="utf-8")
    return text


# ------------------------------------------------------- timing test (part 2)
# Live picks lock Friday 10pm PT, when only part of the opener->close move has
# happened. Measured on our 2026 DraftKings snapshots against the pool sheet:
# NFL ~2/3 of the move is in by the lock, CFB ~1/4.
LOCK_SHARE = {"NFL": 0.67, "CFB": 0.26}


def _half(x):
    return np.round(np.asarray(x, float) * 2) / 2


def timing_frame(d: pd.DataFrame, league: str) -> pd.DataFrame:
    """Lock-time line proxy: opener + share of the open->close move, to the
    half point. Grade line stays the opener (= the pool sheet)."""
    d = d.dropna(subset=["pred2"]).copy()
    d["lock_line"] = _half(d["grade_line"] + LOCK_SHARE[league] * (d["line"] - d["grade_line"]))
    d["ratings"] = d["pred2"].astype(float)          # ratings-only predicted home margin (no market input)
    return d


def _fit_w(past: pd.DataFrame, line_col: str) -> tuple[float, float, float]:
    """Least-squares weight on the ratings' disagreement with `line_col`:
    margin + line = w * (d - mean_d) + e, d = ratings + line. Returns
    (w clipped to [0, 1], mean_d, residual SD)."""
    dd = past["ratings"] + past[line_col]
    r = past["margin_f"] + past[line_col]
    mean_d = dd.mean()
    x = dd - mean_d
    w = float(np.clip((x * r).sum() / (x * x).sum(), 0, 1))
    sd = float((r - w * x).std())
    return w, mean_d, sd


def timing_test(res: dict) -> list[str]:
    L = ["## Part 2: trusting the ratings at Friday-lock timing", "",
         "Picks lock while the line is still near the sheet (proxy: opener + the measured share of the "
         "open->close move by the lock: NFL 0.67, CFB 0.26). Both versions centre on the lock-time line and "
         "add w x (ratings' disagreement with it). They differ only in how w is learned (walk-forward, "
         "past seasons only):", "",
         "- **A (current method):** w from residuals against the closing line.",
         "- **B (timing-matched):** w from residuals against the lock-time line proxy.", "",
         "Same adoption rule as Part 1 (choose on selection seasons, confirm on holdout).", ""]
    both = []
    for lg, d0 in res.items():
        d = timing_frame(d0, lg)
        out = []
        for s in sorted(d["season"].unique()):
            past = d[d["season"] < s]
            if past["season"].nunique() < MIN_TRAIN[lg]:
                continue
            t = d[d["season"] == s].copy()
            for name, col in (("A", "line"), ("B", "lock_line")):
                w, md, sd = _fit_w(past, col)
                centre = -t["lock_line"] + w * (t["ratings"] + t["lock_line"] - md)
                t[name] = norm.cdf((centre + t["grade_line"]) / sd)
                t[f"w_{name}"] = w
            out.append(t)
        t = pd.concat(out, ignore_index=True)
        both.append(t.assign(lg=lg))
        L += [f"### {lg}", "", "| Seasons | Version | w (mean) | Top 6 | Top 10 | All games | Brier |",
              "|---|---|---|---|---|---|---|"]
        for label, yrs in (("selection", SELECT[lg]), ("holdout", HOLDOUT[lg])):
            z = t[t["season"].isin(yrs)]
            for name in ("A", "B"):
                s = score(z, name)
                L.append(f"| {label} {min(yrs)}-{max(yrs)} | {name} | {z[f'w_{name}'].mean():.2f} | "
                         f"{_fmt(s['top6'])} | {_fmt(s['top10'])} | {_fmt(s['all'])} | {s['brier']:.4f} |")
        L.append("")
    t = pd.concat(both, ignore_index=True)
    L += ["### Combined NFL + CFB ranking (the product: one top 6 per week)", "",
          "| Seasons | Version | Top 6 | Top 10 |", "|---|---|---|---|"]
    for label, yrs in (("2023", [2023]), ("holdout 2024-2025", [2024, 2025]), ("2026 to date", [2026])):
        z = t[t["season"].isin(yrs)]
        for name in ("A", "B"):
            s = score(z, name)
            L.append(f"| {label} | {name} | {_fmt(s['top6'])} | {_fmt(s['top10'])} |")
    L.append("")
    t.to_parquet(BT / "research_timing.parquet", index=False)
    return L
