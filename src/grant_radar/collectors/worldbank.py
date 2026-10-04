"""Світовий банк — проєкти та операції. Безкоштовний API без ключа.

Документація: https://search.worldbank.org/api/v2/projects
Показує проєкти МФО по Україні, у межах яких громади та підприємства
отримують обладнання, субпроєкти й підряди.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import requests

from ..models import Opportunity

log = logging.getLogger(__name__)

API = "https://search.worldbank.org/api/v2/projects"


def collect(source: dict[str, Any]) -> list[Opportunity]:
    p = source.get("params", {}) or {}
    rows = int(p.get("rows", 60))
    country = p.get("country", "UA")
    try:
        r = requests.get(API, params={
            "format": "json", "countrycode_exact": country, "rows": rows,
            "fl": ("id,project_name,pdo,boardapprovaldate,closingdate,totalamt,"
                   "sector,theme,url,status,countryname,lendinginstr"),
            "os": 0, "srt": "boardapprovaldate", "order": "desc",
        }, timeout=60)
        r.raise_for_status()
        projects = (r.json() or {}).get("projects") or {}
    except Exception as exc:
        log.warning("World Bank: %s", exc)
        return []

    out: list[Opportunity] = []
    for pid, pr in projects.items():
        name = pr.get("project_name") or ""
        if not name:
            continue
        sectors = ", ".join(s.get("Name", "") for s in (pr.get("sector") or []) if isinstance(s, dict))
        amount = pr.get("totalamt") or ""
        out.append(Opportunity(
            source_id=source["id"],
            source_name=source["name"],
            region=source.get("region", "INT"),
            title=name,
            url=pr.get("url") or f"https://projects.worldbank.org/en/projects-operations/project-detail/{pid}",
            summary=" ".join(filter(None, [
                pr.get("pdo") or "",
                f"Сектори: {sectors}." if sectors else "",
                f"Сума: {amount}." if amount else "",
                f"Статус: {pr.get('status', '')}.",
                "Проєкт Світового банку: громади та підприємства можуть бути "
                "бенефіціарами субпроєктів і учасниками закупівель.",
            ])),
            programme=f"World Bank · {pr.get('lendinginstr', '')}".strip(" ·"),
            identifier=pid,
            status="open" if str(pr.get("status", "")).lower() == "active" else "news",
            published_at=_norm(pr.get("boardapprovaldate")),
            deadline_at=_norm(pr.get("closingdate")),
            budget=str(amount),
            raw={"wb_id": pid},
        ))
    return out


def _norm(raw: str | None) -> str | None:
    """API Світового банку віддає дати то в ISO, то у форматі `6/30/2025 12:00:00`.

    Раніше неформатована дата зберігалась «як є» — і такий рядок не міг
    порівнятися з поточною датою, тож закриті проєкти показувались як чинні.
    Тепер будь-яка дата зводиться до ISO, а нерозпізнана відкидається.
    """
    if not raw:
        return None
    s = str(raw).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).isoformat(timespec="seconds")
    except ValueError:
        pass
    m = re.match(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", s)          # M/D/YYYY
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat(timespec="seconds")
        except ValueError:
            return None
    try:
        from dateutil import parser as dtparser
        return dtparser.parse(s, dayfirst=False).isoformat(timespec="seconds")
    except Exception:
        log.debug("World Bank: невідомий формат дати %r", s)
        return None
