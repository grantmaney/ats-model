"""Football-week helpers. A football week runs Tuesday 00:00 through Monday
23:59 in WEEK_TZ; it is identified by its Tuesday date."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from .config import WEEK_TZ

TUESDAY = 1  # date.weekday()


def football_week_start(ts) -> date:
    """Tuesday that starts the football week containing `ts`.

    `ts` may be a date (taken as-is) or a datetime/Timestamp. Naive datetimes
    are assumed UTC; aware ones are converted to WEEK_TZ before taking the date.
    """
    if isinstance(ts, date) and not isinstance(ts, datetime):
        d = ts
    else:
        t = pd.Timestamp(ts)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        d = t.tz_convert(WEEK_TZ).date()
    return d - timedelta(days=(d.weekday() - TUESDAY) % 7)


def football_week_start_series(kickoff_utc: pd.Series) -> pd.Series:
    """Vectorized football_week_start for a tz-aware UTC Series."""
    local = pd.to_datetime(kickoff_utc, utc=True).dt.tz_convert(WEEK_TZ)
    days = (local.dt.weekday - TUESDAY) % 7
    return (local.dt.normalize() - pd.to_timedelta(days, unit="D")).dt.date


def season_for_date(d: date) -> int:
    """Season a calendar date belongs to: Aug-Dec -> that year; Jan-Jul ->
    the previous year (bowls, NFL playoffs, offseason)."""
    return d.year if d.month >= 8 else d.year - 1


def current_season(today: date | None = None) -> int:
    return season_for_date(today or datetime.now().date())
