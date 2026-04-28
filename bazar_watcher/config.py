# -*- coding: utf-8 -*-
"""
Konfigurace bazar_watcher.

Architektura:
  STORAGE_FILTER  – co se ukládá do CSV/Excel (mid-B a níže = vše co tě zajímá)
  ALERT_PROFILES  – seznam upozorňovacích profilů s individuálními filtry
                    (pro tebe, pro kamarádku, …)
"""

import datetime

CURRENT_YEAR = datetime.datetime.now().year

# ──────────────────────────────────────────────────────────────────────────────
# STORAGE FILTER – co se ukládá do Excel/CSV
# Ukládáme VŠE od mid-B níže: EN A, celý EN B (low i mid), starší označení
# EN C a výše se ignorují
# ──────────────────────────────────────────────────────────────────────────────
STORAGE_FILTER = {
    # Kategorie (case-insensitive substring match v poli category nebo title)
    "categories": [
        # Standardní EN označení
        "EN A", "EN/A",
        "EN B", "EN/B",
        # Německá DHV/LTF označení
        "DHV 1", "LTF 1",
        "DHV 1-2", "LTF 1-2",
        "DHV 1/2",
        # Flugsport B-G / B-R (Gelegenheitsflieger / Routinier = low/mid B)
        "B-G", "B-R",
    ],
    # Pokud kategorie není na stránce uvedena, matchujeme název modelu
    # (viz KNOWN_WINGS níže)
    # Minimální cena – vyřadí absolutní haraburdí
    "min_price_eur": 150,
}

# ──────────────────────────────────────────────────────────────────────────────
# KNOWN WINGS – fallback pokud stránka neuvádí kategorii
# Rozděleno na low-B a mid-B pro použití v alert profilech
# ──────────────────────────────────────────────────────────────────────────────

# EN A – začátečnická křídla
EN_A_WINGS = [
    # Advance
    "alpha 6", "alpha 7",
    # Nova
    "prion 4", "prion 5",
    # Ozone
    "buzz z5", "buzz z6",
    # Swing
    "mito", "arcus rs",
    # Niviuk
    "koyot 5",
    # BGD
    "base", "fun",
    # UP
    "meru", "summit xc",
    # Gradient
    "golden 5",
    # Sky Country
    "eona 3",
    # AirDesign
    "susi", "rise",
    # MacPara
    "eden 7",
    # Axis
    "venus",
]

# EN B low-B (B-G, Gelegenheitsflieger) – přívětivé B
LOW_B_WINGS = [
    # Ozone
    "rush 5", "rush 6", "rush 7", "geo 6", "geo 7",
    # Nova
    "ion 5", "ion 6", "ion light",
    # Advance
    "epsilon 8", "epsilon 9",
    # BGD
    "cure", "lynx",
    # Niviuk
    "hook 5", "hook 6",
    # Gin
    "bonanza 2", "bonanza 3", "explorer 2",
    # Skywalk
    "tonic 2", "tonic 3",
    # Swing
    "serac rs", "nyra rs",
    # UP
    "mana", "malibou",
    # Sky Country
    "discovery 5",
    # Axis
    "comet 4",
    # MacPara
    "elan 3",
    # Phi
    "tenor",
    # Triple Seven
    "rook 3",
    # AirDesign
    "leaf 3", "volt 4",
    # Gradient
    "aspen 7",
    # Skyman
    "crossalps",
]

# EN B mid-B (B-R, Routinier) – výkonnější B, stále pro rekreační piloty
MID_B_WINGS = [
    # Ozone
    "delta 4", "delta 5", "zeno 2",
    # Nova
    "mentor 5", "mentor 6", "mentor 7",
    # Advance
    "sigma 9", "sigma 10", "sigma 11",
    # Niviuk
    "icepeak evox", "peak 5", "peak 6",
    # Gin
    "explorer 2", "carrera plus",
    # Skywalk
    "chili 5", "chili 6",
    # Swing
    "nyos rs", "nyos",
    # UP
    "summit xc 6",
    # Triple Seven
    "queen 2",
    # AirDesign
    "volt 3",
    # PHI
    "symphonia", "maestro",
    # BGD
    "tala",
    # MacPara
    "eden 8",
    # Gradient
    "bright",
]

