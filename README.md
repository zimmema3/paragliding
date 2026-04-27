# 🪂 Paragliding Weather Alert

Python nástroj, který hlídá počasí na paraglidingových vzletovkách do ~400 km od Českých Budějovic a generuje HTML report s verdiktem "LETĚT / NELETĚT" pro každou plochu.

---

## 🎯 Co aplikace dělá

Pasivní asistenční nástroj — nemusíš proklikávat meteo stránky, aplikace za tebe:

1. **Načte seznam vzletovek** (název, GPS, povolené azimutové okno větru)
2. **Stáhne hodinovou předpověď** přes Open-Meteo API (zdarma, bez klíče, data v m/s):
   - rychlost větru v 10 m (`wind_speed_10m`)
   - nárazový vítr (`wind_gusts_10m`)
   - směr větru (`wind_direction_10m`)
   - srážky (`precipitation`)
   - tlak (`pressure_msl`) – pro synoptickou analýzu
3. **Vyhodnotí podmínky** pro každou plochu:
   - max. průměrný vítr ≤ 4,0 m/s
   - max. nárazy ≤ 5,0 m/s
   - gust factor ≤ 1,4
   - žádné srážky
   - směr větru v povoleném okně plochy (±30°)
   - min. 3 po sobě jdoucí letové hodiny v okně 6–21 h
4. **Synoptická analýza** – tendence tlaku za 24 h (stabilní výše / fronta / proměnlivé)
5. **Vygeneruje tmavý HTML report** s kartami ploch, barevným kódováním, klikacími taby a hodinový detail

---

## 📁 Struktura projektu

```
paraglide/
├── manual_run.py                     # CLI skript – ruční spuštění, generuje HTML report
├── paragliding_weather_alert.ipynb   # Notebook – plná verze (scheduler, e-mail, …)
├── paraglide_report.html             # Generovaný HTML report (ignorován Gitem)
├── README.md
├── requirements.txt
├── .env.example                      # Šablona pro SMTP přihlašovací údaje
├── .env                              # SMTP údaje (NIKDY do Gitu!)
└── .gitignore
```

---

## 🚀 Roadmap

### ✅ Hotovo
- [x] Haversine filtrace ploch dle vzdálenosti od Č. Budějovic
- [x] Volání Open-Meteo API (data v m/s)
- [x] Vyhodnocení větru, nárazů, směru (±30°), srážek
- [x] Gust factor kontrola
- [x] Synoptická analýza (tendence tlaku)
- [x] Generování tmavého HTML reportu (karty + klikací taby + hodinový detail)
- [x] HTML se ukládá do složky projektu a otevírá v prohlížeči

### 🔨 Fáze 2 – Rozpracováno / prioritní
- [ ] **Tříúrovňový systém alertů:**
  - **Synoptický výhled (3–7 dní)** – trend front, tlaková situace, orientační "stojí za to hlídat"
  - **D-1 večer** – hodinový detail na zítřek, doporučené plochy
  - **D-0 ráno (6–7 h)** – finální go/no-go, zda předpověď platí
- [ ] **Přidat vlastní vzletovky** – uživatel zadá GPS + orientaci svahu (`slope_az`), aplikace automaticky vypočítá azimutové okno větru (±30°), volitelně ověří odhad z elevačních dat (OpenTopoData API)
- [ ] **Doplnit seznam ploch do 400 km od Č. Budějovic** – zdroje: xcontest.org, paragliding.cz, paraglidingmap.com, Rakousko (Dachstein, Salzburg), Bavorsko
- [ ] **SMTP e-mail notifikace** – odeslat HTML report pokud je alespoň 1 plocha vhodná
- [ ] **Scheduler** – automatické spouštění (schedule / APScheduler / Windows Task Scheduler)

### 🔮 Fáze 3 – Nice to have
- [ ] **Termická predikce** – Open-Meteo má `cape`, `lifted_index` – přidat cloud base a konvekční index
- [ ] **Vizualizace na mapě** – Folium / Plotly, body ploch + barevné skóre
- [ ] **Supabase integrace** – ukládání výsledků predikcí do DB, porovnání s realitou (co opravdu vyšlo), statistiky přesnosti
- [ ] **Skóre pro různé úrovně** – začátečník / pokročilý / XC (různé sady limitů)
- [ ] **Telegram / Pushover** notifikace místo/vedle e-mailu
- [ ] **Nasazení na server** – cron job na VPS nebo GitHub Actions scheduled workflow

---

## ⚙️ Instalace a spuštění

### Požadavky
- Python 3.10+
- závislosti:

```powershell
pip install -r requirements.txt
```

### Ruční spuštění (CLI)
```powershell
python manual_run.py
```
Vygeneruje `paraglide_report.html` ve složce projektu a otevře ho v prohlížeči.

