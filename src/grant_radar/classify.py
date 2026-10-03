"""Визначення типу бенефіціара: комунальне / приватне підприємство / обидва.

Працює на правилах (безкоштовно, без API). Результат — одне зі значень:
    communal  — для комунальних підприємств, ОМС, громад, бюджетних установ
    private   — для бізнесу: МСП, ФОП, приватних компаній, стартапів, фермерів
    both      — підходить обом (консорціуми, «будь-які юридичні особи»)
    unknown   — за текстом визначити не вдалося
"""
from __future__ import annotations

LABEL = {
    "communal": "🏛 Комунальні / ОМС",
    "private": "🏭 Приватний бізнес",
    "both": "🤝 Комунальні + приватні",
    "unknown": "❔ Тип уточнити",
}

COMMUNAL_TERMS = [
    "комунальн", "кп ", "ому ", "орган місцевого самоврядування", "місцев самовряд",
    "громад", "отг", "тергромад", "міськрада", "міська рада", "сільська рада",
    "селищна рада", "райдержадміністрац", "бюджетн установ", "муніципал",
    "municipal", "municipalit", "local authorit", "local government", "public authorit",
    "public body", "public bodies", "public sector", "public entit", "city council",
    "communal enterprise", "utility company", "public utility", "regions and cities",
    "cities and regions", "local and regional", "state-owned", "public administration",
]

PRIVATE_TERMS = [
    "мсп", "малий та середній бізнес", "малого та середнього", "підприємц", "бізнес",
    "приватн компан", "приватного сектор", "фоп", "стартап", "фермер",
    "товаровиробник", "експортер", "інвестор", "приватн підприємств",
    "sme", "smes", "small and medium-sized", "small and medium enterprises",
    "business", "businesses", "start-up", "startup", "entrepreneur", "private sector",
    "private compan", "for-profit", "industry partner", "manufacturer", "scale-up",
    "micro-enterprise", "self-employed", "farmer",
]

BOTH_TERMS = [
    "юридичн особ", "будь-які юридичні особи", "консорціум", "партнерств",
    "legal entities", "any legal entity", "consortium", "partnership",
    "public and private", "public-private", "stakeholders", "organisations established",
    "non-profit and for-profit", "both public and private",
]


def _count(terms: list[str], title: str, body: str) -> tuple[int, list[str]]:
    hits = [t for t in terms if t in title or t in body]
    weight = sum(2 if t in title else 1 for t in hits)
    return weight, hits[:4]


def classify(title: str, summary: str = "", programme: str = "") -> tuple[str, str]:
    """Повертає (тип, пояснення)."""
    t = (title or "").lower()
    b = f"{summary or ''} {programme or ''}".lower()

    c_w, c_hits = _count(COMMUNAL_TERMS, t, b)
    p_w, p_hits = _count(PRIVATE_TERMS, t, b)
    x_w, x_hits = _count(BOTH_TERMS, t, b)

    why = []
    if c_hits:
        why.append("комунальні ознаки: " + ", ".join(c_hits))
    if p_hits:
        why.append("приватні ознаки: " + ", ".join(p_hits))
    if x_hits:
        why.append("відкрито для всіх: " + ", ".join(x_hits))
    reason = "; ".join(why) or "немає прямих вказівок на тип заявника"

    if c_w and p_w and min(c_w, p_w) >= 0.4 * max(c_w, p_w):
        return "both", reason
    if x_w >= 2 and (c_w or p_w):
        return "both", reason
    if c_w > p_w:
        return "communal", reason
    if p_w > c_w:
        return "private", reason
    if x_w:
        return "both", reason
    return "unknown", reason
