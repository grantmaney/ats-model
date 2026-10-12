"""Pickem-line slot: parse the weekly pool sheet in data/pickem/ and match it
to this week's games.

Sources, newest file wins:
- CSV  (exact, recommended fallback): columns league,away,home,home_spread
- PDF  ("ROWANSPOOL 2026 - Football Pickem"): best-effort text parser.
  Heuristic until we've seen a real sheet: on each text line, the spread
  number belongs to the team named immediately before it
  ("Chiefs -3.5 Raiders" -> Chiefs -3.5). Home/away always come from the
  schedule, never from the sheet. Unparsed lines are reported, not guessed.

The pickem line is fixed once published; we record the file name and its
modification time as the line's source/timestamp.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import PICKEM
from .teams import to_canonical

log = logging.getLogger(__name__)
NUM = re.compile(r"(?<![\w.])([+-]?\d{1,2}(?:\.5|½)?|PK|pk|EVEN|even)(?![\w.])")


def latest_file(folder: Path = PICKEM) -> Path | None:
    files = [p for p in folder.glob("*") if p.suffix.lower() in (".pdf", ".csv")]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _num(tok: str) -> float:
    if tok.lower() in ("pk", "even"):
        return 0.0
    return float(tok.replace("½", ".5"))


def pdf_lines(path: Path) -> list[str]:
    import pdfplumber
    out = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            out += [ln.strip() for ln in (page.extract_text() or "").splitlines() if ln.strip()]
    return out


def parse_lines(lines: list[str], week_games: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Match free-text lines to this week's games. week_games: league, game_id,
    home, away (canonical)."""
    by_pair = {}
    for r in week_games.itertuples():
        by_pair[(r.league, frozenset((r.home, r.away)))] = r
    rows, unparsed = [], []
    for ln in lines:
        m = NUM.search(ln)
        if not m:
            continue
        left, right = ln[:m.start()].strip(" @:-|"), ln[m.end():].strip(" @:-|")
        left = re.sub(r"^(at|vs\.?)\s+", "", left, flags=re.I)
        right = re.sub(r"^(at|vs\.?)\s+", "", right, flags=re.I)
        found = None
        for lg in ("NFL", "CFB"):
            (a, b), _ = to_canonical(lg, pd.Series([left, right]), fuzzy=True)
            if isinstance(a, str) and isinstance(b, str):
                g = by_pair.get((lg, frozenset((a, b))))
                if g is not None:
                    found = (lg, g, a)
                    break
        if not found:
            unparsed.append(ln)
            continue
        lg, g, team_with_number = found
        spread = _num(m.group(1))
        home_spread = spread if team_with_number == g.home else -spread
        rows.append({"league": lg, "game_id": g.game_id, "home": g.home, "away": g.away,
                     "pickem_home_spread": home_spread, "raw": ln})
    return pd.DataFrame(rows), unparsed


def load(week_games: pd.DataFrame, path: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """Pickem lines for this week's games. Returns (lines, info)."""
    path = path or latest_file()
    info = {"file": None, "file_mtime": None, "matched": 0, "unparsed": []}
    if path is None:
        return pd.DataFrame(columns=["game_id", "pickem_home_spread"]), info
    info["file"] = path.name
    info["file_mtime"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    if path.suffix.lower() == ".csv":
        c = pd.read_csv(path)
        out = []
        for lg, grp in c.groupby("league"):
            lg = lg.upper()
            h, _ = to_canonical(lg, grp["home"], fuzzy=True)
            a, _ = to_canonical(lg, grp["away"], fuzzy=True)
            out.append(pd.DataFrame({"league": lg, "home": h.values, "away": a.values,
                                     "pickem_home_spread": grp["home_spread"].astype(float).values}))
        lines = pd.concat(out).merge(week_games[["league", "home", "away", "game_id"]],
                                     on=["league", "home", "away"], how="inner")
        unparsed = []
    else:
        lines, unparsed = parse_lines(pdf_lines(path), week_games)
    lines = lines.drop_duplicates("game_id", keep="first")
    info["matched"], info["unparsed"] = len(lines), unparsed[:50]
    if len(lines) == 0:
        log.warning("pickem file %s matched no games this week; ignoring it", path.name)
    return lines[["game_id", "pickem_home_spread"]], info
