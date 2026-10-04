"""Тематичні напрями (треки) — за ними групується підсумковий список грантів.

Напрям визначається за тим, які тематичні групи ключових слів спрацювали.
Пріоритет згори вниз: якщо є збіг у заголовку — він виграє у збігу в тексті.
"""
from __future__ import annotations

# порядок = пріоритет при визначенні основного напряму
TRACK_ORDER = ["waste", "education", "transport", "urban", "water", "energy",
               "business", "recovery", "other"]

LABEL = {
    "waste": "♻️ Відходи та циркулярна економіка",
    "education": "🎓 Освіта та навчання",
    "transport": "🚌 Транспорт і мобільність",
    "urban": "🌳 Благоустрій та громадські простори",
    "water": "💧 Вода та водовідведення",
    "energy": "⚡ Енергоефективність",
    "business": "🏭 Розвиток бізнесу",
    "recovery": "🏗 Відновлення та стійкість",
    "other": "📋 Інше",
}

SHORT = {
    "waste": "♻️ Відходи", "education": "🎓 Освіта", "transport": "🚌 Транспорт",
    "urban": "🌳 Благоустрій", "water": "💧 Вода", "energy": "⚡ Енергетика",
    "business": "🏭 Бізнес", "recovery": "🏗 Відновлення", "other": "📋 Інше",
}

# напрями, які виводяться першими у підсумковому файлі перегляду
PRIORITY_VIEW = ["waste", "education"]


def detect(groups_title: list[str], groups_body: list[str]) -> str:
    """Основний напрям можливості за спрацьованими групами ключових слів."""
    for track in TRACK_ORDER:
        if track in groups_title:
            return track
    for track in TRACK_ORDER:
        if track in groups_body:
            return track
    return "other"


def sort_key(track: str) -> tuple[int, int]:
    """Ключ сортування: спершу пріоритетні напрями (відходи, освіта)."""
    if track in PRIORITY_VIEW:
        return (0, PRIORITY_VIEW.index(track))
    return (1, TRACK_ORDER.index(track) if track in TRACK_ORDER else 99)


def ordered_tracks(present: list[str]) -> list[str]:
    """Напрями у порядку показу: відходи → освіта → решта."""
    return sorted(set(present), key=sort_key)
