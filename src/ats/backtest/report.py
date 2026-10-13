"""Run every backtest configuration and write reports/backtest.md.

Configurations:
  NFL vs closing line; CFB vs closing line; CFB vs opening line (2023+,
  the only seasons CFBD has DraftKings openers); CFB stale line (model sees
  the close, picks graded against the opener: the pickem-sheet situation);
  combined NFL+CFB at close.
Placebo runs (scores shuffled within season) for NFL-close and CFB-open.
Predictions are saved to data/backtest/ for inspection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..config import DATA, ROOT
from ..model import data
from . import metrics as M
from . import walkforward as W

log = logging.getLogger(__name__)
OUT = DATA / "backtest"
REPORTS = ROOT / "reports"
INK, INK2, SERIES, SURFACE, GRID = "#0b0b0b", "#52514e", "#2a78d6", "#fcfcfb", "#e4e3df"


def _fmt_hit(s: dict) -> str:
    if not s["n"]:
        return "n/a"
    return (f"{s['wins']}-{s['n'] - s['wins']} ({100 * s['hit_rate']:.1f}%, "
            f"95% CI {100 * s['ci_lo']:.1f}-{100 * s['ci_hi']:.1f}, p={s['p_vs_50']:.2f})")


def _section(name: str, df: pd.DataFrame, with_clv: bool = False) -> tuple[list[str], pd.DataFrame]:
    e = df[df["eval"]]
    s_used = e.loc[e["pred3"].notna() & e["line"].notna(), "season"]
    seasons = f"{int(s_used.min())}-{int(s_used.max())}" + (" (2026 partial)" if s_used.max() >= 2026 else "")
    mae = M.margin_mae(e)
    b_cal, b_m2 = M.brier(e, "p_cal"), M.brier(e, "p2")
    d = M.picks(e, "p_cal")
    w = e[["m3_w_mkt", "m3_w_model"]].dropna()
    L = [f"## {name}", "",
         f"Evaluated seasons {seasons}; {mae['n']} games with a line and a final score.", "",
         "**Margin MAE (points, lower is better)**", "",
         "| Market line | Ratings only (m2) | Blend (m3) |", "|---|---|---|",
         f"| {mae['market']:.2f} | {mae['ratings (m2)']:.2f} | {mae['blend (m3)']:.2f} |", "",
         f"Blend weights (first -> last week): market {w['m3_w_mkt'].iloc[0]:.2f} -> {w['m3_w_mkt'].iloc[-1]:.2f}, "
         f"ratings model {w['m3_w_model'].iloc[0]:.2f} -> {w['m3_w_model'].iloc[-1]:.2f}. "
         f"sigma (blend residual SD) averaged {e['sigma'].mean():.1f} pts.", "",
         f"**Brier score** (coin flip = 0.2500): calibrated blend {b_cal['brier']:.4f}; "
         f"ratings-only {b_m2['brier']:.4f}.", "",
         "**ATS hit rate of top-N picks per week** (pushes excluded)", "",
         "| Picks | Record |", "|---|---|"]
    for n in (5, 6, 10, None):
        L.append(f"| {'All games' if n is None else f'Top {n}'} | {_fmt_hit(M.hit_summary(M.top_n(d, n)['hit']))} |")
    w_used = e["w_model"].dropna()
    if len(w_used):
        L += ["", f"Model weight w (share of the model's disagreement with the market that is used): "
              f"first {w_used.iloc[0]:.2f}, last {w_used.iloc[-1]:.2f}, mean {w_used.mean():.2f}."]
    if with_clv:
        L += ["", "**Closing-line value of picks made at the open** (points the line moved toward our side)", "",
              "| Picks | n | Mean move | % toward us | % away |", "|---|---|---|---|---|"]
        for n in (5, 10, None):
            c = M.clv(M.top_n(d, n))
            L.append(f"| {'All' if n is None else f'Top {n}'} | {c['n']} | {c['mean_pts']:+.2f} | "
                     f"{100 * c['pct_toward']:.0f}% | {100 * c['pct_away']:.0f}% |")
        big = (d["close_home_spread"] - d["open_home_spread"]).abs().astype(float) > 7
        L += ["", f"Robustness: excluding games whose line moved >7 pts open->close (likely stale or "
              f"erroneous openers), top 5 = {_fmt_hit(M.hit_summary(M.top_n(d[~big], 5)['hit']))}."]
    eb = M.by_edge(d)
    L += ["", "**Hit rate by calibrated edge** (all games)", "",
          "| Edge | n | Hit rate | 95% CI |", "|---|---|---|---|"]
    for _, r in eb.iterrows():
        L.append(f"| {r['edge']} | {r['n']} | {100 * r['hit_rate']:.1f}% | {100 * r['ci_lo']:.1f}-{100 * r['ci_hi']:.1f} |")
    ct = M.calibration_table(e, "p_cal")
    L += ["", "**Calibration of P(home covers)**", "", "| Bin | n | Mean predicted | Observed |", "|---|---|---|---|"]
    for b, r in ct.iterrows():
        L.append(f"| {b} | {r['n']} | {r['mean_pred']:.3f} | {r['observed']:.3f} |")
    L.append("")
    return L, ct


def _placebo_line(name: str, df: pd.DataFrame) -> str:
    d = M.picks(df[df["eval"]], "p_cal")
    return (f"| {name} | {_fmt_hit(M.hit_summary(M.top_n(d, 5)['hit']))} | "
            f"{_fmt_hit(M.hit_summary(M.top_n(d, 10)['hit']))} |")


def _chart(cts: dict[str, pd.DataFrame], path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(cts), figsize=(4.2 * len(cts), 4.2), facecolor=SURFACE)
    for ax, (name, ct) in zip(np.atleast_1d(axes), cts.items()):
        ax.set_facecolor(SURFACE)
        ax.plot([0.3, 0.7], [0.3, 0.7], color=INK2, lw=1, ls="--", zorder=1)
        ax.scatter(ct["mean_pred"], ct["observed"], s=20 + 180 * ct["n"] / ct["n"].max(),
                   color=SERIES, edgecolor=SURFACE, linewidth=2, zorder=2)
        ax.set_xlim(0.3, 0.7); ax.set_ylim(0.3, 0.7)
        ax.set_title(name, color=INK, fontsize=11, loc="left")
        ax.set_xlabel("Predicted P(home covers)", color=INK2, fontsize=9)
        ax.set_ylabel("Observed home cover rate", color=INK2, fontsize=9)
        ax.tick_params(colors=INK2, labelsize=8)
        ax.grid(color=GRID, lw=0.6)
        for s in ax.spines.values():
            s.set_visible(False)
    fig.suptitle("Calibration (dot size = games in bin; dashed = perfect)", color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def run_all(placebo: bool = True) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    runs = {}
    gn, on = data.games("NFL"), data.obs("NFL")
    runs["NFL close"] = W.run("NFL", gn, on)
    gc, oc = data.games("CFB"), data.obs("CFB")
    frame_c = W.build_frame("CFB", gc, oc)
    runs["CFB close"] = W.run("CFB", gc, oc, frame=frame_c)
    runs["CFB open"] = W.run("CFB", gc, oc, line_col="open_home_spread", frame=frame_c)
    runs["CFB stale"] = W.run("CFB", gc, oc, line_col="close_home_spread", grade_col="open_home_spread",
                              frame=frame_c)
    for k, v in runs.items():
        v.to_parquet(OUT / f"{k.replace(' ', '_').lower()}.parquet", index=False)
    # Small committed tables the weekly run uses for Low/Medium/High confidence.
    for lg in ("NFL", "CFB"):
        bt = runs[f"{lg} close"]
        M.by_edge(M.picks(bt[bt["eval"]], "p_cal")).to_csv(REPORTS / f"edge_table_{lg.lower()}.csv", index=False)
    # Picks graded against a stale (pickem) line: confidence comes from this.
    st = runs["CFB stale"]
    M.by_edge(M.picks(st[st["eval"] & st["y"].notna()], "p_cal")).to_csv(REPORTS / "edge_table_stale.csv",
                                                                          index=False)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = ["# Walk-forward backtest", "", f"Generated {now}. Regenerate with `python -m ats backtest`.", "",
         "Every prediction uses only games that kicked off before that week's Tuesday 00:00 PT cutoff. "
         "Ratings, model fits, sigma, the NFL empirical margin distribution and calibration are all refit "
         "each week on past data only. Hyperparameters (prior strength, decay, ridge alpha) were fixed "
         "before running and not tuned on these results.", "",
         "Break-even at -110 is 52.4%. A hit rate whose CI includes 50% is not distinguishable from a coin flip.", ""]
    cts = {}
    titles = {"NFL close": "NFL vs closing line", "CFB close": "CFB (FBS v FBS) vs closing line",
              "CFB open": "CFB (FBS v FBS) vs opening line",
              "CFB stale": "CFB stale line: model sees the close, graded against the opener"}
    for name, with_clv in (("NFL close", False), ("CFB close", False), ("CFB open", True), ("CFB stale", False)):
        sec, ct = _section(titles[name], runs[name], with_clv)
        if name == "CFB stale":
            sec[1:1] = ["", "Stand-in for the pickem sheet: a fixed line set early in the week, while the model "
                        "sees a later market line. This is optimistic, because the close is the latest possible "
                        "line and the live line at Friday's deadline has moved less. Only seasons with openers "
                        "(2023+) are graded."]
        L += sec
        if name != "CFB stale":
            cts[name] = ct

    # Combined ranking at the close, per CLAUDE.md: calibrated edge across leagues.
    comb = pd.concat([M.picks(runs[k][runs[k]["eval"]], "p_cal").assign(lg=k.split()[0])
                      for k in ("NFL close", "CFB close")])
    comb = comb[comb["season"] >= 2016]
    L += ["## Combined NFL + CFB ranking vs closing line (2016+)", "", "| Picks | Record |", "|---|---|"]
    for n in (5, 10):
        t = M.top_n(comb, n)
        L.append(f"| Top {n} | {_fmt_hit(M.hit_summary(t['hit']))}; "
                 f"{100 * (t['lg'] == 'CFB').mean():.0f}% CFB |")
    L.append("")

    if placebo:
        L += ["## Placebo check (market right by construction)", "",
              "Same pipeline on synthetic outcomes: margin = -line + a residual shuffled across games within "
              "each season, and efficiency stats shuffled too. The line is unbiased and outcomes carry no "
              "game-specific signal, so anything far from 50% here would mean the pipeline manufactures edge.", "",
              "| Run | Top 5 | Top 10 |", "|---|---|---|"]
        g2, o2 = W.placebo(gn, on, seed=1)
        L.append(_placebo_line("NFL close (placebo)", W.run("NFL", g2, o2)))
        g2, o2 = W.placebo(gc, oc, line_col="open_home_spread", seed=1)
        L.append(_placebo_line("CFB open (placebo)", W.run("CFB", g2, o2, line_col="open_home_spread")))
        L.append("")

    _chart(cts, REPORTS / "calibration.png")
    L += ["![Calibration](calibration.png)", ""]
    text = "\n".join(L)
    (REPORTS / "backtest.md").write_text(text, encoding="utf-8")
    return text
