# 🪂 Bazar Křídel Watcher

Automatický hlídač bazarů s paraglidingovými křídly pro CZ, AT, DE a CH.
Každý den (přes GitHub Actions) projde všechny bazary, uloží inzeráty do CSV/Excel
a pošle email pokud najde nové Low-B křídlo (EN B, max 5 let staré).

---

## Obsah

- [Co to dělá](#co-to-dělá)
- [Struktura souborů](#struktura-souborů)
- [Filtrovací parametry](#filtrovací-parametry)
- [Sledované bazary](#sledované-bazary)
- [Rychlý start (lokálně)](#rychlý-start-lokálně)
- [GitHub Actions setup](#github-actions-setup)
- [Přidání nového zdroje](#přidání-nového-zdroje)
- [Stav scraperů](#stav-scraperů)
- [TODO / Known issues](#todo--known-issues)

---

## Co to dělá

1. Každý den v **6:00 UTC** GitHub Actions spustí scraper
2. Projde všechny **11 bazarů** (CZ/AT/DE/CH)
3. Porovná nalezené inzeráty s historií v `data/bazar_watcher/listings.csv`
4. Nové inzeráty uloží a **filtruje dle parametrů** (EN B, rok ≥ 2021, cena ≥ 200 €)
5. Pokud existují nové matching inzeráty → **pošle email s přehledem**
6. Commitne aktualizovaný CSV zpět do repozitáře

---

## Struktura souborů

```
bazar_watcher/
├── __init__.py
├── config.py         ← Filtry, seznam Low-B křídel, konfigurace zdrojů
├── scrapers.py       ← Scrapers pro každý bazar (requests + BeautifulSoup)
├── storage.py        ← CSV + Excel I/O, deduplikace, filtrování
├── notify.py         ← Email notifikace (SMTP)
├── run.py            ← Hlavní orchestrátor (spouštěný CLI / GitHub Actions)
├── requirements.txt  ← Závislosti (subset hlavního projektu)
└── BAZAR_WATCHER.md  ← Tato dokumentace

../data/bazar_watcher/
├── listings.csv      ← Persistentní databáze všech inzerátů (git tracked)
└── listings.xlsx     ← Excel report (generovaný, git tracked pro prohlížení)

../../.github/workflows/
└── bazar_check.yml   ← GitHub Actions workflow (denní cron)
```

---

## Filtrovací parametry

Nastavení v `config.py` → `FILTERS`:

| Parametr            | Hodnota (2026)    | Popis                                        |
|---------------------|-------------------|----------------------------------------------|
| `max_age_years`     | 5                 | Max stáří křídla → rok výroby ≥ 2021         |
| `min_year`          | 2021 (dynamicky)  | Přepočítáno automaticky z aktuálního roku     |
| `categories`        | EN B, B-G, LTF 1-2| Akceptované kategorie (case-insensitive)      |
| `min_price_eur`     | 200               | Minimum – vyřadí haraburdí                    |

**Model fallback:** Pokud stránka neuvádí kategorii, scraper porovná název
modelu se seznamem `LOW_B_WINGS` v `config.py`. Přidej modely dle libosti.

---

## Sledované bazary

### CZ
| Zdroj | URL | Metoda | Stav |
|-------|-----|--------|------|
| Paragliding Bazar CZ | paragliding-bazar.cz/cs/wings/en-b-… | BS4 HTML, přímá EN B URL | ✅ |
| Bazoš CZ | sport.bazos.cz/inzeraty/paragliding-kridlo/ | BS4 HTML | ✅ |
| Máme Křídla CZ | mamekridla.cz | BS4 generic shop | ⚠️ verify |

### AT
| Zdroj | URL | Metoda | Stav |
|-------|-----|--------|------|
| Willhaben AT | willhaben.at – search API | JSON API | ✅ |
| Paragliding Store AT | paragliding-store.at/shop/gebrauchtmarkt-used-stuff/ | BS4 generic shop | ⚠️ verify |
| Gleitschirmschule AT | gleitschirmschule.at/shop/gebraucht/ | BS4 generic shop | ⚠️ verify |

### DE
| Zdroj | URL | Metoda | Stav |
|-------|-----|--------|------|
| Flugsport DE | flugsport.de/flugsportladen/gebrauchtschirme.html | BS4 HTML tabulka | ✅ |
| Kleinanzeigen DE | kleinanzeigen.de Atom feed | XML Atom feed | ✅ |
| DHV Gebrauchtmarkt | dhv.de | ❌ disabled | Vyžaduje přihlášení |

### CH
| Zdroj | URL | Metoda | Stav |
|-------|-----|--------|------|
| Swissgliders CH | swissgliders.ch/de/fundgrube/ | BS4 generic shop | ⚠️ verify |
| Paraglidingshop CH | paraglidingshop.ch/Gleitschirme/Occasionen-Ex-Demo/ | BS4 generic shop | ⚠️ verify |
| Flugschule Alpstein CH | flugschule-alpstein.ch/occasionen/ | BS4 generic shop | ⚠️ verify |

**Legenda:**
- ✅ Testováno, selektory ověřeny
- ⚠️ verify = funkcionalita napsaná, ale HTML selektory je potřeba ověřit na živém webu
- ❌ disabled = v `config.py` je `"enabled": False`

---

## Rychlý start (lokálně)

```bash
# 1. Přejdi do složky projektu
cd paraglide

# 2. Instaluj závislosti (pokud ještě nemáš)
pip install -r bazar_watcher/requirements.txt

# 3. Vytvoř / zkopíruj .env s SMTP údaji (viz .env.example)
# SMTP_SERVER=smtp.gmail.com
# SMTP_PORT=465
# SMTP_USER=tvuj@gmail.com
# SMTP_PASS=app-password
# ALERT_EMAIL=kam@posilat.cz

# 4. Spusť – dry run (nevysílá email, jen výpis)
python -m bazar_watcher.run --dry-run

# 5. Opravdové spuštění
python -m bazar_watcher.run

# Jen filtruj existující data bez scrapingu
python -m bazar_watcher.run --filter-only
```

---

## GitHub Actions setup

### 1. Inicializuj git repozitář a pushnue na GitHub

```bash
cd C:\Users\Martin\Desktop\paraglide
git init
git add .
git commit -m "feat: bazar_watcher initial setup"
# Vytvoř repo na github.com, poté:
git remote add origin https://github.com/TVUJ_USER/paraglide.git
git push -u origin main
```

### 2. Nastav Secrets v GitHub repozitáři

`Settings → Secrets and variables → Actions → New repository secret`

| Secret | Hodnota |
|--------|---------|
| `SMTP_SERVER` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | `tvuj@gmail.com` |
| `SMTP_PASS` | App password z Google účtu |
| `ALERT_EMAIL` | `kam@posilat.cz` |

### 3. Povol workflow

GitHub Actions tab → bazar_check.yml → Enable workflow.

Workflow se pak spustí každý den v 6:00 UTC automaticky.
Manuální spuštění: `Actions → Bazar Křídel – denní kontrola → Run workflow`.

### 4. Commit dat

Workflow automaticky commitne aktualizovaný `listings.csv` zpět do repozitáře
po každém spuštění (jen pokud jsou změny).

---

## Přidání nového zdroje

1. **`config.py`** – přidej nový dict do `SOURCES` se správným `id`, `name`, `country`, `url`
2. **`scrapers.py`** – napiš funkci `scrape_<id>(source: dict) -> list[dict]`
3. **`scrapers.py`** – přidej mapování do `_SCRAPERS` dict dole v souboru
4. Otestuj lokálně: `python -m bazar_watcher.run --dry-run`
5. Přidej záznam do tabulky [Sledované bazary](#sledované-bazary) výše

---

## Stav scraperů

### Jak ověřit ⚠️ scrapery

Pro každý `⚠️ verify` zdroj:

```python
from bazar_watcher import scrapers, config
import requests, logging
logging.basicConfig(level=logging.DEBUG)

scrapers._session = requests.Session()
source = next(s for s in config.SOURCES if s["id"] == "mamekridla_cz")
results = scrapers._scrape_generic_shop(source)
for r in results[:5]:
    print(r)
```

Pokud vrátí prázdný list, otevři URL v browseru → DevTools → zkopíruj CSS selektory
a uprav `_scrape_generic_shop` nebo napiš specializovaný scraper.

---

## TODO / Known issues

- [ ] **DHV Gebrauchtmarkt** – vyžaduje přihlášení. Možnost: Selenium s cookies,
      nebo manuální kontrola.
- [ ] **Willhaben AT JSON API** – struktura odpovědi se může změnit.
      Záloha: scraping HTML stránky.
- [ ] **Kleinanzeigen Atom feed** – ověřit dostupnost feed URL (funkčnost se může měnit).
- [ ] **Price proxy CZK→EUR** – Bazoš vrací ceny v Kč, přepočet je orientační (děleno 25).
      Ideálně přidat živý kurz z ECB API.
- [ ] **Playwright fallback** – pro JS-heavy stránky (willhaben, kleinanzeigen) přidat
      volitelný playwright backend pokud JSON/Atom přístup selže.
- [ ] **Velikostní filtr** – přidat volitelný filtr na velikost křídla (XS/S/M/L/XL)
      v `config.py`.
- [ ] **Telegram / Pushover notifikace** – alternativa k emailu.

---

*Dokumentace průběžně aktualizována. Poslední revize: 2026-04-27*
