"""Реєстр донорів: витягування потенційних партнерів із новин вкладки 🤝,
скоринг пріоритету і генерація листів-запитів.

Реалізує методологію з `docs/METODOLOGIA_DONORIV.md`:

  Пріоритет = Д (доведеність) + М (місток) + З (збіг потреби) − В (вартість входу)

Кожен запис вкладки «Побратими та техніка» перетворюється на **картку донора**:
хто передав, що саме, кому, в якій країні, якою мовою писати, скільки балів
і який статус у роботі. За карткою модуль формує готовий лист потрібною мовою
(угорська, німецька, польська, англійська, українська) з паспорта громади
(`config/profile.yaml` → `community`).
"""
from __future__ import annotations

import csv
import re
import textwrap
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .db import Database

# ─────────────────────────── країни ───────────────────────────
COUNTRY_BY_SOURCE = {
    "gnews_twin_hu": "HU", "gnews_twin_de": "DE", "gnews_twin_pl": "PL",
    "gnews_twin_nl": "NL", "gnews_twin_sv": "SE",
}

COUNTRY_MARKS: list[tuple[str, str]] = [
    (r"угорщин|угорськ|magyar|hungar|tiszabecs|ny[íi]regyh[áa]za|budapest", "HU"),
    (r"німеччин|німецьк|german|deutschland|deutsche[rn]?\b|bayern|sachsen", "DE"),
    (r"польщ|польськ|polsk|poland|gmina|krak[óo]w|warszawa", "PL"),
    (r"словаччин|словацьк|slovak|košice|prešov", "SK"),
    (r"румун|romania|satu mare|maramure", "RO"),
    (r"швец|шведськ|sweden|swedish|svensk|kommun\b", "SE"),
    (r"нідерланд|голланд|netherlands|dutch|gemeente", "NL"),
    (r"литв|lithuani|šiauliai|vilnius", "LT"),
    (r"латв|latvia|riga", "LV"),
    (r"естон|estonia|tallinn", "EE"),
    (r"чехі|чеськ|czech|praha|brno", "CZ"),
    (r"австрі|austria|tirol|wien", "AT"),
    (r"швейцар|switzerland|suisse", "CH"),
    (r"франці|france|paris|[îi]le-de-france", "FR"),
    (r"люксембург|luxembourg", "LU"),
    (r"бельгі|belgium|vlaander|wallon", "BE"),
    (r"данія|данськ|denmark|danish", "DK"),
    (r"норвег|norway|norwegian", "NO"),
    (r"фінлянд|finland|finnish", "FI"),
    (r"британ|british|united kingdom|england|scotland|wales", "GB"),
    (r"ірланді|ireland", "IE"),
    (r"італі|italy|italian", "IT"),
    (r"іспані|spain|spanish", "ES"),
    (r"канад|canada", "CA"),
    (r"сша|american|united states|montana|michigan", "US"),
]

COUNTRY_NAME = {
    "HU": "Угорщина", "DE": "Німеччина", "PL": "Польща", "SK": "Словаччина",
    "RO": "Румунія", "SE": "Швеція", "NL": "Нідерланди", "LT": "Литва",
    "LV": "Латвія", "EE": "Естонія", "CZ": "Чехія", "AT": "Австрія",
    "CH": "Швейцарія", "FR": "Франція", "LU": "Люксембург", "BE": "Бельгія",
    "DK": "Данія", "NO": "Норвегія", "FI": "Фінляндія", "GB": "Велика Британія",
    "IE": "Ірландія", "IT": "Італія", "ES": "Іспанія", "CA": "Канада",
    "US": "США", "UA": "Україна", "??": "не визначено",
}

# мова листування за країною
LANG_BY_COUNTRY = {
    "HU": "hu", "DE": "de", "AT": "de", "CH": "de", "PL": "pl", "UA": "uk",
    "RO": "ro",
}

# ───────────────── що саме передали (тип допомоги) ─────────────────
GOODS_RULES: list[tuple[str, str]] = [
    ("waste", r"сміттєвоз|сміттєзбирал|контейнер|відход|kuk[áa]saut|m[üu]llwagen|"
              r"m[üu]llfahrzeug|garbage truck|refuse (?:truck|vehicle)|śmieciark|"
              r"vuilniswagen|sopbil|waste|комунальн\w+ техн|спецтехнік"),
    ("fire", r"пожежн|рятувальн|t[űu]zolt|feuerwehr|fire (?:truck|engine|vehicle)|"
             r"wóz strażacki|brandweer|brandbil|стихі|дснс"),
    ("transport", r"автобус|мікроавтобус|bus\b|busz|школьн\w* автобус|school bus|"
                  r"ambulance|швидк\w+ допомог|автомобіл|fahrzeug|pojazd|vehicle"),
    ("energy", r"генератор|generator|aggregat|energ|сонячн\w+ панел|ecoflow|"
               r"обігрівач|котел"),
    ("edu", r"школ|шкіл|учн|ліце|гімназ|iskol|school|ноутбук|laptop|комп'ютер|"
            r"computer|принтер|бфп|освіт|education|testv[ée]riskola"),
    ("medical", r"лікарн|медичн|hospital|medical|kórház|ліжк|pflegebett"),
]

