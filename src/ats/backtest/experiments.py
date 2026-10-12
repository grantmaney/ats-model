"""Feature / setting experiments with a development-holdout split.

Decision rule (fixed before running anything):
  ADOPT a change only if, versus the baseline,
    1. development ratings-model MAE (m2) improves by >= 0.02 points, and
    2. development Brier (calibrated) does not get worse, and
    3. holdout m2 MAE does not get worse.
  Hit rates are reported but never used to decide: they are too noisy.

Development = NFL 2015-2021, CFB 2016-2021. Holdout = 2022 onward.

    python -m ats experiments
"""
from __future__ import annotations

import time
import warnings
from dataclasses import replace

import pandas as pd

from ..config import ROOT
from ..model import data, features as F, ratings as R
from . import metrics as M
from . import walkforward as W

HOLDOUT_FROM = 2022
MIN_MAE_GAIN = 0.02


def _split_metrics(df: pd.DataFrame) -> dict:
    out = {}
    for name, part in (("dev", df[df["eval"] & (df["season"] < HOLDOUT_FROM)]),
                       ("hold", df[df["season"] >= HOLDOUT_FROM])):
        mae = M.margin_mae(part)
        d = M.picks(part, "p_cal")
        out[name] = {
            "n": mae["n"], "mae_mkt": mae["market"], "mae_m2": mae["ratings (m2)"], "mae_m3": mae["blend (m3)"],
            "brier": M.brier(part, "p_cal")["brier"],
            "top5": M.hit_summary(M.top_n(d, 5)["hit"])["hit_rate"],
            "top10": M.hit_summary(M.top_n(d, 10)["hit"])["hit_rate"],
            "w_model": float(part["m3_w_model"].mean()),
        }
    return out


def _decide(base: dict, x: dict) -> str:
    gain = base["dev"]["mae_m2"] - x["dev"]["mae_m2"]
    ok = (gain >= MIN_MAE_GAIN and x["dev"]["brier"] <= base["dev"]["brier"] + 1e-5
          and x["hold"]["mae_m2"] <= base["hold"]["mae_m2"] + 1e-9)
    return "ADOPT" if ok else "reject"


def experiments() -> list[tuple]:
    """(league, name, kwargs) — kwargs: params, wp, extra, features."""
    base_nfl, base_cfb = R.PARAMS["NFL"], R.PARAMS["CFB"]
    out = [("NFL", "baseline", {})]
    out += [("NFL", "garbage-time filter wp 0.05-0.95", {"wp": (0.05, 0.95)}),
            ("NFL", "garbage-time filter wp 0.10-0.90", {"wp": (0.10, 0.90)}),
            ("NFL", "prior strength 2 games", {"params": replace(base_nfl, lam=2.0)}),
            ("NFL", "prior strength 8 games", {"params": replace(base_nfl, lam=8.0)}),
            ("NFL", "recency half-life 5 wks", {"params": replace(base_nfl, half_life_weeks=5.0)}),
            ("NFL", "recency half-life 20 wks", {"params": replace(base_nfl, half_life_weeks=20.0)}),
            ("NFL", "starting QB Out/Doubtful", {"extra": "qb", "features": W.FEATURES + ["qb_out_diff"]})]
    out += [("CFB", "baseline", {}),
            ("CFB", "prior strength 1.5 games", {"params": replace(base_cfb, lam=1.5)}),
            ("CFB", "prior strength 6 games", {"params": replace(base_cfb, lam=6.0)}),
            ("CFB", "recency half-life 5 wks", {"params": replace(base_cfb, half_life_weeks=5.0)}),
            ("CFB", "recency half-life 20 wks", {"params": replace(base_cfb, half_life_weeks=20.0)}),
            ("CFB", "holdover: last year's top 10, first game", {"extra": "holdover",
                                                                "features": W.FEATURES + ["holdover_diff"]})]
    return out


def run_one(league: str, kw: dict) -> pd.DataFrame:
    g = data.games(league)
    o = data.obs(league, kw.get("wp")) if league == "NFL" else data.obs(league)
    extra = None
    if kw.get("extra") == "qb":
        extra = F.nfl_qb_out(g)
    elif kw.get("extra") == "holdover":
        extra = F.cfb_holdover(g)
    frame = W.build_frame(league, g, o, params=kw.get("params"), extra=extra)
    return W.run(league, g, o, frame=frame, features=kw.get("features"))


def main() -> str:
    warnings.filterwarnings("ignore")
    rows, base = [], {}
    for league, name, kw in experiments():
        t = time.time()
        m = _split_metrics(run_one(league, kw))
        if name == "baseline":
            base[league] = m
        verdict = "-" if name == "baseline" else _decide(base[league], m)
        rows.append((league, name, m, verdict, time.time() - t))
        print(f"{league:3} {name:42} dev m2 {m['dev']['mae_m2']:.3f} brier {m['dev']['brier']:.4f} "
              f"| hold m2 {m['hold']['mae_m2']:.3f} -> {verdict}", flush=True)

    L = ["# Experiments: development vs holdout", "",
         __doc__.split("    python")[0].strip(), "",
         "| League | Change | Dev m2 MAE | Dev m3 MAE | Dev Brier | Dev top-5 | Hold m2 MAE | Hold m3 MAE | Hold Brier | Hold top-5 | Verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for lg, name, m, v, _ in rows:
        d, h = m["dev"], m["hold"]
        L.append(f"| {lg} | {name} | {d['mae_m2']:.3f} | {d['mae_m3']:.3f} | {d['brier']:.4f} | {100*d['top5']:.1f}% | "
                 f"{h['mae_m2']:.3f} | {h['mae_m3']:.3f} | {h['brier']:.4f} | {100*h['top5']:.1f}% | {v} |")
    L += ["", "Market MAE for reference: " + "; ".join(
        f"{lg} dev {base[lg]['dev']['mae_mkt']:.3f}, holdout {base[lg]['hold']['mae_mkt']:.3f}" for lg in base)]
    text = "\n".join(L) + "\n"
    (ROOT / "reports" / "experiments.md").write_text(text, encoding="utf-8")
    return text
