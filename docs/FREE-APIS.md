# 🆓 Каталог безкоштовних API та джерел для грант-радару

Усе в цьому списку **безкоштовне**: або повністю відкрите (без реєстрації),
або має безкоштовний tier, якого вистачає для щоденного моніторингу.
Статус ✅ = вже підключено в `config/sources.yaml`, ➕ = можна додати (інструкція нижче).

---

## 1. Дані про гранти і тендери — ЄС

| Статус | Джерело | Доступ | Посилання |
|---|---|---|---|
| ✅ | **EU Funding & Tenders Portal (SEDIA)** — усі гранти та конкурси ЄС, ~700 відкритих тем | POST API, **ключ не потрібен** (`apiKey=SEDIA`) | https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=*** · опис: https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis |
| ✅ | **TED — Tenders Electronic Daily**: усі тендери ЄС | POST API, без ключа | https://api.ted.europa.eu/v3/notices/search · докум.: https://docs.ted.europa.eu/api/latest/index.html |
| ✅ | **Interreg NEXT HUSKROUA** (Угорщина–Словаччина–Румунія–Україна) | RSS | https://next.huskroua-cbc.eu/feed/ |
| ✅ | **Keep.eu** — проєкти та конкурси територіальної співпраці | RSS | https://www.keep.eu/rss |
| ✅ | **EUSDR / Danube Region** | RSS | https://danube-region.eu/feed/ |
| ✅ | **European Commission Press corner** | RSS | https://ec.europa.eu/commission/presscorner/api/rss?language=en |
| ➕ | **CORDIS** — проєкти Horizon (пошук партнерів і аналогів) | відкриті дані + API | https://cordis.europa.eu/about/api |
| ➕ | **data.europa.eu** — відкриті дані ЄС, зокрема реєстри бенефіціарів | REST API без ключа | https://data.europa.eu/api/hub/search/search?q=waste |
| ➕ | **EU Financial Transparency System** — хто вже отримав гроші ЄС | відкриті дані | https://ec.europa.eu/budget/financial-transparency-system/ |
| ➕ | **LIFE Programme** (екологія, відходи) — усередині порталу F&T | через SEDIA, фільтр `frameworkProgramme` | https://cinea.ec.europa.eu/programmes/life_en |
| ➕ | **EU4Business** | сторінка оголошень (HTML) | https://eu4business.org.ua/ |

## 2. Міжнародні фінансові організації та донори

| Статус | Джерело | Доступ | Посилання |
|---|---|---|---|
| ✅ | **Світовий банк** — проєкти в Україні | REST API без ключа | https://search.worldbank.org/api/v2/projects?format=json&countrycode_exact=UA |
| ✅ | **NEFCO** — екологічне фінансування для муніципалітетів | RSS | https://www.nefco.int/feed/ |
| ✅ | **EIB** — Європейський інвестиційний банк | RSS | https://www.eib.org/en/press/all/index.rss |
| ➕ | **ЄБРР — закупівлі та проєкти** | сторінки без RSS (потрібен HTML-збирач) | https://www.ebrd.com/work-with-us/procurement.html |
| ➕ | **UNDP Procurement Notices** | HTML/CSV | https://procurement-notices.undp.org/ |
| ➕ | **UNGM — закупівлі ООН** (реєстрація безкоштовна) | HTML + сповіщення на email | https://www.ungm.org/ |
| ➕ | **ReliefWeb API v2** — гуманітарне фінансування України | REST без ключа | https://api.reliefweb.int/v2/ · https://apidoc.reliefweb.int/ |
| ➕ | **IATI Datastore** — усі донорські транзакції світу | REST, безкоштовний ключ | https://docs.datastore.iatistandard.org/ |
| ➕ | **OECD Creditor Reporting System** | SDMX API | https://data-explorer.oecd.org/ |
| ➕ | **Grants.gov (США)** — гранти уряду США | POST API без ключа | https://api.grants.gov/v1/api/search2 |
| ➕ | **GlobalGiving API** (безкоштовний ключ) | REST | https://www.globalgiving.org/api/ |

## 3. Україна

| Статус | Джерело | Доступ | Посилання |
|---|---|---|---|
| ✅ | **Громадський простір** — конкурси та гранти | RSS | https://www.prostir.ua/feed/?post_type=grant |
| ✅ | **Фонд енергоефективності** | RSS | https://eef.org.ua/feed/ |
| ✅ | **Міндовкілля** | RSS | https://mepr.gov.ua/feed/ |
| ➕ | **Prozorro (відкритий API)** — усі закупівлі України | REST без ключа | https://public.api.openprocurement.org/api/2.5/tenders |
| ➕ | **DREAM** — реєстр проєктів відновлення | відкриті дані | https://dream.gov.ua/ |
| ➕ | **Дія.Бізнес — гранти** | HTML (потрібен збирач) | https://business.diia.gov.ua/grants |
| ➕ | **Мінрозвитку громад і територій** | HTML, закрито Cloudflare | https://mindev.gov.ua/ |
| ➕ | **Держенергоефективності** | HTML | https://saee.gov.ua/ |
| ➕ | **Ukraine Facility — План України** | HTML | https://ukrainefacility.me.gov.ua/ |
| ➕ | **U-LEAD з Європою** | HTML/новини | https://u-lead.org.ua/ |
| ➕ | **ГУРТ** — ресурсний центр, оголошення грантів | HTML | https://gurt.org.ua/news/grants/ |

