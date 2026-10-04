"""Збирач з офіційного порталу ЄС (EU Funding & Tenders Portal, пошуковий API SEDIA).

Важливо: параметри query/languages/sort портал приймає ТІЛЬКИ як multipart-файли
з Content-Type application/json. Передані звичайними полями форми → HTTP 500.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import requests

from ..models import Opportunity

log = logging.getLogger(__name__)

API = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
TOPIC_URL = ("https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/"
             "opportunities/topic-details/{ident}")
STATUS_MAP = {"31094501": "forthcoming", "31094502": "open", "31094503": "closed"}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KP-GrantRadar/1.0)",
    "Accept": "application/json, text/plain, */*",
}


def _first(meta: dict[str, Any], key: str, default: str = "") -> str:
    val = meta.get(key)
    if isinstance(val, list):
        return str(val[0]) if val else default
    return str(val) if val is not None else default


def _iso(raw: str) -> str | None:
    """'2026-10-29T00:00:00.000+0000' → '2026-10-29T00:00:00+00:00'"""
    if not raw:
        return None
    raw = raw.replace("+0000", "+00:00")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        from datetime import datetime
        return datetime.fromisoformat(raw).isoformat(timespec="seconds")
    except ValueError:
        return raw[:19]


def _search(text: str, query: dict, page: int, page_size: int, timeout: int = 60) -> dict:
    params = {"apiKey": "SEDIA", "text": text or "***",
              "pageSize": str(page_size), "pageNumber": str(page)}
    files = {
        "query": ("blob", json.dumps(query), "application/json"),
        "languages": ("blob", json.dumps(["en"]), "application/json"),
        "sort": ("blob", json.dumps({"field": "sortStatus", "order": "ASC"}), "application/json"),
    }
    r = requests.post(API, params=params, files=files, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def collect(source: dict[str, Any]) -> list[Opportunity]:
    p = source.get("params", {}) or {}
    types = p.get("types", ["1", "2"])
    statuses = p.get("statuses", ["31094501", "31094502"])
    page_size = int(p.get("page_size", 100))
    max_pages = int(p.get("max_pages", 5))
    queries = p.get("queries") or ["***"]

    query = {"bool": {"must": [{"terms": {"type": types}}, {"terms": {"status": statuses}}]}}
    seen: dict[str, Opportunity] = {}

    for text in queries:
        for page in range(1, max_pages + 1):
            try:
                data = _search(text, query, page, page_size)
            except Exception as exc:  # мережа/ліміти — не валимо весь запуск
                log.warning("SEDIA '%s' стор.%s: %s", text, page, exc)
                break
            results = data.get("results") or []
            for item in results:
                opp = _parse(item, source)
                if opp and opp.uid not in seen:
                    seen[opp.uid] = opp
            if len(results) < page_size:
                break
    return list(seen.values())


def _parse(item: dict[str, Any], source: dict[str, Any]) -> Opportunity | None:
    meta = item.get("metadata") or {}
    ident = _first(meta, "identifier")
    title = _first(meta, "title") or item.get("content", "")[:200]
    if not title:
        return None

    summary_parts = [
        _first(meta, "callTitle"),
        _first(meta, "descriptionByte"),
        " ".join(meta.get("keywords") or [])[:500],
        (item.get("content") or "")[:1500],
    ]
    url = item.get("url") or ""
    if ident and "topic-details" not in url:
        url = TOPIC_URL.format(ident=ident)

    return Opportunity(
        source_id=source["id"],
        source_name=source["name"],
        region=source.get("region", "EU"),
        title=title,
        url=url,
        summary=" ".join(x for x in summary_parts if x),
        programme=_first(meta, "frameworkProgramme") or _first(meta, "programmeDivision"),
        identifier=ident,
        status=STATUS_MAP.get(_first(meta, "status"), _first(meta, "status")),
        published_at=_iso(_first(meta, "startDate")),
        deadline_at=_iso(_first(meta, "deadlineDate")),
        budget=_first(meta, "budgetOverview")[:6000],
        raw={"metadata": {k: meta.get(k) for k in
                          ("identifier", "callIdentifier", "typesOfAction", "deadlineModel",
                           "frameworkProgramme", "status", "crossCuttingPriorities")}},
    )
