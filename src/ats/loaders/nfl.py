"""NFL loaders (nflverse via nflreadpy).

nflverse `spread_line` is POSITIVE when the home team is favored (e.g.
2025_01_DAL_PHI: spread_line=+8.5, PHI -8.5). We negate it into
close_home_spread. nflverse lines are closing lines without an observation
timestamp, so line_fetched_at is NaT for them.
`gametime` is US/Eastern local wall-clock time.
"""
from __future__ import annotations

import logging

import nflreadpy as nfl
import pandas as pd

from ..cache import cached, read_manifest
from ..schema import validate_games
from ..weeks import current_season, football_week_start_series

log = logging.getLogger(__name__)
SOURCE = "nflverse"
FIRST_PBP_SEASON = 1999


def _is_immutable(season: int) -> bool:
    return season < current_season()


def load_schedules(season: int, force: bool = False) -> pd.DataFrame:
    return cached(
        SOURCE, f"schedules_{season}",
        lambda: nfl.load_schedules([season]).to_pandas(),
        immutable=_is_immutable(season), ttl_hours=6, force=force,
        meta={"fn": "nflreadpy.load_schedules", "season": season},
    )


def load_pbp(season: int, force: bool = False) -> pd.DataFrame:
    return cached(
        SOURCE, f"pbp_{season}",
        lambda: nfl.load_pbp([season]).to_pandas(),
        immutable=_is_immutable(season), ttl_hours=24, force=force,
        meta={"fn": "nflreadpy.load_pbp", "season": season},
    )


def load_injuries(season: int, force: bool = False) -> pd.DataFrame | None:
    """Official injury reports. nflverse may lag on the current season;
    returns None (logged) when a season isn't published."""
    try:
        return cached(
            SOURCE, f"injuries_{season}",
            lambda: nfl.load_injuries([season]).to_pandas(),
            immutable=_is_immutable(season), ttl_hours=6, force=force,
            meta={"fn": "nflreadpy.load_injuries", "season": season},
        )
    except Exception as e:  # nflreadpy raises on missing release files
        log.warning("injuries %s unavailable: %s", season, e)
        return None


def load_teams(force: bool = False) -> pd.DataFrame:
    return cached(
        SOURCE, "teams", lambda: nfl.load_teams().to_pandas(),
        immutable=False, ttl_hours=24 * 30, force=force,
        meta={"fn": "nflreadpy.load_teams"},
    )


def games(season: int, force: bool = False) -> pd.DataFrame:
    """Canonical games table for one NFL season."""
    s = load_schedules(season, force=force)
    kickoff = (
        pd.to_datetime(s["gameday"] + " " + s["gametime"].fillna("13:00"), format="%Y-%m-%d %H:%M")
        .dt.tz_localize("America/New_York")
        .dt.tz_convert("UTC")
    )
    out = pd.DataFrame({
        "league": "NFL",
        "season": s["season"].astype(int),
        "week": s["week"].astype(int),
        "season_type": s["game_type"].map(lambda g: "regular" if g == "REG" else "postseason"),
        "game_id": s["game_id"].astype(str),
        "kickoff_utc": kickoff,
        "home": s["home_team"],
        "away": s["away_team"],
        "neutral_site": s["location"].eq("Neutral"),
        "home_score": s["home_score"].astype("Float64"),
        "away_score": s["away_score"].astype("Float64"),
        "close_home_spread": -s["spread_line"].astype("Float64"),
        "open_home_spread": pd.Series(pd.NA, index=s.index, dtype="Float64"),
        "line_source": "nflverse_close",
        "line_fetched_at": pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns, UTC]"),
    })
    # Extras for features: rest days are known pregame; roof/temp/wind are
    # game-day conditions (fine as pregame proxies, never post-game stats).
    for c in ("home_rest", "away_rest", "div_game", "roof", "temp", "wind", "home_qb_id", "away_qb_id"):
        if c in s:
            out[c] = s[c]
    out["margin"] = out["home_score"] - out["away_score"]
    # For games not yet played, spread_line is the line at fetch time, not a
    # close: label it and stamp it with our fetch time so it's never mistaken
    # for a closing line.
    pending = out["margin"].isna() & out["close_home_spread"].notna()
    if pending.any():
        fetched = (read_manifest(SOURCE, f"schedules_{season}") or {}).get("fetched_at")
        out.loc[pending, "line_source"] = "nflverse_pregame"
        if fetched:
            out.loc[pending, "line_fetched_at"] = pd.Timestamp(fetched)
    out.loc[out["close_home_spread"].isna(), "line_source"] = pd.NA
    out["football_week_start"] = football_week_start_series(out["kickoff_utc"])
    return validate_games(out)
