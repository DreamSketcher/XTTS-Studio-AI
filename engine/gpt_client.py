"""
engine/gpt_client.py — AI client for XTTS Studio AI (Groq + OpenRouter + российский OpenAI-совместимый прокси)

Provides:
  - chat(prompt, history)          — free chat with conversation history
  - improve_for_tts(text)          — rewrite text for better TTS output
  - get_api_key() / set_api_key()  — key management for active provider
  - get_provider() / set_provider()— "groq" | "openrouter" | "proxy"
  - get_model() / set_model()      — модель активного провайдера

Зачем нужны "openrouter" и "proxy":
  Groq (и большинство западных AI-API) недоступны из России без VPN.

  "openrouter" — сам сервис OpenRouter (openrouter.ai). Его сайт и API
  не блокируются в РФ и работают без VPN; единственное ограничение —
  оплата российской картой может не пройти (нужна крипта/посредник),
  на сам доступ к API это не влияет.

  "proxy" — российский OpenAI-совместимый агрегатор (ProxyAPI / AITUNNEL /
  VseGPT — любой из них подходит, т.к. все говорят одним протоколом
  /v1/chat/completions). Работает напрямую из РФ, без VPN, оплата в рублях.
  Чтобы переключиться — достаточно изменить PROXY_BASE_URL ниже на адрес
  выбранного сервиса и указать его ключ в настройках приложения.
"""

import ipaddress
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

# Локализация подписей провайдеров (i18n не зависит от tkinter)
from i18n import t as _t
from engine.secret_store import is_protected, protect_secret, unprotect_secret


class GroqRateLimitError(RuntimeError):
    """429 — лимит токенов/запросов на стороне провайдера для конкретной модели."""

    pass


class GroqNetworkError(RuntimeError):
    """Сетевая ошибка: нет соединения, разрыв, таймаут и т.п. (не лимит)."""

    pass


# ── paths ──────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SETTINGS_PATH = os.path.join(_BASE_DIR, "json", "gpt_settings.json")

# ── providers ──────────────────────────────────────────────────────────────────
# Любой OpenAI-совместимый эндпоинт подходит для "proxy" — просто поменяйте
# PROXY_BASE_URL на нужный сервис:
#   ProxyAPI   -> "https://api.proxyapi.ru/openai/v1/chat/completions"
#   AITUNNEL   -> "https://api.aitunnel.ru/v1/chat/completions"
#   VseGPT     -> "https://api.vsegpt.ru/v1/chat/completions"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
PROXY_BASE_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

PROVIDERS = {
    "groq": {
        "label": _t("prov_groq"),
        "url": GROQ_API_URL,
        "default_model": "llama-3.3-70b-versatile",
        "fallback_model": "llama-3.1-8b-instant",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ],
        "key_hint": "https://console.groq.com/keys",
    },
    "openrouter": {
        "label": _t("prov_openrouter"),
        "url": OPENROUTER_API_URL,
        "default_model": "openai/gpt-4o-mini",
        "fallback_model": "meta-llama/llama-3.1-8b-instruct:free",
        "models": [
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-3.5-sonnet",
            "deepseek/deepseek-chat",
            "meta-llama/llama-3.1-8b-instruct:free",
        ],
        # OpenRouter требует доп. заголовки (необязательные, но рекомендуемые
        # самим сервисом) — см. _EXTRA_HEADERS ниже.
        "key_hint": "https://openrouter.ai/keys",
    },
    "proxy": {
        "label": _t("prov_proxy"),
        "url": PROXY_BASE_URL,
        "default_model": "gpt-4o-mini",
        "fallback_model": "gpt-4o-mini",
        "models": [
            "gpt-4o-mini",
            "gpt-4o",
            "deepseek-chat",
            "claude-3-5-haiku",
        ],
        "key_hint": "https://proxyapi.ru/cabinet/",
    },
    "local": {
        "label": "Локальная модель",
        "url": None,
        "default_model": "",
        "fallback_model": "",
        "models": [],
        "key_hint": "",
    },
}

DEFAULT_PROVIDER = "groq"

# TASK-005: sensitive-заголовки, которые кастомный провайдер НЕ может переопределить
# через extra_headers (case-insensitive). Попытка override — warning в лог, заголовок
# игнорируется (приложение не падает); реальные Authorization/Content-Type и т.п.
# выставляются кодом и остаются неприкосновенными.
_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "host",
        "content-length",
        "content-type",
        "transfer-encoding",
        "cookie",
        "set-cookie",
        "proxy-authorization",
    }
)


def _apply_extra_headers(headers: dict, extra: dict) -> None:
    """Применяет extra-заголовки провайдера, блокируя sensitive override (TASK-005)."""
    for key, value in (extra or {}).items():
        if str(key).lower() in _SENSITIVE_HEADERS:
            print(f"[GPT] Игнорирую попытку переопределить sensitive-заголовок: {key}")
            continue
        headers[key] = value


# ── i18n refresh ────────────────────────────────────────────────────────────────
# Подписи провайдеров вычисляются при импорте. При живом переключении языка
# в приложении вызывается refresh_i18n_labels(), чтобы обновить их без
# перезапуска (окно настроек AI пересоздаётся и подхватит новые подписи).
_PROVIDER_LABEL_KEYS = {"groq": "prov_groq", "openrouter": "prov_openrouter", "proxy": "prov_proxy"}
_CATALOGUE_I18N = {
    "openrouter": {"notes": "cat_openrouter_notes"},
    "together": {"notes": "cat_together_notes"},
    "mistral": {"notes": "cat_mistral_notes"},
    "deepinfra": {"notes": "cat_deepinfra_notes"},
    "vsegpt": {"label": "cat_vsegpt_label", "notes": "cat_vsegpt_notes"},
    "aitunnel": {"label": "cat_aitunnel_label", "notes": "cat_aitunnel_notes"},
    "proxyapi": {"label": "cat_proxyapi_label", "notes": "cat_proxyapi_notes"},
}


def refresh_i18n_labels():
    """Обновляет подписи провайдеров под текущий язык интерфейса."""
    try:
        for pid, key in _PROVIDER_LABEL_KEYS.items():
            if pid in PROVIDERS:
                PROVIDERS[pid]["label"] = _t(key)
        for entry in PROVIDER_CATALOGUE:
            keys = _CATALOGUE_I18N.get(entry.get("id"))
            if keys:
                for field, key in keys.items():
                    entry[field] = _t(key)
    except Exception:
        pass


