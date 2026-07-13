"""
engine/local_llm_client.py — локальные GGUF-модели через llama-cpp-python
(инференс прямо в процессе приложения, без внешних серверов вроде Ollama).
"""

import json
import os
import shutil
import sys
import threading
import urllib.error
import urllib.request

# Убеждаемся, что папка, куда ставится llama-cpp-python, есть в sys.path
# (актуально для bundled/python и portable-окружений)
try:
    from engine import env_setup

    if env_setup.SITE_PACKAGES not in sys.path:
        sys.path.insert(0, env_setup.SITE_PACKAGES)
except Exception:
    pass

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SETTINGS_PATH = os.path.join(_BASE_DIR, "gpt_settings.json")
MODELS_DIR = os.path.join(_BASE_DIR, "models")

os.makedirs(MODELS_DIR, exist_ok=True)

# ── Каталог известных моделей (прямые ссылки на .gguf) ────────────────────────
# quant: коэффициент GB на 1B параметров для данной квантизации
LOCAL_MODEL_CATALOG = [
    {
        "id": "tinyllama-1.1b-q4",
        "label": "TinyLlama 1.1B Chat (Q4_K_M)",
        "params_b": 1.1,
        "quant": "Q4_K_M",
        "quant_factor": 0.60,
        "description": "Очень компактная модель для слабых CPU. Подходит для тестов и простых задач.",
        "download_link": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "filename": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
    },
    {
        "id": "phi-3-mini-3.8b-q4",
        "label": "Phi-3 Mini 3.8B (Q4_K_M)",
        "params_b": 3.8,
        "quant": "Q4_K_M",
        "quant_factor": 0.60,
        "description": "Хороший баланс качества и скорости. Работает на CPU и средних GPU.",
        "download_link": "https://huggingface.co/bartowski/Phi-3-mini-4k-instruct-GGUF/resolve/main/Phi-3-mini-4k-instruct-Q4_K_M.gguf",
        "filename": "Phi-3-mini-4k-instruct-Q4_K_M.gguf",
    },
    {
        "id": "qwen2.5-7b-q4",
        "label": "Qwen2.5 7B (Q4_K_M)",
        "params_b": 7.0,
        "quant": "Q4_K_M",
        "quant_factor": 0.60,
        "description": "Сильная многоязычная модель. Требует ~4.5 GB RAM/VRAM.",
        "download_link": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
    },
    {
        "id": "llama-3.1-8b-q4",
        "label": "Llama 3.1 8B (Q4_K_M)",
        "params_b": 8.0,
        "quant": "Q4_K_M",
        "quant_factor": 0.60,
        "description": "Популярная универсальная модель. Требует ~5 GB RAM/VRAM.",
        "download_link": "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "filename": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    },
    {
        "id": "mistral-7b-q4",
        "label": "Mistral 7B (Q4_K_M)",
        "params_b": 7.0,
        "quant": "Q4_K_M",
        "quant_factor": 0.60,
        "description": "Быстрая и качественная модель для диалогов. Требует ~4.5 GB RAM/VRAM.",
        "download_link": "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "filename": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
    },
]


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


# ── Установленные модели (persisted список, не статика) ────────────────────────


def get_last_model_dir() -> str:
    """Последняя папка, из которой выбирали файл модели."""
    return _read_settings().get("last_model_dir", "")


def set_last_model_dir(path: str):
    """Сохранить папку файла модели для следующего диалога."""
    if path:
        _write_settings({"last_model_dir": os.path.dirname(os.path.abspath(path))})


# ── Оценка совместимости и скачивание моделей ─────────────────────────────────


def _get_system_ram_gb() -> float:
    try:
        import psutil

        return psutil.virtual_memory().available / (1024**3)
    except Exception:
        return 8.0  # безопасный дефолт


def estimate_memory_gb(params_b: float, quant_factor: float) -> float:
    """Оценка требуемой RAM/VRAM в GB для модели."""
    return params_b * quant_factor


def is_model_downloaded(filename: str) -> bool:
    return os.path.isfile(os.path.join(MODELS_DIR, filename))


def get_model_file_path(filename: str) -> str:
    return os.path.join(MODELS_DIR, filename)


def _download_checkpoint_path(filename: str) -> str:
    return os.path.join(MODELS_DIR, f".download_{filename}.json")


def _load_download_checkpoint(filename: str) -> dict:
    path = _download_checkpoint_path(filename)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_download_checkpoint(filename: str, offset: int, total: int, url: str):
    data = {"filename": filename, "offset": offset, "total": total, "url": url}
    try:
        with open(_download_checkpoint_path(filename), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _clear_download_checkpoint(filename: str):
    try:
        path = _download_checkpoint_path(filename)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def get_compatible_models(ram_gb: float = None, vram_gb: float = None) -> list:
    """
    Возвращает каталог моделей с флагами совместимости.
    Каждая запись дополняется полями:
      - memory_gb: требуемая память
      - compatible: True/False
      - installed: True/False
    """
    available = max(ram_gb or 0, vram_gb or 0, _get_system_ram_gb())
    result = []
    for m in LOCAL_MODEL_CATALOG:
        mem = estimate_memory_gb(m.get("params_b", 0), m.get("quant_factor", 0.6))
        entry = dict(m)
        entry["memory_gb"] = mem
        entry["installed"] = is_model_downloaded(m.get("filename", ""))
        # Небольшой запас (1.5 GB) на систему и другие процессы
        entry["compatible"] = available >= mem + 1.5
        result.append(entry)
    return result


def download_model(
    url: str, filename: str, progress_cb=None, cancelled_flag=None, resume: bool = False
) -> str:
    """
    Скачивает .gguf по url в MODELS_DIR с поддержкой resume и отмены.
    progress_cb(line: str) — вызывается на каждом блоке.
    cancelled_flag — dict/list с ключом/индексом 'cancelled' для остановки.
    resume=True — продолжить скачивание с места остановки.
    Возвращает путь к сохранённому файлу.
    """
    if not url:
        raise ValueError("URL модели не указан")

    dest_path = os.path.join(MODELS_DIR, filename)
    temp_path = dest_path + ".tmp"

    def emit(line):
        if progress_cb:
            progress_cb(line)

    def is_cancelled() -> bool:
        if cancelled_flag is None:
            return False
        if isinstance(cancelled_flag, dict):
            return bool(cancelled_flag.get("cancelled"))
        if isinstance(cancelled_flag, list) and len(cancelled_flag) > 0:
            return bool(cancelled_flag[0])
        return False

    # Загружаем чекпоинт, если resume
    checkpoint = _load_download_checkpoint(filename) if resume else {}
    offset = checkpoint.get("offset", 0) if resume and checkpoint.get("url") == url else 0
    total = checkpoint.get("total", 0)

    try:
        headers = {"User-Agent": "XTTS-Studio/1.0"}
        if offset > 0:
            headers["Range"] = f"bytes={offset}-"
            emit(f"Продолжаю скачивание {filename} с {offset / (1024**2):.1f} MB...")
        else:
            emit(f"Скачивание {filename}...")

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            # Если сервер не поддерживает Range — сбрасываем offset
            if offset > 0 and response.status != 206:
                emit("Сервер не поддерживает докачку — начинаю сначала.")
                offset = 0

            if offset == 0:
                total = int(response.headers.get("Content-Length", 0))

            downloaded = offset
            block_size = 8192
            mode = "ab" if offset > 0 else "wb"
            with open(temp_path, mode) as f:
                while True:
                    if is_cancelled():
                        _save_download_checkpoint(filename, downloaded, total, url)
                        raise InterruptedError("Скачивание отменено пользователем")
                    block = response.read(block_size)
                    if not block:
                        break
                    f.write(block)
                    downloaded += len(block)
                    _save_download_checkpoint(filename, downloaded, total, url)
                    if total:
                        pct = downloaded / total * 100
                        mb = downloaded / (1024**2)
                        total_mb = total / (1024**2)
                        emit(f"\rСкачано: {mb:.1f} / {total_mb:.1f} MB ({pct:.1f}%)")
                    else:
                        emit(f"\rСкачано: {downloaded / (1024 ** 2):.1f} MB")
        os.replace(temp_path, dest_path)
        _clear_download_checkpoint(filename)
        emit(f"✅ Сохранено: {dest_path}")
        return dest_path
    except InterruptedError:
        raise
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Ошибка загрузки {e.code}: {e.reason}")
    except Exception as e:
        # Сохраняем прогресс, чтобы можно было продолжить
        try:
            if os.path.exists(temp_path):
                current = os.path.getsize(temp_path)
                _save_download_checkpoint(filename, current, total, url)
        except Exception:
            pass
        raise RuntimeError(f"Не удалось скачать модель: {e}")
    finally:
        # Удаляем .tmp только при успехе; при отмене/ошибке оставляем для resume
        pass


def install_catalog_model(
    model_id: str, progress_cb=None, cancelled_flag=None, resume: bool = False
) -> dict:
    """
    Скачивает модель из каталога и регистрирует как установленную.
    Возвращает entry установленной модели.
    """
    model = next((m for m in LOCAL_MODEL_CATALOG if m.get("id") == model_id), None)
    if not model:
        raise ValueError(f"Модель {model_id} не найдена в каталоге")

    filename = model.get("filename")
    url = model.get("download_link")
    path = download_model(
        url, filename, progress_cb=progress_cb, cancelled_flag=cancelled_flag, resume=resume
    )
    _clear_download_checkpoint(filename)
    return register_model(path, label=model.get("label"), n_gpu_layers=_default_n_gpu_layers())


def list_installed_models() -> list:
    items = _read_settings().get("installed_local_models", [])
    return items if isinstance(items, list) else []


def _save_installed_models(items: list):
    _write_settings({"installed_local_models": items})


def get_active_model_id() -> str:
    return _read_settings().get("active_local_model_id", "")


def set_active_model_id(model_id: str):
    _write_settings({"active_local_model_id": model_id})


def get_active_model() -> dict:
    """Возвращает запись активной модели (dict) или None."""
    active_id = get_active_model_id()
    for m in list_installed_models():
        if m.get("id") == active_id:
            return m
    return None


def _default_n_gpu_layers() -> int:
    """
    Определяет, сколько слоёв выгружать на GPU.
    -1 = все слои (только если ТОЧНО известно, что установленная сборка
         llama-cpp-python реально собрана с GPU-backend'ом — cuda/vulkan).
     0 = только CPU.

    Важно: раньше здесь проверялось только "GPU физически есть в системе" +
    "llama-cpp-python установлен" — этого недостаточно. Если каскад установки
    (env_setup.install_llama_cpp) откатился с GPU-backend'а на CPU-fallback
    (например, Vulkan-сборка не импортировалась), GPU в системе всё ещё есть,
    но установленная библиотека физически не умеет в GPU-offload. Передача
    n_gpu_layers=-1 в такую сборку роняет процесс C++ исключением
    (0xE06D7363) мимо обычного Python try/except. Поэтому здесь смотрим на
    ФАКТИЧЕСКИ установленный backend (env_setup.get_installed_backend()),
    а не на теоретическую доступность GPU.
    """
    try:
        from engine import env_setup

        backend = env_setup.get_installed_backend()
        if backend in ("cuda", "vulkan"):
            return -1
    except Exception:
        pass
    return 0


def register_model(path: str, label: str = None, n_gpu_layers: int = None) -> dict:
    """Регистрирует уже лежащий по path .gguf как установленную модель."""
    import uuid as _uuid

    filename = os.path.basename(path)
    entry = {
        "id": str(_uuid.uuid4()),
        "filename": filename,
        "path": path,
        "label": label or filename,
        "n_gpu_layers": n_gpu_layers if n_gpu_layers is not None else _default_n_gpu_layers(),
    }
    items = list_installed_models()
    items.append(entry)
    _save_installed_models(items)
    return entry


def remove_model(model_id: str):
    items = [m for m in list_installed_models() if m.get("id") != model_id]
    _save_installed_models(items)
    if get_active_model_id() == model_id:
        _write_settings({"active_local_model_id": ""})
    _unload_if_current(model_id)


def move_model_file(source_path: str, label: str = None) -> dict:
    """
    Переносит .gguf в /models/ и сразу регистрирует как установленную модель.
    Возвращает добавленную запись (entry).
    """
    if not source_path:
        raise ValueError("Путь к файлу не указан")

    filename = os.path.basename(source_path)
    dest_path = os.path.join(MODELS_DIR, filename)

    try:
        if os.path.abspath(source_path) != os.path.abspath(dest_path):
            shutil.move(source_path, dest_path)
    except Exception as e:
        raise RuntimeError(f"Ошибка при перемещении файла модели: {e}")

    return register_model(dest_path, label=label)


# ── In-process инференс через llama-cpp-python ─────────────────────────────────

_loaded_lock = threading.Lock()
_loaded_path = None
_loaded_llm = None


def _unload_if_current(model_id: str):
    global _loaded_path, _loaded_llm
    removed = next((x for x in list_installed_models() if x.get("id") == model_id), None)
    with _loaded_lock:
        if removed and _loaded_path == removed.get("path"):
            _loaded_llm = None
            _loaded_path = None


def _get_llm(path: str):
    global _loaded_path, _loaded_llm

    with _loaded_lock:
        if _loaded_llm is not None and _loaded_path == path:
            return _loaded_llm

        # Убеждаемся, что нужная папка site-packages в путях
        try:
            from engine import env_setup

            if env_setup.SITE_PACKAGES not in sys.path:
                sys.path.insert(0, env_setup.SITE_PACKAGES)
        except Exception:
            pass

        try:
            from llama_cpp import Llama
        except ImportError:
            raise RuntimeError(
                "Библиотека llama-cpp-python не установлена — "
                "локальные модели без неё работать не могут."
            )

        if not os.path.isfile(path):
            raise RuntimeError(f"Файл модели не найден: {path}")

        # Узнаём тренировочный контекст модели заранее (дешёвая операция,
        # только чтение метаданных, без полной загрузки весов)
        try:
            probe = Llama(model_path=path, n_ctx=8, verbose=False, vocab_only=False)
            n_ctx_train = probe.n_ctx_train()
            del probe
        except Exception:
            n_ctx_train = 2048  # безопасный дефолт, если метаданные прочитать не удалось

        safe_ctx = min(4096, n_ctx_train)

        # Определяем n_gpu_layers: из записи модели или дефолт
        entry = None
        for m in list_installed_models():
            if m.get("path") == path:
                entry = m
                break
        n_gpu_layers = entry.get("n_gpu_layers") if entry else None
        if n_gpu_layers is None:
            n_gpu_layers = _default_n_gpu_layers()

        # Подстраховка: если запись модели была создана раньше (со старой
        # логикой _default_n_gpu_layers, до этого фикса) и в ней уже
        # сохранено n_gpu_layers=-1 — всё равно проверяем реальный backend
        # прямо сейчас. GPU-offload физически невозможен в CPU-only сборке
        # независимо от того, что записано в settings.
        try:
            from engine import env_setup

            installed_backend = env_setup.get_installed_backend()
            if installed_backend not in ("cuda", "vulkan") and n_gpu_layers != 0:
                n_gpu_layers = 0
        except Exception:
            pass

        _loaded_llm = Llama(
            model_path=path,
            n_ctx=safe_ctx,
            n_threads=os.cpu_count() or 4,
            n_gpu_layers=n_gpu_layers,
            verbose=True,
        )
        _loaded_path = path
        return _loaded_llm


def call_local_llm(messages: list, model: str = None, max_tokens: int = 2048) -> str:
    """
    Генерирует ответ активной локальной моделью.
    model (опционально) — id установленной модели или прямой путь к .gguf.
    """
    entry = None
    if model:
        entry = next((m for m in list_installed_models() if m.get("id") == model), None)
        path = entry["path"] if entry else model
    else:
        entry = get_active_model()
        if not entry:
            raise RuntimeError("Локальная модель не выбрана. Выберите файл в Настройках AI.")
        path = entry["path"]

    llm = _get_llm(path)

    # Универсальный потолок для CPU-инференса — не даём случайно уйти в
    # многоминутную генерацию на слабом железе.
    max_tokens = min(max_tokens, 256)

    # Стоп-токены нескольких популярных семейств моделей разом — лишние
    # варианты безвредны, если модель их не использует.
    stop_tokens = [
        "</s>",  # Llama-2 / TinyLlama / Mistral (классика)
        "<|im_end|>",  # ChatML — Qwen, многие современные finetune
        "<|eot_id|>",  # Llama-3 / Llama-3.1
        "<end_of_turn>",  # Gemma
        "<|end|>",  # Phi-3
    ]

    try:
        result = llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
            repeat_penalty=1.15,
            stop=stop_tokens,
        )
        return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise RuntimeError(f"Ошибка локальной модели: {e}")
