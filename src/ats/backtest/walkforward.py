"""Walk-forward backtest by football week.

For each week W (cutoff = Tuesday 00:00 Pacific starting W):
  1. Ratings for W's games come from ratings.pregame_ratings (fit on games
     before the cutoff only).
  2. Model 2 (ratings ridge, no market input) is fit on all earlier games.
  3. Model 3 (blend) regresses margin on -line and model 2's OUT-OF-SAMPLE
     predictions from earlier weeks.
  4. sigma, the NFL empirical margin distribution and the calibrator all use
     only earlier weeks' out-of-sample rows.
Every fit records the latest kickoff it saw and asserts it is before the
cutoff (LeakageError otherwise).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..config import WEEK_TZ
from ..model import ratings as R
from ..model.probability import LogitCalibrator, empirical_cover_prob, normal_cover_prob, outcome

log = logging.getLogger(__name__)

FEATURES = ["epa_diff", "sr_diff", "pts_diff", "home_field", "rest_diff"]
MIN_TRAIN_M2 = 200
MIN_TRAIN_M3 = 200
MIN_CALIB = 300
LEAGUE_DEFAULTS = {
    # first rated season is burn-in for ratings only; model training starts after it
    "NFL": {"eval_from": 2015, "use_empirical": True},
    "CFB": {"eval_from": 2016, "use_empirical": False},
}


def cutoff(week_start) -> pd.Timestamp:
    return pd.Timestamp(week_start).tz_localize(WEEK_TZ).tz_convert("UTC")


def _check(train: pd.DataFrame, as_of: pd.Timestamp, what: str) -> None:
    if len(train) and train["kickoff_utc"].max() >= as_of:
        raise R.LeakageError(f"{what}: training row at {train['kickoff_utc'].max()} >= cutoff {as_of}")


def build_frame(league: str, games: pd.DataFrame, obs: pd.DataFrame) -> pd.DataFrame:
    feats = R.pregame_ratings(league, obs, games)
    df = games.merge(feats, on="game_id", how="inner")
    df["home_field"] = (~df["neutral_site"].astype(bool)).astype(float)
    if league == "CFB":
        df = df[(df["home_classification"] == "fbs") & (df["away_classification"] == "fbs")]
    first = df["season"].min()
    df = df[df["season"] > first]  # first season: ratings burn-in only
    return df.dropna(subset=FEATURES).sort_values("kickoff_utc").reset_index(drop=True)


def run(league: str, games: pd.DataFrame, obs: pd.DataFrame, line_col: str = "close_home_spread",
        eval_from: int | None = None, frame: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return one row per game (from the first predictable week) with all
    model outputs. Rows with season >= eval_from are the reported sample."""
    cfg = LEAGUE_DEFAULTS[league]
    eval_from = eval_from or cfg["eval_from"]
    df = frame if frame is not None else build_frame(league, games, obs)
    df = df.copy()
    df["line"] = df[line_col].astype(float)
    df["margin_f"] = df["margin"].astype(float)
    df["y"] = outcome(df["margin"], df["line"])
    for c in ("pred2", "pred3", "p2", "p_raw", "p_norm", "p_cal", "sigma", "calibrated", "m3_w_model", "m3_w_mkt"):
        df[c] = np.nan

    for wk in sorted(df["football_week_start"].unique()):
        as_of = cutoff(wk)
        now = df["football_week_start"] == wk
        past = (df["kickoff_utc"] < as_of) & df["margin_f"].notna()
        tr2 = df[past]
        _check(tr2, as_of, "model2")
        if len(tr2) < MIN_TRAIN_M2:
            continue
        m2 = make_pipeline(StandardScaler(), Ridge(alpha=1.0)).fit(tr2[FEATURES], tr2["margin_f"])
        df.loc[now, "pred2"] = m2.predict(df.loc[now, FEATURES])
        # sigma for model 2 alone, from its past OOS residuals (else market residuals)
        r2 = (tr2["margin_f"] - tr2["pred2"]).dropna()
        s2 = r2.std() if len(r2) >= MIN_TRAIN_M3 else (tr2["margin_f"] + tr2["line"]).std()
        df.loc[now, "p2"] = normal_cover_prob(df.loc[now, "pred2"], df.loc[now, "line"], s2)

        tr3 = df[past & df["pred2"].notna() & df["line"].notna()]
        _check(tr3, as_of, "model3")
        if len(tr3) < MIN_TRAIN_M3:
            continue
        m3 = LinearRegression().fit(np.column_stack([-tr3["line"], tr3["pred2"]]), tr3["margin_f"])
        has_line = now & df["line"].notna()
        if not has_line.any():
            continue
        df.loc[has_line, "pred3"] = m3.predict(np.column_stack([-df.loc[has_line, "line"],
                                                                df.loc[has_line, "pred2"]]))
        df.loc[has_line, "m3_w_mkt"], df.loc[has_line, "m3_w_model"] = m3.coef_

        r3 = (tr3["margin_f"] - tr3["pred3"]).dropna()
        sigma = r3.std() if len(r3) >= MIN_TRAIN_M3 else (tr3["margin_f"] + tr3["line"]).std()
        df.loc[has_line, "sigma"] = sigma
        probs = cover_probs(league, df[past], df.loc[has_line, "pred3"].to_numpy(),
                            df.loc[has_line, "line"].to_numpy(), sigma, as_of)
        for k, v in probs.items():
            df.loc[has_line, k] = v

    df["eval"] = df["season"] >= eval_from
    df["line_col"] = line_col
    return df


