"""Guard against mojibake (UTF-8 text mis-decoded as Windows-1252 and saved
back), which garbled the page's dashes and the pickem parser's '½' once."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOJIBAKE = re.compile("[ÂÃ][\u0080-¿‘-›Œ-Ÿ]|â€")


def test_no_mojibake_in_source_or_site():
    files = [*ROOT.glob("src/**/*.py"), *ROOT.glob("tests/*.py"), *ROOT.glob("site/*.html"),
             *ROOT.glob(".github/workflows/*.yml"), ROOT / "README.md", ROOT / "pyproject.toml"]
    bad = [str(p.relative_to(ROOT)) for p in files
           if p.name != "test_encoding.py" and MOJIBAKE.search(p.read_text(encoding="utf-8"))]
    assert not bad, f"mis-encoded characters in: {bad}"