GOODS_LABEL = {
    "waste": "♻️ техніка для ТПВ", "fire": "🚒 пожежна/рятувальна техніка",
    "transport": "🚌 транспорт", "energy": "⚡ енергетика та генератори",
    "edu": "🎓 обладнання для шкіл", "medical": "🏥 медичне обладнання",
    "other": "📦 інше",
}

# З — збіг із потребами громади (ТПВ і освіта — пріоритет)
NEED_SCORE = {"waste": 3, "edu": 3, "transport": 2, "energy": 1,
              "fire": 1, "medical": 0, "other": 0}

# М — місток (чим ми «свої»); В — вартість входу (логістика)
BRIDGE = {"HU": 3, "SK": 2, "PL": 2, "RO": 2, "AT": 1, "CZ": 1, "DE": 1,
          "LT": 1, "SE": 1, "NL": 1}
ENTRY_COST = {"HU": 0, "SK": 1, "PL": 1, "RO": 1, "AT": 1, "CZ": 1, "DE": 2,
              "LT": 2, "LV": 2, "EE": 2, "CH": 2, "IT": 2, "FR": 2, "BE": 2,
              "NL": 2, "LU": 2, "DK": 2, "SE": 3, "NO": 3, "FI": 3, "GB": 3,
              "IE": 3, "ES": 3, "CA": 3, "US": 3, "??": 3}

# тип організації-донора
ORG_RULES: list[tuple[str, str]] = [
    ("waste_operator", r"abfallwirtschaft|zweckverband|entsorgung|kp \"|комунальн\w+ підприємств|"
                       r"zgk|mpo\b|waste management|renhållning"),
    ("fire_brigade", r"feuerwehr|t[űu]zolt[óo]|пожежн\w+ (?:частин|команд|служб)|"
                     r"fire (?:department|brigade|service)|brandk[åa]r|osp\b"),
    ("district", r"landkreis|kreis\b|j[áa]r[áa]s|powiat|region\b|regione|megye|county"),
    ("ngo", r"фонд|foundation|stiftung|alap[íi]tv[áa]ny|charity|asociac|association|"
            r"egyes[üu]let|verein|stowarzyszenie|rotary|lions|без кордонів|without borders"),
    ("church", r"парафі|церкв|reform[áa]tus|kirchengemeinde|parafia|diak[óo]nia|"
               r"caritas|szeretetszolg[áa]lat|church|plébánia"),
    ("school", r"школ|iskol|schule|szko[łl]a|school|gymnasium|ліце"),
    ("platform", r"cities4cities|united4ukraine|salar|u-lead|skew|engagement global|"
                 r"solidarity fund|асоціац"),
]
ORG_LABEL = {
    "municipality": "🏛 самоврядування", "waste_operator": "♻️ оператор відходів",
    "fire_brigade": "🚒 пожежна команда", "district": "🗺 район / регіон",
    "ngo": "🤲 фонд або НУО", "church": "⛪ церковна громада",
    "school": "🎓 школа", "platform": "🔗 платформа-посередник",
}

# коло близькості (з методології)
CIRCLE_LABEL = {
    1: "1 · угорський канал", 2: "2 · прикордоння і Тиса",
    3: "3 · слід сусіда (Закарпаття)", 4: "4 · профільні мережі",
    5: "5 · освітні донори", 6: "6 · Дунайський басейн",
}

STATUS_LABEL = {
    "new": "🆕 новий", "letter_sent": "📨 лист надіслано",
    "replied": "💬 є відповідь", "negotiating": "🤝 перемовини",
    "agreed": "✅ домовлено", "received": "🎁 допомогу отримано",
    "refused": "🚫 відмова", "archived": "🗄 архів",
}

