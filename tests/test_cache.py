import pandas as pd
import pytest

from ats.cache import cached, write_snapshot


def test_immutable_never_refetches(tmp_path):
    calls = []

    def fetch():
        calls.append(1)
        return pd.DataFrame({"x": [len(calls)]})

    a = cached("s", "k", fetch, immutable=True, root=tmp_path)
    b = cached("s", "k", fetch, immutable=True, root=tmp_path)
    assert len(calls) == 1 and b["x"].iloc[0] == a["x"].iloc[0]
    cached("s", "k", fetch, immutable=True, force=True, root=tmp_path)
    assert len(calls) == 2


def test_ttl_expiry_refetches(tmp_path):
    calls = []

    def fetch():
        calls.append(1)
        return pd.DataFrame({"x": [1]})

    cached("s", "k", fetch, immutable=False, ttl_hours=0, root=tmp_path)
    cached("s", "k", fetch, immutable=False, ttl_hours=0, root=tmp_path)
    assert len(calls) == 2


def test_snapshot_is_append_only(tmp_path):
    df = pd.DataFrame({"x": [1]})
    write_snapshot(df, "odds", "20250101T000000Z", {}, root=tmp_path)
    with pytest.raises(FileExistsError):
        write_snapshot(df, "odds", "20250101T000000Z", {}, root=tmp_path)
