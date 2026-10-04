"""Робота з файлом-пам'яттю (config/memory.yaml): завантаження, аналіз повноти,
формування текстового досьє для заявок і для LLM.
"""
from __future__ import annotations

from typing import Any

from . import config

CRITICAL_PATHS = [
    "identity.legal_name_uk", "identity.legal_name_en", "identity.edrpou",
    "contacts.legal_address_en", "contacts.email_official", "contacts.head.full_name_uk",
    "banking.iban_uah", "boilerplate.org_description_uk_500", "boilerplate.org_description_en_500",
]


def load() -> list[dict[str, Any]]:
    """Читає config/memory.yaml, а якщо його немає — шаблон memory.example.yaml."""
    for name in ("memory.yaml", "memory.example.yaml"):
        try:
            data = config.load_yaml(name)
        except FileNotFoundError:
            continue
        return data.get("organizations", []) or []
    return []


def active_orgs() -> list[dict[str, Any]]:
    return [o for o in load() if o.get("active", True)]


def pick(beneficiary: str, org_id: str | None = None) -> dict[str, Any] | None:
    """Обрати організацію під тип бенефіціара можливості."""
    orgs = active_orgs()
    if not orgs:
        return None
    if org_id:
        for o in orgs:
            if o.get("id") == org_id:
                return o
    want = {"communal": "communal", "private": "private"}.get(beneficiary)
    if want:
        for o in orgs:
            if o.get("entity_type") == want:
                return o
    return orgs[0]


def get_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _is_empty(v: Any) -> bool:
    if v is None or v == "" or v == [] or v == {} or v == 0 or v is False:
        return True
    if isinstance(v, list):
        return all(_is_empty(x) for x in v)
    if isinstance(v, dict):
        return all(_is_empty(x) for x in v.values())
    return False


def completeness(org: dict[str, Any]) -> dict[str, Any]:
    """Відсоток заповнення + перелік прогалин по секціях."""
    sections: dict[str, tuple[int, int]] = {}
    missing: list[str] = []

    def walk(node: Any, prefix: str, section: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{prefix}.{k}" if prefix else k, section)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{prefix}[{i}]", section)
        else:
            filled, total = sections.get(section, (0, 0))
            empty = _is_empty(node)
            sections[section] = (filled + (0 if empty else 1), total + 1)
            if empty:
                missing.append(prefix)

    for key, value in org.items():
        if key in ("id", "entity_type", "active"):
            continue
        walk(value, key, key)

    filled = sum(f for f, _ in sections.values())
    total = sum(t for _, t in sections.values()) or 1
    crit_missing = [p for p in CRITICAL_PATHS if _is_empty(get_path(org, p))]
    return {
        "percent": round(100 * filled / total),
        "filled": filled, "total": total,
        "sections": {k: {"percent": round(100 * f / t) if t else 0, "filled": f, "total": t}
                     for k, (f, t) in sorted(sections.items())},
        "missing": missing,
        "critical_missing": crit_missing,
    }


def dossier_text(org: dict[str, Any], max_len: int = 6000) -> str:
    """Стисле текстове досьє — контекст для LLM і для чернетки заявки."""
    g = lambda p: get_path(org, p) or ""  # noqa: E731
    lines = [
        f"Тип організації: {'комунальне підприємство' if org.get('entity_type') == 'communal' else 'приватне підприємство'}",
        f"Назва (UA): {g('identity.legal_name_uk')}",
        f"Назва (EN): {g('identity.legal_name_en')}",
        f"ЄДРПОУ: {g('identity.edrpou')} · КВЕД: {g('identity.kved_main')}",
        f"Засновник/власники: {g('identity.founder_uk') or g('identity.ownership_structure')}",
        f"Адреса: {g('contacts.legal_address_uk')} ({g('contacts.legal_address_en')})",
        f"Керівник: {g('contacts.head.full_name_uk')}, {g('contacts.head.position_uk')}",
        f"Контакт: {g('contacts.email_official')} {g('contacts.phone')}",
        f"PIC (ЄС): {g('international_ids.eu_pic')}",
        f"Персонал: {g('staff.total') or g('sme_status.employees')} осіб",
        f"Оборот за роками: {g('finance.annual_turnover')}",
        f"Спроможність співфінансування: {g('finance.cofinancing_capacity')}",
    ]
    if org.get("entity_type") == "communal":
        lines += [
            f"Обслуговуване населення: {g('operations.service_area_population')}",
            f"Відходів на рік, тонн: {g('operations.waste_collected_tons_year')}",
            f"Частка сортування, %: {g('operations.waste_sorted_pct')}",
            f"Матеріальна база: {g('assets.vehicles')} | полігон: {g('assets.landfill')}",
            f"Дозволи: {g('permits.waste_management_license')}",
            f"Ключові проблеми: {g('operations.key_problems_uk')}",
            f"Стратегічний контекст: {g('strategy.hromada_development_strategy')}; "
            f"{g('strategy.waste_management_plan')}; {g('strategy.alignment_eu')}",
        ]
    else:
        lines += [
            f"Статус МСП: {g('sme_status.category')}, працівників {g('sme_status.employees')}, "
            f"оборот {g('sme_status.annual_turnover_eur')} EUR",
            f"Продукція: {g('operations.main_products_uk')}",
            f"Потужності та обладнання: {g('operations.production_capacity')} {g('operations.equipment')}",
            f"Експорт: {g('finance.export_share_pct')}% → {g('finance.export_markets')}",
        ]
    exp = org.get("experience", {}) or {}
    projects = [p for p in (exp.get("projects") or []) if not _is_empty(p)]
    if projects:
        lines.append("Досвід проєктів: " + "; ".join(
            f"{p.get('title_uk', '')} ({p.get('donor', '')}, {p.get('budget', '')})" for p in projects))
    pipeline = [p for p in (org.get("project_pipeline") or []) if not _is_empty(p)]
    if pipeline:
        lines.append("Готові ідеї проєктів: " + "; ".join(
            f"[{p.get('code', '')}] {p.get('title_uk', '')} — {p.get('objective_uk', '')} "
            f"(бюджет {p.get('budget_total_eur', 0)} EUR)" for p in pipeline))
    desc = g("boilerplate.org_description_uk_500")
    if desc:
        lines.append(f"Опис організації: {desc}")
    return "\n".join(x for x in lines if x.strip().rstrip(":"))[:max_len]
