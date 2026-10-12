"""Opponent-adjusted efficiency ratings with preseason shrinkage.

For each metric m in (epa, sr, pts) and each (game, offense) row r:

    y_r = mu + eta * h_r + O[off_r] - D[def_r] + noise

O = offensive rating, D = defensive rating (positive = good defense),
h = +1 offense at home, -1 away, 0 neutral. Fit by weighted least squares
with a ridge penalty toward a preseason prior:

    min  sum_r w_r (y_r - yhat_r)^2 + lam * sum_i [(O_i - O0_i)^2 + (D_i - D0_i)^2]

`lam` is in units of games: with n games a team's rating is roughly
(n * data + lam * prior) / (n + lam), so shrinkage is strong in week 1 and
fades as the season goes on. w_r decays with age (half-life in weeks).

Leakage guard: fit() asserts every observation kicked off before `as_of`.
Priors for season S come only from seasons < S.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.linalg import cho_factor, cho_solve

from ..config import WEEK_TZ
from .data import NFL_FRANCHISE, cfb_priors_inputs

METRICS = ("epa", "sr", "pts")


class LeakageError(AssertionError):
    pass


@dataclass
class Params:
    lam: float            # prior strength, in games
    half_life_weeks: float
    default_carry: float  # prior = carry * last season final, until enough seasons to fit it
    min_prior_pairs: int = 2


PARAMS = {
    "NFL": Params(lam=4.0, half_life_weeks=10.0, default_carry=0.6),
    "CFB": Params(lam=3.0, half_life_weeks=10.0, default_carry=0.7),
}


@dataclass
class Ratings:
    """Ratings for every team as of one cutoff."""
    as_of: pd.Timestamp
    table: pd.DataFrame                  # index team; cols O_<m>, D_<m>
    mu: dict = field(default_factory=dict)
    eta: dict = field(default_factory=dict)


def fit(obs: pd.DataFrame, teams: list[str], as_of: pd.Timestamp, prior: Ratings,
        p: Params) -> Ratings:
    """Fit all metrics on `obs` (rows strictly before `as_of`)."""
    if len(obs) and obs["kickoff_utc"].max() >= as_of:
        raise LeakageError(f"observation at {obs['kickoff_utc'].max()} is not before as_of={as_of}")
    teams = sorted(set(teams) | set(obs["off"]) | set(obs["def"]))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    out = pd.DataFrame(index=pd.Index(teams, name="team"))
    mu, eta = {}, {}

    if len(obs):
        # Sparse design, columns [mu, eta, O_1..O_n, D_1..D_n]; 4 nonzeros per
        # row. Solved via normal equations (p x p, p = 2n+2), shared by all metrics.
        k = len(obs)
        age_w = (as_of - obs["kickoff_utc"]).dt.total_seconds().to_numpy() / (7 * 86400)
        w = 0.5 ** (age_w / p.half_life_weeks)
        r = np.repeat(np.arange(k), 4)
        c = np.column_stack([np.zeros(k, int), np.ones(k, int), 2 + obs["off"].map(idx).to_numpy(),
                             2 + n + obs["def"].map(idx).to_numpy()]).ravel()
        v = np.column_stack([np.ones(k), obs["h"].to_numpy(float), np.ones(k), -np.ones(k)]).ravel()
        X = sparse.csr_matrix((v, (r, c)), shape=(k, 2 + 2 * n))
        Xw = X.multiply(w[:, None]).tocsr()
        # weak unit anchors on mu/eta keep them defined with very few games
        A = (X.T @ Xw).toarray() + np.diag(np.r_[1.0, 1.0, np.full(2 * n, p.lam)])
        chol = cho_factor(A)  # A is symmetric positive definite (ridge-penalized)
    for m in METRICS:
        O0 = prior.table.reindex(teams)[f"O_{m}"].fillna(0.0).to_numpy() if len(prior.table) else np.zeros(n)
        D0 = prior.table.reindex(teams)[f"D_{m}"].fillna(0.0).to_numpy() if len(prior.table) else np.zeros(n)
        mu0, eta0 = prior.mu.get(m, 0.0), prior.eta.get(m, 0.0)
        if len(obs) == 0:
            out[f"O_{m}"], out[f"D_{m}"] = O0, D0
            mu[m], eta[m] = mu0, eta0
            continue
        b = Xw.T @ obs[m].to_numpy(float) + np.r_[mu0, eta0, p.lam * O0, p.lam * D0]
        beta = cho_solve(chol, b)
        mu[m], eta[m] = float(beta[0]), float(beta[1])
        out[f"O_{m}"], out[f"D_{m}"] = beta[2:2 + n], beta[2 + n:]
    return Ratings(as_of=as_of, table=out, mu=mu, eta=eta)


def _prior_design(league: str, season: int, prev: pd.DataFrame | None, teams: list[str],
                  nonfbs: set[str]) -> pd.DataFrame:
    d = pd.DataFrame(index=pd.Index(teams, name="team"))
    for m in METRICS:
        for side in ("O", "D"):
            col = f"{side}_{m}"
            d[f"prev_{col}"] = prev[col].reindex(teams).fillna(0.0) if prev is not None else 0.0
    d["has_prev"] = prev.reindex(teams).iloc[:, 0].notna().astype(float) if prev is not None else 0.0
    if league == "CFB":
        extra = cfb_priors_inputs(season).set_index("team")
        d["ret_z"] = extra["ret_z"].reindex(teams).fillna(0.0)
        d["talent_z"] = extra["talent_z"].reindex(teams).fillna(0.0)
        d["nonfbs"] = [1.0 if t in nonfbs else 0.0 for t in teams]
    return d


class PriorModel:
    """Maps last season's final ratings (+ CFB preseason info) to this
    season's prior. Coefficients are refit each season on season pairs that
    are entirely in the past."""

    def __init__(self, league: str, p: Params):
        self.league, self.p = league, p
        self.history: list[tuple[pd.DataFrame, pd.DataFrame]] = []  # (design, final)

    def prior(self, season: int, prev_final: Ratings | None, teams: list[str],
              nonfbs: set[str]) -> tuple[Ratings, pd.DataFrame]:
        prev_tbl = None
        if prev_final is not None:
            prev_tbl = prev_final.table.copy()
            if self.league == "NFL":
                prev_tbl.index = [NFL_FRANCHISE.get(t, t) for t in prev_tbl.index]
        design = _prior_design(self.league, season, prev_tbl, teams, nonfbs)
        out = pd.DataFrame(index=design.index)
        for m in METRICS:
            for side in ("O", "D"):
                col = f"{side}_{m}"
                feats = [f"prev_{col}", "has_prev"] + (["ret_z", "talent_z", "nonfbs"]
                                                       if self.league == "CFB" else [])
                if len(self.history) >= self.p.min_prior_pairs:
                    Xh = pd.concat([h[0][feats] for h in self.history])
                    yh = pd.concat([h[1][col].reindex(h[0].index) for h in self.history])
                    keep = yh.notna()
                    A = np.column_stack([np.ones(keep.sum()), Xh[keep].to_numpy()])
                    coef, *_ = np.linalg.lstsq(A, yh[keep].to_numpy(), rcond=None)
                    out[col] = np.column_stack([np.ones(len(design)), design[feats].to_numpy()]) @ coef
                else:
                    out[col] = self.p.default_carry * design[f"prev_{col}"]
        mu = prev_final.mu if prev_final is not None else {}
        eta = prev_final.eta if prev_final is not None else {}
        return Ratings(as_of=pd.NaT, table=out, mu=dict(mu), eta=dict(eta)), design

    def record(self, design: pd.DataFrame, final: Ratings) -> None:
        self.history.append((design, final.table))


def pregame_ratings(league: str, obs: pd.DataFrame, games: pd.DataFrame,
                    p: Params | None = None) -> pd.DataFrame:
    """Walk forward through every football week; for each game return the
    ratings of both teams as fit on games before that week's Tuesday.
    Also returns end-of-season ratings for the next season's prior."""
    p = p or PARAMS[league]
    pm = PriorModel(league, p)
    prev_final: Ratings | None = None
    rows = []
    for season in sorted(games["season"].unique()):
        gs = games[games["season"] == season]
        os_ = obs[obs["season"] == season]
        rated = sorted(set(os_["off"]) | set(os_["def"]))
        if league == "CFB":
            # Rate every team that has efficiency data this season.
            cls = pd.concat([gs[["home", "home_classification"]].set_axis(["t", "c"], axis=1),
                             gs[["away", "away_classification"]].set_axis(["t", "c"], axis=1)])
            nonfbs = set(cls.loc[cls["c"] != "fbs", "t"]) - set(cls.loc[cls["c"] == "fbs", "t"])
        else:
            rated = sorted(set(rated) | set(gs["home"]) | set(gs["away"]))
            nonfbs = set()
        prior, design = pm.prior(season, prev_final, rated, nonfbs)
        for wk in sorted(gs["football_week_start"].unique()):
            # Week boundary is Tuesday 00:00 Pacific (Monday-night games belong to the prior week).
            as_of = pd.Timestamp(wk).tz_localize(WEEK_TZ).tz_convert("UTC")
            r = fit(os_[os_["kickoff_utc"] < as_of], rated, as_of, prior, p)
            gw = gs[gs["football_week_start"] == wk]
            rows.append(_game_features(gw, r))
        end = pd.Timestamp(gs["kickoff_utc"].max()) + pd.Timedelta(days=1)
        final = fit(os_, rated, end, prior, p)
        pm.record(design, final)
        prev_final = final
    return pd.concat(rows, ignore_index=True)


def _game_features(gw: pd.DataFrame, r: Ratings) -> pd.DataFrame:
    t = r.table
    h = t.reindex(gw["home"].to_numpy())
    a = t.reindex(gw["away"].to_numpy())
    f = pd.DataFrame({"game_id": gw["game_id"].to_numpy(),
                      "ratings_as_of": r.as_of})
    for m in METRICS:
        # Expected home-offense advantage minus away-offense advantage.
        f[f"{m}_diff"] = ((h[f"O_{m}"].to_numpy() - a[f"D_{m}"].to_numpy())
                          - (a[f"O_{m}"].to_numpy() - h[f"D_{m}"].to_numpy()))
    f["hfa_pts_est"] = r.eta.get("pts", np.nan)
    return f
