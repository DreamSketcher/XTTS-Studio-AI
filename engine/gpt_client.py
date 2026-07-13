"""
engine/gpt_client.py — AI client for XTTS Studio (Groq + OpenRouter + российский OpenAI-совместимый прокси)

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

import json
import os
import urllib.error
import urllib.request

# Локализация подписей провайдеров (i18n не зависит от tkinter)
from i18n import t as _t


class GroqRateLimitError(RuntimeError):
    """429 — лимит токенов/запросов на стороне провайдера для конкретной модели."""

    pass


class GroqNetworkError(RuntimeError):
    """Сетевая ошибка: нет соединения, разрыв, таймаут и т.п. (не лимит)."""

    pass


# ── paths ──────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SETTINGS_PATH = os.path.join(_BASE_DIR, "gpt_settings.json")

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
        "extra_headers": {"HTTP-Referer": "https://xtts-studio.local", "X-Title": "XTTS Studio"},
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

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(models_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("data", [])
        ids = []
        for item in items:
            mid = item.get("id", "")
            # Фильтруем не-чат модели (embeddings, image, audio и т.п.)
            itype = (item.get("type") or item.get("architecture", {}).get("modality") or "").lower()
            if any(x in itype for x in ("embed", "image", "audio", "vision")):
                continue
            if mid:
                ids.append(mid)
        return sorted(ids)
    except Exception:
        return []


def _read_settings() -> dict:
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_settings(patch: dict):
    data = _read_settings()
    data.update(patch)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
    return _read_settings().get(f"api_key_{provider}", "")


def set_api_key(key: str, provider: str = None):
    provider = provider or get_provider()
    _write_settings({f"api_key_{provider}": key.strip()})


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
    items = _read_settings().get("key_library", [])
    if not isinstance(items, list):
        return []
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

    entry = {"id": str(_uuid.uuid4()), "label": label, "provider": provider, "key": key}

    items = _read_settings().get("key_library", [])
    if not isinstance(items, list):
        items = []
    items.append(entry)
    _write_settings({"key_library": items})
    return entry


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
                it["key"] = key.strip()
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
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
) -> dict:
    pid = pid.strip()
    if not pid:
        raise ValueError("ID провайдера пустой")
    existing = [p["id"] for p in list_custom_providers()]
    if pid in existing:
        raise ValueError(f"Провайдер с ID {pid!r} уже существует")

    entry = {
        "id": pid,
        "label": label.strip() or pid,
        "url": url.strip(),
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
    items = list_custom_providers()
    for it in items:
        if it.get("id") == pid:
            for k, v in kwargs.items():
                it[k] = v
            break
    _write_settings({"custom_providers": items})


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
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
        headers["X-Title"] = "XTTS Studio"

    extra = info.get("extra_headers", {})
    if extra and isinstance(extra, dict):
        headers.update(extra)

    req = urllib.request.Request(
        info["url"],
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
        return (
            True,
            f"✅ Ключ рабочий. Провайдер: {info['label']} · Модель: {info['default_model']}",
        )
    except RuntimeError as e:
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
