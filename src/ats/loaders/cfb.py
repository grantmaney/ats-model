"""College football loaders (CollegeFootballData.com API v2).

CFBD free tier is ~1,000 calls/month, so every response is cached and
completed seasons are fetched once (~9 calls per season).

Lines: /lines returns one row per game with a list of providers. CFBD
`spread` is from the HOME perspective (negative = home favored), which already
matches our convention, so it is NOT negated. `spread` is the provider's
last/closing number and `spreadOpen` its opener; neither carries an
observation timestamp. Closing-line rule (documented, deterministic):
  1. "consensus" provider if present
  2. else DraftKings
  3. else median of all providers' spreads (line_source = "median_of_<n>")
open_home_spread comes from the same provider as the close when available.
"""
from __future__ import annotations

import logging

import pandas as pd
import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..cache import cached
from ..config import get_key
from ..schema import validate_games
from ..weeks import current_season, football_week_start_series

log = logging.getLogger(__name__)
SOURCE = "cfbd"
BASE = "https://api.collegefootballdata.com"
SEASON_TYPES = ("regular", "postseason")
PROVIDER_PRIORITY = ("consensus", "DraftKings")


def _retryable(e: BaseException) -> bool:
    if isinstance(e, requests.HTTPError) and e.response is not None:
        return e.response.status_code == 429 or e.response.status_code >= 500
    return isinstance(e, (requests.ConnectionError, requests.Timeout))


@retry(retry=retry_if_exception(_retryable), stop=stop_after_attempt(4),
       wait=wait_exponential(multiplier=2, max=30), reraise=True)
def _get(path: str, **params) -> list[dict]:
    r = requests.get(
        f"{BASE}{path}",
        params={k: v for k, v in params.items() if v is not None},
        headers={"Authorization": f"Bearer {get_key('CFBD_API_KEY')}", "Accept": "application/json"},
        timeout=60,
    )
    r.raise_for_status()
    remaining = r.headers.get("X-CallLimit-Remaining")
    if remaining is not None:
        log.info("CFBD %s %s -> calls remaining this month: %s", path, params, remaining)
    return r.json()


def _immutable(season: int) -> bool:
    return season < current_season()


def _fetch_by_season_type(path: str, season: int) -> pd.DataFrame:
    frames = []
    for st in SEASON_TYPES:
        rows = _get(path, year=season, seasonType=st)
        if rows:
            df = pd.json_normalize(rows, sep="_")
            if "seasonType" not in df:
                df["seasonType"] = st
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _season_cached(name: str, path: str, season: int, force: bool) -> pd.DataFrame:
    return cached(
        SOURCE, f"{name}_{season}",
        lambda: _fetch_by_season_type(path, season),
        immutable=_immutable(season), ttl_hours=6, force=force,
        meta={"endpoint": path, "season": season, "seasonTypes": SEASON_TYPES},
    )


def load_games_raw(season: int, force: bool = False) -> pd.DataFrame:
    return _season_cached("games", "/games", season, force)


def load_lines_raw(season: int, force: bool = False) -> pd.DataFrame:
    """One row per (game, provider)."""
    def fetch() -> pd.DataFrame:
        rows = []
        for st in SEASON_TYPES:
            for g in _get("/lines", year=season, seasonType=st):
                for ln in g.get("lines") or []:
                    rows.append({
                        "game_id": str(g["id"]), "season": g.get("season"), "week": g.get("week"),
                        "seasonType": g.get("seasonType", st),
                        "homeTeam": g.get("homeTeam"), "awayTeam": g.get("awayTeam"),
                        "provider": ln.get("provider"),
                        "spread": ln.get("spread"), "spreadOpen": ln.get("spreadOpen"),
                        "overUnder": ln.get("overUnder"), "overUnderOpen": ln.get("overUnderOpen"),
                        "homeMoneyline": ln.get("homeMoneyline"), "awayMoneyline": ln.get("awayMoneyline"),
                    })
        df = pd.DataFrame(rows)
        for c in ("spread", "spreadOpen", "overUnder", "overUnderOpen", "homeMoneyline", "awayMoneyline"):
            if c in df:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
    return cached(SOURCE, f"lines_{season}", fetch, immutable=_immutable(season), ttl_hours=6,
                  force=force, meta={"endpoint": "/lines", "season": season})


