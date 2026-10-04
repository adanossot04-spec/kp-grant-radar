"""TED — Tenders Electronic Daily: усі тендери ЄС. Безкоштовний API, ключ не потрібен.

Документація: https://docs.ted.europa.eu/api/latest/index.html
Корисно насамперед приватним підприємствам (підряди, постачання) та КП,
які можуть бути виконавцями у проєктах міжнародної допомоги.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import requests

from ..models import Opportunity

log = logging.getLogger(__name__)

API = "https://api.ted.europa.eu/v3/notices/search"
FIELDS = [
    "publication-number", "notice-title", "buyer-name", "deadline-receipt-request",
    "place-of-performance", "notice-type", "publication-date",
    "total-value", "classification-cpv",
]


def _val(item: dict[str, Any], key: str) -> str:
    v = item.get(key)
    if isinstance(v, dict):                      # мультимовне поле {"eng": [...]}
        for lang in ("eng", "ENG", "MUL", "ukr"):
            if v.get(lang):
                v = v[lang]
                break
        else:
            v = next(iter(v.values()), "")
    if isinstance(v, list):
        v = v[0] if v else ""
        if isinstance(v, dict):
            v = next(iter(v.values()), "")
    return str(v or "")


def collect(source: dict[str, Any]) -> list[Opportunity]:
    p = source.get("params", {}) or {}
    queries: list[str] = p.get("queries") or ['notice-title ~ (waste)']
    limit = int(p.get("limit", 50))
    out: dict[str, Opportunity] = {}

    for q in queries:
        try:
            r = requests.post(API, json={"query": q, "limit": limit, "page": 1,
                                         "fields": FIELDS, "scope": "ACTIVE"},
                              timeout=60)
            if r.status_code == 400:   # інколи 'scope' не підтримується для запиту
                r = requests.post(API, json={"query": q, "limit": limit, "page": 1,
                                             "fields": FIELDS}, timeout=60)
            r.raise_for_status()
            notices = r.json().get("notices") or []
        except Exception as exc:
            log.warning("TED '%s': %s", q, exc)
            continue

        for n in notices:
            pub = _val(n, "publication-number")
            title = _val(n, "notice-title")
            if not title:
                continue
            deadline = _val(n, "deadline-receipt-request")[:19] or None
            published = _val(n, "publication-date")[:19] or None
            opp = Opportunity(
                source_id=source["id"],
                source_name=source["name"],
                region=source.get("region", "EU"),
                title=title,
                url=f"https://ted.europa.eu/en/notice/-/detail/{pub}",
                summary=" ".join(filter(None, [
                    f"Замовник: {_val(n, 'buyer-name')}" if _val(n, "buyer-name") else "",
                    f"Тип: {_val(n, 'notice-type')}" if _val(n, "notice-type") else "",
                    f"CPV: {_val(n, 'classification-cpv')}" if _val(n, "classification-cpv") else "",
                    f"Вартість: {_val(n, 'total-value')}" if _val(n, "total-value") else "",
                    "Тендер ЄС (TED). Можуть брати участь підприємства, зокрема з України.",
                ])),
                programme="TED — публічні закупівлі ЄС",
                identifier=pub,
                status="open",
                published_at=_norm(published),
                deadline_at=_norm(deadline),
                raw={"ted_query": q},
            )
            out.setdefault(opp.uid, opp)
    return list(out.values())


def _norm(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat(timespec="seconds")
    except ValueError:
        return raw[:19] or None
