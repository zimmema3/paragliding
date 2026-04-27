# -*- coding: utf-8 -*-
"""
Hlavní orchestrátor bazar_watcher.

Spuštění (z adresáře paraglide/):
  python -m bazar_watcher.run

Volby:
  --dry-run       Výpis co by odeslal emailem, bez odeslání
  --no-notify     Přeskoč email (jen scraping + uložení)
  --force-notify  Pošli email i když nejsou nová matching křídla (test)
  --filter-only   Jen zobraz filtrované z existujících dat, bez scrapování

Pipeline:
  1. Scrape všech zdrojů
  2. Storage filter  → ulož EN A + celý EN B do CSV
  3. find_new        → jen dosud neviděné URL
  4. Profile filter  → per-profil matching pro email
  5. save()          → aktualizuj CSV + Excel (listy per profil)
  6. send_alerts()   → email(y)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bazar_watcher import config, scrapers, storage, notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(description="Paragliding Bazar Watcher")
    p.add_argument("--dry-run",      action="store_true")
    p.add_argument("--no-notify",    action="store_true")
    p.add_argument("--force-notify", action="store_true")
    p.add_argument("--filter-only",  action="store_true")
    return p.parse_args()


def _print_profile_results(profile_matches: dict):
    any_found = any(listings for _, listings in profile_matches.values())
    if not any_found:
        print("\n  Zadne nove matching inzeraty pro zadny profil.")
        return

    for pname, (prof, listings) in profile_matches.items():
        if not listings:
            continue
        print(f"\n>>> [{pname}] - {len(listings)} novych:")
        print("-" * 60)
        for lst in listings:
            price_s = f"{float(lst['price_eur']):.0f} EUR" if lst.get("price_eur") else "-"
            print(f"  [{lst.get('country')}] {lst.get('source_name')}")
            print(f"  {lst.get('title','')[:100]}")
            print(f"  {price_s}  rok {lst.get('year','?')}  kat {lst.get('category','?')}  vel {lst.get('size','?')}")
            print(f"  {lst.get('url','')}")
            print()


def main():
    args = parse_args()

    # Zajisti UTF-8 vystup i na Windows cp1250 konzoli
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("\n" + "=" * 60)
    print("  [*]  Paragliding Bazar Watcher")
    print("=" * 60 + "\n")

    # ── 1. Načti existující data ──────────────────────────────────────────
    existing = storage.load_existing()
    logger.info("Existující záznamy: %d", len(existing))

    if args.filter_only:
        all_listings = existing.to_dict(orient="records")
        print("\n── Alert profily (z existujících dat) ──────────────────")
        for prof in config.ALERT_PROFILES:
            matched = storage.apply_profile_filter(all_listings, prof)
            print(f"  [{prof['name']}] → {len(matched)} inzerátů splňuje kritéria")
        return

    # ── 2. Scraper ────────────────────────────────────────────────────────
    logger.info("Spouštím scrapery ...")
    all_scraped = scrapers.scrape_all()
    logger.info("Celkem scraped: %d inzerátů", len(all_scraped))

    # ── 3. Storage filter (mid-B a níže) ──────────────────────────────────
    storage_filtered = storage.apply_storage_filter(all_scraped)
    logger.info("Po storage filtru (mid-B a níže): %d", len(storage_filtered))

    # ── 4. Nové (dosud neviděné) ──────────────────────────────────────────
    new_storage = storage.find_new(storage_filtered, existing)
    logger.info("Nových (dosud neviditelných): %d", len(new_storage))

    # ── 5. Per-profil matching ────────────────────────────────────────────
    # format: { profile_name: (profile_dict, [listings]) }
    profile_matches: dict[str, tuple[dict, list]] = {}
    for prof in config.ALERT_PROFILES:
        # Filtruj z NEW storage (pro email jen nové)
        listings_for_alert = new_storage if not args.force_notify else storage_filtered
        matched = storage.apply_profile_filter(listings_for_alert, prof)
        profile_matches[prof["name"]] = (prof, matched)
        logger.info("Profil '%s': %d matching", prof["name"], len(matched))

    # ── 6. Výpis do konzole ───────────────────────────────────────────────
    print(f"\nShrnutí:")
    print(f"  Scraped celkem:          {len(all_scraped)}")
    print(f"  Po storage filtru:       {len(storage_filtered)}")
    print(f"  Novych (nevidennych):    {len(new_storage)}")
    for pname, (_, ml) in profile_matches.items():
        print(f"  Profil '{pname}':  {len(ml)} matching")

    _print_profile_results(profile_matches)

    # ── 7. Uložení CSV + Excel ────────────────────────────────────────────
    updated = storage.save(new_storage, existing, profile_matches)
    paths = storage.get_paths()
    print(f"\nData ulozena:")
    print(f"   CSV:   {paths['csv']}")
    print(f"   Excel: {paths['excel']}")

    # ── 8. Email notifikace ───────────────────────────────────────────────
    if not args.no_notify:
        notify.send_alerts(profile_matches, dry_run=args.dry_run)
    else:
        logger.info("Email přeskočen (--no-notify).")

    print("\n" + "=" * 60)
    total_matching = sum(len(ml) for _, ml in profile_matches.values())
    print(f"  Hotovo. Nových uloženo: {len(new_storage)}, matching: {total_matching}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
