"""Пошук у вебі без API-ключа (DuckDuckGo HTML).

Дає змогу знаходити грантові оголошення на сайтах, яких немає ні в RSS,
ні в новинних агрегаторах: сторінки донорів, ОДА, фондів, каталоги грантів.

  - id: websearch_ua
    type: websearch
    params:
      per_query: 12
      region: "ua-uk"      # мова/регіон видачі
      queries:
        - "гранти для громад 2026 конкурс заявок"
        - "site:gurt.org.ua гранти громада"
"""
from __future__ import annotations

import logging
import random
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from ..models import Opportunity
from .rss import guess_deadline

log = logging.getLogger(__name__)

ENDPOINTS = ["https://html.duckduckgo.com/html/", "https://lite.duckduckgo.com/lite/"]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "uk,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded",
}
SKIP_HOSTS = ("duckduckgo.com", "youtube.com", "facebook.com", "instagram.com",
              "tiktok.com", "twitter.com", "x.com", "pinterest.")


def _clean_link(href: str) -> str:
    """DuckDuckGo інколи віддає посилання як /l/?uddg=<urlencoded>."""
    if href.startswith("//"):
        href = "https:" + href
    m = re.search(r"[?&]uddg=([^&]+)", href)
    if m:
        href = urllib.parse.unquote(m.group(1))
    return href


def _search(query: str, region: str, timeout: int = 40) -> list[tuple[str, str, str]]:
    for url in ENDPOINTS:
        try:
            r = requests.post(url, data={"q": query, "kl": region},
                              headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            if "anomaly" in r.text[:4000].lower() or "challenge" in r.text[:4000].lower():
                log.warning("websearch: тимчасове обмеження пошуковика (%s)", url)
                continue
            soup = BeautifulSoup(r.text, "lxml")
            rows: list[tuple[str, str, str]] = []

            for a in soup.select("a.result__a, a.result-link"):
                href = _clean_link(a.get("href", ""))
                title = " ".join(a.get_text(" ", strip=True).split())
                if not href.startswith("http") or len(title) < 15:
                    continue
                block = a.find_parent(["div", "tr", "table"])
                snippet = ""
                if block:
                    sn = block.select_one(".result__snippet, .result-snippet")
                    if sn:
                        snippet = " ".join(sn.get_text(" ", strip=True).split())
                rows.append((title, href, snippet))
            if rows:
                return rows
        except Exception as exc:
            log.warning("websearch '%s' (%s): %s", query, url, exc)
    return []


def collect(source: dict[str, Any]) -> list[Opportunity]:
    p = source.get("params", {}) or {}
    queries: list[str] = p.get("queries") or []
    region = str(p.get("region", "ua-uk"))
    per_query = int(p.get("per_query", 12))

    out: dict[str, Opportunity] = {}
    for i, q in enumerate(queries):
        if i:
            time.sleep(random.uniform(2.5, 5.0))   # ввічлива пауза проти блокувань
        for title, href, snippet in _search(q, region)[:per_query]:
            if any(h in href for h in SKIP_HOSTS):
                continue
            opp = Opportunity(
                source_id=source["id"],
                source_name=source["name"],
                region=source.get("region", "UA"),
                title=title,
                url=href,
                summary=snippet,
                programme=f"пошук: {q}"[:300],
                status="news",
                published_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                deadline_at=guess_deadline(f"{title} {snippet}"),
                raw={"query": q},
            )
            out.setdefault(opp.uid, opp)
    return list(out.values())
