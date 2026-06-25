"""
engine/gpt_client.py — Groq API client for XTTS Studio

Provides:
  - chat(prompt, history)      — free chat with conversation history
  - improve_for_tts(text)      — rewrite text for better TTS output
  - get_api_key() / set_api_key() — key management (saved to gpt_settings.json)
"""

import os
import json
import urllib.request
import urllib.error

# ── paths ──────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SETTINGS_PATH = os.path.join(_BASE_DIR, "gpt_settings.json")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

AVAILABLE_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# ── key / model management ─────────────────────────────────────────────────────

def get_api_key() -> str:
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("api_key", "")
    except Exception:
        return ""


def set_api_key(key: str):
    data = {}
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        pass
    data["api_key"] = key.strip()
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_model() -> str:
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("model", DEFAULT_MODEL)
    except Exception:
        return DEFAULT_MODEL


def set_model(model: str):
    data = {}
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        pass
    data["model"] = model
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── low-level API call ─────────────────────────────────────────────────────────

def _call_groq(messages: list, model: str = None, max_tokens: int = 2048) -> str:
    key = get_api_key()
    if not key:
        raise RuntimeError(
            "API-ключ Groq не задан.\n"
            "Нажмите ⚙ Настройки GPT и введите ключ.\n"
            "Получить бесплатно: console.groq.com"
        )

    if model is None:
        model = get_model()

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urllib.request.Request(
        GROQ_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            msg = json.loads(body)["error"]["message"]
        except Exception:
            msg = body[:300]
        raise RuntimeError(f"Groq API error {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Сетевая ошибка: {e.reason}")

    return result["choices"][0]["message"]["content"].strip()


# ── system prompts ─────────────────────────────────────────────────────────────

_CHAT_SYSTEM = (
    "Ты помощник для работы с текстом и озвучкой. "
    "Помогаешь редактировать, улучшать и подготавливать тексты для синтеза речи (TTS). "
    "Отвечай чётко и по делу. Если нужно вернуть готовый текст — только текст, без лишних пояснений."
)

_TTS_SYSTEM = (
    "Ты редактор текстов для синтеза речи (TTS). "
    "Твоя задача — улучшить текст так, чтобы голосовая модель читала его естественно и чисто.\n\n"
    "Правила:\n"
    "1. Раскрой сокращения: «т.е.» → «то есть», «и т.д.» → «и так далее».\n"
    "2. Числа пиши словами только если это улучшает читаемость.\n"
    "3. Убери или замени символы, которые TTS читает плохо: %, №, &, @, * → словами.\n"
    "4. Разбей слишком длинные предложения на короткие (до 20 слов).\n"
    "5. Сохрани смысл, стиль и язык оригинала.\n"
    "6. Верни только готовый текст, без комментариев и пояснений."
)


# ── public API ─────────────────────────────────────────────────────────────────

def chat(prompt: str, history: list = None) -> str:
    """
    Free chat. history — list of {"role": "user"/"assistant", "content": "..."}.
    """
    messages = [{"role": "system", "content": _CHAT_SYSTEM}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    return _call_groq(messages)


def improve_for_tts(text: str) -> str:
    """Rewrite text for better TTS synthesis."""
    if not text or not text.strip():
        raise ValueError("Текст пустой")
    messages = [
        {"role": "system", "content": _TTS_SYSTEM},
        {"role": "user", "content": text},
    ]
    return _call_groq(messages, max_tokens=4096)


def validate_key(key: str) -> tuple:
    """Test API key. Returns (ok: bool, message: str)."""
    if not key or not key.strip():
        return False, "Ключ не введён"
    old_key = get_api_key()
    set_api_key(key)
    try:
        result = _call_groq(
            [{"role": "user", "content": "ping"}],
            model=DEFAULT_MODEL,
            max_tokens=5,
        )
        return True, f"✅ Ключ рабочий. Модель: {DEFAULT_MODEL}"
    except RuntimeError as e:
        return False, f"❌ {e}"
    finally:
        set_api_key(old_key)