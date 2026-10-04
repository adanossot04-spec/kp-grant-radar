# 🚀 Як створити агента на GitHub — покрокова інструкція

Час: **10–15 хвилин**. Нічого платного не потрібно.
Після цих кроків агент щодня сам сканує гранти, оновлює базу, публікує дашборд
і шле дайджест — без вашої участі.

---

## Крок 0. Що підготувати (5 хв)

| Що | Обов'язково? | Де взяти |
|---|---|---|
| Акаунт GitHub | так | https://github.com/signup |
| Безкоштовний LLM-ключ (Groq) | ні, але дуже бажано | https://console.groq.com/keys → «Create API Key» |
| Telegram-бот для сповіщень | ні | напишіть [@BotFather](https://t.me/BotFather) → `/newbot` → отримаєте токен |
| Git на комп'ютері | ні (є варіант без нього) | https://git-scm.com/downloads |

> **Groq замість OpenAI:** реєстрація через Google-акаунт, картка не потрібна,
> безкоштовного ліміту вистачає для щоденного аналізу з великим запасом.

---

## Крок 1. Створити репозиторій

1. Відкрийте https://github.com/new
2. **Repository name:** `kp-grant-radar`
3. **Visibility** — оберіть свідомо:

| | Private (приватний) | Public (публічний) |
|---|---|---|
| Хто бачить `memory.yaml` з реквізитами | тільки ви | **усі в інтернеті** |
| GitHub Pages (онлайн-дашборд) | лише на платному плані | ✅ безкоштовно |
| Хвилини GitHub Actions | 2000/міс безкоштовно | необмежено |

**Рекомендація:**
- Якщо заповнюєте `config/memory.yaml` реальними даними → **Private**
  (дашборд запускаєте локально командою `serve`, Pages не вмикаєте).
- Якщо хочете онлайн-дашборд → **Public**, але спершу додайте `config/memory.yaml`
  в `.gitignore` (рядок уже заготовлений у кінці файлу — просто розкоментуйте).

4. **НЕ** ставте галочки «Add README», «Add .gitignore» — вони вже є у проєкті.
5. Натисніть **Create repository**.

---

## Крок 2. Залити файли

### Варіант А — через браузер (без встановлення git)

1. Розпакуйте архів `kp-grant-radar.zip` у себе на комп'ютері.
2. У порожньому репозиторії натисніть **uploading an existing file**.
3. Перетягніть у вікно **вміст** папки (усі файли й підпапки, не саму папку).
   GitHub зберігає структуру підпапок при перетягуванні.
4. Унизу: «Commit changes» → **Commit directly to the main branch** → **Commit changes**.

> ⚠️ Прихована папка `.github/` при перетягуванні іноді не потрапляє у завантаження.
> Перевірте, що у репозиторії є файл `.github/workflows/monitor.yml`. Якщо немає —
> створіть вручну: **Add file → Create new file**, вкажіть шлях
> `.github/workflows/monitor.yml` і вставте вміст із архіву. Без цього файлу
> автоматичний запуск не працюватиме.

### Варіант Б — через git (швидше та надійніше)

```bash
cd шлях/до/kp-grant-radar

git init
git add .
git commit -m "Грант-радар: моніторинг грантів для комунальних і приватних підприємств"
git branch -M main
git remote add origin https://github.com/<ВАШ-АКАУНТ>/kp-grant-radar.git
git push -u origin main
```

Або просто запустіть готовий скрипт з папки проєкту:

```bash
bash scripts/setup-github.sh <ВАШ-АКАУНТ> kp-grant-radar
```

> Якщо git попросить пароль — це має бути **Personal Access Token**, а не пароль акаунта:
> https://github.com/settings/tokens → Generate new token (classic) → область `repo`.

---

## Крок 3. Додати ключі (Secrets)

`Settings` → ліве меню `Secrets and variables` → `Actions` → кнопка **New repository secret**.

| Name | Secret | Для чого |
|---|---|---|
| `GROQ_API_KEY` | ключ з console.groq.com | AI-аналіз + написання чернеток заявок |
| `GEMINI_API_KEY` | ключ з aistudio.google.com | альтернатива або резерв |
| `TELEGRAM_BOT_TOKEN` | токен від @BotFather | сповіщення |
| `TELEGRAM_CHAT_ID` | ваш chat id | куди слати |

**Як дізнатися `TELEGRAM_CHAT_ID`:** напишіть своєму боту будь-яке повідомлення,
потім відкрийте в браузері
`https://api.telegram.org/bot<ВАШ_ТОКЕН>/getUpdates` і знайдіть `"chat":{"id":123456789`.

Жоден секрет не є обов'язковим — без них агент працює на правилах.

---

## Крок 4. Дозволити боту комітити результати

`Settings` → `Actions` → `General` → розділ **Workflow permissions**:

- ✅ **Read and write permissions**
- ✅ Allow GitHub Actions to create and approve pull requests *(не обов'язково)*
- **Save**

Без цього кроку робочий процес впаде на етапі збереження бази з помилкою `403`.

---

## Крок 5. Увімкнути GitHub Pages (тільки для публічного репозиторію)

`Settings` → `Pages` → **Source: GitHub Actions** → зберегти.

Після першого успішного запуску дашборд буде тут:
`https://<ВАШ-АКАУНТ>.github.io/kp-grant-radar/`

Для приватного репозиторію пропустіть цей крок — у workflow два останні блоки
(`upload-pages-artifact` і `deploy-pages`) можна видалити, решта працюватиме.

---

## Крок 6. Перший запуск

`Actions` → у списку зліва **«Грант-радар — моніторинг»** → **Run workflow** → **Run workflow**.

Перший запуск триває 2–4 хвилини. У логах ви маєте побачити приблизно таке:

```
🛰️  Сканування джерел…
  eu_ft_portal           698 записів
  ted                    160 записів
  huskroua                10 записів
  worldbank               60 записів
  ...
  LLM проаналізував 25 записів (модель llama-3.3-70b-versatile)
Готово: 1029 записів, 249 нових, помилок: 0
```

Далі агент запускається **щодня о 08:00 за Києвом** (`cron: "0 5 * * *"` у файлі
`.github/workflows/monitor.yml` — змініть, якщо потрібен інший час або частота).

Що бот комітить після кожного запуску:
- `data/grants.sqlite` — база з історією та вашими статусами заявок;
- `docs/index.html`, `docs/data.json` — оновлений дашборд;
- `data/drafts/*.md` — чернетки заявок для найкращих можливостей.

---

## Крок 7. Заповнити пам'ять (найцінніший крок)

Відкрийте `config/memory.yaml` прямо на GitHub (олівець ✏️) або локально й заповніть
хоча б критичні поля — саме з них агент складає заявки:

```
identity.legal_name_uk / legal_name_en / edrpou
contacts.legal_address_en / email_official / head.full_name_uk
banking.iban_uah / iban_eur
boilerplate.org_description_uk_500 / org_description_en_500
operations.* (населення, тонни ТПВ, % сортування, ключові проблеми)
project_pipeline (2–3 готові ідеї проєктів)
```

Перевірка заповненості локально:

```bash
pip install -r requirements.txt
export PYTHONPATH=src
python -m grant_radar memory
```

---

## Крок 8. Локальний дашборд (працює і для приватного репо)

```bash
git clone https://github.com/<ВАШ-АКАУНТ>/kp-grant-radar.git
cd kp-grant-radar
pip install -r requirements.txt
export PYTHONPATH=src
python -m grant_radar serve     # http://localhost:8000
```

У дашборді: групування «🏛 комунальні / 🏭 приватні», фільтри, статуси заявок
(⭐ цікаво → ✍️ готуємо → 📨 подано) і кнопка «📝 чернетка заявки».
Статуси зберігаються в `data/grants.sqlite` — закомітьте файл, щоб вони
синхронізувались із командою: `git add data/grants.sqlite && git commit -m "статуси" && git push`.

---

## Типові проблеми

| Симптом | Причина і рішення |
|---|---|
| `Permission denied (403)` на кроці «Зберегти базу» | не виконано **Крок 4** (Read and write permissions) |
| Pages віддає 404 | репозиторій приватний (Pages лише на платному плані) або не обрано Source: GitHub Actions |
| `LLM вимкнено (немає ключа)` у логах | секрет названо інакше — має бути точно `GROQ_API_KEY` або `GEMINI_API_KEY` |
| Workflow не запускається за розкладом | GitHub вимикає cron у репозиторіях без активності 60 днів — зайдіть в Actions і натисніть «Enable workflow» |
| Запуск за розкладом спізнюється на 10–30 хв | нормальна поведінка безкоштовних раннерів GitHub |
| У логах `mepr: ...403` або подібне | сайт джерела закрито Cloudflare — вимкніть його (`enabled: false`) у `config/sources.yaml` |
| Rate limit від Groq/Gemini | зменште `llm_max_items` у `config/profile.yaml` (напр. до 10) |
| Забагато нерелевантних записів | підніміть пороги `high_threshold` / `medium_threshold` у `config/profile.yaml`, потім `python -m grant_radar rescore` |

---

## Склад проєкту (35 файлів)

```
kp-grant-radar/
├── README.md                      ← опис агента й усіх команд
├── requirements.txt               ← залежності Python
├── pyproject.toml
├── .env.example                   ← приклад локальних ключів
├── .gitignore
├── .github/workflows/monitor.yml  ← автозапуск щодня (GitHub Actions)
├── config/
│   ├── sources.yaml               ← 13 джерел моніторингу
│   ├── profile.yaml               ← ключові слова, ваги, пороги скорингу
│   └── memory.yaml                ← 📒 досьє організацій для автозаповнення заявок
├── docs/
│   ├── DEPLOY-GITHUB.md           ← цей файл
│   ├── FREE-APIS.md               ← каталог безкоштовних API з посиланнями
│   ├── index.html                 ← статичний дашборд (GitHub Pages)
│   └── data.json                  ← дані дашборду
├── src/grant_radar/
│   ├── __main__.py                ← CLI: collect / rescore / serve / export /
│   │                                 digest / draft / memory / top / sources
│   ├── pipeline.py                ← збір → дедуплікація → скоринг → класифікація → LLM
│   ├── collectors/
│   │   ├── eu_sedia.py            ← портал грантів ЄС (API без ключа)
│   │   ├── ted.py                 ← тендери ЄС (API без ключа)
│   │   ├── worldbank.py           ← проєкти Світового банку (API без ключа)
│   │   └── rss.py                 ← RSS + розпізнавання дедлайнів у тексті
│   ├── scoring.py                 ← правила релевантності
│   ├── classify.py                ← комунальні / приватні / обидва
│   ├── memory.py                  ← досьє: завантаження, аналіз повноти
│   ├── draft.py                   ← генерація чернетки заявки
│   ├── llm.py                     ← безкоштовні LLM-провайдери
│   ├── db.py                      ← SQLite: історія, статуси, статистика
│   ├── web.py                     ← FastAPI-дашборд + JSON API
│   ├── export.py                  ← статичний сайт
│   └── digest.py                  ← Markdown-дайджест + Telegram
├── templates/dashboard.html       ← інтерфейс дашборду
├── scripts/setup-github.sh        ← автоматизація першого push
└── data/
    ├── grants.sqlite              ← база (1040 можливостей після першого сканування)
    └── drafts/                    ← приклад згенерованої чернетки заявки
```

---

## Що робити далі

1. Заповнити `config/memory.yaml` — тоді чернетки заявок стануть майже готовими документами.
2. Додати 2–3 проєктні ідеї в `project_pipeline` — агент підбиратиме їх під конкурси.
3. Перевіряти дашборд раз на тиждень і ставити статуси можливостям.
4. Додавати нові джерела з `docs/FREE-APIS.md` у міру потреби.
