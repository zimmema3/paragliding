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

def _get(url: str, extra_headers: dict | None = None, **kwargs) -> Optional[requests.Response]:
    """GET s retry (2x) a timeout. Vrátí None při selhání.
    4xx chyby (klient) = neretrujeme – jsou to očekávané stavy (404 = konec pagináce apod.)
    """
    hdrs = {**HEADERS, **(extra_headers or {})}
    for attempt in range(3):
        try:
            r = _session.get(url, headers=hdrs, timeout=20, **kwargs)
            r.raise_for_status()
            return r
        except requests.HTTPError as exc:
            # 4xx – klientská chyba, retry nepomůže
            if exc.response is not None and 400 <= exc.response.status_code < 500:
                logger.debug("GET(%s) client error %d, not retrying", url, exc.response.status_code)
                return None
            logger.warning("GET(%s) attempt %d failed: %s", url, attempt + 1, exc)
            time.sleep(2 ** attempt)
        except requests.RequestException as exc:
            logger.warning("GET(%s) attempt %d failed: %s", url, attempt + 1, exc)
            time.sleep(2 ** attempt)
    return None


def _soup(url: str) -> Optional[BeautifulSoup]:
    r = _get(url)
    if r is None:
        return None
    return BeautifulSoup(r.text, "html.parser")


def _normalize_price_raw(raw: str) -> str:
    """Normalizuje německý/francouzský číselný formát na Python float string.
    Příklady: '1.200,00' → '1200.00', '1.600' → '1600', '820,00' → '820.00'
    """
    raw = re.sub(r"\s", "", raw).strip()
    if "," in raw:
        # Čárka = desetinný oddělovač, tečka = oddělovač tisíců
        raw = raw.replace(".", "").replace(",", ".")
    else:
        parts = raw.split(".")
        if len(parts) > 2:
            # 1.846.53 → '1846.53'
            raw = "".join(parts[:-1]) + "." + parts[-1]
        elif len(parts) == 2 and len(parts[-1]) == 3 and parts[-1].isdigit():
            # '1.600' → '1600' (3 cifry za tečkou = oddělovač tisíců)
            raw = "".join(parts)
    return raw


def _parse_price_eur(text: str) -> Optional[float]:
    """Vytáhne float cenu z textu jako EUR.
    Priorita:
    1. '... 820,00 EUR' (explicitní EUR za číslem)
    2. '... 1.200,00 €' (€ jako trailing currency – DE/AT/CZ standard)
    3. '€ 900' (€ jako leading currency – jen pokud nic jiného)

    Číslo musí mít alespoň 3 cifry (vyfiltruje "8", "25" apod. před €).
    Pokud více cen (orig + sale), vrátí poslední (= sale price).
    """
    text = text.replace("\xa0", " ").strip()
    # Regex pro číslo: aspoň 3 cifry (vyfiltruje "8", "25" apod.).
    # FR/EUR-keyword formát: "1 846,53" (mezera jako tisícový oddělovač)
    NUM_FR = r"(\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?|\d{3,}(?:,\d{1,2})?|\d{1,3},\d{1,2})"
    # AT/DE/CZ pro € formát: tečka jako tisícový OK, mezera ne (mohlo by být "25 990" = velikost+cena)
    NUM_DE = r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d{3,}(?:,\d{1,2})?|\d{1,3},\d{1,2})"

    # 1. Explicitní EUR za číslem (FR formát povoluje mezeru)
    matches = re.findall(NUM_FR + r"\s*EUR\b", text, re.IGNORECASE)
    if matches:
        try:
            return float(_normalize_price_raw(matches[-1].strip()))
        except ValueError:
            pass
    # 2. € za číslem (DE/AT/CZ formát: tečka, NE mezera jako tis. odděl.)
    matches = re.findall(NUM_DE + r"\s*€", text)
    if matches:
        try:
            return float(_normalize_price_raw(matches[-1].strip()))
        except ValueError:
            pass
    # 3. € před číslem (anglický/internacionální formát)
    m = re.search(r"€\s*" + NUM_DE, text)
    if m:
        try:
            return float(_normalize_price_raw(m.group(1).strip()))
        except ValueError:
            return None
    return None


# Aktuální kurz CHF→EUR (přibližný; pro lepší přesnost lze později
# napojit na ECB API nebo settings).
CHF_TO_EUR = 1.0 / 1.05


