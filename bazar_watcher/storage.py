# -*- coding: utf-8 -*-
"""
Ukládání a čtení dat bazar_watcher.

Strategie:
  - data/bazar_watcher/listings.csv  → persistentní databáze VŠECH viděných
    inzerátů od mid-B a níže (git-friendly, commit po každém runu)
  - data/bazar_watcher/listings.xlsx → Excel report generovaný při každém spuštění:
      List "Všechny inzeráty"  – celá CSV historie
      List "Dnes nové"         – všechny nové z dnešního runu
      List "<Profil>"          – nové matching pro každý alert profil
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
DATA_DIR = _HERE.parent / "data" / "bazar_watcher"
CSV_PATH = DATA_DIR / "listings.csv"
EXCEL_PATH = DATA_DIR / "listings.xlsx"

COLUMNS = [
    "source_id", "source_name", "country",
    "title", "url",
    "price_eur", "year", "category", "size", "weight_range", "condition",
    "date_listed", "date_found",
]

TODAY = date.today().isoformat()


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# CSV I/O
# ──────────────────────────────────────────────────────────────────────────────

def load_existing() -> pd.DataFrame:
    """Načte existující CSV. Vrátí prázdný DataFrame pokud soubor neexistuje."""
    _ensure_dir()
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    try:
        df = pd.read_csv(CSV_PATH, dtype=str)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[COLUMNS]
    except Exception as exc:
        logger.error("Chyba při čtení CSV: %s", exc)
        return pd.DataFrame(columns=COLUMNS)


def find_new(new_listings: list[dict], existing: pd.DataFrame) -> list[dict]:
    """Vrátí jen inzeráty, jejichž URL ještě není ve stávajících datech."""
    seen_urls: set[str] = set(existing["url"].dropna().tolist())
    seen_title_src: set[tuple] = set(
        zip(existing["source_id"].tolist(), existing["title"].tolist())
    )
    new = []
    for listing in new_listings:
        url = listing.get("url") or ""
        if url and url not in seen_urls:
            new.append(listing)
            seen_urls.add(url)
        elif not url:
            key = (listing.get("source_id"), listing.get("title"))
            if key not in seen_title_src:
                new.append(listing)
                seen_title_src.add(key)
    return new


# ──────────────────────────────────────────────────────────────────────────────
# Kategorie → číselná úroveň
# ──────────────────────────────────────────────────────────────────────────────

def _detect_level(listing: dict) -> int:
    """
    Odhadne úroveň inzerátu (1=A, 2=low-B, 3=mid-B).
    Používá config.CATEGORY_KEYWORDS_TO_LEVEL.
    """
    from . import config
    text = " ".join([
        (listing.get("category") or ""),
        (listing.get("title") or ""),
    ]).lower()

    for keywords, level in config.CATEGORY_KEYWORDS_TO_LEVEL:
        if any(kw in text for kw in keywords):
            return level
    return 2  # default: EN B bez bližšího určení = low-B


# ──────────────────────────────────────────────────────────────────────────────
# Storage filter – co ukládáme (mid-B a níže)
# ──────────────────────────────────────────────────────────────────────────────

def apply_storage_filter(listings: list[dict]) -> list[dict]:
    """
    Propustí inzeráty EN A + celý EN B (low i mid) + starší označení.
    Vyřadí EN C, D, CCC, motory a ceny pod minimem.
    """
    from . import config

    accepted_cats = [c.upper() for c in config.STORAGE_FILTER["categories"]]
    all_known = [w.lower() for w in config.ALL_KNOWN_WINGS]
    min_price = config.STORAGE_FILTER.get("min_price_eur", 150)

    # Klíčová slova pro vyřazení (EN C a výše)
    exclude_cats = ["EN C", "EN/C", "EN D", "EN/D", "CCC", "DHV 2-3", "DHV 3",
                    "LTF 2-3", "DAGC", "motor", "B-R+", "C-"]

    matched = []
    for lst in listings:
        price = lst.get("price_eur")
        if price is not None:
            try:
                if float(price) < min_price:
                    continue
            except (ValueError, TypeError):
                pass

        cat = (lst.get("category") or "").upper()
        title_lower = (lst.get("title") or "").lower()
        full_text = cat + " " + title_lower

        # Vyřaď EN C a výše
        if any(ex.upper() in full_text.upper() for ex in exclude_cats):
            continue

        # Propusť pokud kategorie odpovídá NEBO model je v known wings
        cat_ok = any(ac in cat for ac in accepted_cats)
        model_ok = any(m in title_lower for m in all_known)

        if cat_ok or model_ok:
            matched.append(lst)

    return matched


# ──────────────────────────────────────────────────────────────────────────────
# Alert filter – matching pro konkrétní profil
# ──────────────────────────────────────────────────────────────────────────────

def apply_profile_filter(listings: list[dict], profile: dict) -> list[dict]:
    """
    Filtruje listings dle jednoho alert profilu.
    Profil musí mít klíče: max_category, sizes, max_price_eur, min_year, countries
    """
    from . import config

    max_cat_str = (profile.get("max_category") or "mid-b").lower().replace(" ", "-")
    max_level = config.CATEGORY_LEVEL.get(max_cat_str, 3)

    sizes_raw = profile.get("sizes")
    allowed_sizes = (
        [str(s).upper() for s in sizes_raw] if sizes_raw else None
    )

    max_price = profile.get("max_price_eur")
    min_year = profile.get("min_year") or (config.CURRENT_YEAR - 5)
    countries = profile.get("countries")  # None = vše

    matched = []
    for lst in listings:
        # Filtr: úroveň kategorie
        level = _detect_level(lst)
        if level > max_level:
            continue

        # Filtr: rok výroby
        year = lst.get("year")
        if year is not None:
            try:
                if int(year) < int(min_year):
                    continue
            except (ValueError, TypeError):
                pass

        # Filtr: cena
        price = lst.get("price_eur")
        if max_price is not None and price is not None:
            try:
                if float(price) > float(max_price):
                    continue
            except (ValueError, TypeError):
                pass

        # Filtr: velikost
        if allowed_sizes is not None:
            size_val = str(lst.get("size") or "").upper()
            title_up = (lst.get("title") or "").upper()
            size_ok = (
                size_val in allowed_sizes
                or any(
                    re.search(rf"\b{re.escape(s)}\b", title_up)
                    for s in allowed_sizes
                )
            )
            if not size_ok:
                continue

        # Filtr: země
        if countries is not None:
            if (lst.get("country") or "").upper() not in [c.upper() for c in countries]:
                continue

        matched.append(lst)

    return matched


# ──────────────────────────────────────────────────────────────────────────────
# Save + Excel
# ──────────────────────────────────────────────────────────────────────────────

def save(
    new_storage: list[dict],
    existing: pd.DataFrame,
    profile_matches: dict[str, list[dict]],
) -> pd.DataFrame:
    """
    Přidá nové storage-filtered inzeráty do CSV.
    Vygeneruje Excel se listy:
      - Všechny inzeráty (celá historie)
      - Dnes nové (všechny dnešní přírůstky)
      - Po jednom listu pro každý alert profil s dnešními matches
    Vrátí aktualizovaný DataFrame.
    """
    _ensure_dir()

    if new_storage:
        new_df = pd.DataFrame(new_storage, columns=COLUMNS)
        updated = pd.concat([existing, new_df], ignore_index=True)
        updated.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
        logger.info("CSV uloženo: %s (%d řádků celkem)", CSV_PATH, len(updated))
    else:
        updated = existing
        logger.info("Žádné nové storage inzeráty.")

    _write_excel(updated, new_storage, profile_matches)
    return updated


def _write_excel(
    all_df: pd.DataFrame,
    new_today: list[dict],
    profile_matches: dict[str, list[dict]],
):
    try:
        with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
            # List 1: celá historie
            all_df.to_excel(writer, sheet_name="Všechny inzeráty", index=False)

            # List 2: dnes nové (storage filter, bez profil. filtrace)
            today_df = pd.DataFrame(new_today or [], columns=COLUMNS)
            today_df.to_excel(writer, sheet_name="Dnes nové", index=False)

            # Listy per profil
            for profile_name, listings in profile_matches.items():
                # Zkrátit název listu na max 31 znaků (Excel omezení)
                sheet_name = profile_name[:28] + "..." if len(profile_name) > 31 else profile_name
                # Nahradit znaky nepovolené v názvech listů
                for ch in r"\/*?:[]":
                    sheet_name = sheet_name.replace(ch, "-")
                prof_df = pd.DataFrame(listings or [], columns=COLUMNS)
                prof_df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Autofit šíře sloupců
            for sheet in writer.sheets.values():
                for col_cells in sheet.columns:
                    col_letter = col_cells[0].column_letter
                    max_len = max(
                        (len(str(c.value)) for c in col_cells if c.value is not None),
                        default=10,
                    )
                    sheet.column_dimensions[col_letter].width = min(max_len + 3, 60)

        logger.info("Excel uložen: %s", EXCEL_PATH)
    except Exception as exc:
        logger.error("Excel zápis selhal: %s", exc)


def get_paths() -> dict:
    return {"csv": str(CSV_PATH), "excel": str(EXCEL_PATH)}
CSV_PATH = DATA_DIR / "listings.csv"
EXCEL_PATH = DATA_DIR / "listings.xlsx"

COLUMNS = [
    "source_id", "source_name", "country",
    "title", "url",
    "price_eur", "year", "category", "size", "weight_range", "condition",
    "date_listed", "date_found",
]

TODAY = date.today().isoformat()


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_existing() -> pd.DataFrame:
    """Načte existující CSV. Vrátí prázdný DataFrame pokud soubor neexistuje."""
    _ensure_dir()
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    try:
        df = pd.read_csv(CSV_PATH, dtype=str)
        # Zajisti přítomnost všech sloupců
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[COLUMNS]
    except Exception as exc:
        logger.error("Chyba při čtení CSV: %s", exc)
        return pd.DataFrame(columns=COLUMNS)


def find_new(new_listings: list[dict], existing: pd.DataFrame) -> list[dict]:
    """
    Vrátí pouze ty inzeráty z new_listings, jejichž URL ještě není v existing.
    Inzeráty bez URL (flugsport tabulka) jsou identifikovány kombinací
    source_id + title.
    """
    seen_urls: set[str] = set(existing["url"].dropna().tolist())
    seen_title_src: set[tuple] = set(
        zip(existing["source_id"].tolist(), existing["title"].tolist())
    )

    new = []
    for listing in new_listings:
        url = listing.get("url") or ""
        if url and url not in seen_urls:
            new.append(listing)
            seen_urls.add(url)
        elif not url:
            key = (listing.get("source_id"), listing.get("title"))
            if key not in seen_title_src:
                new.append(listing)
                seen_title_src.add(key)
    return new


def apply_filters(listings: list[dict]) -> list[dict]:
    """
    Filtruje inzeráty dle config.FILTERS:
      1. Rok výroby >= min_year (pokud je znám)
      2. Kategorie odpovídá EN B / B-G / ... NEBO název sedí na LOW_B_WINGS
      3. Cena >= min_price_eur (pokud je známa)
    """
    from . import config

    min_year = config.FILTERS["min_year"]
    accepted_cats = [c.upper() for c in config.FILTERS["categories"]]
    low_b = [w.lower() for w in config.LOW_B_WINGS]
    min_price = config.FILTERS.get("min_price_eur", 0)

    matched = []
    for lst in listings:
        year = lst.get("year")
        # Rok: pokud je uveden a je příliš starý → vyřadit
        if year is not None and int(year) < min_year:
            continue

        price = lst.get("price_eur")
        if price is not None and float(price) < min_price:
            continue

        cat = (lst.get("category") or "").upper()
        title_lower = (lst.get("title") or "").lower()

        cat_ok = any(ac in cat for ac in accepted_cats)
        model_ok = any(m in title_lower for m in low_b)

        if cat_ok or model_ok:
            matched.append(lst)

    return matched


def save(all_new: list[dict], existing: pd.DataFrame) -> pd.DataFrame:
    """
    Přidá nové inzeráty do CSV a vygeneruje Excel se dvěma listy:
      - 'Všechny inzeráty' (celá historie)
      - 'Dnes nové' (jen dnešní přírůstky)
    Vrátí aktualizovaný DataFrame.
    """
    _ensure_dir()

    if not all_new:
        logger.info("Žádné nové inzeráty k uložení.")
        # Přesto aktualizuj Excel pro přehled
        _write_excel(existing, [])
        return existing

    new_df = pd.DataFrame(all_new, columns=COLUMNS)
    updated = pd.concat([existing, new_df], ignore_index=True)

    # Ulož CSV
    updated.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    logger.info("CSV uloženo: %s (%d řádků celkem)", CSV_PATH, len(updated))

    # Vygeneruj Excel
    _write_excel(updated, all_new)
    return updated


def _write_excel(all_df: pd.DataFrame, new_today: list[dict]):
    """Zapíše/přepíše Excel soubor se dvěma listy."""
    try:
        with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
            # List 1: vše
            all_df.to_excel(writer, sheet_name="Všechny inzeráty", index=False)

            # List 2: dnešní nové (filtrované = hlídané parametry)
            if new_today:
                new_df = pd.DataFrame(new_today, columns=COLUMNS)
            else:
                new_df = pd.DataFrame(columns=COLUMNS)
            new_df.to_excel(writer, sheet_name="Dnes nové", index=False)

            # Autofit šíři sloupců na obou listech
            for sheet in writer.sheets.values():
                for col_cells in sheet.columns:
                    col_letter = col_cells[0].column_letter
                    max_len = max(
                        (len(str(c.value)) for c in col_cells if c.value is not None),
                        default=10,
                    )
                    sheet.column_dimensions[col_letter].width = min(max_len + 3, 60)

        logger.info("Excel uložen: %s", EXCEL_PATH)
    except Exception as exc:
        logger.error("Excel zápis selhal: %s", exc)


def get_paths() -> dict:
    """Vrátí cesty k souborům dat."""
    return {"csv": str(CSV_PATH), "excel": str(EXCEL_PATH)}
