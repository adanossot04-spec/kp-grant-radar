"""Тематичні напрями (треки) — за ними групується підсумковий список грантів.

Напрям визначається за тим, які тематичні групи ключових слів спрацювали.
Пріоритет згори вниз: якщо є збіг у заголовку — він виграє у збігу в тексті.
"""
from __future__ import annotations

# порядок = пріоритет при визначенні основного напряму
TRACK_ORDER = ["partnership", "waste", "education", "inclusion", "water", "nature", "transport",
               "urban", "safety", "energy", "health", "veterans", "housing",
               "culture", "youth", "digital", "tourism", "business",
               "recovery", "other"]

LABEL = {
    "partnership": "🤝 Побратими та допомога технікою",
    "waste": "♻️ Відходи та циркулярна економіка",
    "education": "🎓 Освіта та навчання",
    "inclusion": "♿ Інклюзивність і безбар'єрність",
    "water": "💧 Вода, водовідведення, водні ресурси",
    "nature": "🌿 Довкілля, річки та біорізноманіття",
    "transport": "🚌 Транспорт і мобільність",
    "urban": "🌳 Благоустрій та громадські простори",
    "safety": "🛡 Безпека, укриття, розмінування",
    "energy": "⚡ Енергоефективність",
    "health": "🏥 Охорона здоров'я",
    "culture": "🎭 Культура та спадщина",
    "youth": "🧑\u200d🤝\u200d🧑 Молодь, спорт, громадська активність",
    "veterans": "🎖 Ветерани та соціальна підтримка",
    "housing": "🏘 Житло, ОСББ, модернізація будинків",
    "digital": "💻 Цифровізація та е-послуги",
    "tourism": "🧭 Туризм і рекреація",
    "business": "🏭 Розвиток бізнесу",
    "recovery": "🏗 Відновлення та стійкість",
    "other": "📋 Інше",
}

SHORT = {
    "partnership": "🤝 Побратими",
    "waste": "♻️ Відходи", "education": "🎓 Освіта", "inclusion": "♿ Інклюзія",
    "water": "💧 Вода", "nature": "🌿 Довкілля", "transport": "🚌 Транспорт",
    "urban": "🌳 Благоустрій", "safety": "🛡 Безпека", "energy": "⚡ Енергетика",
    "health": "🏥 Здоров'я", "culture": "🎭 Культура", "youth": "🧑\u200d🤝\u200d🧑 Молодь",
    "veterans": "🎖 Ветерани", "housing": "🏘 Житло", "digital": "💻 Цифровізація",
    "tourism": "🧭 Туризм", "business": "🏭 Бізнес", "recovery": "🏗 Відновлення",
    "other": "📋 Інше",
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
