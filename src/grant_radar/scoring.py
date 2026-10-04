"""Скоринг релевантності: правила + ключові слова (працює без жодних API-ключів).

Логіка:
  • збіг у ЗАГОЛОВКУ важить повний бал, збіг лише в тексті — 55 %;
  • профільна тема (відходи / комунальне / благоустрій / транспорт / бізнес) обов'язкова:
    без неї запис не може потрапити у «високу» релевантність;
  • для новин (не офіційних конкурсів) діють додаткові запобіжники від шуму;
  • мінус-слова (оборонка, поліція, суто наукові гранти, вакансії) б'ють сильно;
  • терміновість дедлайну та статус конкурсу дають невеликі бонуси.

Ключові слова можуть бути:
  • звичайним підрядком:        "комунальн"
  • регулярним виразом:         "re:громад(а|и|і|у|ою)\\b"
    (регулярні вирази потрібні там, де підрядок дає хибні збіги:
     «громад» інакше матчиться у «громадська організація», «громадянське суспільство»)
"""
from __future__ import annotations

import re
from typing import Any, Pattern

from .models import Opportunity

CORE_GROUPS = ("waste", "municipal", "urban", "transport", "business", "education")
BAND_LABEL = {"high": "🔥 Висока", "medium": "🟡 Середня", "low": "⚪ Низька"}

# Пороги для новинних записів (RSS), які не є офіційними конкурсами
NEWS_CAP_NO_CORE_TITLE = 22   # у заголовку немає профільного слова
NEWS_CAP_NO_SIGNAL = 28       # немає ознак конкурсу/фінансування


class Term:
    """Ключове слово: підрядок або регулярний вираз."""

    __slots__ = ("raw", "rx")

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.rx: Pattern[str] | None = (
            re.compile(raw[3:], re.IGNORECASE | re.UNICODE) if raw.startswith("re:") else None
        )

    def found(self, text: str) -> bool:
        return bool(self.rx.search(text)) if self.rx else (self.raw in text)

    @property
    def label(self) -> str:
        return self.raw[3:] if self.rx else self.raw


class Scorer:
    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile
        self.cfg = profile.get("scoring", {})
        self.scale = float(self.cfg.get("scale", 0.92))
        self.groups = {
            name: {"points": float(g.get("points", 0)),
                   "terms": [Term(t) for t in g.get("terms", [])]}
            for name, g in (profile.get("keyword_groups") or {}).items()
        }
        self.geo = self._block(profile.get("geo", {}))
        self.signal = self._block(profile.get("funding_signal", {}))
        self.negative = self._block(profile.get("negative", {}))

    @staticmethod
    def _block(block: dict[str, Any]) -> dict[str, Any]:
        return {"points": float(block.get("points", 0)),
                "terms": [Term(t) for t in block.get("terms", [])]}

    @staticmethod
    def _hits(terms: list[Term], title: str, body: str) -> tuple[list[str], list[str]]:
        th = [t.label for t in terms if t.found(title)]
        bh = [t.label for t in terms if t.label not in th and t.found(body)]
        return th, bh

    # ─────────────────────────────────────────────────────────────
    def score(self, opp: Opportunity, source_weight: float = 1.0
              ) -> tuple[int, str, list[str], dict[str, Any]]:
        """Повертає (бал, рівень, причини, метадані).

        Метадані: які групи спрацювали в заголовку / тексті та чи йдеться
        про придбання техніки, контейнерів, обладнання.
        """
        title = opp.title.lower()
        body = f"{opp.summary} {opp.programme} {opp.identifier}".lower()
        is_news = opp.status == "news"

        base = 0.0
        reasons: list[str] = []
        core_title = False
        core_any = False
        groups_title: list[str] = []
        groups_body: list[str] = []

        for name, group in self.groups.items():
            th, bh = self._hits(group["terms"], title, body)
            if not th and not bh:
                continue
            base += group["points"] * (1.0 if th else 0.55)
            reasons.append(f"{name}{'★' if th else ''}: {', '.join((th + bh)[:4])}")
            (groups_title if th else groups_body).append(name)
            if name in CORE_GROUPS:
                core_any = True
                core_title = core_title or bool(th)

        # Бонус: грант дозволяє придбати техніку, контейнери, обладнання —
        # для комунального підприємства це найцінніший тип підтримки.
        has_equipment = "equipment" in groups_title or "equipment" in groups_body
        if has_equipment and core_any:
            bonus = float(self.cfg.get("equipment_bonus", 10))
            base += bonus * (1.0 if "equipment" in groups_title else 0.6)
            reasons.append("🚛 можливе придбання техніки/контейнерів/обладнання")

        th, bh = self._hits(self.geo["terms"], title, body)
        if th or bh:
            base += self.geo["points"] * (1.0 if th else 0.6)
            reasons.append(f"гео: {', '.join((th + bh)[:3])}")

        sig_th, sig_bh = self._hits(self.signal["terms"], title, body)
        has_signal = bool(sig_th or sig_bh)
        if has_signal:
            base += self.signal["points"] * (1.0 if sig_th else 0.6)
            reasons.append(f"фінансування: {', '.join((sig_th + sig_bh)[:3])}")
        elif is_news:
            base -= 18
            reasons.append("немає ознак конкурсу/фінансування")

        neg_th, neg_bh = self._hits(self.negative["terms"], title, body)
        if neg_th or neg_bh:
            base += self.negative["points"] * (1.0 if neg_th else 0.6) * min(len(neg_th + neg_bh), 3)
            reasons.append(f"мінус: {', '.join((neg_th + neg_bh)[:3])}")

        days = opp.days_left()
        if days is not None:
            if days < 0:
                base += float(self.cfg.get("expired_penalty", -100))
                reasons.append("дедлайн минув")
            elif days <= int(self.cfg.get("deadline_bonus_days", 45)):
                base += float(self.cfg.get("deadline_bonus", 8))
                reasons.append(f"дедлайн через {days} дн.")

        if opp.status == "open":
            base += 8
            reasons.append("конкурс відкрито")
        elif opp.status == "forthcoming":
            base += 4
            reasons.append("конкурс анонсовано")

        if not core_any:
            base -= 30
            reasons.append("немає профільної тематики")

        points = max(0, min(100, int(round(base * float(source_weight) * self.scale))))

        # ── Запобіжники від шуму ────────────────────────────────────────────
        high = int(self.cfg.get("high_threshold", 60))
        if not core_title:
            # профільного слова немає в заголовку → максимум «середня»
            points = min(points, high - 1)
        if is_news:
            # новина без профільного слова в заголовку — майже завжди шум
            if not core_title and points > NEWS_CAP_NO_CORE_TITLE:
                points = NEWS_CAP_NO_CORE_TITLE
                reasons.append("новина без профільної теми в заголовку")
            # новина без жодної згадки конкурсу/дедлайну/фінансування
            if not has_signal and points > NEWS_CAP_NO_SIGNAL:
                points = NEWS_CAP_NO_SIGNAL

        meta = {"groups_title": groups_title, "groups_body": groups_body,
                "equipment": has_equipment}
        return points, self.band(points), reasons, meta

    def band(self, points: int) -> str:
        if points >= int(self.cfg.get("high_threshold", 60)):
            return "high"
        if points >= int(self.cfg.get("medium_threshold", 35)):
            return "medium"
        return "low"
