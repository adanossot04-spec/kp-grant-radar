"""Чернетка заявки: агент бере можливість з бази + пам'ять організації
і сам заповнює все, що може (команда: python -m grant_radar draft <uid>).

Без LLM — заповнює адміністративну частину, чеклісти, бюджет, перелік документів.
З безкоштовним LLM-ключем — ще й пише змістовні розділи (проблема, мета,
діяльність, результати, сталість) українською та англійською.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config, memory
from .classify import LABEL
from .db import Database
from .llm import LLMAnalyzer

log = logging.getLogger(__name__)

ADMIN_FIELDS_COMMON = [
    ("Повна назва (UA)", "identity.legal_name_uk"),
    ("Повна назва (EN)", "identity.legal_name_en"),
    ("Організаційно-правова форма", "identity.legal_form_en"),
    ("Код ЄДРПОУ", "identity.edrpou"),
    ("Дата реєстрації", "identity.registration_date"),
    ("КВЕД (основний)", "identity.kved_main"),
    ("Юридична адреса (UA)", "contacts.legal_address_uk"),
    ("Legal address (EN)", "contacts.legal_address_en"),
    ("Регіон / NUTS", "contacts.region_nuts"),
    ("Телефон", "contacts.phone"),
    ("Офіційний email", "contacts.email_official"),
    ("Вебсайт", "identity.website"),
    ("Керівник", "contacts.head.full_name_uk"),
    ("Head of organisation (EN)", "contacts.head.full_name_en"),
    ("Посада керівника", "contacts.head.position_en"),
    ("Контактна особа проєкту", "contacts.project_contact.full_name_uk"),
    ("Email контактної особи", "contacts.project_contact.email"),
    ("PIC (портал ЄС)", "international_ids.eu_pic"),
    ("LEI / UEI", "international_ids.lei"),
    ("Банк", "banking.bank_name_en"),
    ("IBAN (EUR)", "banking.iban_eur"),
    ("IBAN (UAH)", "banking.iban_uah"),
    ("SWIFT", "banking.swift"),
]
ADMIN_FIELDS_COMMUNAL = [
    ("Засновник", "identity.founder_uk"),
    ("Громада", "contacts.hromada"),
    ("Працівників", "staff.total"),
    ("Обслуговуване населення", "operations.service_area_population"),
    ("Відходів, т/рік", "operations.waste_collected_tons_year"),
    ("Ліцензія на поводження з відходами", "permits.waste_management_license"),
]
ADMIN_FIELDS_PRIVATE = [
    ("Кінцеві бенефіціарні власники", "identity.ultimate_beneficial_owners"),
    ("Категорія МСП", "sme_status.category"),
    ("Працівників", "sme_status.employees"),
    ("Річний оборот, EUR", "sme_status.annual_turnover_eur"),
    ("Сертифікати", "operations.certificates"),
]
DOC_LABELS = {
    "statute": "Статут", "edr_extract": "Витяг з ЄДР", "founder_decision": "Рішення засновника",
    "financial_reports": "Фінансова звітність", "director_appointment": "Наказ про призначення керівника",
    "bank_details_letter": "Довідка з банку", "tax_status_certificate": "Довідка про податковий статус",
    "council_cofinancing_decision": "Рішення ради про співфінансування",
    "ubo_structure": "Структура власності (UBO)", "other": "Інше",
}

NARRATIVE_SYSTEM = """Ти — досвідчений грант-менеджер, який пише заявки для українських
організацій на фінансування ЄС та міжнародних донорів. Пишеш конкретно, з цифрами з
наданого досьє, без води та без вигаданих фактів. Якщо даних бракує — пишеш
[ПОТРЕБУЄ УТОЧНЕННЯ: що саме]. Відповідь — у форматі Markdown."""

NARRATIVE_USER = """ДОСЬЄ ОРГАНІЗАЦІЇ:
{dossier}

МОЖЛИВІСТЬ ФІНАНСУВАННЯ:
Назва: {title}
Програма: {programme}
Донор/джерело: {source}
Дедлайн: {deadline}
Опис: {summary}
Посилання: {url}

Напиши чернетку змістовної частини заявки. Структура (саме такі заголовки):

### 1. Обґрунтування проблеми (UA)
### 2. Мета та завдання проєкту (UA)
### 3. Основні заходи (UA, списком з орієнтовними термінами)
### 4. Очікувані результати та індикатори (UA, з цифрами)
### 5. Цільові групи та бенефіціари (UA)
### 6. Сталість після завершення фінансування (UA)
### 7. Відповідність пріоритетам донора та політикам ЄС (UA)
### 8. Project summary (EN, 1200-1500 characters)
### 9. Ризики та заходи їх мінімізації (UA, таблиця)

