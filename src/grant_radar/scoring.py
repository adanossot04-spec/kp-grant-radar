"""Скоринг релевантності: правила + ключові слова (працює без жодних API-ключів).

Логіка:
  • збіг у ЗАГОЛОВКУ важить повний бал, збіг лише в тексті — 55 % бала;
  • профільна тема (відходи / комунальне / благоустрій / транспорт) обов'язкова:
    без неї запис не може потрапити у «високу» релевантність;
  • мінус-слова (оборонка, поліція, наука заради науки, вакансії) б'ють сильно;
  • терміновість дедлайну та статус конкурсу дають невеликі бонуси.
"""
from __future__ import annotations

from typing import Any

from .models import Opportunity

CORE_GROUPS = ("waste", "municipal", "urban", "transport", "business")
BAND_LABEL = {"high": "🔥 Висока", "medium": "🟡 Середня", "low": "⚪ Низька"}


class Scorer:
    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile
        self.groups: dict[str, dict] = profile.get("keyword_groups", {})
        self.geo = profile.get("geo", {})
        self.signal = profile.get("funding_signal", {})
        self.negative = profile.get("negative", {})
        self.cfg = profile.get("scoring", {})
        self.scale = float(self.cfg.get("scale", 0.75))

    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _hits(terms: list[str], title: str, body: str) -> tuple[list[str], list[str]]:
        th = [t for t in terms if t in title]
        bh = [t for t in terms if t not in th and t in body]
        return th, bh

    def score(self, opp: Opportunity, source_weight: float = 1.0) -> tuple[int, str, list[str]]:
        title = opp.title.lower()
        body = f"{opp.summary} {opp.programme} {opp.identifier}".lower()

        base = 0.0
        reasons: list[str] = []
        core_title = False
        core_any = False

        for name, group in self.groups.items():
            pts = float(group.get("points", 0))
            th, bh = self._hits(group.get("terms", []), title, body)
            if not th and not bh:
                continue
            factor = 1.0 if th else 0.55
            base += pts * factor
            shown = (th + bh)[:4]
            reasons.append(f"{name}{'★' if th else ''}: {', '.join(shown)}")
            if name in CORE_GROUPS:
                core_any = True
                core_title = core_title or bool(th)

        for block, label in ((self.geo, "гео"), (self.signal, "фінансування")):
            th, bh = self._hits(block.get("terms", []), title, body)
            if th or bh:
                base += float(block.get("points", 0)) * (1.0 if th else 0.6)
                reasons.append(f"{label}: {', '.join((th + bh)[:3])}")
            elif block is self.signal and opp.status == "news":
                # новина без жодної згадки про конкурс/дедлайн/фінансування — це не можливість
                base -= 18
                reasons.append("немає ознак конкурсу/фінансування")

        neg_th, neg_bh = self._hits(self.negative.get("terms", []), title, body)
        if neg_th or neg_bh:
            penalty = float(self.negative.get("points", -25))
            base += penalty * (1.0 if neg_th else 0.6) * min(len(neg_th + neg_bh), 3)
            reasons.append(f"мінус: {', '.join((neg_th + neg_bh)[:3])}")

        # Терміновість дедлайну
        days = opp.days_left()
        if days is not None:
            if days < 0:
                base += float(self.cfg.get("expired_penalty", -100))
                reasons.append("дедлайн минув")
            elif days <= int(self.cfg.get("deadline_bonus_days", 45)):
                base += float(self.cfg.get("deadline_bonus", 8))
                reasons.append(f"дедлайн через {days} дн.")

        # Статус офіційного конкурсу важливіший за новину
        if opp.status == "open":
            base += 8
            reasons.append("конкурс відкрито")
        elif opp.status == "forthcoming":
            base += 4
            reasons.append("конкурс анонсовано")

        if not core_any:
            base -= 30
            reasons.append("немає профільної тематики")

        points = int(round(base * float(source_weight) * self.scale))
        points = max(0, min(100, points))

        # Без профільного слова в заголовку — максимум «середня» релевантність
        if not core_title:
            points = min(points, int(self.cfg.get("high_threshold", 60)) - 1)

        return points, self.band(points), reasons

    def band(self, points: int) -> str:
        if points >= int(self.cfg.get("high_threshold", 60)):
            return "high"
        if points >= int(self.cfg.get("medium_threshold", 35)):
            return "medium"
        return "low"
