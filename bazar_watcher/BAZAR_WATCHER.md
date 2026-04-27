# 🪂 Bazar Watcher — vývojářská dokumentace

Detailní popis modulu `bazar_watcher/`. Pro projektový přehled (instalace, GitHub Actions, datový model) viz [hlavní README](../README.md).

---

## Obsah

- [Architektura a datový tok](#architektura-a-datový-tok)
- [Soubory modulu](#soubory-modulu)
- [Konfigurace](#konfigurace)
  - [STORAGE_FILTER](#storage_filter)
  - [ALERT_PROFILES](#alert_profiles)
  - [SOURCES](#sources)
- [CLI flagy](#cli-flagy)
- [Jak fungují scrapery](#jak-fungují-scrapery)
- [Cenové parsery](#cenové-parsery)
- [Přidání nového zdroje](#přidání-nového-zdroje)
- [Přidání nového alert profilu](#přidání-nového-alert-profilu)
- [Excel report — co je v jakém listu](#excel-report--co-je-v-jakém-listu)
- [Debugging](#debugging)
- [Známé problémy a TODO](#známé-problémy-a-todo)

---

## Architektura a datový tok

```
┌──────────────┐      ┌────────────────────────────────┐
│  config.py   │      │ run.py (CLI / GitHub Actions)  │
│  SOURCES     │ ◀──── │  parse_args()                  │
│  ALERT_*     │      │  load_existing_listings()       │
│  STORAGE_*   │      └─────────────┬──────────────────┘
└──────────────┘                    │
                                    ▼
                       ┌────────────────────────────┐
                       │ scrapers.run_all_scrapers() │
                       │  for src in SOURCES:        │
                       │    _SCRAPERS[src.id](src)   │ ← per-source scraper
                       └─────────────┬──────────────┘
                                     │ list[dict]  (raw, ze všech zdrojů)
                                     ▼
                       ┌────────────────────────────┐
                       │ storage.apply_storage_filter│ ← propustí EN A + EN B
                       └─────────────┬──────────────┘
                                     │ filtrovaný list[dict]
                                     ▼
                       ┌────────────────────────────┐
                       │ storage.find_new()          │ ← dedup vs. listings.csv
                       │   (source_id, url)          │
                       │   nebo (source_id, title)   │
                       └─────────────┬──────────────┘
                                     │ jen nové od posledního běhu
                                     ▼
                       ┌────────────────────────────┐
                       │ storage.save() →            │
                       │   listings.csv              │ ← akumuluje
                       │   listings.xlsx             │ ← přepíše
                       └─────────────┬──────────────┘
                                     │
                                     ▼
                       ┌────────────────────────────┐
                       │ for profile in ALERT_PROFILES:│
                       │   matches = apply_profile_  │
                       │     filter(new, profile)    │
                       └─────────────┬──────────────┘
                                     │
                                     ▼
                       ┌────────────────────────────┐
                       │ notify.send_email_per_      │
                       │   recipient(profile_matches)│
                       └────────────────────────────┘
```

---

## Soubory modulu

| Soubor | Co obsahuje |
|---|---|
| [\_\_init\_\_.py](__init__.py) | Prázdný marker, dělá z modulu Python balíček |
| [config.py](config.py) | `STORAGE_FILTER`, `EN_A_WINGS`/`LOW_B_WINGS`/`MID_B_WINGS`, `ALERT_PROFILES`, `SOURCES` |
| [scrapers.py](scrapers.py) | HTTP session, helpery `_listing`, `_parse_price_eur`, `_parse_price_chf_to_eur`, per-source funkce, registry `_SCRAPERS`, `run_all_scrapers()` |
| [storage.py](storage.py) | `load_existing_listings`, `apply_storage_filter`, `apply_profile_filter`, `find_new`, `save`, `_write_excel` |
| [notify.py](notify.py) | `send_email_per_recipient(profile_matches, force=False)` — HTML render + SMTP |
| [run.py](run.py) | CLI orchestrátor (argparse + main flow) |
| [requirements.txt](requirements.txt) | Závislosti modulu (subset) |

---

## Konfigurace

### STORAGE_FILTER

Co se ukládá do CSV/Excel. Default: vše od mid-B níže.

```python
STORAGE_FILTER = {
    "categories": [
        "EN A", "EN/A",
        "EN B", "EN/B",
        "DHV 1", "LTF 1",
        "DHV 1-2", "LTF 1-2", "DHV 1/2",
        "B-G", "B-R",   # Flugsport DE klasifikace
    ],
    "min_price_eur": 150,   # vyřadí absolutní haraburdí (např. 1 € testy)
}
```

EN C, EN D, CCC, ACR (=competition) se neukládají vůbec — `apply_storage_filter` má explicit blocklist přes `exclude_cats` v profilech.

### ALERT_PROFILES

Komu pošleme e-mail. Lista dictů, každý profil samostatně.

```python
ALERT_PROFILES = [
    {
        "name": "Martin – M mid-B a níže",
        "email": None,                  # None = ALERT_EMAIL z env
        "max_category": "mid-B",        # "A" | "low-B" | "mid-B"
        "sizes": ["M", "ML"],           # None = libovolná velikost
        "max_price_eur": None,          # None = bez stropu
        "min_year": CURRENT_YEAR - 5,
        "countries": None,              # None = všechny (CZ/AT/CH/DE)
    },
    {
        "name": "Kamarádka – XS/S EN A",
        "email": None,
        "max_category": "A",
        "sizes": ["XS", "S", "22", "24", "25", "26"],
        "max_price_eur": 1500,
        "min_year": CURRENT_YEAR - 6,
        "countries": None,
    },
]
```

**Hodnoty `max_category` — kategorie zahrnuté v daném levelu:**

| `max_category` | Co zahrnuje |
|---|---|
| `"A"` | jen EN A |
| `"low-B"` | EN A + low-B (Rush, Ion, Epsilon, Hook, Geo, Tonic, …) |
| `"mid-B"` | EN A + low-B + mid-B (Mentor, Sigma, Delta, Chili, Peak, …) |

Mapování modelů → level je v `KNOWN_WINGS` listech v [config.py](config.py). Pokud inzerát neuvádí `category` field, scraper porovná `title` proti seznamům.

**Více příjemců:**
Profily s různým `email` se posílají na různé adresy. Profily se stejným `email` se sloučí do jedné zprávy se sekcemi (jeden e-mail, více sekcí).

### SOURCES

Lista nakonfigurovaných zdrojů. Klíčové fieldy:

```python
{
    "id": "paragliding_store_at",     # unikátní, používá se jako lookup do _SCRAPERS
    "name": "Paragliding Store AT – Used",
    "country": "AT",                  # CZ / AT / DE / CH
    "url": "https://...",             # vstupní URL
    "enabled": True,                  # False = scraper se přeskočí
    "trusted": True,                  # volitelný flag (pro budoucí logic)
    "notes": "...",                   # popisek pro člověka
}
```

Aktuální stav (13 zdrojů, 11 enabled):

| ID | Země | Platforma | Stav |
|---|---|---|---|
| paragliding_bazar_cz_b | CZ | bazar (paginace) | ✅ |
| paragliding_bazar_cz_a | CZ | bazar (paginace) | ✅ |
| bazos_cz | CZ | Bazoš (paginace) | ✅ |
| mamekridla_cz | CZ | e-shop | ✅ |
| willhaben_at | AT | JSON API | ⚠️ |
| paragliding_store_at | AT | Cumulus CMS / Jimdo (`hproduct`) | ✅ |
| gleitschirmschule_at | AT | JS Shopware | ❌ disabled |
| flugsport_de | DE | HTML tabulka | ✅ |
| kleinanzeigen_de | DE | Atom feed | ⚠️ |
| dhv_de | DE | login required | ❌ disabled |
| swissgliders_ch | CH | WordPress (Avia) | ✅ |
| paraglidingshop_ch | CH | Shopware | ✅ |
| alpstein_ch | CH | Divi/ET Builder | ✅ |

---

## CLI flagy

```text
python -m bazar_watcher.run [FLAGS]

  --dry-run        Scrape + filtr, nic se neukládá ani neposílá. Užitečné pro testování.
  --no-notify      Scrape + filtr + uložit, ale neposílat e-mail.
  --force-notify   Pošli e-mail i když nejsou žádné nové matching inzeráty
                   (jen "běh OK" notifikace).
  --filter-only    Přeskočí scrape, použije existující listings.csv.
                   Užitečné po změně ALERT_PROFILES — zjistíš matching ze starých dat.
  --reimport       Profilový matching počítá ze VŠECH aktuálně viditelných inzerátů,
                   ne jen z nových. Pro počáteční import nebo když změníš filtr.
                   (CSV se stále děduplikuje standardně.)
```

---

## Jak fungují scrapery

Každý zdroj má vlastní funkci `scrape_<id>(source: dict) -> list[dict]`. Vrací listings ve standardizovaném formátu (klíče: `source_id`, `country`, `title`, `url`, `price_eur`, `year`, `category`, `size`, `weight_range`, `condition`, `date_listed`).

**Společné helpery v scrapers.py:**

| Helper | Účel |
|---|---|
| `_session` | Sdílená `requests.Session` s `HEADERS` |
| `_get(url, **kw)` | GET s 3× retry, exponenciální backoff |
| `_listing(source, **fields)` | Vytvoří dict s defaulty (None pro chybějící fieldy, `date_found` = dnešek) |
| `_parse_price_eur(text)` | DE/AT/CZ EUR formát |
| `_parse_price_chf_to_eur(text)` | CHF → EUR konverze (1 CHF = `1.0/1.05` EUR) |
| `_extract_year(text)` | Najde rok 19xx/20xx v textu |
| `_extract_size(text)` | XS/S/M/L/XL nebo numerické 22-29 |
| `_extract_category(text)` | EN A/B/C/D, DHV/LTF varianty |

**Specifické platformy a jak je scrapeme:**

| Platforma | Selektor | Příklad zdroje |
|---|---|---|
| Bazos | `div.inzeraty` + detail page | bazos_cz |
| WooCommerce | `li.product` / `div.product` | mamekridla_cz |
| Shopware | `div.product-box` + `.product-price` | paraglidingshop_ch |
| Cumulus / Jimdo | `class="hproduct"` microformat | paragliding_store_at |
| WordPress Avia | `article.slide-entry` | swissgliders_ch |
| Divi/ET Builder | `div.et_pb_blurb_content` | alpstein_ch |
| HTML tabulka | `table tr td` | flugsport_de |
| Atom feed | `feedparser`-style XML | kleinanzeigen_de |
| JSON API | přímo `response.json()` | willhaben_at |

---

## Cenové parsery

### `_parse_price_eur(text)`

Pokrývá DE/AT/CZ formáty:

```
1.200,00 €     → 1200.0
820 EUR        → 820.0
1 846,53 EUR   → 1846.53
EUR 1.500,-    → 1500.0
820,-          → 820.0  (jen pokud je nablízku € nebo EUR)
```

### `_parse_price_chf_to_eur(text)`

CHF input → EUR output. Konstanta `CHF_TO_EUR = 1.0 / 1.05` (≈ 0.952).

**Strategie (v pořadí priority):**

1. Hledá keyword `Verkaufspreis` + číslo poblíž (bez ohledu na pořadí CHF/Fr.)
2. Jinak najde všechny výskyty `CHF` nebo `Fr.` v textu (před i za číslem)
3. Z kandidátů vrátí **první** v rozsahu 50–100 000 (eliminuje placeholder „0.00")

**Podporované formáty:**

```
CHF 2'800.00       → 2800 × 0.952 = 2667
CHF 1’990.00       → 1990 × 0.952 = 1895   (curly apostrof U+2019)
Fr. 999.00         → 999 × 0.952 = 951
1000CHF            → 1000 × 0.952 = 952
Verkaufspreis CHF: 1000   → 952
CHF 0,00 (Verkaufspreis 980)   → preferuje 980 (Verkaufspreis keyword)
```

**Filtrace placeholderu „0,00 €":** `apply_storage_filter` má `min_price_eur = 150`, takže 0,00 ze storefrontu (kde je cena jen v popisu) propadne sítem; `_parse_price_chf_to_eur` má vlastní range filter 50–100k.

---

## Přidání nového zdroje

1. **Přidej zdroj do `SOURCES`** v [config.py](config.py):
   ```python
   {
       "id": "novy_shop_cz",
       "name": "Novy Shop CZ",
       "country": "CZ",
       "url": "https://example.cz/bazar/",
       "enabled": True,
       "notes": "Statický HTML, BS4",
   },
   ```

2. **Napiš scraper** v [scrapers.py](scrapers.py):
   ```python
   def scrape_novy_shop_cz(source: dict) -> list[dict]:
       resp = _get(source["url"])
       soup = BeautifulSoup(resp.text, "html.parser")
       results = []
       for card in soup.select("div.product"):
           title = card.select_one("h3").get_text(strip=True)
           price = _parse_price_eur(card.get_text())
           results.append(_listing(
               source,
               title=title,
               url=urljoin(source["url"], card.select_one("a")["href"]),
               price_eur=price,
               year=_extract_year(title),
           ))
       return results
   ```

3. **Zaregistruj** v `_SCRAPERS` na konci [scrapers.py](scrapers.py):
   ```python
   _SCRAPERS = {
       ...
       "novy_shop_cz": scrape_novy_shop_cz,
   }
   ```

4. **Otestuj:**
   ```powershell
   python -m bazar_watcher.run --dry-run 2>&1 | Select-String "novy_shop_cz"
   ```

5. Aktualizuj tabulku zdrojů v [hlavním README](../README.md) a v sekci [SOURCES](#sources) výše.

---

## Přidání nového alert profilu

Edituj jen `ALERT_PROFILES` v [config.py](config.py). Žádný jiný soubor není potřeba měnit.

```python
{
    "name": "Kamarád – low-B L/XL, do 2000€",
    "email": "kamarad@example.com",   # nebo None pro default ALERT_EMAIL
    "max_category": "low-B",
    "sizes": ["L", "ML", "XL", "28", "29"],
    "max_price_eur": 2000,
    "min_year": CURRENT_YEAR - 4,
    "countries": ["CZ", "AT", "DE"],   # bez CH
},
```

Otestuj:
```powershell
python -m bazar_watcher.run --filter-only --no-notify   # vypíše matching pro každý profil
```

---

## Excel report — co je v jakém listu

`listings.xlsx` se generuje při každém běhu. Listy:

| List | Obsah |
|---|---|
| **Vsechny inzeraty** | Kompletní `listings.csv` (akumulovaná historie) |
| **MM-RRRR** (např. `04-2026`) | Inzeráty z aktuálního měsíce (filtr přes `date_listed`, fallback `date_found`) |
| **Dnes pridane** | Jen ty, které tento běh přidal nově |
| **<profil1 name>** | Matching profilu 1 (po sanitaci znaků nepovolených v Excel sheet names) |
| **<profil2 name>** | Matching profilu 2 |
| … | (jeden list per `ALERT_PROFILES`) |

Sheet names v Excelu nesmí obsahovat `\ / * ? : [ ]` — `_write_excel` je nahrazuje pomlčkou.

---

## Debugging

### Test jednoho scraperu

```python
from bazar_watcher import scrapers, config
import requests, logging

logging.basicConfig(level=logging.DEBUG)
scrapers._session = requests.Session()
scrapers._session.headers.update(scrapers.HEADERS)

source = next(s for s in config.SOURCES if s["id"] == "swissgliders_ch")
results = scrapers._SCRAPERS[source["id"]](source)
print(f"Nalezeno: {len(results)}")
for r in results[:5]:
    print(r)
```

### Test cenového parseru

```python
from bazar_watcher.scrapers import _parse_price_chf_to_eur

print(_parse_price_chf_to_eur("CHF 2'800.00"))            # 2667.0
print(_parse_price_chf_to_eur("Fr. 1’990.00"))             # 1895.0
print(_parse_price_chf_to_eur("Verkaufspreis: 1000CHF"))   # 952.0
```

### Excel zápis bez scrapingu

```python
from bazar_watcher import storage
import pandas as pd
df = pd.read_csv("data/bazar_watcher/listings.csv")
storage._write_excel(df, [], {})
```

---

## Známé problémy a TODO

- [ ] **DHV Gebrauchtmarkt** — vyžaduje DHV členský login. Možnost: cookies + Selenium.
- [ ] **gleitschirmschule_at** — JS-rendered Shopware. Vyžadovalo by Playwright headless.
- [ ] **kleinanzeigen_de** — Atom feed občas vrací HTTP 500 (~1× za týden). Aktuálně 3× retry s backoffem.
- [ ] **willhaben_at** — JSON API občas neaktualizuje výsledky (vrátí 0 listings i když přes browser jdou vidět). Možná je potřeba změnit User-Agent header.
- [ ] **CZK → EUR** — Bazoš ceny jsou v Kč, přepočet je orientační (×0.04). Ideálně přidat ECB API pro live kurz (i pro CHF→EUR konstantu).
- [ ] **Velikostní normalizace** — někteří výrobci používají numerické (Advance Alpha 24, Ozone Rush 25), jiní písmena (Skywalk Tonic S). Mapping je v `_extract_size`, ale není kompletní.
- [ ] **Telegram / Pushover notifikace** — alternativa k SMTP.
- [ ] **Excel autofilter** — přidat `auto_filter.ref` na všech listech pro pohodlnější browsing.

---

*Poslední revize: 2026-04-27*
