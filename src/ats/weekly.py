"""Weekly ranking (Tuesday main run) and daily refresh.

    python -m ats weekly     # Tuesday: grade last week, refresh data, rank, publish
    python -m ats refresh    # Wed-Sat: refresh lines, re-rank, lock kicked-off games

Outputs (append-only; an existing file is never rewritten):
    data/rankings/<week_start>/<UTC stamp>_<kind>.json / .csv
    site/data/latest.json  (what the web page renders; overwritten each run)

Lines: the pick is graded against the pickem line when the pool sheet has the
game, else the live DraftKings line. The model's market input is always the
live line (latest snapshot as of this run), so a stale pickem line shows up
as edge, as CLAUDE.md intends.
"""
from __future__ import annotations

import json
import logging
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import pickem
from .backtest import metrics as M
from .backtest import walkforward as W
from .config import DATA, ROOT, WEEK_TZ
from .weeks import current_season, football_week_start, football_week_start_series

log = logging.getLogger(__name__)
RANKINGS = DATA / "rankings"
RESULTS = DATA / "results" / "results.csv"
SITE_DATA = ROOT / "site" / "data"
FIRST_SEASON = {"NFL": 2012, "CFB": 2014}


# ---------------------------------------------------------------- data refresh
def refresh_data(season: int, snapshot_odds: bool = True) -> dict:
    """Refresh current-season data (past seasons are cached immutably) and
    rebuild the interim games tables. Returns odds snapshot info."""
    from .__main__ import cmd_fetch
    from argparse import Namespace
    for lg in ("nfl", "cfb"):
        cmd_fetch(Namespace(league=lg, seasons=f"{FIRST_SEASON[lg.upper()]}-{season}",
                            no_pbp=False, force=False))
    info = {}
    if snapshot_odds:
        from .loaders import odds
        for lg in ("NFL", "CFB"):
            try:
                df = odds.snapshot(lg)
                info[lg] = {"events": len(df), "fetched_at": str(df["fetched_at"].max()) if len(df) else None}
            except Exception as e:  # keep ranking with older snapshots
                log.error("odds snapshot %s failed: %s", lg, e)
                info[lg] = {"error": str(e)}
    return info


MAX_LINE_AGE = pd.Timedelta(hours=36)


def live_lines(league: str, games: pd.DataFrame, as_of: datetime) -> pd.DataFrame:
    """Latest DraftKings home spread per game as of `as_of`, matched to games
    (home/away swapped matches have their sign flipped). Lines fetched more
    than MAX_LINE_AGE before `as_of` are dropped: DraftKings posts next week's
    games early, and a week-old look-ahead line is not a live line (the game
    is then flagged "no live DK line")."""
    from .loaders import odds
    s = odds.latest_lines(league, as_of=as_of)
    if not s.empty:
        s = s[pd.to_datetime(s["fetched_at"], utc=True) >= pd.Timestamp(as_of) - MAX_LINE_AGE]
    if s.empty:
        return pd.DataFrame(columns=["game_id", "live_home_spread", "live_fetched_at", "live_book_update"])
    s = s.assign(football_week_start=pd.to_datetime(football_week_start_series(s["commence_time"])))
    key = ["home", "away", "football_week_start"]
    g = games[key + ["game_id"]]
    a = s.merge(g, on=key, how="inner").assign(sign=1.0)
    b = s.merge(g.rename(columns={"home": "away", "away": "home"}), on=key, how="inner").assign(sign=-1.0)
    m = pd.concat([a, b]).drop_duplicates("game_id")
    return pd.DataFrame({"game_id": m["game_id"], "live_home_spread": m["home_spread"] * m["sign"],
                         "live_fetched_at": m["fetched_at"], "live_book_update": m["book_last_update"]})


