"""Відсів: лишаємо тільки те, на що реально можна подати заявку.

Три правила, які задав користувач:

1. **Новини про гранти — не можливості.** Якщо запис розповідає, що хтось уже
   *отримав* грант, переміг у конкурсі чи підписав меморандум — це не конкурс,
   і такий запис ховаємо.
2. **Без першоджерела новина не має цінності.** Якщо запис прийшов із новинної
   стрічки й агент не зміг знайти сторінку донора (`apply_url`) — ховаємо.
3. **Протермінованого не показуємо.** Дедлайн виймаємо з тексту оголошення
   («КОЛИ: до 02.05.2023», «Заявки приймаються до 15 листопада 2026»,
   «Deadline: 30 June 2026») і, якщо дата вже минула, запис ховаємо.

Записи не видаляються з бази — їм проставляється `actionable = 0` і
`hide_reason`, тож завжди можна подивитись, що саме відсіялось і чому.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

# ─────────────────────────── дедлайни ────────────────────────────

MONTHS = {
    "січ": 1, "лют": 2, "бер": 3, "квіт": 4, "трав": 5, "черв": 6, "лип": 7,
    "серп": 8, "вер": 9, "жовт": 10, "listopad": 11, "лист": 11, "груд": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# контекст, біля якого шукаємо дату подачі
DEADLINE_CUES = re.compile(
    r"(дедлайн|кінцевий[ _]термін|останній день|термін(и)? подач|термін подання|"
    r"заявки приймаються|приймаються заявки|прийом заявок|подання заявок|подача заявок|"
    r"подати заявку до|подати документи до|реєстрація (?:триває )?до|коли:|"
    r"triває до|конкурс триває до|аплікації до|"
    r"deadline|closing date|applications? (?:are )?(?:accepted|open|received) "
    r"(?:until|till|by)|submission (?:deadline|date)|submit(?:ted)? by|apply by)", re.I)

# дати поряд із цими словами — НЕ дедлайн подачі заявки
NOT_A_DEADLINE = re.compile(
    r"(обговоренн|консультац|коментар|опитуванн|звітн|сплат|до сплати|"
    r"цілей до|до \d{4} року|public consultation|comments? by)", re.I)

DATE_DMY = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")
DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DATE_WORD_UA = re.compile(
    r"\b(\d{1,2})\s+([а-яіїєґa-z]{3,12})\.?\s*(\d{4})?", re.I)
DATE_WORD_EN = re.compile(
    r"\b(\d{1,2})\s+([a-z]{3,12})\.?,?\s*(\d{4})?\b|\b([a-z]{3,12})\.?\s+(\d{1,2}),?\s*(\d{4})?\b", re.I)


def _mk(y: int, m: int, d: int, today: date) -> date | None:
    try:
        out = date(y, m, d)
    except ValueError:
        return None
    if not (today.year - 8 <= out.year <= today.year + 8):
        return None
    return out


def _dates_in(chunk: str, today: date, base_year: int) -> list[tuple[date, bool]]:
    """Дати у фрагменті тексту: (дата, чи був рік вказаний явно).

    Дати без року прив'язуємо до `base_year` — це рік публікації оголошення,
    а не поточний. Інакше архівний пост «Заявки приймаються з 20 червня по
    20 липня 2025» перетворюється на «20 червня 2027» і протермінований
    конкурс виглядає як відкритий.
    """
    found: list[tuple[date, bool]] = []
    for m in DATE_ISO.finditer(chunk):
        d = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)), today)
        if d:
            found.append((d, True))
    for m in DATE_DMY.finditer(chunk):
        d = _mk(int(m.group(3)), int(m.group(2)), int(m.group(1)), today)
        if d:
            found.append((d, True))
    for m in DATE_WORD_UA.finditer(chunk):
        day, word, year = m.group(1), (m.group(2) or "").lower(), m.group(3)
        mon = next((v for k, v in MONTHS.items() if word.startswith(k)), None)
        if not mon:
            continue
        d = _mk(int(year) if year else base_year, mon, int(day), today)
        if d:
            found.append((d, bool(year)))
    return found


def extract_deadline(*texts: str, today: date | None = None,
                     published: str | None = None) -> str | None:
    """Шукає дату закінчення прийому заявок. Повертає ISO-дату або None.

    `published` — дата публікації оголошення (ISO). Саме до неї прив'язуються
    дати без року; якщо її немає, беремо поточний рік.
    """
    today = today or datetime.now(timezone.utc).date()
    base_year = today.year
    if published:
        try:
            base_year = datetime.fromisoformat(
                str(published).replace("Z", "+00:00")).year
        except ValueError:
            pass

    blob = " ".join(t for t in texts if t)
    if not blob:
        return None
    blob = re.sub(r"\s+", " ", blob)[:6000]

    # дати поряд зі словами про подачу; контекст перевіряємо з обох боків,
    # щоб не сплутати з громадським обговоренням, звітністю чи «цілей до 2050»
    near: list[tuple[date, bool]] = []
    low = blob.lower()
    for m in DEADLINE_CUES.finditer(low):
        window = blob[max(0, m.start() - 60): m.start() + 90]
        if NOT_A_DEADLINE.search(window):
            continue
        near += _dates_in(blob[m.start(): m.start() + 110], today, base_year)
    if not near:
        return None

    # якщо хоч десь рік написано явно — довіряємо лише таким датам
    explicit = [d for d, has_year in near if has_year]
    pool = explicit or [d for d, _ in near]
    # у діапазоні «з 20 червня по 20 липня» дедлайн — пізніша дата
    return max(pool).isoformat()


# ───────────────────── новина чи справжній конкурс ─────────────────────

# «уже сталося» — про це читати цікаво, подати заявку неможливо
RETRO = re.compile(
    r"(отрима(в|ла|ли|є|ють|но)|вигра(в|ла|ли)|перемо(га|жц|жни)|переміг|"
    r"посі(в|ла)\s+\w*\s*місце|здобу(в|ла|ли)\s+(грант|перемог)|стал(а|и|о)\s+переможц|"
    r"підбито підсумки|підсумки конкурсу|завершився прийом|завершено прийом|прийом заявок завершен|"
    r"вручили|вручення|урочисто|підписа(ли|но) меморандум|відкри(ли|то) (?:новий|оновлен)|"
    r"збудува(ли|ло)|реалізовано проєкт|звіт про|дякуємо за участь|"
    r"was awarded|has been awarded|won the|winners? (?:of|announced)|has received|"
    r"signed a memorandum|results of the competition)", re.I)

# історії успіху та репортажі — теж не конкурс
STORY = re.compile(
    r"(історія успіху|істори[ія] про|: як |як \w+ (?:розвива|відкри|створ|побудува|змінив|заснува)|"
    r"шлях від|розповідь про|репортаж|інтерв'ю|success story|how \w+ (?:built|turned|started))", re.I)

# «донор щось зробив» — теж новина, а не відкритий конкурс
DONOR_NEWS = re.compile(
    r"(нада(є|ють|в|ла) (?:гарант|кредит|позик|підтримк)|виділ(ив|ила|яє|яють|ено)|"
    r"інвесту(є|ють)|профінансу(є|ють|вав)|спряму(є|ють)|переда(в|ли|но)|"
    r"підписа(в|ли|но) (?:угоду|меморандум|договір)|проголосуйте|голосуванн[яі]|"
    r"receives?|will receive|provides? (?:a )?guarantee|allocat(es|ed)|signs? (?:a )?(?:deal|agreement))",
    re.I)

# події: вебінари, тренінги, форуми — корисно, але заявку на грант там не подаси
EVENT = re.compile(
    r"(вебінар|воркшоп|тренінг|семінар|конференці|форум|саміт|хакатон|"
    r"інформаційн(а|ий) (?:сесі|день|захід)|відбудеться|запрошуємо на (?:зустріч|подію)|"
    r"webinar|workshop|training session|conference|info ?session|summit)", re.I)

# вакансії, тендери на працівників, навчання без фінансування
VACANCY = re.compile(
    r"(вакансі|запрошуємо на роботу|шукаємо (?:фахів|координат|менеджер|спеціаліс)|"
    r"оголошення про вакансі|консультант/к[аи] з|job opening|we are hiring|"
    r"call for (?:experts?|consultants?|cv)|terms of reference for an? (?:consultant|expert))", re.I)

# ознаки живого конкурсу — перекривають «ретроспективні» слова в заголовку
OPEN_CALL = re.compile(
    r"(прийом заявок|заявки приймаються|подати заявку|подача заявок|подання заявок|"
    r"оголоше(но|ний) конкурс|оголошує конкурс|конкурс триває|триває прийом|"
    r"запрошує(мо)? (?:до участі|взяти участь|подавати)|аплікаційна форма|заповнити форму|"
    r"грантова програма|умови участі|хто може подати|критерії відбору|"
    r"call for (?:proposals|applications|projects)|applications? (?:are )?open|"
    r"submit your application|how to apply|eligibility criteria|apply now)", re.I)

# ознаки того, що це взагалі можливість отримати гроші, а не стаття
FUNDING_SIGNS = re.compile(
    r"(грант|конкурс|заявк|аплікац|фінансуванн|співфінансуванн|субсид|субвенц|дотац|"
    r"стипенді|тендер|закупівл|програма підтримки|підтримк[аи] проєкт|фонд оголо|"
    r"конкурсн|відбір проєкт|прийом пропозиц|пільгов(ий|е) кредит|"
    r"call for (?:proposals|applications|tenders|projects)|funding|grant|tender|"
    r"subsid|scholarship|fellowship|procurement|financing|award)", re.I)

# джерела, де трапляються саме новини, а не оголошення конкурсів
NEWS_SOURCES = {"gnews_ua", "gnews_en", "decentralization", "hromady",
                "prostir_all", "websearch_ua", "websearch_eu"}

# структуровані портали конкурсів — там новин не буває
CALL_PORTALS = {"eu_ft_portal", "ted", "worldbank"}

REASON_TEXT = {
    "news": "новина про вже виданий грант, а не відкритий конкурс",
    "vacancy": "вакансія або пошук експерта, а не грант",
    "no_source": "новина без знайденого першоджерела — немає куди подавати заявку",
    "expired": "термін подачі заявок минув",
    "not_a_call": "стаття без ознак конкурсу чи фінансування",
    "event": "подія (вебінар, тренінг, форум), а не конкурс",
    "stale": "оголошення старше за рік, а дедлайн не підтверджено",
}

# джерела, де запис без дедлайну — нормально (проєктний пайплайн, не конкурс із датою)
NO_DEADLINE_OK = {"worldbank", "eu_ft_portal"}
STALE_AFTER_DAYS = 365


def screen(item: dict[str, Any], today: date | None = None) -> tuple[bool, str, str | None]:
    """Вирішує, чи показувати запис.

    Повертає `(показувати, причина_приховування, знайдений_дедлайн)`.
    """
    today = today or datetime.now(timezone.utc).date()
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    body = item.get("body") or ""
    source_id = item.get("source_id") or ""
    apply_url = (item.get("apply_url") or "").strip()

    # 1) дедлайн: беремо збережений або виймаємо з тексту
    deadline = (item.get("deadline_at") or "").strip() or None
    found = extract_deadline(title, summary, body, today=today,
                             published=item.get("published_at"))
    if not deadline and found:
        deadline = found
    if deadline:
        try:
            dl = datetime.fromisoformat(deadline.replace("Z", "+00:00")).date()
            if dl < today:
                return False, "expired", deadline
        except ValueError:
            pass

    # старе оголошення без підтвердженого дедлайну — майже напевно вже закрите
    if not deadline and source_id not in NO_DEADLINE_OK:
        published = (item.get("published_at") or "").strip()
        if published:
            try:
                pub = datetime.fromisoformat(published.replace("Z", "+00:00")).date()
                if (today - pub).days > STALE_AFTER_DAYS:
                    return False, "stale", None
            except ValueError:
                pass

    blob = f"{title} {summary} {body}"
    if VACANCY.search(blob[:900]):
        return False, "vacancy", deadline

    if source_id not in CALL_PORTALS:
        open_call = bool(OPEN_CALL.search(blob))
        if not FUNDING_SIGNS.search(f"{title} {summary}"[:700]):
            return False, "not_a_call", deadline
        if (RETRO.search(title) or STORY.search(title)) and not open_call:
            return False, "news", deadline
        if EVENT.search(title) and not apply_url and not re.search(
                r"(грант|конкурс|заявк|call for|grant)", title, re.I):
            return False, "event", deadline
        if DONOR_NEWS.search(title) and not open_call and not apply_url:
            return False, "news", deadline
        if source_id in NEWS_SOURCES:
            # новина корисна лише тоді, коли знайдено сторінку донора
            if not apply_url:
                return False, "no_source", deadline
            if not open_call and RETRO.search(blob[:600]):
                return False, "news", deadline

    return True, "", deadline


def screen_all(db, fetch: int = 0, workers: int = 8, redate: bool = False) -> dict[str, int]:
    """Перевіряє всю базу.

    `fetch`  — скільки сторінок довантажити, щоб знайти дедлайн у тексті.
    `redate` — перерахувати дедлайни з тексту для всіх нествруктурованих джерел
               (разова чистка хибних дат на кшталт «до 8 жовтня 2026» з абзацу
               про громадське обговорення). Портали конкурсів не чіпаємо —
               там дата приходить структуровано.
    """
    rows = [dict(r) for r in db.conn.execute(
        "SELECT uid, title, summary, source_id, url, apply_url, deadline_at, "
        "published_at, resolved_at, score FROM opportunities ORDER BY score DESC")]

    bodies: dict[str, str] = {}
    if fetch:
        bodies = _fetch_bodies(
            [r for r in rows if not (r.get("deadline_at") or "").strip()][:fetch], workers)

    counts = {"shown": 0, "news": 0, "vacancy": 0, "no_source": 0, "expired": 0,
              "not_a_call": 0, "event": 0, "stale": 0, "deadlines": 0, "cleared": 0}
    for r in rows:
        r["body"] = bodies.get(r["uid"], "")
        if redate and r.get("source_id") not in CALL_PORTALS:
            fresh = extract_deadline(r.get("title") or "", r.get("summary") or "",
                                     r["body"], published=r.get("published_at"))
            # дати, знайдені на самій сторінці оголошення (крок resolve),
            # не чіпаємо — у короткому описі їх просто немає
            if fresh:
                r["deadline_at"] = fresh
                db.conn.execute("UPDATE opportunities SET deadline_at=? WHERE uid=?",
                                (fresh, r["uid"]))
            elif r.get("deadline_at") and not r.get("resolved_at"):
                counts["cleared"] += 1
                r["deadline_at"] = ""
                db.conn.execute("UPDATE opportunities SET deadline_at=NULL WHERE uid=?",
                                (r["uid"],))
        ok, reason, deadline = screen(r)
        if deadline and deadline != (r.get("deadline_at") or ""):
            counts["deadlines"] += 1
        db.conn.execute(
            "UPDATE opportunities SET actionable=?, hide_reason=?, deadline_at=COALESCE(?, deadline_at) "
            "WHERE uid=?",
            (1 if ok else 0, reason, deadline, r["uid"]))
        counts["shown" if ok else reason] += 1
    db.conn.commit()
    return counts


def _fetch_bodies(rows: list[dict[str, Any]], workers: int = 8) -> dict[str, str]:
    """Довантажує сторінки оголошень, щоб дістати дедлайн із тексту."""
    from concurrent.futures import ThreadPoolExecutor

    import requests

    from .resolve import HEADERS, _body_text

    def one(row: dict[str, Any]) -> tuple[str, str]:
        url = row.get("apply_url") or row.get("url") or ""
        if not url.startswith("http") or "news.google.com" in url:
            return row["uid"], ""
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding or "utf-8"
            return row["uid"], _body_text(r.text)[:6000]
        except Exception:
            return row["uid"], ""

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return {uid: text for uid, text in ex.map(one, rows) if text}