Спирайся на реальні цифри з досьє. Там, де даних немає, явно познач [ПОТРЕБУЄ УТОЧНЕННЯ]."""


def _slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "-", text.lower(), flags=re.UNICODE).strip("-")
    return s[:n] or "draft"


def _fmt(value: Any) -> str:
    if value in (None, "", 0, [], {}, False):
        return "⚠️ **не заповнено в memory.yaml**"
    if isinstance(value, (list, dict)):
        return str(value)
    return str(value)


def _best_pipeline_idea(org: dict[str, Any], opp: dict[str, Any]) -> dict[str, Any] | None:
    ideas = [p for p in (org.get("project_pipeline") or []) if p.get("title_uk")]
    if not ideas:
        return None
    text = f"{opp.get('title', '')} {opp.get('summary', '')}".lower()
    best, best_hits = None, -1
    for idea in ideas:
        words = re.findall(r"\w{5,}", f"{idea.get('title_uk', '')} {idea.get('objective_uk', '')}".lower())
        hits = sum(1 for w in set(words) if w in text)
        if hits > best_hits:
            best, best_hits = idea, hits
    return best


def build(uid: str, db: Database | None = None, org_id: str | None = None,
          use_llm: bool = True) -> Path:
    db = db or Database(config.DB_PATH)
    opp = db.get(uid)
    if not opp:
        raise SystemExit(f"Можливість {uid} не знайдено в базі")

    org = memory.pick(opp.get("beneficiary") or "unknown", org_id)
    if not org:
        raise SystemExit("У config/memory.yaml немає активних організацій — заповніть файл")

    comp = memory.completeness(org)
    dossier = memory.dossier_text(org)
    is_communal = org.get("entity_type") == "communal"
    fields = ADMIN_FIELDS_COMMON + (ADMIN_FIELDS_COMMUNAL if is_communal else ADMIN_FIELDS_PRIVATE)

    dl = opp.get("deadline_at") or "не вказано"
    days = opp.get("days_left")
    lines: list[str] = [
        f"# Чернетка заявки — {opp['title']}",
        "",
        f"> Згенеровано агентом «Грант-радар» {datetime.now().strftime('%d.%m.%Y %H:%M')} · "
        f"заповненість пам'яті: **{comp['percent']}%**",
        "",
        "## 0. Паспорт можливості",
        "",
        "| Параметр | Значення |",
        "|---|---|",
        f"| Джерело | {opp['source_name']} |",
        f"| Програма | {opp.get('programme') or '—'} |",
        f"| Ідентифікатор | {opp.get('identifier') or '—'} |",
        f"| Статус | {opp.get('status') or '—'} |",
        f"| Дедлайн | {dl}{f' (залишилось {days} дн.)' if days is not None else ''} |",
        f"| Релевантність | {opp.get('score')}/100 |",
        f"| Тип заявника | {LABEL.get(opp.get('beneficiary', 'unknown'), '—')} |",
        f"| Посилання | {opp['url']} |",
        "",
        f"**Заявник:** {org.get('identity', {}).get('legal_name_uk') or org.get('id')} "
        f"({'комунальне підприємство' if is_communal else 'приватне підприємство'})",
        "",
        "## 1. Адміністративні дані заявника (автозаповнення з пам'яті)",
        "",
        "| Поле заявки | Значення |",
        "|---|---|",
    ]
    for label, path in fields:
        lines.append(f"| {label} | {_fmt(memory.get_path(org, path))} |")

    # ── ідея проєкту ────────────────────────────────────────────────────────
    idea = _best_pipeline_idea(org, opp)
    lines += ["", "## 2. Проєктна ідея з вашого пайплайну", ""]
    if idea:
        lines += [
            f"**[{idea.get('code', '')}] {idea.get('title_uk', '')}**", "",
            f"- Проблема: {_fmt(idea.get('problem_uk'))}",
            f"- Мета: {_fmt(idea.get('objective_uk'))}",
            f"- Заходи: {_fmt(idea.get('activities_uk'))}",
            f"- Результати: {_fmt(idea.get('expected_results_uk'))}",
            f"- Індикатори: {_fmt(idea.get('indicators'))}",
            f"- Бюджет: {idea.get('budget_total_eur', 0)} EUR, "
            f"співфінансування {idea.get('cofinancing_eur', 0)} EUR, "
            f"тривалість {idea.get('duration_months', 0)} міс.",
            f"- Готовність: {_fmt(idea.get('readiness'))}",
        ]
    else:
        lines.append("⚠️ У `memory.yaml` ще немає жодної проєктної ідеї (`project_pipeline`). "
                     "Додайте 2–3 ідеї — агент автоматично підбиратиме їх під конкурси.")

    # ── змістовна частина ───────────────────────────────────────────────────
    analyzer = LLMAnalyzer(dossier)
    lines += ["", "## 3. Змістовна частина заявки", ""]
    if use_llm and analyzer.enabled:
        narrative = analyzer.chat(
            NARRATIVE_SYSTEM,
            NARRATIVE_USER.format(
                dossier=dossier, title=opp["title"], programme=opp.get("programme") or "—",
                source=opp["source_name"], deadline=dl,
                summary=(opp.get("summary") or "")[:3000], url=opp["url"]),
            max_tokens=2600)
        lines.append(narrative or "⚠️ LLM не відповів — спробуйте ще раз або заповніть вручну.")
        lines.insert(len(lines) - 1, f"*Згенеровано моделлю `{analyzer.model}` ({analyzer.provider}).*\n")
    else:
        lines += [
            "ℹ️ LLM-ключ не налаштовано — нижче структура для ручного заповнення "
            "(додайте безкоштовний ключ Groq або Gemini, і агент писатиме ці розділи сам).", "",
            "### 1. Обґрунтування проблеми",
            f"{_fmt(memory.get_path(org, 'operations.key_problems_uk'))}", "",
            "### 2. Мета та завдання", "", "### 3. Основні заходи", "",
            "### 4. Очікувані результати та індикатори", "", "### 5. Цільові групи", "",
            "### 6. Сталість після проєкту",
            f"{_fmt(memory.get_path(org, 'boilerplate.sustainability_after_project_en'))}", "",
            "### 7. Відповідність політикам",
            f"{_fmt(memory.get_path(org, 'strategy.alignment_eu'))}", "",
        ]

    # ── бюджет ──────────────────────────────────────────────────────────────
    cof = memory.get_path(org, "finance.cofinancing_capacity") or {}
    lines += [
        "", "## 4. Бюджет (скелет)", "",
        "| Стаття | Сума, EUR | Грант | Співфінансування |",
        "|---|---|---|---|",
        "| Обладнання / техніка | | | |",
        "| Будівельні роботи | | | |",
        "| Послуги та експертиза | | | |",
        "| Персонал проєкту | | | |",
        "| Комунікація та видимість | | | |",
        "| Адміністративні витрати | | | |",
        "| **Разом** | | | |",
        "",
        f"Доступне співфінансування за пам'яттю: {_fmt(cof)}",
    ]

    # ── документи ───────────────────────────────────────────────────────────
    lines += ["", "## 5. Пакет документів", "", "| Документ | Статус |", "|---|---|"]
    for key, label in DOC_LABELS.items():
        val = memory.get_path(org, f"documents.{key}")
        lines.append(f"| {label} | {'✅ ' + str(val) if val else '⚠️ немає в memory.yaml'} |")

    # ── чеклист подачі ──────────────────────────────────────────────────────
    lines += [
        "", "## 6. Чекліст перед подачею", "",
        "- [ ] Перевірено умови прийнятності (eligibility) в офіційному документі конкурсу",
        "- [ ] Підтверджено, що тип організації відповідає вимогам заявника",
        "- [ ] Знайдено партнерів (якщо програма вимагає консорціум)",
        "- [ ] Отримано рішення засновника/ради про співфінансування" if is_communal
        else "- [ ] Підтверджено наявність власних коштів на співфінансування",
        "- [ ] Зареєстровано/оновлено профіль у системі донора (PIC, UNGM тощо)",
        "- [ ] Підготовлено переклади документів англійською",
        "- [ ] Узгоджено бюджет з бухгалтерією",
        "- [ ] Заявку подано не пізніше ніж за 24 год до дедлайну",
    ]

    # ── прогалини пам'яті ───────────────────────────────────────────────────
    if comp["critical_missing"]:
        lines += ["", "## 7. Що терміново додати в `config/memory.yaml`", ""]
        lines += [f"- `{p}`" for p in comp["critical_missing"]]

    out_dir = config.DATA_DIR / "drafts"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{uid}-{_slug(opp['title'])}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
