"""Канал «Дунайський басейн»: громади Австрії, Угорщини та Румунії на Дунаї.

Навіщо окремий канал. Вилок стоїть на Тисі — найбільшій притоці Дунаю.
Усе, що не зібрано як відходи у верхів'ї, паводок зносить у річку, і за
кілька днів пластик уже в Угорщині, далі — у Дунаї та Чорному морі. Для
громад нижче за течією наведення ладу з відходами у нас — не благодійність,
а власний інтерес: чистіша вода, рибні та рекреаційні ресурси, виконання
Рамкової водної директиви ЄС і зобов'язань ICPDR. Тому придунайські
самоврядування — природні адресати для листів про спільне КПП і техніку.

Перелік громад збирає `scripts/fetch_danube_partners.py` (OpenStreetMap +
Wikidata, без платних API) у файл `config/danube_partners.yaml`. Цей модуль
перетворює їх на картки донорів з uid `danube:<КРАЇНА>:<osm-id>`, рахує
пріоритет за тією самою методологією (Д + М + З − В) і готує розсилку.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .db import Database

UID_PREFIX = "danube:"
CIRCLE = 6  # «6 · Дунайський басейн» у donors.CIRCLE_LABEL

# М — місток: спільний річковий басейн додає +1 до базової близькості країни
BASIN_BONUS = 1

WHAT = {
    "AT": "громада на Дунаї (Австрія) — спільний річковий басейн Тиса → Дунай",
    "HU": "громада на Дунаї (Угорщина) — спільний річковий басейн Тиса → Дунай",
    "RO": "громада на Дунаї (Румунія) — спільний річковий басейн Тиса → Дунай",
}


def load_partners() -> list[dict[str, Any]]:
    """Читає `config/danube_partners.yaml`."""
    data = config.load_yaml("danube_partners.yaml") or {}
    return list(data.get("partners") or [])


def _uid(p: dict[str, Any]) -> str:
    return f"{UID_PREFIX}{p.get('country', '??')}:{p.get('osm') or p.get('name')}"


def card(p: dict[str, Any]) -> dict[str, Any]:
    """Картка донора з рядка довідника придунайських громад."""
    from . import donors as donors_mod

    country = (p.get("country") or "??").upper()
    bridge = min(3, donors_mod.BRIDGE.get(country, 0) + BASIN_BONUS)
    need = donors_mod.NEED_SCORE["waste"]
    cost = donors_mod.ENTRY_COST.get(country, 3)
    population = int(p.get("population") or 0)
    # великі міста мають бюджет і профільні департаменти — трохи вищий шанс
    proven = 1 if population >= 20000 else 0
    notes = []
    if p.get("admin"):
        notes.append(str(p["admin"]))
    if population:
        notes.append(f"{population:,}".replace(",", " ") + " мешканців")
    notes.append("канал: спільний басейн Дунаю")
    return {
        "uid": _uid(p),
        "name": p.get("name") or "—",
        "country": country,
        "org_type": "municipality",
        "circle": CIRCLE,
        "goods": "waste",
        "what": WHAT.get(country, "громада на Дунаї"),
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


def seed(db: Database) -> dict[str, int]:
    """Додає/оновлює придунайські громади в реєстрі донорів.

    Ручні правки (статус, контактна особа, нотатки) не чіпаються: для вже
    наявних карток оновлюємо лише бали, сайт і e-mail, якщо його ще не було.
    """
    added = updated = 0
    for p in load_partners():
        c = card(p)
        existing = db.donor_by_uid(c["uid"])
        if existing:
            fields: dict[str, Any] = {
                "circle": c["circle"], "goods": c["goods"], "lang": c["lang"],
                "proven": c["proven"], "bridge": c["bridge"], "need": c["need"],
                "cost": c["cost"], "priority": c["priority"],
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
    return {"added": added, "updated": updated, "total": len(list_donors(db))}


def list_donors(db: Database, *, only_with_email: bool = False) -> list[dict[str, Any]]:
    """Усі придунайські картки з реєстру (за uid-префіксом)."""
    rows = [d for d in db.donors(limit=5000)
            if str(d.get("uid") or "").startswith(UID_PREFIX)]
    if only_with_email:
        rows = [d for d in rows if d.get("contact_email")]
    rows.sort(key=lambda d: (d.get("country", ""), -(d.get("priority") or 0),
                             d.get("name", "")))
    return rows


def _slug(text: str) -> str:
    text = re.sub(r"[^\w\-]+", "_", text, flags=re.U).strip("_")
    return text[:40] or "partner"


def export_mailing(db: Database, out: Path | None = None) -> Path:
    """CSV для розсилки: кому, якою мовою, на яку адресу."""
    out = Path(out or config.DATA_DIR / "danube_mailing.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = list_donors(db)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["країна", "громада", "мова", "e-mail", "телефон",
                    "сайт", "населення", "пріоритет", "статус"])
        for d in rows:
            pop = re.search(r"([\d\s]+) мешканців", d.get("notes") or "")
            w.writerow([d.get("country", ""), d.get("name", ""), d.get("lang", ""),
                        d.get("contact_email", ""), d.get("contact_phone", ""),
                        d.get("site", ""), pop.group(1).strip() if pop else "",
                        d.get("priority", 0), d.get("status", "")])
    return out


def stats(db: Database) -> dict[str, Any]:
    rows = list_donors(db)
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