# ───────────────── витягування назви донора з заголовка ─────────────────
_NAME = r"[A-ZÁÄÉÍÓÖŐÚÜŰÇŁŚŻŹÅÄÖÀÂÎÔÛА-ЯЇІЄҐ][\w''’\-\.]+"
DONOR_PATTERNS = [
    rf"(?:від|з)\s+(?:міста[- ]побратима|міста|громади|партнерів з|комуни)\s+({_NAME}(?:\s+{_NAME}){{0,2}})",
    rf"({_NAME}(?:\s+{_NAME}){{0,2}})\s+(?:переда[влн]\w*|подарува\w+|передано)",
    rf"(?:від|з)\s+(?:німецького|угорського|польського|литовського|шведського|"
    rf"чеського|словацького|австрійського|французького|британського)\s+міста\s+({_NAME})",
    rf"({_NAME})\s+(?:spendet|übergibt|schickt|liefert|unterstützt)",
    rf"(?:aus|von)\s+({_NAME}(?:\s+{_NAME})?)\s+(?:nach|an)\s+",
    rf"({_NAME})\s+(?:adom[áa]nyoz\w+|[áa]tad\w+|t[áa]mogat\w+)",
    rf"({_NAME}(?:\s+{_NAME}){{0,2}})\s+(?:donat\w+|hands over|sends|gifts|delivers)",
    rf"({_NAME})\s+(?:przekaza\w+|podarowa\w+)",
    rf"({_NAME})\s+(?:sk[äa]nker|donerar)",
    # німецька прикметникова форма: «Flensburger Müllfahrzeug» → Flensburg
    r"\b([A-ZÄÖÜ][a-zäöüß]{3,})er\s+\w*(?:fahrzeug|wagen|spende|hilfe|transport)",
    # «Swedish Ronneby», «German Fulda»
    r"(?:Swedish|German|Polish|Lithuanian|Dutch|Danish|Finnish|Norwegian|"
    r"Hungarian|Czech|Slovak|French|Swiss|Austrian|Italian)\s+({0})".format(_NAME),
    # «від німецького міста Фульда» вже є вище; «з міста Фленсбург»
    rf"(?:міст[аі]|громад[иі]|комуни)\s+({_NAME})",
    # угорські форми: «Debrecen önkormányzata», «Zalaegerszeg testvérvárosa»
    rf"({_NAME})\s+(?:[öo]nkorm[áa]nyzat\w*|v[áa]ros\w*\s+[öo]nkorm|testv[ée]rv[áa]ros\w*)",
    rf"testv[ée]rv[áa]ros\w*\s+(?:lesz\s+)?({_NAME})",
    rf"({_NAME})\s+(?:és|and)\s+{_NAME}\s+testv[ée]r",
    # шведські / нідерландські форми: «Norrtälje kommun», «Friese brandweer»
    rf"({_NAME})\s+(?:kommun|stad|gemeente|brandweer|brandk[åa]r)",
    rf"({_NAME})\s+und\s+(?:die|das|der)\s+ukrainisch",
    rf"k[öo]t[öo]tt\s+({_NAME})\s+(?:és|and)",
]

_STOP = {"Україна", "Україні", "України", "Ukraine", "Ukrajna", "Ukrainie",
         "Громада", "Громаді", "Місто", "Місту", "Нові", "Новий", "Два", "Як",
         "Stadt", "Gemeinde", "Partnerstadt", "Partnergemeinde", "Город"}


def _clean(name: str | None) -> str:
    if not name:
        return ""
    name = re.sub(r"\s+", " ", name).strip(" -–—,.:;«»\"'")
    if name in _STOP or len(name) < 3:
        return ""
    return name


def guess_donor_name(title: str, summary: str = "") -> str:
    text = f"{title}. {summary}"[:400]
    for rx in DONOR_PATTERNS:
        m = re.search(rx, text)
        if m:
            cleaned = _clean(m.group(1))
            if cleaned:
                return cleaned
    return ""


def guess_recipient(title: str) -> str:
    for rx in [rf"(?:громаді|місту|для громади|передали)\s+({_NAME}(?:\s+{_NAME})?)",
               rf"({_NAME}(?:\s+{_NAME})?)\s+громад[аі]",
               rf"Partnerstadt\s+({_NAME})", rf"(?:to|for)\s+({_NAME})"]:
        m = re.search(rx, title)
        if m and _clean(m.group(1)):
            return _clean(m.group(1))
    return ""


def detect_country(item: dict[str, Any]) -> str:
    sid = item.get("source_id") or ""
    text = f"{item.get('title') or ''} {item.get('summary') or ''}".lower()
    for rx, code in COUNTRY_MARKS:
        if re.search(rx, text, re.I):
            return code
    return COUNTRY_BY_SOURCE.get(sid, "??")


def detect_goods(item: dict[str, Any]) -> str:
    text = f"{item.get('title') or ''} {item.get('summary') or ''}"
    for key, rx in GOODS_RULES:
        if re.search(rx, text, re.I):
            return key
    return "other"


def detect_org_type(name: str, item: dict[str, Any]) -> str:
    text = f"{name} {item.get('title') or ''} {item.get('summary') or ''}"
    for key, rx in ORG_RULES:
        if re.search(rx, text, re.I):
            return key
    return "municipality"