# ---------------------------------------------------------------- prediction
def predict_league(league: str, week_start: pd.Timestamp, now: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the walk-forward pipeline through the current week, with the live
    line substituted as the market input for this week's games. Returns
    (this week's rows, all earlier rows)."""
    from .model import data
    data.games.cache_clear(); data.obs.cache_clear()
    g, o = data.games(league), data.obs(league)
    live = live_lines(league, g[g["football_week_start"] == week_start], now)
    frame = W.build_frame(league, g, o)
    frame = frame.merge(live, on="game_id", how="left")
    cur = frame["football_week_start"] == week_start
    # Market input for this week = live DK line; fall back to the source's
    # pregame line (flagged) when DK has none.
    frame["market_line_source"] = np.where(cur & frame["live_home_spread"].notna(), "draftkings_live",
                                           np.where(cur, frame["line_source"], "historical_close"))
    frame.loc[cur & frame["live_home_spread"].notna(), "close_home_spread"] = frame.loc[
        cur & frame["live_home_spread"].notna(), "live_home_spread"]
    frame = frame[frame["football_week_start"] <= week_start]
    out = W.run(league, g, o, frame=frame)
    return out[out["football_week_start"] == week_start].copy(), out[out["football_week_start"] < week_start]


def _confidence_table(league: str) -> pd.DataFrame | None:
    """league = 'NFL' / 'CFB' (graded vs the live line) or 'stale' (graded vs
    a pickem line the market may have moved away from)."""
    p = ROOT / "reports" / f"edge_table_{league.lower()}.csv"
    return pd.read_csv(p) if p.exists() else None


def confidence(edge: float, table: pd.DataFrame | None) -> tuple[str, str]:
    """Low/Medium/High from the backtested hit rate at this edge level."""
    if table is None or np.isnan(edge):
        return "Low", "no backtest"
    for _, r in table.iterrows():
        lo, hi = (float(x) for x in r["edge"].strip("([]").split(", "))
        if lo < edge <= hi or (edge <= hi and lo < 0):
            label = "High" if r["ci_lo"] > M.BREAKEVEN else "Medium" if r["ci_lo"] > 0.5 else "Low"
            return label, f"backtest {100 * r['hit_rate']:.1f}% (n={r['n']}) at this edge"
    return "Low", "edge outside backtested range"


def _fmt_line(x: float) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return "PK" if x == 0 else f"{x:+.1f}"


def key_reason(r: pd.Series) -> str:
    pick_home = r["pick_home"]
    sgn = 1 if pick_home else -1
    team = r["home"] if pick_home else r["away"]
    if pd.notna(r.get("pickem_home_spread")) and pd.notna(r.get("live_home_spread")):
        move = (r["pickem_home_spread"] - r["live_home_spread"]) * sgn  # >0: market moved toward pick
        if abs(move) >= 1:
            return (f"Line moved {abs(move):.1f} pts {'toward' if move > 0 else 'away from'} {team} since the "
                    f"pickem line ({_fmt_line(sgn * r['pickem_home_spread'])} -> {_fmt_line(sgn * r['live_home_spread'])})")
    fair2 = -r["pred2"] * sgn
    mkt = r["line"] * sgn
    if abs(fair2 - mkt) >= 2:
        return f"Ratings alone imply {team} {_fmt_line(fair2)} vs market {_fmt_line(mkt)}"
    if abs(r.get("rest_diff", 0) or 0) >= 4:
        rd = r["rest_diff"] * sgn
        return f"Rest: {team} has {rd:+.0f} days vs opponent"
    return "Small blended edge; no single dominant factor"


def build_table(league: str, cur: pd.DataFrame, past: pd.DataFrame, pick_lines: pd.DataFrame,
                now: datetime) -> pd.DataFrame:
    cur = cur.merge(pick_lines, on="game_id", how="left")
    cur["grade_line_kind"] = np.where(cur["pickem_home_spread"].notna(), "pickem", "live")
    cur["grade_line"] = cur["pickem_home_spread"].where(cur["pickem_home_spread"].notna(), cur["line"])
    has = cur["pred3"].notna() & cur["grade_line"].notna()
    cur["p_home"] = np.nan
    if has.any():
        as_of = W.cutoff(cur["football_week_start"].iloc[0])
        probs = W.cover_probs(league, past, cur.loc[has, "pred3"].to_numpy(float),
                              cur.loc[has, "grade_line"].to_numpy(float), as_of,
                              market_line=cur.loc[has, "line"].to_numpy(float))
        cur.loc[has, "p_home"] = probs["p_cal"]
        cur.loc[has, "calibrated"] = probs["calibrated"]
        cur.loc[has, "w_model"] = probs["w_model"]
        cur.loc[has, "centre"] = probs["centre"]
    cur["pick_home"] = cur["p_home"].fillna(0.5) >= 0.5
    cur["p_pick"] = np.where(cur["pick_home"], cur["p_home"], 1 - cur["p_home"])
    cur["edge"] = cur["p_pick"] - 0.5
    ctab, stab = _confidence_table(league), _confidence_table("stale")
    rows = []
    for _, r in cur.iterrows():
        sgn = 1 if r["pick_home"] else -1
        team = r["home"] if r["pick_home"] else r["away"]
        flags = []
        if pd.isna(r.get("live_home_spread")):
            flags.append("no live DK line")
        if pd.isna(r.get("pickem_home_spread")):
            flags.append("no pickem match")
        if pd.isna(r["pred3"]):
            flags.append("no model prediction")
        if r.get("calibrated", 1) == 0:
            flags.append("uncalibrated")
        conf, conf_why = confidence(r["edge"], stab if r["grade_line_kind"] == "pickem" else ctab)
        rows.append({
            "league": league, "game_id": r["game_id"], "kickoff_utc": r["kickoff_utc"].isoformat(),
            "away": r["away"], "home": r["home"], "neutral_site": bool(r["neutral_site"]),
            "pick_team": team, "pick_side": "home" if r["pick_home"] else "away",
            "pick_line": sgn * r["grade_line"] if pd.notna(r["grade_line"]) else None,
            "grade_line_kind": r["grade_line_kind"],
            "pickem_home_spread": r.get("pickem_home_spread"),
            "live_home_spread": r.get("live_home_spread"),
            "live_fetched_at": str(r.get("live_fetched_at")) if pd.notna(r.get("live_fetched_at")) else None,
            "market_line_source": r.get("market_line_source"),
            # fair line = market moved toward the model by the backtested weight w
            "model_fair_home_spread": -r["centre"] if pd.notna(r.get("centre")) else None,
            "model_weight": r.get("w_model"),
            "ratings_fair_home_spread": -r["pred2"] if pd.notna(r["pred2"]) else None,
            "sigma": r.get("sigma"),
            "p_cover": r["p_pick"], "edge": r["edge"],
            "key_reason": key_reason(r) if pd.notna(r["pred3"]) else "No model prediction",
            "confidence": conf, "confidence_basis": conf_why,
            "flags": "; ".join(flags),
        })
    return pd.DataFrame(rows)


def _unmodeled(league: str, week_start, now, modeled: set, pick_lines: pd.DataFrame) -> pd.DataFrame:
    """Games with a live line or pickem line that the model can't rate
    (e.g. FBS vs FCS). They stay in the table, flagged, with no probability."""
    from .model import data
    g = data.games(league)
    g = g[(g["football_week_start"] == week_start) & ~g["game_id"].isin(modeled)]
    g = g.merge(live_lines(league, g, now), on="game_id", how="left").merge(pick_lines, on="game_id", how="left")
    g = g[g["live_home_spread"].notna() | g["pickem_home_spread"].notna()]
    return pd.DataFrame([{
        "league": league, "game_id": r["game_id"], "kickoff_utc": r["kickoff_utc"].isoformat(),
        "away": r["away"], "home": r["home"], "neutral_site": bool(r["neutral_site"]),
        "pick_team": None, "pick_side": None, "pick_line": None,
        "grade_line_kind": "pickem" if pd.notna(r["pickem_home_spread"]) else "live",
        "pickem_home_spread": r["pickem_home_spread"], "live_home_spread": r["live_home_spread"],
        "live_fetched_at": str(r["live_fetched_at"]) if pd.notna(r["live_fetched_at"]) else None,
        "p_cover": None, "edge": None, "key_reason": "No model prediction",
        "confidence": "Low", "confidence_basis": "not modeled",
        "flags": "not modeled (non-FBS opponent or no ratings)",
    } for _, r in g.iterrows()])


# ---------------------------------------------------------------- logging
def _week_dir(week_start) -> Path:
    return RANKINGS / pd.Timestamp(week_start).strftime("%Y-%m-%d")


def previous_rankings(week_start) -> list[dict]:
    d = _week_dir(week_start)
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))] if d.exists() else []