def _parse_price_chf_to_eur(text: str) -> Optional[float]:
    """Najde CHF cenu (Fr. / CHF) a převede na EUR.
    Strategie:
        - Pokud text obsahuje 'Verkaufspreis' / 'Sell price' → vzít cenu hned za tímto klíčovým slovem.
        - Jinak vzít PRVNÍ rozumnou CHF hodnotu (= cena v UI).
    Podporuje apostrofy ' ’, non-breaking space, číslo před i za CHF.
    Filtruje hodnoty mimo rozsah 50–100 000.
    """
    text = text.replace("\xa0", " ")

    def _to_float(raw: str) -> Optional[float]:
        raw = raw.replace("'", "").replace("\u2019", "").replace(" ", "")
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        elif raw.count(".") > 1:
            parts = raw.split(".")
            raw = "".join(parts[:-1]) + "." + parts[-1]
        elif raw.endswith("."):
            raw = raw[:-1]
        try:
            v = float(raw)
        except ValueError:
            return None
        return v if 50 <= v <= 100000 else None

    # 1) Preferuj cenu po klíčovém slově "Verkaufspreis" / "Verkaufspreis in CHF"
    m = re.search(
        r"Verkaufspreis(?:\s+in\s+CHF)?\s*[:.]?\s*([\d'\u2019.,]+)\s*(?:CHF|Fr\.?)?",
        text,
        re.IGNORECASE,
    )
    if m:
        v = _to_float(m.group(1))
        if v is not None:
            return round(v * CHF_TO_EUR, 0)

    # 2) Jinak: PRVNÍ CHF/Fr. v textu (po nebo před číslem)
    candidates = []
    for m in re.finditer(r"(?:Fr\.?|CHF)[\s:]*([\d'\u2019.,]+)", text, re.IGNORECASE):
        candidates.append((m.start(), m.group(1)))
    for m in re.finditer(r"([\d'\u2019.,]+)\s*(?:CHF|Fr\.?)\b", text, re.IGNORECASE):
        candidates.append((m.start(), m.group(1)))
    if not candidates:
        return None
    # Seřaď podle pozice v textu, vrať první rozumnou hodnotu
    for _, raw in sorted(candidates):
        v = _to_float(raw)
        if v is not None:
            return round(v * CHF_TO_EUR, 0)
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

            # Datum zveřejnění – zkus více formátů
            date_listed = None
            # Anglický formát MM/DD/YYYY (používá paragliding-bazar.cz)
            date_m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
            if date_m:
                try:
                    date_listed = datetime.strptime(date_m.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    pass
            # Český formát DD.MM.YYYY nebo D.M.YYYY
            if date_listed is None:
                date_m2 = re.search(r"(\d{1,2})\.(\d{1,2})\.(20[012]\d)", text)
                if date_m2:
                    try:
                        date_listed = datetime.strptime(
                            f"{date_m2.group(1)}.{date_m2.group(2)}.{date_m2.group(3)}",
                            "%d.%m.%Y",
                        ).strftime("%Y-%m-%d")
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
        r = _get(base_api, params=params, extra_headers={
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
    """Generický scraper pro e-shopy s produktovými kartami.

    Strategie:
    1. Zkusí postupně různé selektory; vybere ten, který dá nejvíc UNIKÁTNÍCH hrefů
       (zabrání matchování navigačních / wrapper kontejnerů).
    2. Filtruje:
       - href musí mít alespoň 2 path segmenty (ne nav)
       - href musí směřovat na stejnou doménu
       - ze stejného hrefu zachová jen první výskyt (deduplikace)
    """
    results = []
    soup = _soup(source["url"])
    if soup is None:
        return results

    base = "/".join(source["url"].split("/")[:3])

    # Kandidátní selektory v pořadí specifičnosti
    candidate_selectors = [
        # Specifické (Shopware, atd.)
        {"name": ["div", "article"], "class_": re.compile(r"product[-_]box|product[-_]card|product[-_]item|product[-_]thumb|product[-_]wrap", re.I)},
        # WooCommerce
        {"name": "li", "class_": re.compile(r"\bproduct\b", re.I)},
        {"name": "article", "class_": re.compile(r"\bproduct\b|\bitem\b", re.I)},
        # Obecné
        {"name": "div", "class_": re.compile(r"\bproduct\b|\bitem\b", re.I)},
    ]

    best_items: list = []
    best_unique = 0
    for sel in candidate_selectors:
        items = soup.find_all(sel["name"], class_=sel["class_"])
        if not items:
            continue
        # Spočti unikátní href v této kandidátní sadě
        unique_hrefs = set()
        for it in items:
            a = it.find("a", href=True)
            if a:
                href = a.get("href", "")
                if href:
                    unique_hrefs.add(href)
        if len(unique_hrefs) > best_unique:
            best_unique = len(unique_hrefs)
            best_items = items
        # Pokud první selektor už dal slušně produkty, neutrácet čas dalšími
        if best_unique >= 5:
            break

    items = best_items
    if not items:
        items = soup.find_all(["h2", "h3"], class_=re.compile(r"title|name", re.I))

    seen_hrefs: set[str] = set()
    for item in items:
        a_tag = item.find("a", href=True) if item.name != "a" else item
        if not a_tag:
            continue
        href = a_tag.get("href", "")
        if not href:
            continue
        full_url = urljoin(base, href) if not href.startswith("http") else href

        # Přeskoč navigační položky – URL musí mít alespoň 2 path segmenty
        path = full_url.replace(base, "").rstrip("/")
        path_parts = [p for p in path.split("/") if p]
        if len(path_parts) < 2:
            continue
        # Přeskoč href mimo doménu obchodu
        if not full_url.startswith(base):
            continue
        # Deduplikace: stejný href = stejný produkt (vyšší vs nižší kontejner)
        if full_url in seen_hrefs:
            continue
        seen_hrefs.add(full_url)

        title_tag = item.find(["h2", "h3", "h4", "span"], class_=re.compile(r"title|name|product", re.I))
        title = (title_tag or a_tag).get_text(strip=True)
        if not title or len(title) < 4:
            continue

        text = item.get_text(" ", strip=True)
        price = _parse_price_eur(text)
        year = _parse_year_strict(text, ["Baujahr", "Jahr", "Rok výroby", "year"])
        cat_m = re.search(r"\bEN[-\s/]*[ABCD]\b|\bB[-\s]G\b|\bLTF\s*1[-–]2\b", text, re.IGNORECASE)
        category = cat_m.group(0).upper().replace("-", " ").replace("/", " ") if cat_m else None

        # Velikost / hmotnostní rozsah z titulku
        size_m = re.search(r"\b(XXS|XS|S|M|ML|L|XL|XXL|\d{2})\b", title)
        size = size_m.group(1).upper() if size_m else None
        wt_m = re.search(r"(\d{2,3}\s*[-–]\s*\d{2,3}\s*kg)", text, re.IGNORECASE)
        weight = wt_m.group(1).replace(" ", "") if wt_m else None

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=full_url,
            price_eur=price,
            year=year,
            category=category,
            size=size,
            weight_range=weight,
        ))

    logger.info("[%s] scraped %d listings (selektor unique=%d)", source["id"], len(results), best_unique)
    return results


scrape_paragliding_store_at = _scrape_generic_shop
scrape_gleitschirmschule_at = _scrape_generic_shop  # disabled in config (JS shop)


# ──────────────────────────────────────────────────────────────────────────────
# AT – Paragliding Store AT (Cumulus CMS / Jimdo, hproduct microformat)
# https://www.paragliding-store.at/shop/gebrauchtmarkt-used-stuff/used-paragliders/
# Položky mají strukturovaná pole v desc: Baujahr/Erstflug, Größe, Gewichtsbereich
# Skutečná cena (např. "980,00 €") je v textu, "0,00 €" je placeholder MwSt-info.
# ──────────────────────────────────────────────────────────────────────────────

def scrape_paragliding_store_at(source: dict) -> list[dict]:
    results = []
    soup = _soup(source["url"])
    if soup is None:
        return results

    items = soup.find_all(class_="hproduct")
    for it in items:
        full = it.get_text(" ", strip=True)
        # Filtr navigačních/kategoriálních hproduct prvků – reálný inzerát
        # vždy obsahuje Baujahr nebo Erstflug. Bez toho je to kategorie.
        if not re.search(r"\b(Baujahr|Erstflug)\b", full, re.IGNORECASE):
            continue
        # Title: vše před "Baujahr" / "Erstflug" (ať je první)
        title_m = re.match(r"\s*(.+?)\s*(?=Baujahr|Erstflug)", full)
        title = (title_m.group(1) if title_m else full[:80]).strip()
        # Často duplicitní "Verkaufe X Verkaufe X" → ponech 2. polovinu (= čistší)
        if title.count("Verkaufe") >= 2:
            parts = title.split("Verkaufe")
            title = ("Verkaufe " + parts[-1]).strip()
        # Strip "Verkaufe " prefix pro čistší titulek
        title = re.sub(r"^Verkaufe\s+", "", title, flags=re.IGNORECASE).strip()
        if len(title) < 4:
            continue
        # Skip non-křídla (pokud by se náhodou objevilo)
        if re.search(r"\b(gurtzeug|harness|helm|reserve|vario|skytraxx|funk)\b", title, re.IGNORECASE):
            continue

        # Cena: hledej "X,XX €" v desc, ignoruj placeholder "0,00 €"
        price_eur = None
        prices = re.findall(
            r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d{3,}(?:,\d{1,2})?|\d{1,3},\d{1,2})\s*€",
            full,
        )
        # Vyhoď "0,00" placeholdery
        prices = [p for p in prices if _normalize_price_raw(p) not in ("0", "0.00", "0.0")]
        if prices:
            try:
                price_eur = float(_normalize_price_raw(prices[0]))  # první reálná cena
            except ValueError:
                pass

        # Year (Baujahr / Erstflug: 07.2016 nebo 05/2020)
        year = None
        year_m = re.search(r"(?:Baujahr|Erstflug)\s*[:.]?\s*(?:\d{1,2}[./])?(\d{4})", full)
        if year_m:
            year = int(year_m.group(1))

        # Size (Größe: 25, MS, XS, ...)
        size = None
        size_m = re.search(r"Größe\s*[:.]?\s*([A-Z0-9]{1,4})", full)
        if size_m:
            size = size_m.group(1).strip()

        # Weight range (Gewichtsbereich: 70kg - 100kg)
        weight = None
        wt_m = re.search(r"Gewichtsbereich\s*[:.]?\s*(\d{2,3}\s*kg?\s*[-–]\s*\d{2,3}\s*kg)", full)
        if wt_m:
            weight = wt_m.group(1).replace(" ", "")

        # Condition (Zustand: ...)
        condition = None
        cond_m = re.search(r"Zustand\s*[:.]?\s*([^.]{3,40})", full)
        if cond_m:
            condition = cond_m.group(1).strip()[:60]

        # Category (EN A/B/C/D) – obvykle není explicitní, jen pokud ho prodejce uvedl
        cat_m = re.search(r"\bEN[-\s/]?[ABCD]\b", full, re.IGNORECASE)
        category = cat_m.group(0).upper().replace(" ", "").replace("/", "-") if cat_m else None

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=source["url"],  # Cumulus shop nemá individuální URL
            price_eur=price_eur,
            year=year,
            category=category,
            size=size,
            weight_range=weight,
            condition=condition,
        ))

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# CH – Paragliding Shop CH (Shopware: div.product-box, a[title]=produkt, CHF cena)
# https://paraglidingshop.ch/Occasionen/
# ──────────────────────────────────────────────────────────────────────────────