def detect_circle(country: str, item: dict[str, Any], goods: str) -> int:
    text = f"{item.get('title') or ''} {item.get('summary') or ''}"
    if country == "HU":
        return 1
    if re.search(r"закарпат|ужгород|мукачев|берегов|виноград|хуст|тячів|чоп\b|"
                 r"k[áa]rp[áa]talj", text, re.I):
        return 3
    if country in ("SK", "RO", "PL"):
        return 2
    if goods == "edu":
        return 5
    return 4


TRANSFER_RX = re.compile(
    r"(переда[влно]|подарува|отрима|надійш|adom[áa]ny|[áa]tad|spende|gespendet|"
    r"[üu]bergeb|[üu]bergab|schickt|donat|hands over|przekaza|podarowa|sk[äa]nk|"
    r"doneer|gedoneerd|delivered|handed)", re.I)


def score_donor(country: str, goods: str, item: dict[str, Any],
                today: date | None = None) -> dict[str, int]:
    """Д + М + З − В за методологією."""
    today = today or datetime.now(timezone.utc).date()
    text = f"{item.get('title') or ''} {item.get('summary') or ''}"

    # Д — доведеність: чи вже передавав і наскільки свіжо
    proven = 0
    if TRANSFER_RX.search(text):
        proven = 2
        pub = (item.get("published_at") or "")[:10]
        try:
            if pub and (today - date.fromisoformat(pub)).days <= 365:
                proven = 3
        except ValueError:
            pass
    elif re.search(r"побратим|testv[ée]r|partnerst|twinning|partner cit", text, re.I):
        proven = 1

    # М — місток
    bridge = BRIDGE.get(country, 0)
    if re.search(r"закарпат|k[áa]rp[áa]talj|берегів|виноград", text, re.I):
        bridge = min(3, bridge + 1)

    need = NEED_SCORE.get(goods, 0)
    cost = ENTRY_COST.get(country, 3)
    return {"proven": proven, "bridge": bridge, "need": need, "cost": cost,
            "priority": proven + bridge + need - cost}


def card_from_item(item: dict[str, Any]) -> dict[str, Any]:
    """Перетворює запис стрічки 🤝 на картку донора."""
    title = item.get("title") or ""
    summary = item.get("summary") or ""
    country = detect_country(item)
    goods = detect_goods(item)
    name = guess_donor_name(title, summary)
    org_type = detect_org_type(name, item)
    sc = score_donor(country, goods, item)
    return {
        "uid": item.get("uid"),
        "name": name or "—",
        "country": country,
        "org_type": org_type,
        "circle": detect_circle(country, item, goods),
        "goods": goods,
        "what": title[:300],
        "recipient": guess_recipient(title),
        "event_date": (item.get("published_at") or "")[:10],
        "news_url": item.get("url") or "",
        "site": "",
        "contact_person": "", "contact_email": "", "contact_phone": "",
        "lang": LANG_BY_COUNTRY.get(country, "en"),
        "proven": sc["proven"], "bridge": sc["bridge"], "need": sc["need"],
        "cost": sc["cost"], "priority": sc["priority"],
        "status": "new", "letter_sent_at": None, "followup_at": None,
        "notes": "" if name else "ім'я донора не зчиталося із заголовка — "
                                   "уточніть у тексті новини",
    }


def rebuild(db: Database, limit: int = 1000) -> dict[str, int]:
    """Перебудовує реєстр донорів зі стрічки 🤝 (ручні правки не чіпає)."""
    rows = db.query(feed="aid", min_score=0, limit=limit, only_active=True)
    live = {r["uid"] for r in rows}
    # прибираємо автоматичні картки, чия новина вже не у стрічці (шум, фільтри);
    # усе, з чим уже працювали вручну, лишається
    removed = db.prune_donors(live)
    added = updated = 0
    for r in rows:
        card = card_from_item(r)
        if card["name"] == "—" and card["country"] == "??":
            continue  # нічого корисного не витягли
        if db.donor_by_uid(card["uid"]):
            db.update_donor_scores(card)
            updated += 1
        else:
            db.add_donor(card)
            added += 1
    return {"added": added, "updated": updated, "removed": removed,
            "total": db.donor_count()}


