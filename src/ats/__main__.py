"""CLI entry point: python -m ats <command>.

    fetch nfl --seasons 2012-2026 [--no-pbp] [--force]
    fetch cfb --seasons 2014-2026 [--force]
    odds [--league NFL|CFB|all]
    check
"""
from __future__ import annotations

import argparse
import logging
import sys

import numpy as np
import pandas as pd

from .config import INTERIM
from .weeks import current_season, football_week_start_series

log = logging.getLogger("ats")


def parse_seasons(spec: str) -> list[int]:
    if "-" in spec:
        a, b = (int(x) for x in spec.split("-"))
        return list(range(a, b + 1))
    return [int(x) for x in spec.split(",")]


def _save_interim(df: pd.DataFrame, name: str) -> None:
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(INTERIM / f"{name}.parquet", index=False)
    log.info("wrote %s (%d rows)", INTERIM / f"{name}.parquet", len(df))


def cmd_fetch(args) -> None:
    seasons = parse_seasons(args.seasons)
    frames = []
    if args.league == "nfl":
        from .loaders import nfl
        nfl.load_teams(force=args.force)
        for s in seasons:
            frames.append(nfl.games(s, force=args.force))
            nfl.load_injuries(s, force=args.force)
            if not args.no_pbp:
                nfl.load_pbp(s, force=args.force)
            log.info("NFL %s done", s)
    else:
        from .loaders import cfb
        cfb.load_teams(force=args.force)
        for s in seasons:
            frames.append(cfb.games(s, force=args.force))
            cfb.load_advanced_game_stats(s, force=args.force)
            cfb.load_talent(s, force=args.force)
            cfb.load_returning_production(s, force=args.force)
            log.info("CFB %s done", s)
    _save_interim(pd.concat(frames, ignore_index=True), f"games_{args.league}")


def cmd_odds(args) -> None:
    from .loaders import odds
    leagues = ["NFL", "CFB"] if args.league == "all" else [args.league]
    for lg in leagues:
        df = odds.snapshot(lg)
        n_line = int(df["home_spread"].notna().sum()) if not df.empty else 0
        print(f"{lg}: {len(df)} events, {n_line} with a DraftKings spread")


def _sign_and_mae(g: pd.DataFrame) -> dict:
    d = g.dropna(subset=["margin", "close_home_spread"])
    d = d.astype({"margin": float, "close_home_spread": float})
    if len(d) < 10:
        return {"n": len(d)}
    resid = d["margin"] + d["close_home_spread"]  # >0: home covered
    return {
        "n": len(d),
        "corr(-spread, margin)": round(float(np.corrcoef(-d["close_home_spread"], d["margin"])[0, 1]), 3),
        "mean(margin+spread)": round(float(resid.mean()), 2),
        "market MAE": round(float(resid.abs().mean()), 2),
        "home cover %": round(float(100 * (resid > 0).sum() / (resid != 0).sum()), 1),
    }