### Konfigurace SMTP (pro e-mail notifikace)
Zkopíruj `.env.example` → `.env` a vyplň SMTP údaje. Soubor `.env` **nesmí** do Gitu.

---

## 🧠 Architektura alertů (plánovaná)

```
Open-Meteo API
      │
      ├─ forecast_days=7  →  Synoptický výhled (3–7 dní)  →  "Pátek vypadá nadějně"
      ├─ forecast_days=2  →  D-1 večer (18–20 h)          →  "Zítra na Ráně okno 6–9 h"
      └─ current + hourly →  D-0 ráno (6–7 h)             →  "Dnes GO: Rána, okno do 10 h"
```

Každá úroveň generuje samostatný alert (e-mail / Telegram) s různou granularitou.

---

## 📁 Struktura projektu

```
paraglide/
├── paragliding_weather_alert.ipynb   # Hlavní notebook
├── README.md                         # Tento soubor
├── requirements.txt                  # Python knihovny (vytvořit)
├── .gitignore                        # Co necommitovat (vytvořit)
├── .env                              # SMTP údaje (NIKDY do Gitu!)
└── paragliding_alert.log             # Log běhů (generovaný)
```

---

## 🚀 Další postup / roadmap

### ✅ Fáze 1 – Hotovo
- [x] Základní kostra notebooku (12 sekcí)
- [x] Haversine filtrace ploch do 200 km
- [x] Volání Open-Meteo API
- [x] Vyhodnocení větru, nárazů, směru, srážek
- [x] Synoptická analýza
- [x] HTML report + SMTP e-mail
- [x] Plánovač (schedule / APScheduler)

