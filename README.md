# 🪂 Paragliding Toolkit

Privátní repo se dvěma nezávislými nástroji pro paragliding pilota:

| Modul | Co dělá | Spouštění |
|---|---|---|
| **[bazar_watcher/](bazar_watcher/)** | Denně scrapuje 11 bazarů křídel (CZ/AT/CH/DE), ukládá do CSV/Excel, posílá e-mail s novými inzeráty splňujícími profilové filtry | GitHub Actions cron 8:00 UTC |
| **[paragliding_weather_alert.ipynb](paragliding_weather_alert.ipynb)** + [manual_run.py](manual_run.py) | Vyhodnocuje meteo z Open-Meteo pro vzletovky do ~400 km od Č. Budějovic, generuje HTML report | Lokálně (notebook nebo CLI) |

---

## 📂 Adresářová struktura (autoritativní)

```
paragliding/
├── bazar_watcher/                     Modul: scraping bazarů
│   ├── __init__.py                    (prázdný marker)
│   ├── config.py                      Zdroje, filtry, alert profily
│   ├── scrapers.py                    Per-source scrapery + sdílené helpers
│   ├── storage.py                     CSV/Excel I/O, dedup, filtrování
│   ├── notify.py                      SMTP e-mail (HTML, sekce per profil)
│   ├── run.py                         CLI vstup (`python -m bazar_watcher.run`)
│   ├── requirements.txt               BS4, requests, pandas, openpyxl, lxml
│   └── BAZAR_WATCHER.md               Detailní dokumentace modulu ↘ čti pro vývoj
│
├── data/bazar_watcher/                Výstupy (commitované zpět do repa)
│   ├── listings.csv                   Akumulovaná databáze, dedup dle (source_id, url)
│   ├── listings.xlsx                  Excel report (historie + dnes + per profil)
│   └── .gitkeep
│
├── paragliding_weather_alert.ipynb    Notebook: weather alert + scheduler + e-mail
├── manual_run.py                      CLI: vygeneruj paraglide_report.html
│
├── .github/workflows/
│   └── bazar_check.yml                GitHub Actions: cron 8 UTC, plain SMTP env
│
├── requirements.txt                   Závislosti pro weather alert
├── .env.example                       Šablona pro lokální SMTP (nepotřebuješ pro CI)
├── .gitignore
├── LICENSE                            MIT
└── README.md                          (tenhle soubor)
```

> **Co je `paraglide_report.html`?** Generovaný výstup z `manual_run.py`. Není v gitu (gitignorováno).

---

## 🚀 Rychlý start

### 1. Klonuj a nainstaluj

```powershell
git clone https://github.com/zimmema3/paragliding.git
cd paragliding

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt                  # weather alert
pip install -r bazar_watcher/requirements.txt    # bazar watcher
```

### 2. Spusť bazar watcher (lokálně)

```powershell
# Plný běh (scrape → filter → save → e-mail, pokud je SMTP nastaveno)
python -m bazar_watcher.run

# Bez e-mailu (jen scrape + save)
python -m bazar_watcher.run --no-notify

# Bez ukládání ani e-mailu (jen výpis)
python -m bazar_watcher.run --dry-run

# Re-import: matching profilu počítá ze VŠECH aktuálně viditelných inzerátů
# (ne jen nových od posledního běhu) — užitečné po změně filtru
python -m bazar_watcher.run --reimport
```

### 3. Spusť weather alert

```powershell
# CLI: vygeneruje paraglide_report.html a otevře v prohlížeči
python manual_run.py

# Notebook: VS Code → otevři paragliding_weather_alert.ipynb → Run All
```

---

## ☁️ Bazar Watcher — co se kde děje

### Datový tok

```
SOURCES (config.py)
   ↓ (per-source scrapery z scrapers.py)
list[dict] s 12 standardními poli (source_id, country, title, url, price_eur, year, category, size, weight_range, condition, date_listed, date_found)
   ↓ apply_storage_filter() — nechá vše od mid-B níže (EN A + EN B)
   ↓ find_new() — dedup proti listings.csv podle (source_id, url) nebo (source_id, title)
   ↓ uloží do listings.csv (akumuluje napříč běhy)
   ↓ apply_profile_filter() — pro každý profil v ALERT_PROFILES filtruje matching
   ↓ notify.py — pošle 1 e-mail per unikátní příjemce, se sekcí per profil
listings.xlsx — historie + tento měsíc + dnes přidané + per profil
```