def submit_lock(week_start) -> pd.Timestamp:
    """Pick submission deadline: Friday 10pm Pacific of the football week."""
    fri = pd.Timestamp(week_start) + pd.Timedelta(days=3, hours=22)
    return fri.tz_localize(WEEK_TZ).tz_convert("UTC")


def lock_time(kickoff_utc: str, week_start) -> pd.Timestamp:
    """A game locks at the submission deadline, or at kickoff if earlier."""
    return min(pd.Timestamp(kickoff_utc), submit_lock(week_start))


PICK_FIELDS = ("pick_team", "pick_side", "pick_line", "p_cover", "edge", "confidence",
               "confidence_basis", "key_reason", "model_fair_home_spread", "ratings_fair_home_spread")


def apply_locks(table: pd.DataFrame, prior: list[dict], now: datetime, week_start) -> pd.DataFrame:
    """Locked games (past kickoff or the Friday deadline) keep their last
    entry published before their lock time. A game that locked before any
    ranking existed gets no pick at all: it is shown, unranked, and never graded."""
    table = table.copy()
    table["locked"] = False
    table["unranked"] = False
    locks = table["kickoff_utc"].map(lambda k: lock_time(k, week_start))
    is_locked = locks <= pd.Timestamp(now)
    last = {}
    for rk in prior:
        for g in rk["games"]:
            if pd.Timestamp(rk["generated_at"]) < lock_time(g["kickoff_utc"], week_start) and g.get("pick_side"):
                last[g["game_id"]] = g
    for i in table.index[is_locked]:
        gid = table.at[i, "game_id"]
        table.at[i, "locked"] = True
        if gid in last:
            for k, v in last[gid].items():
                if k in table.columns and k not in ("rank", "locked", "unranked"):
                    table.at[i, k] = v
        else:
            for k in PICK_FIELDS:
                if k in table.columns:
                    table.at[i, k] = None
            table.at[i, "unranked"] = True
            table.at[i, "key_reason"] = "Started before this week's first ranking; no pick made"
            table.at[i, "flags"] = "not ranked (not graded)"
    return table


