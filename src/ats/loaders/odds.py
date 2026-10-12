"""Live DraftKings spreads via The Odds API v4.

Every pull is an append-only snapshot:
    data/raw/odds_api/<league>/<YYYYmmddTHHMMSSZ>.parquet   (flattened)
    data/raw/odds_api/<league>/<YYYYmmddTHHMMSSZ>.raw.json  (verbatim response)
Each row carries `fetched_at` (when we pulled it) and `book_last_update`
(DraftKings' own update time), so any line used later can be cited and any
use of a line observed after kickoff/prediction time can be detected.

Odds API outcome `point` is per-team, so the home outcome's point IS the
home spread in our convention (negative = home favored).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import pandas as pd
import requests

from ..cache import utcnow, write_snapshot
from ..config import RAW, get_key
from ..teams import to_canonical

log = logging.getLogger(__name__)
BASE = "https://api.the-odds-api.com/v4"
SPORTS = {"NFL": "americanfootball_nfl", "CFB": "americanfootball_ncaaf"}
BOOK = "draftkings"


def _source(league: str) -> str:
    return f"odds_api/{league.lower()}"


def flatten(events: list[dict], fetched_at: datetime) -> pd.DataFrame:
    rows = []
    for ev in events:
        row = {
            "event_id": ev["id"],
            "commence_time": ev["commence_time"],
            "home_team_src": ev["home_team"],
            "away_team_src": ev["away_team"],
            "book": None, "book_last_update": None,
            "home_spread": None, "home_price": None,
            "away_spread": None, "away_price": None,
        }
        for bk in ev.get("bookmakers", []):
            if bk.get("key") != BOOK:
                continue
            for mk in bk.get("markets", []):
                if mk.get("key") != "spreads":
                    continue
                row["book"] = BOOK
                row["book_last_update"] = mk.get("last_update") or bk.get("last_update")
                for o in mk.get("outcomes", []):
                    side = "home" if o["name"] == ev["home_team"] else "away" if o["name"] == ev["away_team"] else None
                    if side:
                        row[f"{side}_spread"] = o.get("point")
                        row[f"{side}_price"] = o.get("price")
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["commence_time"] = pd.to_datetime(df["commence_time"], utc=True)
    df["book_last_update"] = pd.to_datetime(df["book_last_update"], utc=True)
    for c in ("home_spread", "home_price", "away_spread", "away_price"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["fetched_at"] = pd.Timestamp(fetched_at)
    # Sanity: the two sides of a spread must be mirror images.
    both = df["home_spread"].notna() & df["away_spread"].notna()
    if (df.loc[both, "home_spread"] + df.loc[both, "away_spread"]).abs().gt(1e-9).any():
        raise ValueError("DraftKings home/away spreads are not symmetric; check parsing")
    return df


def snapshot(league: str) -> pd.DataFrame:
    """Pull current DraftKings spreads for one league and store a snapshot."""
    sport = SPORTS[league]
    r = requests.get(
        f"{BASE}/sports/{sport}/odds",
        params={"apiKey": get_key("ODDS_API_KEY"), "regions": "us", "markets": "spreads",
                "bookmakers": BOOK, "oddsFormat": "american", "dateFormat": "iso"},
        timeout=60,
    )
    r.raise_for_status()
    fetched_at = utcnow()
    quota = {k: r.headers.get(f"x-requests-{k}") for k in ("remaining", "used", "last")}
    log.info("Odds API %s: %s events, credits remaining=%s", league, len(r.json()), quota["remaining"])

    df = flatten(r.json(), fetched_at)
    if not df.empty:
        df.insert(0, "league", league)
        df["home"], unmatched_h = to_canonical(league, df["home_team_src"])
        df["away"], unmatched_a = to_canonical(league, df["away_team_src"])
        unmatched = sorted(set(unmatched_h) | set(unmatched_a))
        if unmatched:
            log.warning("%s: %d unmatched Odds API team names: %s", league, len(unmatched), unmatched)
    stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    write_snapshot(df, _source(league), stamp,
                   meta={"url": f"{BASE}/sports/{sport}/odds", "book": BOOK, "quota": quota})
    (RAW / _source(league) / f"{stamp}.raw.json").write_text(json.dumps(r.json()), encoding="utf-8")
    return df


def load_snapshots(league: str, as_of: datetime | None = None) -> pd.DataFrame:
    """All stored snapshots for a league, optionally only those fetched at or
    before `as_of` (use this to reconstruct what was knowable at a time)."""
    d = RAW / _source(league)
    frames = [pd.read_parquet(p) for p in sorted(d.glob("*.parquet"))] if d.exists() else []
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    # Re-map from the verbatim source names so mapping fixes apply to old
    # snapshots without ever rewriting them.
    df["home"], _ = to_canonical(league, df["home_team_src"])
    df["away"], _ = to_canonical(league, df["away_team_src"])
    if as_of is not None:
        df = df[df["fetched_at"] <= pd.Timestamp(as_of)]
    return df


def latest_lines(league: str, as_of: datetime | None = None) -> pd.DataFrame:
    """Most recent observed DraftKings line per event (as of `as_of`)."""
    df = load_snapshots(league, as_of)
    if df.empty:
        return df
    df = df.dropna(subset=["home_spread"])
    return df.sort_values("fetched_at").groupby("event_id", as_index=False).tail(1)
