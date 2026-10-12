"""Paths, environment and API-key handling.

Keys are read from the process environment, with a local .env as fallback
(GitHub Actions will inject them as secrets). A missing key only raises when
the loader that needs it is actually called, so NFL work never needs keys.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PICKEM = DATA / "pickem"

load_dotenv(ROOT / ".env", override=False)

# Football weeks (Tue-Mon) are evaluated in this timezone, so a Monday-night
# kickoff at 5:15pm PT stays in its week even though it is Tuesday in UTC.
WEEK_TZ = "America/Los_Angeles"


class MissingKeyError(RuntimeError):
    pass


def get_key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingKeyError(
            f"{name} is not set. Add it to {ROOT / '.env'} (local) or as a "
            f"repository secret (CI)."
        )
    return value
