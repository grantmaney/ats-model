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


def test_pickem_uses_the_sheet_that_matches_this_week(tmp_path):
    (tmp_path / "week5.csv").write_text("league,away,home,home_spread\nNFL,Jets,Patriots,-3\n")
    (tmp_path / "week6.csv").write_text("league,away,home,home_spread\nNFL,Raiders,Chiefs,-7.5\nNFL,Cowboys,Eagles,-3\n")
    lines, info = pickem.load(WEEK, folder=tmp_path)
    assert info["file"] == "week6.csv" and info["matched"] == 2
    assert lines.set_index("game_id")["pickem_home_spread"].to_dict() == {"g1": -7.5, "g2": -3.0}


def test_no_sheet_for_this_week_means_live_lines(tmp_path):
    (tmp_path / "week5.csv").write_text("league,away,home,home_spread\nNFL,Jets,Patriots,-3\n")
    lines, info = pickem.load(WEEK, folder=tmp_path)
    assert info["file"] is None and lines.empty


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
    # after the Friday 10pm PT deadline (2026-10-10 05:00 UTC): not the submission
    (wk / "c.json").write_text(json.dumps(_ranking("2026-10-10T12:00:00+00:00", [{**g, "rank": 7}])))
    # after kickoff: ignored
    (wk / "d.json").write_text(json.dumps(_ranking("2026-10-11T18:00:00+00:00", [{**g, "rank": 9}])))

    finals = pd.DataFrame({"game_id": ["g1"], "league": ["NFL"], "margin": [7.0], "close_home_spread": [-6.5]})
    import ats.model.data as D
    monkeypatch.setattr(D, "games", type("F", (), {"__call__": staticmethod(lambda lg: finals if lg == "NFL" else finals.iloc[:0]),
                                                   "cache_clear": staticmethod(lambda: None)})())
    new = weekly.grade().set_index("version")
    assert new.loc["headline", "rank"] == 1 and new.loc["submitted", "rank"] == 4
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


WK = "2026-10-06"  # Tue; deadline Fri 2026-10-09 22:00 PDT = 2026-10-10 05:00 UTC


def test_submit_lock_is_friday_10pm_pacific():
    assert weekly.submit_lock(WK) == pd.Timestamp("2026-10-10T05:00:00Z")
    # Thursday-night game locks at its own kickoff
    assert weekly.lock_time("2026-10-09T00:15:00+00:00", WK) == pd.Timestamp("2026-10-09T00:15:00Z")


def _table(rows):
    return pd.DataFrame([{"flags": "", "pick_side": "home", "pick_team": "X", **r} for r in rows])


def test_thursday_game_locks_at_kickoff_others_stay_open():
    now = datetime(2026, 10, 9, 2, tzinfo=timezone.utc)  # Thu 7pm PT, after TNF kickoff
    table = _table([{"game_id": "thu", "kickoff_utc": "2026-10-09T00:15:00+00:00", "p_cover": 0.60},
                    {"game_id": "sun", "kickoff_utc": "2026-10-11T17:00:00+00:00", "p_cover": 0.55}])
    prior = [{"generated_at": "2026-10-07T14:00:00+00:00", "games": [
        {"game_id": "thu", "kickoff_utc": "2026-10-09T00:15:00+00:00", "p_cover": 0.52, "pick_side": "home"}]}]
    out = weekly.apply_locks(table, prior, now, WK).set_index("game_id")
    assert out.loc["thu", "p_cover"] == 0.52 and out.loc["thu", "locked"]
    assert out.loc["sun", "p_cover"] == 0.55 and not out.loc["sun", "locked"]


def test_everything_frozen_after_friday_deadline():
    now = datetime(2026, 10, 10, 15, tzinfo=timezone.utc)  # Sat morning, before Sunday kickoff
    table = _table([{"game_id": "sun", "kickoff_utc": "2026-10-11T17:00:00+00:00", "p_cover": 0.61},
                    {"game_id": "new", "kickoff_utc": "2026-10-11T20:00:00+00:00", "p_cover": 0.58}])
    prior = [
        {"generated_at": "2026-10-09T14:00:00+00:00", "games": [
            {"game_id": "sun", "kickoff_utc": "2026-10-11T17:00:00+00:00", "p_cover": 0.53, "pick_side": "away"}]},
        # published after the deadline: must not be used
        {"generated_at": "2026-10-10T06:00:00+00:00", "games": [
            {"game_id": "sun", "kickoff_utc": "2026-10-11T17:00:00+00:00", "p_cover": 0.70, "pick_side": "home"}]},
    ]
    out = weekly.apply_locks(table, prior, now, WK).set_index("game_id")
    assert out.loc["sun", "p_cover"] == 0.53 and out.loc["sun", "pick_side"] == "away"
    # never ranked before its lock -> no pick at all
    assert out.loc["new", "unranked"] and pd.isna(out.loc["new", "p_cover"]) and pd.isna(out.loc["new", "pick_side"])


def test_rowanspool_picksheet_layout():
    # Rows copied from the real Week 6 sheet: favorite first, home in caps,
    # NFL line on the next line, college line at the end of the kickoff line.
    text = ["Kickoff Favorite Line Underdog",
            "Sun 10/18/2026 1:25 PM PT", "KANSAS CITY (4-0) Las Vegas (0-5)", "8.5",
            "Sun 10/18/2026 5:20 PM PT", "Dallas (2-3) PHILADELPHIA (3-1-1)", "1.5",
            "College Games", "Kickoff Favorite Spread Underdog"]
    assert pickem.is_rowanspool(text)
    lines, unparsed = pickem.parse_rowanspool(text, WEEK)
    assert unparsed == []
    assert lines.set_index("game_id")["pickem_home_spread"].to_dict() == {"g1": -8.5, "g2": 1.5}