def write_ranking(payload: dict, table: pd.DataFrame, week_start, kind: str) -> Path:
    d = _week_dir(week_start)
    d.mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp(payload["generated_at"]).strftime("%Y%m%dT%H%M%SZ")
    jp, cp = d / f"{stamp}_{kind}.json", d / f"{stamp}_{kind}.csv"
    if jp.exists() or cp.exists():
        raise FileExistsError(f"{jp} exists; rankings are append-only")
    jp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    table.to_csv(cp, index=False)
    return jp


# ---------------------------------------------------------------- grading
def grade(now: datetime | None = None) -> pd.DataFrame:
    """Grade every finished, logged game not yet in results.csv (append-only).
    Two versions per game: 'headline' (first ranking of the week, i.e. the
    Tuesday list) and 'submitted' (last ranking published before the game's
    lock: Friday 10pm PT, or kickoff if earlier). 'submitted' is the record."""
    from .model import data
    data.games.cache_clear()
    finals = pd.concat([data.games(lg)[["game_id", "league", "margin", "close_home_spread"]]
                        for lg in ("NFL", "CFB")])
    finals = finals[finals["margin"].notna()].set_index(["league", "game_id"])
    done = set()
    if RESULTS.exists():
        prev = pd.read_csv(RESULTS, dtype={"game_id": str})
        done = set(zip(prev["league"], prev["game_id"], prev["version"]))
    rows = []
    for wdir in sorted(RANKINGS.glob("*")) if RANKINGS.exists() else []:
        ranks = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(wdir.glob("*.json"))]
        if not ranks:
            continue
        entries: dict[tuple, dict] = {}
        for rk in ranks:
            for g in rk["games"]:
                if pd.Timestamp(rk["generated_at"]) >= lock_time(g["kickoff_utc"], wdir.name) or g.get("locked"):
                    continue
                if not g.get("pick_side"):  # unmodeled/unranked game: nothing to grade
                    continue
                k = (g["league"], g["game_id"])
                entries.setdefault(k, {})
                entries[k].setdefault("headline", {**g, "generated_at": rk["generated_at"]})
                entries[k]["submitted"] = {**g, "generated_at": rk["generated_at"]}
        for (lg, gid), vers in entries.items():
            if (lg, gid) not in finals.index:
                continue
            f = finals.loc[(lg, gid)]
            for version, g in vers.items():
                if (lg, gid, version) in done:
                    continue
                sgn = 1 if g["pick_side"] == "home" else -1
                rec = {"week_start": wdir.name, "league": lg, "game_id": gid, "version": version,
                       "ranked_at": g["generated_at"], "rank": g.get("rank"),
                       "pick_team": g["pick_team"], "p_cover": g["p_cover"], "edge": g["edge"],
                       "margin": float(f["margin"]), "graded_at": datetime.now(timezone.utc).isoformat()}
                for kind, hs in (("pickem", g.get("pickem_home_spread")), ("live", g.get("live_home_spread")),
                                 ("close", f["close_home_spread"])):
                    if hs is None or pd.isna(hs):
                        rec[f"hit_{kind}"] = None
                        continue
                    x = sgn * (float(f["margin"]) + float(hs))
                    rec[f"hit_{kind}"] = None if x == 0 else float(x > 0)  # push = None
                    rec[f"line_{kind}"] = float(hs)
                graded = g.get("grade_line_kind", "live")
                rec["hit_graded"] = rec.get(f"hit_{graded}")
                rows.append(rec)
    new = pd.DataFrame(rows)
    if len(new):
        _append_results(new)
    return new


