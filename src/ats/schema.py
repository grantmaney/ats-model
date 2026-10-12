"""Canonical games table shared by both leagues.

Spread convention (everywhere downstream of the loaders):
    home_spread < 0  ->  home team favored
    home covers  <=>  margin + home_spread > 0       (margin = home - away)
"""
from __future__ import annotations

import pandas as pd

GAME_COLUMNS = [
    "league",               # "NFL" | "CFB"
    "season",
    "week",                 # league's official week number
    "season_type",          # "regular" | "postseason"
    "football_week_start",  # Tuesday (date) of the Tue-Mon week, Pacific time
    "game_id",              # source-native id, as string
    "kickoff_utc",
    "home",                 # canonical team name (NFL: nflverse abbr; CFB: CFBD school)
    "away",
    "neutral_site",
    "home_score",
    "away_score",
    "margin",               # home - away; NaN until final
    "close_home_spread",
    "open_home_spread",
    "line_source",          # provider the close/open came from
    "line_fetched_at",      # when WE observed the line; NaT for historical closes
]


def validate_games(df: pd.DataFrame) -> pd.DataFrame:
    """Check invariants; returns canonical columns first, league extras after."""
    missing = [c for c in GAME_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"games table missing columns: {missing}")
    if df["game_id"].duplicated().any():
        dups = df.loc[df["game_id"].duplicated(), "game_id"].head().tolist()
        raise ValueError(f"duplicate game_id values, e.g. {dups}")
    if str(df["kickoff_utc"].dt.tz) != "UTC":
        raise ValueError("kickoff_utc must be tz-aware UTC")
    final = df["home_score"].notna() & df["away_score"].notna()
    bad = final & (df["margin"] != df["home_score"] - df["away_score"])
    if bad.any():
        raise ValueError("margin != home_score - away_score for some games")
    extras = [c for c in df.columns if c not in GAME_COLUMNS]
    return df[GAME_COLUMNS + extras].reset_index(drop=True)
