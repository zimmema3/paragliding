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
        print("\n  Žádné nové matching inzeráty pro žádný profil.")
        return

    for pname, (prof, listings) in profile_matches.items():
        if not listings:
            continue
        print(f"\n✅ [{pname}] – {len(listings)} nových:")
        print("-" * 60)
        for lst in listings:
            price_s = f"{float(lst['price_eur']):.0f} €" if lst.get("price_eur") else "—"
            print(f"  [{lst.get('country')}] {lst.get('source_name')}")
            print(f"  📋 {lst.get('title','')[:100]}")
            print(f"  💰 {price_s}  🗓  rok {lst.get('year','?')}  "
                  f"📐 {lst.get('category','?')}  📏 {lst.get('size','?')}")
            print(f"  🔗 {lst.get('url','')}")
            print()


def main():
    args = parse_args()

    print("\n" + "=" * 60)
    print("  🪂  Paragliding Bazar Watcher")
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
    print(f"\n📊 Shrnutí:")
    print(f"  Scraped celkem:          {len(all_scraped)}")
    print(f"  Po storage filtru:       {len(storage_filtered)}")
    print(f"  Nových (neviděných):     {len(new_storage)}")
    for pname, (_, ml) in profile_matches.items():
        print(f"  Profil '{pname}':  {len(ml)} matching")

    _print_profile_results(profile_matches)

    # ── 7. Uložení CSV + Excel ────────────────────────────────────────────
    updated = storage.save(new_storage, existing, profile_matches)
    paths = storage.get_paths()
    print(f"\n💾 Data uložena:")
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

Spuštění:
  # Z adresáře paraglide/
  python -m bazar_watcher.run

  # Nebo přímo:
  python paraglide/bazar_watcher/run.py

Volby:
  --dry-run       Jen vytiskne co by odeslal emailem, neposílá
  --no-notify     Přeskoč email (jen scraping + uložení)
  --force-notify  Pošli email i když nejsou nové inzeráty (test)
  --filter-only   Jen zobraz filtrované z existujících dat, bez scrapingu
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Přidej rodiče do PYTHONPATH pro spuštění jako skript
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bazar_watcher import scrapers, storage, notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(description="Bazar křídel watcher")
    p.add_argument("--dry-run", action="store_true", help="Netiskne email, jen výpis")
    p.add_argument("--no-notify", action="store_true", help="Přeskoč email")
    p.add_argument("--force-notify", action="store_true", help="Pošli email i bez novinek")
    p.add_argument("--filter-only", action="store_true", help="Nezakrapuj, jen filtruj existující data")
    return p.parse_args()


def main():
    args = parse_args()

    print("\n" + "=" * 60)
    print("  🪂  Paragliding Bazar Watcher")
    print("=" * 60 + "\n")

    # 1. Načti existující data
    existing = storage.load_existing()
    logger.info("Existující záznamy: %d", len(existing))

    if args.filter_only:
        # Jen filtruj a zobraz existující
        all_listings = existing.to_dict(orient="records")
        matched = storage.apply_filters(all_listings)
        print(f"\nFiltrovaných inzerátů (EN B, max 5 let): {len(matched)}")
        for lst in matched:
            print(f"  [{lst.get('country')}] {lst.get('source_name')} | "
                  f"{lst.get('title', '')[:80]} | "
                  f"{lst.get('price_eur', '?')} € | rok {lst.get('year', '?')}")
        return

    # 2. Scrapuj všechny zdroje
    logger.info("Spouštím scrapery ...")
    all_scraped = scrapers.scrape_all()
    logger.info("Celkem scraped: %d inzerátů", len(all_scraped))

    # 3. Zjisti nové (ještě neviděné URL)
    new_all = storage.find_new(all_scraped, existing)
    logger.info("Nových inzerátů (dosud neviditelných): %d", len(new_all))

    # 4. Filtruj nové dle parametrů (EN B, rok >= min_year, cena)
    new_matching = storage.apply_filters(new_all)
    logger.info("Nových MATCHING (Low B, rok >= %d): %d",
                storage.apply_filters.__module__ and __import__("bazar_watcher.config", fromlist=["FILTERS"]).FILTERS["min_year"],
                len(new_matching))

    # Stručný výpis do konzole
    if new_matching:
        print(f"\n✅ NOVÉ matching inzeráty ({len(new_matching)}):")
        print("-" * 60)
        for lst in new_matching:
            price_str = f"{lst['price_eur']:.0f} €" if lst.get("price_eur") else "—"
            print(f"  [{lst.get('country')}] {lst.get('source_name')}")
            print(f"  📋 {lst.get('title', '')[:100]}")
            print(f"  💰 {price_str}  🗓  rok {lst.get('year', '?')}  📐 {lst.get('category', '?')}")
            print(f"  🔗 {lst.get('url', '')}")
            print()
    else:
        print("\n  Žádné nové matching inzeráty dnes.")

    # 5. Ulož všechny nové do CSV + aktualizuj Excel
    if new_all:
        storage.save(new_all, existing)
    else:
        # Aktualizuj Excel i bez nových (přepíše "Dnes nové" na prázdno)
        storage.save([], existing)

    paths = storage.get_paths()
    print(f"\n💾 Data uložena:")
    print(f"   CSV:   {paths['csv']}")
    print(f"   Excel: {paths['excel']}")

    # 6. Notifikace emailem
    if not args.no_notify:
        listings_to_send = new_matching if not args.force_notify else new_matching or new_all
        notify.send_alert(listings_to_send, dry_run=args.dry_run)
    else:
        logger.info("Email přeskočen (--no-notify).")

    print("\n" + "=" * 60)
    print(f"  Hotovo. Nové all: {len(new_all)}, matching: {len(new_matching)}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