# Обратная совместимость со старым кодом, который импортирует DEFAULT_MODEL /
# AVAILABLE_MODELS / FALLBACK_MODEL напрямую (chat_window.py читает их через
# getattr с фоллбэком, так что наличие этих имён ничего не ломает).
DEFAULT_MODEL = PROVIDERS["groq"]["default_model"]
AVAILABLE_MODELS = PROVIDERS["groq"]["models"]
FALLBACK_MODEL = PROVIDERS["groq"]["fallback_model"]

# ── provider catalogue ─────────────────────────────────────────────────────────
# Встроенный каталог известных OpenAI-совместимых провайдеров.
# models_url — эндпоинт GET /v1/models (None если не поддерживается).
PROVIDER_CATALOGUE = [
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "models_url": "https://openrouter.ai/api/v1/models",
        "key_hint": "https://openrouter.ai/keys",
        "extra_headers": {"HTTP-Referer": "https://xtts-studio.local", "X-Title": "XTTS Studio AI"},
        "notes": _t("cat_openrouter_notes"),
        "models": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemini-2.0-flash-001",
            "deepseek/deepseek-chat-v3-0324:free",
            "openai/gpt-4o-mini",
            "mistralai/mistral-nemo:free",
        ],
    },
    {
        "id": "together",
        "label": "Together AI",
        "url": "https://api.together.xyz/v1/chat/completions",
        "models_url": "https://api.together.xyz/v1/models",
        "key_hint": "https://api.together.ai/settings/api-keys",
        "extra_headers": {},
        "notes": _t("cat_together_notes"),
        "models": [
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "meta-llama/Llama-3.1-8B-Instruct-Turbo",
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "deepseek-ai/DeepSeek-V3",
            "google/gemma-2-27b-it",
        ],
    },
    {
        "id": "mistral",
        "label": "Mistral AI",
        "url": "https://api.mistral.ai/v1/chat/completions",
        "models_url": "https://api.mistral.ai/v1/models",
        "key_hint": "https://console.mistral.ai/api-keys",
        "extra_headers": {},
        "notes": _t("cat_mistral_notes"),
        "models": [
            "mistral-large-latest",
            "mistral-small-latest",
            "codestral-latest",
            "open-mixtral-8x22b",
            "open-mistral-nemo",
        ],
    },
    {
        "id": "deepinfra",
        "label": "DeepInfra",
        "url": "https://api.deepinfra.com/v1/openai/chat/completions",
        "models_url": "https://api.deepinfra.com/v1/openai/models",
        "key_hint": "https://deepinfra.com/dash/api_keys",
        "extra_headers": {},
        "notes": _t("cat_deepinfra_notes"),
        "models": [
            "meta-llama/Llama-3.3-70B-Instruct",
            "meta-llama/Llama-3.1-8B-Instruct",
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
        ],
    },
    {
        "id": "vsegpt",
        "label": _t("cat_vsegpt_label"),
        "url": "https://api.vsegpt.ru/v1/chat/completions",
        "models_url": "https://api.vsegpt.ru/v1/models",
        "key_hint": "https://vsegpt.ru/cabinet/",
        "extra_headers": {},
        "notes": _t("cat_vsegpt_notes"),
        "models": [
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-3-5-haiku",
            "meta-llama/llama-3.3-70b-instruct",
            "deepseek/deepseek-chat",
        ],
    },
    {
        "id": "aitunnel",
        "label": _t("cat_aitunnel_label"),
        "url": "https://api.aitunnel.ru/v1/chat/completions",
        "models_url": "https://api.aitunnel.ru/v1/models",
        "key_hint": "https://aitunnel.ru/cabinet/",
        "extra_headers": {},
        "notes": _t("cat_aitunnel_notes"),
        "models": [
            "gpt-4o-mini",
            "gpt-4o",
            "claude-3-5-haiku",
            "deepseek-chat",
            "gemini-2.0-flash",
        ],
    },
    {
        "id": "proxyapi",
        "label": _t("cat_proxyapi_label"),
        "url": "https://api.proxyapi.ru/openai/v1/chat/completions",
        "models_url": "https://api.proxyapi.ru/openai/v1/models",
        "key_hint": "https://proxyapi.ru/cabinet/",
        "extra_headers": {},
        "notes": _t("cat_proxyapi_notes"),
        "models": [
            "gpt-4o-mini",
            "gpt-4o",
            "o1-mini",
            "deepseek-chat",
            "claude-3-5-haiku",
        ],
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "url": "https://api.openai.com/v1/chat/completions",
        "models_url": "https://api.openai.com/v1/models",
        "key_hint": "https://platform.openai.com/api-keys",
        "extra_headers": {},
        "notes": _t("cat_openai_notes"),
        "models": [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1-mini",
            "gpt-4.1",
            "o4-mini",
        ],
    },
    {
        "id": "anthropic",
        "label": "Anthropic (Claude)",
        "url": "https://api.anthropic.com/v1/chat/completions",
        "key_hint": "https://console.anthropic.com/settings/keys",
        "extra_headers": {},
        "notes": _t("cat_anthropic_notes"),
        "models": [
            "claude-3-5-haiku-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-7-sonnet-latest",
        ],
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "models_url": "https://generativelanguage.googleapis.com/v1beta/openai/models",
        "key_hint": "https://aistudio.google.com/apikey",
        "extra_headers": {},
        "notes": _t("cat_gemini_notes"),
        "models": [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ],
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "url": "https://api.deepseek.com/v1/chat/completions",
        "models_url": "https://api.deepseek.com/v1/models",
        "key_hint": "https://platform.deepseek.com/api_keys",
        "extra_headers": {},
        "notes": _t("cat_deepseek_notes"),
        "models": [
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    },
    {
        "id": "xai",
        "label": "xAI (Grok)",
        "url": "https://api.x.ai/v1/chat/completions",
        "models_url": "https://api.x.ai/v1/models",
        "key_hint": "https://console.x.ai/",
        "extra_headers": {},
        "notes": _t("cat_xai_notes"),
        "models": [
            "grok-3-mini",
            "grok-3",
            "grok-4",
        ],
    },
    {
        "id": "cerebras",
        "label": "Cerebras",
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "models_url": "https://api.cerebras.ai/v1/models",
        "key_hint": "https://cloud.cerebras.ai/",
        "extra_headers": {},
        "notes": _t("cat_cerebras_notes"),
        "models": [
            "llama-3.3-70b",
            "llama-3.1-8b",
            "llama-4-scout-17b-16e-instruct",
        ],
    },
    {
        "id": "sambanova",
        "label": "SambaNova",
        "url": "https://api.sambanova.ai/v1/chat/completions",
        "models_url": "https://api.sambanova.ai/v1/models",
        "key_hint": "https://cloud.sambanova.ai/",
        "extra_headers": {},
        "notes": _t("cat_sambanova_notes"),
        "models": [
            "Meta-Llama-3.3-70B-Instruct",
            "DeepSeek-R1-Distill-Llama-70B",
            "Qwen2.5-72B-Instruct",
        ],
    },
    {
        "id": "fireworks",
        "label": "Fireworks AI",
        "url": "https://api.fireworks.ai/inference/v1/chat/completions",
        "models_url": "https://api.fireworks.ai/inference/v1/models",
        "key_hint": "https://fireworks.ai/account/api-keys",
        "extra_headers": {},
        "notes": _t("cat_fireworks_notes"),
        "models": [
            "accounts/fireworks/models/llama-v3p3-70b-instruct",
            "accounts/fireworks/models/mixtral-8x22b-instruct",
            "accounts/fireworks/models/qwen2p5-72b-instruct",
        ],
    },
    {
        "id": "novita",
        "label": "Novita AI",
        "url": "https://api.novita.ai/v3/openai/chat/completions",
        "models_url": "https://api.novita.ai/v3/openai/models",
        "key_hint": "https://novita.ai/dashboard/keys",
        "extra_headers": {},
        "notes": _t("cat_novita_notes"),
        "models": [
            "deepseek/deepseek-v3-turbo",
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen2.5-72b-instruct",
        ],
    },
    {
        "id": "hyperbolic",
        "label": "Hyperbolic",
        "url": "https://api.hyperbolic.xyz/v1/chat/completions",
        "models_url": "https://api.hyperbolic.xyz/v1/models",
        "key_hint": "https://app.hyperbolic.xyz/settings",
        "extra_headers": {},
        "notes": _t("cat_hyperbolic_notes"),
        "models": [
            "meta-llama/Llama-3.3-70B-Instruct",
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
        ],
    },
    {
        "id": "nvidia",
        "label": "NVIDIA NIM",
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "models_url": "https://integrate.api.nvidia.com/v1/models",
        "key_hint": "https://build.nvidia.com/",
        "extra_headers": {},
        "notes": _t("cat_nvidia_notes"),
        "models": [
            "meta/llama-3.3-70b-instruct",
            "deepseek-ai/deepseek-r1",
            "qwen/qwen2.5-72b-instruct",
        ],
    },
    {
        "id": "chutes",
        "label": "Chutes AI",
        "url": "https://llm.chutes.ai/v1/chat/completions",
        "models_url": "https://llm.chutes.ai/v1/models",
        "key_hint": "https://chutes.ai/",
        "extra_headers": {},
        "notes": _t("cat_chutes_notes"),
        "models": [
            "deepseek-ai/DeepSeek-V3",
            "meta-llama/Llama-3.3-70B-Instruct",
            "Qwen/Qwen2.5-72B-Instruct",
        ],
    },
    {
        "id": "ollama",
        "label": "Ollama (local)",
        "url": "http://localhost:11434/v1/chat/completions",
        "models_url": "http://localhost:11434/v1/models",
        "key_hint": "",
        "extra_headers": {},
        "notes": _t("cat_ollama_notes"),
        "models": [
            "llama3.3",
            "qwen2.5",
            "mistral",
        ],
    },
    {
        "id": "lmstudio",
        "label": "LM Studio (local)",
        "url": "http://localhost:1234/v1/chat/completions",
        "models_url": "http://localhost:1234/v1/models",
        "key_hint": "",
        "extra_headers": {},
        "notes": _t("cat_lmstudio_notes"),
        "models": [
            "local-model",
        ],
    },
]