def scrape_paraglidingshop_ch(source: dict) -> list[dict]:
    results = []
    soup = _soup(source["url"])
    if soup is None:
        return results

    cards = soup.find_all("div", class_=re.compile(r"\bproduct-box\b", re.I))
    seen_hrefs = set()
    for card in cards:
        a = card.find("a", href=True, title=True)
        if not a:
            a = card.find("a", href=True)
        if not a:
            continue
        href = urljoin(source["url"], a.get("href", "").strip())
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        # Skip Shopware servisních / informačních stránek
        # (Kontakt, Impressum, AGB, Team, Testberichte, Kategorie listings)
        if re.search(r"/(Shop-Service|Gleitschirme/Occasionen-?Ex-?Demo)", href, re.I):
            continue
        # Reálný produkt má URL končící "/SW<digits>" (Shopware kód)
        if not re.search(r"/SW\d+/?$", href):
            continue

        title = (a.get("title") or a.get_text(" ", strip=True)).strip()
        if not title or len(title) < 5:
            continue
        # Skip non-wing items (vouchers, accessories)
        if re.search(r"\b(gutschein|voucher|helm|gurtzeug|harness|reserve|vario|skytraxx|funk|garmin)\b", title, re.IGNORECASE):
            continue

        text = card.get_text(" ", strip=True)
        # 1) Preferuj explicitní price element (Shopware: .product-price)
        price_eur = None
        price_el = card.select_one(".product-price") or card.select_one(".product-price-info")
        if price_el:
            price_eur = _parse_price_chf_to_eur(price_el.get_text(" ", strip=True))
        # 2) Fallback: € z celého textu
        if price_eur is None:
            price_eur = _parse_price_eur(text)
        # 3) Fallback: CHF z celého textu (pomalejší, méně přesné)
        if price_eur is None:
            price_eur = _parse_price_chf_to_eur(text)

        # Kategorie (EN A/B/C/D)
        cat_m = re.search(r"\bEN[-\s/]?[ABCD]\b", title + " " + text, re.IGNORECASE)
        category = cat_m.group(0).upper().replace(" ", "").replace("/", "-") if cat_m else None

        # Hmotnost / velikost z titulku: "(EN-B 80-100kg)"
        wt_m = re.search(r"(\d{2,3}\s*[-–]\s*\d{2,3})\s*kg", title, re.IGNORECASE)
        weight = wt_m.group(0).replace(" ", "") if wt_m else None
        size_m = re.search(r"\b(XXS|XS|S|M|ML|L|XL|XXL|\d{2})\b", title)
        size = size_m.group(1).upper() if size_m else None

        year = _parse_year(title + " " + text)

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=href,
            price_eur=price_eur,
            year=year,
            category=category,
            size=size,
            weight_range=weight,
        ))

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# CH – Swissgliders Fundgrube (WordPress Avia theme, article.slide-entry)
# https://swissgliders.ch/de/fundgrube/
# ──────────────────────────────────────────────────────────────────────────────