def _append_results(new: pd.DataFrame) -> None:
    """Append rows under the file's existing header. Rows don't all carry the
    same keys (line_pickem only exists for pool-sheet games), so a blind
    append can add a column the header lacks and break the CSV. If a new
    column appears, the file is rewritten with the wider header; existing
    rows are kept as they are, with the new column blank."""
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS.exists():
        new.to_csv(RESULTS, index=False)
        return
    header = pd.read_csv(RESULTS, nrows=0).columns.tolist()
    extra = [c for c in new.columns if c not in header]
    if extra:
        old = pd.read_csv(RESULTS, dtype={"game_id": str})
        pd.concat([old, new[header + extra]], ignore_index=True).to_csv(RESULTS, index=False)
    else:
        new.reindex(columns=header).to_csv(RESULTS, mode="a", header=False, index=False)


def pool_list(games: list[dict]) -> list[dict]:
    """The picks that count for a week: when a pool sheet exists, only games
    on the sheet (others, e.g. midweek games locked before it arrived, were
    never submitted), renumbered in the published order."""
    ranked = sorted((g for g in games if g.get("rank") is not None), key=lambda g: g["rank"])
    if any(g.get("pickem_home_spread") is not None for g in ranked):
        ranked = [g for g in ranked if g.get("pickem_home_spread") is not None]
    return [{**g, "rank": i + 1} for i, g in enumerate(ranked)]


def _hits(games: list[dict], n: int | None) -> pd.Series:
    g = games if n is None else games[:n]
    return pd.Series([1.0 if x.get("result") == "hit" else 0.0 for x in g if x.get("result") in ("hit", "miss")],
                     dtype=float)