def fetch_models_from_url(models_url: str, api_key: str = "") -> list[str]:
    """
    GET models_url -> список model id строк.
    Поддерживает стандартный OpenAI-формат {"data": [{"id": ...}]}
    и OpenRouter-формат {"data": [{"id": ..., "name": ...}]}.
    Возвращает пустой список при любой ошибке.
    """
    if not models_url:
        return []
    try:
        models_url = _validate_api_url(models_url)
    except ValueError:
        return []

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(models_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    return _parse_models_payload(data)


def _parse_models_payload(data) -> list[str]:
    """
    Нормализовать ответ /v1/models в список model id.
    Поддерживает:
      * OpenAI/OpenRouter: {"data": [{"id": "...", "type": "...", "architecture": {...}}]}
      * Google Gemini:     {"models": [{"name": "models/gemini-...",
        "supportedGenerationMethods": [...]}]}
    Не-чат модели (embeddings, image, audio, rerank, moderation) отфильтровываются.
    """
    # Мусор/не тот формат — тихо возвращаем пусто
    if not isinstance(data, dict):
        return []

    ids: list[str] = []

    if isinstance(data.get("data"), list):
        for item in data["data"]:
            if not isinstance(item, dict):
                continue
            mid = str(item.get("id") or "").strip()
            if not mid:
                continue
            arch = item.get("architecture")
            if not isinstance(arch, dict):
                arch = {}
            itype = str(item.get("type") or arch.get("modality") or "").lower()
            if any(
                x in itype
                for x in (
                    "embed",
                    "image",
                    "audio",
                    "tts",
                    "speech",
                    "rerank",
                    "moderation",
                    "whisper",
                    "guard",
                )
            ):
                continue
            ids.append(mid)
    elif isinstance(data.get("models"), list):
        # Gemini: только модели, умеющие generateContent
        for item in data["models"]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("id") or "").strip()
            if name.startswith("models/"):
                name = name[len("models/") :]
            methods = item.get("supportedGenerationMethods")
            if isinstance(methods, list) and "generateContent" not in methods:
                continue
            if name:
                ids.append(name)

    return sorted(dict.fromkeys(ids))


def _validate_api_url(url: str, *, allow_loopback_http: bool = True) -> str:
    """Accept HTTPS endpoints and, optionally, explicit loopback HTTP only."""
    value = str(url or "").strip()
    parsed = urllib.parse.urlsplit(value)
    if parsed.username or parsed.password:
        raise ValueError("URL с учётными данными запрещён")
    if parsed.fragment:
        raise ValueError("Fragment в API URL запрещён")
    if not parsed.hostname or parsed.scheme not in ("https", "http"):
        raise ValueError("API URL должен использовать https://")
    if parsed.scheme == "http":
        is_loopback = parsed.hostname.lower() == "localhost"
        try:
            is_loopback = is_loopback or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            pass
        if not (allow_loopback_http and is_loopback):
            raise ValueError("Незашифрованный HTTP разрешён только для localhost")
    return value