def scrape_swissgliders_ch(source: dict) -> list[dict]:
    results = []
    soup = _soup(source["url"])
    if soup is None:
        return results

    articles = soup.find_all("article", class_=re.compile(r"slide-entry", re.I))

    for art in articles:
        # Titulek a URL jsou v <a class="slide-image" title="..." href="...">
        a_tag = art.find("a", class_=re.compile(r"slide-image", re.I))
        if not a_tag:
            a_tag = art.find("a", href=re.compile(r"swissgliders\.ch/de/", re.I))
        if not a_tag:
            continue
        href = a_tag.get("href", "").strip()
        title = a_tag.get("title", "").strip()
        if not href or not title:
            continue
        # Skip the index page itself (title=="Fundgrube", URL ends with /fundgrube/)
        if re.search(r"/fundgrube/?$", href, re.I):
            continue
        # Strip "Fundgrube " prefix if present
        title = re.sub(r"^Fundgrube\s+", "", title, flags=re.IGNORECASE).strip()
        if len(title) < 5:
            continue

        art_text = art.get_text(" ", strip=True)
        # Datum: DD.MM.YYYY v textu inzerátu
        date_m = re.search(r"(\d{1,2})\.(\d{2})\.(20[012]\d)", art_text)
        date_listed = None
        if date_m:
            try:
                date_listed = datetime.strptime(
                    f"{date_m.group(1)}.{date_m.group(2)}.{date_m.group(3)}", "%d.%m.%Y"
                ).strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Hmotnostní rozsah z titulku nebo textu
        wt_m = re.search(r"(\d{2,3}\s*[-–]\s*\d{2,3}\s*kg)", title + " " + art_text, re.IGNORECASE)
        weight = wt_m.group(1).replace(" ", "") if wt_m else None

        # Velikost z titulku
        size_m = re.search(r"\b(XXS|XS|S|M|ML|L|XL|XXL|\d{2})\b", title)
        size = size_m.group(1).upper() if size_m else None

        year = _parse_year_strict(art_text, ["Baujahr", "Kaufjahr", "Jahr"])
        cat_m = re.search(r"\bEN\s*[-/]?\s*[ABCD]\b", art_text, re.IGNORECASE)
        category = cat_m.group(0).upper() if cat_m else None

        # Cena je jen na detail stránce (≤5 inzerátů → OK načíst)
        price_eur = None
        try:
            detail_r = _get(href)
            if detail_r:
                dsoup = BeautifulSoup(detail_r.text, "html.parser")
                dc = dsoup.find(["div", "section"], class_=re.compile(r"entry.content|post.content", re.I))
                dtext = (dc or dsoup.find("article") or dsoup).get_text(" ", strip=True)
                price_eur = _parse_price_eur(dtext)
                if price_eur is None:
                    # CHF cena: "Fr. 3500.-" nebo "CHF 1000" nebo "Verkaufspreis in CHF: 1000"
                    price_eur = _parse_price_chf_to_eur(dtext)
                if not category:
                    cat2 = re.search(r"\bEN\s*[-/]?\s*[ABCD]\b", dtext, re.IGNORECASE)
                    if cat2:
                        category = cat2.group(0).upper()
            time.sleep(1)
        except Exception:
            pass

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=href,
            price_eur=price_eur,
            year=year,
            category=category,
            size=size,
            weight_range=weight,
            date_listed=date_listed,
        ))

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# CH – Flugschule Alpstein Occasionen (Divi/ET Builder, div.et_pb_blurb_content)
# https://www.flugschule-alpstein.ch/occasionen/
# Inzeráty jsou v div.et_pb_blurb_content – vše na jedné stránce, bez detail URL
# ──────────────────────────────────────────────────────────────────────────────