# ─────────────────────────── листи ───────────────────────────
LETTERS: dict[str, str] = {
"hu": """Tárgy: Együttműködési kezdeményezés – {center_hu} ({name_en}), {region_hu}

Tisztelt Polgármester Úr / Asszony! Tisztelt Kollégák!

A(z) {name_hu} nevében fordulok Önökhöz. Községünk Kárpátalján, a magyar határ
mellett fekszik ({border}), {settlements} település tartozik hozzá, lakosságunk
mintegy {population} fő, jelentős részük magyar anyanyelvű.

{reference_hu}

{situation}
{water}
Legfontosabb szükségleteink:
{needs_hu}

Vállaljuk a vámkezelést, az ukrán oldali szállítást, az üzemeltetést és a
biztosítást, fényképes beszámolót készítünk az eszközök használatáról, és
készek vagyunk testvértelepülési megállapodást aláírni.

Hálásak lennénk, ha egy online megbeszélés vagy levélváltás keretében
megvitathatnánk az együttműködés lehetséges formáit. Hisszük, hogy közös
erővel megállíthatjuk a környezeti válságot, és tisztább vizet, biztonságos
jövőt teremthetünk mindannyiunk folyói mentén.

Köszönettel és tisztelettel,
{person_en}{position_part_en}
{name_hu} · {name_en}
{email} · {phone}{website_part}""",

"de": """Betreff: Kooperationsanfrage – {name_de} ({center_hu}), Transkarpatien, Ukraine

Sehr geehrte Damen und Herren,

wir wenden uns an Sie im Namen der Gemeinde {center_en} ({center_hu}) in
Transkarpatien, Ukraine: {settlements} Ortschaften, rund {population}
Einwohner, direkt an der EU-Außengrenze ({border}).

{reference_de}

{situation}
{water}
Unser vorrangiger Bedarf:
{needs_de}

Zollabfertigung, Transport ab der Grenze, Wartung und Versicherung übernehmen
wir. Über den Einsatz berichten wir mit Fotos und einer Pressemitteilung; eine
Partnerschaftsvereinbarung würden wir gerne unterzeichnen.

Wir würden uns sehr freuen, mögliche Wege der Zusammenarbeit in einem
Online-Gespräch oder im Schriftverkehr zu besprechen. Gemeinsam können wir die
ökologische Krise stoppen und für sauberes Wasser und eine sichere Zukunft
entlang unserer gemeinsamen Flüsse sorgen.

Mit freundlichen Grüßen,
{person_en}{position_part_en}
{name_en}
{email} · {phone}{website_part}""",

"pl": """Temat: Propozycja współpracy – gmina {center_en}, Zakarpacie, Ukraina

Szanowni Państwo,

zwracamy się do Państwa w imieniu gminy {center_en} (Zakarpacie, Ukraina):
{settlements} miejscowości, około {population} mieszkańców, przy samej granicy
z Unią Europejską ({border}).

{reference_pl}

{situation}
{water}
Nasze priorytetowe potrzeby:
{needs_pl}

Pokrywamy odprawę celną, transport po stronie ukraińskiej, eksploatację i
ubezpieczenie. Zobowiązujemy się do sprawozdania ze zdjęciami oraz jesteśmy
gotowi podpisać umowę o współpracy partnerskiej.

Będziemy wdzięczni za możliwość omówienia form współpracy podczas spotkania
online lub korespondencji roboczej. Wierzymy, że wspólnymi siłami zatrzymamy
kryzys ekologiczny i zapewnimy czystszą wodę oraz bezpieczną przyszłość
naszym regionom.

Z wyrazami szacunku,
{person_en}{position_part_en}
{name_en}
{email} · {phone}{website_part}""",

"ro": """Subiect: Propunere de parteneriat – comunitatea {center_en} ({center_hu}), Transcarpatia, Ucraina

Stimată doamnă primar, stimate domnule primar, stimați colegi,

Vă scriem în numele comunității {center_en} ({center_hu}) din regiunea
Transcarpatia, Ucraina: {settlements} localități, aproximativ {population} de
locuitori, chiar la frontiera Uniunii Europene ({border}).

{reference_ro}

{situation}
{water}
Nevoile noastre prioritare:
{needs_ro}

Ne asumăm vămuirea, transportul pe teritoriul Ucrainei, întreținerea și
asigurarea. Vom prezenta un raport foto privind utilizarea echipamentelor și
suntem pregătiți să semnăm un memorandum de cooperare.

V-am fi sincer recunoscători pentru posibilitatea de a discuta formele
concrete de cooperare într-o întâlnire online sau prin corespondență. Credem
că împreună putem opri criza ecologică și putem asigura apă mai curată și un
viitor sigur de-a lungul râurilor pe care le împărțim.

Cu deosebită considerație,
{person_en}{position_part_en}
{name_en}
{email} · {phone}{website_part}""",

"en": """Subject: Partnership request – {name_en} ({center_en}), Zakarpattia, Ukraine

Dear Mayor, dear colleagues,

We are writing on behalf of {name_en} in {region_en}: {settlements}
settlements, about {population} residents, located directly on the EU border
({border}).

{reference_en}

{situation}
{water}
Our priority needs:
{needs_en}

We cover customs clearance, transport on the Ukrainian side, maintenance and
insurance. We will report on the use of the equipment with photos and a press
release, and we are ready to sign a twinning memorandum.

We would be sincerely grateful for the opportunity to discuss possible forms of
cooperation in an online meeting or by correspondence. We believe that together
we can stop this environmental crisis and secure cleaner water and a safe
future along the rivers we share.

Kind regards,
{person_en}{position_part_en}
{name_en}
{email} · {phone}{website_part}""",

"uk": """Тема: Пропозиція співпраці — {name_uk}, Закарпаття

Шановні колеги!

Звертаємося від імені {name_uk_gen} ({region_uk}): {settlements} населених
пунктів, близько {population} мешканців, {border}.

{reference_uk}

{situation}
{water}
Першочергові потреби:
{needs_uk}

Розмитнення, транспортування територією України, обслуговування та страхування
беремо на себе. Гарантуємо фотозвіт, публікацію подяки та готові підписати
меморандум про співпрацю.

Будемо щиро вдячні за можливість обговорити потенційні шляхи співпраці під час
онлайн-зустрічі чи робочого листування. Віримо, що спільними зусиллями ми
зможемо зупинити екологічну кризу та забезпечити чистішу воду і безпечне
майбутнє вздовж наших спільних річок.

З повагою,
{person_uk}{position_part_uk}
{name_uk}
{email} · {phone}{website_part}""",
}