def cmd_check(args) -> None:
    ok = True
    for lg in ("nfl", "cfb"):
        p = INTERIM / f"games_{lg}.parquet"
        if not p.exists():
            print(f"\n[{lg.upper()}] no data yet (run: python -m ats fetch {lg})")
            continue
        g = pd.read_parquet(p)
        if lg == "cfb":
            # Market check on FBS-vs-FBS only; FCS games often lack lines.
            g_eval = g[(g["home_classification"] == "fbs") & (g["away_classification"] == "fbs")]
        else:
            g_eval = g
        print(f"\n[{lg.upper()}] games by season "
              f"(final = has score, line = has close; {'FBS v FBS' if lg == 'cfb' else 'all'})")
        summary = g_eval.groupby("season").agg(
            games=("game_id", "size"),
            final=("margin", lambda s: int(s.notna().sum())),
            line=("close_home_spread", lambda s: int(s.notna().sum())),
        )
        summary["missing_line_%"] = (100 * (1 - summary["line"] / summary["games"])).round(1)
        print(summary.to_string())
        if lg == "cfb":
            print("line_source mix:", g_eval["line_source"].value_counts(dropna=False).head(6).to_dict())
        stats = _sign_and_mae(g_eval)
        print("spread sanity:", stats)
        c = stats.get("corr(-spread, margin)")
        if c is not None and c < 0.3:
            ok = False
            print("  !! correlation too low or negative: spread sign convention is likely wrong")
        if "mean(margin+spread)" in stats and abs(stats["mean(margin+spread)"]) > 1.5:
            ok = False
            print("  !! mean(margin+spread) far from 0: lines and scores may be misaligned")

    # Odds snapshot -> canonical games match rate.
    from .loaders import odds
    for lg in ("NFL", "CFB"):
        snap = odds.latest_lines(lg)
        p = INTERIM / f"games_{lg.lower()}.parquet"
        if snap.empty or not p.exists():
            print(f"\n[{lg} odds] no snapshot or games table yet")
            continue
        g = pd.read_parquet(p)
        g = g[g["season"] == current_season()]
        snap = snap.assign(football_week_start=football_week_start_series(snap["commence_time"]))
        m = snap.merge(g[["home", "away", "football_week_start", "game_id"]],
                       on=["home", "away", "football_week_start"], how="left")
        # Neutral-site games can list home/away in opposite order across sources.
        swapped = snap.merge(g[["home", "away", "football_week_start"]].rename(
            columns={"home": "away", "away": "home"}).assign(swapped=True),
            on=["home", "away", "football_week_start"], how="inner")
        unmatched = m[m["game_id"].isna()]
        print(f"\n[{lg} odds] latest snapshot {snap['fetched_at'].max()}: "
              f"{len(m) - len(unmatched)}/{len(m)} events matched to schedule; "
              f"{len(swapped)} more match only with home/away swapped")
        if len(unmatched):
            print(unmatched[["commence_time", "home_team_src", "away_team_src", "home", "away"]]
                  .head(20).to_string(index=False))
    sys.exit(0 if ok else 1)


def cmd_weekly(args) -> None:
    from .weekly import run
    p = run(kind=args.kind, fetch=not args.no_fetch)
    g = pd.DataFrame(p["games"])
    print(f"\n{p['kind']} ranking for week of {p['week_start']} -> {p['path']}")
    for n in p["notes"]:
        print("note:", n)
    if not g.empty:
        cols = ["rank", "league", "pick_team", "pick_line", "pickem_home_spread", "live_home_spread",
                "model_fair_home_spread", "p_cover", "edge", "confidence", "key_reason", "flags"]
        cols = [c for c in cols + ["result"] if c in g]
        print(g[cols].head(25).to_string(index=False, float_format=lambda x: f"{x:.3f}"))


def cmd_grade(args) -> None:
    from .weekly import grade
    new = grade()
    print(f"graded {len(new)} new entries")


def cmd_backtest(args) -> None:
    import warnings
    from .backtest.report import run_all
    warnings.filterwarnings("ignore", category=FutureWarning)
    print(run_all(placebo=not args.no_placebo))


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="ats")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="fetch + cache historical/current data")
    f.add_argument("league", choices=["nfl", "cfb"])
    f.add_argument("--seasons", help="e.g. 2012-2026 or 2024,2025")
    f.add_argument("--no-pbp", action="store_true", help="NFL: skip play-by-play")
    f.add_argument("--force", action="store_true", help="refetch even immutable seasons")
    f.set_defaults(func=cmd_fetch)

    o = sub.add_parser("odds", help="snapshot current DraftKings spreads")
    o.add_argument("--league", choices=["NFL", "CFB", "all"], default="all")
    o.set_defaults(func=cmd_odds)

    c = sub.add_parser("check", help="data sanity report")
    c.set_defaults(func=cmd_check)

    for name, hlp in (("weekly", "Tuesday run: grade last week, refresh, rank, publish"),
                      ("refresh", "daily refresh: new lines, re-rank, lock kicked-off games")):
        w = sub.add_parser(name, help=hlp)
        w.add_argument("--no-fetch", action="store_true", help="use cached data/odds only")
        w.set_defaults(func=cmd_weekly, kind=name)

    gr = sub.add_parser("grade", help="grade logged rankings for finished games")
    gr.set_defaults(func=cmd_grade)

    b = sub.add_parser("backtest", help="walk-forward backtest -> reports/backtest.md")
    b.add_argument("--no-placebo", action="store_true", help="skip the shuffled-score placebo runs")
    b.set_defaults(func=cmd_backtest)

    args = ap.parse_args(argv)
    if args.cmd == "fetch" and not args.seasons:
        start = 2012 if args.league == "nfl" else 2014
        args.seasons = f"{start}-{current_season()}"
    args.func(args)


if __name__ == "__main__":
    main()
