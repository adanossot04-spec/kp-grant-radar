"""Дайджест нових можливостей: Markdown-файл + (опційно) Telegram."""
from __future__ import annotations

import logging
import os
from datetime import datetime

import requests

from .db import Database
from . import tracks as tracks_mod
from . import budget as budget_mod
from .classify import LABEL as BENEF_LABEL
from .scoring import BAND_LABEL

log = logging.getLogger(__name__)


def build_markdown(db: Database, min_score: int = 40, only_new: bool = True) -> tuple[str, list[str]]:
    items = db.unnotified(min_score) if only_new else db.query(min_score=min_score, limit=40)
    today = datetime.now().strftime("%d.%m.%Y")
    if not items:
        return f"# Грант-радар — {today}\n\nНових релевантних можливостей не знайдено.\n", []

    lines = [f"# 🛰️ Грант-радар — {today}", "",
             f"Нових можливостей з балом ≥ {min_score}: **{len(items)}**", ""]

    buckets: dict[str, list] = {"communal": [], "both": [], "private": [], "unknown": []}
    for it in items:
        buckets.setdefault(it.get("beneficiary") or "unknown", buckets["unknown"]).append(it)

    for key in ("communal", "both", "private", "unknown"):
        part = buckets[key]
        if not part:
            continue
        lines += [f"---", "", f"# {BENEF_LABEL[key]} ({len(part)})", ""]
        for it in part:
            dl = ""
            if it.get("days_left") is not None:
                dl = f" · ⏳ дедлайн {it['deadline_at'][:10]} ({it['days_left']} дн.)"
            lines.append(f"## {BAND_LABEL.get(it['band'], '')} {it['score']}/100 — {it['title']}")
            marks = tracks_mod.SHORT.get(it.get("track") or "other", "")
            if it.get("equipment"):
                marks += " · 🚛 техніка/контейнери"
            money = budget_mod.human(it.get("budget_eur"))
            if money:
                marks += f" · 💶 {money}"
            lines.append(f"*{marks} · {it['source_name']}{dl}*")
            lines.append("")
            text = it.get("llm_summary") or (it.get("summary") or "")[:400]
            if text:
                lines.append(text)
            if it.get("llm_fit"):
                lines.append(f"\n**Чи підходить:** {it['llm_fit']}")
            if it.get("llm_actions"):
                lines.append(f"\n**Наступні кроки:** {it['llm_actions']}")
            lines.append(f"\n🔗 {it['url']}\n")
    return "\n".join(lines), [it["uid"] for it in items]


def send_telegram(text: str) -> bool:
    """Потрібні TELEGRAM_BOT_TOKEN і TELEGRAM_CHAT_ID (GitHub Secrets)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat):
        return False
    ok = True
    for chunk in _chunks(text, 3800):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": chunk, "parse_mode": "Markdown",
                      "disable_web_page_preview": False},
                timeout=30)
            ok = ok and r.ok
            if not r.ok:
                log.warning("Telegram: %s", r.text[:200])
        except Exception as exc:
            log.warning("Telegram: %s", exc)
            ok = False
    return ok


def _chunks(text: str, size: int):
    buf = ""
    for para in text.split("\n\n"):
        if len(buf) + len(para) + 2 > size:
            yield buf
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        yield buf
