"""Два міські канали партнерства: «великі громади» і «зелені».

**Великі громади** — усі міста Австрії, Італії та Словенії понад 100 000
мешканців. Логіка проста: у великому місті є окремий департамент екології
чи комунального господарства, бюджет на міжнародну співпрацю і парк
техніки, який регулярно оновлюють. Списана, але цілком робоча машина для
них — рядок у відомості на утилізацію, для нас — ціла система вивезення.

**Зелені** — міста Центральної та Північної Європи понад 30 000 мешканців,
де Зелені у міській владі. Для такої ради наш проєкт — не чергове
прохання про допомогу, а профільний екологічний проєкт у верхів'ї річки,
що впадає в Дунай і Чорне море.

Переліки збирає `scripts/fetch_city_partners.py` (Wikidata, безкоштовно),
e-mail добирає `scripts/harvest_emails.py --file config/<файл>.yaml`.
Цей модуль перетворює їх на картки донорів, рахує пріоритет за тією самою
методологією (Д + М + З − В) і готує листи та список розсилки.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .db import Database

CHANNELS: dict[str, dict[str, Any]] = {
    "big": {
        "file": "big_cities.yaml",
        "uid": "bigcity:",
        "circle": 7,
        "what": "велике місто (понад 100 тис. мешканців) — власна служба "
                "поводження з відходами",
        "letters_dir": "letters_big",
        "csv": "big_cities_mailing.csv",
        "page": "cities_big.html",
        "title": "🏙 Великі громади: Австрія · Італія · Словенія",
        "sub": "міста понад 100 000 мешканців із власною комунальною службою",
        "hint": "Критерій добору: місто Австрії, Італії або Словенії з "
                "населенням <b>понад 100 000 мешканців</b> (Wikidata P1082) і "
                "чинним офіційним сайтом. У такому місті є профільний "
                "департамент, бюджет на міжнародну співпрацю і парк техніки, "
                "який оновлюється — тобто є і з ким говорити, і що передати. "
                "Листи італійською, німецькою та англійською лежать у теці "
                "<code>data/letters_big/</code>; перелік — у "
                "<code>config/big_cities.yaml</code>.",
        "footer": "Оновлення: <code>python scripts/fetch_city_partners.py "
                  "--only big</code> → <code>python -m grant_radar cities</code> "
                  "· розсилка: <code>data/big_cities_mailing.csv</code>",
    },
    "green": {
        "file": "green_cities.yaml",
        "uid": "green:",
        "circle": 8,
        "what": "місто, де Зелені у складі міської влади — екологія є "
                "політичним пріоритетом",
        "letters_dir": "letters_green",
        "csv": "green_cities_mailing.csv",
        "page": "cities_green.html",
        "title": "🌱 «Зелені» міста Центральної та Північної Європи",
        "sub": "міста понад 30 000 мешканців, де Зелені у міській владі",
        "hint": "Два способи потрапити в перелік. <b>Автоматично</b> — чинний "
                "голова міста (Wikidata P6) є членом партії, що входить до "
                "Європейської партії зелених (примітка «мер від Зелених»). "
                "<b>Вручну</b> — місто, де Зелені є партнером правлячої "
                "коаліції: склад коаліцій у відкритих структурованих даних не "
                "публікується, тому такі міста внесено списком і позначено "
                "«коаліція (перевірити)» — перед листом варто переконатися, що "
                "коаліція ще чинна. Правиться у "
                "<code>config/green_cities.yaml</code>.",
        "footer": "Оновлення: <code>python scripts/fetch_city_partners.py "
                  "--only green</code> → <code>python -m grant_radar cities</code> "
                  "· розсилка: <code>data/green_cities_mailing.csv</code>",
    },
}


def load_partners(channel: str) -> list[dict[str, Any]]:
    data = config.load_yaml(CHANNELS[channel]["file"]) or {}
    return list(data.get("partners") or [])


def _uid(channel: str, p: dict[str, Any]) -> str:
    key = p.get("wikidata") or re.sub(r"\W+", "_", str(p.get("name", "")))
    return f"{CHANNELS[channel]['uid']}{p.get('country', '??')}:{key}"


def card(channel: str, p: dict[str, Any]) -> dict[str, Any]:
    """Картка донора з рядка довідника міст."""
    from . import donors as donors_mod

    meta = CHANNELS[channel]
    country = (p.get("country") or "??").upper()
    bridge = donors_mod.BRIDGE.get(country, 0)
    need = donors_mod.NEED_SCORE["waste"]
    cost = donors_mod.ENTRY_COST.get(country, 3)
    population = int(p.get("population") or 0)

    if channel == "big":
        # Д: місто-мільйонник має і бюджет, і гучну програму міжнародної
        # співпраці; від 100 тис. — принаймні профільний департамент
        proven = 2 if population >= 500000 else 1
    else:
        # Д: екологія в політичному порядку денному; мер від Зелених — вагоміше
        proven = 2 if str(p.get("note", "")).startswith("мер") else 1

    notes = [x for x in (p.get("admin"), ) if x]
    if population:
        notes.append(f"{population:,}".replace(",", " ") + " мешканців")
    if p.get("mayor"):
        notes.append(f"{p['mayor']} ({p.get('party', '')})".strip(" ()"))
    notes.append(p.get("note") or meta["what"])
    return {
        "uid": _uid(channel, p),
        "name": p.get("name") or "—",
        "country": country,
        "org_type": "municipality",
        "circle": meta["circle"],
        "goods": "waste",
        "what": meta["what"],
        "recipient": "",
        "event_date": "",
        "news_url": p.get("site") or "",
        "site": p.get("site") or "",
        "contact_person": "",
        "contact_email": p.get("email") or "",
        "contact_phone": p.get("phone") or "",
        "lang": p.get("lang") or donors_mod.LANG_BY_COUNTRY.get(country, "en"),
        "proven": proven, "bridge": bridge, "need": need, "cost": cost,
        "priority": proven + bridge + need - cost,
        "status": "new", "letter_sent_at": None, "followup_at": None,
        "notes": " · ".join(notes),
    }


def seed(db: Database, channel: str) -> dict[str, int]:
    """Додає/оновлює міста каналу в реєстрі донорів (ручні правки не чіпає)."""
    added = updated = 0
    for p in load_partners(channel):
        c = card(channel, p)
        existing = db.donor_by_uid(c["uid"])
        if existing:
            fields: dict[str, Any] = {
                "circle": c["circle"], "goods": c["goods"], "lang": c["lang"],
                "proven": c["proven"], "bridge": c["bridge"], "need": c["need"],
                "cost": c["cost"], "priority": c["priority"],
                "notes": c["notes"],
                "site": c["site"] or existing.get("site", ""),
            }
            if not existing.get("contact_email") and c["contact_email"]:
                fields["contact_email"] = c["contact_email"]
            if not existing.get("contact_phone") and c["contact_phone"]:
                fields["contact_phone"] = c["contact_phone"]
            db.set_donor(existing["id"], **fields)
            updated += 1
        else:
            db.add_donor(c)
            added += 1
    return {"added": added, "updated": updated}


def list_donors(db: Database, channel: str, *,
                only_with_email: bool = False) -> list[dict[str, Any]]:
    prefix = CHANNELS[channel]["uid"]
    rows = [d for d in db.donors(limit=5000)
            if str(d.get("uid") or "").startswith(prefix)]
    if only_with_email:
        rows = [d for d in rows if d.get("contact_email")]
    rows.sort(key=lambda d: (d.get("country", ""), -(d.get("priority") or 0),
                             d.get("name", "")))
    return rows


def _slug(text: str) -> str:
    return (re.sub(r"[^\w\-]+", "_", text, flags=re.U).strip("_")[:40]
            or "city")


def write_letters(db: Database, channel: str, out_dir: Path | None = None,
                  only_with_email: bool = True, limit: int = 1000) -> list[Path]:
    from . import donors as donors_mod

    meta = CHANNELS[channel]
    out_dir = Path(out_dir or config.DATA_DIR / meta["letters_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for d in list_donors(db, channel, only_with_email=only_with_email)[:limit]:
        path = out_dir / f"{d['country']}-{_slug(d['name'])}.txt"
        path.write_text(donors_mod.build_letter(d), encoding="utf-8")
        paths.append(path)
    return paths


def export_mailing(db: Database, channel: str, out: Path | None = None) -> Path:
    meta = CHANNELS[channel]
    out = Path(out or config.DATA_DIR / meta["csv"])
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["країна", "місто", "мова листа", "e-mail", "телефон",
                    "сайт", "населення", "пріоритет", "примітка", "статус",
                    "файл листа"])
        for d in list_donors(db, channel):
            pop = re.search(r"([\d\s]+) мешканців", d.get("notes") or "")
            fname = (f"data/{meta['letters_dir']}/"
                     f"{d['country']}-{_slug(d['name'])}.txt"
                     if d.get("contact_email") else "")
            note = (d.get("notes") or "").split(" · ")[-1]
            w.writerow([d.get("country", ""), d.get("name", ""),
                        d.get("lang", ""), d.get("contact_email", ""),
                        d.get("contact_phone", ""), d.get("site", ""),
                        pop.group(1).strip() if pop else "",
                        d.get("priority", 0), note, d.get("status", ""), fname])
    return out


def stats(db: Database, channel: str) -> dict[str, Any]:
    rows = list_donors(db, channel)
    by_country: dict[str, int] = {}
    mails: dict[str, int] = {}
    for d in rows:
        cc = d.get("country", "??")
        by_country[cc] = by_country.get(cc, 0) + 1
        if d.get("contact_email"):
            mails[cc] = mails.get(cc, 0) + 1
    return {"total": len(rows), "by_country": by_country, "with_email": mails,
            "emails": sum(mails.values()),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