def scrape_alpstein_ch(source: dict) -> list[dict]:
    results = []
    soup = _soup(source["url"])
    if soup is None:
        return results

    blurbs = soup.find_all("div", class_=re.compile(r"et_pb_blurb_content", re.I))

    for blurb in blurbs:
        text = blurb.get_text(" ", strip=True)
        if not text or len(text) < 8:
            continue

        # Titulek: text před první informací o stavu/barvě/velikosti/ceně
        title_m = re.match(r"^(.+?)(?:\s+Zustand:|\s+Farbe:|\s+Gr[öo]sse:|\s+Preis)", text)
        if title_m:
            title = title_m.group(1).strip()
        else:
            title = " ".join(text.split()[:6])
        if not title or len(title) < 4:
            continue

        # Přeskoč non-křídla: upoutávky, helmy, vaky, přístroje, záchranné padáky
        NON_WING_KW = [
            "skytraxx", "funkgerät", "funke", "handschuhe", "helm", "integralhelm",
            "gurtzeug", "packsack", "rucksack", "container", "rettungsschirme",
            "tasche", "bag", "variometer", "gps", "basisrausch", "ultracross",
            "frontcontainer", "schnellpacksack", "aria", "pilot alpin", "buffy",
            "altirando", "radical 4", "string ", "radical4", "delight", "strike",
            "nanga", "aria ", "liter",
        ]
        title_lower_nw = title.lower()
        if any(kw in title_lower_nw for kw in NON_WING_KW):
            continue

        # Kategorie z titulku: "(EN A)", "(EN B/C)"
        cat_m = re.search(r"EN\s*[-/]?\s*[ABCD](?:[/]\s*[ABCD])?", title, re.IGNORECASE)
        category = cat_m.group(0).upper() if cat_m else None
        # Alternativně z celého textu
        if not category:
            cat_m2 = re.search(r"\bEN\s*[-/]?\s*[ABCD]\b", text, re.IGNORECASE)
            if cat_m2:
                category = cat_m2.group(0).upper()

        # Velikost
        size_m = re.search(r"Gr[öo]sse[:\s]+([A-Z0-9]+)", text, re.IGNORECASE)
        size = size_m.group(1).upper() if size_m else None

        # Hmotnostní rozsah (v závorce za velikostí nebo v textu)
        wt_m = re.search(r"(\d{2,3}\s*kg\s*[-–]\s*\d{2,3}\s*kg|\d{2,3}\s*[-–]\s*\d{2,3}\s*kg)", text, re.IGNORECASE)
        weight = wt_m.group(0).replace(" ", "") if wt_m else None

        year = _parse_year_strict(text, ["Jahrgang", "Baujahr", "Jahr"])

        # Cena: EUR nebo CHF / Fr.
        price_eur = _parse_price_eur(text)
        if price_eur is None:
            price_eur = _parse_price_chf_to_eur(text)
            if price_eur is None:
                # "3500.-" formát
                p_m = re.search(r"Preis[:\s]+(\d+)[\.,\-]", text, re.IGNORECASE)
                if p_m:
                    try:
                        price_eur = round(float(p_m.group(1)) / 1.05, 0)
                    except ValueError:
                        pass

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=source["url"],  # Žádné individuální URL na této stránce
            price_eur=price_eur,
            year=year,
            category=category,
            size=size,
            weight_range=weight,
        ))

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


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

        # Modell sloupec (typicky cells[1]) má strukturu:
        #   <p><span>Modelname [Velikost]</span></p>
        #   <p>Popis…</p>
        # Vytáhneme modelové jméno čistě z prvního <p>/<span>, ne celý text.
        model_clean = None
        if len(cells) > 1:
            modell_cell = cells[1]
            first_p = modell_cell.find("p")
            if first_p:
                first_span = first_p.find("span")
                model_clean = (first_span or first_p).get_text(" ", strip=True)
            if not model_clean:
                model_clean = modell_cell.get_text(" ", strip=True).split("\n", 1)[0]

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
        # Model: použij čistý model_clean (bez popisu), ne plný text buňky
        model = model_clean or col("modell") or (texts[1] if len(texts) > 1 else "")
        baujahr = col("baujahr") or col("jahr") or col("bauj") or (texts[2] if len(texts) > 2 else "")
        weight = col("gewicht") or col("startgewicht") or col("startgew") or (texts[3] if len(texts) > 3 else "")
        kategorie = col("kategorie") or col("kat") or (texts[4] if len(texts) > 4 else "")
        preis = col("preis") or col("price") or (texts[5] if len(texts) > 5 else "")

        title = f"{manufacturer} {model}".strip()
        if not title or len(title) < 4:
            continue

        # Velikost z konce model line (čistý, bez popisu).
        # Flugsport formáty: "Geo-6 ML", "Serac RS XS", "Mescal-4 XS",
        # "Mito-2 RS, alle Größen" (= bez velikosti)
        size = None
        m_clean = model.strip().rstrip(",").strip()
        if not re.search(r"alle\s+Gr[öo]?[ÖöÄäéÃ]+en|alle\s+Gr.+", m_clean, re.IGNORECASE):
            size_m = re.search(r"\b(XXS|XS|S|M|ML|L|XL|XXL)\s*$", m_clean, re.IGNORECASE)
            if size_m:
                size = size_m.group(1).upper()
            else:
                # Číselný rozměrový kód (Advance: 22/24/26, Ozone: 25/27)
                size_n = re.search(r"\b(\d{2})\s*$", m_clean)
                if size_n:
                    size = size_n.group(1)

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
            size=size,
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
# Generický WooCommerce scraper – pro shopy s <li class="product"> strukturou
# Použití: fly_ikarus_ch, parafly_at
# ──────────────────────────────────────────────────────────────────────────────

