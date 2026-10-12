import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from ats import pickem, weekly
from ats.teams import build_nfl_map

TEAMS = pd.DataFrame({
    "team_abbr": ["KC", "LV", "DAL", "PHI"],
    "team_name": ["Kansas City Chiefs", "Las Vegas Raiders", "Dallas Cowboys", "Philadelphia Eagles"],
    "team_nick": ["Chiefs", "Raiders", "Cowboys", "Eagles"],
})


@pytest.fixture(autouse=True)
def nfl_names(monkeypatch):
    import ats.teams as T
    T._name_map.cache_clear()
    m = build_nfl_map(TEAMS)
    monkeypatch.setattr(T, "_name_map", lambda lg: m if lg == "NFL" else {})


WEEK = pd.DataFrame({"league": ["NFL", "NFL"], "game_id": ["g1", "g2"],
                     "home": ["KC", "PHI"], "away": ["LV", "DAL"]})


def test_pickem_number_belongs_to_preceding_team_and_home_from_schedule():
    lines, unparsed = pickem.parse_lines(
        ["Chiefs -7.5 Raiders", "Cowboys +3 at Eagles", "TIEBREAKER: total points ____"], WEEK)
    got = lines.set_index("game_id")["pickem_home_spread"].to_dict()
    assert got == {"g1": -7.5, "g2": -3.0}   # DAL +3 -> PHI (home) -3
    assert len(lines) == 2  # the tiebreaker line has no team pair and is skipped


def test_pickem_pk_and_away_favorite():
    lines, _ = pickem.parse_lines(["Raiders -2.5 Chiefs", "Eagles PK Cowboys"], WEEK)
    got = lines.set_index("game_id")["pickem_home_spread"].to_dict()
    assert got == {"g1": 2.5, "g2": 0.0}


def _ranking(gen, games):
    return {"generated_at": gen, "games": games}


def test_grade_headline_vs_final_and_push(tmp_path, monkeypatch):
    monkeypatch.setattr(weekly, "RANKINGS", tmp_path / "rankings")
    monkeypatch.setattr(weekly, "RESULTS", tmp_path / "results.csv")
    wk = tmp_path / "rankings" / "2026-10-06"
    wk.mkdir(parents=True)
    g = {"league": "NFL", "game_id": "g1", "kickoff_utc": "2026-10-11T17:00:00+00:00",
         "pick_side": "home", "pick_team": "KC", "p_cover": 0.53, "edge": 0.03, "rank": 1,
         "pickem_home_spread": -7.0, "live_home_spread": -6.5, "grade_line_kind": "pickem"}
    (wk / "a.json").write_text(json.dumps(_ranking("2026-10-06T13:00:00+00:00", [g])))
    (wk / "b.json").write_text(json.dumps(_ranking("2026-10-09T14:00:00+00:00", [{**g, "rank": 4}])))
    # ranking published after kickoff must be ignored
    (wk / "c.json").write_text(json.dumps(_ranking("2026-10-11T18:00:00+00:00", [{**g, "rank": 9}])))

    finals = pd.DataFrame({"game_id": ["g1"], "league": ["NFL"], "margin": [7.0], "close_home_spread": [-6.5]})
    import ats.model.data as D
    monkeypatch.setattr(D, "games", type("F", (), {"__call__": staticmethod(lambda lg: finals if lg == "NFL" else finals.iloc[:0]),
                                                   "cache_clear": staticmethod(lambda: None)})())
    new = weekly.grade().set_index("version")
    assert new.loc["headline", "rank"] == 1 and new.loc["final", "rank"] == 4
    assert pd.isna(new.loc["headline", "hit_pickem"])          # 7 - 7 = push
    assert new.loc["headline", "hit_live"] == 1.0               # 7 - 6.5 > 0
    assert pd.isna(new.loc["headline", "hit_graded"])           # graded on pickem -> push
    assert len(weekly.grade()) == 0                             # append-only: nothing regraded


def test_write_ranking_is_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr(weekly, "RANKINGS", tmp_path)
    p = {"generated_at": "2026-10-06T13:00:00+00:00", "games": []}
    weekly.write_ranking(p, pd.DataFrame(), "2026-10-06", "weekly")
    with pytest.raises(FileExistsError):
        weekly.write_ranking(p, pd.DataFrame(), "2026-10-06", "weekly")


def test_locks_keep_pre_kickoff_entry():
    now = datetime(2026, 10, 11, 18, tzinfo=timezone.utc)
    table = pd.DataFrame([{"game_id": "g1", "kickoff_utc": "2026-10-11T17:00:00+00:00", "p_cover": 0.60,
                           "flags": ""},
                          {"game_id": "g2", "kickoff_utc": "2026-10-12T00:20:00+00:00", "p_cover": 0.55,
                           "flags": ""}])
    prior = [{"generated_at": "2026-10-10T14:00:00+00:00",
              "games": [{"game_id": "g1", "kickoff_utc": "2026-10-11T17:00:00+00:00", "p_cover": 0.52}]}]
    out = weekly.apply_locks(table, prior, now).set_index("game_id")
    assert out.loc["g1", "p_cover"] == 0.52 and out.loc["g1", "locked"]
    assert out.loc["g2", "p_cover"] == 0.55 and not out.loc["g2", "locked"]
