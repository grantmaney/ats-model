"""Model inputs built from the Phase 1 cache.

Two tables per league:
- games: one row per game (canonical schema + rest days), the unit we predict.
- obs:   one row per (game, offense team) with per-play efficiency for that
         offense against that defense. Ratings are fit on these.

Everything here is a pure transform of cached data; no fitting happens here.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from ..config import INTERIM, RAW

# NFL relocations: carry a franchise's prior across abbreviation changes.
NFL_FRANCHISE = {"STL": "LA", "SD": "LAC", "OAK": "LV"}


@lru_cache(maxsize=2)
def games(league: str) -> pd.DataFrame:
    g = pd.read_parquet(INTERIM / f"games_{league.lower()}.parquet")
    g = g.sort_values("kickoff_utc").reset_index(drop=True)
    g["football_week_start"] = pd.to_datetime(g["football_week_start"])
    if league == "CFB":
        g = _cfb_rest(g)
    else:
        g["home_rest"] = g["home_rest"].astype(float)
        g["away_rest"] = g["away_rest"].astype(float)
    g["rest_diff"] = (g["home_rest"].clip(upper=14) - g["away_rest"].clip(upper=14)).fillna(0)
    return g


def _cfb_rest(g: pd.DataFrame) -> pd.DataFrame:
    """Days since each team's previous game in the same season (cap 14)."""
    long = pd.concat([
        g[["game_id", "season", "kickoff_utc", "home"]].rename(columns={"home": "team"}).assign(side="home"),
        g[["game_id", "season", "kickoff_utc", "away"]].rename(columns={"away": "team"}).assign(side="away"),
    ]).sort_values("kickoff_utc")
    prev = long.groupby(["season", "team"])["kickoff_utc"].shift()
    long["rest"] = ((long["kickoff_utc"] - prev).dt.total_seconds() / 86400).fillna(14).clip(upper=14)
    rest = long.pivot_table(index="game_id", columns="side", values="rest", aggfunc="first")
    g = g.merge(rest.rename(columns={"home": "home_rest", "away": "away_rest"}),
                left_on="game_id", right_index=True, how="left")
    return g


def _home_flag(off_is_home: pd.Series, neutral: pd.Series) -> pd.Series:
    return np.where(neutral, 0.0, np.where(off_is_home, 1.0, -1.0))


@lru_cache(maxsize=8)
def obs(league: str, nfl_wp_window: tuple[float, float] | None = None) -> pd.DataFrame:
    """Per (game, offense) efficiency: epa (EPA or PPA per play), sr (success
    rate), pts (points scored). h = +1 offense at home, -1 away, 0 neutral.
    nfl_wp_window=(lo, hi) keeps only NFL plays with win probability in that
    range (drops garbage time)."""
    g = games(league)
    g = g[g["margin"].notna()]
    if league == "NFL":
        eff = _nfl_efficiency(tuple(sorted(g["season"].unique())), nfl_wp_window)
    else:
        eff = _cfb_efficiency(tuple(sorted(g["season"].unique())))
    cols = ["game_id", "season", "week", "kickoff_utc", "football_week_start", "home", "away",
            "neutral_site", "home_score", "away_score"]
    m = eff.merge(g[cols], on="game_id", how="inner")
    if league == "NFL":
        m["off"] = np.where(m["off_is_home"], m["home"], m["away"])
        m["def"] = np.where(m["off_is_home"], m["away"], m["home"])
    off_home = m["off"] == m["home"]
    # Drop rows whose teams don't match the game (source disagreements).
    ok = off_home | (m["off"] == m["away"])
    m = m[ok].copy()
    off_home = off_home[ok]
    m["h"] = _home_flag(off_home, m["neutral_site"].astype(bool))
    m["pts"] = np.where(off_home, m["home_score"], m["away_score"]).astype(float)
    return m[["game_id", "season", "week", "kickoff_utc", "football_week_start",
              "off", "def", "h", "epa", "sr", "pts", "plays"]].reset_index(drop=True)


def _nfl_efficiency(seasons: tuple[int, ...], wp_window: tuple[float, float] | None = None) -> pd.DataFrame:
    frames = []
    for s in seasons:
        p = pd.read_parquet(RAW / "nflverse" / f"pbp_{s}.parquet",
                            columns=["game_id", "posteam", "home_team", "epa", "success", "play_type", "wp"])
        p = p[p["play_type"].isin(["pass", "run"]) & p["epa"].notna()]
        if wp_window is not None:
            # in-game win probability (nflverse `wp`, not the Vegas-informed one)
            p = p[p["wp"].between(*wp_window)]
        # pbp uses current franchise codes (LA/LAC/LV) even for STL/SD/OAK
        # seasons; keep only home/away and take team codes from the schedule.
        p = p.assign(off_is_home=p["posteam"] == p["home_team"])
        frames.append(p.groupby(["game_id", "off_is_home"], as_index=False)
                      .agg(epa=("epa", "mean"), sr=("success", "mean"), plays=("epa", "size")))
    return pd.concat(frames, ignore_index=True)


def _cfb_efficiency(seasons: tuple[int, ...]) -> pd.DataFrame:
    frames = []
    for s in seasons:
        p = RAW / "cfbd" / f"adv_game_stats_{s}.parquet"
        if not p.exists():
            continue
        a = pd.read_parquet(p, columns=["gameId", "team", "opponent", "offense_ppa",
                                        "offense_successRate", "offense_plays"])
        frames.append(pd.DataFrame({
            "game_id": a["gameId"].astype(str), "off": a["team"], "def": a["opponent"],
            "epa": a["offense_ppa"], "sr": a["offense_successRate"], "plays": a["offense_plays"],
        }))
    out = pd.concat(frames, ignore_index=True)
    return out.dropna(subset=["epa", "sr"]).drop_duplicates(["game_id", "off"])


def cfb_priors_inputs(season: int) -> pd.DataFrame:
    """Preseason info for CFB teams in `season`: returning production share and
    talent composite (both published before the season), z-scored."""
    ret_p = RAW / "cfbd" / f"returning_{season}.parquet"
    tal_p = RAW / "cfbd" / f"talent_{season}.parquet"
    out = pd.DataFrame(columns=["team"])
    if ret_p.exists():
        r = pd.read_parquet(ret_p)[["team", "percentPPA"]].rename(columns={"percentPPA": "ret"})
        out = r
    t = pd.read_parquet(tal_p) if tal_p.exists() else pd.DataFrame()
    if not t.empty:  # CFBD talent starts in 2015
        t = t.rename(columns={"school": "team"})[["team", "talent"]]
        t["talent"] = pd.to_numeric(t["talent"], errors="coerce")
        out = t if out.empty else out.merge(t, on="team", how="outer")
    for c in ("ret", "talent"):
        if c not in out:
            out[c] = np.nan
        x = pd.to_numeric(out[c], errors="coerce")
        out[c + "_z"] = ((x - x.mean()) / x.std()).fillna(0.0)
    return out[["team", "ret_z", "talent_z"]]
