"""Завантаження конфігурації агента."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.getenv("GR_CONFIG_DIR", ROOT / "config"))
DATA_DIR = Path(os.getenv("GR_DATA_DIR", ROOT / "data"))
DOCS_DIR = Path(os.getenv("GR_DOCS_DIR", ROOT / "docs"))
TEMPLATES_DIR = ROOT / "templates"
DB_PATH = Path(os.getenv("GR_DB_PATH", DATA_DIR / "grants.sqlite"))


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_sources() -> list[dict[str, Any]]:
    data = load_yaml("sources.yaml")
    return [s for s in data.get("sources", []) if s.get("enabled", True)]


def load_profile() -> dict[str, Any]:
    return load_yaml("profile.yaml")


def profile_text(profile: dict[str, Any]) -> str:
    org = profile.get("organization", {})
    return (
        f"Організація: {org.get('name', '')}\n"
        f"Країна/регіон: {org.get('country', '')}, {org.get('region', '')}\n"
        f"Сфера: {org.get('sector', '')}\n"
        f"Опис: {org.get('description', '')}"
    )
