"""engine/xtts_engine.py — автономная загрузка официального движка XTTS v2.

Зачем: приложение (портативная версия) обновляется по manifest через
`engine/updater.py`, а тяжёлый «движок» — основная модель XTTS v2
(~1,87 ГБ, под `models/xtts_v2/`) — в репозиторий не входит и раньше
поставлялся только вместе с полным multi-GB архивуом. Этот модуль позволяет
докачать движок софициального источника при первом запуске (фоновая
предзагрузка модели в `engine/gui/generation.py`) и после повреждения/
удаления файлов модели.

Модель и сам софт скачиваются ОТДЕЛЬНО: код — из GitHub Releases (updater),
движок — отсюда.

Официальные источники (обе копии — одного и того же репозитория
Coqui XTTS v2, MIT-подобный некоммерческий CPML):
  • primary — HuggingFace `coqui/XTTS-v2`, ЗАКРЕПЛЕНО на ревизии
    ENGINE_REVISION (неизменяемый коммит на момент фиксации каталога);
  • fallback — официальный шлюз Coqui (coqui.gateway.scarf.sh), тот же,
    что использует сам пакет TTS при `TTS(model_name=...)`.

Проверка целостности скачанных файлов (torch.load для .pth исполняет
pickle, поэтому подмена файлов = RCE — проверка ОБЯЗАТЕЛЬНА):
  • model.pth / speakers_xtts.pth — SHA-256 с API HuggingFace
    (LFS oid, официальные значения);
  • model.pth дополнительно — md5 из официального `hash.md5`
    (он же `model_hash` из models.json пакета TTS 0.22.0);
  • config.json / vocab.json — точный размер + разбор JSON
    (+ обязательные поля XTTS-конфига);
  • hash.md5 — точное содержимое.

Скачанные файлы ставятся АТОМАРНО (`.part` → os.replace); проверенные
файлы не перекачиваются; частичная закачка (`*.part`) сохраняется между
запусками для докачки. Содержимое источников НИКОГДА не исполняется
до успешной проверки (кроме распаковки нет ничего — .pth проверяется
хешами ДО передачи в TTS).
"""

import contextlib
import hashlib
import http.client
import json
import os
import ssl
import time
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.join(BASE_DIR, "models", "xtts_v2")

# Ревизия репозитория coqui/XTTS-v2, на которой сняты размеры/хеши каталога
# (main на 2023-12-11; файлы модели не менялись). При обновлении каталога —
# сменить ENGINE_REVISION и размер/хеши файлов ниже.
ENGINE_REVISION = "6c2b0d75eae4b7047358e3b6bd9325f857d43f77"

ENGINE_BASE_URLS = (
    f"https://huggingface.co/coqui/XTTS-v2/resolve/{ENGINE_REVISION}/",
    "https://coqui.gateway.scarf.sh/hf-coqui/XTTS-v2/main/",
)

# Официальный md5 model.pth: файл hash.md5 в репозитории модели, совпадает с
# model_hash из models.json openai/coqui TTS 0.22.0 (пин TTS==0.22.0).
OFFICIAL_MODEL_MD5 = "10f92b55c512af7a8d39d650547a15a7"

# Каталог движка. size — ТОЧНЫЙ размер в байтах (файлы неизменяемы, ревизия
# закреплена). Только перечисленные файлы нужны TTS для загрузки XTTS v2.
ENGINE_FILES = (
    {
        "name": "model.pth",
        "size": 1867929118,
        "sha256": "c7ea20001c6a0a841c77e252d8409f6a74fb423e79b3206a0771ba5989776187",
        "md5": OFFICIAL_MODEL_MD5,
    },
    {
        "name": "speakers_xtts.pth",
        "size": 7754818,
        "sha256": "f0f6137c19a4eab0cbbe4c99b5babacf68b1746e50da90807708c10e645b943b",
    },
    {
        "name": "vocab.json",
        "size": 361219,
        "json": "vocab",
    },
    {
        "name": "config.json",
        "size": 4368,
        "json": "xtts_config",
    },
    {
        "name": "hash.md5",
        "size": 32,
        "md5_file": OFFICIAL_MODEL_MD5,
    },
)

