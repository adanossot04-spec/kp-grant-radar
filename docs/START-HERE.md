# ▶️ Що робити далі — покроково для `adanossot04-spec/kp-grant-radar`

Репозиторій створено як **Public**. Проєкт уже підготовлено саме під цей режим:
файл `config/memory.yaml` з вашими реквізитами **не комітиться** (він у `.gitignore`),
у репозиторій іде лише шаблон `config/memory.example.yaml`.
Для автоматичних запусків пам'ять передається через Secret — див. крок 4.

Загальний час: ~10 хвилин.

---

## Крок 1. Залити файли (оберіть один варіант)

### Варіант А — через браузер, без git

1. Завантажте з робочого простору архів **`kp-grant-radar.zip`** і розпакуйте його.
2. На сторінці репозиторію натисніть **uploading an existing file**
   (посилання у синьому блоці «Quick setup»).
3. Перетягніть у вікно **вміст** папки `kp-grant-radar` — усі файли й підпапки
   (не саму папку!).
4. Внизу натисніть **Commit changes**.
5. **Перевірте, що завантажилась прихована папка `.github/`.** Браузер часто її пропускає.
   Якщо її немає у списку файлів:
   - **Add file → Create new file**
   - у полі імені введіть: `.github/workflows/monitor.yml`
   - вставте вміст однойменного файлу з архіву → **Commit changes**.
6. Так само перевірте наявність `.gitignore`. Якщо його немає — створіть той самий спосіб.

### Варіант Б — через git (швидше)

```bash
cd шлях/до/kp-grant-radar

git init
git add .
git commit -m "Грант-радар: моніторинг грантів для комунальних і приватних підприємств"
git branch -M main
git remote add origin https://github.com/adanossot04-spec/kp-grant-radar.git
git push -u origin main
```

Якщо git попросить пароль — це **Personal Access Token**, не пароль акаунта:
https://github.com/settings/tokens → *Generate new token (classic)* → область **repo**.

Або одна команда з папки проєкту:

```bash
bash scripts/setup-github.sh adanossot04-spec kp-grant-radar
```

---

## Крок 2. Дозволити боту зберігати результати

**Settings → Actions → General →** секція **Workflow permissions**:

- ✅ **Read and write permissions** → **Save**

Без цього запуск впаде з помилкою `403` на кроці збереження бази.

---

## Крок 3. Додати безкоштовний LLM-ключ

1. Відкрийте https://console.groq.com/keys → увійдіть через Google → **Create API Key** → скопіюйте.
2. У репозиторії: **Settings → Secrets and variables → Actions → New repository secret**
   - **Name:** `GROQ_API_KEY`
   - **Secret:** вставте ключ → **Add secret**

Без ключа агент теж працює, але без українських AI-резюме та без автоматичного
написання змістовної частини заявок.

---

## Крок 4. (Коли заповните досьє) Передати пам'ять через Secret

Поки `config/memory.yaml` не заповнений — пропустіть цей крок.

Коли заповните його локально:

1. Відкрийте файл, виділіть **увесь текст**, скопіюйте.
2. **Settings → Secrets and variables → Actions → New repository secret**
   - **Name:** `MEMORY_YAML`
   - **Secret:** вставте весь вміст файлу → **Add secret**

Workflow сам відновить файл перед запуском, а в репозиторій його не закомітить —
реквізити залишаться прихованими навіть у публічному репо.

---

## Крок 5. Увімкнути онлайн-дашборд (GitHub Pages)

**Settings → Pages → Build and deployment → Source: GitHub Actions** → зберегти.

Після першого успішного запуску дашборд буде доступний тут:

### 🔗 https://adanossot04-spec.github.io/kp-grant-radar/

---

## Крок 6. Перший запуск

**Actions** → у лівому списку **«Грант-радар — моніторинг»** → **Run workflow** → **Run workflow**.

