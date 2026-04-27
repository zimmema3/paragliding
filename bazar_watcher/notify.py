# -*- coding: utf-8 -*-
"""
Email notifikace pro bazar_watcher.

Posílá jeden souhrnný email s oddílem pro každý alert profil.
Pokud profil nemá žádné matching inzeráty, oddíl se nezobrazí.

Env proměnné (.env nebo GitHub Secrets):
  SMTP_SERVER   (default: smtp.gmail.com)
  SMTP_PORT     (default: 465)
  SMTP_USER     – přihlašovací email
  SMTP_PASS     – app password
  ALERT_EMAIL   – výchozí příjemce (pokud profil nemá vlastní email)
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_LOADED = False


def _load_env():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent / ".env"
        load_dotenv(dotenv_path=env_path, override=False)
    except ImportError:
        pass
    _ENV_LOADED = True


def _smtp_cfg() -> dict:
    _load_env()
    return {
        "server":   os.environ.get("SMTP_SERVER", "smtp.gmail.com"),
        "port":     int(os.environ.get("SMTP_PORT", "465")),
        "user":     os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASS", ""),
        "default_to": os.environ.get("ALERT_EMAIL", os.environ.get("SMTP_USER", "")),
    }


# ──────────────────────────────────────────────────────────────────────────────
# HTML generátor
# ──────────────────────────────────────────────────────────────────────────────

def _table_rows(listings: list[dict]) -> str:
    rows = ""
    for lst in listings:
        price = f"{float(lst['price_eur']):.0f} €" if lst.get("price_eur") else "—"
        year  = str(lst.get("year") or "—")
        cat   = lst.get("category") or "—"
        src   = lst.get("source_name") or lst.get("source_id") or "—"
        url   = lst.get("url") or "#"
        title = lst.get("title") or "—"
        size  = lst.get("size") or "—"
        wt    = lst.get("weight_range") or "—"
        ctry  = lst.get("country") or "—"
        rows += f"""
    <tr>
      <td style="padding:5px 8px;border:1px solid #ddd;">{ctry} – {src}</td>
      <td style="padding:5px 8px;border:1px solid #ddd;">
        <a href="{url}" style="color:#1a73e8;">{title[:90]}</a>
      </td>
      <td style="padding:5px 8px;border:1px solid #ddd;text-align:center;">{cat}</td>
      <td style="padding:5px 8px;border:1px solid #ddd;text-align:center;">{year}</td>
      <td style="padding:5px 8px;border:1px solid #ddd;text-align:right;">{price}</td>
      <td style="padding:5px 8px;border:1px solid #ddd;text-align:center;">{size}</td>
      <td style="padding:5px 8px;border:1px solid #ddd;text-align:center;">{wt}</td>
    </tr>"""
    return rows


def _profile_section(profile: dict, listings: list[dict]) -> str:
    if not listings:
        return ""
    rows = _table_rows(listings)
    cat_label = profile.get("max_category", "?")
    sizes_label = ", ".join(profile.get("sizes") or []) or "libovolná"
    price_label = f"max {profile['max_price_eur']} €" if profile.get("max_price_eur") else "—"

    return f"""
  <h3 style="font-family:sans-serif;margin-top:24px;border-left:4px solid #1a73e8;
             padding-left:10px;color:#222;">
    🪂 {profile['name']} ({len(listings)} nových)
  </h3>
  <p style="font-family:sans-serif;font-size:12px;color:#555;margin:4px 0 8px 14px;">
    Kategorie: max <strong>{cat_label}</strong> &nbsp;|&nbsp;
    Velikosti: <strong>{sizes_label}</strong> &nbsp;|&nbsp;
    Cena: <strong>{price_label}</strong>
  </p>
  <table style="border-collapse:collapse;font-family:sans-serif;font-size:12px;width:100%;">
    <thead>
      <tr style="background:#1a73e8;color:white;font-size:11px;">
        <th style="padding:6px 8px;border:1px solid #ddd;">Zdroj</th>
        <th style="padding:6px 8px;border:1px solid #ddd;">Inzerát</th>
        <th style="padding:6px 8px;border:1px solid #ddd;">Kat.</th>
        <th style="padding:6px 8px;border:1px solid #ddd;">Rok</th>
        <th style="padding:6px 8px;border:1px solid #ddd;">Cena</th>
        <th style="padding:6px 8px;border:1px solid #ddd;">Vel.</th>
        <th style="padding:6px 8px;border:1px solid #ddd;">Váha</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>"""


def _build_email_html(profile_matches: dict[str, tuple[dict, list[dict]]]) -> str:
    """
    profile_matches: { profile_name: (profile_dict, [listings]) }
    """
    sections = "".join(
        _profile_section(prof, listings)
        for prof, listings in profile_matches.values()
        if listings
    )
    total = sum(len(lst) for _, lst in profile_matches.values())

    return f"""<html><body style="max-width:900px;margin:auto;">
  <h2 style="font-family:sans-serif;color:#1a73e8;">
    🪂 Bazar křídel – {total} nových inzerátů ({date.today()})
  </h2>
  {sections}
  <p style="font-family:sans-serif;font-size:11px;color:#aaa;margin-top:24px;">
    Paragliding Bazar Watcher &nbsp;|&nbsp; CZ · AT · DE · CH &nbsp;|&nbsp;
    Mid-B a níže &nbsp;|&nbsp; {date.today()}
  </p>
