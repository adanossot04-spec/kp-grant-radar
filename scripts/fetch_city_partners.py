#!/usr/bin/env python3
"""Збирає два додаткові канали партнерів і пише їх у `config/`.

1. **Великі громади** → `config/big_cities.yaml`
   Усі міста Австрії, Італії та Словенії з населенням понад 100 000.
   Велике місто — це власний департамент екології, бюджет на міжнародну
   співпрацю і, як правило, парк комунальної техніки, що оновлюється
   (а отже, є що передати).

2. **Зелені** → `config/green_cities.yaml`
   Міста Центральної та Північної Європи з населенням понад 30 000, де
   міську владу очолює представник партії Зелених. Критерій машинно
   перевірний: у Wikidata в міста є чинний голова (P6), який є членом
   (P102) партії — члена Європейської партії зелених (P463 → Q950179)
   або партії зі списку `EXTRA_GREEN`.

   ⚠️ Склад правлячої коаліції у відкритих структурованих даних не
   публікується: Wikidata знає лише посадовця, а не коаліційну угоду.
   Тому міста, де Зелені входять у коаліцію, але мер — не від Зелених,
   дописуються вручну в секцію `manual:` відповідного YAML (там уже є
   стартовий перелік, кожен запис варто перевірити перед листом).

Джерело одне — Wikidata (безкоштовно, без ключів). E-mail, якого немає
в Wikidata, добирається потім: `python3 scripts/harvest_emails.py --file
config/big_cities.yaml`.

Запуск:  python3 scripts/fetch_city_partners.py [--only big|green]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = "kp-grant-radar/1.0 (https://github.com/; adanossot@ukr.net)"
WDQS = "https://query.wikidata.org/sparql"

# ─────────────────────── канал 1: великі громади ───────────────────────
BIG = {
    "file": "big_cities.yaml",
    "min_pop": 100000,
    "countries": {"AT": ("Q40", "de"), "IT": ("Q38", "it"), "SI": ("Q215", "sl")},
    "lang": {"AT": "de", "IT": "it", "SI": "en"},   # якою мовою писати листа
}

# ─────────────────────── канал 2: «зелені» міста ───────────────────────
# Центральна та Північна Європа
GREEN_COUNTRIES = {
    "DE": ("Q183", "de", "de"), "AT": ("Q40", "de", "de"),
    "CH": ("Q39", "de", "de"), "LU": ("Q32", "de", "de"),
    "NL": ("Q55", "nl", "en"), "BE": ("Q31", "nl", "en"),
    "CZ": ("Q213", "cs", "en"), "PL": ("Q36", "pl", "pl"),
    "SK": ("Q214", "sk", "en"), "HU": ("Q28", "hu", "hu"),
    "SI": ("Q215", "sl", "en"), "DK": ("Q35", "da", "en"),
    "SE": ("Q34", "sv", "en"), "NO": ("Q20", "no", "en"),
    "FI": ("Q33", "fi", "en"), "IS": ("Q189", "is", "en"),
    "EE": ("Q191", "et", "en"), "LV": ("Q211", "lv", "en"),
    "LT": ("Q37", "lt", "en"),
}
# Партії, яких немає в переліку членів Європейської партії зелених,
# але які є «зеленими» у місцевих коаліціях Півночі Європи.
EXTRA_GREEN = ["Q215912",    # Socialistisk Folkeparti / Green Left (DK)
               "Q18042964",  # Alternativet (DK)
               "Q1130754",   # Vinstrihreyfingin – grænt framboð (IS)
               "Q28966907",  # Progresīvie (LV)
               ]
GREEN = {"file": "green_cities.yaml", "min_pop": 30000}

# Міста, де Зелені — партнер правлячої коаліції (мер при цьому може бути
# від іншої партії, тому Wikidata їх не бачить). Перелік курований: перед
# надсиланням листа варто перевірити, чи коаліція ще чинна — у YAML вони
# позначені приміткою «коаліція (перевірити)».
MANUAL_GREEN = [
    ("Hamburg", "DE"), ("Bremen", "DE"), ("Köln", "DE"), ("Düsseldorf", "DE"),
    ("Frankfurt am Main", "DE"), ("Stuttgart", "DE"), ("Freiburg im Breisgau", "DE"),
    ("Bonn", "DE"), ("Karlsruhe", "DE"), ("Heidelberg", "DE"), ("Konstanz", "DE"),
    ("Mainz", "DE"), ("Kiel", "DE"), ("Aachen", "DE"), ("Augsburg", "DE"),
    ("Kassel", "DE"), ("Potsdam", "DE"), ("Oldenburg", "DE"), ("Osnabrück", "DE"),
    ("Göttingen", "DE"), ("Marburg", "DE"), ("Jena", "DE"), ("Leipzig", "DE"),
    ("Graz", "AT"), ("Innsbruck", "AT"), ("Salzburg", "AT"),
    ("Zürich", "CH"), ("Bern", "CH"), ("Basel", "CH"), ("Winterthur", "CH"),
    ("Lausanne", "CH"), ("Genève", "CH"), ("Luzern", "CH"),
    ("Amsterdam", "NL"), ("Utrecht", "NL"), ("Nijmegen", "NL"),
    ("Groningen", "NL"), ("Arnhem", "NL"), ("Leiden", "NL"), ("Haarlem", "NL"),
    ("Gent", "BE"), ("Leuven", "BE"),
    ("Stockholm", "SE"), ("Göteborg", "SE"), ("Malmö", "SE"), ("Uppsala", "SE"),
    ("Lund", "SE"),
    ("Helsinki", "FI"), ("Tampere", "FI"), ("Turku", "FI"), ("Espoo", "FI"),
    ("Oulu", "FI"), ("Jyväskylä", "FI"),
    ("Oslo", "NO"), ("Bergen", "NO"), ("Trondheim", "NO"),
    ("København", "DK"), ("Aarhus", "DK"), ("Odense", "DK"),
    ("Luxembourg", "LU"), ("Praha", "CZ"), ("Brno", "CZ"), ("Ljubljana", "SI"),
]


def wd(query: str, timeout: int = 300, tries: int = 4) -> list[dict]:
    """Запит до Wikidata Query Service із повторами: сервіс часто дає 504."""
    url = WDQS + "?" + urllib.parse.urlencode({"query": query})
    req = urllib.request.Request(url, headers={
        "Accept": "application/sparql-results+json", "User-Agent": UA})
    last: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())["results"]["bindings"]
        except Exception as exc:
            last = exc
            print(f"    ⚠️ спроба {attempt}/{tries}: {exc}", flush=True)
            time.sleep(10 * attempt)
    raise RuntimeError(f"Wikidata не відповідає: {last}")


def val(row: dict, key: str, default: str = "") -> str:
    return row.get(key, {}).get("value", default)


def clean_mail(value: str) -> str:
    value = (value or "").replace("mailto:", "").strip()
    return value if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", value, re.I) else ""


def clean_site(value: str) -> str:
    value = (value or "").strip()
    return value if value.startswith("http") else ""


def merge(rows: list[dict], key: str = "city") -> dict[str, dict]:
    out: dict[str, dict] = {}
    for b in rows:
        qid = val(b, key).rsplit("/", 1)[-1]
        rec = out.setdefault(qid, {"qid": qid})
        for field in b:
            if field == key:
                continue
            value = val(b, field)
            if value and not rec.get(field):
                rec[field] = value
    return out


def fetch_big() -> list[dict]:
    partners: list[dict] = []
    for cc, (country_qid, label_lang) in BIG["countries"].items():
        query = f"""SELECT ?city ?cityLabel ?pop ?site ?mail ?phone ?adminLabel ?lat ?lon WHERE {{
  ?city wdt:P17 wd:{country_qid} ; wdt:P1082 ?pop ; wdt:P31/wdt:P279* wd:Q515 .
  FILTER(?pop >= {BIG['min_pop']})
  OPTIONAL {{ ?city wdt:P856 ?site }} OPTIONAL {{ ?city wdt:P968 ?mail }}
  OPTIONAL {{ ?city wdt:P1329 ?phone }} OPTIONAL {{ ?city wdt:P131 ?admin }}
  OPTIONAL {{ ?city p:P625/psv:P625 ?co .
             ?co wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{label_lang},en" }} }}"""
        print(f"  Wikidata {cc}: міста понад {BIG['min_pop']:,} мешканців…"
              .replace(",", " "), flush=True)
        found = merge(wd(query))
        for rec in found.values():
            rec["name"] = rec.get("cityLabel", "")
            if not rec.get("name") or rec["name"].startswith("Q") or not rec.get("site"):
                continue  # без офіційного сайту писати нікуди
            partners.append({
                "name": rec["name"], "country": cc, "lang": BIG["lang"][cc],
                "admin": rec.get("adminLabel", ""),
                "population": int(float(rec.get("pop", 0))),
                "site": clean_site(rec.get("site", "")),
                "email": clean_mail(rec.get("mail", "")),
                "phone": rec.get("phone", "").strip(),
                "wikidata": rec["qid"],
                "lat": round(float(rec.get("lat", 0) or 0), 5),
                "lon": round(float(rec.get("lon", 0) or 0), 5),
                "note": "місто понад 100 тис. мешканців",
            })
        print(f"    {cc}: {len([p for p in partners if p['country'] == cc])}")
    return partners


def fetch_green() -> list[dict]:
    countries = " ".join("wd:" + q for q, _, _ in GREEN_COUNTRIES.values())
    extra = " ".join("wd:" + q for q in EXTRA_GREEN)
    query = f"""SELECT ?city ?cityLabel ?cc ?pop ?site ?mail ?phone ?mayorLabel ?partyLabel
                       ?adminLabel ?lat ?lon WHERE {{
  VALUES ?country {{ {countries} }}
  ?city wdt:P17 ?country ; wdt:P1082 ?pop ; wdt:P31/wdt:P279* wd:Q515 ; p:P6 ?st .
  FILTER(?pop >= {GREEN['min_pop']})
  ?st ps:P6 ?mayor . FILTER NOT EXISTS {{ ?st pq:P582 ?end }}
  ?mayor wdt:P102 ?party .
  {{ ?party wdt:P463 wd:Q950179 }} UNION {{ VALUES ?party {{ {extra} }} }}
  ?country wdt:P297 ?cc .
  OPTIONAL {{ ?city wdt:P856 ?site }} OPTIONAL {{ ?city wdt:P968 ?mail }}
  OPTIONAL {{ ?city wdt:P1329 ?phone }} OPTIONAL {{ ?city wdt:P131 ?admin }}
  OPTIONAL {{ ?city p:P625/psv:P625 ?co .
             ?co wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,nl,en" }} }}"""
    print("  Wikidata: міста, де мера обрано від партії Зелених…", flush=True)
    found = merge(wd(query))
    partners = []
    for rec in found.values():
        cc = rec.get("cc", "")
        if cc not in GREEN_COUNTRIES or not rec.get("site"):
            continue
        name = rec.get("cityLabel") or ""
        if not name or name.startswith("Q"):
            continue
        partners.append({
            "name": name, "country": cc,
            "lang": GREEN_COUNTRIES[cc][2],
            "admin": rec.get("adminLabel", ""),
            "population": int(float(rec.get("pop", 0))),
            "site": clean_site(rec.get("site", "")),
            "email": clean_mail(rec.get("mail", "")),
            "phone": rec.get("phone", "").strip(),
            "wikidata": rec["qid"],
            "lat": round(float(rec.get("lat", 0) or 0), 5),
            "lon": round(float(rec.get("lon", 0) or 0), 5),
            "mayor": rec.get("mayorLabel", ""),
            "party": rec.get("partyLabel", ""),
            "note": "мер від Зелених (Wikidata P6 → P102)",
        })
    return partners


def search_qid(name: str, lang: str) -> list[str]:
    """Кандидати Q-ідентифікаторів за назвою (безкоштовний wbsearchentities)."""
    url = ("https://www.wikidata.org/w/api.php?action=wbsearchentities&"
           + urllib.parse.urlencode({"search": name, "language": lang,
                                     "uselang": lang, "type": "item",
                                     "format": "json", "limit": 6}))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except Exception as exc:
        print(f"    ⚠️ пошук «{name}»: {exc}")
        return []
    return [item["id"] for item in data.get("search", [])]


def fetch_manual_green() -> list[dict]:
    """Контакти для курованого переліку «коаліційних» міст.

    Пошук назви через SPARQL по мітках надто важкий (WDQS віддає 504),
    тому спершу беремо кандидатів через API пошуку, а потім одним
    запитом перевіряємо країну, населення і тягнемо контакти.
    """
    candidates: dict[str, tuple[str, str]] = {}
    print(f"  Пошук Q-ідентифікаторів для {len(MANUAL_GREEN)} міст…", flush=True)
    for name, cc in MANUAL_GREEN:
        if cc not in GREEN_COUNTRIES:
            continue
        for qid in search_qid(name, GREEN_COUNTRIES[cc][1]):
            candidates[qid] = (name, cc)
        time.sleep(0.2)
    if not candidates:
        return []
    values = " ".join("wd:" + q for q in candidates)
    query = f"""SELECT ?city ?cityLabel ?cc ?pop ?site ?mail ?phone ?adminLabel ?lat ?lon WHERE {{
  VALUES ?city {{ {values} }}
  ?city wdt:P17/wdt:P297 ?cc ; wdt:P1082 ?pop ; wdt:P856 ?site ;
        wdt:P31/wdt:P279* wd:Q515 .
  OPTIONAL {{ ?city wdt:P968 ?mail }} OPTIONAL {{ ?city wdt:P1329 ?phone }}
  OPTIONAL {{ ?city wdt:P131 ?admin }}
  OPTIONAL {{ ?city p:P625/psv:P625 ?co .
             ?co wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,nl,en" }} }}"""
    print(f"  Wikidata: перевірка {len(candidates)} кандидатів…", flush=True)
    found = merge(wd(query))
    best: dict[tuple[str, str], dict] = {}
    for qid, rec in found.items():
        want = candidates.get(qid)
        if not want or rec.get("cc") != want[1]:
            continue
        key = want
        if float(rec.get("pop", 0) or 0) > float(best.get(key, {}).get("pop", 0) or 0):
            rec["wanted_name"] = want[0]
            best[key] = rec
    out = []
    for (name, cc), rec in best.items():
        out.append({
            "name": rec.get("cityLabel") or name,
            "country": cc, "lang": GREEN_COUNTRIES[cc][2],
            "admin": rec.get("adminLabel", ""),
            "population": int(float(rec.get("pop", 0))),
            "site": clean_site(rec.get("site", "")),
            "email": clean_mail(rec.get("mail", "")),
            "phone": rec.get("phone", "").strip(),
            "wikidata": rec["qid"],
            "lat": round(float(rec.get("lat", 0) or 0), 5),
            "lon": round(float(rec.get("lon", 0) or 0), 5),
            "note": "Зелені в міській коаліції (перевірити)",
        })
    print(f"    знайдено {len(out)} з {len(MANUAL_GREEN)}")
    return out


def names_for(qids: list[str]) -> dict[str, dict]:
    """Назви й контакти для вручну доданих міст (секція manual:)."""
    if not qids:
        return {}
    values = " ".join("wd:" + q for q in qids)
    query = f"""SELECT ?city ?name ?cc ?pop ?site ?mail ?phone ?adminLabel ?lat ?lon WHERE {{
  VALUES ?city {{ {values} }}
  OPTIONAL {{ ?city wdt:P17/wdt:P297 ?cc }} OPTIONAL {{ ?city wdt:P1082 ?pop }}
  OPTIONAL {{ ?city wdt:P856 ?site }} OPTIONAL {{ ?city wdt:P968 ?mail }}
  OPTIONAL {{ ?city wdt:P1329 ?phone }} OPTIONAL {{ ?city wdt:P131 ?admin }}
  OPTIONAL {{ ?city p:P625/psv:P625 ?co .
             ?co wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon }}
  OPTIONAL {{ ?city rdfs:label ?name FILTER(LANG(?name) IN ("de","nl","en","sv","fi","da","no","cs","pl","hu","sl","et","lv","lt","is")) }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,nl,en" }} }}"""
    return merge(wd(query))


def esc(value) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def dump(partners: list[dict], header: str, path: Path) -> None:
    lines = [header.rstrip(), "", "partners:"]
    for p in sorted(partners, key=lambda x: (x.get("country") or "",
                                             -(x.get("population") or 0),
                                             x.get("name") or "")):
        lines.append(f"  - name: {esc(p['name'])}")
        # лапки обов'язкові: YAML 1.1 читає NO (Норвегія) як False
        lines.append(f"    country: {esc(p['country'])}")
        lines.append(f"    lang: {esc(p['lang'])}")
        for key in ("admin", "site", "email", "phone", "mayor", "party", "note"):
            if p.get(key):
                lines.append(f"    {key}: {esc(p[key])}")
        lines.append(f"    population: {p.get('population', 0)}")
        if p.get("wikidata"):
            lines.append(f"    wikidata: {p['wikidata']}")
        lines.append(f"    coords: [{p.get('lat', 0)}, {p.get('lon', 0)}]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with_mail = sum(1 for p in partners if p.get("email"))
    print(f"✅ {path.relative_to(ROOT)}: {len(partners)} міст, "
          f"з них з e-mail — {with_mail}")


HEADER_BIG = """# Великі громади Австрії, Італії та Словенії (понад 100 000 мешканців).
#
# Згенеровано автоматично: scripts/fetch_city_partners.py --only big
# Джерело: Wikidata (P1082 населення, P856 сайт, P968 e-mail, P1329 телефон).
#
# Навіщо канал: у місті понад 100 тис. мешканців є окремий департамент
# екології або комунального господарства, бюджет на міжнародну співпрацю
# і регулярне оновлення парку техніки — тобто є і з ким говорити, і що
# передати. Листи таким адресатам підписує агент командою `cities`.
#
# Файл можна правити руками: уточнити e-mail профільного відділу
# (Umweltamt / assessorato all'ambiente), додати або прибрати місто."""

HEADER_GREEN = """# «Зелені» міста Центральної та Північної Європи (понад 30 000 мешканців).
#
# Згенеровано автоматично: scripts/fetch_city_partners.py --only green
# Джерело: Wikidata — чинний голова міста (P6), який є членом (P102)
# партії, що входить до Європейської партії зелених (P463 → Q950179).
#
# ⚠️ ВАЖЛИВО. Склад правлячої коаліції у відкритих структурованих даних
# не публікується: Wikidata знає посадовця, а не коаліційну угоду. Тому
# автоматично сюди потрапляють лише міста, де мер — від Зелених. Міста,
# де Зелені є молодшим партнером коаліції (Гамбург, Бремен, Цюрих, Берн,
# Базель, Амстердам, Утрехт, Гент, Грац, Інсбрук, Стокгольм, Гельсінкі,
# Осло та інші), додавайте сюди руками — і перед надсиланням листа
# перевіряйте, чи коаліція ще чинна.
#
# Навіщо канал: там, де Зелені у владі, екологічний проєкт у сусідній
# країні — це профільний пріоритет, а не «ще одне прохання про допомогу»."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["big", "green"], default=None)
    args = ap.parse_args()

    if args.only in (None, "big"):
        dump(fetch_big(), HEADER_BIG, ROOT / "config" / BIG["file"])
    if args.only in (None, "green"):
        rows = fetch_green()
        have = {(p["name"], p["country"]) for p in rows}
        for p in fetch_manual_green():
            if (p["name"], p["country"]) not in have:
                rows.append(p)
        dump(rows, HEADER_GREEN, ROOT / "config" / GREEN["file"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
