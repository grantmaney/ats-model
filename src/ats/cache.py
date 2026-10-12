"""Local raw-data cache: one parquet file plus a JSON manifest per key.

    data/raw/<source>/<key>.parquet
    data/raw/<source>/<key>.json   {source, key, fetched_at, rows, meta}

Rules:
- immutable=True (completed seasons): once written, always served from disk
  unless force=True. Historical data is fetched exactly once.
- immutable=False (current season): refetched when older than ttl_hours.
- Append-only snapshots (live odds) use write_snapshot(), which refuses to
  overwrite an existing file.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

from .config import RAW

log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _paths(source: str, key: str, root: Path) -> tuple[Path, Path]:
    d = root / source
    return d / f"{key}.parquet", d / f"{key}.json"


def read_manifest(source: str, key: str, root: Path = RAW) -> dict | None:
    _, mpath = _paths(source, key, root)
    if not mpath.exists():
        return None
    return json.loads(mpath.read_text(encoding="utf-8"))


def _write(df: pd.DataFrame, source: str, key: str, meta: dict, root: Path) -> None:
    ppath, mpath = _paths(source, key, root)
    ppath.parent.mkdir(parents=True, exist_ok=True)
    tmp = ppath.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(ppath)  # atomic on same volume: no half-written cache files
    manifest = {
        "source": source,
        "key": key,
        "fetched_at": utcnow().isoformat(),
        "rows": int(len(df)),
        "meta": meta,
    }
    mpath.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")


def cached(
    source: str,
    key: str,
    fetch: Callable[[], pd.DataFrame],
    *,
    immutable: bool,
    ttl_hours: float = 12.0,
    force: bool = False,
    meta: dict | None = None,
    root: Path = RAW,
) -> pd.DataFrame:
    ppath, _ = _paths(source, key, root)
    manifest = read_manifest(source, key, root)
    if ppath.exists() and manifest and not force:
        if immutable:
            return pd.read_parquet(ppath)
        age_h = (utcnow() - datetime.fromisoformat(manifest["fetched_at"])).total_seconds() / 3600
        if age_h < ttl_hours:
            return pd.read_parquet(ppath)
    log.info("fetching %s/%s", source, key)
    df = fetch()
    _write(df, source, key, meta or {}, root)
    return df


def write_snapshot(df: pd.DataFrame, source: str, key: str, meta: dict, root: Path = RAW) -> Path:
    """Append-only write. Raises if the snapshot already exists."""
    ppath, _ = _paths(source, key, root)
    if ppath.exists():
        raise FileExistsError(f"snapshot {ppath} already exists; snapshots are append-only")
    _write(df, source, key, meta, root)
    return ppath
