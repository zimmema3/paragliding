# 🪂 Bazar Křídel Watcher

Automatický hlídač bazarů s paraglidingovými křídly pro CZ, AT, DE a CH.
Každý den (přes GitHub Actions) projde všechny bazary, uloží **vše od mid-B níže**
do CSV/Excel a pošle email pro každý nakonfigurovaný **alert profil**.

---

## Obsah

- [Co to dělá](#co-to-dělá)
- [Struktura souborů](#struktura-souborů)
- [Dvě vrstvy filtrování](#dvě-vrstvy-filtrování)
- [Konfigurace alert profilů](#konfigurace-alert-profilů)
- [Sledované bazary](#sledované-bazary)
- [Rychlý start (lokálně)](#rychlý-start-lokálně)
- [GitHub Actions setup](#github-actions-setup)
- [Přidání nového zdroje](#přidání-nového-zdroje)
- [Stav scraperů](#stav-scraperů)
- [TODO / Known issues](#todo--known-issues)

---

## Co to dělá

1. Každý den v **6:00 UTC** GitHub Actions spustí scraper
2. Projde všechny **12 zdrojů** (CZ/AT/DE/CH)
3. **Storage filter**: propustí vše od mid-B níže (EN A + celý EN B) → uloží do CSV
4. Porovná s historií → identifikuje **nové inzeráty** (deduplikace dle URL)
5. **Per-profil matching**: pro každý profil v `ALERT_PROFILES` filtruje nové inzeráty
6. Pokud profil má matching inzeráty → **pošle email** s HTML přehledem
7. Commitne aktualizovaný `listings.csv` zpět do repozitáře
8. `listings.xlsx` se generuje lokálně – má list pro každý profil

---

## Struktura souborů

```
bazar_watcher/
├── __init__.py
├── config.py           ← Storage filter, seznam křídel, ALERT_PROFILES, SOURCES
├── scrapers.py         ← Scrapers (requests + BeautifulSoup/JSON/Atom)
├── storage.py          ← CSV + Excel I/O, deduplikace, apply_storage_filter(),
│                            apply_profile_filter()
├── notify.py           ← Email notifikace – jeden email per příjemce, sekce per profil
├── run.py              ← CLI orchestrátor
├── requirements.txt
└── BAZAR_WATCHER.md    ← Tato dokumentace

data/bazar_watcher/
├── listings.csv        ← Persistentní databáze, git tracked
├── listings.xlsx       ← Excel report, git ignored (binary)
└── .gitkeep

.github/workflows/
└── bazar_check.yml     ← GitHub Actions: daily cron 6:00 UTC
```

---

## Dvě vrstvy filtrování

### Vrstva 1 – Storage (co se ukládá do CSV/Excel)

Vše od **mid-B níže**: EN A + celý EN B (low-B i mid-B) + starší DHV/LTF označení.

Nastavení v `config.py` → `STORAGE_FILTER`:

```python
STORAGE_FILTER = {
    "categories": ["EN A", "EN B", "DHV 1", "LTF 1", "DHV 1-2", "B-G", "B-R", ...],
    "min_price_eur": 150,
}
```

EN C, D, CCC, DAGC (motory) jsou **automaticky vyřazeny**.

### Vrstva 2 – Alert profily (komu co posílat)

Každý profil v `ALERT_PROFILES` má vlastní sadu kritérií.
Notifikace chodí jen pro **nové** inzeráty splňující daný profil.

---

## Konfigurace alert profilů

Edituj `config.py` → `ALERT_PROFILES`:

```python
ALERT_PROFILES = [
    {
        "name": "Martin – M mid-B a níže",
        "email": None,            # None = použije ALERT_EMAIL z .env
        "max_category": "mid-B",  # "A" | "low-B" | "mid-B"
        "sizes": ["M", "ML"],     # None = libovolná velikost
        "max_price_eur": None,    # None = bez stropu
        "min_year": 2021,         # nebo CURRENT_YEAR - 5
        "countries": None,        # None = CZ+AT+DE+CH
    },
    {
        "name": "Kamarádka – XS/S EN A",
        "email": None,
        "max_category": "A",
        "sizes": ["XS", "S", "22", "24"],
        "max_price_eur": 1500,
        "min_year": 2020,
        "countries": None,
    },
    # Přidej libovolný další profil...
]
```

**Popis `max_category`:**
| Hodnota | Co zahrnuje |
|---------|-------------|
| `"A"` | Pouze EN A |
| `"low-B"` | EN A + low-B (Rush, Ion, Epsilon, Geo, …) |
| `"mid-B"` | EN A + low-B + mid-B (Mentor, Sigma, Delta, Chili, …) |

**Více příjemců:** nastav různý `"email"` u profilů → každý příjemce dostane
svůj email jen se svými profily. Profily se stejným emailem se slučují do jednoho emailu.

---

## Sledované bazary

### CZ (12 zdrojů celkem)
| Zdroj | Metoda | Stav |
|-------|--------|------|
| Paragliding Bazar CZ – EN B | BS4 HTML, přímá kategorie URL | ✅ |
| Paragliding Bazar CZ – EN A | BS4 HTML, přímá kategorie URL | ✅ |
| Bazoš CZ | BS4 HTML | ✅ |
| Máme Křídla CZ | BS4 generic shop | ⚠️ verify |

### AT
| Zdroj | Metoda | Stav |
|-------|--------|------|
| Willhaben AT | JSON API (bez JS) | ✅ |
| Paragliding Store AT | BS4 generic shop | ⚠️ verify |
| Gleitschirmschule AT | BS4 generic shop | ⚠️ verify |

### DE
| Zdroj | Metoda | Stav |
|-------|--------|------|
| Flugsport DE | BS4 HTML tabulka (B-G/B-R kategorie) | ✅ |
| Kleinanzeigen DE | Atom XML feed (bez JS) | ✅ |
| DHV Gebrauchtmarkt | disabled – vyžaduje přihlášení | ❌ |

### CH
| Zdroj | Metoda | Stav |
|-------|--------|------|
| Swissgliders CH | BS4 generic shop | ⚠️ verify |
| Paraglidingshop CH | BS4 generic shop | ⚠️ verify |
| Flugschule Alpstein CH | BS4 generic shop | ⚠️ verify |

---

## Rychlý start (lokálně)

```bash
# Z adresáře paraglide/ (= git root)
cd C:\Users\Martin\Desktop\paraglide\paraglide

# Instalace závislostí
pip install -r bazar_watcher/requirements.txt

# Zkopíruj .env.example → .env a vyplň SMTP údaje
copy .env.example .env
# Edituj .env: SMTP_USER, SMTP_PASS, ALERT_EMAIL

# Dry run – výpis bez emailu a bez uložení
python -m bazar_watcher.run --dry-run

# Opravdové spuštění
python -m bazar_watcher.run

# Bez emailu (jen scraping + Excel)
python -m bazar_watcher.run --no-notify

# Zobraz profil-matching z existujících dat (bez scrapingu)
python -m bazar_watcher.run --filter-only
```

---

## GitHub Actions setup

### 1. Vytvoř GitHub repozitář a pushnui

```bash
# Na github.com vytvoř nový repo (např. "paraglide")
# Poté lokálně:
cd C:\Users\Martin\Desktop\paraglide\paraglide

git remote add origin https://github.com/TVUJ_USERNAME/paraglide.git
git branch -M main
git push -u origin main
```

### 2. Nastav Secrets

`GitHub repo → Settings → Secrets and variables → Actions → New repository secret`

| Secret | Příklad hodnoty |
|--------|----------------|
| `SMTP_SERVER` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | `tvuj@gmail.com` |
| `SMTP_PASS` | App password (ne běžné heslo!) |
| `ALERT_EMAIL` | `kam@posilat.cz` |

> **Gmail App password:** Google účet → Zabezpečení → Dvoufázové ověření →
> Hesla aplikací → vygeneruj pro "Mail / Windows Computer"

### 3. Spuštění workflow

Workflow se spustí automaticky každý den v 6:00 UTC.
Manuálně: `Actions → Bazar Křídel – denní kontrola → Run workflow`.

---

## Přidání nového zdroje

1. `config.py` → přidej dict do `SOURCES`
2. `scrapers.py` → napiš `scrape_<id>(source) -> list[dict]`
3. `scrapers.py` → přidej do `_SCRAPERS` dict
4. Test: `python -m bazar_watcher.run --dry-run`
5. Aktualizuj tabulku zdrojů výše

---

## Přidání dalšího alert profilu

Jen edituj `ALERT_PROFILES` v `config.py` – nepotřebuješ měnit žádný jiný soubor.

---

## Stav scraperů

Pro debug ⚠️ zdrojů:

```python
from bazar_watcher import scrapers, config
import requests, logging
logging.basicConfig(level=logging.DEBUG)

scrapers._session = requests.Session()
source = next(s for s in config.SOURCES if s["id"] == "swissgliders_ch")
results = scrapers._scrape_generic_shop(source)
print(f"Nalezeno: {len(results)}")
for r in results[:3]: print(r)
```

---

## TODO / Known issues

- [ ] **DHV Gebrauchtmarkt** – přihlášení přes cookies / Selenium
- [ ] **Willhaben JSON API** – záloha HTML scraping pokud API změní strukturu
- [ ] **Kleinanzeigen Atom** – ověřit stabilitu feed URL
- [ ] **CZK → EUR přepočet** (Bazoš) – přidat ECB API kurz místo pevného 1/25
- [ ] **Velikostní normalizace** – mapovat "26", "S", "small" → stejný formát
- [ ] **Playwright fallback** – pro JS-heavy stránky
- [ ] **Telegram/Pushover** – alternativa k emailu
- [ ] **Excel autofilter** – přidat Excel AutoFilter na všech listech

---

*Poslední revize: 2026-04-27 · git root: `paraglide/paraglide/`*

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
