"""Build a minimal, validated GitHub Pages artifact without source or raw caches.

Run from any directory:
    python scripts/build_pages.py "$RUNNER_TEMP/pages-site"
"""
from pathlib import Path
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = (
    "index.html", "styles.css", "app.js",
    "history.js", "bse50.js", "star100.js", "industry.js", "valuation-nav.js", "gold.js",
    "data/industry_latest.json", "data/industry_status.json",
    "data/latest.json", "data/status.json",
    "data/us_latest.json", "data/us_status.json",
    "data/gold_latest.json", "data/gold_status.json",
)


def build(destination):
    out = Path(destination).resolve()
    if out == ROOT or ROOT in out.parents or out in ROOT.parents:
        raise ValueError("Publishing must use a separate external staging directory")
    missing = [str(item) for item in PUBLIC if not (ROOT / item).is_file()]
    if missing:
        raise FileNotFoundError("Missing public assets: " + ", ".join(missing))
    if out.exists():
        shutil.rmtree(out)
    # Verify JSON is parseable BEFORE deleting any prior build directory.
    for rel in PUBLIC:
        if rel.endswith(".json"):
            try:
                obj = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            except (UnicodeError, ValueError, OSError) as exc:
                raise ValueError(f"Public JSON is invalid: {rel}") from exc
            if not isinstance(obj, dict):
                raise ValueError(f"Public JSON must contain an object: {rel}")
    for rel in PUBLIC:
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, target)
    (out / ".nojekyll").touch()
    count = sum(p.is_file() for p in out.rglob("*"))
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"Pages bundle: {count} public files, {total:,} bytes; no raw data CSVs, tests or Git history")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_pages.py DESTINATION")
    build(sys.argv[1])
