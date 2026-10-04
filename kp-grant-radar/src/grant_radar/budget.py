"""Розпізнавання суми фінансування та розподіл за діапазонами бюджету.

Ідея: з сирого поля `budget` (у кожного джерела свій формат) та з тексту
оголошення дістати орієнтовну суму **на один проєкт** у євро, щоб можна було
фільтрувати стрічку за діапазонами:

    до 100 тис. €   |   100–500 тис. €   |   понад 500 тис. €

Курси перерахунку приблизні (оновіть за потреби) — для фільтра цього досить.
"""
from __future__ import annotations

import json
import re

# ─────────────────────────── діапазони ───────────────────────────
SMALL_MAX = 100_000      # до 100 тис. €
MID_MAX = 500_000        # 100–500 тис. €

BAND_ORDER = ["s", "m", "l", "unknown"]
BAND_LABEL = {
    "s": "💶 до 100 тис. €",
    "m": "💶 100–500 тис. €",
    "l": "💶 понад 500 тис. €",
    "unknown": "💶 суму не вказано",
}
BAND_SHORT = {
    "s": "до 100 тис. €",
    "m": "100–500 тис. €",
    "l": "понад 500 тис. €",
    "unknown": "сума н/д",
}

# ─────────────────────────── курси ───────────────────────────
RATES = {          # у євро за одиницю валюти
    "EUR": 1.0,
    "USD": 0.92,
    "UAH": 0.022,
    "PLN": 0.23,
    "GBP": 1.17,
}

_CUR_WORDS = {
    "eur": "EUR", "euro": "EUR", "euros": "EUR", "€": "EUR",
    "євро": "EUR", "eвро": "EUR",
    "usd": "USD", "$": "USD", "dollar": "USD", "dollars": "USD", "долар": "USD",
    "uah": "UAH", "грн": "UAH", "гривень": "UAH", "гривні": "UAH", "₴": "UAH",
    "pln": "PLN", "zł": "PLN", "злотих": "PLN", "gbp": "GBP", "£": "GBP",
    "грив": "UAH", "дола": "UAH" if False else "USD",
}

_MULT = [
    (r"(?:млрд|billion|bn|bln)", 1_000_000_000),
    (r"(?:млн|million|mln|m\b)", 1_000_000),
    (r"(?:тис\.?|thousand|k\b)", 1_000),
]

_NUM = r"\d{1,3}(?:[ \u00a0.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"


def _to_float(raw: str) -> float | None:
    """'1 234 567,50' / '1,234,567.50' / '1.5' → float."""
    s = raw.strip().replace("\u00a0", " ")
    s = re.sub(r"(?<=\d)[ ](?=\d{3}\b)", "", s)          # пробіли-роздільники тисяч
    if re.search(r"[.,]\d{3}\b", s) and not re.search(r"[.,]\d{1,2}$", s):
        s = re.sub(r"[.,](?=\d{3}\b)", "", s)            # 1,234,567 / 1.234.567
    s = s.replace(",", ".")
    if s.count(".") > 1:
        head, _, tail = s.rpartition(".")
        s = head.replace(".", "") + "." + tail
    try:
        return float(s)
    except ValueError:
        return None


_CUR_RE = (r"€|\$|₴|£|"
           r"\b(?:eur|euros?|usd|uah|pln|gbp|dollars?|євро|грн|гривень|гривні|грив\w*|"
           r"долар\w*|злотих)\b")

_MULT_RE = (r"(?:млрд|млн|тис\w*|мільйон\w*|мільярд\w*|billion|bn|bln|million|mln|"
            r"thousand|[kmb])\.?(?![a-zа-яіїєґ'\u2019])")