### 🔨 Fáze 2 – Doplnit data a odladit
- [ ] **Doplnit kompletní seznam vzletovek** do 200 km od Č. Budějovic. Aktuálně je v notebooku jen ukázka (Kleť, Kozí pláň, …). Zdroje:
  - [xcontest.org](https://www.xcontest.org/) – databáze startovišť
  - [paragliding.cz](https://www.paragliding.cz/) – oficiální ČR plochy
  - [paraglidingmap.com](https://www.paraglidingmap.com/)
  - Rakouské (Dachstein, Salzburg, Mühlviertel) a bavorské (Šumava) plochy
- [ ] Ověřit povolené azimutové okna u každé plochy (u skrajních je to individuální).
- [ ] Kalibrovat limity podle vlastní úrovně (po pár letech zvýšit `max_wind_avg`).
- [ ] Přidat **termickou predikci** (konvekce, cloud base) – Open-Meteo má `cape`, `lifted_index`.
- [ ] Přidat **vizualizaci** – mapa s Folium / Plotly (body ploch + barevné skóre).

### 🔮 Fáze 3 – Nice to have
- [ ] Telegram / Pushover notifikace místo/vedle e-mailu.
- [ ] Webové rozhraní (Streamlit / FastAPI).
- [ ] Historie předpovědí (uložit do SQLite) a porovnání s realitou (co opravdu vyšlo).
- [ ] Skóre pro různé úrovně pilota (začátečník / pokročilý / XC).

---

## 💻 Přenos na jiný počítač

### 1. Co je potřeba nainstalovat

Na cílovém PC:

- **Python 3.10+** ([python.org](https://www.python.org/downloads/))
- **VS Code** s rozšířeními:
  - Python
  - Jupyter
- **Python knihovny** (viz `requirements.txt`):
  ```powershell
  pip install requests pandas numpy schedule apscheduler ipython jupyter
  ```

### 2. Jak soubor přenést

| Způsob | Výhody | Nevýhody |
|---|---|---|
| **Git (doporučeno)** | Verzování, historie, sync mezi PC, zálohy | Nutný Git účet, setup |
| **OneDrive / cloud** | Automatický sync | Nesdílí se s ostatníma, žádné verzování |
| **USB / e-mail** | Jednoduché | Ruční, snadno zapomeneš poslat update |

### 3. ⚠️ Úskalí přenosu – na co si dát bacha

#### a) **Proměnné prostředí se NEpřenášejí**
SMTP údaje (`SMTP_USER`, `SMTP_PASS`, …) jsou nastavené v systému, **ne v notebooku**. Musíš je znovu nastavit na druhém PC:

```powershell
# Windows PowerShell (persistentně)
setx SMTP_SERVER "smtp.gmail.com"
setx SMTP_PORT "465"
setx SMTP_USER "tvuj@gmail.com"
setx SMTP_PASS "app-password-z-gmailu"
setx ALERT_EMAIL "kam@posilat.cz"
```

Nebo jednorázově do session:
```powershell
$env:SMTP_USER = "tvuj@gmail.com"
```

💡 **Lepší varianta:** použít soubor `.env` + knihovnu `python-dotenv`. Soubor `.env` **nesmí** do Gitu.

#### b) **Gmail vyžaduje App Password**
Normální heslo SMTP nepřijme. Musíš:
1. Zapnout 2FA na Google účtu.
2. Vygenerovat [App Password](https://myaccount.google.com/apppasswords).
3. Použít tento 16místný kód jako `SMTP_PASS`.

#### c) **Plánovač běží jen pokud něco drží proces naživu**
Buňka s `while True: schedule.run_pending()` v notebooku běží, **jen když je notebook otevřený a buňka spuštěná**. Pro skutečný 24/7 provoz:

- **Windows Task Scheduler** → spouštět notebook / skript každou hodinu
- **Převést notebook na `.py` skript**: `jupyter nbconvert --to script paragliding_weather_alert.ipynb`
- **Cloudové varianty**: GitHub Actions (cron), Azure Functions, PythonAnywhere

#### d) **Časová zóna**
Open-Meteo volá se s `timezone=Europe/Prague`, ale Python `datetime.now()` bere lokální čas systému. Pokud notebook poběží v jiné TZ (server v cloudu), výsledky se rozjedou. Řeš explicitně přes `zoneinfo`:
```python
from zoneinfo import ZoneInfo
now = datetime.datetime.now(ZoneInfo("Europe/Prague"))
```

#### e) **Cesty k souborům**
Notebook loguje do `paragliding_alert.log` v aktuálním adresáři. Když ho spustíš odjinud, log vznikne tam. Používej absolutní cestu nebo `Path(__file__).parent`.

#### f) **OneDrive konflikty**
Když máš notebook v OneDrive a upravuješ ho na dvou PC zároveň, OneDrive vytvoří konfliktní kopie (`paragliding_weather_alert-PC1.ipynb`). **Git je tu lepší.**

#### g) **Jupyter kernel**
VS Code na novém PC se tě zeptá, který kernel použít. Vyber ten s nainstalovanýma knihovnama (typicky systémový Python nebo venv).

---

## 🔐 Git – push na alternativní GitHub účet

Chci to pushnout na **jiný účet než `tradivis`**. Postup:

### 1. Vytvoř si nový účet na github.com
Např. `martin-paraglide`.

### 2. Inicializuj repo lokálně
```powershell
cd "C:\Users\martin.zimmermann\OneDrive - UCED\Plocha\paraglide"
git init
git config user.name "Martin Zimmermann"
git config user.email "martin-paraglide@example.com"  # e-mail nového účtu
```
⚠️ **`git config` bez `--global`** – nastaví jen pro tento repo, globální zůstane `tradivis`.

### 3. Vytvoř `.gitignore`
```
.env
*.log
__pycache__/
.ipynb_checkpoints/
```

### 4. Push přes HTTPS s Personal Access Tokenem (PAT)
- Na GitHubu nového účtu: Settings → Developer settings → Personal access tokens → Generate new (scope `repo`).
- Token si ulož (je vidět jen jednou).
- Při `git push` zadáš jako username nový login a jako heslo tento token.

```powershell
git remote add origin https://github.com/martin-paraglide/paragliding-weather-alert.git
git add .
git commit -m "Initial commit – paragliding weather alert"
git branch -M main
git push -u origin main
```

### 5. Nebo přes SSH klíč (čistší)
```powershell
# Vygenerovat nový SSH klíč pro tento účet
ssh-keygen -t ed25519 -C "martin-paraglide@example.com" -f $HOME\.ssh\id_paraglide

# Přidat public klíč (id_paraglide.pub) do nastavení GitHub účtu martin-paraglide

# V ~/.ssh/config nastavit alias:
# Host github-paraglide
#   HostName github.com
#   User git
#   IdentityFile ~/.ssh/id_paraglide

# Remote pak vypadá takhle:
git remote add origin git@github-paraglide:martin-paraglide/paragliding-weather-alert.git
```

---

## 🧪 Rychlý test, že to funguje

1. Otevři `paragliding_weather_alert.ipynb` ve VS Code.
2. Spusť buňky 1–9 (import → report). Pokud vidíš HTML report → předpověď funguje.
3. Nastav SMTP env proměnné a spusť buňku 10 – mělo by dojít e-mail.
4. Buňka 11 (plánovač) – spusť jen pokud chceš, aby notebook jel napořád.

---

## 📚 Použité zdroje

- [Open-Meteo API](https://open-meteo.com/) – zdarma, bez klíče, hodinová předpověď
- [xcontest.org](https://www.xcontest.org/) – databáze vzletovek
- [paragliding.cz](https://www.paragliding.cz/) – české plochy

---

## 📄 Licence

MIT – dělej si s tím co chceš, na vlastní zodpovědnost. **Vždy ověř podmínky na místě** – tahle apka je pomocník, ne autorita. Bezpečné lety! 🪂
