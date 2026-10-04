#!/usr/bin/env python3
"""Збирає перелік придунайських громад Австрії, Угорщини та Румунії
з відкритих джерел і записує їх у `config/danube_partners.yaml`.

Логіка:
  1. OpenStreetMap / Overpass API — беремо геометрію річки (waterway=river
     з назвою «Donau» / «Duna» / «Dunăre») у межах країни і всі
     адміністративні одиниці 8-го рівня (громада / település / comună),
     межі яких проходять ближче ніж 800 м від русла. Так у перелік
     потрапляють саме ті, хто реально стоїть на Дунаї.
  2. Wikidata (SPARQL) — за `wikidata`-тегом кожної громади дістаємо
     офіційний сайт (P856), е-mail (P968), телефон (P1329), населення
     (P1082) і країну (P17). Країна потрібна, бо Дунай — прикордонна
     річка: навколо румунського берега трапляються сербські, болгарські
     та молдовські громади, їх відсіюємо.

Обидва джерела безкоштовні й не потребують ключів. Відповіді Overpass
кешуються в `data/cache/`, бо один запит виконується 5–10 хвилин.

Запуск:  PYTHONPATH=src python3 scripts/fetch_danube_partners.py [--refresh]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
OUT = ROOT / "config" / "danube_partners.yaml"

UA = "kp-grant-radar/1.0 (https://github.com/; adanossot@ukr.net)"
OVERPASS = "https://overpass-api.de/api/interpreter"
WDQS = "https://query.wikidata.org/sparql"

COUNTRIES = {
    "AT": {"river": "Donau", "lang": "de", "name_uk": "Австрія", "wd": "Q40",
           "classes": ["Q667509", "Q1802801", "Q562061", "Q13539802", "Q261023"],
           "label": "de",
           "bboxes": ["48.20,13.40,48.75,14.45", "48.10,14.20,48.60,15.25",
                      "47.95,15.00,48.50,16.15", "47.90,16.00,48.60,17.25"]},
    "HU": {"river": "Duna", "lang": "hu", "name_uk": "Угорщина", "wd": "Q28",
           "classes": ["Q2590631", "Q13218690", "Q681277", "Q851110"],
           "label": "hu",
           "bboxes": ["47.55,16.90,48.10,17.95", "47.45,17.70,48.05,18.95",
                      "47.25,18.60,48.05,19.35", "46.85,18.55,47.55,19.40",
                      "46.20,18.45,47.00,19.25", "45.70,18.30,46.40,19.05"]},
    "RO": {"river": "Dun[aă]re", "lang": "ro", "name_uk": "Румунія", "wd": "Q218",
           "classes": ["Q659103", "Q16858213", "Q640364", "Q34843301"],
           "label": "ro",
           "bboxes": ["44.30,21.00,45.30,22.60", "43.60,22.30,44.90,23.90",
                      "43.50,23.50,44.50,25.20", "43.50,25.00,44.60,26.60",
                      "43.90,26.40,45.10,28.10", "44.40,27.80,45.60,29.80"]},
}

# Статутні міста на Дунаї, чия межа в OSM має не 8-й рівень (Відень — 4-й,
# Лінц і Кремс — 6-й), тому в запит вище вони не потрапляють. Додаємо вручну.
EXTRA = {
    "AT": [("Wien", "Q1741"), ("Linz", "Q41329"),
           ("Krems an der Donau", "Q131266")],
    "HU": [],
    "RO": [],
}

OVERPASS_QL = """[out:json][timeout:400][bbox:{bbox}];
way["waterway"="river"]["name"~"{river}"]->.riv;
rel(around.riv:800)["boundary"="administrative"]["admin_level"="8"];
out tags center;
"""

MIRRORS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.osm.jp/api/interpreter"]


def http(url: str, data: bytes | None = None, accept: str = "application/json",
         timeout: int = 700) -> str:
    req = urllib.request.Request(url, data=data,
                                 headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def overpass(cc: str, refresh: bool = False) -> list[dict]:
    """Адмінодиниці вздовж русла — короткими ділянками, щоб не ловити таймаут.

    Один запит на всю країну Overpass не витягує (504), тому коридор річки
    поділено на 4–6 прямокутників; результати зливаємо за osm-id.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"overpass_{cc}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8")).get("elements", [])
    meta = COUNTRIES[cc]
    merged: dict[int, dict] = {}
    for n, bbox in enumerate(meta["bboxes"], 1):
        ql = OVERPASS_QL.format(river=meta["river"], bbox=bbox)
        body = urllib.parse.urlencode({"data": ql}).encode()
        for mirror in MIRRORS:
            print(f"  Overpass {cc} · ділянка {n}/{len(meta['bboxes'])} "
                  f"({mirror.split('/')[2]})…", flush=True)
            try:
                els = json.loads(http(mirror, data=body, timeout=500)).get("elements", [])
            except Exception as exc:  # дзеркало перевантажене — беремо наступне
                print(f"    ⚠️ {exc}")
                time.sleep(5)
                continue
            for e in els:
                merged[e["id"]] = e
            print(f"    +{len(els)}")
            break
        time.sleep(3)
    path.write_text(json.dumps({"elements": list(merged.values())},
                               ensure_ascii=False), encoding="utf-8")
    return list(merged.values())