> Джерела з позначкою «HTML» не мають RSS або закриті Cloudflare — для них потрібен
> окремий збирач (тип `html`), це наступний крок розвитку агента.

---

## 4. Безкоштовні LLM API (для AI-аналізу та написання заявок)

Агент підтримує їх «з коробки» — достатньо додати **один** ключ у GitHub Secrets.
Усі вони OpenAI-сумісні, код міняти не треба.

| Провайдер | Безкоштовний ліміт | Змінна оточення | Де взяти ключ |
|---|---|---|---|
| **Groq** (рекомендовано) | щедрий free tier, дуже швидкий, llama-3.3-70b | `GROQ_API_KEY` | https://console.groq.com/keys |
| **Google Gemini** | безкоштовний tier (gemini-2.0-flash), великий контекст | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
| **OpenRouter** | моделі з суфіксом `:free` | `OPENROUTER_API_KEY` | https://openrouter.ai/keys |
| **Cerebras** | безкоштовний tier, llama-3.3-70b | `CEREBRAS_API_KEY` | https://cloud.cerebras.ai/ |
| **Mistral** | безкоштовний «experiment» tier | `MISTRAL_API_KEY` | https://console.mistral.ai/ |
| **Ollama / LM Studio** | повністю безкоштовно, локально | `OLLAMA_BASE_URL=http://localhost:11434/v1` | https://ollama.com/ |

Пріоритет вибору: Groq → Gemini → OpenRouter → Cerebras → Mistral → OpenAI.
Примусово задати провайдера: `LLM_PROVIDER=gemini`, модель: `LLM_MODEL=gemini-2.0-flash`.

**Рекомендація для цього агента:** `GROQ_API_KEY` для щоденного аналізу можливостей
(швидко, безкоштовно) + `GEMINI_API_KEY` для написання чернеток заявок
(довший контекст). Обидва — безкоштовні.

---

## 5. Інша безкоштовна інфраструктура

| Що | Навіщо | Ліміт |
|---|---|---|
| **GitHub Actions** | щоденний автозапуск агента | 2000 хв/міс для приватних репо, безлімітно для публічних |
| **GitHub Pages** | хостинг дашборду | безкоштовно |
| **Telegram Bot API** | сповіщення про нові гранти | безкоштовно, https://core.telegram.org/bots/api |
| **SQLite** | база даних у репозиторії | без сервера |
| **DeepL Free API** *(опційно)* | переклад заявок UA↔EN, 500 тис. знаків/міс | https://www.deepl.com/pro-api |
| **LibreTranslate** *(опційно)* | безкоштовний переклад, self-hosted | https://libretranslate.com/ |

---

## 6. Як додати нове джерело

**RSS** — додайте блок у `config/sources.yaml`:

```yaml
  - id: my_source
    name: "Назва джерела"
    type: rss
    region: UA              # EU | UA | INT
    enabled: true
    weight: 1.0             # 0.8–1.2
    beneficiary_hint: private   # необов'язково: communal | private
    url: "https://example.org/feed/"
```

**API зі своїм форматом** — створіть файл `src/grant_radar/collectors/<ім'я>.py`
з функцією `collect(source: dict) -> list[Opportunity]` (зразки: `ted.py`, `worldbank.py`),
додайте його в словник `COLLECTORS` у `pipeline.py` і вкажіть `type: <ім'я>` у конфізі.

Перевірити, чи джерело віддає дані:

```bash
curl -sL "https://example.org/feed/" | head -c 500
PYTHONPATH=src python -m grant_radar collect --no-llm
```


## Пошук по новинах без ключа (підключено, тип `gnews`)
`https://news.google.com/rss/search?q=<запит>&hl=uk&gl=UA&ceid=UA:uk` — безкоштовно,
без реєстрації, підтримує оператори Google (`"фраза"`, `OR`, `-`, `site:`, `when:120d`).

## Перевірені, але малокорисні
* **Grants.gov** `POST api.grants.gov/v1/api/search2` — працює без ключа,
  але по запиту «Ukraine» лише 4 позиції (гранти уряду США), тож джерело не додане.

## Нові робочі RSS (підключені)
* `https://euneighbourseast.eu/feed/` — EU NEIGHBOURS east, 15 позицій
* `https://www.eu4environment.org/feed/` — EU4Environment, 10
* `https://hromady.org/feed/` — дайджести можливостей для громад, 10
* `https://www.prostir.ua/feed/?post_type=tender` — тендери «Громадського простору», 10
* `https://ecoaction.org.ua/feed` — Екодія, 10

## Перевірені й мертві (не додавати)
interregeurope.eu/rss.xml, interreg-danube.eu/rss, visegradfund.org/feed, undp.org/ukraine/rss.xml,
decentralization.ua/feed, gurt.org.ua/rss, u-lead.org.ua/feed, ebrd.com news.rss, coebank.org rss,
epale.ec.europa.eu/en/rss.xml (403), cinea/eismea/cordis RSS (0 items), minregion.gov.ua/feed (403).