# ── привід для листа: новина про допомогу, яку донор уже надавав ──
REFERENCE = {
    "hu": "Értesültünk arról, hogy Önök {date_part}{what_hu}. Ezért fordulunk "
          "Önökhöz azzal a kéréssel, hogy fontolják meg a velünk való "
          "együttműködést is.",
    "de": "Wir haben erfahren, dass Sie {date_part}{what_de}. Deshalb wenden "
          "wir uns mit der Bitte um Zusammenarbeit an Sie.",
    "pl": "Dowiedzieliśmy się, że {date_part}wsparli Państwo ukraińską gminę: "
          "«{what}». Dlatego zwracamy się do Państwa.",
    "ro": "Am aflat că {date_part}ați sprijinit o comunitate din Ucraina: "
          "«{what}». De aceea ne adresăm dumneavoastră.",
    "en": "We have learned that {date_part}you supported a Ukrainian community: "
          "«{what}». This is why we are turning to you.",
    "uk": "Ми дізналися, що {date_part}ви підтримали українську громаду: "
          "«{what}». Саме тому звертаємося до вас.",
}

# ── привід для громад Дунайського басейну (спільна річка, а не новина) ──
REFERENCE_DANUBE = {
    "hu": "Önökhöz, {donor} önkormányzatához fordulunk, mint a Duna partján "
          "fekvő közösséghez. Községünk a Tisza partján fekszik, amely a Duna "
          "legnagyobb mellékfolyója, így egy vízgyűjtő terület két végén élünk: "
          "ami nálunk a hulladékkal történik, néhány nap alatt az Önök "
          "folyószakaszának vízminőségét is érinti.",
    "de": "Wir wenden uns an die Gemeinde {donor} als Kommune an der Donau. "
          "Unsere Gemeinde liegt an der Theiß, dem größten Nebenfluss der "
          "Donau — wir leben also an zwei Enden desselben Einzugsgebiets: Was "
          "bei uns mit dem Abfall geschieht, erreicht binnen weniger Tage auch "
          "Ihren Flussabschnitt.",
    "pl": "Zwracamy się do gminy {donor} jako do samorządu położonego nad "
          "Dunajem. Nasza gmina leży nad Cisą, największym dopływem Dunaju — "
          "mieszkamy więc na dwóch końcach tego samego dorzecza: to, co dzieje "
          "się u nas z odpadami, w ciągu kilku dni dotyczy także Państwa "
          "odcinka rzeki.",
    "ro": "Ne adresăm localității {donor}, în calitate de comunitate situată "
          "pe Dunăre. Comunitatea noastră se află pe Tisa, cel mai mare afluent "
          "al Dunării — trăim deci la cele două capete ale aceluiași bazin "
          "hidrografic: ceea ce se întâmplă la noi cu deșeurile ajunge în "
          "câteva zile și pe sectorul dumneavoastră de râu.",
    "en": "We are writing to the municipality of {donor} as a community on the "
          "Danube. Our hromada lies on the Tisza, the largest tributary of the "
          "Danube — we live at two ends of the same river basin: what happens "
          "with waste here reaches your stretch of the river within days.",
    "uk": "Звертаємося до громади {donor} як до самоврядування на Дунаї. Наша "
          "громада стоїть на Тисі — найбільшій притоці Дунаю, тож ми живемо на "
          "двох кінцях одного річкового басейну: те, що відбувається з "
          "відходами в нас, за кілька днів стосується і вашої ділянки річки.",
}


MONTHS = {
    "de": ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
    "en": ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "pl": ["", "styczniu", "lutym", "marcu", "kwietniu", "maju", "czerwcu",
           "lipcu", "sierpniu", "wrześniu", "październiku", "listopadzie",
           "grudniu"],
    "ro": ["", "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
           "iulie", "august", "septembrie", "octombrie", "noiembrie",
           "decembrie"],
    "uk": ["", "січні", "лютому", "березні", "квітні", "травні", "червні",
           "липні", "серпні", "вересні", "жовтні", "листопаді", "грудні"],
}