### Dvě vrstvy filtrování

1. **Storage filter** (`config.py` → `STORAGE_FILTER`) — **co se uloží** do CSV/Excel.
   Aktuálně: vše s kategorií EN A nebo EN B (low-B i mid-B), min. cena 150 EUR.
   EN C/D/CCC se neukládají vůbec.

2. **Alert profily** (`config.py` → `ALERT_PROFILES`) — **komu pošleme e-mail**.
   Každý profil má vlastní limity: `max_category` (A / low-B / mid-B), `sizes`, `max_price_eur`, `min_year`, `countries`.
   Aktuálně 2 profily: Martin (M, mid-B) + Kamarádka (XS/S, EN A, ≤1500 EUR).

Detaily a recepty pro úpravy: [bazar_watcher/BAZAR_WATCHER.md](bazar_watcher/BAZAR_WATCHER.md).

### Sledované zdroje (13 nakonfigurovaných, 11 aktivních)

| ID | Země | Typ | Stav |
|---|---|---|---|
| `paragliding_bazar_cz_b` | CZ | bazar, EN B kategorie, paginace | ✅ |
| `paragliding_bazar_cz_a` | CZ | bazar, EN A kategorie, paginace | ✅ |
| `bazos_cz` | CZ | bazar, paginace | ✅ |
| `mamekridla_cz` | CZ | e-shop | ✅ |
| `willhaben_at` | AT | JSON API, paginace | ⚠️ občasné výpadky |
| `paragliding_store_at` | AT | Cumulus CMS (Jimdo, hproduct) | ✅ |
| `gleitschirmschule_at` | AT | JS-rendered Shopware | ❌ disabled |
| `flugsport_de` | DE | HTML tabulka | ✅ |
| `kleinanzeigen_de` | DE | Atom feed | ⚠️ občasné HTTP 500 |
| `dhv_de` | DE | vyžaduje login | ❌ disabled |
| `swissgliders_ch` | CH | WordPress Avia | ✅ |
| `paraglidingshop_ch` | CH | Shopware | ✅ |
| `alpstein_ch` | CH | Divi/ET Builder | ✅ |

---

## ⚙️ GitHub Actions

Workflow [.github/workflows/bazar_check.yml](.github/workflows/bazar_check.yml) běží:

- **Cron:** `0 8 * * *` (denně 8:00 UTC = 9:00 SEČ / 10:00 SELČ)
- **Manuálně:** [Actions → Bazar Křídel → Run workflow](https://github.com/zimmema3/paragliding/actions)

Co dělá:
1. Checkout repa, Python 3.11, `pip install -r bazar_watcher/requirements.txt`
2. Spustí `python -m bazar_watcher.run`
3. `git add data/bazar_watcher/listings.csv listings.xlsx` → commit (jen pokud jsou změny) → push

### SMTP konfigurace — naotevřeno v workflow

V tomhle privátním repu jsou SMTP údaje **přímo v YAML** workflow (sekce `env:`),
nepoužívají se GitHub Secrets. Důvod: privátní repo, e-mailová schránka je osobní,
nic kritického. Pokud bys chtěl přejít na secrets, viz [Migrace na secrets](#migrace-na-secrets-volitelně) níže.

```yaml
env:
  SMTP_SERVER: smtp.gmail.com
  SMTP_PORT:   "465"
  SMTP_USER:   zimmema3@gmail.com
  SMTP_PASS:   <gmail-app-password>
  ALERT_EMAIL: zimmema3@gmail.com
```

> **Upozornění na App Password:** Gmail SMTP s 2FA účtem **vyžaduje App Password** (16 lowercase znaků z <https://myaccount.google.com/apppasswords>), ne běžné heslo k účtu. Pokud workflow padá s `Authentication failed`, vygeneruj App Password a přepiš hodnotu `SMTP_PASS` ve workflow.

### Migrace na secrets (volitelně)

Kdybys repo někdy zveřejnil nebo začal sdílet:

1. V GitHub UI → repo → Settings → Secrets and variables → Actions → New repository secret
2. Přidej: `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL`
3. Ve [bazar_check.yml](.github/workflows/bazar_check.yml) nahraď plain hodnoty za:
   ```yaml
   SMTP_USER: ${{ secrets.SMTP_USER }}
   ```
4. Commit + push.

---

## 🔧 Lokální SMTP konfigurace (volitelné, pro běh mimo CI)

Pokud chceš e-maily i z lokálního běhu, zkopíruj [.env.example](.env.example) na `.env` a vyplň. `.env` je v `.gitignore`, takže se nikdy nedostane do repa.

```powershell
Copy-Item .env.example .env
notepad .env   # vyplň hodnoty
```

`bazar_watcher/notify.py` čte env vars přes `os.environ.get(...)`, takže `.env` načti přes `python-dotenv` nebo nastav přímo proměnné prostředí.

---

## 🛒 Datový model — `listings.csv`

| Sloupec | Typ | Popis |
|---|---|---|
| `source_id` | str | ID zdroje (`paragliding_bazar_cz_b`, `willhaben_at`, …) |
| `source_name` | str | Lidsky čitelný název |
| `country` | str | CZ / AT / CH / DE |
| `title` | str | Titulek inzerátu |
| `url` | str | URL detailu (nebo URL zdroje, pokud detail page chybí) |
| `price_eur` | float \| `` | Cena v EUR (CHF×0.952, CZK×0.04 orientačně) |
| `year` | int \| `` | Rok výroby |
| `category` | str \| `` | EN A / EN B / EN C / EN D |
| `size` | str \| `` | XS / S / M / 22 / 25 … |
| `weight_range` | str \| `` | např. `70kg-100kg` |
| `condition` | str \| `` | volný text (sehr gut, neuwertig, …) |
| `date_listed` | str \| `` | YYYY-MM-DD (kdy byl inzerát publikován) |
| `date_found` | str | YYYY-MM-DD (kdy ho scraper poprvé viděl) |

Dedup klíč: `(source_id, url)` — pokud zdroj nemá detail URL, padá na `(source_id, title)`.

---

## 🧪 Vývoj a debug

### Test jednoho scraperu

```python
from bazar_watcher import scrapers, config
import requests

scrapers._session = requests.Session()
scrapers._session.headers.update(scrapers.HEADERS)

src = next(s for s in config.SOURCES if s["id"] == "paragliding_store_at")
results = scrapers.scrape_paragliding_store_at(src)
for r in results:
    print(r["title"], "|", r.get("price_eur"), "|", r.get("year"))
```

### Cenové parsery

V [scrapers.py](bazar_watcher/scrapers.py) jsou dva sdílené helpery:

- `_parse_price_eur(text)` — DE/AT/CZ formát: `1.200,00 €`, `820 EUR`, `1 846,53 EUR`
- `_parse_price_chf_to_eur(text)` — CHF s konverzí na EUR (kurz 1 CHF ≈ 0.952 EUR):
  - Apostrofy: rovný `'` i kudrnatý `’` (U+2019)
  - Pořadí: `CHF 1'990.00`, `Fr. 1’990.-`, `1990 CHF`, `Verkaufspreis: 1000CHF`
  - Filtr 50–100 000 (eliminuje placeholder „0.00")
  - Preferuje keyword `Verkaufspreis`, jinak první výskyt

### Přidání nového zdroje

1. Přidej dict do `SOURCES` v [config.py](bazar_watcher/config.py)
2. Napiš `scrape_<id>(source) -> list[dict]` v [scrapers.py](bazar_watcher/scrapers.py)
   - Vracej standardní pole přes helper `_listing(...)` (viz vrch souboru)
3. Zaregistruj v `_SCRAPERS` na konci [scrapers.py](bazar_watcher/scrapers.py)
4. Test: `python -m bazar_watcher.run --dry-run`

---

## ☁️ Weather Alert — krátce

[manual_run.py](manual_run.py) a notebook stahují 7-denní hodinovou předpověď z Open-Meteo a pro každou plochu vyhodnotí go/no-go:

- max. průměrný vítr ≤ 4,0 m/s
- max. nárazy ≤ 5,0 m/s
- gust factor ≤ 1,4
- žádné srážky
- směr větru v okně plochy (±30°)
- ≥ 3 po sobě jdoucí letové hodiny v 6–21 h
- synoptická tendence tlaku (24 h)

Výstup: tmavý HTML report `paraglide_report.html` s kartou per plocha. Notebook navíc umí poslat e-mail (sdílí SMTP konfiguraci s bazar watcherem).

---

## 📜 Licence

[MIT](LICENSE) — Martin Zimmermann, 2025.