def season_record(season: int, current: dict | None = None) -> dict:
    """Season-to-date record of the submitted lists (as on the page): every
    finished week's file plus `current` (this week's payload with results).
    Pushes and unplayed games don't count."""
    weeks = {}
    wdir = SITE_DATA / "weeks"
    for f in sorted(wdir.glob("*.json")) if wdir.exists() else []:
        if f.name == "index.json":
            continue
        p = json.loads(f.read_text(encoding="utf-8"))
        if p.get("season") == season:
            weeks[p["week_start"]] = pool_list(p["games"])
    if current is not None and current.get("season") == season and current.get("games"):
        weeks[current["week_start"]] = pool_list(current["games"])
    out = {"weeks": len(weeks)}
    for label, n in (("top6", 6), ("top10", 10), ("all", None)):
        h = pd.concat([_hits(g, n) for g in weeks.values()]) if weeks else pd.Series(dtype=float)
        out[f"{label}_graded"] = {k: (None if pd.isna(v) else float(v)) for k, v in M.hit_summary(h).items()}
    return out


# ---------------------------------------------------------------- main entry
def run(kind: str = "weekly", now: datetime | None = None, fetch: bool = True) -> dict:
    warnings.filterwarnings("ignore", category=FutureWarning)
    now = now or datetime.now(timezone.utc)
    season = current_season(now.date())
    week_start = pd.Timestamp(football_week_start(now))
    lock = submit_lock(week_start)
    frozen = pd.Timestamp(now) >= lock
    # Always pull fresh results first, then grade anything newly finished.
    odds_info = refresh_data(season, snapshot_odds=not frozen) if fetch else {}
    graded = grade(now)
    # Lines snapshotted just now must count: `now` was taken before the fetch.
    lines_as_of = datetime.now(timezone.utc) if fetch else now
    log.info("graded %d new entries", len(graded))
    if frozen:
        return publish_locked(week_start, season, now)

    tables, notes = [], []
    week_games = []
    from .model import data
    for lg in ("NFL", "CFB"):
        data.games.cache_clear()
        g = data.games(lg)
        week_games.append(g[g["football_week_start"] == week_start][["league", "game_id", "home", "away"]])
    week_games = pd.concat(week_games)
    for c in pickem.convert_pdfs(week_games):
        if c["csv"] is None:
            notes.append(f"Pool sheet {c['pdf']} matched none of this week's games and was not used.")
        elif c["unparsed"]:
            notes.append(f"Pool sheet {c['pdf']}: {len(c['unparsed'])} rows could not be matched: "
                         + "; ".join(c["unparsed"][:5]))
    pick_lines, pick_info = pickem.load(week_games)
    if pick_info["file"] is None:
        notes.append("No pool sheet for this week yet (it arrives Thursday); picks use the live DraftKings line. "
                     "Against the live line every game is close to a coin flip (NFL model weight is 0, so NFL "
                     "games show no edge at all); the ordering only becomes meaningful once pool lines differ "
                     "from the market.")
    elif pick_info["unparsed"]:
        notes.append(f"Pool sheet {pick_info['file']}: {pick_info['matched']} games matched; "
                     f"{len(pick_info['unparsed'])} lines could not be matched (see sources.pickem.unparsed).")

    for lg in ("NFL", "CFB"):
        cur, past = predict_league(lg, week_start, lines_as_of)
        if cur.empty:
            notes.append(f"{lg}: no modeled games for week of {week_start.date()}.")
        else:
            tables.append(build_table(lg, cur, past, pick_lines, now))
        tables.append(_unmodeled(lg, week_start, lines_as_of, set(cur["game_id"]), pick_lines))
    table = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    prior = previous_rankings(week_start)
    if not table.empty:
        table = apply_locks(table, prior, now, week_start)
        has_pick = table["pick_side"].notna() & ~table["unranked"]
        ranked = table[has_pick].sort_values("edge", ascending=False).reset_index(drop=True)
        ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
        rest = table[~has_pick].sort_values("kickoff_utc").assign(rank=None)
        table = pd.concat([ranked, rest], ignore_index=True)

    payload = {
        "generated_at": now.isoformat(), "kind": kind, "status": "open",
        "week_start": str(week_start.date()), "submit_lock": lock.isoformat(), "season": season,
        "sources": {"odds": odds_info, "pickem": pick_info,
                    "stats": "nflverse (nflreadpy), CollegeFootballData.com"},
        "notes": notes,
        "season_record": season_record(season),
        "games": json.loads(table.to_json(orient="records")) if not table.empty else [],
    }
    path = write_ranking(payload, table, week_start, kind)
    _publish_site(attach_results(dict(payload)))
    payload["path"] = str(path)
    return payload


