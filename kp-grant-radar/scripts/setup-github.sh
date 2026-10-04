#!/usr/bin/env bash
# Перший завантаження проєкту на GitHub.
# Використання:  bash scripts/setup-github.sh <github-акаунт> [назва-репозиторію]
# Приклад:       bash scripts/setup-github.sh ivanenko kp-grant-radar
set -euo pipefail

ACCOUNT="${1:-}"
REPO="${2:-kp-grant-radar}"

if [[ -z "$ACCOUNT" ]]; then
  echo "Вкажіть акаунт GitHub:  bash scripts/setup-github.sh <акаунт> [репозиторій]"
  exit 1
fi

cd "$(dirname "$0")/.."

echo "▌ Перевірка структури проєкту…"
for f in README.md requirements.txt .github/workflows/monitor.yml \
         config/sources.yaml config/profile.yaml config/memory.yaml \
         src/grant_radar/__main__.py; do
  [[ -f "$f" ]] || { echo "  ✗ немає файлу $f"; exit 1; }
done
echo "  ✓ усі ключові файли на місці"

# Захист від випадкової публікації персональних даних
if grep -qE '^\s*(iban_uah|edrpou|legal_name_uk):\s*"[^"]+"' config/memory.yaml 2>/dev/null; then
  echo
  echo "⚠️  У config/memory.yaml уже є заповнені реквізити."
  echo "    Переконайтесь, що репозиторій ПРИВАТНИЙ, або додайте файл у .gitignore."
  read -r -p "    Продовжити? [y/N] " answer
  [[ "${answer,,}" == "y" ]] || exit 1
fi

echo "▌ Ініціалізація git…"
[[ -d .git ]] || git init -q
git add -A
git commit -q -m "Грант-радар: моніторинг грантів для комунальних і приватних підприємств" || \
  echo "  (нових змін немає)"
git branch -M main

if git remote | grep -q '^origin$'; then
  git remote set-url origin "https://github.com/$ACCOUNT/$REPO.git"
else
  git remote add origin "https://github.com/$ACCOUNT/$REPO.git"
fi

echo "▌ Відправка на https://github.com/$ACCOUNT/$REPO …"
echo "   (якщо попросить пароль — введіть Personal Access Token:"
echo "    https://github.com/settings/tokens → Generate new token (classic) → область repo)"
git push -u origin main

cat <<EOF

✅ Готово. Далі в браузері:
   1) Settings → Actions → General → Workflow permissions → Read and write → Save
   2) Settings → Secrets and variables → Actions → New repository secret:
        GROQ_API_KEY       (безкоштовно: https://console.groq.com/keys)
        TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  — за бажання
   3) Settings → Pages → Source: GitHub Actions   (лише для публічного репозиторію)
   4) Actions → «Грант-радар — моніторинг» → Run workflow

   Детально: docs/DEPLOY-GITHUB.md
EOF
