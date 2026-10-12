"""Candidate situational features (tested in backtest/experiments.py; a
feature is only used in production once it passes the dev/holdout test).

All features use only information available before the Friday lock.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import RAW


def nfl_qb_out(games: pd.DataFrame) -> pd.DataFrame:
    """qb_out_diff = home_qb_out - away_qb_out, where a team's *_qb_out = 1 if
    the QB who started its previous game is listed Out or Doubtful on this
    week's official injury report. Uses the previous game's starter (known)
    and the injury report (published before kickoff); never the actual
    starter of the game being predicted."""
    g = games.sort_values("kickoff_utc")
    long = pd.concat([
        g[["game_id", "season", "week", "kickoff_utc", "home", "home_qb_id"]]
        .rename(columns={"home": "team", "home_qb_id": "qb"}).assign(side="home"),
        g[["game_id", "season", "week", "kickoff_utc", "away", "away_qb_id"]]
        .rename(columns={"away": "team", "away_qb_id": "qb"}).assign(side="away"),
    ]).sort_values("kickoff_utc")
    long["prev_qb"] = long.groupby(["season", "team"])["qb"].shift()
    inj = []
    for s in sorted(g["season"].unique()):
        p = RAW / "nflverse" / f"injuries_{s}.parquet"
        if p.exists():
            i = pd.read_parquet(p, columns=["season", "week", "gsis_id", "position", "report_status"])
            inj.append(i[i["report_status"].isin(["Out", "Doubtful"])])
    inj = pd.concat(inj, ignore_index=True)[["season", "week", "gsis_id"]].drop_duplicates() if inj else \
        pd.DataFrame(columns=["season", "week", "gsis_id"])
    inj["out"] = 1.0
    long = long.merge(inj.rename(columns={"gsis_id": "prev_qb"}), on=["season", "week", "prev_qb"], how="left")
    long["out"] = long["out"].fillna(0.0)
    w = long.pivot_table(index="game_id", columns="side", values="out", aggfunc="max").fillna(0.0)
    return pd.DataFrame({"game_id": w.index, "qb_out_diff": (w.get("home", 0) - w.get("away", 0)).to_numpy()})


def cfb_holdover(games: pd.DataFrame) -> pd.DataFrame:
    """holdover_diff = home - away, where a team's flag is 1 in its first game
    of the season if it finished last season in the final AP top 10."""
    top10 = []
    for s in sorted(games["season"].unique()):
        p = RAW / "cfbd" / f"final_poll_{s - 1}.parquet"
        if p.exists():
            f = pd.read_parquet(p)
            f = f[pd.to_numeric(f["rank"], errors="coerce") <= 10]
            top10 += [(s, t) for t in f["team"]]
    top = set(top10)
    g = games.sort_values("kickoff_utc")
    long = pd.concat([g[["game_id", "season", "kickoff_utc", "home"]].rename(columns={"home": "team"}).assign(side="home"),
                      g[["game_id", "season", "kickoff_utc", "away"]].rename(columns={"away": "team"}).assign(side="away")])
    long = long.sort_values("kickoff_utc")
    long["first"] = ~long.duplicated(["season", "team"])
    long["flag"] = [1.0 if f and (s, t) in top else 0.0 for f, s, t in zip(long["first"], long["season"], long["team"])]
    w = long.pivot_table(index="game_id", columns="side", values="flag", aggfunc="max").fillna(0.0)
    return pd.DataFrame({"game_id": w.index, "holdover_diff": (w.get("home", 0) - w.get("away", 0)).to_numpy()})
