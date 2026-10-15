"""Pickem-line slot: parse the weekly pool sheet in data/pickem/ and match it
to this week's games.

Every sheet in the folder is tried; the one that matches the most of this
week's games is used (so past weeks' sheets can stay). Formats:
- CSV  (exact, recommended fallback): columns league,away,home,home_spread
- PDF  ("ROWANSPOOL 2026 - Football Pickem" Picksheet print preview):
  rows are "Favorite (W-L) Underdog (W-L)" with the favorite's spread as an
  unsigned number, on the line after the matchup for NFL and at the end of
  the kickoff line before it for college ("College Games" starts CFB).
  Home teams are in capitals on the sheet, but home/away always come from
  the schedule; the sign is set by whether the favorite is the home team.
  Other PDFs fall back to a heuristic: the number belongs to the team named
  immediately before it ("Chiefs -3.5 Raiders" -> Chiefs -3.5).
  Unparsed rows are reported, not guessed.

PDFs are not kept: convert_pdfs() turns each one into a CSV holding only
league, away, home and home_spread, then deletes the PDF, so the member name
printed on the sheet never stays in the repo. The weekly run does this
before reading lines, and `python -m ats pickem` does it locally.

The pickem line is fixed once published; we record the file name and when it
was committed to the repo as the line's source/timestamp. Until a sheet for
the current week is present, picks use the live DraftKings line.
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


REC = r"\(\d+-\d+(?:-\d+)?\)"
MATCHUP = re.compile(rf"^(?:None\s+)?(?P<fav>.+?)\s+{REC}\s+(?P<dog>.+?)\s+{REC}$")
KICKOFF = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*[AP]M\s+PT"
                     r"(?:\s+(?P<num>\d{1,2}(?:\.\d)?))?$")
BARE_NUM = re.compile(r"^\d{1,2}(?:\.\d)?$")


def is_rowanspool(lines: list[str]) -> bool:
    return any(ln.startswith("Kickoff Favorite") for ln in lines)


def parse_rowanspool(lines: list[str], week_games: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Picksheet layout (see module docstring). The line is the favorite's
    spread, so home_spread = -line if the favorite is the home team."""
    by_pair = {(r.league, frozenset((r.home, r.away))): r for r in week_games.itertuples()}
    rows, unparsed = [], []
    league, pending = "NFL", None
    for i, ln in enumerate(lines):
        if ln.startswith("College Games"):
            league = "CFB"
            continue
        k = KICKOFF.match(ln)
        if k:
            pending = _num(k.group("num")) if k.group("num") else None
            continue
        m = MATCHUP.match(ln)
        if not m:
            continue
        num = pending
        if num is None and i + 1 < len(lines) and BARE_NUM.match(lines[i + 1]):
            num = float(lines[i + 1])
        pending = None
        (fav, dog), _ = to_canonical(league, pd.Series([m["fav"], m["dog"]]), fuzzy=True)
        g = by_pair.get((league, frozenset((fav, dog)))) if isinstance(fav, str) and isinstance(dog, str) else None
        if g is None or num is None:
            unparsed.append(f"{league}: {ln}" + ("" if num is not None else " (no line)"))
            continue
        rows.append({"league": league, "game_id": g.game_id, "home": g.home, "away": g.away,
                     "pickem_home_spread": -num if fav == g.home else num, "raw": f"{ln} {num}"})
    return pd.DataFrame(rows), unparsed


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


def added_at(path: Path) -> str:
    """When the sheet entered the repo (git commit time); file mtime is
    meaningless on CI checkouts, so it is only a local fallback."""
    import subprocess
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", str(path)], cwd=path.parent,
                             capture_output=True, text=True, timeout=10).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


EMPTY = pd.DataFrame(columns=["game_id", "pickem_home_spread"])


def _csv_name(text: list[str], pdf: Path) -> str:
    season = next((m[1] for ln in text if (m := re.match(r"Season:\s*(\d{4})", ln))), None)
    week = next((m[1] for ln in text if (m := re.match(r"Week:\s*Week\s*(\d+)", ln))), None)
    if season and week:
        return f"{season}-week{int(week):02d}-pool.csv"
    return re.sub(r"[^A-Za-z0-9]+", "-", pdf.stem).strip("-").lower() + ".csv"


def convert_pdfs(week_games: pd.DataFrame, folder: Path | None = None) -> list[dict]:
    """Replace every pool-sheet PDF in the folder with a CSV of its lines
    (no member name or other sheet text). A PDF none of whose games match
    this week's schedule is left in place and reported, so nothing is lost."""
    folder = folder or PICKEM
    report = []
    for pdf in sorted(p for p in folder.glob("*") if p.suffix.lower() == ".pdf"):
        text = pdf_lines(pdf)
        parse = parse_rowanspool if is_rowanspool(text) else parse_lines
        lines, unparsed = parse(text, week_games)
        item = {"pdf": pdf.name, "matched": len(lines), "unparsed": unparsed, "csv": None}
        if len(lines):
            out = folder / _csv_name(text, pdf)
            (lines.drop_duplicates("game_id")
                  .rename(columns={"pickem_home_spread": "home_spread"})
                  [["league", "away", "home", "home_spread"]]
                  .to_csv(out, index=False))
            pdf.unlink()
            item["csv"] = out.name
            log.info("pool sheet %s -> %s (%d games, %d unparsed)", pdf.name, out.name, len(lines), len(unparsed))
        else:
            log.warning("pool sheet %s matched no games this week; left as is", pdf.name)
        report.append(item)
    return report


def load(week_games: pd.DataFrame, path: Path | None = None, folder: Path | None = None
         ) -> tuple[pd.DataFrame, dict]:
    """Pickem lines for this week's games. With no explicit path, every sheet in
    data/pickem/ is tried and the one matching the most of this week's games
    wins, so old weeks' sheets can stay in the folder. Returns (lines, info)."""
    if path is not None:
        return _load_one(path, week_games)
    folder = folder or PICKEM
    files = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".pdf", ".csv"))
    best = (EMPTY, {"file": None, "added_at": None, "matched": 0, "unparsed": []})
    for p in files:
        try:
            lines, info = _load_one(p, week_games)
        except Exception as e:  # one unreadable sheet shouldn't block the run
            log.warning("could not read pickem file %s: %s", p.name, e)
            continue
        if info["matched"] > best[1]["matched"]:
            best = (lines, info)
    return best


def _load_one(path: Path, week_games: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    info = {"file": path.name, "added_at": added_at(path), "matched": 0, "unparsed": []}
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
        text = pdf_lines(path)
        parse = parse_rowanspool if is_rowanspool(text) else parse_lines
        lines, unparsed = parse(text, week_games)
    if lines.empty:
        return EMPTY, info
    lines = lines.drop_duplicates("game_id", keep="first")
    info["matched"], info["unparsed"] = len(lines), unparsed[:50]
    return lines[["game_id", "pickem_home_spread"]], info
