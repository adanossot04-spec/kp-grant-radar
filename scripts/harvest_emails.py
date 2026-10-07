#!/usr/bin/env python3
"""Добирає e-mail придунайських громад там, де Wikidata його не має.

Заходить на офіційний сайт громади (поле `site` у `config/danube_partners.yaml`),
перебирає типові сторінки контактів кількома мовами й витягує адреси. Бере
лише адреси на домені самої громади і віддає перевагу «офіційним» скриньках
(hivatal, onkormanyzat, primaria, gemeinde, info, office…). Результат
дописується в той самий YAML — повторний запуск не чіпає вже заповнені рядки.

Окремо шукає пряму скриньку голови міста (Bürgermeister, sindaco, maire,
burgemeester, polgármester…) — її видно в колонці «пошта мера».

Запуск:  python3 scripts/harvest_emails.py [--file config/…] [--workers 8]
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
DEFAULT_YAML = ROOT / "config" / "danube_partners.yaml"

PAGES = ("", "kontakt", "contatti", "contatto", "kapcsolat", "elerhetoseg", "elerhetosegek", "onkormanyzat",
         "hivatal", "polgarmesteri-hivatal", "kontakt", "impressum",
         "contact", "contacts", "contacte", "date-de-contact", "primaria",
         "despre-noi/contact", "kapcsolatok", "ugyintezes", "contacto",
         "amministrazione/contatti", "il-comune/contatti", "urp",
         "uffici/urp", "servizi/urp", "comune/urp", "scrivici", "contattaci",
         "aree-tematiche/urp", "municipio/contatti", "comune/contatti", "kontakta-oss",
         "yhteystiedot", "kontaktinformasjon", "contact/colofon",
         "over-deze-site/contact", "gemeinde/kontakt", "rathaus/kontakt")

MAX_LOCAL = 32  # довші локальні частини — майже завжди склеєний текст
EMAIL_RX = re.compile(r"[\w\.\-\+]+@[\w\-]+(?:\.[\w\-]+)+", re.I)
JUNK = re.compile(r"(example|sentry|wixpress|wordpress|\.png$|\.jpg$|\.jpeg$|"
                  r"\.gif$|\.webp$|no-?reply|donotreply|sentry\.io|"
                  r"webmaster@localhost|@domain|@email|@site|@your)", re.I)
# адреси, які технічно існують, але писати на них немає сенсу
BAD = re.compile(r"(rechnung|invoice|faktur|szamla|bewerbung|job|karriere|"
                 r"presse|press@|media@|datenschutz|privacy|dsgvo|abuse|"
                 r"spam|phish|webmaster|redaktion|newsletter|szobaberlet|"
                 r"bibliothek|museum|theater|tourist|shop|ticket)", re.I)
# італійська PEC (сертифікована пошта) приймає листи лише з інших PEC-скриньок
PEC = re.compile(r"@(pec|cert|postacert|legalmail|pecaziendale)\.|"
                 r"@.*\.(pec|cert)\.|@pec\.|@legalmail\.it", re.I)
GOOD = re.compile(r"(hivatal|onkormanyzat|önkormányzat|polgarmester|jegyzo|"
                  r"primaria|primar|consiliul|gemeinde|stadt|amt|rathaus|"
                  r"info|office|post|kontakt|contact|titkarsag|secretariat)", re.I)

# сторінки, де зазвичай є пряма скринька мера
MAYOR_PAGES = ("buergermeister", "oberbuergermeister", "rathaus/buergermeister",
               "stadt/buergermeister", "politik/buergermeister", "sindaco",
               "il-sindaco", "amministrazione/sindaco", "maire", "le-maire",
               "mairie/le-maire", "burgemeester", "college-van-burgemeester-en-wethouders",
               "bestuur/burgemeester", "mayor", "alcaldia", "alcalde",
               "polgarmester", "primar", "borgmester", "borgmastare",
               "pormestari", "kaupunginjohtaja", "byradsleder", "ordforer",
               "prezydent", "starosta", "zupan", "gradonacelnik", "kmet",
               "borgmesteren", "stadtpraesident", "stadtpraesidentin")

# локальні частини, що вказують на скриньку голови міста
MAYOR_BOX = re.compile(
    r"(b(ü|ue)rgermeister|stadtpr(ä|ae)sident|sindaco|burgemeester|"
    r"polg(á|a)rmester|borgmester|borgm(ä|a)stare|borgmesteren|pormestari|"
    r"kaupunginjohtaja|byr(å|a)dsleder|ordf(ø|o)rer|prezydent|burmistrz|"
    r"alcald|(ž|z)upan|gradona(č|c)elnik|starosta|"
    r"^ob@|^obm@|^maire|^lemaire|^le-maire|^cabinet|^mayor|^primar|"
    r"^segreteria\.sindaco|^ufficio\.sindaco|^gabinetto)", re.I)

# посилання на сторінку голови міста трапляються під різними адресами,
# тому додатково йдемо за посиланнями з головної
MAYOR_LINK = re.compile(
    r"(b(ü|ue)rgermeister|stadtpr(ä|ae)sident|sindaco|maire|burgemeester|"
    r"mayor|polg(á|a)rmester|primar|borgmester|borgm(ä|a)stare|pormestari|"
    r"byr(å|a)dsleder|ordf(ø|o)rer|prezydent|burmistrz|alcald|(ž|z)upan|"
    r"gradona(č|c)elnik|кмет|starosta)", re.I)
A_TAG = re.compile(r'<a\s[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.{0,120}?)</a>',
                   re.I | re.S)
HUB_LINK = re.compile(
    r"(rathaus|stadtverwaltung|verwaltung|politik|amministrazione|municipio|"
    r"il-comune|bestuur|college|gemeenteraad|mairie|municipalite|"
    r"onkormanyzat|hivatal|urzad|miasto|primaria|ayuntamiento|concello|"
    r"kommune|kaupunki|stadshuset|administration|city-council|council|"
    r"government|organisation)", re.I)


def hub_links(html: str, site: str, limit: int = 2) -> list[str]:
    """Розділи «Ратуша / Політика / Amministrazione», де зазвичай мер."""
    out: list[str] = []
    for href, text in A_TAG.findall(html):
        if len(out) >= limit:
            break
        label = re.sub(r"<[^>]+>", " ", text)
        if HUB_LINK.search(href) or HUB_LINK.search(label):
            url = urljoin(site, href)
            if url.startswith("http") and url not in out:
                out.append(url)
    return out


def mayor_links(html: str, site: str, limit: int = 4) -> list[str]:
    """Посилання, що ведуть на сторінку голови міста."""
    out: list[str] = []
    for href, text in A_TAG.findall(html):
        if len(out) >= limit:
            break
        label = re.sub(r"<[^>]+>", " ", text)
        if MAYOR_LINK.search(href) or MAYOR_LINK.search(label):
            url = urljoin(site, href)
            if url.startswith("http") and url not in out:
                out.append(url)
    return out


# Сторінки підбираються за країною: інакше кожне місто означає 45 запитів.
GEN = {
    "de": ("", "kontakt", "impressum", "rathaus/kontakt", "gemeinde/kontakt"),
    "it": ("", "contatti", "urp", "amministrazione/contatti", "comune/contatti"),
    "nl": ("", "contact", "contact/colofon", "over-deze-site/contact"),
    "fr": ("", "contact", "contactez-nous", "mairie", "nous-contacter"),
    "hu": ("", "kapcsolat", "elerhetoseg", "onkormanyzat", "hivatal"),
    "pl": ("", "kontakt", "urzad"),
    "ro": ("", "contact", "primaria", "date-de-contact"),
    "es": ("", "contacto", "contactar", "ayuntamiento"),
    "nord": ("", "kontakt", "kontakta-oss", "yhteystiedot", "kontaktinformasjon"),
    "en": ("", "contact", "contacts", "contact-us"),
}
MAY = {
    "de": ("buergermeister", "oberbuergermeister", "rathaus/buergermeister",
           "stadtpraesident"),
    "it": ("sindaco", "il-sindaco", "amministrazione/sindaco"),
    "nl": ("burgemeester", "bestuur/burgemeester",
           "college-van-burgemeester-en-wethouders"),
    "fr": ("maire", "le-maire", "mairie/le-maire"),
    "hu": ("polgarmester",),
    "pl": ("prezydent", "burmistrz"),
    "ro": ("primar", "primarul"),
    "es": ("alcaldia", "alcalde", "presidente"),
    "nord": ("borgmester", "borgmastare", "pormestari", "byradsleder",
             "ordforer", "kaupunginjohtaja"),
    "en": ("mayor", "mayor-and-council"),
}
GROUP = {"DE": "de", "AT": "de", "CH": "de", "LU": "fr", "LI": "de",
         "IT": "it", "NL": "nl", "BE": "nl", "FR": "fr", "HU": "hu",
         "PL": "pl", "RO": "ro", "ES": "es", "PT": "es",
         "DK": "nord", "SE": "nord", "NO": "nord", "FI": "nord", "IS": "nord"}


def pages_for(entry: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    group = GROUP.get((entry.get("country") or "").upper(), "en")
    general = tuple(dict.fromkeys(GEN[group] + GEN["en"]))
    mayor = tuple(dict.fromkeys(MAY[group] + MAY["en"]))
    if group == "nl" and (entry.get("country") == "BE"):
        general += GEN["fr"][1:]
        mayor += MAY["fr"]
    return general, mayor


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
    local = mail.split("@")[0]
    hashish = 1 if re.fullmatch(r"[0-9a-f]{16,}", local, re.I) else 0
    return (same, hashish, 1 if PEC.search(mail) else 0,
            1 if BAD.search(mail) else 0, 0 if GOOD.search(mail) else 1,
            len(mail), mail)


def mayor_keys(entry: dict) -> list[str]:
    """Прізвище мера латиницею — щоб упізнати особисту скриньку."""
    name = (entry.get("mayor") or "").lower()
    name = re.sub(r"[^\w\s\-]", " ", name, flags=re.U)
    parts = [x for x in re.split(r"[\s\-]+", name) if len(x) > 3]
    return parts[-2:]


def pick_mayor(mails: set[str], entry: dict, site_domain: str) -> str:
    """Серед знайдених адрес шукає скриньку голови міста."""
    keys = mayor_keys(entry)
    same = [m for m in mails
            if not site_domain or m.split("@")[-1].endswith(site_domain)]
    pool = same or list(mails)
    box = [m for m in pool if MAYOR_BOX.search(m.split("@")[0])]
    if box:
        return sorted(box, key=len)[0]
    named = [m for m in pool
             if any(k in m.split("@")[0].lower() for k in keys)]
    return sorted(named, key=len)[0] if named else ""


def harvest(entry: dict) -> tuple[list[str], str]:
    """Повертає (загальні адреси, скринька мера) для однієї громади."""
    site = entry.get("site") or ""
    if not site:
        return [], ""
    found: set[str] = set()
    sd = domain(site)
    session = requests.Session()
    general_pages, mayor_pages = pages_for(entry)
    extra_links: list[str] = []
    mayor_pool: set[str] = set()
    need_general = not entry.get("email")
    need_mayor = not entry.get("mayor_email")
    queue = list(general_pages + mayor_pages)
    for page in queue:
        is_mayor_page = (page in mayor_pages and page not in general_pages) \
            or page in extra_links
        if is_mayor_page and not need_mayor:
            break
        if not is_mayor_page and not need_general and not need_mayor:
            continue
        url = page if page.startswith("http") else urljoin(site.rstrip("/") + "/", page)
        try:
            r = session.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        except Exception:
            continue
        if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
            continue
        if page == "" and need_mayor:
            # з головної збираємо прямі посилання «Bürgermeister / sindaco…»,
            # а якщо їх немає — заходимо в розділ «Ратуша / Amministrazione»
            extra_links = mayor_links(r.text, r.url)
            if not extra_links:
                for hub in hub_links(r.text, r.url):
                    try:
                        hr = session.get(hub, headers=HEADERS, timeout=12)
                    except Exception:
                        continue
                    if hr.status_code == 200:
                        extra_links += mayor_links(hr.text, hr.url, limit=2)
                    if extra_links:
                        break
            queue.extend(extra_links)
        for m in EMAIL_RX.findall(r.text):
            m = m.strip(".").lower()
            if (not JUNK.search(m) and len(m) < 60
                    and len(m.split('@')[0]) <= MAX_LOCAL):
                found.add(m)
                mayor_pool.add(m)
        # загальні сторінки перебираємо до першого влучання,
        # сторінки мера — завжди, бо там інша скринька
        if not is_mayor_page and any(rank(m, sd)[0] == 0 for m in found):
            need_general = False
        if pick_mayor(mayor_pool, entry, sd):
            need_mayor = False
            if not need_general:
                break
    ordered = sorted(found, key=lambda m: rank(m, sd))
    general = [m for m in ordered if rank(m, sd)[0] == 0][:3] or ordered[:1]
    return general, pick_mayor(mayor_pool, entry, sd)


def _is_mayor_box(mail: str) -> bool:
    return bool(MAYOR_BOX.search(mail.split("@")[0]))


ORDER = ("country", "lang", "admin", "site", "email", "email_alt",
         "mayor_email", "phone", "mayor", "party", "note")


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
            # усе в лапках: YAML 1.1 інакше перетворює country: NO на False
            out.append(f"    {key}: {esc(p[key])}")
        out.append(f"    population: {p.get('population', 0)}")
        if p.get("osm") is not None:
            out.append(f"    osm: {p['osm']}")
        if p.get("wikidata"):
            out.append(f"    wikidata: {p['wikidata']}")
        if p.get("coords"):
            out.append(f"    coords: [{p['coords'][0]}, {p['coords'][1]}]")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="0 — усі")
    ap.add_argument("--file", default=str(DEFAULT_YAML),
                    help="YAML із переліком громад "
                         "(danube_partners.yaml | big_cities.yaml | green_cities.yaml)")
    args = ap.parse_args()

    global YAML_PATH
    YAML_PATH = Path(args.file)
    if not YAML_PATH.is_absolute():
        YAML_PATH = ROOT / YAML_PATH if (ROOT / YAML_PATH).exists() else YAML_PATH
    raw = YAML_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    partners = data.get("partners") or []
    todo = [p for p in partners
            if p.get("site") and not (p.get("email") and p.get("mayor_email"))]
    if args.limit:
        todo = todo[:args.limit]
    print(f"Шукаю e-mail для {len(todo)} громад (усього {len(partners)})…",
          flush=True)

    results: dict[int, tuple[list[str], str]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, res in zip(range(len(todo)), pool.map(harvest, todo)):
            results[i] = res
            mails, mayor_mail = res
            if mails or mayor_mail:
                tail = f" · мер: {mayor_mail}" if mayor_mail else ""
                print(f"  ✉️  {todo[i]['name']}: "
                      f"{mails[0] if mails else '—'}{tail}", flush=True)

    # перезаписуємо файл, зберігаючи шапку з коментарями
    added = mayors = 0
    for i, p in enumerate(todo):
        mails, mayor_mail = results.get(i) or ([], "")
        if mails and not p.get("email"):
            p["email"] = mails[0]
            if len(mails) > 1:
                p["email_alt"] = ", ".join(mails[1:])
            added += 1
        if mayor_mail and not p.get("mayor_email"):
            p["mayor_email"] = mayor_mail
            mayors += 1
    head = raw.split("\npartners:")[0]
    YAML_PATH.write_text(head + "\npartners:\n" + dump(partners), encoding="utf-8")

    check = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))["partners"]
    have = sum(1 for p in check if p.get("email"))
    have_m = sum(1 for p in check if p.get("mayor_email"))
    print(f"✅ додано {added} адрес (+{mayors} скриньок мера) · "
          f"тепер з e-mail: {have} з {len(check)}, зі скринькою мера: {have_m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
