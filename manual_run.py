# -*- coding: utf-8 -*-""Ruční zkušební běh paragliding weather alertu - zjednodušená verze."""
import requests, pandas as pd, numpy as np, datetime, math, os, webbrowser, tempfile

CB = (48.9747, 14.4743)

SITES = [
    {"name": "Klet",           "lat": 48.8581, "lon": 14.2831, "az_min": 270, "az_max": 360},
    {"name": "Kozi Plan",      "lat": 48.7267, "lon": 14.1631, "az_min":  90, "az_max": 180},
    {"name": "Rana",           "lat": 50.3972, "lon": 13.8031, "az_min": 270, "az_max":  90},
    {"name": "Durrnberg (A)",  "lat": 47.6350, "lon": 13.0930, "az_min": 180, "az_max": 270},
    {"name": "Javorovy vrch",  "lat": 49.6517, "lon": 18.6261, "az_min": 270, "az_max":  30},  # Beskydy, SZ-S-SV
]

# Limity pro zacatecnika: prumer 4 m/s, narazy 5 m/s
LIMITS = {"wind": 4.0, "gust": 5.0, "gf": 1.4, "tol": 30, "min_streak": 3}
MAX_DIST_KM = 400  # docasne zvyseno kvuli Javorovemu (~340 km)


def haversine(a, b):
    R = 6371
    la1, la2 = math.radians(a[0]), math.radians(b[0])
    dla = math.radians(b[0]-a[0]); dlo = math.radians(b[1]-a[1])
    h = math.sin(dla/2)**2 + math.cos(la1)*math.cos(la2)*math.sin(dlo/2)**2
    return 2*R*math.asin(math.sqrt(h))


def dir_in_window(wd, lo, hi, tol):
    a = (lo - tol) % 360
    b = (hi + tol) % 360
    return (wd >= a) and (wd <= b) if a < b else (wd >= a) or (wd <= b)


def fetch(lat, lon):
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&hourly=wind_speed_10m,wind_gusts_10m,wind_direction_10m,precipitation,pressure_msl"
           "&wind_speed_unit=ms&forecast_days=2&timezone=Europe/Prague")
    return requests.get(url, timeout=20).json()


def main():
    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    print(f"\n=== Paragliding weather alert ===")
    print(f"Dnes: {today}  |  Vyhodnocuji zitrek: {tomorrow}\n")

    # Synoptika (stred CR)
    syn = fetch(49.5, 15.5)
    p = np.array(syn["hourly"]["pressure_msl"])
    t = syn["hourly"]["time"]
    p_today = np.mean([p[i] for i, x in enumerate(t) if x.startswith(today)])
    p_tom = np.mean([p[i] for i, x in enumerate(t) if x.startswith(tomorrow)])
    delta = p_tom - p_today
    if delta > 2:
        syn_txt = "stabilni vysoky tlak"
    elif delta < -2:
        syn_txt = "pokles tlaku / fronta"
    else:
        syn_txt = "mirne promenlive"
    print(f"Synoptika (stred CR): {syn_txt}, delta p = {delta:+.1f} hPa\n")

    rows = []
    details = {}
    for s in SITES:
        dist = haversine(CB, (s["lat"], s["lon"]))
        if dist > MAX_DIST_KM:
            continue
        w = fetch(s["lat"], s["lon"])
        df = pd.DataFrame({
            "time": w["hourly"]["time"],
            "ws":   w["hourly"]["wind_speed_10m"],
            "wg":   w["hourly"]["wind_gusts_10m"],
            "wd":   w["hourly"]["wind_direction_10m"],
            "pr":   w["hourly"]["precipitation"],
        })
        df = df[df["time"].str.startswith(tomorrow)].copy()
        df["h"] = df["time"].str[11:13].astype(int)
        df = df[(df["h"] >= 6) & (df["h"] <= 21)].reset_index(drop=True)
        df["dir_ok"] = df["wd"].apply(lambda x: dir_in_window(x, s["az_min"], s["az_max"], LIMITS["tol"]))
        df["fly"] = (
            (df["ws"] <= LIMITS["wind"]) &
            (df["wg"] <= LIMITS["gust"]) &
            (df["pr"] <= 0) &
            df["dir_ok"]
        )
        streak = mx = 0
        for ok in df["fly"]:
            streak = streak + 1 if ok else 0
            mx = max(mx, streak)
        rows.append({
            "site": s["name"],
            "dist_km": round(dist, 0),
            "fly_h": int(df["fly"].sum()),
            "streak": mx,
            "ws_avg": round(df["ws"].mean(), 1),
            "wg_max": round(df["wg"].max(), 1),
            "wd_avg": int(df["wd"].mean()),
            "rain_mm": round(df["pr"].sum(), 1),
        })
        details[s["name"]] = df

    summary = pd.DataFrame(rows).sort_values(["streak", "fly_h"], ascending=False).reset_index(drop=True)
    print("=== Souhrn ploch (denni okno 6-21) ===")
    print(summary.to_string(index=False))

    good = summary[summary["streak"] >= LIMITS["min_streak"]]
    print()
    if good.empty:
        print(">>> VERDIKT: Zitra NIKDE vhodne podminky pro zacatecnika.")
    else:
        print(">>> VERDIKT: LETET! Doporucene plochy:")
        for _, r in good.iterrows():
            print(f"   * {r['site']} - {r['streak']} h v kuse, vitr {r['ws_avg']} m/s, narazy do {r['wg_max']} m/s, smer ~{r['wd_avg']}°")

    print("\n=== Detail po plochach ===")
    for name, df in details.items():
        print(f"\n-- {name} --")
        print(df[["h", "ws", "wg", "wd", "pr", "dir_ok", "fly"]].to_string(index=False))

    html = build_html(tomorrow, today, syn_txt, delta, summary, details)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paraglide_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML report: {out}")
    webbrowser.open(f"file://{out}")


