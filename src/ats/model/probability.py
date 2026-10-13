"""Predicted margin -> P(home covers), and per-league calibration.

Convention: line = home spread (negative = home favored). Home covers iff
margin + line > 0; margin + line == 0 is a push (no decision), so all
probabilities here are P(home covers | not a push).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

MIN_EMPIRICAL = 200  # minimum historical games in the line window


def normal_cover_prob(pred_margin, line, sigma):
    return norm.cdf((np.asarray(pred_margin, float) + np.asarray(line, float)) / sigma)


def empirical_cover_prob(pred_margin: np.ndarray, line: np.ndarray,
                         hist_margin: np.ndarray, hist_line: np.ndarray,
                         shape_line: np.ndarray | None = None) -> np.ndarray:
    """NFL key-number-aware probability.

    For a game with line s, take historical games whose line was within a
    small window of s (mirrored, so every game counts from both sides), and
    use their actual margins as the market-implied margin distribution. That
    keeps the clustering at 3, 7, 10... Shift it by the model's disagreement
    delta = pred + s, then P(cover) = P(M + delta > -s | M + delta != -s).
    `shape_line` (default `line`) is the market line whose window supplies
    M; `line` is the line being graded, so a stale pickem line is priced
    against the live market's distribution.
    hist_* must contain only games before the prediction cutoff.
    """
    hm = np.concatenate([hist_margin, -hist_margin]).astype(float)
    hl = np.concatenate([hist_line, -hist_line]).astype(float)
    out = np.empty(len(line))
    line = np.asarray(line, float)
    shape = line if shape_line is None else np.asarray(shape_line, float)
    for i, (pm, g, s) in enumerate(zip(np.asarray(pred_margin, float), line, shape)):
        win = 0.5
        sel = np.abs(hl - s) <= win
        while sel.sum() < MIN_EMPIRICAL and win < 7:
            win += 0.5
            sel = np.abs(hl - s) <= win
        M = hm[sel]                 # margins of games lined near s: centred near -s
        delta = pm + s              # shift so the distribution centres on pm
        x = M + delta + g           # > 0 means home covers the grading line g
        cover, lose = (x > 1e-9).sum(), (x < -1e-9).sum()
        out[i] = cover / (cover + lose) if cover + lose else 0.5
    return out


class LogitCalibrator:
    """Platt-style calibration on logit(p_raw): 2 parameters, stable with a
    few hundred games (isotonic needs far more). Fit only on past OOS rows."""

    def __init__(self):
        self.a, self.b = 1.0, 0.0
        self.fitted = False

    @staticmethod
    def _logit(p):
        p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
        return np.log(p / (1 - p))

    def fit(self, p_raw, y) -> "LogitCalibrator":
        from sklearn.linear_model import LogisticRegression
        x = self._logit(p_raw).reshape(-1, 1)
        lr = LogisticRegression(C=1e6).fit(x, np.asarray(y, int))
        self.a, self.b = float(lr.coef_[0, 0]), float(lr.intercept_[0])
        self.fitted = True
        return self

    def predict(self, p_raw):
        z = self.a * self._logit(p_raw) + self.b
        return 1 / (1 + np.exp(-z))


def outcome(margin: pd.Series, line: pd.Series) -> pd.Series:
    """1 home covered, 0 away covered, NaN push or unplayed."""
    x = margin.astype(float) + line.astype(float)
    return pd.Series(np.where(x > 0, 1.0, np.where(x < 0, 0.0, np.nan)), index=margin.index).where(x.notna())