LETTER_LANGS = ("uk", "en", "de", "hu", "pl", "ro")


def _needs_block(community: dict[str, Any], lang: str, goods: str) -> str:
    needs = community.get("needs") or {}
    topic = "edu" if goods == "edu" else "waste"
    key = f"{topic}_{lang if lang in LETTER_LANGS else 'en'}"
    items = needs.get(key) or needs.get(f"{topic}_en") or []
    lines = []
    for i, raw in enumerate(items, 1):
        item = str(raw).strip().rstrip(";")
        if not item.endswith((".", "!", "?")):
            item += "."
        lines.append(f"  {i}. {item}")
    return "\n".join(lines)


def _profile_block(community: dict[str, Any], key: str, lang: str) -> str:
    block = community.get(key) or {}
    text = block.get(lang) or block.get("en") or block.get("uk") or ""
    return text.rstrip() + "\n" if text else ""


def _situation_block(community: dict[str, Any], lang: str, goods: str) -> str:
    """Опис ситуації громади з `config/profile.yaml` → `community.situation`."""
    return _profile_block(community, "situation_edu" if goods == "edu"
                          else "situation", lang)


def _water_block(community: dict[str, Any], lang: str, goods: str) -> str:
    """Водний аргумент (Тиса → Дунай) з `config/profile.yaml` → `community.water`.

    Додається до всіх листів про відходи й комунальну техніку: забруднення
    басейну Дунаю стосується і сусідів нижче за течією, і донорів, які
    фінансують екологічні проєкти. Для суто освітніх звернень пропускається.
    """
    if goods == "edu":
        return ""
    return _profile_block(community, "water", lang)


_SUBJECT_RX = re.compile(r"^(Betreff|T[áa]rgy|Subject|Temat|Subiect|Тема):")


def _reflow(body: str, width: int = 78) -> str:
    """Вирівнює абзаци, у які підставилися довгі значення з профілю.

    Чіпаємо лише суцільні абзаци: списки (рядки з відступом), тему листа
    й підпис лишаємо як є, щоб не зламати форматування.
    """
    out = []
    for block in body.split("\n\n"):
        lines = block.split("\n")
        long_line = max((len(x) for x in lines), default=0) > width
        plain = all(not x.startswith((" ", "\t")) for x in lines)
        if long_line and plain and not _SUBJECT_RX.match(block) and len(lines) > 1:
            out.append(textwrap.fill(" ".join(x.strip() for x in lines), width))
        else:
            out.append(block)
    return "\n\n".join(out)


