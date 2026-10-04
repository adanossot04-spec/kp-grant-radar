"""Збирач зі звичайних HTML-сторінок зі списками грантів (без RSS).

Багато українських грантових каталогів не мають стрічки RSS, тому читаємо
безпосередньо сторінку-список за CSS-селекторами, які задаються в
`config/sources.yaml`:

  - id: gurt_grants
    type: html
    url: "https://m.gurt.org.ua/news/grants/all"
    params:
      item: "div.grid a[href*='/news/grants/']"   # елемент-картка або одразу <a>
      title: null          # селектор заголовка всередині item (якщо потрібен)
      summary: null        # селектор опису
      link: null           # селектор посилання (якщо item — не <a>)
      limit: 40
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import Opportunity
from .rss import UA, guess_deadline

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "uk,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml",
}


def _text(node, selector: str | None) -> str:
    if node is None:
        return ""
    target = node.select_one(selector) if selector else node
    return " ".join(target.get_text(" ", strip=True).split()) if target else ""


def _href(node, selector: str | None, base: str) -> str:
    if node is None:
        return ""
    if selector:
        a = node.select_one(selector)
    elif node.name == "a" and node.get("href"):
        a = node
    else:
        a = node.select_one("a[href]")
    if not a or not a.get("href"):
        return ""
    return urljoin(base, a["href"])


def collect(source: dict[str, Any]) -> list[Opportunity]:
    p = source.get("params", {}) or {}
    urls = p.get("urls") or [source.get("url")]
    item_sel = p.get("item") or "article"
    title_sel = p.get("title")
    summary_sel = p.get("summary")
    link_sel = p.get("link")
    limit = int(p.get("limit", 40))
    min_len = int(p.get("min_title_len", 18))

    out: dict[str, Opportunity] = {}
    for url in [u for u in urls if u]:
        try:
            r = requests.get(url, headers={**HEADERS, "User-Agent": HEADERS["User-Agent"] or UA},
                             timeout=40)
            r.raise_for_status()
            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding or "utf-8"
            soup = BeautifulSoup(r.text, "lxml")
        except Exception as exc:
            log.warning("HTML %s: %s", url, exc)
            continue

        items = soup.select(item_sel)[:limit]
        for el in items:
            title = _text(el, title_sel)
            if len(title) < min_len:
                continue
            link = _href(el, link_sel, url)
            if not link:
                continue
            summary = _text(el, summary_sel) if summary_sel else ""
            if not summary and not title_sel:
                summary = ""
            opp = Opportunity(
                source_id=source["id"],
                source_name=source["name"],
                region=source.get("region", "UA"),
                title=title,
                url=link,
                summary=summary,
                status="news",
                published_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                deadline_at=guess_deadline(f"{title} {summary}"),
                raw={"page": url},
            )
            out.setdefault(opp.uid, opp)
    return list(out.values())