def _scrape_woocommerce(source: dict) -> list[dict]:
    results = []
    soup = _soup(source["url"])
    if soup is None:
        return results

    products = soup.select(
        "li.product, ul.products li, .products .product, "
        ".product.type-product, div.product.type-product"
    )
    seen = set()
    for p in products:
        link = p.find("a", href=True)
        if not link:
            continue
        href = urljoin(source["url"], link["href"].strip())
        # Skip self-link na kategorii (WooCommerce loop někdy obsahuje category badge)
        if href.rstrip("/") == source["url"].rstrip("/"):
            continue
        if "/produkt/" not in href and "/product/" not in href:
            continue
        if href in seen:
            continue
        seen.add(href)

        title_el = p.select_one(
            ".woocommerce-loop-product__title, h2, h3, .product-title, .product_title"
        )
        title = title_el.get_text(strip=True) if title_el else ""
        if not title or len(title) < 4:
            continue

        # Skip non-křídla (sedačky, padáky, vario, helmy)
        if re.search(
            r"\b(gurtzeug|harness|sedacka|sedačka|reserve|notschirm|rettung|"
            r"helm|integralhelm|vario|skytraxx|garmin|funkger[äa]t|rucksack|"
            r"packsack|tasche|cockpit|gutschein|voucher|pod\b)\b",
            title, re.IGNORECASE,
        ):
            continue

        # Cena: WooCommerce má <span class="price"><bdi>1.234,00 €</bdi></span>
        # Někdy je tam přeškrtnutá + zlevněná → vezmi POSLEDNÍ cenu (= aktuální)
        price_eur = None
        price_el = p.select_one(".price")
        if price_el:
            # Vezmi všechny <bdi> = jednotlivé ceny v rámci span.price
            bdis = price_el.find_all("bdi")
            price_text = bdis[-1].get_text(" ", strip=True) if bdis else price_el.get_text(" ", strip=True)
            price_eur = _parse_price_eur(price_text)
            if price_eur is None:
                price_eur = _parse_price_chf_to_eur(price_text)

        # Kategorie EN A/B/C/D z titulku
        cat_m = re.search(r"\bEN[-\s/]?[ABCD]\b", title, re.IGNORECASE)
        category = cat_m.group(0).upper().replace(" ", "").replace("/", "-") if cat_m else None

        # Velikost: XS/S/M/ML/L/XL nebo číslo (21, 24, 27)
        size = None
        size_m = re.search(r"\b(XXS|XS|S|M|ML|L|XL|XXL)\b", title)
        if size_m:
            size = size_m.group(1).upper()
        else:
            size_n = re.search(r"\b(\d{2})\b", title)
            if size_n:
                size = size_n.group(1)

        # Hmotnostní rozsah (z titulku, např. "70-90kg")
        wt_m = re.search(r"(\d{2,3}\s*[-–]\s*\d{2,3}\s*kg)", title, re.IGNORECASE)
        weight = wt_m.group(1).replace(" ", "") if wt_m else None

        year = _parse_year(title)

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=href,
            price_eur=price_eur,
            year=year,
            category=category,
            size=size,
            weight_range=weight,
        ))

    logger.info("[%s] scraped %d listings", source["id"], len(results))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Generický Shopware scraper – .product-box karty