def build_letter(donor: dict[str, Any], lang: str | None = None) -> str:
    """Формує готовий лист-запит під конкретного донора."""
    profile = config.load_profile()
    c = profile.get("community", {}) or {}
    contact = c.get("contact", {}) or {}
    lang = (lang or donor.get("lang") or "en").lower()
    if lang not in LETTERS:
        lang = "en"

    date_part = ""
    if donor.get("event_date"):
        try:
            d = date.fromisoformat(donor["event_date"])
            months = MONTHS.get(lang, MONTHS["en"])
            date_part = {
                "hu": f"{d.year}. {d.month:02d}. hónapban ",
                "de": f"im {months[d.month]} {d.year} ",
                "pl": f"w {months[d.month]} {d.year} roku ",
                "ro": f"în {months[d.month]} {d.year} ",
                "en": f"in {months[d.month]} {d.year} ",
                "uk": f"у {months[d.month]} {d.year} року ",
            }.get(lang, f"in {MONTHS['en'][d.month]} {d.year} ")
        except ValueError:
            date_part = ""

    def wrap(text: str) -> str:
        """Переносимо абзац по 78 символів — щоб лист читався в будь-якій пошті."""
        return "\n".join(textwrap.wrap(text, width=78)) if text else ""

    what = donor.get("what") or ""
    ref_lang = lang if lang in REFERENCE else "en"
    if str(donor.get("uid") or "").startswith("danube:"):
        # громада з Дунаю: приводом є спільний річковий басейн, а не новина
        reference = wrap(REFERENCE_DANUBE[ref_lang].format(
            donor=donor.get("name") or ""))
    else:
        reference = wrap(REFERENCE[ref_lang].format(
            date_part=date_part, what=what,
            what_hu=f"támogattak egy ukrán közösséget: «{what}»",
            what_de=f"eine ukrainische Gemeinde unterstützt haben: «{what}»"))

    person_uk = contact.get("person_uk") or "<ПІБ відповідальної особи>"
    person_en = contact.get("person_en") or "<name in Latin letters>"
    pos_uk = contact.get("position_uk") or ""
    pos_en = contact.get("position_en") or ""
    goods = donor.get("goods", "waste")
    values = {
        "name_uk": c.get("name_uk", ""), "name_en": c.get("name_en", ""),
        "name_uk_gen": c.get("name_uk_gen") or c.get("name_uk", ""),
        "name_hu": c.get("name_hu", ""), "name_de": c.get("name_de", ""),
        "center_uk": c.get("center_uk", ""), "center_hu": c.get("center_hu", ""),
        "center_en": c.get("center_en", ""),
        "region_uk": c.get("region_uk", ""), "region_en": c.get("region_en", ""),
        "region_hu": c.get("region_hu", ""),
        "population": f"{c.get('population', 0):,}".replace(",", " "),
        "settlements": c.get("settlements", ""),
        "border": c.get(f"border_{lang}") or c.get("border_en") or c.get("border", ""),
        "fleet_uk": c.get("fleet_uk", ""), "fleet_en": c.get("fleet_en", ""),
        "fleet_de": c.get("fleet_de", ""), "fleet_hu": c.get("fleet_hu", ""),
        "email": contact.get("email") or "<e-mail громади>",
        "phone": contact.get("phone") or "<телефон / WhatsApp>",
        "website_part": f" · {contact.get('website')}" if contact.get("website") else "",
        "person_uk": person_uk, "person_en": person_en,
        "position_part_uk": f", {pos_uk}" if pos_uk else "",
        "position_part_en": f", {pos_en}" if pos_en else "",
        "situation": _situation_block(c, lang, goods),
        "water": _water_block(c, lang, goods),
    }
    for code in LETTER_LANGS:
        values[f"reference_{code}"] = reference
        values[f"needs_{code}"] = _needs_block(c, code, goods)
    header = (f"# Лист до: {donor.get('name')} ({COUNTRY_NAME.get(donor.get('country',''), '')})\n"
              f"# Привід: {donor.get('what')}\n"
              f"# Джерело: {donor.get('news_url')}\n"
              f"# Пріоритет: {donor.get('priority')} "
              f"(Д{donor.get('proven')} М{donor.get('bridge')} "
              f"З{donor.get('need')} −В{donor.get('cost')})\n"
              f"{'-' * 72}\n\n")
    return header + _reflow(LETTERS[lang].format(**values))


def write_letters(db: Database, out_dir: Path | None = None, min_priority: int = 4,
                  limit: int = 50) -> list[Path]:
    """Готує файли листів для найпріоритетніших донорів."""
    out_dir = Path(out_dir or config.DATA_DIR / "letters")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for d in db.donors(min_priority=min_priority, limit=limit * 10):
        if str(d.get("uid") or "").startswith("danube:"):
            continue  # придунайські громади — окрема команда `danube`
        if len(paths) >= limit:
            break
        safe = re.sub(r"[^\w\-]+", "_", f"{d['id']}-{d['name']}")[:60]
        path = out_dir / f"{safe}.txt"
        path.write_text(build_letter(d), encoding="utf-8")
        paths.append(path)
    return paths


def export_csv(db: Database, out: Path | None = None) -> Path:
    """Вивантажує реєстр у CSV (для роботи в Excel / Google Таблицях)."""
    out = Path(out or config.DATA_DIR / "donors.csv")
    rows = db.donors(limit=5000, order="priority")
    fields = ["id", "name", "country", "org_type", "circle", "goods", "what",
              "recipient", "event_date", "news_url", "site", "contact_person",
              "contact_email", "contact_phone", "lang", "proven", "bridge",
              "need", "cost", "priority", "status", "letter_sent_at",
              "followup_at", "notes"]
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return out


# ───────────────── пошук контактів на сайті донора ─────────────────
CONTACT_PAGES = ("", "kontakt", "impressum", "kapcsolat", "contact", "contacts",
                 "kontakty", "over-ons/contact", "om-oss/kontakt")
EMAIL_RX = re.compile(r"[\w\.\-\+]+@[\w\-]+\.[a-z]{2,}", re.I)
SKIP_EMAIL = re.compile(r"(example|sentry|wixpress|\.png|\.jpg|webmaster@localhost)", re.I)


def find_contacts(site: str, timeout: int = 15) -> list[str]:
    """Best-effort: шукає e-mail на сторінках контактів донора."""
    import requests
    from urllib.parse import urljoin

    found: list[str] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; KP-GrantRadar/1.0)"}
    for page in CONTACT_PAGES:
        try:
            r = requests.get(urljoin(site.rstrip("/") + "/", page),
                             headers=headers, timeout=timeout)
            if r.status_code != 200:
                continue
            for m in EMAIL_RX.findall(r.text):
                if not SKIP_EMAIL.search(m) and m.lower() not in found:
                    found.append(m.lower())
            if found:
                break
        except Exception:
            continue
    return found[:5]