def attach_results(payload: dict) -> dict:
    """Add each game's graded outcome (submitted version) for the page."""
    if not RESULTS.exists():
        return payload
    r = pd.read_csv(RESULTS, dtype={"game_id": str})
    r = r[(r["version"] == "submitted") & (r["week_start"] == payload["week_start"])]
    res = {(row.league, row.game_id): row for row in r.itertuples()}
    games = []
    for g in payload["games"]:
        g = dict(g)
        row = res.get((g["league"], g["game_id"]))
        if row is not None:
            h = row.hit_graded
            g["result"] = "push" if pd.isna(h) else ("hit" if h == 1 else "miss")
            g["final_margin_home"] = row.margin
        games.append(g)
    payload["games"] = games
    return payload


def publish_locked(week_start, season: int, now: datetime) -> dict:
    """After the Friday deadline: re-publish the submitted list (no re-ranking)
    with results filled in as games finish."""
    subs = [rk for rk in previous_rankings(week_start)
            if pd.Timestamp(rk["generated_at"]) < submit_lock(week_start)]
    if not subs:
        payload = {"generated_at": now.isoformat(), "kind": "locked", "status": "locked",
                   "week_start": str(pd.Timestamp(week_start).date()),
                   "submit_lock": submit_lock(week_start).isoformat(), "season": season,
                   "notes": ["No ranking was published before this week's Friday 10pm PT deadline."],
                   "season_record": season_record(season), "games": [], "sources": {}}
    else:
        payload = dict(subs[-1])
        payload["status"] = "locked"
        payload["notes"] = list(payload.get("notes", [])) + [
            f"Picks locked at the Friday 10pm PT deadline; results updated {now.strftime('%Y-%m-%d %H:%M UTC')}."]
        payload["season_record"] = season_record(season)
        payload["results_updated_at"] = now.isoformat()
    payload = attach_results(payload)
    _publish_site(payload)
    payload["path"] = "(locked; no new ranking written)"
    return payload


def _publish_site(payload: dict) -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    publish_past_weeks(payload["week_start"])
    payload["season_record"] = season_record(payload["season"], payload)
    (SITE_DATA / "latest.json").write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    if RESULTS.exists():
        pd.read_csv(RESULTS).to_json(SITE_DATA / "results.json", orient="records", indent=1)


def week_record(games: list[dict]) -> dict:
    """Top-6 / top-10 / all record for one week's submitted list."""
    out = {}
    for key, n in (("top6", 6), ("top10", 10), ("all", None)):
        g = [x for x in games if x.get("rank") is not None and (n is None or x["rank"] <= n)]
        w = sum(x.get("result") == "hit" for x in g)
        l = sum(x.get("result") == "miss" for x in g)
        p = sum(x.get("result") == "push" for x in g)
        out[key] = {"wins": w, "losses": l, "pushes": p, "pending": len(g) - w - l - p}
    return out


def publish_past_weeks(current_week: str) -> list[str]:
    """site/data/weeks/<week>.json for every finished week: the submitted list
    (last ranking before the Friday deadline) with results, plus index.json."""
    out_dir = SITE_DATA / "weeks"
    out_dir.mkdir(parents=True, exist_ok=True)
    weeks = []
    for d in sorted(RANKINGS.glob("*"), reverse=True):
        if not d.is_dir() or d.name >= current_week:
            continue
        subs = [rk for rk in previous_rankings(d.name)
                if pd.Timestamp(rk["generated_at"]) < submit_lock(d.name)]
        if not subs:
            continue
        p = attach_results(dict(subs[-1]))
        p["status"] = "final"
        p["notes"] = []
        p["games"] = pool_list(p["games"])
        p["week_record"] = week_record(p["games"])
        (out_dir / f"{d.name}.json").write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
        weeks.append(d.name)
    (out_dir / "index.json").write_text(json.dumps(weeks), encoding="utf-8")
    return weeks