# Použití: hochries_de (Shopware 6), částečně podobně paraglidingshop_ch
# Title je v <a title="..."> nebo v product-name elementu.
# ──────────────────────────────────────────────────────────────────────────────

def _scrape_shopware(source: dict) -> list[dict]:
    results = []
    soup = _soup(source["url"])
    if soup is None:
        return results

    boxes = soup.select(".product-box, .product--box, .product-box-container")
    seen = set()
    for box in boxes:
        link = box.find("a", href=True)
        if not link:
            continue
        href = urljoin(source["url"], link["href"].strip())
        if href in seen:
            continue
        seen.add(href)

        # Title: nejprve a[title], pak .product-name / .product--title, pak link text
        title = (link.get("title") or "").strip()
        if not title:
            title_el = box.select_one(".product-name, .product--title, .product-box-title")
            if title_el:
                title = title_el.get_text(strip=True)
        if not title:
            # Fallback: vytáhni z URL (Shopware 6 SEO URL)
            title = re.sub(r"-", " ", href.rstrip("/").split("/")[-1])
        if not title or len(title) < 4:
            continue

        # Skip non-křídla
        if re.search(
            r"\b(gurtzeug|harness|reserve|notschirm|rettung|helm|integralhelm|"
            r"vario|skytraxx|garmin|funkger[äa]t|rucksack|packsack|tasche|"
            r"cockpit|gutschein|voucher|pod\b)\b",
            title, re.IGNORECASE,
        ):
            continue

        # Cena
        price_eur = None
        price_el = box.select_one(".product-price, .product--price, .price--default")
        if price_el:
            price_text = price_el.get_text(" ", strip=True)
            price_eur = _parse_price_eur(price_text)
            if price_eur is None:
                price_eur = _parse_price_chf_to_eur(price_text)

        # Kategorie EN A/B/C/D
        cat_m = re.search(r"\bEN[-\s/]?[ABCD]\b", title, re.IGNORECASE)
        category = cat_m.group(0).upper().replace(" ", "").replace("/", "-") if cat_m else None

        # Velikost
        size = None
        size_m = re.search(r"\b(XXS|XS|S|M|ML|L|XL|XXL)\b", title)
        if size_m:
            size = size_m.group(1).upper()
        else:
            size_n = re.search(r"\b(\d{2})\b", title)
            if size_n:
                size = size_n.group(1)

        # Hmotnost
        wt_m = re.search(r"(\d{2,3}\s*[-–]\s*\d{2,3}\s*kg)", title, re.IGNORECASE)
        weight = wt_m.group(1).replace(" ", "") if wt_m else None

        year = _parse_year(title)

        results.append(_listing(
            source_id=source["id"],
            source_name=source["name"],
            country=source["country"],
            title=title[:160],
            url=href,
            price_eur=price_eur,
            year=year,
            category=category,
            size=size,
            weight_range=weight,
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
    "paragliding_store_at":   scrape_paragliding_store_at,
    "gleitschirmschule_at":   _scrape_generic_shop,
    "parafly_at":             _scrape_woocommerce,
    "flugsport_de":           scrape_flugsport_de,
    "kleinanzeigen_de":       scrape_kleinanzeigen_de,
    "hochries_de":            _scrape_shopware,
    "swissgliders_ch":        scrape_swissgliders_ch,
    "paraglidingshop_ch":     scrape_paraglidingshop_ch,
    "alpstein_ch":            scrape_alpstein_ch,
    "fly_ikarus_ch":          _scrape_woocommerce,
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