def cover_probs(league: str, past: pd.DataFrame, pred3: np.ndarray, line: np.ndarray,
                sigma: float, as_of: pd.Timestamp) -> dict[str, np.ndarray]:
    """P(home covers) for games with blended margin `pred3` against `line`.
    `past` = earlier rows of the same walk-forward frame (margin_f, line,
    p_raw, y); used for the NFL empirical distribution and calibration only."""
    _check(past, as_of, "cover_probs")
    p_norm = normal_cover_prob(pred3, line, sigma)
    if LEAGUE_DEFAULTS[league]["use_empirical"]:
        hist = past[past["line"].notna() & past["margin_f"].notna()]
        p_raw = empirical_cover_prob(pred3, line, hist["margin_f"].to_numpy(), hist["line"].to_numpy())
    else:
        p_raw = p_norm
    cal_rows = past[past["p_raw"].notna() & past["y"].notna()]
    if len(cal_rows) >= MIN_CALIB:
        p_cal = LogitCalibrator().fit(cal_rows["p_raw"], cal_rows["y"]).predict(p_raw)
        calibrated = np.ones(len(line))
    else:
        p_cal, calibrated = p_raw, np.zeros(len(line))
    return {"p_norm": p_norm, "p_raw": p_raw, "p_cal": p_cal, "calibrated": calibrated}


def scramble_after(games: pd.DataFrame, obs: pd.DataFrame, as_of: pd.Timestamp,
                   seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replace every outcome at/after `as_of` with noise (leakage test)."""
    rng = np.random.default_rng(seed)
    g, o = games.copy(), obs.copy()
    fut = g["kickoff_utc"] >= as_of
    g.loc[fut, "home_score"] = rng.integers(0, 60, fut.sum()).astype(float)
    g.loc[fut, "away_score"] = rng.integers(0, 60, fut.sum()).astype(float)
    g.loc[fut, "margin"] = g.loc[fut, "home_score"] - g.loc[fut, "away_score"]
    fo = o["kickoff_utc"] >= as_of
    for c in ("epa", "sr", "pts"):
        o.loc[fo, c] = rng.permutation(o.loc[fo, c].to_numpy()) + rng.normal(0, 0.1, fo.sum())
    return g, o


def placebo(games: pd.DataFrame, obs: pd.DataFrame, line_col: str = "close_home_spread",
            seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Synthetic world where the market is right by construction:
        margin* = -line + (residual vs line, permuted across games in a season)
    Outcomes keep their real distribution around the line but carry no
    game-specific information, so no honest model can beat 50% ATS here.
    (Shuffling raw scores instead would make the line itself wrong, and a
    model would legitimately learn to fade it.)"""
    rng = np.random.default_rng(seed)
    g = games.copy()
    has = g["margin"].notna() & g[line_col].notna()
    line = g[line_col].astype(float)
    resid = g["margin"].astype(float) + line
    total = g["home_score"].astype(float) + g["away_score"].astype(float)
    for s, idx in g[has].groupby("season").groups.items():
        resid.loc[idx] = rng.permutation(resid.loc[idx].to_numpy())
    new_margin = -line + resid
    g.loc[has, "margin"] = new_margin[has]
    g.loc[has, "home_score"] = ((total + new_margin) / 2)[has]
    g.loc[has, "away_score"] = ((total - new_margin) / 2)[has]
    o = obs.copy()
    sc = g.set_index("game_id")
    home_of = sc["home"]
    is_home = o["off"].to_numpy() == home_of.reindex(o["game_id"]).to_numpy()
    o["pts"] = np.where(is_home, sc["home_score"].reindex(o["game_id"]).to_numpy(),
                        sc["away_score"].reindex(o["game_id"]).to_numpy()).astype(float)
    # efficiency stats are shuffled the same way so they don't carry the real result
    for s, idx in o.groupby("season").groups.items():
        perm = rng.permutation(idx)
        o.loc[idx, ["epa", "sr"]] = o.loc[perm, ["epa", "sr"]].to_numpy()
    return g, o
