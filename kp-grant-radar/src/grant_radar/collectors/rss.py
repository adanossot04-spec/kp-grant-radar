"""Універсальний збирач RSS/Atom-стрічок (донори, програми, міністерства)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import feedparser
import requests

from ..models import Opportunity

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (compatible; KP-GrantRadar/1.0; +https://github.com/)"

# Пошук дедлайну прямо в тексті новини: «до 15 листопада 2026», «deadline: 30 November 2026»
UA_MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}
EN_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

RE_UA = re.compile(r"до\s+(\d{1,2})\s+([а-яіїєґ]+)\s+(\d{4})", re.IGNORECASE)
RE_EN = re.compile(r"(?:deadline|until|by)\D{0,15}(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)
RE_ISO = re.compile(r"(?:дедлайн|deadline|до)\D{0,15}(\d{4})-(\d{2})-(\d{2})", re.IGNORECASE)
RE_DOT = re.compile(r"(?:дедлайн|deadline|до)\D{0,15}(\d{1,2})[./](\d{1,2})[./](\d{4})", re.IGNORECASE)


def guess_deadline(text: str) -> str | None:
    t = text.lower()
    try:
        m = RE_UA.search(t)
        if m and m.group(2) in UA_MONTHS:
            return datetime(int(m.group(3)), UA_MONTHS[m.group(2)], int(m.group(1)),
                            tzinfo=timezone.utc).isoformat(timespec="seconds")
        m = RE_EN.search(t)
        if m and m.group(2).lower() in EN_MONTHS:
            return datetime(int(m.group(3)), EN_MONTHS[m.group(2).lower()], int(m.group(1)),
                            tzinfo=timezone.utc).isoformat(timespec="seconds")
        m = RE_ISO.search(t)
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            tzinfo=timezone.utc).isoformat(timespec="seconds")
        m = RE_DOT.search(t)
        if m:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                            tzinfo=timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return None
    return None


def collect(source: dict[str, Any]) -> list[Opportunity]:
    url = source["url"]
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=40)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as exc:
        log.warning("RSS %s: %s", url, exc)
        return []

    out: list[Opportunity] = []
    for e in feed.entries[:120]:
        title = getattr(e, "title", "")
        if not title:
            continue
        body = ""
        for key in ("summary", "description"):
            if getattr(e, key, None):
                body = getattr(e, key)
                break
        if getattr(e, "content", None):
            body = " ".join(c.get("value", "") for c in e.content) or body

        published = None
        for key in ("published_parsed", "updated_parsed"):
            tt = getattr(e, key, None)
            if tt:
                published = datetime(*tt[:6], tzinfo=timezone.utc).isoformat(timespec="seconds")
                break

        full_text = f"{title} {body}"
        out.append(Opportunity(
            source_id=source["id"],
            source_name=source["name"],
            region=source.get("region", "INT"),
            title=title,
            url=getattr(e, "link", url),
            summary=body,
            status="news",
            published_at=published,
            deadline_at=guess_deadline(full_text),
            raw={"feed": url},
        ))
    return out