def _scan_text(text: str) -> list[float]:
    """Шукає в тексті суми грошей і повертає їх у євро."""
    out: list[float] = []
    low = text.lower()
    pattern = re.compile(
        r"(?P<cur1>" + _CUR_RE + r")?\s*"
        r"(?P<num>" + _NUM + r")\s*"
        r"(?P<mult>" + _MULT_RE + r")?\s*"
        r"(?P<cur2>" + _CUR_RE + r")?",
        re.IGNORECASE,
    )
    for m in pattern.finditer(low):
        cur_raw = (m.group("cur1") or m.group("cur2") or "").strip().lower()
        if not cur_raw:
            continue                                     # число без валюти ігноруємо
        num_raw = m.group("num") or ""
        val = _to_float(num_raw)
        if val is None:
            continue
        mult_raw = (m.group("mult") or "").strip().lower().rstrip(".")
        if mult_raw:
            if mult_raw.startswith(("млрд", "мільярд", "billion", "bn", "bln")) or mult_raw == "b":
                val *= 1_000_000_000
            elif mult_raw.startswith(("млн", "мільйон", "million", "mln")) or mult_raw == "m":
                val *= 1_000_000
            elif mult_raw.startswith(("тис", "thousand")) or mult_raw == "k":
                val *= 1_000
        else:
            # «2027 EUR» у тексті — це рік, а не сума
            if 1900 <= val <= 2100 and not re.search(r"[ .,\u00a0]", num_raw):
                continue
        cur = (_CUR_WORDS.get(cur_raw) or _CUR_WORDS.get(cur_raw.rstrip("s"))
               or _CUR_WORDS.get(cur_raw[:4]) or _CUR_WORDS.get(cur_raw[:3]) or "EUR")
        eur = val * RATES.get(cur, 1.0)
        if 500 <= eur <= 50_000_000_000:                 # відсікаємо дрібницю і сміття
            out.append(eur)
    return out


def _from_sedia_json(raw: str) -> float | None:
    """Бюджет порталу Funding & Tenders: беремо максимальний внесок на один грант."""
    try:
        data = json.loads(raw)
    except Exception:
        # портал часто віддає обрізаний JSON — дістаємо числа регулярками
        per_grant = [float(x) for x in re.findall(r'"maxContribution"\s*:\s*(\d+)', raw)]
        per_grant = [v for v in per_grant if v > 0]
        if per_grant:
            return max(per_grant)
        years = [float(x) for x in re.findall(r'"\d{4}"\s*:\s*"?(\d+)"?', raw)]
        years = [v for v in years if v > 0]
        grants = [int(x) for x in re.findall(r'"expectedGrants"\s*:\s*(\d+)', raw)]
        if years:
            total = max(years)
            n = max(grants) if grants and max(grants) > 0 else 0
            return total / n if n else total
        return None
    actions: list[dict] = []
    for lst in (data.get("budgetTopicActionMap") or {}).values():
        if isinstance(lst, list):
            actions += [a for a in lst if isinstance(a, dict)]
    if not actions:
        return None
    per_grant = [float(a.get("maxContribution") or 0) for a in actions]
    per_grant = [v for v in per_grant if v > 0]
    if per_grant:
        return max(per_grant)
    # запасний варіант: загальний бюджет / очікувана кількість грантів
    totals, grants = 0.0, 0
    for a in actions:
        for v in (a.get("budgetYearMap") or {}).values():
            try:
                totals += float(str(v).replace(" ", "") or 0)
            except ValueError:
                pass
        try:
            grants += int(a.get("expectedGrants") or 0)
        except (TypeError, ValueError):
            pass
    if totals <= 0:
        return None
    return totals / grants if grants > 0 else totals


def parse(budget_raw: str | None, text: str = "", currency: str = "EUR") -> int | None:
    """Орієнтовна сума фінансування на проєкт у євро (None — не визначено)."""
    raw = (budget_raw or "").strip()

    if raw.startswith("{"):
        val = _from_sedia_json(raw)
        if val:
            return int(val)

    if raw and re.fullmatch(r"[\d \u00a0.,]+", raw):      # «750,000,000» (World Bank, USD)
        val = _to_float(raw)
        if val and val > 0:
            return int(val * RATES.get(currency.upper(), 1.0))

    found = _scan_text(raw) if raw else []
    if not found and text:
        found = _scan_text(text[:2500])
    if found:
        return int(max(found))
    return None


def band(amount_eur: int | None) -> str:
    """Діапазон бюджету: s (<100k) | m (100–500k) | l (>500k) | unknown."""
    if not amount_eur or amount_eur <= 0:
        return "unknown"
    if amount_eur < SMALL_MAX:
        return "s"
    if amount_eur <= MID_MAX:
        return "m"
    return "l"


def human(amount_eur: int | None) -> str:
    """Коротке подання суми: 85 тис. € / 1,2 млн € / 3,5 млрд €."""
    if not amount_eur or amount_eur <= 0:
        return ""
    a = float(amount_eur)
    if a >= 1_000_000_000:
        return f"{a / 1_000_000_000:.1f}".replace(".", ",").rstrip(",0") + " млрд €"
    if a >= 1_000_000:
        return f"{a / 1_000_000:.1f}".replace(".", ",").replace(",0", "") + " млн €"
    if a >= 1_000:
        return f"{a / 1_000:.0f} тис. €"
    return f"{a:.0f} €"
