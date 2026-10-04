"""Пошуковий збирач: Google News RSS (безкоштовно, без ключа й реєстрації).

Дає змогу шукати грантові оголошення скрізь — у регіональних ЗМІ, на сайтах
громад, у телеграм-дайджестах тощо, навіть якщо в джерела немає власної RSS.

Кожен запит у `params.queries` перетворюється на окрему стрічку:
    https://news.google.com/rss/search?q=<запит>&hl=uk&gl=UA&ceid=UA:uk

Підтримуються оператори Google: лапки, OR, -мінус, site:, when:7d.
Приклад: '"конкурс грантів" громада (сміттєвоз OR контейнери) when:30d'
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import feedparser
import requests

from ..models import Opportunity
from .rss import UA, guess_deadline

log = logging.getLogger(__name__)

BASE = "https://news.google.com/rss/search"


def _feed_url(query: str, lang: str, country: str) -> str:
    q = urllib.parse.quote(query)
    return f"{BASE}?q={q}&hl={lang}&gl={country}&ceid={country}:{lang}"


def collect(source: dict[str, Any]) -> list[Opportunity]:
    p = source.get("params", {}) or {}
    queries: list[str] = p.get("queries") or []
    lang = str(p.get("lang", "uk"))
    country = str(p.get("country", "UA"))
    per_query = int(p.get("per_query", 20))

    out: dict[str, Opportunity] = {}
    for q in queries:
        url = _feed_url(q, lang, country)
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        except Exception as exc:
            log.warning("Google News '%s': %s", q, exc)
            continue

        for e in feed.entries[:per_query]:
            title = getattr(e, "title", "")
            if not title:
                continue
            # Google додає до заголовка « - Назва видання» — прибираємо
            clean = re.sub(r"\s+-\s+[^-]{2,40}$", "", title).strip()
            body = getattr(e, "summary", "") or ""
            link = getattr(e, "link", "")
            published = None
            tt = getattr(e, "published_parsed", None)
            if tt:
                published = datetime(*tt[:6], tzinfo=timezone.utc).isoformat(timespec="seconds")

            opp = Opportunity(
                source_id=source["id"],
                source_name=source["name"],
                region=source.get("region", "UA"),
                title=clean or title,
                url=link,
                summary=body,
                programme=f"пошук: {q}"[:300],
                status="news",
                published_at=published,
                deadline_at=guess_deadline(f"{clean} {body}"),
                raw={"query": q},
            )
            out.setdefault(opp.uid, opp)
    return list(out.values())
