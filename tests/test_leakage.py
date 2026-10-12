"""Look-ahead leakage tests on real cached NFL data (skipped if not fetched).

1. Future scramble: replace every outcome and efficiency stat from a cutoff
   onward with noise; every prediction for weeks up to and including the
   cutoff week must be bit-identical.
2. The fit-level guard raises if handed a game at/after its cutoff.
"""
import numpy as np
import pandas as pd
import pytest

from ats.config import INTERIM
from ats.model import ratings as R

pytestmark = pytest.mark.skipif(not (INTERIM / "games_nfl.parquet").exists(),
                                reason="run `python -m ats fetch nfl` first")


@pytest.fixture(scope="module")
def nfl_small():
    from ats.model import data
    g = data.games("NFL")
    g = g[g["season"] <= 2015].reset_index(drop=True)
    o = data.obs("NFL")
    o = o[o["game_id"].isin(g["game_id"])].reset_index(drop=True)
    return g, o


def test_future_scramble_does_not_change_past_predictions(nfl_small):
    from ats.backtest import walkforward as W
    g, o = nfl_small
    weeks = sorted(g.loc[g["season"] == 2015, "football_week_start"].unique())
    wk = weeks[8]
    cut = W.cutoff(wk)
    a = W.run("NFL", g, o, eval_from=2014)
    g2, o2 = W.scramble_after(g, o, cut)
    b = W.run("NFL", g2, o2, eval_from=2014)
    cols = ["pred2", "pred3", "p2", "p_raw", "p_cal", "sigma"]
    keep = a["football_week_start"] <= wk
    assert keep.sum() > 500
    pd.testing.assert_frame_equal(
        a.loc[keep, ["game_id"] + cols].reset_index(drop=True),
        b.loc[b["football_week_start"] <= wk, ["game_id"] + cols].reset_index(drop=True))
    # sanity: the scramble really did change later predictions
    later_a = a.loc[a["football_week_start"] > wk, "pred3"].to_numpy()
    later_b = b.loc[b["football_week_start"] > wk, "pred3"].to_numpy()
    assert not np.allclose(later_a, later_b, equal_nan=True)


def test_fit_rejects_future_rows(nfl_small):
    g, o = nfl_small
    as_of = o["kickoff_utc"].iloc[100]
    prior = R.Ratings(as_of=pd.NaT, table=pd.DataFrame())
    with pytest.raises(R.LeakageError):
        R.fit(o.iloc[:200], [], as_of, prior, R.PARAMS["NFL"])