def _read_settings() -> dict:
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_all_settings(data: dict):
    """Atomically replace settings so interruption cannot truncate the JSON."""
    directory = os.path.dirname(os.path.abspath(_SETTINGS_PATH))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".gpt_settings_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, _SETTINGS_PATH)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def _write_settings(patch: dict):
    data = _read_settings()
    data.update(patch)
    _write_all_settings(data)


# ── provider cache & health tracking ───────────────────────────────────────────
# Механизм отслеживания актуального состояния провайдеров: отдельный кэш
# json/provider_cache.json — без секретов. Хранит живые списки моделей и
# результат последней проверки (ok / invalid_key / rate_limited / network_error /
# models_error / unchecked). Файл кэша можно смело удалять — он восстановится.


def _cache_path() -> str:
    # Лениво — уважает monkeypatched _BASE_DIR в тестах.
    return os.path.join(_BASE_DIR, "json", "provider_cache.json")


MODELS_CACHE_TTL = 24 * 60 * 60  # 24 часа: старше — требует обновления

PROVIDER_HEALTH_STATES = (
    "unchecked",
    "ok",
    "invalid_key",
    "rate_limited",
    "network_error",
    "models_error",
    "error",
)


def _read_cache() -> dict:
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            models = data.get("models")
            health = data.get("health")
            return {
                "models": models if isinstance(models, dict) else {},
                "health": health if isinstance(health, dict) else {},
            }
    except Exception:
        pass
    return {"models": {}, "health": {}}


def _write_cache(cache: dict):
    try:
        cache_path = _cache_path()
        directory = os.path.dirname(os.path.abspath(cache_path))
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".provider_cache_", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, cache_path)
        except Exception:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            raise
    except Exception as e:  # кэш — не критичные данные, не роняем приложение
        print(f"[AI] Не удалось записать provider_cache.json: {e}")