</body></html>"""


# ──────────────────────────────────────────────────────────────────────────────
# Odesílání
# ──────────────────────────────────────────────────────────────────────────────

def _send_smtp(cfg: dict, to: str, subject: str, html: str, plain: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = to
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        context = ssl.create_default_context()
        if cfg["port"] == 587:
            with smtplib.SMTP(cfg["server"], cfg["port"]) as smtp:
                smtp.starttls(context=context)
                smtp.login(cfg["user"], cfg["password"])
                smtp.sendmail(cfg["user"], to, msg.as_string())
        else:
            with smtplib.SMTP_SSL(cfg["server"], cfg["port"], context=context) as smtp:
                smtp.login(cfg["user"], cfg["password"])
                smtp.sendmail(cfg["user"], to, msg.as_string())
        return True
    except smtplib.SMTPException as exc:
        logger.error("SMTP selhalo (%s): %s", to, exc)
        return False


def send_alerts(
    profile_matches: dict[str, tuple[dict, list[dict]]],
    dry_run: bool = False,
) -> bool:
    """
    Pošle emaily pro všechny profily co mají matching inzeráty.

    profile_matches format:
      { "Martin – M mid-B a níže": (profile_dict, [listing, ...]), ... }

    Pokud všechny profily mají stejný email (nebo None) → 1 souhrnný email.
    Pokud má profil vlastní email → samostatný email jen pro ten profil.

    Returns True pokud vše proběhlo (nebo dry_run).
    """
    cfg = _smtp_cfg()

    # Seskup profily dle cílového emailu
    by_email: dict[str, dict[str, tuple[dict, list]]] = {}
    for name, (prof, listings) in profile_matches.items():
        if not listings:
            continue
        target = prof.get("email") or cfg["default_to"] or ""
        if not target:
            logger.warning("Profil '%s': neznámý cílový email, přeskakuji.", name)
            continue
        by_email.setdefault(target, {})[name] = (prof, listings)

    if not by_email:
        logger.info("Žádné matching inzeráty pro žádný profil → email se neposílá.")
        return True

    if not cfg["user"] or not cfg["password"]:
        logger.warning("SMTP přihlašovací údaje chybí. Email se neposílá.")
        return False

    success = True
    for to_addr, profiles in by_email.items():
        total = sum(len(lst) for _, lst in profiles.values())
        subject = (
            f"🪂 Bazar křídel: {total} nový{'ch' if total > 1 else ''} inzerát"
            f"{'ů' if total > 1 else ''} – "
            + ", ".join(profiles.keys())[:60]
            + f" ({date.today()})"
        )
        html = _build_email_html(profiles)

        # Plaintext fallback
        plain_lines = [f"Nové inzeráty ({date.today()}):\n"]
        for pname, (_, listings) in profiles.items():
            plain_lines.append(f"\n== {pname} ({len(listings)}) ==")
            for lst in listings:
                plain_lines.append(
                    f"  {lst.get('source_name')} | {lst.get('title','')[:80]} | "
                    f"{lst.get('price_eur','?')} € | rok {lst.get('year','?')}\n"
                    f"  {lst.get('url','')}"
                )
        plain = "\n".join(plain_lines)

        if dry_run:
            print(f"\n{'='*60}")
            print(f"DRY RUN → To: {to_addr}")
            print(f"Subject: {subject}")
            for pname, (_, listings) in profiles.items():
                print(f"  [{pname}] {len(listings)} inzerátů")
                for lst in listings:
                    print(f"    - {lst.get('title','')[:80]} | {lst.get('price_eur','?')} € | {lst.get('year','?')}")
            print("=" * 60)
        else:
            ok = _send_smtp(cfg, to_addr, subject, html, plain)
            if ok:
                logger.info("Email odeslán → %s (%d inzerátů)", to_addr, total)
            else:
                success = False

    return success
