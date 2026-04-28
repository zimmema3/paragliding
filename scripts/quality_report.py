"""Diagnostika kvality scrapingu: pro každý enabled zdroj zavolá scraper
a spočítá % vyplněnosti polí (price_eur, year, category, size).

Spustit: .\.venv\Scripts\python scripts\quality_report.py
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bazar_watcher import config, scrapers  # noqa: E402
import requests  # noqa: E402


def pct(n_filled: int, n_total: int) -> str:
    if n_total == 0:
        return "  -"
    return f"{round(n_filled / n_total * 100):>3}%"


def main() -> int:
    scrapers._session = requests.Session()
    scrapers._session.headers.update(scrapers.HEADERS)
    rows = []
    for src in config.SOURCES:
        if not src.get("enabled", True):
            continue
        fn = scrapers._SCRAPERS.get(src["id"])
        if fn is None:
            rows.append((src["id"], 0, 0, 0, 0, 0, "no scraper"))
            continue
        try:
            listings = fn(src)
        except Exception as exc:  # noqa: BLE001
            rows.append((src["id"], 0, 0, 0, 0, 0, f"ERROR: {exc!r}"))
            continue
        n = len(listings)
        if n == 0:
            rows.append((src["id"], 0, 0, 0, 0, 0, "0 listings"))
            continue
        n_price = sum(1 for x in listings if x.get("price_eur") is not None)
        n_year = sum(1 for x in listings if x.get("year") is not None)
        n_cat = sum(1 for x in listings if x.get("category"))
        n_size = sum(1 for x in listings if x.get("size"))
        rows.append((src["id"], n, n_price, n_year, n_cat, n_size, ""))

    print(f"{'source_id':<28} {'n':>4}  {'price':>5}  {'year':>5}  {'cat':>5}  {'size':>5}   note")
    print("-" * 80)
    for sid, n, p, y, c, s, note in rows:
        print(
            f"{sid:<28} {n:>4}   {pct(p, n):>4}   {pct(y, n):>4}   {pct(c, n):>4}   {pct(s, n):>4}   {note}"
        )
    total_n = sum(r[1] for r in rows)
    print("-" * 80)
    print(f"{'TOTAL':<28} {total_n:>4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