# Kombinace všeho co ukládáme (mid-B a níže)
ALL_KNOWN_WINGS = EN_A_WINGS + LOW_B_WINGS + MID_B_WINGS

# ──────────────────────────────────────────────────────────────────────────────
# ALERT PROFILY – každý profil je samostatná sada filtrů
# Při splnění podmínek profilu přijde email s daným profilem v předmětu
#
# Povinné klíče:
#   name        – zobrazí se v emailu jako sekce
#   email       – komu poslat (nebo None = použij ALERT_EMAIL z .env)
#
# Volitelné klíče (None = nefiltruj):
#   max_category  – nejhorší akceptovaná kategorie; pořadí: A < low-B < mid-B < C
#                   hodnoty: "A", "low-B", "mid-B"   (case-insensitive)
#   sizes         – list akceptovaných velikostí, např. ["XS", "S"] nebo None
#   max_price_eur – max cena v EUR nebo None
#   min_year      – rok výroby >= tato hodnota nebo None (použije CURRENT_YEAR-5)
#   countries     – list zemí ["CZ","AT","DE","CH"] nebo None = vše
# ──────────────────────────────────────────────────────────────────────────────
ALERT_PROFILES = [
    {
        "name": "Martin – velikost S/M (mid-B a níže)",
        "email": None,           # použije ALERT_EMAIL = zimmema3@gmail.com
        "max_category": "mid-B", # EN A + low-B + mid-B
        # S, M, ML + rozměrové kódy odpovídající S a M (Advance, Ozone, Gin, ...)
        "sizes": ["S", "SM", "M", "ML", "24", "25", "26", "27", "28"],
        "max_price_eur": None,
        "min_year": CURRENT_YEAR - 5,
        "countries": None,
    },
    {
        "name": "Klárka – EN A / low-B, XS/S",
        # DOČASNĚ přesměrováno na Martina kvůli testování;
        # pro ostré nasazení vrátit zpět na "klsavlova@gmail.com"
        "email": None,
        "max_category": "low-B", # EN A + low-B (začátečnická křídla)
        "sizes": ["XS", "S", "22", "23", "24", "25", "26"],
        "max_price_eur": None,
        "min_year": CURRENT_YEAR - 6,
        "countries": None,
    },
    # Přidej další profil zkopírováním a upravením:
    # {
    #     "name": "Kamarád – low-B L",
    #     "email": "nekdo@gmail.com",
    #     "max_category": "low-B",
    #     "sizes": ["L", "LM"],
    #     "max_price_eur": 2000,
    #     "min_year": CURRENT_YEAR - 4,
    #     "countries": ["CZ", "AT"],
    # },
]

# ──────────────────────────────────────────────────────────────────────────────
# Interní mapování kategorie → číselná úroveň pro porovnání max_category
# ──────────────────────────────────────────────────────────────────────────────
CATEGORY_LEVEL = {
    "a":     1,
    "low-b": 2,
    "mid-b": 3,
}

# Klíčová slova v textu kategorie / názvu → úroveň (pro zařazení inzerátu)
CATEGORY_KEYWORDS_TO_LEVEL = [
    # Nejdřív specifičtější
    (["b-r", "mid b", "mid-b", "mentor", "sigma", "delta", "chili", "peak"], 3),
    (["b-g", "low b", "low-b", "rush", "ion", "epsilon", "hook", "geo",
      "tonic", "serac", "nyra", "cure", "comet", "tenor", "rook",
      "leaf", "volt", "elan", "bonanza", "aspen", "discovery"], 2),
    (["en a", "en/a", "dhv 1 ", "ltf 1 ", "dhv1", "ltf1",
      "alpha", "ion light", "prion", "buzz z", "mito", "koyot",
      "eden", "venus", "eona", "susi", "rise", "meru"], 1),
    (["en b", "en/b", "dhv 1-2", "ltf 1-2", "dhv 1/2"], 2),  # default B → low-B
]

