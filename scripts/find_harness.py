# -*- coding: utf-8 -*-
"""
Jednorázový průzkum bazarů na sedačky (harness/Gurtzeug).

Cíl: pilot ~185 cm, velikost M (akceptuje M, ML, "medium", 80-100 kg),
všechny typy včetně cocoonu, rok ≥ 2019, cena ≤ 1500 EUR (orientačně).

Použití:
    cd paraglide
    python -m scripts.find_harness                # výpis matchů
    python -m scripts.find_harness --all          # bez filtru velikosti/roku
    python -m scripts.find_harness --csv out.csv  # uloží do CSV

Výstup: tabulka v terminálu, seřazená podle ceny.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Reuse helpery z bazar_watcher
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bazar_watcher import scrapers as bw  # noqa: E402

# Inicializace sdílené HTTP session
bw._session = requests.Session()
bw._session.headers.update(bw.HEADERS)

CURRENT_YEAR = 2026

# ───────────────────────────────────────────────────────────────────────
# Konfigurace lovu
# ───────────────────────────────────────────────────────────────────────

# URL kandidáti pro každý zdroj — zkusíme po pořadí, vezmeme první 200.
SOURCES = [
    {
        "id": "paragliding_bazar_cz",
        "country": "CZ",
        "candidates": [
            "https://paragliding-bazar.cz/cs/harnesses/",
            "https://paragliding-bazar.cz/cs/sedacky/",
            "https://paragliding-bazar.cz/cs/postroje/",
        ],
        "scraper": "paragliding_bazar",
    },
    {
        "id": "bazos_cz",
        "country": "CZ",
        "candidates": [
            "https://sport.bazos.cz/inzeraty/paragliding-sedacka/",
            "https://sport.bazos.cz/inzeraty/sedacka/",
            "https://sport.bazos.cz/inzeraty/postroj/",
        ],
        "scraper": "bazos",
    },
    {
        "id": "paragliding_store_at",
        "country": "AT",
        "candidates": [
            "https://www.paragliding-store.at/shop/gebrauchtmarkt-used-stuff/used-harness/",
            "https://www.paragliding-store.at/shop/gebrauchtmarkt-used-stuff/used-gurtzeug/",
            "https://www.paragliding-store.at/shop/gebrauchtmarkt-used-stuff/",  # umbrella, filtrujeme keywordem
        ],
        "scraper": "hproduct",
    },
    {
        "id": "parafly_at",
        "country": "AT",
        "candidates": [
            "https://shop.parafly.at/produkt-kategorie/gebrauchtmarkt/gurtzeug/",
            "https://shop.parafly.at/produkt-kategorie/gebrauchtmarkt/",
        ],
        "scraper": "generic_shop",
    },
    {
        "id": "alpstein_ch",
        "country": "CH",
        "candidates": [
            "https://www.alpstein.ch/de/secondhand/gurtzeuge/",
            "https://www.alpstein.ch/de/secondhand/",
        ],
        "scraper": "generic_shop",
    },
    {
        "id": "abc_paragliding_cz",
        "country": "CZ",
        "candidates": [
            "https://www.abcparagliding.cz/bazar/14-prodam/",
            "https://www.abcparagliding.cz/bazar/15-prodam/",
            "https://www.abcparagliding.cz/bazar/",
        ],
        "scraper": "abc_table",
    },
    {
        "id": "mamekridla_cz",
        "country": "CZ",
        "candidates": [
            "https://mamekridla.cz/sedacky/",
            "https://mamekridla.cz/kategorie/sedacky/",
            "https://mamekridla.cz/postroje/",
        ],
        "scraper": "generic_shop",
    },
    {
        "id": "willhaben_at",
        "country": "AT",
        "candidates": [
            "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz?keyword=gleitschirm+gurtzeug",
            "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz?keyword=paragliding+gurtzeug",
        ],
        "scraper": "willhaben_html",
    },
    {
        "id": "kleinanzeigen_de",
        "country": "DE",
        "candidates": [
            "https://www.kleinanzeigen.de/s-gleitschirm-gurtzeug/k0",
            "https://www.kleinanzeigen.de/s-suchanfrage.html?keywords=gleitschirm+gurtzeug",
        ],
        "scraper": "kleinanzeigen_html",
    },
    {
        "id": "swissgliders_ch",
        "country": "CH",
        "candidates": [
            "https://swissgliders.ch/occasionen/gurtzeuge/",
            "https://swissgliders.ch/produkt-kategorie/occasionen/gurtzeug/",
            "https://swissgliders.ch/category/gebraucht-gurtzeug/",
        ],
        "scraper": "generic_shop",
    },
    {
        "id": "paraglidingshop_ch",
        "country": "CH",
        "candidates": [
            "https://paraglidingshop.ch/de/occasionen/occasion-gurtzeuge",
            "https://paraglidingshop.ch/de/gurtzeug-occasionen",
        ],
        "scraper": "generic_shop",
    },
]

# Známé modely sedaček (pro detekci v titulku, když chybí explicitní kategorie).
HARNESS_BRANDS = [
    # generické značky / klíčová slova
    "harness", "gurtzeug", "sedačka", "sedacka", "postroj", "selette",
    # výrobci & modely
    "kortel", "kuik", "karver",
    "woody valley", "wani", "x-rated", "haska", "gto",
    "supair", "sup'air", "altirando", "delight", "radical", "skypper", "strike",
    "advance", "easiness", "lightness", "axess", "success",
    "ozone", "ozium", "exoceat", "submarine", "forza",
    "skywalk", "range", "cult",
    "gin", "yeti", "genie", "verso",
    "niviuk", "kargo", "kuyma",
    "nova", "itus", "montis",
    "kanibal", "neo", "string",
    "independence", "evo", "sky",
    "air design", "airdesign",
    "ava sport", "airbag",
    "cocoon", "kokon",
]

SIZE_M_PATTERNS = [
    r"\bM\b", r"\bM-?L\b", r"\bMS\b", r"\bSM\b",
    r"\bmedium\b",
    # pilotní hmotnost (in-flight) typická pro M: 80-100 kg
    r"\b(8[0-9]|9[0-9]|100)\s*[-–]\s*(9[0-9]|10[0-9]|11[0-5])\s*kg",
]


def _looks_like_harness(text: str) -> bool:
    t = text.lower()
    return any(b in t for b in HARNESS_BRANDS)


def _looks_size_m(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in SIZE_M_PATTERNS)


# ───────────────────────────────────────────────────────────────────────
# Scrapery (zjednodušené verze ze základního modulu)
# ───────────────────────────────────────────────────────────────────────

def _probe(candidates: list[str]) -> str | None:
    for url in candidates:
        r = bw._get(url)
        if r is not None and r.status_code == 200 and len(r.text) > 1000:
            return url
    return None


def scrape_paragliding_bazar(url: str, country: str) -> list[dict]:
    out, seen = [], set()
    base = "https://paragliding-bazar.cz"
    page = 1
    while True:
        page_url = url if page == 1 else f"{url}?page={page}"
        soup = bw._soup(page_url)
        if soup is None:
            break
        links = soup.find_all("a", href=re.compile(r"/cs/offering/"))
        if not links:
            break
        before = len(out)
        for a in links:
            href = a.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            text = a.get_text(" ", strip=True)
            out.append({
                "source": "paragliding_bazar_cz", "country": country,
                "title": text[:160], "url": urljoin(base, href),
                "price_eur": bw._parse_price_eur(text),
                "year": bw._parse_year(text),
                "raw": text,
            })
        if len(out) == before:
            break
        page += 1
        if page > 5:
            break
    return out


def scrape_bazos(url: str, country: str) -> list[dict]:
    out = []
    soup = bw._soup(url)
    if soup is None:
        return out
    items = soup.select("div.inzeraty") or soup.find_all("div", class_=re.compile(r"\binzerat", re.I))
    for box in items:
        a = box.select_one("h2.nadpis a, h2 a, div.inzeratynadpis a")
        if not a:
            continue
        href = a.get("href", "")
        if not href:
            continue
        title = a.get_text(" ", strip=True)
        text = box.get_text(" ", strip=True)
        # bazoš píše ceny v Kč
        czk = re.search(r"([\d\s]+)\s*Kč", text)
        price_eur = None
        if czk:
            try:
                price_eur = round(float(re.sub(r"\s", "", czk.group(1))) / 25, 0)
            except ValueError:
                pass
        out.append({
            "source": "bazos_cz", "country": country,
            "title": title[:160], "url": urljoin("https://sport.bazos.cz", href),
            "price_eur": price_eur,
            "year": bw._parse_year(text),
            "raw": text,
        })
    return out


def scrape_hproduct(url: str, country: str, source_id: str) -> list[dict]:
    out = []
    soup = bw._soup(url)
    if soup is None:
        return out
    for prod in soup.select(".hproduct, .j-product, article.product, .product"):
        title_el = prod.select_one(".fn, .title, h2, h3, a")
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        link_el = prod.find("a", href=True)
        href = link_el["href"] if link_el else url
        text = prod.get_text(" ", strip=True)
        out.append({
            "source": source_id, "country": country,
            "title": title[:160], "url": urljoin(url, href),
            "price_eur": bw._parse_price_eur(text),
            "year": bw._parse_year(text),
            "raw": text,
        })
    return out


def scrape_generic_shop(url: str, country: str, source_id: str) -> list[dict]:
    out, seen = [], set()
    soup = bw._soup(url)
    if soup is None:
        return out
    selectors = [
        "li.product", "div.product", "article.product",
        ".product-item", ".woocommerce-LoopProduct-link",
        "li.et_pb_gallery_item", "div.et_pb_blurb",
    ]
    cards = []
    for sel in selectors:
        cards.extend(soup.select(sel))
    if not cards:
        cards = [a.find_parent() for a in soup.select("a.woocommerce-LoopProduct-link, a.product")]
    for card in cards:
        if card is None:
            continue
        link_el = card.find("a", href=True)
        if not link_el:
            continue
        href = link_el["href"]
        if href in seen:
            continue
        seen.add(href)
        title = (card.select_one("h2, h3, .woocommerce-loop-product__title") or link_el).get_text(" ", strip=True)
        text = card.get_text(" ", strip=True)
        price_eur = bw._parse_price_eur(text)
        if price_eur is None and country == "CH":
            price_eur = bw._parse_price_chf_to_eur(text)
        out.append({
            "source": source_id, "country": country,
            "title": title[:160], "url": urljoin(url, href),
            "price_eur": price_eur,
            "year": bw._parse_year(text),
            "raw": text,
        })
    return out


def scrape_abc_table(url: str, country: str) -> list[dict]:
    out = []
    soup = bw._soup(url)
    if soup is None:
        return out
    for row in soup.select("table tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        text = " | ".join(cells)
        if not _looks_like_harness(text):
            continue
        out.append({
            "source": "abc_paragliding_cz", "country": country,
            "title": text[:160], "url": url,
            "price_eur": bw._parse_price_eur(text),
            "year": bw._parse_year(text),
            "raw": text,
        })
    return out


def scrape_kleinanzeigen(url: str, country: str) -> list[dict]:
    out = []
    soup = bw._soup(url)
    if soup is None:
        return out
    for item in soup.select("article.aditem, li.ad-listitem"):
        a = item.select_one("a.ellipsis, h2 a, a[href*='/s-anzeige/']")
        if not a:
            continue
        href = a.get("href", "")
        title = a.get_text(" ", strip=True)
        text = item.get_text(" ", strip=True)
        out.append({
            "source": "kleinanzeigen_de", "country": country,
            "title": title[:160], "url": urljoin("https://www.kleinanzeigen.de", href),
            "price_eur": bw._parse_price_eur(text),
            "year": bw._parse_year(text),
            "raw": text,
        })
    return out


def scrape_willhaben_html(url: str, country: str) -> list[dict]:
    out = []
    soup = bw._soup(url)
    if soup is None:
        return out
    for a in soup.select("a[href*='/iad/kaufen-und-verkaufen/d/']"):
        href = a.get("href", "")
        text = a.get_text(" ", strip=True)
        if not text:
            continue
        out.append({
            "source": "willhaben_at", "country": country,
            "title": text[:160], "url": urljoin("https://www.willhaben.at", href),
            "price_eur": bw._parse_price_eur(text),
            "year": bw._parse_year(text),
            "raw": text,
        })
    return out


SCRAPERS = {
    "paragliding_bazar": lambda u, c, sid: scrape_paragliding_bazar(u, c),
    "bazos": lambda u, c, sid: scrape_bazos(u, c),
    "hproduct": scrape_hproduct,
    "generic_shop": scrape_generic_shop,
    "abc_table": lambda u, c, sid: scrape_abc_table(u, c),
    "kleinanzeigen_html": lambda u, c, sid: scrape_kleinanzeigen(u, c),
    "willhaben_html": lambda u, c, sid: scrape_willhaben_html(u, c),
}


# ───────────────────────────────────────────────────────────────────────
# Hlavní run
# ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="Bez filtru velikosti M / roku")
    ap.add_argument("--max-price", type=int, default=2000)
    ap.add_argument("--min-year", type=int, default=2017)
    ap.add_argument("--strict-size", action="store_true",
                    help="Vyžaduj výslovně velikost M (default: neznámá velikost tež prochází)")
    ap.add_argument("--csv", type=str, help="Uložit výsledky do CSV")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    all_listings: list[dict] = []
    print(f"Probing {len(SOURCES)} sources…\n")
    for src in SOURCES:
        url = _probe(src["candidates"])
        if not url:
            print(f"  ✗ {src['id']:24s} (žádný URL kandidát nevrátil 200)")
            continue
        scraper = SCRAPERS[src["scraper"]]
        try:
            items = scraper(url, src["country"], src["id"])
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {src['id']:24s} chyba: {exc}")
            if args.debug:
                import traceback
                traceback.print_exc()
            continue
        print(f"  ✓ {src['id']:24s} {url}  →  {len(items)} položek")
        all_listings.extend(items)

    print(f"\nCelkem {len(all_listings)} položek před filtrací.\n")

    # Filtrace
    matches = []
    for it in all_listings:
        text = (it.get("title") or "") + " " + (it.get("raw") or "")

        # Musí být sedačka
        if not _looks_like_harness(text):
            continue

        # Cena
        price = it.get("price_eur")
        if price is not None and price > args.max_price:
            continue
        if price is not None and price < 100:  # haraburdí
            continue

        # Velikost M (pokud --all, přeskoč)
        if not args.all:
            has_size_marker = re.search(r"\b(XS|S|M|L|XL|XXL|small|medium|large)\b", text, re.IGNORECASE)
            size_m_ok = _looks_size_m(text)
            if args.strict_size:
                if not size_m_ok:
                    continue
            else:
                # Propouštíme: M-shody, nebo položky bez jakéhokoliv size markeru (= manuálně dohledat)
                # Vyřazujeme jen ty, které explicitně uvádějí XS/S/L/XL bez M.
                if has_size_marker and not size_m_ok:
                    continue
            year = it.get("year")
            if year is not None and year < args.min_year:
                continue

        matches.append(it)

    # Dedup podle URL
    seen_urls = set()
    deduped = []
    for m in matches:
        u = m.get("url")
        if u in seen_urls:
            continue
        seen_urls.add(u)
        deduped.append(m)
    matches = deduped

    # Seřaď podle ceny (None na konec)
    matches.sort(key=lambda x: (x.get("price_eur") is None, x.get("price_eur") or 0))

    # Výpis
    print("=" * 100)
    print(f"NALEZENO {len(matches)} POTENCIÁLNĚ ZAJÍMAVÝCH SEDAČEK")
    print("=" * 100)
    for m in matches:
        price = m.get("price_eur")
        price_s = f"{int(price):>5} €" if price else "    ?"
        year = m.get("year") or "----"
        print(f"\n  [{m['source']:22s}] {price_s}  {year}")
        print(f"  {m['title']}")
        print(f"  {m['url']}")

    if args.csv:
        path = Path(args.csv)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["source", "country", "price_eur", "year", "title", "url"])
            w.writeheader()
            for m in matches:
                w.writerow({k: m.get(k) for k in w.fieldnames})
        print(f"\n→ CSV: {path}")


if __name__ == "__main__":
    main()