def wind_arrow(deg):
    """Vrátí Unicode šipku podle směru větru (odkud vítr fouká)."""
    dirs = ["↓","↙","←","↖","↑","↗","→","↘"]
    return dirs[int(((deg + 22.5) % 360) / 45)]


def build_html(tomorrow, today, syn_txt, delta, summary, details):
    if delta > 2:
        syn_color, syn_icon = "#2ecc71", "📈"
    elif delta < -2:
        syn_color, syn_icon = "#e74c3c", "📉"
    else:
        syn_color, syn_icon = "#f39c12", "📊"

    good_any = not summary[summary["streak"] >= LIMITS["min_streak"]].empty
    verdict_bg = "#1a472a" if good_any else "#4a1942"
    verdict_txt = "✅ LETĚT!" if good_any else "❌ Zítra nikde vhodné podmínky"

    # Souhrnné karty ploch
    cards_html = ""
    for _, r in summary.iterrows():
        fly_ok = r["streak"] >= LIMITS["min_streak"]
        card_color = "#1a472a" if fly_ok else "#2c2c2c"
        border = "#2ecc71" if fly_ok else "#555"
        badge = f'<span style="background:#2ecc71;color:#000;padding:2px 8px;border-radius:12px;font-size:0.8em;font-weight:bold;">✈ LETĚT • {r["streak"]} h v kuse</span>' if fly_ok else f'<span style="background:#555;color:#aaa;padding:2px 8px;border-radius:12px;font-size:0.8em;">streak: {r["streak"]} h</span>'
        ws_color = "#2ecc71" if r["ws_avg"] <= LIMITS["wind"] else "#e74c3c"
        wg_color = "#2ecc71" if r["wg_max"] <= LIMITS["gust"] else "#e74c3c"
        cards_html += f"""
        <div style="background:{card_color};border:1px solid {border};border-radius:10px;padding:16px 20px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="font-size:1.2em;font-weight:bold;">[^] {r['site']}</span>
            <span style="color:#aaa;font-size:0.85em;">{r['dist_km']} km od Č. Budějovic</span>
          </div>
          <div style="margin-bottom:8px;">{badge}</div>
          <div style="display:flex;gap:20px;font-size:0.9em;flex-wrap:wrap;">
            <span>💨 vítr avg: <b style="color:{ws_color}">{r['ws_avg']} m/s</b></span>
            <span>💥 nárazy max: <b style="color:{wg_color}">{r['wg_max']} m/s</b></span>
            <span>🧭 směr: <b>{wind_arrow(r['wd_avg'])} {r['wd_avg']}°</b></span>
            <span>🌧 srážky: <b>{r['rain_mm']} mm</b></span>
            <span>⏱ letových h: <b>{r['fly_h']}</b></span>
          </div>
        </div>"""

    # Detail tabulky
    detail_tabs = ""
    tab_buttons = ""
    first = True
    for name, df in details.items():
        tid = name.replace(" ", "_").replace("(", "").replace(")", "")
        active_btn = "background:#3498db;color:#fff;" if first else "background:#2c2c2c;color:#aaa;"
        active_div = "block" if first else "none"
        tab_buttons += f'<button onclick="showTab(\'{tid}\')" id="btn_{tid}" style="{active_btn}border:none;padding:8px 16px;border-radius:6px;cursor:pointer;margin-right:6px;margin-bottom:6px;">{name}</button>'
        rows_html = ""
        for _, row in df.iterrows():
            fly_style = "background:#1a472a;" if row["fly"] else ""
            dir_icon = "✅" if row["dir_ok"] else "❌"
            fly_icon = "✈" if row["fly"] else "–"
            wg_style = "color:#e74c3c;font-weight:bold;" if row["wg"] > LIMITS["gust"] else ""
            ws_style = "color:#e74c3c;font-weight:bold;" if row["ws"] > LIMITS["wind"] else ""
            rows_html += f"""<tr style="{fly_style}">
              <td style="padding:6px 10px;text-align:center;">{int(row['h']):02d}:00</td>
              <td style="padding:6px 10px;text-align:center;{ws_style}">{row['ws']:.1f}</td>
              <td style="padding:6px 10px;text-align:center;{wg_style}">{row['wg']:.1f}</td>
              <td style="padding:6px 10px;text-align:center;">{wind_arrow(row['wd'])} {int(row['wd'])}°</td>
              <td style="padding:6px 10px;text-align:center;">{row['pr']:.1f}</td>
              <td style="padding:6px 10px;text-align:center;">{dir_icon}</td>
              <td style="padding:6px 10px;text-align:center;font-size:1.1em;">{fly_icon}</td>
            </tr>"""
        detail_tabs += f"""
        <div id="tab_{tid}" style="display:{active_div};">
          <table style="width:100%;border-collapse:collapse;font-size:0.9em;">
            <thead><tr style="background:#1a1a2e;color:#aaa;">
              <th style="padding:8px 10px;">Hodina</th>
              <th style="padding:8px 10px;">Vítr<br><small>m/s</small></th>
              <th style="padding:8px 10px;">Nárazy<br><small>m/s</small></th>
              <th style="padding:8px 10px;">Směr</th>
              <th style="padding:8px 10px;">Déšť<br><small>mm</small></th>
              <th style="padding:8px 10px;">Směr OK</th>
              <th style="padding:8px 10px;">Letět</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>"""
        first = False

    limits_html = f"""
    <div style="background:#1e1e2e;border-radius:8px;padding:12px 20px;font-size:0.85em;color:#aaa;display:flex;gap:24px;flex-wrap:wrap;">
      <span>💨 max vítr: <b style="color:#fff">{LIMITS['wind']} m/s</b></span>
      <span>💥 max nárazy: <b style="color:#fff">{LIMITS['gust']} m/s</b></span>
      <span>📐 gust factor: <b style="color:#fff">≤ {LIMITS['gf']}</b></span>
      <span>⏱ min. streak: <b style="color:#fff">{LIMITS['min_streak']} h</b></span>
      <span>🧭 tolerance směru: <b style="color:#fff">±{LIMITS['tol']}°</b></span>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <title>🪂 Paragliding Alert – {tomorrow}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: #121212; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; padding: 24px; max-width: 900px; margin: 0 auto; }}
    h2 {{ margin-bottom: 6px; }}
    h3 {{ margin: 20px 0 10px; color: #aaa; font-size: 0.95em; text-transform: uppercase; letter-spacing: 1px; }}
  </style>
</head>
<body>
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px;flex-wrap:wrap;gap:12px;">
    <div>
      <h2>🪂 Paragliding Weather Alert</h2>
      <div style="color:#888;font-size:0.9em;">Vygenerováno: {today} &nbsp;|&nbsp; Hodnocený den: <b style="color:#fff">{tomorrow}</b></div>
    </div>
    <div style="background:{syn_color}22;border:1px solid {syn_color};border-radius:8px;padding:10px 18px;text-align:center;">
      <div style="font-size:1.5em;">{syn_icon}</div>
      <div style="font-size:0.85em;color:{syn_color};font-weight:bold;">{syn_txt}</div>
      <div style="font-size:0.8em;color:#aaa;">Δp = {delta:+.1f} hPa</div>
    </div>
  </div>

  <div style="background:{verdict_bg};border-radius:10px;padding:18px 24px;margin-bottom:24px;font-size:1.3em;font-weight:bold;text-align:center;">
    {verdict_txt}
  </div>

  <h3>Limity pro začátečníka</h3>
  {limits_html}

  <h3>Přehled ploch</h3>
  {cards_html}

  <h3>Detail po hodinách (6–21 h)</h3>
  <div style="margin-bottom:12px;">{tab_buttons}</div>
  {detail_tabs}

  <div style="margin-top:32px;color:#555;font-size:0.8em;text-align:center;">Data: Open-Meteo API &nbsp;•&nbsp; Referenční bod: České Budějovice</div>

  <script>
    function showTab(id) {{
      document.querySelectorAll('[id^="tab_"]').forEach(el => el.style.display = 'none');
      document.querySelectorAll('[id^="btn_"]').forEach(el => {{ el.style.background='#2c2c2c'; el.style.color='#aaa'; }});
      document.getElementById('tab_' + id).style.display = 'block';
      document.getElementById('btn_' + id).style.background = '#3498db';
      document.getElementById('btn_' + id).style.color = '#fff';
    }}
  </script>
</body>
</html>"""


if __name__ == "__main__":
    main()
