# 🪂 Paragliding Toolkit

Sada Python nástrojů pro paragliding pilota:

1. **[Bazar Watcher](#-bazar-watcher)** — denní scraping bazarů křídel (CZ, AT, CH, DE) s e-mailovou notifikací o nových inzerátech splňujících kritéria.
2. **[Weather Alert](#%EF%B8%8F-weather-alert)** — vyhodnocení podmínek pro létání na vzletovkách v okolí (do ~400 km od Č. Budějovic) přes Open-Meteo API + HTML report.

GitHub Actions automaticky spouští bazar watcher každý den a commituje výsledky do repozitáře.

---

## 📂 Struktura projektu

```
paragliding/
├── bazar_watcher/                  # Modul: scraping bazarů křídel
│   ├── __init__.py
│   ├── config.py                   # Definice zdrojů + filtrační profily
│   ├── scrapers.py                 # Per-source scrapery (CZ/AT/CH/DE)
│   ├── storage.py                  # CSV/Excel ukládání + dedup + filtrování
│   ├── notify.py                   # SMTP e-mail s grupovanými inzeráty
│   ├── run.py                      # CLI vstupní bod (`python -m bazar_watcher.run`)
│   ├── requirements.txt            # Závislosti modulu
│   └── BAZAR_WATCHER.md            # Detailní dokumentace modulu
│
├── paragliding_weather_alert.ipynb # Notebook: weather alert (plná verze + scheduler)
├── manual_run.py                   # CLI: jednorázové vygenerování weather reportu
├── paraglide_report.html           # Generovaný HTML report (gitignorováno)
│
├── data/bazar_watcher/             # Výstupy bazar watcheru
│   ├── listings.csv                # Hlavní akumulovaná databáze inzerátů
│   └── listings.xlsx               # Excel s měsíčními listy
│
├── .github/workflows/
│   └── bazar_check.yml             # GitHub Actions – denní cron
│
├── requirements.txt                # Společné závislosti (weather alert)
├── .env.example                    # Šablona pro SMTP konfiguraci
└── README.md                       # Tento soubor
```

---

## 🚀 Rychlý start

### Instalace

```powershell
# Klon repozitáře
git clone https://github.com/<user>/paragliding.git
cd paragliding

# Virtuální prostředí (doporučeno)
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate    # Linux/macOS

# Závislosti
pip install -r requirements.txt          # weather alert
pip install -r bazar_watcher/requirements.txt  # bazar watcher
```

### Konfigurace SMTP (volitelné, pro e-mailové notifikace)

```powershell
Copy-Item .env.example .env
# Otevři .env a vyplň SMTP_*, ALERT_EMAIL
```

Pro Gmail je potřeba [App Password](https://myaccount.google.com/apppasswords) (vyžaduje zapnuté 2FA).

---

## 🛒 Bazar Watcher

Denní scraping bazarů paragliderů s notifikací, když se objeví křídlo splňující profilové filtry (kategorie EN A/B, hmotnostní rozsah, max cena, …).

### Sledované zdroje (10 zdrojů, 4 země)

| Zdroj | Země | Typ | Status |
|---|---|---|---|
| paragliding-bazar.cz (EN A i EN B) | CZ | bazar, paginated | ✅ |
| bazos.cz | CZ | bazar, paginated | ✅ |
| mamekridla.cz | CZ | e-shop | ✅ |
| willhaben.at | AT | JSON API, paginated | ⚠️ občasné výpadky |
| paragliding-store.at | AT | Cumulus CMS shop | ✅ |
| gleitschirmschule.at | AT | JS-rendered Shopware | ❌ disabled (potřebuje headless) |
| flugsport-paragliding.de | DE | HTML tabulka | ✅ |
| kleinanzeigen.de | DE | Atom feed | ⚠️ občasné HTTP 500 |
| swissgliders.ch | CH | WordPress (Avia theme) | ✅ |
| paraglidingshop.ch | CH | Shopware | ✅ |
| flugschule-alpstein.ch | CH | Divi/ET Builder | ✅ |

### Spuštění

```powershell
# Plný běh (scrape + filter + uložit + e-mail)
.\.venv\Scripts\python -m bazar_watcher.run

# Bez e-mailu (jen scrape + uložit)
.\.venv\Scripts\python -m bazar_watcher.run --no-notify

# Dry-run (jen scrape, nic neukládá)
.\.venv\Scripts\python -m bazar_watcher.run --dry-run

# Přepnutí na jiný profil filtrů
.\.venv\Scripts\python -m bazar_watcher.run --profile martin
```

### Více dní v CSV / Excel

CSV se napříč běhy **automaticky akumuluje**. Funkce `find_new()` přidává jen nové inzeráty (dedup podle `(source_id, url)` nebo `(source_id, title)`). Excel má list **„Tento měsíc"** (filtrovaný podle `date_listed`) a měsíční historické listy.

GitHub Actions běží denně v 8:00 UTC a commituje aktualizovaný `listings.csv`/`.xlsx` do repa, takže historie roste automaticky.

### Profily filtrů

Definované v [bazar_watcher/config.py](bazar_watcher/config.py) (`PROFILES`). Příklad pro Martina (cca 75 kg pilot, mid-B):

```python
{
  "id": "martin",
  "name": "Martin – mid-B",
  "categories": ["EN B", "EN/B", "ENB", "B"],
  "min_year": 2018,
  "max_price_eur": 2000,
  "weight_in_range": (60, 90),  # vzletová hmotnost
  "exclude_cats": ["EN C", "EN/C", "EN D", "EN/D", "ENC", "END", "EN B/C", "ENB/C", "CCC"],
}
```

### Detaily

Viz [bazar_watcher/BAZAR_WATCHER.md](bazar_watcher/BAZAR_WATCHER.md) — architektura, parsing pravidla, debugging.

---

## ☁️ Weather Alert

Vyhodnocuje meteo podmínky pro paragliding na vzletovkách do ~400 km od Č. Budějovic. Pro každou plochu spočítá go/no-go verdikt na základě:

- max. průměrný vítr ≤ 4,0 m/s
- max. nárazy ≤ 5,0 m/s
- gust factor ≤ 1,4
- žádné srážky
- směr větru v povoleném okně plochy (±30°)
- min. 3 po sobě jdoucí letové hodiny v okně 6–21 h
- synoptická analýza (tendence tlaku za 24 h)

### Spuštění (CLI)

```powershell
.\.venv\Scripts\python manual_run.py
```

Vygeneruje `paraglide_report.html` (tmavý report s kartami ploch) a otevře v prohlížeči.

### Notebook (plná verze)

`paragliding_weather_alert.ipynb` obsahuje rozšířenou verzi s e-mail alertem a schedulerem. Otevři ve VS Code → Run All.

### Datový zdroj

[Open-Meteo API](https://open-meteo.com/) — zdarma, bez klíče, hodinová předpověď v m/s.

---

## ⚙️ GitHub Actions – automatický denní běh

Workflow [.github/workflows/bazar_check.yml](.github/workflows/bazar_check.yml) spouští bazar watcher denně v **8:00 UTC** (10:00 SELČ / 9:00 SEČ) a po doběhnutí:

1. Commituje aktualizovaný `data/bazar_watcher/listings.csv` a `.xlsx` zpět do repa.
2. Volitelně pošle e-mail s novými inzeráty (pokud jsou nastaveny secrets).

### Required GitHub Secrets

V GitHub UI → repo → Settings → Secrets and variables → Actions:

| Secret | Příklad | Popis |
|---|---|---|
| `SMTP_SERVER` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `465` | SMTP port (SSL) |
| `SMTP_USER` | `tvuj@gmail.com` | Odesílatel |
| `SMTP_PASS` | `app-password-16-znaku` | Gmail App Password |
| `ALERT_EMAIL` | `prijemce@example.com` | Příjemce alertů |

Pokud nejsou secrets nastavené, workflow proběhne, ale e-mail se neodešle (logovaná warning).

### Manuální spuštění

V GitHub UI → záložka **Actions** → workflow „Bazar Křídel – denní kontrola" → **Run workflow**.

---

## 🗄️ Datový model (CSV)

Každý řádek v `data/bazar_watcher/listings.csv` má strukturu:

| Sloupec | Typ | Popis |
|---|---|---|
| `source_id` | str | ID zdroje (`paragliding_bazar_cz_b`, `willhaben_at`, …) |
| `source_name` | str | Lidsky čitelný název |
| `country` | str | CZ / AT / CH / DE |
| `title` | str | Titulek inzerátu |
| `url` | str | URL detail stránky (nebo URL zdroje, pokud nemá detail page) |
| `price_eur` | float \| None | Cena v EUR (CHF×1/1.05, Kč orientační) |
| `year` | int \| None | Rok výroby |
| `category` | str \| None | EN A / EN B / EN C / EN D |
| `size` | str \| None | XS / S / M / 22 / 25 … |
| `weight_range` | str \| None | např. `70kg-100kg` |
| `condition` | str \| None | volný text (sehr gut, neuwertig, …) |
| `date_listed` | str \| None | YYYY-MM-DD (kdy byl inzerát publikován) |
| `date_found` | str | YYYY-MM-DD (kdy ho scraper poprvé viděl) |

---

## 🛠️ Vývoj

### Spuštění testu jednoho scraperu

```python
import bazar_watcher.scrapers as s
import requests
s._session = requests.Session()
s._session.headers.update(s.HEADERS)

src = {"id": "paragliding_store_at", "name": "...", "country": "AT",
       "url": "https://www.paragliding-store.at/shop/gebrauchtmarkt-used-stuff/used-paragliders/"}
print(s.scrape_paragliding_store_at(src))
```

### Cenový parser

[bazar_watcher/scrapers.py](bazar_watcher/scrapers.py) má dvě helper funkce:

- `_parse_price_eur(text)` — DE/AT/CZ formát (`1.200,00 €`, `820 EUR`, `1 846,53 EUR`)
- `_parse_price_chf_to_eur(text)` — CHF s konverzí (`CHF 2'800.00`, `Verkaufspreis: 1000CHF`, kurz 1 CHF ≈ 0.95 EUR)

### Přidání nového zdroje

1. Doplň záznam do `SOURCES` v [bazar_watcher/config.py](bazar_watcher/config.py).
2. Napiš `scrape_<id>()` v [bazar_watcher/scrapers.py](bazar_watcher/scrapers.py) vracející `list[dict]` se standardními klíči (viz `_listing()`).
3. Zaregistruj v `_SCRAPERS` na konci `scrapers.py`.

---

## 📜 Licence

MIT — viz [LICENSE](LICENSE).

---

## 🙋 FAQ

**Proč jsou některé ceny `None`?**
Inzerát ji buď neuvádí (Preis VHB, "auf Anfrage"), nebo je v nestandardním formátu, který parser zatím nepokrývá. PR vítány.

**Proč chybí GitHub Actions secrets — zlobí workflow?**
Workflow detekuje chybějící secrets a logguje warning, ale nezhroutí se. E-mail se neodešle, ale CSV se aktualizuje.

**Můžu přidat vlastní zdroj?**
Ano, viz [Přidání nového zdroje](#přidání-nového-zdroje).

**Proč je `gleitschirmschule_at` disabled?**
Jejich shop je renderovaný JavaScriptem (Shopware) a statický HTML neobsahuje produkty. Vyžadovalo by to headless browser (Playwright). Není v plánu.