Якщо GitHub показує банер «Workflows aren't being run on this forked repository» або
просить підтвердження — натисніть **I understand my workflows, go ahead and enable them**.

Запуск триває 2–4 хвилини. В успішному логу буде приблизно таке:

```
ℹ️  Secret MEMORY_YAML не задано — використовується шаблон memory.example.yaml
🛰️  Сканування джерел…
  eu_ft_portal           698 записів
  ted                    160 записів
  worldbank               60 записів
  huskroua                10 записів
  ...
  LLM проаналізував 25 записів (модель llama-3.3-70b-versatile)
Готово: 1029 записів, 249 нових, помилок: 0
📄 Статичний сайт: docs/index.html
```

Після цього у репозиторії з'являться оновлені `data/grants.sqlite` і `docs/`,
закомічені ботом `grant-radar-bot`.

Далі агент працює сам — **щодня о 08:00 за Києвом**.

---

## Крок 7. Заповнити досьє (найцінніше)

```bash
git clone https://github.com/adanossot04-spec/kp-grant-radar.git
cd kp-grant-radar
cp config/memory.example.yaml config/memory.yaml     # локальна копія, не комітиться
pip install -r requirements.txt
export PYTHONPATH=src
python -m grant_radar memory        # покаже, скільки заповнено і чого бракує
```

Мінімум, щоб чернетки заявок стали корисними:

| Поле | Приклад |
|---|---|
| `identity.legal_name_uk` / `legal_name_en` | КП «Виноградівський комунальник» / Municipal Enterprise «...» |
| `identity.edrpou` | 12345678 |
| `contacts.legal_address_en` | 1 Myru Str., Vynohradiv, Zakarpattia obl., 90300, Ukraine |
| `contacts.email_official`, `contacts.head.full_name_uk` | — |
| `banking.iban_uah`, `banking.iban_eur` | — |
| `operations.*` | населення, тонни ТПВ/рік, % сортування, ключові проблеми |
| `project_pipeline` | 2–3 готові ідеї проєктів |
| `boilerplate.org_description_uk_500` / `_en_500` | опис організації на ~500 знаків |

Потім:

```bash
python -m grant_radar draft --benef communal    # чернетка заявки
python -m grant_radar serve                     # дашборд на http://localhost:8000
```

І не забудьте додати вміст заповненого файлу в Secret `MEMORY_YAML` (крок 4),
щоб агент писав чернетки й у хмарі.

---

## Контрольний чеклист

- [ ] Файли залиті, у списку видно `.github/workflows/monitor.yml` і `.gitignore`
- [ ] Settings → Actions → **Read and write permissions**
- [ ] Secret `GROQ_API_KEY` додано
- [ ] Settings → Pages → Source: **GitHub Actions**
- [ ] Actions → Run workflow → зелена галочка
- [ ] Дашборд відкривається: https://adanossot04-spec.github.io/kp-grant-radar/
- [ ] `config/memory.yaml` заповнено локально + додано в Secret `MEMORY_YAML`

---

## Якщо щось пішло не так

| Симптом | Рішення |
|---|---|
| `remote: Permission to ... denied` при push | використайте Personal Access Token замість пароля |
| Workflow не з'явився у вкладці Actions | не завантажилась папка `.github/` — створіть файл вручну (крок 1, п.5) |
| `403` на кроці «Зберегти базу та сайт» | не виконано крок 2 |
| Pages показує 404 | не обрано Source: GitHub Actions, або workflow ще не завершився |
| У логах `LLM вимкнено (немає ключа)` | секрет має називатися рівно `GROQ_API_KEY` |
| Cron не спрацьовує | GitHub вимикає розклад після 60 днів без активності — зайдіть в Actions і натисніть «Enable workflow» |

Повна документація: [README.md](../README.md) ·
[docs/DEPLOY-GITHUB.md](DEPLOY-GITHUB.md) · [docs/FREE-APIS.md](FREE-APIS.md)