def wd_registry(cc: str, refresh: bool = False) -> list[dict]:
    """Усі самоврядування країни з Wikidata: сайт, e-mail, телефон, населення.

    Wikidata тримає офіційні контакти майже для всіх громад (P856 — сайт,
    P968 — е-mail), але OSM-межі далеко не завжди мають тег `wikidata`.
    Тому вантажимо повний реєстр країни один раз і прив'язуємо до меж за
    назвою та координатами.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"wikidata_{cc}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    meta = COUNTRIES[cc]
    classes = " ".join("wd:" + q for q in meta["classes"])
    query = f"""SELECT ?item ?name ?site ?mail ?phone ?pop ?adminLabel ?lat ?lon WHERE {{
  VALUES ?type {{ {classes} }}
  ?item wdt:P17 wd:{meta['wd']} ; wdt:P31 ?type ; rdfs:label ?name .
  FILTER(LANG(?name) = "{meta['label']}")
  OPTIONAL {{ ?item wdt:P856 ?site }}
  OPTIONAL {{ ?item wdt:P968 ?mail }}
  OPTIONAL {{ ?item wdt:P1329 ?phone }}
  OPTIONAL {{ ?item wdt:P1082 ?pop }}
  OPTIONAL {{ ?item wdt:P131 ?admin }}
  OPTIONAL {{ ?item p:P625/psv:P625 ?co .
             ?co wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{meta['label']},en" }} }}"""
    print(f"  Wikidata {cc}: реєстр самоврядувань…", flush=True)
    url = WDQS + "?" + urllib.parse.urlencode({"query": query})
    data = json.loads(http(url, accept="application/sparql-results+json",
                           timeout=300))
    merged: dict[str, dict] = {}
    for row in data["results"]["bindings"]:
        qid = row["item"]["value"].rsplit("/", 1)[-1]
        rec = merged.setdefault(qid, {"qid": qid})
        for key in ("name", "site", "mail", "phone", "pop", "adminLabel",
                    "lat", "lon"):
            val = row.get(key, {}).get("value")
            if val and not rec.get(key):
                rec[key] = val
    out = list(merged.values())
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"    {len(out)} записів")
    return out


def wd_items(qids: list[str]) -> dict[str, dict]:
    """Точкові картки Wikidata за списком Q-ідентифікаторів."""
    if not qids:
        return {}
    values = " ".join("wd:" + q for q in qids)
    query = f"""SELECT ?item ?name ?site ?mail ?phone ?pop ?adminLabel ?lat ?lon WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item rdfs:label ?name FILTER(LANG(?name) = "de") }}
  OPTIONAL {{ ?item wdt:P856 ?site }} OPTIONAL {{ ?item wdt:P968 ?mail }}
  OPTIONAL {{ ?item wdt:P1329 ?phone }} OPTIONAL {{ ?item wdt:P1082 ?pop }}
  OPTIONAL {{ ?item wdt:P131 ?admin }}
  OPTIONAL {{ ?item p:P625/psv:P625 ?co .
             ?co wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,hu,ro,en" }} }}"""
    url = WDQS + "?" + urllib.parse.urlencode({"query": query})
    data = json.loads(http(url, accept="application/sparql-results+json",
                           timeout=120))
    out: dict[str, dict] = {}
    for row in data["results"]["bindings"]:
        qid = row["item"]["value"].rsplit("/", 1)[-1]
        rec = out.setdefault(qid, {"qid": qid})
        for key in ("name", "site", "mail", "phone", "pop", "adminLabel",
                    "lat", "lon"):
            val = row.get(key, {}).get("value")
            if val and not rec.get(key):
                rec[key] = val
    return out


def norm(text: str) -> str:
    """Назва без діакритики й розділових знаків — для зіставлення."""
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ß", "ss").replace("ł", "l").replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "", text)


def pick(cands: list[dict], lat: float, lon: float) -> dict | None:
    """З кількох однойменних громад беремо найближчу до межі з OSM (до 30 км)."""
    best, best_d = None, 1e9
    for c in cands:
        try:
            clat, clon = float(c.get("lat")), float(c.get("lon"))
        except (TypeError, ValueError):
            continue
        d = ((clat - lat) * 111.0) ** 2 + ((clon - lon) * 74.0) ** 2
        if d < best_d:
            best, best_d = c, d
    if best is None:
        return cands[0] if len(cands) == 1 else None
    return best if best_d <= 30.0 ** 2 else None


def clean_mail(value: str | None) -> str:
    if not value:
        return ""
    value = value.replace("mailto:", "").strip()
    return value if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", value, re.I) else ""


def clean_site(value: str | None) -> str:
    if not value:
        return ""
    return value.strip() if value.startswith("http") else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="не брати Overpass із кешу")
    args = ap.parse_args()

    partners: list[dict] = []
    for cc, meta in COUNTRIES.items():
        els = overpass(cc, refresh=args.refresh)
        print(f"  {cc}: {len(els)} адмінодиниць уздовж річки")
        reg = wd_registry(cc, refresh=args.refresh)
        by_qid = {r["qid"]: r for r in reg}
        by_name: dict[str, list[dict]] = {}
        for r in reg:
            by_name.setdefault(norm(r.get("name", "")), []).append(r)

        seen: set[str] = set()
        matched = 0
        for e in els:
            t = e.get("tags", {})
            name = t.get("name", "")
            if not name:
                continue
            center = e.get("center", {})
            lat, lon = center.get("lat", 0.0), center.get("lon", 0.0)
            info = by_qid.get(t.get("wikidata", ""))
            if info is None:
                cands = by_name.get(norm(name), [])
                info = pick(cands, lat, lon) if cands else None
            # Дунай — прикордонна річка: якщо громади немає в реєстрі країни,
            # це майже напевно сусідня держава (RS, BG, MD, SK, HR) — пропускаємо
            if info is None:
                continue
            key = info.get("qid") or norm(name)
            if key in seen:
                continue
            seen.add(key)
            matched += 1
            try:
                pop = int(float(info.get("pop") or t.get("population") or 0))
            except ValueError:
                pop = 0
            partners.append({
                "name": name,
                "name_local": info.get("name") or name,
                "country": cc,
                "lang": meta["lang"],
                "admin": info.get("adminLabel", ""),
                "population": pop,
                "site": clean_site(info.get("site")) or clean_site(t.get("website")),
                "email": clean_mail(info.get("mail")) or clean_mail(
                    t.get("email") or t.get("contact:email")),
                "phone": (info.get("phone") or t.get("phone") or "").strip(),
                "osm": e.get("id"),
                "wikidata": info.get("qid", ""),
                "lat": round(lat, 5),
                "lon": round(lon, 5),
            })
        extra = wd_items([q for _, q in EXTRA.get(cc, [])])
        for ename, qid in EXTRA.get(cc, []):
            info = extra.get(qid)
            if not info or qid in seen:
                continue
            seen.add(qid)
            try:
                pop = int(float(info.get("pop") or 0))
            except ValueError:
                pop = 0
            partners.append({
                "name": ename, "name_local": info.get("name") or ename,
                "country": cc, "lang": meta["lang"],
                "admin": info.get("adminLabel", ""), "population": pop,
                "site": clean_site(info.get("site")),
                "email": clean_mail(info.get("mail")),
                "phone": (info.get("phone") or "").strip(),
                "osm": 0, "wikidata": qid,
                "lat": round(float(info.get("lat") or 0), 5),
                "lon": round(float(info.get("lon") or 0), 5),
            })
            matched += 1
        print(f"    зіставлено з реєстром країни: {matched}")

    partners.sort(key=lambda p: (p["country"], -p["population"], p["name"]))

    def esc(value) -> str:
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'

    lines = [
        "# Придунайські громади Австрії, Угорщини та Румунії — база для листування.",
        "#",
        "# Згенеровано автоматично: scripts/fetch_danube_partners.py",
        "# Джерела: OpenStreetMap (Overpass API) + Wikidata. Обидва безкоштовні.",
        "#",
        "# Логіка добору: адміністративна одиниця 8-го рівня, межа якої проходить",
        "# не далі ніж 800 м від русла Дунаю. Контакти — офіційний сайт (P856) та",
        "# е-mail (P968) з Wikidata; порожній email добирається командою",
        "# `contacts` (пошук на сайті громади).",
        "#",
        "# Файл можна правити руками: додати громаду, вписати точний e-mail",
        "# профільного відділу (Umweltamt / környezetvédelmi osztály / serviciul",
        "# de mediu) — агент бере дані звідси.",
        "",
        "partners:",
    ]
    for p in partners:
        lines.append(f"  - name: {esc(p['name'])}")
        for key in ("country", "lang"):
            lines.append(f"    {key}: {p[key]}")
        for key in ("admin", "site", "email", "phone"):
            if p[key]:
                lines.append(f"    {key}: {esc(p[key])}")
        lines.append(f"    population: {p['population']}")
        lines.append(f"    osm: {p['osm']}")
        if p["wikidata"]:
            lines.append(f"    wikidata: {p['wikidata']}")
        lines.append(f"    coords: [{p['lat']}, {p['lon']}]")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    by_cc: dict[str, int] = {}
    mails = 0
    for p in partners:
        by_cc[p["country"]] = by_cc.get(p["country"], 0) + 1
        mails += bool(p["email"])
    print(f"✅ {OUT.relative_to(ROOT)}: {len(partners)} громад "
          f"({', '.join(f'{k} {v}' for k, v in sorted(by_cc.items()))}), "
          f"з них з e-mail — {mails}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