# ──────────────────────────────────────────────────────────────────────────────
# ZDROJE
# enabled=False → zakomentovat dočasně bez mazání
# ──────────────────────────────────────────────────────────────────────────────
SOURCES = [

    # ── CZ ──────────────────────────────────────────────────────────────────
    {
        "id": "paragliding_bazar_cz_b",
        "name": "Paragliding Bazar CZ – EN B",
        "country": "CZ",
        "url": "https://paragliding-bazar.cz/cs/wings/en-b-ltf-dhv-1-2-standard/",
        "enabled": True,
        "notes": "Statický HTML, BS4 scraper, paginace /?page=N",
    },
    {
        "id": "paragliding_bazar_cz_a",
        "name": "Paragliding Bazar CZ – EN A",
        "country": "CZ",
        "url": "https://paragliding-bazar.cz/cs/wings/en-a-ltf-dhv-1/",
        "enabled": True,
        "notes": "Statický HTML, BS4 scraper, paginace /?page=N",
    },
    {
        "id": "bazos_cz",
        "name": "Bazoš CZ – křídla",
        "country": "CZ",
        "url": "https://sport.bazos.cz/inzeraty/paragliding-kridlo/",
        "enabled": True,
        "notes": "Statický HTML, BS4 scraper, málo inzerátů (~10)",
    },
    {
        "id": "mamekridla_cz",
        "name": "Máme Křídla CZ",
        "country": "CZ",
        "url": "https://mamekridla.cz/",
        "enabled": True,
        "notes": "E-shop, statický HTML, produktové karty",
    },
    {
        "id": "abc_paragliding_cz",
        "name": "ABC Paragliding CZ – Bazar",
        "country": "CZ",
        "url": "https://www.abcparagliding.cz/bazar/13-prodam/",
        "enabled": True,
        "trusted": True,
        "notes": "HTML tabulka (model | vel | EN | rok | cena € | stav), bez per-row URL",
    },
    {
        "id": "airsport_cz",
        "name": "Air-Sport CZ – Bazar",
        "country": "CZ",
        "url": "https://www.air-sport.cz/index.php?id_category=15&controller=category&id_lang=2",
        "enabled": True,
        "notes": "PrestaShop, ceny v Kč → /25 EUR (orientačně)",
    },

    # ── AT ──────────────────────────────────────────────────────────────────
    {
        "id": "willhaben_at",
        "name": "Willhaben AT – Gleitschirm",
        "country": "AT",
        # JSON API endpoint – vrací data bez JS renderu
        "url": "https://www.willhaben.at/webapi/iad/search/atz/seo/kaufen-und-verkaufen/l/gleitschirm",
        "enabled": True,
        "notes": "JSON API, rows=100, header Accept: application/json",
    },
    {
        "id": "paragliding_store_at",
        "name": "Paragliding Store AT – Used",
        "country": "AT",
        "url": "https://www.paragliding-store.at/shop/gebrauchtmarkt-used-stuff/used-paragliders/",
        "enabled": True,
        "trusted": True,  # specializovaný paragliding obchod → vše jsou křídla
        "notes": "Cumulus CMS shop (Jimdo), hproduct microformat – jen křídla, ne harness",
    },
    {
        "id": "parafly_at",
        "name": "Parafly AT – Gebrauchtmarkt",
        "country": "AT",
        "url": "https://shop.parafly.at/produkt-kategorie/gebrauchtmarkt/",
        "enabled": True,
        "trusted": True,
        "notes": "WooCommerce, generic scraper",
    },
    {
        "id": "gleitschirmschule_at",
        "name": "Gleitschirmschule AT \u2013 Gebraucht",
        "country": "AT",
        "url": "https://www.gleitschirmschule.at/shop/gebraucht/",
        "enabled": False,  # Shop renderován JavaScriptem – statický HTML neobsahuje produkty
        "trusted": True,
        "notes": "JS-rendered Shopware – bez headless browseru nelze scrapovat",
    },

    # ── DE ──────────────────────────────────────────────────────────────────
    {
        "id": "flugsport_de",
        "name": "Flugsport DE – Gebrauchtschirme",
        "country": "DE",
        "url": "https://www.flugsport.de/flugsportladen/gebrauchtschirme.html",
        "enabled": True,
        "notes": "HTML tabulka, přímo parsovatelná, B-G kategorie",
    },
    {
        "id": "hochries_de",
        "name": "Flugschule Hochries DE – Gebrauchtmarkt",
        "country": "DE",
        "url": "https://shop.flugschule-hochries.de/Gebrauchtmarkt/",
        "enabled": True,
        "trusted": True,
        "notes": "Shopware 6, .product-box, generic shopware scraper",
    },
    {
        "id": "kleinanzeigen_de",
        "name": "Kleinanzeigen DE – Atom feed",
        "country": "DE",
        # Atom/RSS feed – nevyžaduje JS render
        "url": "https://www.kleinanzeigen.de/s-sport-camping/paragliding/k0c230.atom",
        "enabled": True,
        "notes": "Atom XML feed, žádný JS",
    },
    {
        "id": "dhv_de",
        "name": "DHV Gebrauchtmarkt DE",
        "country": "DE",
        "url": "https://www.dhv.de/mitgliedschaft/gebrauchtmarkt/",
        "enabled": False,  # vyžaduje DHV přihlášení – TODO
        "notes": "Vyžaduje DHV členský login, zatím disabled",
    },

    # ── CH ──────────────────────────────────────────────────────────────────
    {
        "id": "swissgliders_ch",
        "name": "Swissgliders CH – Fundgrube",
        "country": "CH",
        "url": "https://swissgliders.ch/de/fundgrube/",
        "enabled": True,
        "trusted": True,
        "notes": "article.slide-entry, dedicated scraper",
    },
    {
        "id": "paraglidingshop_ch",
        "name": "Paraglidingshop CH – Occasionen",
        "country": "CH",
        "url": "https://paraglidingshop.ch/Gleitschirme/Occasionen-Ex-Demo/",
        "enabled": True,
        "trusted": True,
        "notes": "E-shop statický HTML",
    },
    {
        "id": "alpstein_ch",
        "name": "Flugschule Alpstein CH – Occasionen",
        "country": "CH",
        "url": "https://www.flugschule-alpstein.ch/occasionen/",
        "enabled": True,
        "trusted": True,
        "notes": "Statický HTML",
    },
    {
        "id": "fly_ikarus_ch",
        "name": "Fly Ikarus CH – Occasionen",
        "country": "CH",
        "url": "https://fly-ikarus.ch/produkt-kategorie/occasionen/",
        "enabled": True,
        "trusted": True,
        "notes": "WooCommerce, generic scraper",
    },
    # ── TODO – kandidáti vyžadující custom scraper / další ladění ──────────
    # {
    #     "id": "gleitschirm_direkt_de",  # Joomla, listing podkategorií, vyžaduje hloubkový crawl
    #     "url": "https://www.gleitschirm-direkt.de/Gebrauchtmarkt/",
    # },
    # {
    #     "id": "airscout365",            # DACH marketplace (.at i .ch alias),
    #     "url": "https://airscout365.at/",  # vyžaduje JS / search query / API
    # },
    # {
    #     "id": "flyingcenter_ch",        # Joomla, plain text seznam, custom parsing
    #     "url": "https://www.flyingcenter.ch/fuer-piloten/ausruestung/occasionen",
    # },
    # {
    #     "id": "airsport_cz",            # PrestaShop s mnoha podkategoriemi
    #     "url": "https://www.air-sport.cz/index.php?id_category=15&controller=category&id_lang=2",
    # },
    # {
    #     "id": "abc_paragliding_cz",     # Vlastní bazar, paginace, neobvyklá struktura
    #     "url": "https://www.abcparagliding.cz/bazar/13-prodam/",
    # },
]