ENGINE_TOTAL_BYTES = sum(entry["size"] for entry in ENGINE_FILES)

_MAX_RETRIES = 5
_RETRY_BACKOFF_SEC = 3
_CHUNK_SIZE = 1024 * 1024  # 1 МБ — прогресс обновляем не чаще раза в МБ

# Обрывы соединения/TLS на уровне сети — повод повторить (с того же оффсета),
# в отличие от HTTP-ответов (404/403/502), где правильнее перейти к следующему
# источнику.
_TRANSIENT_DOWNLOAD_ERRORS = (
    ssl.SSLError,
    TimeoutError,
    ConnectionError,
    EOFError,
    http.client.IncompleteRead,
    http.client.HTTPException,
    OSError,
)

try:
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CONTEXT = None  # certifi не установлен — системные сертификаты


# ── Пути и статус ─────────────────────────────────────────────────────────────


def engine_dir() -> str:
    """Каталог движка XTTS v2 (models/xtts_v2 относительно корня приложения)."""
    return ENGINE_DIR


def _path(entry: dict) -> str:
    return os.path.join(engine_dir(), entry["name"])


def _part_path(entry: dict) -> str:
    return _path(entry) + ".part"


def _sha256_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _md5_of_file(path: str) -> str:
    digest = hashlib.md5()  # noqa: S324 — официальный якорь Coqui (не парольный хеш)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_xtts_config(path: str) -> None:
    """config.json обязан быть XTTS-конфигом (защита от подмены JSON'ом-пустышкой)."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        cfg = json.loads(raw)
    except Exception as e:
        raise ValueError(f"config.json не разобран как JSON: {e}") from e
    if not isinstance(cfg, dict):
        raise ValueError("config.json должен быть JSON-объектом")
    if cfg.get("model") != "xtts":
        raise ValueError(f"config.json: неожиданное поле 'model' = {cfg.get('model')!r}")
    model_args = cfg.get("model_args")
    if not isinstance(model_args, dict) or not model_args:
        raise ValueError("config.json: отсутствует model_args")


def _check_vocab(path: str) -> None:
    with open(path, "rb") as f:
        raw = f.read()
    try:
        vocab = json.loads(raw)
    except Exception as e:
        raise ValueError(f"vocab.json не разобран как JSON: {e}") from e
    if not isinstance(vocab, list | dict) or not vocab:
        raise ValueError("vocab.json должен быть непустым JSON-массивом/объектом")


def _check_md5_file(path: str, expected_md5: str) -> None:
    with open(path, "rb") as f:
        content = f.read().decode("utf-8", errors="replace").strip()
    if content != expected_md5:
        raise ValueError(f"hash.md5 содержит {content!r}, ожидалось {expected_md5!r}")


def verify_engine_file(path: str, entry: dict) -> tuple[bool, str]:
    """Глубокая проверка файла (размер + хеши/структура). Для использования
    после скачивания; при каждом старте — только engine_ready() (stat, без хешей)."""
    name = entry["name"]
    try:
        size = os.path.getsize(path)
    except OSError as e:
        return False, f"{name}: нет доступа ({e})"
    if size != entry["size"]:
        return False, f"{name}: размер {size} байт, ожидалось {entry['size']}"
    try:
        if "sha256" in entry:
            actual = _sha256_of_file(path)
            if actual.lower() != entry["sha256"].lower():
                return False, f"{name}: SHA-256 не совпал ({actual[:16]}…)"
        if "md5" in entry:
            actual = _md5_of_file(path)
            if actual.lower() != entry["md5"].lower():
                return False, f"{name}: md5 не совпал ({actual[:16]}…)"
        if entry.get("json") == "xtts_config":
            _check_xtts_config(path)
        elif entry.get("json") == "vocab":
            _check_vocab(path)
        if "md5_file" in entry:
            _check_md5_file(path, entry["md5_file"])
    except ValueError as e:
        return False, str(e)
    return True, "ok"


def engine_status(deep: bool = False) -> dict:
    """Состояние движка: {"state", "missing", "dir", "total_bytes"}.

    state:
      "ok"      — все файлы на месте (в deep-режиме — и валидные);
      "partial" — есть хотя бы один файл, но не все;
      "missing" — ничего нет (или каталог отсутствует).
    deep=False — быстрая проверка (только существование+точный размер).
    deep=True  — + SHA-256/md5/JSON-проверка каждого файла (медленно для model.pth).
    """
    missing = []
    for entry in ENGINE_FILES:
        path = _path(entry)
        if not os.path.isfile(path):
            missing.append(entry["name"])
            continue
        if deep:
            ok, _detail = verify_engine_file(path, entry)
            if not ok:
                missing.append(entry["name"])
                continue
        else:
            try:
                if os.path.getsize(path) != entry["size"]:
                    missing.append(entry["name"])
            except OSError:
                missing.append(entry["name"])
    present = len(ENGINE_FILES) - len(missing)
    if not missing:
        state = "ok"
    elif present:
        state = "partial"
    else:
        state = "missing"
    return {
        "state": state,
        "missing": missing,
        "dir": engine_dir(),
        "total_bytes": ENGINE_TOTAL_BYTES,
    }


def engine_ready() -> bool:
    """Дешёвая проверка «движок скачан» для фоновой предзагрузки (только stat)."""
    return engine_status(deep=False)["state"] == "ok"


# ── Скачивание ────────────────────────────────────────────────────────────────


def _is_cancelled(cancelled_cb) -> bool:
    if cancelled_cb is None:
        return False
    if isinstance(cancelled_cb, dict):
        return bool(cancelled_cb.get("cancelled"))
    if callable(cancelled_cb):
        try:
            return bool(cancelled_cb())
        except Exception:
            return False
    return False


def _emit(progress_cb, **kwargs):
    if callable(progress_cb):
        with contextlib.suppress(Exception):  # best effort, не должен ронять скачивание
            progress_cb(kwargs)


def _open_url(url: str, offset: int = 0, timeout: int = 30):
    """Открыть URL (с поддержкой докачки через Range). Отдельная функция,
    чтобы тесты могли подменить сеть без monkeypatch urllib целиком."""
    headers = {"User-Agent": "XTTS-Studio-Engine/1.0"}
    if offset > 0:
        headers["Range"] = f"bytes={offset}-"
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT)


def _download_one(
    entry: dict,
    overall_done_before: int,
    progress_cb,
    cancelled_cb,
    file_index: int,
    file_count: int,
) -> int:
    """Скачать один файл со всех источников по очереди + докачка. Возвращает
    количество байт, скачанных для ЭТОГО файла (0, если файл был валиден)."""
    name = entry["name"]
    dest = _path(entry)
    part = _part_path(entry)
    expected_size = entry["size"]

    last_error: Exception | None = None
    for base_url in ENGINE_BASE_URLS:
        url = base_url + name
        attempt = 0
        while True:
            attempt += 1
            offset = 0
            try:
                if os.path.exists(part):
                    offset = os.path.getsize(part)
                    if offset >= expected_size:
                        offset = 0  # больше ожидаемого — битый остаток, качаем заново
                        os.remove(part)
                with _open_url(url, offset=offset) as response:
                    status = getattr(response, "status", None) or 200
                    if offset > 0 and status != 206:
                        # Сервер не поддерживает Range — начинаем сначала
                        offset = 0
                        with contextlib.suppress(OSError):
                            os.remove(part)
                        response.close()
                        continue
                    downloaded = offset
                    mode = "ab" if offset else "wb"
                    with open(part, mode) as f:
                        while True:
                            if _is_cancelled(cancelled_cb):
                                raise InterruptedError("Загрузка движка отменена пользователем")
                            block = response.read(_CHUNK_SIZE)
                            if not block:
                                break
                            f.write(block)
                            downloaded += len(block)
                            _emit(
                                progress_cb,
                                file=name,
                                file_index=file_index,
                                file_count=file_count,
                                file_done=downloaded,
                                file_total=expected_size,
                                overall_done=overall_done_before + downloaded,
                                overall_total=ENGINE_TOTAL_BYTES,
                            )
                _emit(
                    progress_cb,
                    file=name,
                    file_index=file_index,
                    file_count=file_count,
                    file_done=expected_size,
                    file_total=expected_size,
                    overall_done=overall_done_before + downloaded,
                    overall_total=ENGINE_TOTAL_BYTES,
                    stage="verify",
                )
                ok, detail = verify_engine_file(part, entry)
                if not ok:
                    # Байты невалидны — докачка бессмысленна, удаляем и пробуем
                    # следующий источник.
                    with contextlib.suppress(OSError):
                        os.remove(part)
                    last_error = ValueError(detail)
                    break  # следующий base_url
                os.replace(part, dest)  # атомарная установка
                return downloaded
            except InterruptedError:
                # Отмена — сохраняем .part для докачки, выходим из цикла источников.
                raise
            except urllib.error.HTTPError as e:
                # HTTP-ответ (404/403/502): 5 повторов одного и того же URL не
                # помогут — переходим к следующему источнику сразу.
                last_error = e
                break
            except _TRANSIENT_DOWNLOAD_ERRORS as e:
                last_error = e
                if attempt >= _MAX_RETRIES:
                    break  # следующий base_url
                wait_s = _RETRY_BACKOFF_SEC * attempt
                slept = 0.0
                while slept < wait_s:
                    if _is_cancelled(cancelled_cb):
                        raise InterruptedError("Загрузка движка отменена пользователем") from None
                    time.sleep(0.5)
                    slept += 0.5
                continue
            except Exception as e:
                last_error = e
                break  # следующий base_url
    raise RuntimeError(
        f"Не удалось скачать {name} ни из одного источника. " f"Последняя ошибка: {last_error}"
    ) from last_error


def download_engine(progress_cb=None, cancelled_cb=None) -> dict:
    """Скачать отсутствующие/невалидные файлы движка XTTS v2.

    Возвращает {"ok": bool, "error": str|None, "cancelled": bool, "dir": str}.
    Уже валидные файлы пропускаются (идемпотентно, можно вызывать повторно).
    Отмена сохраняет *.part для докачки при следующем вызове.
    """
    directory = engine_dir()
    os.makedirs(directory, exist_ok=True)

    # Файлы, уже лежащие валидными, учитываем в общем прогрессе и не качаем.
    done_before = 0
    pending = []
    for entry in ENGINE_FILES:
        path = _path(entry)
        ok, _detail = (False, "")
        if os.path.isfile(path):
            ok, _detail = verify_engine_file(path, entry)
        if ok:
            done_before += entry["size"]
        else:
            pending.append(entry)

    try:
        for index, entry in enumerate(pending, start=1):
            _emit(
                progress_cb,
                file=entry["name"],
                file_index=index,
                file_count=len(pending),
                overall_done=done_before,
                overall_total=ENGINE_TOTAL_BYTES,
                stage="start",
            )
            _download_one(entry, done_before, progress_cb, cancelled_cb, index, len(pending))
            done_before += entry["size"]
    except InterruptedError as e:
        return {"ok": False, "error": str(e), "cancelled": True, "dir": directory}
    except Exception as e:
        return {"ok": False, "error": str(e), "cancelled": False, "dir": directory}

    status = engine_status(deep=False)
    if status["state"] == "ok":
        return {"ok": True, "error": None, "cancelled": False, "dir": directory}
    return {
        "ok": False,
        "error": f"Движок установлен не полностью: отсутствуют {', '.join(status['missing'])}",
        "cancelled": False,
        "dir": directory,
    }
