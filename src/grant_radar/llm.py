"""AI-шар на БЕЗКОШТОВНИХ API (опційний).

Жоден платний сервіс не потрібен. Агент автоматично знаходить перший доступний
безкоштовний провайдер за змінними оточення (у GitHub — Actions Secrets):

    GROQ_API_KEY       — Groq, безкоштовний tier (llama-3.3-70b)   https://console.groq.com/keys
    GEMINI_API_KEY     — Google Gemini free tier (gemini-2.0-flash) https://aistudio.google.com/apikey
    OPENROUTER_API_KEY — OpenRouter, моделі з суфіксом :free        https://openrouter.ai/keys
    CEREBRAS_API_KEY   — Cerebras free tier                         https://cloud.cerebras.ai
    MISTRAL_API_KEY    — Mistral free tier                          https://console.mistral.ai
    OLLAMA_BASE_URL    — локальна модель (повністю безкоштовно)     http://localhost:11434/v1
    OPENAI_API_KEY     — будь-який інший OpenAI-сумісний сервіс (опційно)

Усі перелічені провайдери мають OpenAI-сумісний /chat/completions, тому код один.
Якщо ключів немає — агент працює лише на правилах, нічого не ламається.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

log = logging.getLogger(__name__)

# (назва, env-ключ, base_url, модель за замовчуванням)
PROVIDERS: list[tuple[str, str, str, str]] = [
    ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    ("gemini", "GEMINI_API_KEY",
     "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash"),
    ("openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1",
     "meta-llama/llama-3.3-70b-instruct:free"),
    ("cerebras", "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1", "llama-3.3-70b"),
    ("mistral", "MISTRAL_API_KEY", "https://api.mistral.ai/v1", "mistral-small-latest"),
    ("openai", "OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o-mini"),
]

SYSTEM = """Ти — експерт з грантового фандрейзингу для українських комунальних підприємств,
органів місцевого самоврядування та приватного бізнесу. Оцінюєш, чи варто конкретній
організації витрачати час на цю можливість фінансування.
Відповідаєш ВИКЛЮЧНО валідним JSON без markdown-огорожі."""

USER_TMPL = """ПРОФІЛЬ ОРГАНІЗАЦІЇ:
{profile}

МОЖЛИВІСТЬ:
Джерело: {source}
Назва: {title}
Програма: {programme}
Статус: {status}
Дедлайн: {deadline}
Опис: {summary}
Посилання: {url}

Поверни JSON:
{{
  "score": 0-100,
  "beneficiary": "communal" | "private" | "both" | "unknown",
  "summary_uk": "2-3 речення українською: суть, хто фінансує, на що гроші",
  "fit_uk": "1-2 речення: чому підходить або не підходить цій організації",
  "eligible": true/false,
  "actions_uk": "конкретні наступні кроки: що підготувати, кого залучити, на що звернути увагу"
}}"""


class LLMAnalyzer:
    def __init__(self, profile_text: str) -> None:
        self.profile_text = profile_text
        self.provider, self.api_key, self.base_url, self.model = self._detect()

    @staticmethod
    def _detect() -> tuple[str, str, str, str]:
        forced = os.getenv("LLM_PROVIDER", "").strip().lower()
        candidates = [p for p in PROVIDERS if not forced or p[0] == forced]
        for name, env, base, model in candidates:
            key = os.getenv(env, "").strip()
            if key:
                return (name, key,
                        os.getenv("LLM_BASE_URL", "").strip() or base,
                        os.getenv("LLM_MODEL", "").strip() or model)
        # локальна модель без ключа (Ollama / LM Studio)
        local = os.getenv("OLLAMA_BASE_URL", "").strip()
        if local:
            return ("ollama", "none", local.rstrip("/"),
                    os.getenv("LLM_MODEL", "llama3.1:8b"))
        return ("", "", "", "")

    @property
    def enabled(self) -> bool:
        return bool(self.provider)

    def chat(self, system: str, user: str, max_tokens: int = 900) -> str | None:
        if not self.enabled:
            return None
        try:
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.model,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}],
                      "temperature": 0.2, "max_tokens": max_tokens},
                timeout=120,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            log.warning("LLM (%s): %s", self.provider, exc)
            return None

    def analyze(self, opp: dict[str, Any] | Any) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        get = (lambda k: opp.get(k, "")) if isinstance(opp, dict) else (lambda k: getattr(opp, k, ""))
        prompt = USER_TMPL.format(
            profile=self.profile_text.strip(),
            source=get("source_name"), title=get("title"), programme=get("programme") or "—",
            status=get("status") or "—", deadline=get("deadline_at") or "не вказано",
            summary=(get("summary") or "")[:2500], url=get("url"),
        )
        content = self.chat(SYSTEM, prompt, max_tokens=700)
        return _parse_json(content) if content else None


def _parse_json(content: str) -> dict[str, Any] | None:
    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None
