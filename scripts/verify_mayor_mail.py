#!/usr/bin/env python3
"""Перевіряє, чи існує пряма поштова скринька голови міста.

Більшість великих міст не публікує адресу мера на сайті, але вона майже
завжди існує за стандартним шаблоном: `buergermeister@…`, `sindaco@…`,
`maire@…`, `burgemeester@…`, `polgarmester@…`. Цей скрипт перебирає такі
шаблони на домені міста й питає поштовий сервер, чи приймає він листи на
таку адресу (команда SMTP `RCPT TO`, лист при цьому **не надсилається**).

Захист від хибних спрацювань: спершу перевіряється вигадана адреса
(`zzq-no-such-box-…@домен`). Якщо сервер приймає і її, домен — «catch-all»,
і перевірити нічого не можна: місто пропускається.

Запуск:
    python3 scripts/verify_mayor_mail.py --file config/big_cities.yaml
    python3 scripts/verify_mayor_mail.py --file config/green_cities.yaml --workers 6

⚠️ Потрібен вихідний порт 25. На GitHub Actions він закритий, тому скрипт
призначений для локального запуску; у разі блокування він просто нічого не
знаходить і нічого не псує.
"""
from __future__ import annotations

import argparse
import random
import re
import smtplib
import socket
import string
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
HELO = "grant-radar.local"
MAIL_FROM = "adanossot@ukr.net"      # зворотна адреса громади
TIMEOUT = 12

# шаблони скриньки голови міста за країнами
CANDIDATES = {
    "de": ("buergermeister", "oberbuergermeister", "buergermeisterin",
           "ob", "bm", "buergermeisteramt", "stadtpraesident"),
    "it": ("sindaco", "segreteria.sindaco", "ufficio.sindaco", "gabinetto.sindaco"),
    "nl": ("burgemeester", "secretariaatburgemeester", "kabinet"),
    "fr": ("maire", "cabinet.maire", "cabinetdumaire", "secretariat.maire"),
    "hu": ("polgarmester", "polgarmesteri.hivatal"),
    "pl": ("prezydent", "burmistrz", "sekretariat.prezydenta"),
    "ro": ("primar", "cabinet.primar"),
    "es": ("alcalde", "alcaldia", "gabinete.alcaldia"),
    "nord": ("borgmester", "borgmastare", "borgmesteren", "pormestari",
             "kaupunginjohtaja", "byradsleder", "ordforer"),
    "en": ("mayor", "mayors.office", "mayoroffice"),
}
GROUP = {"DE": "de", "AT": "de", "CH": "de", "LI": "de", "LU": "fr",
         "IT": "it", "NL": "nl", "BE": "nl", "FR": "fr", "HU": "hu",
         "PL": "pl", "RO": "ro", "ES": "es", "PT": "es",
         "DK": "nord", "SE": "nord", "NO": "nord", "FI": "nord",
         "IS": "nord"}


def domain_of(entry: dict) -> str:
    """Домен міста: беремо з наявного e-mail, інакше з сайту."""
    mail = entry.get("email") or ""
    if "@" in mail:
        return mail.split("@")[-1].lower()
    host = urlsplit(entry.get("site") or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def mx_hosts(domain: str) -> list[str]:
    """MX-записи домену (dnspython, інакше — сам домен)."""
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "MX", lifetime=8)
        hosts = sorted((r.preference, str(r.exchange).rstrip("."))
                       for r in answers)
        if hosts:
            return [h for _, h in hosts][:2]
    except Exception:
        pass
    try:                                  # немає MX — пробуємо сам домен
        socket.gethostbyname(domain)
        return [domain]
    except Exception:
        return []


def transliterate(name: str) -> str:
    table = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
                           "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
                           "å": "a", "ø": "o", "æ": "ae", "č": "c", "š": "s",
                           "ž": "z", "ő": "o", "ű": "u", "ł": "l", "ń": "n",
                           "ç": "c", "à": "a", "è": "e", "ì": "i", "ò": "o"})
    return re.sub(r"[^a-z0-9.\-]", "", name.lower().translate(table))


def candidates_for(entry: dict) -> list[str]:
    group = GROUP.get((entry.get("country") or "").upper(), "en")
    locals_ = list(CANDIDATES[group]) + list(CANDIDATES["en"])
    mayor = transliterate((entry.get("mayor") or "").replace(" ", "."))
    if mayor and "." in mayor:
        first, last = mayor.split(".")[0], mayor.split(".")[-1]
        locals_ += [f"{first}.{last}", last, f"{first[0]}.{last}"]
    return list(dict.fromkeys(x for x in locals_ if x))[:12]


def probe(entry: dict) -> tuple[str, str]:
    """Повертає (адреса мера, примітка) після перевірки SMTP."""
    domain = domain_of(entry)
    if not domain:
        return "", ""
    hosts = mx_hosts(domain)
    if not hosts:
        return "", "домен без MX"
    rnd = "".join(random.choices(string.ascii_lowercase, k=12))
    for host in hosts:
        try:
            srv = smtplib.SMTP(host, 25, local_hostname=HELO, timeout=TIMEOUT)
            srv.ehlo_or_helo_if_needed()
            srv.mail(MAIL_FROM)
            code, _ = srv.rcpt(f"zzq-{rnd}@{domain}")
            if code in (250, 251):
                srv.quit()
                return "", "catch-all (перевірити неможливо)"
            found = ""
            for local in candidates_for(entry):
                try:
                    code, _ = srv.rcpt(f"{local}@{domain}")
                except smtplib.SMTPServerDisconnected:
                    break
                if code in (250, 251):
                    found = f"{local}@{domain}"
                    break
            try:
                srv.quit()
            except Exception:
                pass
            if found:
                return found, "перевірено SMTP"
            return "", "скриньки за шаблоном немає"
        except Exception:
            continue
    return "", "сервер не відповів"


ORDER = ("country", "lang", "admin", "site", "email", "email_alt",
         "mayor_email", "phone", "mayor", "party", "note")


def esc(value) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def dump(partners: list[dict]) -> str:
    out = []
    for p in partners:
        out.append(f"  - name: {esc(p['name'])}")
        for key in ORDER:
            if p.get(key):
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
    ap.add_argument("--file", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = ROOT / path
    raw = path.read_text(encoding="utf-8")
    partners = yaml.safe_load(raw)["partners"]
    todo = [p for p in partners if not p.get("mayor_email")
            and (p.get("email") or p.get("site"))]
    if args.limit:
        todo = todo[:args.limit]
    print(f"SMTP-перевірка скриньок мера: {len(todo)} міст "
          f"(усього {len(partners)})…", flush=True)

    found = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for entry, (mail, why) in zip(todo, pool.map(probe, todo)):
            if mail:
                entry["mayor_email"] = mail
                found += 1
                print(f"  👤 {entry['name']}: {mail}", flush=True)
    head = raw.split("\npartners:")[0]
    path.write_text(head + "\npartners:\n" + dump(partners), encoding="utf-8")
    have = sum(1 for p in partners if p.get("mayor_email"))
    print(f"✅ знайдено {found} нових · зі скринькою мера: {have} "
          f"з {len(partners)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
