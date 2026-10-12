"""Evaluation metrics for walk-forward predictions."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import binomtest

BREAKEVEN = 0.5238  # -110 juice


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def hit_summary(hits: pd.Series) -> dict:
    h = hits.dropna()
    n, k = len(h), int(h.sum())
    lo, hi = wilson(k, n)
    return {"n": n, "wins": k, "hit_rate": k / n if n else np.nan, "ci_lo": lo, "ci_hi": hi,
            "p_vs_50": binomtest(k, n, 0.5).pvalue if n else np.nan}


def picks(df: pd.DataFrame, p_col: str) -> pd.DataFrame:
    """Turn P(home covers) into a pick per game: side, edge, and hit."""
    d = df[df[p_col].notna()].copy()
    d["p_pick"] = np.maximum(d[p_col], 1 - d[p_col])
    d["edge"] = d["p_pick"] - 0.5
    d["pick_home"] = d[p_col] >= 0.5
    d["hit"] = np.where(d["y"].isna(), np.nan, (d["pick_home"] == (d["y"] == 1)).astype(float))
    return d


def top_n(d: pd.DataFrame, n: int | None) -> pd.DataFrame:
    """Top-n picks by edge within each football week (n=None: all games)."""
    d = d.sort_values("edge", ascending=False)
    return d if n is None else d.groupby("football_week_start", group_keys=False).head(n)


def margin_mae(df: pd.DataFrame) -> dict:
    d = df[df["margin_f"].notna() & df["line"].notna() & df["pred3"].notna()]
    return {
        "n": len(d),
        "market": float((d["margin_f"] + d["line"]).abs().mean()),
        "ratings (m2)": float((d["margin_f"] - d["pred2"]).abs().mean()),
        "blend (m3)": float((d["margin_f"] - d["pred3"]).abs().mean()),
    }


def brier(df: pd.DataFrame, p_col: str) -> dict:
    d = df[df[p_col].notna() & df["y"].notna()]
    b = float(((d[p_col] - d["y"]) ** 2).mean())
    return {"n": len(d), "brier": b, "coin_flip": 0.25, "skill_vs_coin": 1 - b / 0.25}


def calibration_table(df: pd.DataFrame, p_col: str, bins=(0, .40, .45, .48, .50, .52, .55, .60, 1)) -> pd.DataFrame:
    d = df[df[p_col].notna() & df["y"].notna()].copy()
    d["bin"] = pd.cut(d[p_col], bins, include_lowest=True)
    t = d.groupby("bin", observed=True).agg(n=("y", "size"), mean_pred=(p_col, "mean"), observed=("y", "mean"))
    return t


def by_edge(d: pd.DataFrame, edges=(0, .01, .02, .03, .05, 1)) -> pd.DataFrame:
    x = d[d["hit"].notna()].copy()
    x["edge_bin"] = pd.cut(x["edge"], edges, include_lowest=True)
    rows = []
    for b, grp in x.groupby("edge_bin", observed=True):
        s = hit_summary(grp["hit"])
        rows.append({"edge": str(b), **s})
    return pd.DataFrame(rows)


def clv(d: pd.DataFrame) -> dict:
    """Closing-line value for picks made at the open: points the line moved
    toward our side (positive = market agreed with us after we picked)."""
    x = d.dropna(subset=["open_home_spread", "close_home_spread"]).copy()
    o, c = x["open_home_spread"].astype(float), x["close_home_spread"].astype(float)
    move = np.where(x["pick_home"], o - c, c - o)
    return {"n": len(x), "mean_pts": float(np.mean(move)) if len(x) else np.nan,
            "pct_toward": float(np.mean(move > 0)) if len(x) else np.nan,
            "pct_away": float(np.mean(move < 0)) if len(x) else np.nan}