def derive_models_url(url: str) -> str | None:
    """
    Вывести endpoint /v1/models из chat/completions endpoint или базового URL.
    Возвращает None, если вывести нельзя (пустой url).
    """
    value = str(url or "").strip().rstrip("/")
    if not value:
        return None
    for suffix in ("/chat/completions", "/responses", "/completions"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    if value.endswith("/models"):
        return value
    return value + "/models"


def _catalogue_entry(pid: str) -> dict:
    for entry in PROVIDER_CATALOGUE:
        if entry.get("id") == pid:
            return entry
    return {}


def effective_models_url(pid: str) -> str | None:
    """URL /v1/models для любого провайдера: custom → catalogue → вывод из url."""
    try:
        info = get_provider_info(pid)
    except KeyError:
        return None
    # 1) Явно сохранённый models_url (пользовательский провайдер)
    explicit = str(info.get("models_url") or "").strip()
    if explicit:
        return explicit
    # 2) Каталог (подходит и для встроенных провайдеров openai/openrouter/...)
    cat_entry = _catalogue_entry(pid)
    cat_url = str(cat_entry.get("models_url") or "").strip()
    if cat_url:
        return cat_url
    # 3) Выводим из chat endpoint
    return derive_models_url(str(info.get("url") or ""))


def get_cached_models(pid: str) -> list[str]:
    """Живые модели из кэша без похода в сеть (пустой список, если кэша нет)."""
    entry = _read_cache()["models"].get(pid) or {}
    models = entry.get("models")
    return [str(m) for m in models] if isinstance(models, list) else []


def get_models_cache_meta(pid: str) -> dict:
    """Метаданные кэша моделей.

    Возвращает {"models": [...], "ts": float|None, "url": str|None, "ok": bool, "error": str|None}.
    """
    meta = {"models": [], "ts": None, "url": None, "ok": False, "error": None}
    entry = _read_cache()["models"].get(pid) or {}
    if not isinstance(entry, dict):
        return meta
    models = entry.get("models")
    if isinstance(models, list):
        meta["models"] = [str(m) for m in models]
    meta["ts"] = entry.get("ts") if isinstance(entry.get("ts"), (int, float)) else None
    meta["url"] = entry.get("url") or None
    meta["ok"] = bool(entry.get("ok"))
    meta["error"] = entry.get("error") or None
    return meta


def get_provider_models(pid: str) -> dict:
    """
    Что показывать в UI: live-кэш → встроенный/каталожный список → пусто.
    Возвращает {"models": [...], "source": "live"|"builtin"|"none",
                "ts": float|None, "fresh": bool, "url": str|None, "error": str|None}
    """
    meta = get_models_cache_meta(pid)
    fresh = bool(meta["ts"]) and (time.time() - meta["ts"] < MODELS_CACHE_TTL)
    if meta["models"]:
        return {
            "models": meta["models"],
            "source": "live",
            "ts": meta["ts"],
            "fresh": fresh,
            "url": meta["url"],
            "error": meta["error"],
        }
    # Кэш пуст/нет — отдаём встроенный список (seed) как временную опору
    builtin: list[str] = []
    try:
        info = get_provider_info(pid)
        builtin = [str(m) for m in (info.get("models") or [])]
    except KeyError:
        pass
    if not builtin:
        builtin = [str(m) for m in (_catalogue_entry(pid).get("models") or [])]
    return {
        "models": builtin,
        "source": "builtin" if builtin else "none",
        "ts": None,
        "fresh": False,
        "url": effective_models_url(pid),
        "error": meta["error"],
    }


def record_provider_state(pid: str, state: str, detail: str = ""):
    """Записать результат последней проверки провайдера (health tracking)."""
    if state not in PROVIDER_HEALTH_STATES:
        state = "error"
    cache = _read_cache()
    cache["health"][pid] = {"state": state, "detail": str(detail or "")[:300], "ts": time.time()}
    _write_cache(cache)


def get_provider_health(pid: str = None):
    """Состояние одного провайдера или всех: {"state": ..., "detail": ..., "ts": ...}."""
    health = _read_cache()["health"]

    def _norm(entry):
        if not isinstance(entry, dict):
            return {"state": "unchecked", "detail": "", "ts": None}
        return {
            "state": entry.get("state") or "unchecked",
            "detail": entry.get("detail") or "",
            "ts": entry.get("ts") if isinstance(entry.get("ts"), (int, float)) else None,
        }

    if pid is not None:
        return _norm(health.get(pid))
    return {k: _norm(v) for k, v in health.items()}


def clear_provider_cache(pid: str):
    """Удалить кэш моделей и health-записи провайдера (после смены url/удаления)."""
    cache = _read_cache()
    removed = False
    for section in ("models", "health"):
        if pid in cache[section]:
            del cache[section][pid]
            removed = True
    if removed:
        _write_cache(cache)


def refresh_provider_models(pid: str, *, force: bool = False, timeout: int = 10):
    """
    Подтянуть актуальный список моделей из /v1/models и закэшировать его.

    Возвращает (models, error): при успехе error is None; при ошибке —
    (возможно устаревшие кэшированные модели, текст ошибки).
    TTL: если кэш свежее MODELS_CACHE_TTL и not force — сеть не дёргаем.
    Заодно обновляет health-состояние провайдера.
    """
    meta = get_models_cache_meta(pid)
    fresh = bool(meta["ts"]) and (time.time() - meta["ts"] < MODELS_CACHE_TTL)
    if fresh and not force and meta["models"]:
        return list(meta["models"]), None

    models_url = effective_models_url(pid)
    if not models_url:
        # local / или невозможно вывести — health не портим, возвращаем seed
        return get_provider_models(pid)["models"], None

    try:
        api_key = get_api_key(pid)
    except Exception:
        api_key = ""

    error_detail = None
    models: list[str] = []
    try:
        req = urllib.request.Request(
            _validate_api_url(models_url),
            headers=(
                {
                    "Content-Type": "application/json",
                    **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
                }
            ),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        models = _parse_models_payload(payload)
        if not models:
            error_detail = "endpoint вернул пустой или нераспознанный список моделей"
            record_provider_state(pid, "models_error", error_detail)
    except ValueError as e:
        error_detail = str(e)
        record_provider_state(pid, "models_error", error_detail)
    except urllib.error.HTTPError as e:
        code = getattr(e, "code", 0) or 0
        if code in (401, 403):
            error_detail = f"HTTP {code}: ключ не подходит"
            record_provider_state(pid, "invalid_key", error_detail)
        elif code == 429:
            error_detail = "HTTP 429: превышен лимит запросов"
            record_provider_state(pid, "rate_limited", error_detail)
        else:
            error_detail = f"HTTP {code}"
            record_provider_state(pid, "models_error", error_detail)
    except Exception as e:
        error_detail = str(e)
        record_provider_state(pid, "network_error", error_detail)

    cache = _read_cache()
    if models:
        cache["models"][pid] = {
            "models": models,
            "ts": time.time(),
            "url": models_url,
            "ok": True,
            "error": None,
        }
        _write_cache(cache)
        record_provider_state(pid, "ok", f"моделей: {len(models)}")
        return models, None

    # Ошибка: сохраняем старые модели (stale) и фиксируем ошибку
    prev = cache["models"].get(pid) or {}
    prev_models = prev.get("models") if isinstance(prev.get("models"), list) else []
    cache["models"][pid] = {
        "models": [str(m) for m in prev_models],
        "ts": prev.get("ts"),
        "url": prev.get("url") or models_url,
        "ok": False,
        "error": error_detail,
    }
    _write_cache(cache)
    stale = get_provider_models(pid)["models"]
    return stale, error_detail


def validate_provider_models_url(models_url: str, api_key: str = ""):
    """
    Проверить произвольный models endpoint (для формы провайдера).
    Возвращает (ok, message, models). Ничего не сохраняет.
    """
    url = str(models_url or "").strip()
    if not url:
        return False, "Пустой URL", []
    try:
        _validate_api_url(url)
    except ValueError as e:
        return False, str(e), []
    models = fetch_models_from_url(url, api_key)
    if models:
        return True, f"Ок: {len(models)} моделей", models
    return False, "Не удалось получить список моделей (проверьте URL и ключ)", []


# ── provider management ─────────────────────────────────────────────────────────


def get_provider() -> str:
    val = _read_settings().get("provider", DEFAULT_PROVIDER)
    all_ids = set(PROVIDERS.keys()) | {p["id"] for p in list_custom_providers()}
    return val if val in all_ids else DEFAULT_PROVIDER


def set_provider(provider: str):
    all_ids = list(PROVIDERS.keys()) + [p["id"] for p in list_custom_providers()]
    if provider not in all_ids:
        raise ValueError(f"Неизвестный провайдер: {provider!r}")
    _write_settings({"provider": provider})


def get_provider_info(provider: str = None) -> dict:
    pid = provider or get_provider()
    if pid in PROVIDERS:
        return PROVIDERS[pid]
    for p in list_custom_providers():
        if p.get("id") == pid:
            return p
    raise KeyError(f"Провайдер {pid!r} не найден")


# ── key / model management (per-provider) ──────────────────────────────────────
# Ключи храним раздельно по провайдеру (api_key_groq / api_key_proxy), чтобы
# переключение провайдера в настройках не затирало второй ключ.


def get_api_key(provider: str = None) -> str:
    provider = provider or get_provider()
    field = f"api_key_{provider}"
    stored = _read_settings().get(field, "")
    if not stored:
        return ""
    secret = unprotect_secret(stored)
    if not is_protected(stored):
        # One-time migration from legacy plaintext; fail closed if protected
        # storage is unavailable rather than continuing to retain plaintext.
        _write_settings({field: protect_secret(secret)})
    return secret


def set_api_key(key: str, provider: str = None):
    provider = provider or get_provider()
    value = key.strip()
    _write_settings({f"api_key_{provider}": protect_secret(value) if value else ""})


def get_model(provider: str = None) -> str:
    provider = provider or get_provider()
    info = get_provider_info(provider)
    val = _read_settings().get(f"model_{provider}", info["default_model"])
    return val if val else info["default_model"]


def set_model(model: str, provider: str = None):
    provider = provider or get_provider()
    _write_settings({f"model_{provider}": model})


def get_fallback_model(provider: str = None) -> str:
    provider = provider or get_provider()
    return get_provider_info(provider)["fallback_model"]


# ── key library (несколько именованных ключей на провайдера) ──────────────────
# Хранится в gpt_settings.json -> "key_library": [{"id", "label", "provider", "key"}, ...]
# Это НЕЗАВИСИМО от api_key_<provider> (тот хранит "текущий активный" ключ).
# Библиотека — это просто записная книжка ключей, из которой можно одним
# кликом подставить нужный ключ в активный слот провайдера.


def list_keys(provider: str = None) -> list:
    """Вернуть список сохранённых ключей. Если provider задан — только для него."""
    stored_items = _read_settings().get("key_library", [])
    if not isinstance(stored_items, list):
        return []
    items = []
    migration_needed = False
    migrated = []
    for raw in stored_items:
        if not isinstance(raw, dict):
            continue
        entry = dict(raw)
        stored_key = str(entry.get("key") or "")
        plain_key = unprotect_secret(stored_key) if stored_key else ""
        entry["key"] = plain_key
        items.append(entry)
        protected_entry = dict(raw)
        if stored_key and not is_protected(stored_key):
            protected_entry["key"] = protect_secret(plain_key)
            migration_needed = True
        migrated.append(protected_entry)
    if migration_needed:
        _write_settings({"key_library": migrated})
    if provider:
        return [it for it in items if it.get("provider") == provider]
    return items


def add_key(label: str, key: str, provider: str = None) -> dict:
    """Добавить ключ в библиотеку. Возвращает добавленную запись."""
    import uuid as _uuid

    provider = provider or get_provider()
    label = (label or "").strip() or f"Ключ {provider}"
    key = (key or "").strip()
    if not key:
        raise ValueError("Ключ пустой")

    entry = {
        "id": str(_uuid.uuid4()),
        "label": label,
        "provider": provider,
        "key": protect_secret(key),
    }

    items = _read_settings().get("key_library", [])
    if not isinstance(items, list):
        items = []
    items.append(entry)
    _write_settings({"key_library": items})
    return {**entry, "key": key}


def update_key(key_id: str, *, label: str = None, key: str = None):
    """Обновить запись в библиотеке по id."""
    items = _read_settings().get("key_library", [])
    if not isinstance(items, list):
        return
    changed = False
    for it in items:
        if it.get("id") == key_id:
            if label is not None:
                it["label"] = label.strip()
                changed = True
            if key is not None:
                value = key.strip()
                it["key"] = protect_secret(value) if value else ""
                changed = True
    if changed:
        _write_settings({"key_library": items})


def delete_key(key_id: str):
    """Удалить запись из библиотеки по id."""
    items = _read_settings().get("key_library", [])
    if not isinstance(items, list):
        return
    new_items = [it for it in items if it.get("id") != key_id]
    if len(new_items) != len(items):
        _write_settings({"key_library": new_items})


# ── custom providers ───────────────────────────────────────────────────────────


def get_hidden_providers() -> set:
    return set(_read_settings().get("hidden_providers", []))


def hide_provider(pid: str):
    if pid not in PROVIDERS:
        raise ValueError(f"{pid!r} не встроенный провайдер")
    hidden = get_hidden_providers()
    hidden.add(pid)
    data = _read_settings()
    data["hidden_providers"] = list(hidden)
    data.pop(f"api_key_{pid}", None)
    data.pop(f"model_{pid}", None)
    _write_all_settings(data)


def show_provider(pid: str):
    hidden = get_hidden_providers()
    hidden.discard(pid)
    _write_settings({"hidden_providers": list(hidden)})


def list_custom_providers() -> list:
    items = _read_settings().get("custom_providers", [])
    return items if isinstance(items, list) else []


def add_custom_provider(
    pid: str,
    label: str,
    url: str,
    models: list,
    fallback: str,
    headers: dict = None,
    key_hint: str = "",
    models_url: str = "",
) -> dict:
    pid = pid.strip()
    if not pid:
        raise ValueError("ID провайдера пустой")
    existing = [p["id"] for p in list_custom_providers()]
    if pid in existing:
        raise ValueError(f"Провайдер с ID {pid!r} уже существует")

    validated_url = _validate_api_url(url)
    validated_models_url = ""
    if str(models_url or "").strip():
        validated_models_url = _validate_api_url(models_url)
    entry = {
        "id": pid,
        "label": label.strip() or pid,
        "url": validated_url,
        "models_url": validated_models_url,
        "key_hint": key_hint or "",
        "default_model": models[0] if models else "",
        "fallback_model": fallback.strip() or (models[0] if models else ""),
        "models": [m.strip() for m in models if m.strip()],
        "extra_headers": headers or {},
    }
    items = list_custom_providers()
    items.append(entry)
    _write_settings({"custom_providers": items})
    return entry


def update_custom_provider(pid: str, **kwargs):
    url_changed = False
    if "url" in kwargs:
        new_url = _validate_api_url(kwargs["url"])
        url_changed = True
        kwargs["url"] = new_url
    if "models_url" in kwargs:
        mu = str(kwargs.get("models_url") or "").strip()
        if mu:
            mu = _validate_api_url(mu)
        kwargs["models_url"] = mu
        url_changed = True
    items = list_custom_providers()
    for it in items:
        if it.get("id") == pid:
            for k, v in kwargs.items():
                it[k] = v
            break
    _write_settings({"custom_providers": items})
    if url_changed:
        try:
            clear_provider_cache(pid)
        except Exception:
            pass


def delete_custom_provider(pid: str):
    items = [p for p in list_custom_providers() if p.get("id") != pid]
    data = _read_settings()
    data["custom_providers"] = items
    # чистим все возможные варианты ключей
    for key in list(data.keys()):
        if key in (f"api_key_{pid}", f"model_{pid}"):
            del data[key]
    # если это был активный провайдер — сбрасываем на дефолт
    if data.get("provider") == pid:
        data["provider"] = DEFAULT_PROVIDER
    _write_all_settings(data)
    try:
        clear_provider_cache(pid)
    except Exception:
        pass


def get_key_entry(key_id: str):
    for it in list_keys():
        if it.get("id") == key_id:
            return it
    return None


def apply_key_from_library(key_id: str) -> dict:
    """
    Подставить ключ из библиотеки как активный для его провайдера
    (и переключить активный провайдер на тот, к которому привязан ключ).
    Возвращает применённую запись.
    """
    entry = get_key_entry(key_id)
    if not entry:
        raise ValueError(f"Ключ с id={key_id!r} не найден в библиотеке")

    provider = entry.get("provider") or get_provider()
    set_api_key(entry.get("key", ""), provider)
    set_provider(provider)
    return entry


# ── low-level API call ─────────────────────────────────────────────────────────


def _call_api(
    messages: list, model: str = None, max_tokens: int = 2048, provider: str = None
) -> str:
    provider = provider or get_provider()

    if provider == "local":
        from engine import local_llm_client

        model = model or get_model(provider)
        try:
            return local_llm_client.call_local_llm(messages, model=model, max_tokens=max_tokens)
        except RuntimeError as e:
            # Сервер локальной модели недоступен/не запущен — трактуем как
            # сетевую ошибку, чтобы _call_with_chain корректно перешёл дальше.
            raise GroqNetworkError(str(e))

    info = get_provider_info(provider)

    key = get_api_key(provider)
    if not key:
        raise RuntimeError(
            f"API-ключ для «{info['label']}» не задан.\n"
            f"Нажмите ⚙ Настройки GPT и введите ключ.\n"
            f"{info['key_hint']}"
        )

    if not model:
        model = get_model(provider)

    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }

    # OpenRouter рекомендует (не обязательно, но влияет на отображение
    # приложения в их статистике/рейтингах) передавать эти два заголовка.
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://xtts-studio.local"
        headers["X-Title"] = "XTTS Studio AI"

    extra = info.get("extra_headers", {})
    if extra and isinstance(extra, dict):
        _apply_extra_headers(headers, extra)

    endpoint_url = _validate_api_url(info["url"])
    req = urllib.request.Request(
        endpoint_url,
        data=payload,
        headers=headers,
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
        if e.code == 429 or "rate limit" in msg.lower() or "rate_limit" in msg.lower():
            raise GroqRateLimitError(f"{info['label']} error 429: {msg}")
        if e.code in (503, 502, 500) or ("model" in msg.lower() and "unavailable" in msg.lower()):
            raise GroqRateLimitError(f"{info['label']} error {e.code} (модель недоступна): {msg}")
        if e.code == 404 and "no endpoints found" in msg.lower():
            raise GroqRateLimitError(f"{info['label']} error 404 (модель снята): {msg}")
        raise RuntimeError(f"{info['label']} error {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise GroqNetworkError(
            f"Сетевая ошибка ({info['label']}): {e.reason}\n"
            f"Проверьте подключение или смените провайдера в настройках AI."
        )
    except (ConnectionError, TimeoutError, OSError) as e:
        raise GroqNetworkError(f"Сетевая ошибка ({info['label']}): {e}")

    return result["choices"][0]["message"]["content"].strip()


# Старое имя функции — для совместимости с любым кодом, который мог звать
# _call_groq напрямую (chat_window.py делает это в фоллбэк-ветке при 429).
def _call_groq(messages: list, model: str = None, max_tokens: int = 2048) -> str:
    return _call_api(messages, model=model, max_tokens=max_tokens, provider=get_provider())


# ── unified provider-chain fallback ─────────────────────────────────────────
# Единая точка входа для всех AI-вызовов (chat, improve_for_tts, conduct).
# Логика:
#   - сетевая ошибка (нет интернета у пользователя) -> сразу прерываем всю
#     цепочку, дальше пробовать бессмысленно
#   - ошибка конкретного провайдера (лимит, 5xx, невалидный ключ) -> пробуем
#     следующую модель / следующего провайдера в цепочке
#   - провайдеры без сохранённого ключа пропускаются молча (с записью в лог)
#   - если цепочка закончилась без успеха -> возвращаем None, как при сети


class AIUnavailable(RuntimeError):
    """ИИ временно недоступен (сеть или вся цепочка провайдеров) — не баг, не показываем messagebox."""

    pass


def _provider_available(pid: str) -> bool:
    """Есть ли у провайдера всё нужное для вызова: API-ключ (обычные)
    или выбранная модель (local — своя проверка, без ключа)."""
    if pid == "local":
        try:
            from engine import local_llm_client

            return local_llm_client.get_active_model() is not None
        except Exception:
            return False
    return bool(get_api_key(pid))


def _build_provider_chain() -> list:
    chain = []

    # Сначала — выбранный пользователем провайдер
    active = get_provider()
    if _provider_available(active):
        chain.append(active)

    # Затем остальные встроенные
    for pid in PROVIDERS.keys():
        if pid == active:
            continue
        if pid in get_hidden_providers():
            continue
        if _provider_available(pid):
            chain.append(pid)

    # Затем кастомные
    for p in list_custom_providers():
        pid = p.get("id")
        if pid == active:
            continue
        if _provider_available(pid):
            chain.append(pid)

    return chain


def get_chain_diagnostics() -> dict:
    """
    Структурированная диагностика цепочки провайдеров — без парсинга
    print()/консоли. Используется UI для окна "🔌 AI статус".

    Возвращает:
        {
            "active": "groq",                  # id активного провайдера
            "chain_order": ["groq", "proxy"],   # реальный порядок fallback
            "providers": [
                {
                    "id": "groq",
                    "label": "Groq (нужен VPN из РФ)",
                    "status": "active" | "in_chain" | "skipped" | "hidden",
                    "reason": "человекочитаемая причина",
                    "has_key": True/False,
                    "model": "llama-3.3-70b-versatile",
                    "builtin": True/False,
                },
                ...
            ]
        }
    """
    active = get_provider()
    hidden = get_hidden_providers()

    def _entry(pid, info, is_active):
        has_key = bool(get_api_key(pid))
        is_hidden = pid in hidden
        if is_active:
            status, reason = "active", _t("prov_reason_active")
        elif is_hidden:
            status, reason = "hidden", _t("prov_reason_hidden")
        elif not has_key:
            status, reason = "skipped", _t("prov_reason_no_key")
        else:
            status, reason = "in_chain", _t("prov_reason_fallback")
        return {
            "id": pid,
            "label": info.get("label", pid),
            "status": status,
            "reason": reason,
            "has_key": has_key,
            "model": get_model(pid) if (has_key or is_active) else info.get("default_model", ""),
            "builtin": pid in PROVIDERS,
        }

    entries = []

    if active in PROVIDERS:
        entries.append(_entry(active, PROVIDERS[active], True))
    else:
        custom_active = next((p for p in list_custom_providers() if p.get("id") == active), None)
        if custom_active:
            entries.append(_entry(active, custom_active, True))

    for pid, info in PROVIDERS.items():
        if pid == active:
            continue
        entries.append(_entry(pid, info, False))

    for p in list_custom_providers():
        pid = p.get("id")
        if pid == active:
            continue
        entries.append(_entry(pid, p, False))

    return {
        "active": active,
        "chain_order": _build_provider_chain(),
        "providers": entries,
    }


def _call_with_chain(messages: list, max_tokens: int = 2048) -> str:
    """
    Пробует все провайдеры из цепочки по очереди (primary, затем fallback модель
    каждого). Сетевая ошибка прерывает попытки ТОЛЬКО для текущего провайдера
    (этот конкретный хост недоступен — например геоблокировка), переходим
    к следующему провайдеру в цепочке. Если ВСЕ провайдеры упёрлись в сетевую
    ошибку — это уже похоже на отсутствие интернета у пользователя в принципе.
    Если цепочка исчерпана по любой причине — поднимает AIUnavailable.
    """
    chain = _build_provider_chain()
    if not chain:
        raise AIUnavailable("Нет ни одного провайдера с сохранённым ключом")

    network_failures = 0
    total_attempts = 0

    for provider in chain:
        primary = get_model(provider)
        fallback = get_fallback_model(provider)
        models_to_try = [primary] if primary == fallback else [primary, fallback]

        for model in models_to_try:
            total_attempts += 1
            try:
                return _call_api(messages, model=model, max_tokens=max_tokens, provider=provider)
            except GroqNetworkError as e:
                network_failures += 1
                print(f"[AI] {provider}/{model}: недоступен по сети ({e}), пробую дальше...")
                continue
            except GroqRateLimitError:
                print(f"[AI] {provider}/{model}: лимит/недоступна, пробую дальше...")
                continue
            except Exception as e:
                print(f"[AI] {provider}/{model}: ошибка — {e}")
                continue

    if total_attempts > 0 and network_failures == total_attempts:
        # Абсолютно все попытки упали по сети -> похоже на отсутствие интернета у пользователя
        raise AIUnavailable("Нет подключения к интернету")

    raise AIUnavailable("Все провайдеры в цепочке недоступны (лимиты/ключи/сеть)")


# ── system prompts ─────────────────────────────────────────────────────────────

_CHAT_SYSTEM = (
    "Ты помощник для работы с текстом и озвучкой. "
    "Помогаешь редактировать, улучшать и подготавливать тексты для синтеза речи (TTS). "
    "Отвечай чётко и по делу. Если нужно вернуть готовый текст — только текст, без лишних пояснений."
)

FREE_CHAT_SYSTEM = (
    "Ты умный и полезный AI-ассистент. " "Отвечай чётко, по делу, на том же языке что и вопрос."
)
_FREE_CHAT_SYSTEM = (
    FREE_CHAT_SYSTEM  # алиас для обратной совместимости, если где-то ещё используется старое имя
)

_TTS_SYSTEM = (
    "Ты редактор текстов для синтеза речи (TTS). "
    "Твоя задача — ТОЛЬКО техническая подготовка текста к озвучке, а НЕ переписывание или улучшение стиля.\n\n"
    "ГЛАВНОЕ ОГРАНИЧЕНИЕ: запрещено менять смысл, факты, порядок событий, добавлять или убирать "
    "информацию, заменять слова синонимами без технической необходимости. Если сомневаешься, "
    "нужна ли правка — не делай её и оставь как в оригинале.\n\n"
    "Правила:\n"
    "1. Раскрой сокращения: «т.е.» → «то есть», «и т.д.» → «и так далее».\n"
    "2. Числа пиши словами только если это улучшает читаемость.\n"
    "3. Убери или замени символы, которые TTS читает плохо: %, №, &, @, * → словами.\n"
    "4. Разбей слишком длинные предложения на короткие (до 20 слов), не меняя их смысл и не переставляя части.\n"
    "5. Исправляй только явные орфографические и пунктуационные ошибки.\n"
    "6. Сохрани смысл, факты, стиль и язык оригинала дословно там, где это не мешает пункту 1–3.\n"
    "7. Верни только готовый текст, без комментариев и пояснений."
)


# ── public API ─────────────────────────────────────────────────────────────────


def chat(prompt: str, history: list = None, system: str = None) -> str:
    """
    Free chat. history — list of {"role": "user"/"assistant", "content": "..."}.
    Пробует все провайдеры из цепочки (см. _call_with_chain).
    Поднимает AIUnavailable если ИИ временно недоступен — это не баг,
    вызывающий код должен обработать это мягко (без messagebox с ошибкой).
    """
    messages = [{"role": "system", "content": system or _CHAT_SYSTEM}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    return _call_with_chain(messages, max_tokens=2048)


def improve_for_tts(text: str) -> str:
    if not text or not text.strip():
        raise ValueError("Текст пустой")

    messages = [
        {"role": "system", "content": _TTS_SYSTEM},
        {"role": "user", "content": text},
    ]

    try:
        return _call_with_chain(messages, max_tokens=4096)
    except AIUnavailable as e:
        # ИИ недоступен (сеть пользователя или вся цепочка провайдеров исчерпана) —
        # это не ошибка, продолжаем без AI-улучшения, текст идёт как есть.
        print(f"[GPT] improve_for_tts: ИИ недоступен ({e}), возвращаю текст без изменений")
        return text


def preprocess_for_tts(text: str, mode: str = "assistant") -> str:
    """
    Обёртка над GPT-обработкой текста для TTS с поддержкой режимов (mode).
    Сейчас поддерживается только mode="assistant" (= improve_for_tts).
    Новые режимы добавлять сюда, не трогая improve_for_tts/_TTS_SYSTEM.
    """
    if mode == "assistant":
        return improve_for_tts(text)

    raise ValueError(
        f"preprocess_for_tts: неизвестный mode={mode!r}. " f"Доступные режимы: 'assistant'."
    )


def validate_key(key: str, provider: str = None) -> tuple:
    """Test API key for given (or current) provider. Returns (ok: bool, message: str)."""
    provider = provider or get_provider()
    info = get_provider_info(provider)

    if not key or not key.strip():
        return False, "Ключ не введён"

    old_key = get_api_key(provider)
    set_api_key(key, provider)
    try:
        _call_api(
            [{"role": "user", "content": "ping"}],
            model=info["default_model"],
            max_tokens=5,
            provider=provider,
        )
        record_provider_state(provider, "ok", "ключ принят")
        return (
            True,
            f"✅ Ключ рабочий. Провайдер: {info['label']} · Модель: {info['default_model']}",
        )
    except GroqNetworkError as e:
        record_provider_state(provider, "network_error", str(e))
        return False, f"❌ {e}"
    except GroqRateLimitError as e:
        record_provider_state(provider, "rate_limited", str(e))
        return False, f"❌ {e}"
    except RuntimeError as e:
        detail = str(e).lower()
        if any(
            x in detail
            for x in (
                "401",
                "403",
                "unauthorized",
                "forbidden",
                "invalid",
                "api key",
                "api-key",
                "apikey",
                "auth",
            )
        ):
            record_provider_state(provider, "invalid_key", str(e))
        else:
            record_provider_state(provider, "error", str(e))
        return False, f"❌ {e}"
    finally:
        set_api_key(old_key, provider)


# ── UI state (для аккордеона настроек) ─────────────────────────────────────────


def get_ui_state() -> dict:
    return _read_settings().get("ui_state", {})


def set_ui_state(**kwargs):
    state = get_ui_state()
    state.update(kwargs)
    _write_settings({"ui_state": state})
