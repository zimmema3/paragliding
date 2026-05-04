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
    p.add_argument(
        "--reimport",
        action="store_true",
        help=(
            "Ukáže všechny aktuálně scrapované inzeráty (nejen nové od posledního runu). "
            "CSV se děplikuje standardně, ale email/výpis obsahuje vše ze storage filtru. "
            "Použi pro počáteční import nebo úplný přehled aktualních inzerátů."
        ),
    )
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
            print(f"  {price_s}  rok {lst.get('year','?')}  kat {lst.get('category','?')}  vel {lst.get('size','?')}  {lst.get('weight_range','') or ''}")
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
            if prof.get("enabled") is False:
                continue
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

    # ── 4. Nové (dosud neviděné) – pro CSV ukládání ──────────────────────────────────
    new_for_csv = storage.find_new(storage_filtered, existing)
    logger.info("Nových (dosud neviditelných): %d", len(new_for_csv))

    # --reimport: zobraz vše ze storage filtru (i již uložené), CSV dedup zůstává
    if args.reimport:
        new_for_alert = storage_filtered
        logger.info("REIMPORT: pro alert/email používám všech %d inzerátů", len(new_for_alert))
    else:
        new_for_alert = new_for_csv

    # ── 5. Per-profil matching ────────────────────────────────────────────
    # format: { profile_name: (profile_dict, [listings]) }
    profile_matches: dict[str, tuple[dict, list]] = {}
    for prof in config.ALERT_PROFILES:
        if prof.get("enabled") is False:
            logger.info("Profil '%s': enabled=False, přeskočeno", prof["name"])
            continue
        listings_for_alert = new_for_alert if not args.force_notify else storage_filtered
        # Doplň first_seen z CSV (pro reimport/force_notify ukáže reálné stáří)
        storage.enrich_first_seen(listings_for_alert, existing)
        matched = storage.apply_profile_filter(listings_for_alert, prof)
        profile_matches[prof["name"]] = (prof, matched)
        logger.info("Profil '%s': %d matching", prof["name"], len(matched))

    # ── 6. Výpis do konzole ───────────────────────────────────────────────
    mode_str = " [REIMPORT - vsechny aktualni]" if args.reimport else ""
    print(f"\nShrnuti{mode_str}:")
    print(f"  Scraped celkem:          {len(all_scraped)}")
    print(f"  Po storage filtru:       {len(storage_filtered)}")
    print(f"  Novych pro CSV:          {len(new_for_csv)}")
    if args.reimport:
        print(f"  Pro alert (reimport):    {len(new_for_alert)}")
    for pname, (_, ml) in profile_matches.items():
        print(f"  Profil '{pname}':  {len(ml)} matching")

    _print_profile_results(profile_matches)

    # ── 7. Uložení CSV + Excel ────────────────────────────────────────────
    # Do CSV jde vždy jen new_for_csv (dedup), do Excelu i reimport data
    profile_for_save = {name: listings for name, (_, listings) in profile_matches.items()}
    updated = storage.save(new_for_csv, existing, profile_for_save)
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
    print(f"  Hotovo. Novych do CSV: {len(new_for_csv)}, matching: {total_matching}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
