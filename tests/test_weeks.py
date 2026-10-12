from datetime import date

import pandas as pd

from ats.weeks import football_week_start, football_week_start_series, season_for_date


def test_tuesday_starts_week():
    assert football_week_start(date(2025, 9, 9)) == date(2025, 9, 9)    # Tue
    assert football_week_start(date(2025, 9, 15)) == date(2025, 9, 9)   # Mon
    assert football_week_start(date(2025, 9, 16)) == date(2025, 9, 16)  # next Tue


def test_monday_night_stays_in_week_despite_utc_tuesday():
    # MNF 8:15pm ET Mon 2025-09-15 = 00:15 UTC Tue 2025-09-16.
    ts = pd.Timestamp("2025-09-16 00:15", tz="UTC")
    assert football_week_start(ts) == date(2025, 9, 9)


def test_naive_datetime_assumed_utc():
    assert football_week_start(pd.Timestamp("2025-09-16 00:15").to_pydatetime()) == date(2025, 9, 9)


def test_dst_boundary():
    # DST ends Sun 2025-11-02. Mon night 11/03 game, Tue 11/04 morning.
    s = pd.Series(pd.to_datetime(["2025-11-04 01:15", "2025-11-04 16:00"], utc=True))
    assert list(football_week_start_series(s)) == [date(2025, 10, 28), date(2025, 11, 4)]


def test_series_matches_scalar():
    s = pd.Series(pd.date_range("2025-08-20", "2026-02-15", freq="7h", tz="UTC"))
    assert list(football_week_start_series(s)) == [football_week_start(t) for t in s]


def test_season_for_date():
    assert season_for_date(date(2025, 9, 1)) == 2025
    assert season_for_date(date(2026, 1, 20)) == 2025
    assert season_for_date(date(2026, 8, 1)) == 2026
