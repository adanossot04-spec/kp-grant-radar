#!/usr/bin/env python3
"""Добирає e-mail придунайських громад там, де Wikidata його не має.

Заходить на офіційний сайт громади (поле `site` у `config/danube_partners.yaml`),
перебирає типові сторінки контактів кількома мовами й витягує адреси. Бере
лише адреси на домені самої громади і віддає перевагу «офіційним» скриньках
(hivatal, onkormanyzat, primaria, gemeinde, info, office…). Результат
дописується в той самий YAML — повторний запуск не чіпає вже заповнені рядки.

Запуск:  python3 scripts/harvest_emails.py [--workers 8] [--limit 0]
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
YAML_PATH = ROOT / "config" / "danube_partners.yaml"

PAGES = ("", "kapcsolat", "elerhetoseg", "elerhetosegek", "onkormanyzat",
         "hivatal", "polgarmesteri-hivatal", "kontakt", "impressum",
         "contact", "contacts", "contacte", "date-de-contact", "primaria",
         "despre-noi/contact", "kapcsolatok", "ugyintezes")

EMAIL_RX = re.compile(r"[\w\.\-\+]+@[\w\-]+(?:\.[\w\-]+)+", re.I)
JUNK = re.compile(r"(example|sentry|wixpress|wordpress|\.png$|\.jpg$|\.jpeg$|"
                  r"\.gif$|\.webp$|no-?reply|donotreply|sentry\.io|"
                  r"webmaster@localhost|@domain|@email|@site|@your)", re.I)
GOOD = re.compile(r"(hivatal|onkormanyzat|önkormányzat|polgarmester|jegyzo|"
                  r"primaria|primar|consiliul|gemeinde|stadt|amt|rathaus|"
                  r"info|office|post|kontakt|contact|titkarsag|secretariat)", re.I)

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KP-GrantRadar/1.0; "
                         "+mailto:adanossot@ukr.net)",
           "Accept-Language": "hu,ro,de,en;q=0.8"}


def domain(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def rank(mail: str, site_domain: str) -> tuple[int, int, int, str]:
    """Менше — краще: спершу адреси на домені громади й «офіційні» скриньки."""
    mail_domain = mail.split("@")[-1].lower()
    same = 0 if (site_domain and (mail_domain == site_domain
                                  or mail_domain.endswith("." + site_domain)
                                  or site_domain.endswith("." + mail_domain))) else 1
    return (same, 0 if GOOD.search(mail) else 1, len(mail), mail)


def harvest(entry: dict) -> list[str]:
    site = entry.get("site") or ""
    if not site:
        return []
    found: set[str] = set()
    sd = domain(site)
    session = requests.Session()
    for page in PAGES:
        url = urljoin(site.rstrip("/") + "/", page)
        try:
            r = session.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        except Exception:
            continue
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            continue
        for m in EMAIL_RX.findall(r.text):
            m = m.strip(".").lower()
            if not JUNK.search(m) and len(m) < 60:
                found.add(m)
        if any(rank(m, sd)[0] == 0 for m in found):
            break
    ordered = sorted(found, key=lambda m: rank(m, sd))
    return [m for m in ordered if rank(m, sd)[0] == 0][:3] or ordered[:1]


ORDER = ("country", "lang", "admin", "site", "email", "email_alt", "phone")


def dump(partners: list[dict]) -> str:
    """Той самий формат, що й у scripts/fetch_danube_partners.py."""
    def esc(value) -> str:
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    out = []
    for p in partners:
        out.append(f"  - name: {esc(p['name'])}")
        for key in ORDER:
            if not p.get(key):
                continue
            out.append(f"    {key}: {p[key]}" if key in ("country", "lang")
                       else f"    {key}: {esc(p[key])}")
        out.append(f"    population: {p.get('population', 0)}")
        out.append(f"    osm: {p.get('osm', 0)}")
        if p.get("wikidata"):
            out.append(f"    wikidata: {p['wikidata']}")
        if p.get("coords"):
            out.append(f"    coords: [{p['coords'][0]}, {p['coords'][1]}]")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="0 — усі")
    args = ap.parse_args()

    raw = YAML_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    partners = data.get("partners") or []
    todo = [p for p in partners if not p.get("email") and p.get("site")]
    if args.limit:
        todo = todo[:args.limit]
    print(f"Шукаю e-mail для {len(todo)} громад (усього {len(partners)})…",
          flush=True)

    results: dict[int, list[str]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, mails in zip(range(len(todo)), pool.map(harvest, todo)):
            results[i] = mails
            if mails:
                print(f"  ✉️  {todo[i]['name']}: {mails[0]}", flush=True)

    # перезаписуємо файл, зберігаючи шапку з коментарями
    added = 0
    for i, p in enumerate(todo):
        mails = results.get(i) or []
        if mails:
            p["email"] = mails[0]
            if len(mails) > 1:
                p["email_alt"] = ", ".join(mails[1:])
            added += 1
    head = raw.split("\npartners:")[0]
    YAML_PATH.write_text(head + "\npartners:\n" + dump(partners), encoding="utf-8")

    check = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))["partners"]
    have = sum(1 for p in check if p.get("email"))
    print(f"✅ додано {added} адрес · тепер з e-mail: {have} з {len(check)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
