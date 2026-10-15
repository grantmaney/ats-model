"""Team-name normalization across sources.

Canonical names: NFL -> nflverse abbreviation (KC, LA, LAC, ...);
CFB -> CFBD school name ("Alabama", "Miami (OH)", "San José State").

The Odds API uses full names ("Kansas City Chiefs", "Alabama Crimson Tide"),
so we key on a normalized "school mascot" string. Unmatched names are
returned to the caller to report; nothing is dropped silently.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import pandas as pd

# Source name (normalized) -> canonical name, for cases the automatic
# school+mascot keys miss. Add entries as `ats check` reports them.
# nflverse's team list carries both LA and LAR for the Rams; schedules use LA.
# Short names used by the pool sheet and other sources.
NFL_OVERRIDES: dict[str, str] = {"Los Angeles Rams": "LA", "LA Rams": "LA", "LA Chargers": "LAC",
                                 "NY Jets": "NYJ", "NY Giants": "NYG"}
CFB_OVERRIDES: dict[str, str] = {"Louisiana-Lafayette": "Louisiana", "Louisiana-Monroe": "UL Monroe"}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[.'`’]", "", s)
    s = re.sub(r"[^a-z0-9()]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def build_nfl_map(teams: pd.DataFrame) -> dict[str, str]:
    m = {norm(n): a for n, a in zip(teams["team_name"], teams["team_abbr"])}
    m.update({norm(a): a for a in teams["team_abbr"]})
    # Nicknames ("Chiefs") and cities ("Kansas City") for pool sheets; current
    # franchises only, so "Rams" -> LA rather than STL.
    current = teams[~teams["team_abbr"].isin(["STL", "SD", "OAK", "LAR"])]
    if "team_nick" in teams:
        for nick, name, a in zip(current["team_nick"], current["team_name"], current["team_abbr"]):
            m.setdefault(norm(nick), a)
            city = str(name)[: -len(str(nick))].strip() if str(name).endswith(str(nick)) else None
            if city and city not in ("New York", "Los Angeles"):  # ambiguous cities
                m.setdefault(norm(city), a)
    m.update({norm(k): v for k, v in NFL_OVERRIDES.items()})
    return m


def build_cfb_map(teams: pd.DataFrame) -> dict[str, str]:
    m: dict[str, str] = {}
    for _, r in teams.iterrows():
        school, mascot = r["school"], r.get("mascot")
        names = [school]
        alts = r.get("alternateNames")  # list (or ndarray after a parquet round-trip)
        if alts is not None and not isinstance(alts, (str, float)):
            names += [a for a in list(alts) if isinstance(a, str)]
        for n in names:
            m.setdefault(norm(n), school)
            if isinstance(mascot, str) and mascot:
                m.setdefault(norm(f"{n} {mascot}"), school)
    m.update({norm(k): v for k, v in CFB_OVERRIDES.items()})
    return m


@lru_cache(maxsize=2)
def _name_map(league: str) -> dict[str, str]:
    if league == "NFL":
        from .loaders import nfl
        return build_nfl_map(nfl.load_teams())
    from .loaders import cfb
    return build_cfb_map(cfb.load_teams())


def to_canonical(league: str, names: pd.Series, mapping: dict[str, str] | None = None,
                 fuzzy: bool = False) -> tuple[pd.Series, list[str]]:
    """Map source names to canonical names. Returns (mapped, unmatched).
    fuzzy=True adds a close-match fallback (for hand-typed pool sheets only;
    API names must match exactly)."""
    import difflib
    mapping = mapping if mapping is not None else _name_map(league)
    keys = list(mapping)

    def one(n):
        if not isinstance(n, str):
            return None
        k = norm(n)
        if k in mapping:
            return mapping[k]
        if fuzzy:
            hit = difflib.get_close_matches(k, keys, n=1, cutoff=0.88)
            return mapping[hit[0]] if hit else None
        return None

    mapped = names.map(one)
    unmatched = sorted(set(names[mapped.isna() & names.notna()]))
    return mapped, unmatched
