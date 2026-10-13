"""Cover probability is centred on the market line: no gap and no model
weight -> 0.5; a stale grading line the market moved away from -> edge on
the side the market moved toward."""
import numpy as np
import pandas as pd

from ats.backtest import walkforward as W


def _past(league, n=3000, seed=0):
    rng = np.random.default_rng(seed)
    line = rng.choice(np.arange(-14, 14.5, 0.5), n)
    sd = 13.0 if league == "NFL" else 16.0
    margin = np.round(-line + rng.normal(-0.4, sd, n))  # small home/road base-rate offset
    return pd.DataFrame({
        "kickoff_utc": pd.Timestamp("2020-01-01", tz="UTC") + pd.to_timedelta(np.arange(n), "h"),
        "line": line, "margin_f": margin,
        "pred3": -line + rng.normal(0, 1, n),  # model disagreement is pure noise -> w ~ 0
    })


def test_no_gap_is_coin_flip_and_gap_points_the_right_way():
    as_of = pd.Timestamp("2030-01-01", tz="UTC")
    for lg in ("NFL", "CFB"):
        past = _past(lg)
        mkt = np.array([-3.0, -7.0, -4.0, 2.5])
        grade = np.array([-3.0, -7.0, -7.0, 2.5])   # 3rd game: sheet has home -7, market now -4
        p = W.cover_probs(lg, past, -mkt, grade, as_of, market_line=mkt)
        assert p["w_model"][0] < 0.1
        assert np.allclose(p["p_cal"][[0, 1, 3]], 0.5, atol=0.01), (lg, p["p_cal"])
        assert p["p_cal"][2] < 0.45, (lg, p["p_cal"])  # take the road team +7
