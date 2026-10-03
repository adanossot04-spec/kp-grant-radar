"""Моделі даних агента."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _clean(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(text))
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@dataclass
class Opportunity:
    """Одна грантова можливість / оголошення."""

    source_id: str
    source_name: str
    region: str                 # EU | UA | INT
    title: str
    url: str
    summary: str = ""
    programme: str = ""
    identifier: str = ""
    status: str = ""            # open | forthcoming | news
    published_at: str | None = None   # ISO
    deadline_at: str | None = None    # ISO
    budget: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    # обчислюється пайплайном
    uid: str = ""
    beneficiary: str = "unknown"      # communal | private | both | unknown
    beneficiary_why: str = ""
    score: int = 0
    band: str = ""
    reasons: str = ""
    llm_score: int | None = None
    llm_summary: str = ""
    llm_fit: str = ""
    llm_actions: str = ""
    first_seen: str = ""
    last_seen: str = ""

    def __post_init__(self) -> None:
        self.title = _clean(self.title)[:500]
        self.summary = _clean(self.summary)[:4000]
        self.programme = _clean(self.programme)[:300]
        if not self.uid:
            basis = (self.identifier or self.url or self.title).lower().strip()
            self.uid = hashlib.sha1(f"{self.source_id}|{basis}".encode()).hexdigest()[:16]

    @property
    def text_blob(self) -> str:
        return " ".join([self.title, self.summary, self.programme, self.identifier]).lower()

    def days_left(self) -> int | None:
        if not self.deadline_at:
            return None
        try:
            dt = datetime.fromisoformat(self.deadline_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt - datetime.now(timezone.utc)).days

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["raw"] = ""  # сире тіло зберігаємо окремо
        d["days_left"] = self.days_left()
        return d