def load_advanced_game_stats(season: int, force: bool = False) -> pd.DataFrame:
    """Per team-game advanced stats (PPA/EPA, success rate, explosiveness,
    havoc...) for offense and defense, flattened. Includes per-game PPA, so a
    separate /ppa/games pull is not needed."""
    return _season_cached("adv_game_stats", "/stats/game/advanced", season, force)


def load_talent(season: int, force: bool = False) -> pd.DataFrame:
    return cached(SOURCE, f"talent_{season}", lambda: pd.DataFrame(_get("/talent", year=season)),
                  immutable=_immutable(season), ttl_hours=24 * 7, force=force,
                  meta={"endpoint": "/talent", "season": season})


def load_returning_production(season: int, force: bool = False) -> pd.DataFrame:
    return cached(SOURCE, f"returning_{season}",
                  lambda: pd.DataFrame(_get("/player/returning", year=season)),
                  immutable=_immutable(season), ttl_hours=24 * 7, force=force,
                  meta={"endpoint": "/player/returning", "season": season})


def load_teams(force: bool = False) -> pd.DataFrame:
    return cached(SOURCE, "teams", lambda: pd.json_normalize(_get("/teams"), sep="_"),
                  immutable=False, ttl_hours=24 * 30, force=force, meta={"endpoint": "/teams"})


def choose_lines(lines: pd.DataFrame) -> pd.DataFrame:
    """Apply the closing-line rule; one row per game_id."""
    cols = ["game_id", "close_home_spread", "open_home_spread", "line_source"]
    if lines.empty:
        return pd.DataFrame(columns=cols)
    ln = lines.dropna(subset=["spread"])
    out = []
    for gid, grp in ln.groupby("game_id", sort=False):
        prov = grp["provider"].fillna("").str.lower()
        for p in PROVIDER_PRIORITY:
            hit = grp[prov == p.lower()]
            if not hit.empty:
                out.append((gid, hit["spread"].iloc[0], hit["spreadOpen"].iloc[0], p))
                break
        else:
            out.append((gid, grp["spread"].median(), grp["spreadOpen"].median(),
                        f"median_of_{len(grp)}"))
    return pd.DataFrame(out, columns=cols)


def games(season: int, force: bool = False) -> pd.DataFrame:
    """Canonical games table for one CFB season (all divisions; FBS/FCS
    classification kept as extra columns for Phase 2 filtering)."""
    g = load_games_raw(season, force=force)
    lines = choose_lines(load_lines_raw(season, force=force))

    def col(name):
        return g[name] if name in g else pd.Series(pd.NA, index=g.index)

    out = pd.DataFrame({
        "league": "CFB",
        "season": g["season"].astype(int),
        "week": g["week"].astype(int),
        "season_type": g["seasonType"],
        "game_id": g["id"].astype(str),
        "kickoff_utc": pd.to_datetime(g["startDate"], utc=True, format="ISO8601"),
        "home": g["homeTeam"],
        "away": g["awayTeam"],
        "neutral_site": g["neutralSite"].fillna(False).astype(bool),
        "home_score": pd.to_numeric(g["homePoints"], errors="coerce").astype("Float64"),
        "away_score": pd.to_numeric(g["awayPoints"], errors="coerce").astype("Float64"),
        "home_classification": col("homeClassification"),
        "away_classification": col("awayClassification"),
        "conference_game": col("conferenceGame"),
        "start_time_tbd": col("startTimeTBD"),
    })
    out = out.merge(lines, on="game_id", how="left")
    out["close_home_spread"] = pd.to_numeric(out["close_home_spread"]).astype("Float64")
    out["open_home_spread"] = pd.to_numeric(out["open_home_spread"]).astype("Float64")
    out["line_fetched_at"] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    out["margin"] = out["home_score"] - out["away_score"]
    out["football_week_start"] = football_week_start_series(out["kickoff_utc"])
    return validate_games(out)
