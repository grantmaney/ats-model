"""Spread sign conventions per source. A flip here silently inverts every
pick, so each conversion is pinned to a real, known game."""
from datetime import datetime, timezone

import pandas as pd

from ats.loaders.cfb import choose_lines
from ats.loaders.odds import flatten


def test_nfl_spread_line_is_negated(monkeypatch):
    # 2025_01_DAL_PHI: PHI (home) closed -8.5; nflverse spread_line = +8.5.
    from ats.loaders import nfl
    sched = pd.DataFrame({
        "game_id": ["2025_01_DAL_PHI"], "season": [2025], "week": [1], "game_type": ["REG"],
        "gameday": ["2025-09-04"], "gametime": ["20:20"], "home_team": ["PHI"], "away_team": ["DAL"],
        "location": ["Home"], "home_score": [24], "away_score": [20], "spread_line": [8.5],
    })
    monkeypatch.setattr(nfl, "load_schedules", lambda season, force=False: sched)
    g = nfl.games(2025)
    row = g.iloc[0]
    assert row["close_home_spread"] == -8.5
    assert row["margin"] == 4
    assert str(row["kickoff_utc"]) == "2025-09-05 00:20:00+00:00"


def test_cfb_choose_lines_priority_and_sign_passthrough():
    lines = pd.DataFrame({
        "game_id": ["1", "1", "2", "2", "3"],
        "provider": ["Bovada", "consensus", "Bovada", "DraftKings", "teamrankings"],
        "spread": [-7.0, -6.5, 3.0, 3.5, -10.0],
        "spreadOpen": [-6.0, -6.0, 2.5, 3.0, None],
    })
    out = choose_lines(lines).set_index("game_id")
    assert out.loc["1", "close_home_spread"] == -6.5 and out.loc["1", "line_source"] == "consensus"
    assert out.loc["2", "close_home_spread"] == 3.5 and out.loc["2", "line_source"] == "DraftKings"
    assert out.loc["3", "line_source"] == "median_of_1"


def test_odds_api_home_point_is_home_spread():
    ev = [{
        "id": "e1", "commence_time": "2025-09-07T17:00:00Z",
        "home_team": "Atlanta Falcons", "away_team": "Tampa Bay Buccaneers",
        "bookmakers": [{"key": "draftkings", "last_update": "2025-09-07T16:00:00Z", "markets": [{
            "key": "spreads", "last_update": "2025-09-07T16:00:00Z", "outcomes": [
                {"name": "Tampa Bay Buccaneers", "price": -110, "point": -1.5},
                {"name": "Atlanta Falcons", "price": -110, "point": 1.5}]}]}],
    }]
    df = flatten(ev, datetime(2025, 9, 7, 16, 5, tzinfo=timezone.utc))
    assert df.loc[0, "home_spread"] == 1.5 and df.loc[0, "away_spread"] == -1.5


def test_odds_event_without_draftkings_is_kept():
    ev = [{"id": "e2", "commence_time": "2025-09-07T17:00:00Z", "home_team": "A", "away_team": "B",
           "bookmakers": []}]
    df = flatten(ev, datetime(2025, 9, 7, tzinfo=timezone.utc))
    assert len(df) == 1 and pd.isna(df.loc[0, "home_spread"])
