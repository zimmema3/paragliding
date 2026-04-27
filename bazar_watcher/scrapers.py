# -*- coding: utf-8 -*-
"""
Scrapers pro každý zdroj bazaru křídel.

Každý scraper vrací List[dict] se standardizovanými klíči:
  source_id, source_name, country, title, url, price_eur,
  year, category, size, weight_range, condition, date_listed, date_found

Konvence:
  - Pokud hodnota neznámá → None
  - price_eur je float nebo None
  - year je int nebo None
  - date_found je vždy dnešní datum (YYYY-MM-DD)
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from . import config

logger = logging.getLogger(__name__)

TODAY = date.today().isoformat()

# HTTP session – sdílená, nastavena v scrape_all()
_session: Optional[requests.Session] = None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "cs,de;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ──────────────────────────────────────────────────────────────────────────────
# Pomocné funkce
# ──────────────────────────────────────────────────────────────────────────────

def _get(url: str, **kwargs) -> Optional[requests.Response]:
    """GET s retry (2x) a timeout. Vrátí None při selhání."""
    for attempt in range(3):
        try:
            r = _session.get(url, headers=HEADERS, timeout=20, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            logger.warning("GET(%s) attempt %d failed: %s", url, attempt + 1, exc)
            time.sleep(2 ** attempt)
    return None


def _soup(url: str) -> Optional[BeautifulSoup]:
    r = _get(url)
    if r is None:
        return None
    return BeautifulSoup(r.text, "html.parser")


def _parse_price_eur(text: str) -> Optional[float]:
    """Vytáhne float cenu z textu jako EUR.
    Příklady: '450,00 EUR', '1 846,53 EUR (45 000,00 CZK)', '€ 900', '1.600 €'
    """
    text = text.replace("\xa0", " ").strip()
    # Preferuj explicitní EUR hodnotu
    m = re.search(r"([\d\s.,]+)\s*EUR", text, re.IGNORECASE)
    if not m:
        m = re.search(r"€\s*([\d\s.,]+)", text)
    if not m:
        return None
    raw = m.group(1).strip()
    # Normalizace: odstraň mezery jako oddělovač tisíců, čárku → tečka
    raw = re.sub(r"\s", "", raw)
    raw = raw.replace(",", ".")
    # Pokud více teček (1.846.53) → fixace: ponech jen poslední jako decimal
    parts = raw.split(".")
    if len(parts) > 2:
        raw = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_year(text: str) -> Optional[int]:
    """Najde rok výroby křídla v textu. Pátrá po 4místném čísle 2000–2030."""
    years = re.findall(r"\b(20[012]\d)\b", text)
    if not years:
        return None
    # Vrátí nejnovější nalezený rok (pravděpodobnější = rok výroby)
    return max(int(y) for y in years)


def _parse_year_strict(text: str, labels: list[str]) -> Optional[int]:
    """Hledá rok za konkrétním labelm: 'Rok výroby: 2022', 'Baujahr: 2022' apod."""
    for label in labels:
        m = re.search(rf"{re.escape(label)}\D{{0,5}}(20[012]\d)", text, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return _parse_year(text)


def _empty() -> dict:
    return {
        "source_id": None, "source_name": None, "country": None,
        "title": None, "url": None, "price_eur": None,
        "year": None, "category": None, "size": None,
        "weight_range": None, "condition": None,
        "date_listed": None, "date_found": TODAY,
    }


def _listing(
    source_id: str,
    source_name: str,
    country: str,
    title: str,
    url: str,
    **kwargs,
) -> dict:
    d = _empty()
    d.update({
        "source_id": source_id,
        "source_name": source_name,
        "country": country,
        "title": title.strip(),
        "url": url,
        "date_found": TODAY,
    })
    d.update(kwargs)
    return d


# ──────────────────────────────────────────────────────────────────────────────
# CZ – Paragliding Bazar CZ
# URL: https://paragliding-bazar.cz/cs/wings/en-b-ltf-dhv-1-2-standard/
# HTML: paginated, /cs/offering/<slug>/ links
# ──────────────────────────────────────────────────────────────────────────────

def scrape_paragliding_bazar_cz(source: dict) -> list[dict]:
    results = []
    base = "https://paragliding-bazar.cz"
    page = 1

    while True:
        url = f"{source['url']}?page={page}" if page > 1 else source["url"]
        soup = _soup(url)
        if soup is None:
            break

        # Každý inzerát je obalený div/article s odkazem na /cs/offering/
        links = soup.find_all("a", href=re.compile(r"/cs/offering/"))
        if not links:
            break

        seen_hrefs = set()
        for a in links:
            href = a.get("href", "")
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            full_url = urljoin(base, href)
            text = a.get_text(" ", strip=True)

            # Cena: vzor "450,00 EUR" nebo "1 846,53 EUR"
            price = _parse_price_eur(text)

            # Rok výroby
            year = _parse_year_strict(text, ["Rok výroby", "rok výroby"])

            # Kategorie – v textu je "EN B", "EN A" apod.
            cat_m = re.search(r"\bEN\s+[ABCD]\b", text, re.IGNORECASE)
            category = cat_m.group(0).upper() if cat_m else "EN B"  # URL filtru

            # Velikost
            size_m = re.search(r"Velikost[:\s]+([A-Z0-9]+)", text, re.IGNORECASE)
            size = size_m.group(1) if size_m else None

            # Vzletová hmotnost
            wt_m = re.search(r"Vzletová hmotnost[:\s]+([\d\s\-–]+kg)", text, re.IGNORECASE)
            weight = wt_m.group(1).strip() if wt_m else None

            # Podmínka (opotřebení)
            cond_m = re.search(
                r"Opotřebení[:\s]+([^\n\r,]+?)(?:\s+Rok|\s*$)", text, re.IGNORECASE
            )
            condition = cond_m.group(1).strip() if cond_m else None

            # Datum zveřejnění (formát MM/DD/YYYY v textu)
            date_m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
            date_listed = None
            if date_m:
                try:
                    date_listed = datetime.strptime(date_m.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    pass

            results.append(_listing(
                source_id=source["id"],
                source_name=source["name"],
                country=source["country"],
                title=text[:120],
                url=full_url,
                price_eur=price,
                year=year,
                category=category,
                size=size,
                weight_range=weight,
                condition=condition,
                date_listed=date_listed,
            ))

        # Zkontroluj odkaz na další stránku
        next_link = soup.find("a", string=re.compile(r"Next|Další|»", re.IGNORECASE))
        if not next_link:
            # Alternativní: hledej odkaz ?page=N+1
            next_href = soup.find("a", href=re.compile(rf"page={page+1}"))
            if not next_href:
                break
        page += 1
        time.sleep(1)

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# CZ – Bazoš
# URL: https://sport.bazos.cz/inzeraty/paragliding-kridlo/
# HTML: klasický Bazoš layout
# ──────────────────────────────────────────────────────────────────────────────

def scrape_bazos_cz(source: dict) -> list[dict]:
    results = []
    base = "https://sport.bazos.cz"
    page = 0  # Bazoš paginuje po 20: ?od=0, ?od=20, ...

    while True:
        url = source["url"] if page == 0 else f"{source['url']}?od={page}"
        soup = _soup(url)
        if soup is None:
            break

        # Každý inzerát: div.inzeraty > div.inzerat (nebo podobná struktura)
        # Fallback: hledej <h2> s <a> odkazem na /inzerat/
        items = soup.find_all("a", href=re.compile(r"/inzerat/\d+/"))
        if not items:
            break

        new_count = 0
        for a in items:
            href = a.get("href", "")
            if not href:
                continue
            full_url = urljoin(base, href)
            title = a.get_text(strip=True)
            if not title:
                continue

            # Rodičovský kontejner pro cenu a datum
            parent = a.find_parent(["div", "li", "article"]) or a.find_parent()
            parent_text = parent.get_text(" ", strip=True) if parent else title

            price = _parse_price_eur(parent_text.replace("Kč", ""))
            # Bazoš má ceny v Kč – přepočet není spolehlivý, necháme None pokud není EUR
            # Pro Kč: zaznamenáme do price_eur jako None, do title dáme cenu
            kc_m = re.search(r"([\d\s]+)\s*Kč", parent_text)
            price_eur = None
            if kc_m:
                kc_raw = re.sub(r"\s", "", kc_m.group(1))
                try:
                    price_eur = round(float(kc_raw) / 25.0, 0)  # orientační přepočet
                except ValueError:
                    pass

            year = _parse_year(parent_text)
            # Kategorie z textu nadpisu
            cat_m = re.search(r"\bEN\s*[-/ ]?\s*[ABCD]\b|\bEN\s[ABCD]\b", title, re.IGNORECASE)
            category = cat_m.group(0).upper().replace(" ", " ") if cat_m else None

            results.append(_listing(
                source_id=source["id"],
                source_name=source["name"],
                country=source["country"],
                title=title[:160],
                url=full_url,
                price_eur=price_eur,
                year=year,
                category=category,
            ))
            new_count += 1

        if new_count == 0:
            break
        # Bazoš má zřídka víc jak 20 inzerátů na paragliding, ale zkusíme
        page += 20
        if page > 200:
            break
        time.sleep(1)

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# CZ – Máme Křídla
# URL: https://mamekridla.cz/
# Malý bazar, produktové karty
# ──────────────────────────────────────────────────────────────────────────────

def scrape_mamekridla_cz(source: dict) -> list[dict]:
    results = []
    base = "https://mamekridla.cz"
    soup = _soup(source["url"])
    if soup is None:
        return results

    # Typické WooCommerce / vlastní e-shop: <li class="product"> nebo <div class="product">
    items = soup.find_all(["article", "li", "div"], class_=re.compile(r"product|item|listing", re.I))
    if not items:
        # Fallback: všechny <a> s href absolutním nebo relativním odkazem na produkt
        items = soup.find_all("a", href=re.compile(r"mamekridla\.cz/.+|^/[^/].+"))

    for item in items:
        a_tag = item.find("a") if item.name != "a" else item
        if not a_tag:
            continue
        href = a_tag.get("href", "")
        if not href or href in ("#", "/"):
            continue
        full_url = urljoin(base, href)
        title_tag = item.find(["h2", "h3", "h4", "span"], class_=re.compile(r"title|name|nadpis", re.I))
        title = (title_tag or a_tag).get_text(strip=True)
        if not title or len(title) < 5:
            continue

        text = item.get_text(" ", strip=True)
        price = _parse_price_eur(text)
        year = _parse_year(text)
        cat_m = re.search(r"\bEN\s*[ABCD]\b|\bB[-\s]G\b", text, re.IGNORECASE)
        category = cat_m.group(0) if cat_m else None

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=full_url,
            price_eur=price,
            year=year,
            category=category,
        ))

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# AT – Willhaben (JSON API)
# API: https://www.willhaben.at/webapi/iad/search/atz/seo/kaufen-und-verkaufen/l/gleitschirm
# Vrací JSON s polem advertSummaryList.advertSummary
# ──────────────────────────────────────────────────────────────────────────────

def scrape_willhaben_at(source: dict) -> list[dict]:
    results = []
    base_api = source["url"]

    page = 1
    while True:
        params = {
            "rows": 100,
            "isNavigation": "true",
            "page": page,
        }
        r = _get(base_api, params=params, headers={
            **HEADERS,
            "Accept": "application/json",
            "Referer": "https://www.willhaben.at/",
        })
        if r is None:
            break

        try:
            data = r.json()
        except ValueError:
            logger.warning("[willhaben_at] JSON parse failed, page %d", page)
            break

        ads = (
            data.get("advertSummaryList", {}).get("advertSummary", [])
            or data.get("searchResult", {}).get("advertSummaryList", {}).get("advertSummary", [])
        )
        if not ads:
            break

        for ad in ads:
            ad_id = ad.get("id", "")
            attrs = {a["name"]: a.get("values", [None])[0]
                     for a in ad.get("advertAttributeList", {}).get("advertAttribute", [])
                     if a.get("values")}

            title = ad.get("description", ad.get("heading", ""))
            url = f"https://www.willhaben.at/iad/kaufen-und-verkaufen/d/{ad.get('seoUrl', ad_id)}/"
            price_str = ad.get("price", {}).get("amount", "") if isinstance(ad.get("price"), dict) else ""
            price_eur = None
            try:
                price_eur = float(str(price_str).replace(",", ".").replace(" ", "")) if price_str else None
            except ValueError:
                pass

            year_str = attrs.get("YEAR_OF_PRODUCTION") or attrs.get("PRODUCTION_YEAR") or ""
            year = int(year_str) if str(year_str).isdigit() else _parse_year(title)

            results.append(_listing(
                source_id=source["id"],
                source_name=source["name"],
                country=source["country"],
                title=str(title)[:160],
                url=url,
                price_eur=price_eur,
                year=year,
                category=attrs.get("CATEGORY"),
                size=attrs.get("SIZE"),
            ))

        if len(ads) < 100:
            break
        page += 1
        time.sleep(1.5)

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# AT – Paragliding Store AT / Gleitschirmschule AT
# Genericý e-shop scraper (WooCommerce / vlastní)
# ──────────────────────────────────────────────────────────────────────────────

def _scrape_generic_shop(source: dict) -> list[dict]:
    """Generický scraper pro e-shopy s produktovými kartami."""
    results = []
    soup = _soup(source["url"])
    if soup is None:
        return results

    base = "/".join(source["url"].split("/")[:3])

    # WooCommerce / obecné: article.product, li.product, div.product-item apod.
    selectors = [
        {"name": "article", "class_": re.compile(r"product|item", re.I)},
        {"name": "li", "class_": re.compile(r"product|item", re.I)},
        {"name": "div", "class_": re.compile(r"product[-_]?(?:card|item|thumb|wrap)", re.I)},
    ]
    items = []
    for sel in selectors:
        items = soup.find_all(sel["name"], class_=sel["class_"])
        if items:
            break

    if not items:
        # Fallback: hledej h2/h3 s <a>
        items = soup.find_all(["h2", "h3"], class_=re.compile(r"title|name", re.I))

    for item in items:
        a_tag = item.find("a") if item.name not in ("a",) else item
        if not a_tag:
            continue
        href = a_tag.get("href", "")
        if not href:
            continue
        full_url = urljoin(base, href) if not href.startswith("http") else href

        title_tag = item.find(["h2", "h3", "h4", "span"], class_=re.compile(r"title|name|product", re.I))
        title = (title_tag or a_tag).get_text(strip=True)
        if not title or len(title) < 4:
            continue

        text = item.get_text(" ", strip=True)
        price = _parse_price_eur(text)
        year = _parse_year_strict(text, ["Baujahr", "Jahr", "Rok výroby", "year"])
        cat_m = re.search(r"\bEN\s*[ABCD]\b|\bB[-\s]G\b|\bLTF\s*1[-–]2\b", text, re.IGNORECASE)
        category = cat_m.group(0) if cat_m else None

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=full_url,
            price_eur=price,
            year=year,
            category=category,
        ))

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


scrape_paragliding_store_at = _scrape_generic_shop
scrape_gleitschirmschule_at = _scrape_generic_shop
scrape_swissgliders_ch = _scrape_generic_shop
scrape_paraglidingshop_ch = _scrape_generic_shop
scrape_alpstein_ch = _scrape_generic_shop
scrape_mamekridla_cz_shop = _scrape_generic_shop  # alias


# ──────────────────────────────────────────────────────────────────────────────
# DE – Flugsport DE (HTML tabulka)
# Sloupce: Hersteller | Modell+popis | Baujahr | Startgewicht | Kategorie | Preis
# ──────────────────────────────────────────────────────────────────────────────

def scrape_flugsport_de(source: dict) -> list[dict]:
    results = []
    soup = _soup(source["url"])
    if soup is None:
        return results

    table = soup.find("table")
    if not table:
        return results

    rows = table.find_all("tr")
    headers = []
    for row in rows:
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        texts = [c.get_text(strip=True) for c in cells]

        # Detekuj řádek se záhlavím
        if not headers:
            low = [t.lower() for t in texts]
            if any(k in " ".join(low) for k in ("hersteller", "modell", "baujahr", "kategorie")):
                headers = low
                continue

        if len(texts) < 3:
            continue

        # Mapování sloupců dle záhlaví
        def col(keyword: str) -> Optional[str]:
            for i, h in enumerate(headers):
                if keyword in h and i < len(texts):
                    return texts[i]
            return None

        # Fallback pořadí: Hersteller | Modell | Baujahr | Gewicht | Kat | Preis
        manufacturer = col("hersteller") or (texts[0] if len(texts) > 0 else "")
        model = col("modell") or (texts[1] if len(texts) > 1 else "")
        baujahr = col("baujahr") or col("jahr") or (texts[2] if len(texts) > 2 else "")
        weight = col("gewicht") or col("startgewicht") or (texts[3] if len(texts) > 3 else "")
        kategorie = col("kategorie") or col("kat") or (texts[4] if len(texts) > 4 else "")
        preis = col("preis") or col("price") or (texts[5] if len(texts) > 5 else "")

        title = f"{manufacturer} {model}".strip()
        if not title or len(title) < 4:
            continue

        year_m = re.search(r"20[012]\d", baujahr)
        year = int(year_m.group(0)) if year_m else None

        price = _parse_price_eur(preis + " EUR") if preis else None
        if price is None and "anfrage" in preis.lower():
            price = None  # "auf Anfrage" = unknown

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=source["url"],  # Tabulka, žádné individuální URL
            price_eur=price,
            year=year,
            category=kategorie.strip() if kategorie else None,
            weight_range=weight.strip() if weight else None,
        ))

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# DE – Kleinanzeigen Atom feed
# URL: https://www.kleinanzeigen.de/s-sport-camping/paragliding/k0c230.atom
# ──────────────────────────────────────────────────────────────────────────────

def scrape_kleinanzeigen_de(source: dict) -> list[dict]:
    results = []
    r = _get(source["url"])
    if r is None:
        return results

    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as e:
        logger.warning("[kleinanzeigen_de] XML parse failed: %s", e)
        return results

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    if not entries:
        # Zkus bez namespace
        entries = root.findall("entry")

    for entry in entries:
        def txt(tag):
            el = entry.find(f"atom:{tag}", ns) or entry.find(tag)
            return el.text.strip() if el is not None and el.text else None

        title = txt("title") or ""
        link_el = entry.find("atom:link", ns) or entry.find("link")
        url = (link_el.get("href") if link_el is not None else None) or ""
        summary = txt("summary") or txt("content") or ""
        published = txt("published") or txt("updated") or ""

        full_text = f"{title} {summary}"
        price = _parse_price_eur(full_text)
        year = _parse_year(full_text)
        cat_m = re.search(r"\bEN\s*[ABCD]\b|\bB[-\s]G\b|\bgleitschirm\b", full_text, re.IGNORECASE)
        category = cat_m.group(0) if cat_m else None

        date_listed = None
        if published:
            try:
                date_listed = datetime.fromisoformat(published[:10]).strftime("%Y-%m-%d")
            except ValueError:
                pass

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=url,
            price_eur=price,
            year=year,
            category=category,
            date_listed=date_listed,
        ))

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Registry: source_id → scraper funkce
# ──────────────────────────────────────────────────────────────────────────────

_SCRAPERS = {
    # Oba CZ zdroje z paragliding-bazar.cz (EN A i EN B) = stejný scraper
    "paragliding_bazar_cz":   scrape_paragliding_bazar_cz,
    "paragliding_bazar_cz_b": scrape_paragliding_bazar_cz,
    "paragliding_bazar_cz_a": scrape_paragliding_bazar_cz,
    "bazos_cz":               scrape_bazos_cz,
    "mamekridla_cz":          scrape_mamekridla_cz,
    "willhaben_at":           scrape_willhaben_at,
    "paragliding_store_at":   _scrape_generic_shop,
    "gleitschirmschule_at":   _scrape_generic_shop,
    "flugsport_de":           scrape_flugsport_de,
    "kleinanzeigen_de":       scrape_kleinanzeigen_de,
    "swissgliders_ch":        _scrape_generic_shop,
    "paraglidingshop_ch":     _scrape_generic_shop,
    "alpstein_ch":            _scrape_generic_shop,
}


# ──────────────────────────────────────────────────────────────────────────────
# Hlavní vstupní bod
# ──────────────────────────────────────────────────────────────────────────────

def scrape_all() -> list[dict]:
    """Spustí všechny enabled scrapers a vrátí agregovaný seznam inzerátů."""
    global _session
    _session = requests.Session()
    _session.headers.update(HEADERS)

    all_listings = []

    for source in config.SOURCES:
        if not source.get("enabled", True):
            logger.info("[%s] disabled, skipping", source["id"])
            continue

        scraper_fn = _SCRAPERS.get(source["id"])
        if scraper_fn is None:
            logger.warning("[%s] no scraper registered, skipping", source["id"])
            continue

        logger.info("Scraping: %s (%s) ...", source["name"], source["country"])
        try:
            listings = scraper_fn(source)
            all_listings.extend(listings)
        except Exception as exc:
            logger.error("[%s] ERROR: %s", source["id"], exc, exc_info=True)

        time.sleep(2)  # Zdvořilostní pauza mezi zdroji

    _session.close()
    logger.info("Total scraped: %d listings from %d sources", len(all_listings), len(config.SOURCES))
    return all_listings
