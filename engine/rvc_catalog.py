"""
rvc_catalog.py — каталог сторонних RVC-моделей (community models) для XTTS Studio.
Place in engine/.

В отличие от updater.py (обновление самого приложения, где SHA256
обязателен и всё сначала льётся в staging), тут:
  - модели — это большие пользовательские файлы, а не часть релиза
    приложения, поэтому SHA256 опционален (есть — проверяем, нет — просто
    предупреждаем в логе и всё равно принимаем файл);
  - скачивание идёт сразу в целевую директорию (models/rvc/), а не в
    staging: тут нет риска сломать рабочую копию приложения, максимум —
    недокачанный файл модели, который никак не мешает остальной программе;
  - прогресс — по байтам (Content-Length), а не по количеству файлов,
    т.к. качаем один крупный файл за раз.

Источники каталога (в порядке убывания свежести):
  1. Онлайн rvc_catalog.json из GitHub-релиза (если когда-нибудь появится)
  2. Локальный кэш models/rvc/catalog_cache.json
  3. Seed json/rvc_catalog_seed.json (ставится с приложением; сейчас —
     подборка HF-моделей, индексированных на voice-models.com)

Дополнительно — живой поиск по voice-models.com (fetch_data.php / search),
чтобы не тащить 200k+ моделей в seed. Результаты поиска нормализуются
в тот же формат entry, что и seed/кэш.

Ретраи/SSL-контекст/формат cancelled_flag переиспользуются напрямую из
engine/updater.py — чтобы не заводить вторую копию той же логики.
"""

import os
import re
import io
import json
import time
import shutil
import hashlib
import zipfile
import tempfile
import html as htmlmod
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from engine.updater import (
    _urlopen_with_retry,
    _is_cancelled,
    REPO,
    BRANCH,
)

# ----------------------------------------------------------------
#  Пути и константы
# ----------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Каталог, который ставится вместе с приложением (версионируется в git,
# всегда доступен офлайн, даже на самом первом запуске без сети).
# Лежит в json/ в корне проекта (по твоему выбору), не в engine/.
SEED_CATALOG_PATH = os.path.join(BASE_DIR, "json", "rvc_catalog_seed.json")

# Директория для скачанных моделей и кэша каталога — данные пользователя,
# НЕ версионируется в git (аналогично models/, library/ и т.п.).
RVC_MODELS_DIR = os.path.join(BASE_DIR, "models", "rvc")
RVC_PREVIEW_CACHE_DIR = os.path.join(RVC_MODELS_DIR, ".preview_cache")
RVC_PARAMETER_PREVIEW_CACHE_DIR = os.path.join(
    RVC_MODELS_DIR,
    ".parameter_preview_cache",
)
RVC_METADATA_DIR = os.path.join(RVC_MODELS_DIR, ".metadata")
CATALOG_CACHE_PATH = os.path.join(RVC_MODELS_DIR, "catalog_cache.json")
PREVIEW_MAX_BYTES = 32 * 1024 * 1024
RVC_ARCHIVE_MAX_MEMBERS = 10_000
RVC_ARCHIVE_MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024
RVC_ARCHIVE_MAX_COMPRESSION_RATIO = 200

CATALOG_RAW_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/rvc_catalog.json"

# voice-models.com — community-индекс RVC-моделей (не официальный API,
# reverse-engineered из публичного UI сайта; при поломке — фоллбэк на seed).
VOICE_MODELS_HOME_URL = "https://voice-models.com/"
VOICE_MODELS_TOP_URL = "https://voice-models.com/top"
VOICE_MODELS_FETCH_URL = "https://voice-models.com/fetch_data.php"
VOICE_MODELS_SEARCH_URL = "https://voice-models.com/search"
VOICE_MODELS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 XTTS-Studio-RVCCatalog/1.0"
)

MAX_RETRIES = 4
SEARCH_MAX_RESULTS = 30
SEARCH_PAGES = 1  # 1 страница: меньше таймаутов/трафика; seed уже даёт базу
VM_SEARCH_TIMEOUT = 8  # сек; voice-models.dev часто отвечает медленно
VM_SEARCH_ATTEMPTS = 1  # без ретраев: KeyRelease и так шлёт много запросов

# Не долбим GitHub 4×1.5–4.5с на каждый open dropdown / search.
# rvc_catalog.json на main сейчас 404 — после первого фейла ждём cooldown.
_GITHUB_CATALOG_COOLDOWN_SEC = 6 * 60 * 60  # 6 часов после 404/ошибки
_github_catalog_fail_until = 0.0
_github_catalog_fail_logged = False
_local_catalog_cache = None  # in-memory: seed/кэш без повторного disk+network
_preview_url_cache = {}  # key -> (valid_until_monotonic, url-or-empty)
_browse_catalog_cache = {}  # mode -> (valid_until_monotonic, entries)
_known_entry_cache = {}  # id -> entry, включая результаты поиска текущей сессии
_PREVIEW_SUCCESS_TTL = 24 * 60 * 60
_PREVIEW_FAILURE_TTL = 5 * 60
_BROWSE_CATALOG_TTL = 15 * 60


# ----------------------------------------------------------------
#  Каталог: кэш/seed сразу, GitHub — редко и без 4 ретраев
# ----------------------------------------------------------------


def _validate_catalog(data) -> list:
    """Отбрасывает записи без обязательных полей вместо падения на всём каталоге."""
    if not isinstance(data, list):
        return []
    valid = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if not entry.get("id") or not entry.get("name") or not entry.get("url"):
            continue
        valid.append(entry)
    return valid


def _load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_local_catalog() -> list:
    """Кэш на диске → seed. Без сети. Кэшируется в памяти процесса."""
    global _local_catalog_cache
    if _local_catalog_cache is not None:
        return _local_catalog_cache

    cached = _load_json(CATALOG_CACHE_PATH)
    valid_cached = _validate_catalog(cached) if cached is not None else []
    if valid_cached:
        _local_catalog_cache = valid_cached
        return valid_cached

    seed = _load_json(SEED_CATALOG_PATH)
    valid_seed = _validate_catalog(seed) if seed is not None else []
    _local_catalog_cache = valid_seed
    return valid_seed


def _fetch_remote_catalog_once() -> list:
    """
    Одна попытка GitHub raw (без 4 ретраев updater'а).
    404/сеть → исключение; успех с пустым списком → [].
    """
    # Не используем _urlopen_with_retry: при 404 он орёт 4 попытки в лог.
    req = urllib.request.Request(
        CATALOG_RAW_URL,
        headers={"User-Agent": VOICE_MODELS_UA, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read().decode("utf-8"))
    return _validate_catalog(data)


def _save_cache(entries: list):
    try:
        os.makedirs(RVC_MODELS_DIR, exist_ok=True)
        with open(CATALOG_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_catalog(force_refresh: bool = False) -> list:
    """
    Возвращает список моделей каталога.

    Обычный путь (быстрый, без спама логов):
      1. Локальный кэш models/rvc/catalog_cache.json
      2. Seed json/rvc_catalog_seed.json

    Онлайн GitHub rvc_catalog.json:
      - только если force_refresh=True, ИЛИ локального каталога ещё нет;
      - 1 попытка, timeout 5с (без 4 ретраев);
      - после 404/ошибки — cooldown 6ч (не долбим raw.githubusercontent).

    Живой поиск voice-models.com — отдельно: search_catalog(query).
    """
    global _github_catalog_fail_until, _github_catalog_fail_logged, _local_catalog_cache

    local = _load_local_catalog()
    now = time.monotonic()

    # Есть seed/кэш — отдаём сразу. GitHub только:
    #   force_refresh=True, или локально пусто (первый запуск без seed).
    # Раньше каждый open dropdown долбил raw.githubusercontent 4 ретраями →
    # лог забит 404, UI тормозит.
    should_try_github = force_refresh or not local
    if should_try_github and (now < _github_catalog_fail_until) and not force_refresh:
        should_try_github = False

    if should_try_github:
        try:
            entries = _fetch_remote_catalog_once()
            if entries:
                _save_cache(entries)
                _local_catalog_cache = entries
                _github_catalog_fail_until = 0.0
                _github_catalog_fail_logged = False
                return entries
            _github_catalog_fail_logged = True
            _github_catalog_fail_until = now + _GITHUB_CATALOG_COOLDOWN_SEC
        except Exception:
            _github_catalog_fail_until = now + _GITHUB_CATALOG_COOLDOWN_SEC
            _github_catalog_fail_logged = True

    return local


# ----------------------------------------------------------------
#  voice-models.com — поиск и нормализация
# ----------------------------------------------------------------


def _vm_request(url: str, data: bytes = None, timeout: int = None):
    """HTTP GET/POST к voice-models.com. Без ретраев — UI и так debounce'ит."""
    if timeout is None:
        timeout = VM_SEARCH_TIMEOUT
    headers = {
        "User-Agent": VOICE_MODELS_UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://voice-models.com/",
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
    req = urllib.request.Request(url, data=data, headers=headers)
    # 1 попытка: повтор на timeout только удлиняет «Ищу…» и спамит лог.
    return urllib.request.urlopen(req, timeout=timeout)


class _PreviewAudioParser(HTMLParser):
    """Достаёт основной generated sample из страницы voice-models.com."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if str(tag).lower() != "audio":
            return
        data = {str(k).lower(): v for k, v in attrs if k}
        src = (data.get("src") or "").strip()
        if not src:
            return
        # На странице может быть JS-шаблон audio. Берём только реальный URL;
        # vm-fit-audio — основной пример из Sample deck.
        if src.startswith(("https://", "http://")):
            priority = 0 if data.get("id") == "vm-fit-audio" else 1
            self.urls.append((priority, src))


def _entry_page_url(entry: dict) -> str:
    page_url = str(entry.get("page_url") or "").strip()
    if re.match(r"^https?://(?:www\.)?voice-models\.com/model/", page_url, re.I):
        return page_url

    source_url = str(entry.get("url") or "").strip()
    if re.match(r"^https?://(?:www\.)?voice-models\.com/model/", source_url, re.I):
        return source_url

    description = str(entry.get("description") or "")
    match = re.search(
        r"https?://(?:www\.)?voice-models\.com/model/[A-Za-z0-9_-]+",
        description,
        re.I,
    )
    if match:
        return match.group(0)

    entry_id = str(entry.get("id") or "")
    if entry_id.startswith("vm_") and len(entry_id) > 3:
        return f"https://voice-models.com/model/{entry_id[3:]}"
    return ""


def can_preview(entry: dict) -> bool:
    """True, если запись содержит sample, его кэш или страницу-источник."""
    cached_path = str(entry.get("preview_cache_path") or "")
    return bool(
        (cached_path and os.path.isfile(cached_path))
        or entry.get("preview_url")
        or _entry_page_url(entry)
    )


def _normalize_preview_url(url: str) -> str:
    value = htmlmod.unescape(str(url or "").strip()).replace(r"\/", "/")
    if not value.startswith(("https://", "http://")):
        return ""
    parsed = urllib.parse.urlparse(value)
    if not parsed.netloc:
        return ""
    # Сейчас Sample deck отдаёт MP3 с Backblaze B2; оставляем также wav/ogg/m4a
    # и URL с query-параметрами.
    if not re.search(r"\.(?:mp3|wav|ogg|m4a)(?:$|[?#])", value, re.I):
        return ""
    return value


def get_preview_url(entry: dict, force_refresh: bool = False) -> str:
    """
    Возвращает URL короткого примера голоса без скачивания RVC-модели.

    Для voice-models.com ссылка извлекается лениво из <audio id="vm-fit-audio">.
    Сетевой запрос выполняется только по нажатию кнопки preview, а не при поиске.
    """
    direct = _normalize_preview_url(entry.get("preview_url") or "")
    if direct:
        return direct

    page_url = _entry_page_url(entry)
    if not page_url:
        return ""

    cache_key = str(entry.get("id") or page_url)
    now = time.monotonic()
    if not force_refresh:
        cached = _preview_url_cache.get(cache_key)
        if cached and now < cached[0]:
            return cached[1]

    preview_url = ""
    try:
        req = urllib.request.Request(
            page_url,
            headers={
                "User-Agent": VOICE_MODELS_UA,
                "Accept": "text/html,application/xhtml+xml",
                "Referer": "https://voice-models.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=VM_SEARCH_TIMEOUT) as response:
            raw = response.read(2 * 1024 * 1024).decode("utf-8", "replace")

        parser = _PreviewAudioParser()
        parser.feed(raw)
        for _priority, candidate in sorted(parser.urls, key=lambda item: item[0]):
            preview_url = _normalize_preview_url(candidate)
            if preview_url:
                break

        # Fallback для страниц, где sample лежит только в JSON внутри <script>.
        if not preview_url:
            candidates = re.findall(
                r"https?(?::|\u003A)(?:\/|\u002F){2}[^\"'<> ]+?"
                r"\.(?:mp3|wav|ogg|m4a)(?:[^\"'<> ]*)",
                raw,
                re.I,
            )
            for candidate in candidates:
                candidate = (
                    candidate.replace("\u003A", ":").replace("\u002F", "/").replace(r"\/", "/")
                )
                preview_url = _normalize_preview_url(candidate)
                if preview_url:
                    break
    except Exception:
        preview_url = ""

    ttl = _PREVIEW_SUCCESS_TTL if preview_url else _PREVIEW_FAILURE_TTL
    _preview_url_cache[cache_key] = (now + ttl, preview_url)
    if preview_url:
        entry["preview_url"] = preview_url
        try:
            if is_downloaded(entry):
                _save_local_model_metadata(entry)
        except Exception:
            pass
    return preview_url


def get_preview_audio_path(entry: dict, force_refresh: bool = False) -> str:
    """Скачивает только короткий sample в кэш и возвращает локальный аудиофайл.

    Это не скачивание RVC-модели: обычно загружается небольшой MP3 из Sample
    deck. Повторное прослушивание использует models/rvc/.preview_cache.
    """
    remembered_path = str(entry.get("preview_cache_path") or "")
    if remembered_path and os.path.isfile(remembered_path) and not force_refresh:
        return remembered_path

    url = get_preview_url(entry, force_refresh=force_refresh)
    if not url:
        return ""

    parsed = urllib.parse.urlparse(url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if ext not in (".mp3", ".wav", ".ogg", ".m4a"):
        ext = ".mp3"
    digest = hashlib.sha256(url.encode("utf-8", "replace")).hexdigest()[:20]
    readable = re.sub(
        r"[^\w\-]+", "_", str(entry.get("name") or entry.get("id") or "preview")[:42]
    ).strip("_")
    readable = readable or "preview"
    cache_path = os.path.join(RVC_PREVIEW_CACHE_DIR, f"{readable}_{digest}{ext}")

    try:
        if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 0:
            if not _download_is_html_error(cache_path):
                entry["preview_cache_path"] = cache_path
                try:
                    if is_downloaded(entry):
                        _save_local_model_metadata(entry)
                except Exception:
                    pass
                return cache_path
            os.remove(cache_path)
    except Exception:
        pass

    part_path = cache_path + ".part"
    try:
        os.makedirs(RVC_PREVIEW_CACHE_DIR, exist_ok=True)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": VOICE_MODELS_UA,
                "Accept": "audio/mpeg,audio/*;q=0.9,*/*;q=0.1",
                "Referer": _entry_page_url(entry) or "https://voice-models.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            total_header = response.headers.get("Content-Length")
            if total_header and str(total_header).isdigit():
                if int(total_header) > PREVIEW_MAX_BYTES:
                    raise ValueError("аудиопример слишком большой")
            received = 0
            with open(part_path, "wb") as output:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > PREVIEW_MAX_BYTES:
                        raise ValueError("аудиопример превысил допустимый размер")
                    output.write(chunk)

        if not os.path.isfile(part_path) or os.path.getsize(part_path) <= 0:
            raise ValueError("получен пустой аудиопример")
        if _download_is_html_error(part_path):
            raise ValueError("вместо аудио сервер вернул HTML-страницу")
        os.replace(part_path, cache_path)
        entry["preview_cache_path"] = cache_path
        try:
            if is_downloaded(entry):
                _save_local_model_metadata(entry)
        except Exception:
            pass
        return cache_path
    except Exception:
        _cleanup_tmp(part_path)
        return ""


def open_preview(entry: dict) -> bool:
    """Fallback: открывает потоковый sample в браузере."""
    url = get_preview_url(entry)
    if not url:
        return False
    try:
        import webbrowser

        return bool(webbrowser.open(url))
    except Exception:
        return False


def _clean_download_url(url: str) -> str:
    if not url:
        return ""
    u = htmlmod.unescape(url.strip())
    u = u.replace("%3Fdownload%3Dtrue", "")
    while u.endswith("?download=true"):
        u = u[: -len("?download=true")]
    if "/blob/" in u and "huggingface.co" in u:
        u = u.replace("/blob/", "/resolve/")
    # autocomplete API иногда отдаёт voice-model.com (без s)
    u = u.replace("https://voice-model.com/", "https://voice-models.com/")
    u = u.replace("http://voice-model.com/", "https://voice-models.com/")
    return u


def _safe_filename_stem(name: str, url: str, mid: str) -> str:
    path = urllib.parse.urlparse(url or "").path
    base = urllib.parse.unquote(os.path.basename(path))
    stem = re.sub(r"\.(zip|pth|index)$", "", base, flags=re.I)
    stem = re.sub(r"[^\w\-]+", "_", stem, flags=re.U).strip("_")
    if not stem or stem.lower() in ("resolve", "main", "blob", "view"):
        stem = re.sub(r"[^\w\-]+", "_", (name or "")[:48], flags=re.U).strip("_")
    if not stem:
        stem = f"model_{mid or int(time.time())}"
    return stem[:80]


def _guess_filename(name: str, url: str, mid: str) -> str:
    stem = _safe_filename_stem(name, url, mid)
    path = urllib.parse.urlparse(url or "").path.lower()
    if path.endswith(".pth"):
        return stem + ".pth"
    # zip / gdrive / unknown — скачиваем как zip (для pth extract сделает своё)
    if (
        path.endswith(".zip")
        or "huggingface.co" in (url or "")
        or "drive.google.com" in (url or "")
    ):
        return stem + ".zip"
    return stem + ".zip"


def _is_direct_downloadable(url: str) -> bool:
    """True, если URL можно качать urllib'ом (HF / прямой файл / gdrive file)."""
    if not url:
        return False
    u = url.lower()
    if "huggingface.co" in u and "/resolve/" in u:
        return True
    if re.search(r"\.(zip|pth)(\?|$)", u):
        return True
    if "drive.google.com" in u and ("/file/d/" in u or "id=" in u or "uc?export=download" in u):
        return True
    # folder — не прямой файл
    if "drive.google.com" in u and "/folders/" in u:
        return False
    return False


def _parse_vm_table(table_html: str) -> list:
    """Парсит HTML-таблицу из fetch_data.php → список сырых dict."""
    if not table_html:
        return []
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", table_html, re.S | re.I):
        m = re.search(r"href='(/model/[^']+)'[^>]*class='fs-5'>(.*?)</a>", tr, re.S)
        if not m:
            continue
        path, title_html = m.group(1), m.group(2)
        mid = path.rstrip("/").rsplit("/", 1)[-1]
        creator = None
        cm = re.search(r"title='Uploaded by ([^']+)'", tr)
        if cm:
            creator = cm.group(1)
        size = None
        sm = re.search(r"badge bg-secondary[^>]*>([^<]+)</span>", tr)
        if sm:
            size = sm.group(1).strip()
        dl = None
        dm = re.search(r"data-clipboard-text='([^']+)'", tr)
        if dm:
            dl = htmlmod.unescape(dm.group(1))
        if not dl:
            rm = re.search(r"easyaivoice\.com/run\?url=([^'\"&]+)", tr)
            if rm:
                dl = urllib.parse.unquote(rm.group(1))
        title = re.sub(r"<[^>]+>", "", title_html or "")
        title = htmlmod.unescape(title).strip()
        rows.append(
            {
                "mid": mid,
                "path": path,
                "title": title,
                "author": creator or "Community",
                "size": size,
                "download": _clean_download_url(dl or ""),
            }
        )
    return rows


def _row_to_entry(row: dict) -> dict | None:
    """Сырой ряд voice-models → entry формата каталога (или None)."""
    mid = row.get("mid") or ""
    title = (row.get("title") or "").strip()
    url = _clean_download_url(row.get("download") or "")
    if not mid or not title:
        return None
    # Без URL скачивать нечего — но page_url всё равно полезен (открыть в браузере)
    page_url = f"https://voice-models.com/model/{mid}"
    if not url:
        url = page_url
    filename = _guess_filename(title, url, mid)
    entry = {
        "id": f"vm_{mid}",
        "name": title[:160],
        "url": url,
        "filename": filename,
        "author": row.get("author") or "Community",
        "license": "Community (voice-models.com)",
        "description": page_url + (f" · {row['size']}" if row.get("size") else ""),
        "source": "voice-models",
        "page_url": page_url,
        "downloadable": _is_direct_downloadable(url),
    }
    if row.get("size"):
        entry["size"] = row["size"]
    return entry


def _remember_catalog_entries(entries):
    for entry in entries or []:
        try:
            entry_id = entry.get("id")
            if entry_id:
                _known_entry_cache[entry_id] = dict(entry)
        except Exception:
            pass


def browse_voice_models(
    mode: str = "new", max_results: int = 50, force_refresh: bool = False
) -> list:
    """Загружает публичные каталоги сайта: ``new`` или ``top``.

    ``new`` использует тот же fetch_data.php, что главная страница сайта.
    ``top`` разбирает публичную таблицу /top. Результаты кэшируются на 15 минут.
    При сетевой ошибке возвращается последний успешный кэш, если он существует.
    """
    catalog_mode = str(mode or "new").strip().lower()
    if catalog_mode not in ("new", "top"):
        return []

    now = time.monotonic()
    cached = _browse_catalog_cache.get(catalog_mode)
    if cached and not force_refresh and now < cached[0]:
        return [dict(entry) for entry in cached[1][:max_results]]

    entries = []
    try:
        if catalog_mode == "new":
            data = urllib.parse.urlencode({"page": "1", "search": ""}).encode()
            with _vm_request(
                VOICE_MODELS_FETCH_URL,
                data=data,
                timeout=VM_SEARCH_TIMEOUT,
            ) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            html_table = payload.get("table", "") if isinstance(payload, dict) else ""
        else:
            request = urllib.request.Request(
                VOICE_MODELS_TOP_URL,
                headers={
                    "User-Agent": VOICE_MODELS_UA,
                    "Accept": "text/html,application/xhtml+xml",
                    "Referer": VOICE_MODELS_HOME_URL,
                },
            )
            with urllib.request.urlopen(request, timeout=VM_SEARCH_TIMEOUT) as response:
                html_table = response.read(2 * 1024 * 1024).decode("utf-8", "replace")

        seen = set()
        for row in _parse_vm_table(html_table):
            entry = _row_to_entry(row)
            if not entry or entry["id"] in seen:
                continue
            seen.add(entry["id"])
            entry["catalog"] = catalog_mode
            entries.append(entry)
            if len(entries) >= max_results:
                break
    except Exception:
        entries = []

    if entries:
        _browse_catalog_cache[catalog_mode] = (
            now + _BROWSE_CATALOG_TTL,
            [dict(entry) for entry in entries],
        )
        _remember_catalog_entries(entries)
        return entries
    if cached:
        return [dict(entry) for entry in cached[1][:max_results]]
    return []


# cooldown логов live-поиска — не печатать timeout на каждую букву
_vm_search_fail_log_until = 0.0


def search_voice_models(query: str, max_results: int = SEARCH_MAX_RESULTS) -> list:
    """
    Живой поиск по voice-models.com.

    Возвращает list[entry] в том же формате, что get_catalog().
    Пустой query → пустой список (не тянем всю главную).
    Ошибки сети глотаются → [] + редкий print в лог.
    """
    global _vm_search_fail_log_until

    q = (query or "").strip()
    if len(q) < 2:
        return []

    seen_ids = set()
    results = []
    errors = []

    # 1) fetch_data.php — полные карточки с download URL (1 страница)
    try:
        for page in range(1, SEARCH_PAGES + 1):
            if len(results) >= max_results:
                break
            data = urllib.parse.urlencode({"page": str(page), "search": q}).encode()
            with _vm_request(VOICE_MODELS_FETCH_URL, data=data, timeout=VM_SEARCH_TIMEOUT) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
            table = payload.get("table") if isinstance(payload, dict) else ""
            for row in _parse_vm_table(table or ""):
                entry = _row_to_entry(row)
                if not entry or entry["id"] in seen_ids:
                    continue
                seen_ids.add(entry["id"])
                results.append(entry)
                if len(results) >= max_results:
                    break
    except Exception as e:
        errors.append(f"fetch_data: {e}")

    # 2) autocomplete — только если fetch_data ничего не дал
    #    (не тратим второй timeout, если уже есть HF-ссылки)
    if len(results) < 5:
        try:
            url = VOICE_MODELS_SEARCH_URL + "?search=" + urllib.parse.quote(q)
            with _vm_request(url, data=None, timeout=min(6, VM_SEARCH_TIMEOUT)) as resp:
                raw = resp.read().decode("utf-8", "replace")
            items = json.loads(raw) if raw.strip().startswith("[") else []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                title = (item.get("title") or "").strip()
                link = _clean_download_url(item.get("url") or "")
                m = re.search(r"/model/([^/?#]+)", link)
                mid = m.group(1) if m else ""
                if not mid or not title:
                    continue
                eid = f"vm_{mid}"
                if eid in seen_ids:
                    continue
                entry = _row_to_entry(
                    {
                        "mid": mid,
                        "title": title,
                        "author": "Community",
                        "size": None,
                        "download": link if _is_direct_downloadable(link) else "",
                    }
                )
                if not entry:
                    continue
                if not entry.get("downloadable"):
                    entry["url"] = entry.get("page_url") or link
                    entry["downloadable"] = False
                seen_ids.add(eid)
                results.append(entry)
                if len(results) >= max_results:
                    break
        except Exception as e:
            errors.append(f"autocomplete: {e}")

    if errors and not results:
        # тихо: UI покажет seed/локальные результаты; online просто недоступен
        _vm_search_fail_log_until = time.monotonic() + 60

    results.sort(key=lambda e: (0 if e.get("downloadable") else 1, e.get("name", "").lower()))
    return results[:max_results]


def search_catalog(query: str, max_results: int = SEARCH_MAX_RESULTS, live: bool = True) -> list:
    """
    Поиск по seed/кэшу + (опционально) live voice-models.com.

    Локальные совпадения (seed) идут первыми, затем live-результаты
    без дублей по id. Локальный поиск НЕ трогает GitHub (get_catalog
    с cooldown / in-memory seed).
    """
    q = (query or "").strip().lower()
    if len(q) < 2:
        return []

    local_hits = []
    try:
        # _load_local_catalog — без сети; get_catalog тоже, пока cooldown
        for entry in _load_local_catalog() or get_catalog(force_refresh=False):
            blob = " ".join(
                [
                    str(entry.get("name") or ""),
                    str(entry.get("author") or ""),
                    str(entry.get("description") or ""),
                    str(entry.get("id") or ""),
                ]
            ).lower()
            if q in blob:
                e = dict(entry)
                e.setdefault("downloadable", _is_direct_downloadable(e.get("url") or ""))
                e.setdefault("source", e.get("source") or "seed")
                local_hits.append(e)
    except Exception:
        pass

    live_hits = []
    if live:
        try:
            live_hits = search_voice_models(query, max_results=max_results)
        except Exception as e:
            # редкий лог внутри search_voice_models
            pass

    seen = set()
    out = []
    for e in local_hits + live_hits:
        eid = e.get("id")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        out.append(e)
        if len(out) >= max_results:
            break
    _remember_catalog_entries(out)
    return out


# ----------------------------------------------------------------
#  Скачивание модели
# ----------------------------------------------------------------


def _sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def local_model_path(entry: dict) -> str:
    """
    Путь, по которому модель должна лежать локально, если скачана.

    Важно: UI/RVC pipeline ждут .pth в models/rvc/. Если в entry.filename
    указан .zip — локальный «канонический» путь это .pth с тем же stem
    (после распаковки zip).
    """
    filename = entry.get("filename") or os.path.basename(urllib.parse.urlparse(entry["url"]).path)
    filename = urllib.parse.unquote(filename)
    stem, ext = os.path.splitext(filename)
    if ext.lower() == ".zip":
        filename = stem + ".pth"
    elif not ext:
        filename = filename + ".pth"
    # на всякий случай чистим path separators из имени
    filename = os.path.basename(filename)
    return os.path.join(RVC_MODELS_DIR, filename)


def is_downloaded(entry: dict) -> bool:
    return os.path.isfile(local_model_path(entry))


def is_local_model_trusted(name: str) -> bool:
    from engine.rvc_pipeline import is_rvc_checkpoint_trusted

    model_path = os.path.join(RVC_MODELS_DIR, f"{os.path.basename(str(name or ''))}.pth")
    return is_rvc_checkpoint_trusted(model_path)


def trust_local_model(name: str, source: str = "user-confirmed") -> str:
    from engine.rvc_pipeline import mark_rvc_checkpoint_trusted

    safe_name = os.path.basename(str(name or "").strip())
    if not safe_name or safe_name != str(name or "").strip():
        raise ValueError("некорректное имя RVC-модели")
    return mark_rvc_checkpoint_trusted(
        os.path.join(RVC_MODELS_DIR, f"{safe_name}.pth"), source=source
    )


def _metadata_path_for_local_name(name: str) -> str:
    safe_name = os.path.basename(str(name or "").strip())
    return os.path.join(RVC_METADATA_DIR, f"{safe_name}.json")


def _save_local_model_metadata(entry: dict, model_path: str = "") -> bool:
    """Сохраняет источник и preview для показа ▶ у локальной модели."""
    try:
        resolved_path = model_path or local_model_path(entry)
        local_name = os.path.splitext(os.path.basename(resolved_path))[0]
        if not local_name:
            return False
        os.makedirs(RVC_METADATA_DIR, exist_ok=True)
        allowed = (
            "id",
            "name",
            "url",
            "filename",
            "author",
            "license",
            "description",
            "source",
            "page_url",
            "preview_url",
            "preview_cache_path",
            "size",
            "downloadable",
        )
        metadata = {key: entry.get(key) for key in allowed if entry.get(key) is not None}
        metadata["local_name"] = local_name
        metadata["filename"] = os.path.basename(resolved_path)
        target = _metadata_path_for_local_name(local_name)
        temp_target = target + ".tmp"
        with open(temp_target, "w", encoding="utf-8") as output:
            json.dump(metadata, output, ensure_ascii=False, indent=2)
        os.replace(temp_target, target)
        return True
    except Exception:
        return False


def _entry_matches_local_name(entry: dict, local_name: str) -> bool:
    try:
        candidate = os.path.splitext(os.path.basename(local_model_path(entry)))[0]
        return os.path.normcase(candidate) == os.path.normcase(local_name)
    except Exception:
        return False


def _parameter_preview_model_dir(model_name: str) -> str:
    safe_model = re.sub(
        r"[^\w\-]+",
        "_",
        os.path.basename(str(model_name or "model")),
        flags=re.U,
    ).strip("_")
    safe_model = (safe_model or "model")[:64]
    model_digest = hashlib.sha256(
        str(model_name or "model").encode("utf-8", "replace")
    ).hexdigest()[:10]
    return os.path.join(
        RVC_PARAMETER_PREVIEW_CACHE_DIR,
        f"{safe_model}_{model_digest}",
    )


def get_parameter_preview_cache_path(model_name: str, fingerprint: str) -> str:
    """Путь к локальному preview текущих Index/Pitch/f0 для модели."""
    digest = hashlib.sha256(str(fingerprint).encode("utf-8", "replace")).hexdigest()[:24]
    model_cache_dir = _parameter_preview_model_dir(model_name)
    os.makedirs(model_cache_dir, exist_ok=True)
    return os.path.join(model_cache_dir, f"{digest}.wav")


def prune_parameter_preview_cache(model_name: str, keep: int = 6):
    """Оставляет несколько последних вариантов параметрического preview модели."""
    try:
        model_cache_dir = _parameter_preview_model_dir(model_name)
        if not os.path.isdir(model_cache_dir):
            return
        files = [
            os.path.join(model_cache_dir, filename)
            for filename in os.listdir(model_cache_dir)
            if filename.lower().endswith(".wav")
        ]
        files.sort(key=lambda path: os.path.getmtime(path), reverse=True)
        for old_path in files[max(1, int(keep)) :]:
            try:
                os.remove(old_path)
            except Exception:
                pass
    except Exception:
        pass


def _delete_parameter_preview_cache(model_name: str):
    try:
        model_cache_dir = _parameter_preview_model_dir(model_name)
        if os.path.isdir(model_cache_dir):
            shutil.rmtree(model_cache_dir, ignore_errors=True)
    except Exception:
        pass


def get_local_model_entry(name: str) -> dict | None:
    """Возвращает метаданные локальной модели, включая источник preview."""
    local_name = os.path.basename(str(name or "").strip())
    if not local_name:
        return None

    metadata = _load_json(_metadata_path_for_local_name(local_name))
    if isinstance(metadata, dict):
        entry = dict(metadata)
        entry.setdefault("id", f"local_{local_name}")
        entry.setdefault("name", local_name)
        entry.setdefault("filename", f"{local_name}.pth")
        entry["local_name"] = local_name
        return entry

    # Миграция старых скачиваний: пытаемся восстановить запись из seed/кэша
    # и из уже загруженных в этой сессии каталогов New/Top.
    candidates = []
    try:
        candidates.extend(_load_local_catalog())
    except Exception:
        pass
    try:
        for _expires, entries in _browse_catalog_cache.values():
            candidates.extend(entries or [])
    except Exception:
        pass
    try:
        candidates.extend(_known_entry_cache.values())
    except Exception:
        pass

    seen = set()
    for candidate in candidates:
        entry_id = candidate.get("id") if isinstance(candidate, dict) else None
        if not entry_id or entry_id in seen:
            continue
        seen.add(entry_id)
        if not _entry_matches_local_name(candidate, local_name):
            continue
        entry = dict(candidate)
        entry["local_name"] = local_name
        _save_local_model_metadata(
            entry,
            os.path.join(RVC_MODELS_DIR, f"{local_name}.pth"),
        )
        return entry
    return None


def _path_is_inside(path: str, directory: str) -> bool:
    try:
        return os.path.commonpath(
            [os.path.abspath(path), os.path.abspath(directory)]
        ) == os.path.abspath(directory)
    except Exception:
        return False


def _installed_preview_paths(exclude_local_name: str = "") -> set:
    """Preview-файлы, принадлежащие установленным .pth и защищённые от очистки."""
    protected = set()
    try:
        metadata_files = os.listdir(RVC_METADATA_DIR)
    except Exception:
        metadata_files = []
    excluded = os.path.normcase(str(exclude_local_name or ""))
    for filename in metadata_files:
        if not filename.lower().endswith(".json"):
            continue
        metadata = _load_json(os.path.join(RVC_METADATA_DIR, filename))
        if not isinstance(metadata, dict):
            continue
        local_name = str(metadata.get("local_name") or os.path.splitext(filename)[0])
        if excluded and os.path.normcase(local_name) == excluded:
            continue
        model_path = os.path.join(RVC_MODELS_DIR, f"{local_name}.pth")
        if not os.path.isfile(model_path):
            continue
        preview_path = str(metadata.get("preview_cache_path") or "")
        if preview_path and os.path.isfile(preview_path):
            protected.add(os.path.normcase(os.path.abspath(preview_path)))
    return protected


def clear_rvc_cache() -> dict:
    """Удаляет orphan preview и недокачанные модели, не трогая установленные.

    Preview, записанный в metadata существующей .pth, защищён и удаляется
    только вместе с самой моделью через delete_local_model().
    """
    protected = _installed_preview_paths()
    removed_files = 0
    removed_bytes = 0
    removed_previews = 0
    removed_partials = 0

    def remove_file(path, kind):
        nonlocal removed_files, removed_bytes, removed_previews, removed_partials
        try:
            size = os.path.getsize(path) if os.path.isfile(path) else 0
            os.remove(path)
            removed_files += 1
            removed_bytes += max(0, size)
            if kind == "preview":
                removed_previews += 1
            elif kind == "partial":
                removed_partials += 1
        except Exception:
            pass

    try:
        preview_files = os.listdir(RVC_PREVIEW_CACHE_DIR)
    except Exception:
        preview_files = []
    for filename in preview_files:
        path = os.path.join(RVC_PREVIEW_CACHE_DIR, filename)
        if not os.path.isfile(path):
            continue
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized in protected:
            continue
        remove_file(path, "preview")

    try:
        model_files = os.listdir(RVC_MODELS_DIR)
    except Exception:
        model_files = []
    for filename in model_files:
        path = os.path.join(RVC_MODELS_DIR, filename)
        if not os.path.isfile(path):
            continue
        lower = filename.lower()
        is_partial = bool(
            re.search(r"\.part(?:\.|$)", lower)
            or lower.endswith((".partial", ".tmp", ".download", ".crdownload"))
        )
        if is_partial:
            remove_file(path, "partial")

    # Параметрические previews принадлежат установленной модели. Для живых
    # моделей удаляем только незавершённые .part; orphan-каталоги очищаем целиком.
    installed_parameter_dirs = set()
    try:
        for filename in os.listdir(RVC_MODELS_DIR):
            if filename.lower().endswith(".pth"):
                local_name = os.path.splitext(filename)[0]
                installed_parameter_dirs.add(
                    os.path.normcase(os.path.abspath(_parameter_preview_model_dir(local_name)))
                )
    except Exception:
        pass
    try:
        parameter_dirs = os.listdir(RVC_PARAMETER_PREVIEW_CACHE_DIR)
    except Exception:
        parameter_dirs = []
    for dirname in parameter_dirs:
        directory = os.path.join(RVC_PARAMETER_PREVIEW_CACHE_DIR, dirname)
        if not os.path.isdir(directory):
            continue
        normalized_dir = os.path.normcase(os.path.abspath(directory))
        if normalized_dir not in installed_parameter_dirs:
            for root_dir, _subdirs, filenames in os.walk(directory):
                for filename in filenames:
                    remove_file(os.path.join(root_dir, filename), "preview")
            shutil.rmtree(directory, ignore_errors=True)
            continue
        for filename in os.listdir(directory):
            lower = filename.lower()
            if re.search(r"\.part(?:\.|$)", lower) or lower.endswith(".tmp"):
                remove_file(os.path.join(directory, filename), "partial")

    # Атомарная запись metadata может оставить .tmp после аварийного закрытия.
    try:
        metadata_files = os.listdir(RVC_METADATA_DIR)
    except Exception:
        metadata_files = []
    for filename in metadata_files:
        if filename.lower().endswith(".tmp"):
            remove_file(os.path.join(RVC_METADATA_DIR, filename), "partial")

    return {
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "removed_previews": removed_previews,
        "removed_partials": removed_partials,
        "protected_previews": len(protected),
    }


def delete_local_model(name: str) -> bool:
    """
    Удаляет локально скачанную модель по имени (без расширения — так же,
    как её отдаёт get_rvc_models() в presets.py: f[:-4]).

    Заодно удаляет .index-файл с тем же именем, если он есть — RVC-модели
    часто идут парой .pth + .index, оставлять осиротевший .index бессмысленно.

    Ошибка удаления одного из двух файлов не считается полным провалом —
    возвращает False, только если НИ ОДИН файл не был удалён (например,
    их вообще не было — нечего было удалять).
    """
    pth = os.path.join(RVC_MODELS_DIR, f"{name}.pth")
    idx = os.path.join(RVC_MODELS_DIR, f"{name}.index")
    metadata_path = _metadata_path_for_local_name(name)
    metadata = _load_json(metadata_path)
    preview_path = ""
    if isinstance(metadata, dict):
        preview_path = str(metadata.get("preview_cache_path") or "")

    removed_any = False
    trust_path = pth + ".trust.json"
    for p in (pth, idx, trust_path):
        try:
            if os.path.isfile(p):
                os.remove(p)
                removed_any = True
        except Exception:
            pass

    # Metadata и закреплённый sample удаляем только когда самой .pth уже нет.
    if not os.path.isfile(pth):
        _delete_parameter_preview_cache(name)
        try:
            if os.path.isfile(metadata_path):
                os.remove(metadata_path)
        except Exception:
            pass
        if (
            preview_path
            and _path_is_inside(preview_path, RVC_PREVIEW_CACHE_DIR)
            and os.path.isfile(preview_path)
        ):
            protected_elsewhere = _installed_preview_paths(exclude_local_name=name)
            normalized_preview = os.path.normcase(os.path.abspath(preview_path))
            if normalized_preview not in protected_elsewhere:
                try:
                    os.remove(preview_path)
                except Exception:
                    pass
    return removed_any


def _gdrive_file_id(url: str) -> str | None:
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    return None


def _resolve_download_url(url: str) -> str:
    """
    Нормализует URL перед скачиванием.
    Google Drive file → uc?export=download&id=...
    HF blob → resolve.
    """
    u = _clean_download_url(url)
    if "drive.google.com" in u:
        if "/folders/" in u:
            raise ValueError(
                "Google Drive folder URL — прямое скачивание не поддерживается. "
                "Откройте ссылку в браузере и положите .pth в models/rvc/"
            )
        fid = _gdrive_file_id(u)
        if fid:
            return f"https://drive.google.com/uc?export=download&id={fid}"
    return u


def _download_bytes_to_file(
    url: str, tmp_path: str, progress_callback=None, cancelled_flag=None
) -> None:
    """Качает url во tmp_path с прогрессом. Бросает при ошибке/отмене."""
    resolved = _resolve_download_url(url)

    # Google Drive иногда отдаёт HTML confirm — обрабатываем confirm token
    if "drive.google.com" in resolved:
        _download_gdrive(resolved, tmp_path, progress_callback, cancelled_flag)
        return

    with _urlopen_with_retry(resolved, timeout=30, max_retries=MAX_RETRIES) as resp:
        total = resp.headers.get("Content-Length")
        total = int(total) if total and str(total).isdigit() else None
        downloaded = 0
        with open(tmp_path, "wb") as f:
            while True:
                if _is_cancelled(cancelled_flag):
                    raise InterruptedError("Скачивание модели отменено пользователем")
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)


def _download_gdrive(
    uc_url: str, tmp_path: str, progress_callback=None, cancelled_flag=None
) -> None:
    """Best-effort скачивание Google Drive file (с confirm-cookie для больших файлов)."""
    # Первый запрос
    req = urllib.request.Request(uc_url, headers={"User-Agent": VOICE_MODELS_UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        data = resp.read()
        # Если сразу бинарник
        if (
            "text/html" not in ctype
            and not data[:200].lstrip().startswith(b"<!DOCTYPE")
            and not data[:200].lstrip().lower().startswith(b"<html")
        ):
            with open(tmp_path, "wb") as f:
                f.write(data)
            if progress_callback:
                progress_callback(len(data), len(data))
            return
        html = data.decode("utf-8", "replace")
        # confirm token
        m = re.search(r"confirm=([0-9A-Za-z_]+)", html)
        token = m.group(1) if m else None
        # form download
        m2 = re.search(r"name=\"confirm\"\s+value=\"([^\"]+)\"", html)
        if m2:
            token = m2.group(1)
        fid = None
        m3 = re.search(r"name=\"id\"\s+value=\"([^\"]+)\"", html)
        if m3:
            fid = m3.group(1)
        if not fid:
            fid = _gdrive_file_id(uc_url)
        if not token or not fid:
            # иногда достаточно &confirm=t
            token = token or "t"
        if not fid:
            raise RuntimeError("Google Drive: не удалось извлечь file id / confirm token")

    final = f"https://drive.google.com/uc?export=download&confirm={token}&id={fid}"
    with _urlopen_with_retry(final, timeout=30, max_retries=MAX_RETRIES) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        total = resp.headers.get("Content-Length")
        total = int(total) if total and str(total).isdigit() else None
        downloaded = 0
        with open(tmp_path, "wb") as f:
            while True:
                if _is_cancelled(cancelled_flag):
                    raise InterruptedError("Скачивание модели отменено пользователем")
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)
        # если скачали HTML — провал
        if downloaded < 1024:
            with open(tmp_path, "rb") as f:
                head = f.read(256).lstrip().lower()
            if head.startswith(b"<!doctype") or head.startswith(b"<html"):
                raise RuntimeError(
                    "Google Drive вернул HTML вместо файла "
                    "(нужен ручной download / публичный доступ)"
                )


def _extract_rvc_from_zip(zip_path: str, dest_pth: str) -> bool:
    """
    Достаёт .pth (+ опционально .index) из zip в models/rvc/.

    Выбор .pth: самый большой .pth в архиве (обычно это и есть веса).
    .index: файл с тем же stem, что у выбранного pth, иначе самый большой .index.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            infos = [info for info in zf.infolist() if not info.is_dir()]
            if len(infos) > RVC_ARCHIVE_MAX_MEMBERS:
                return False
            names = [info.filename for info in infos]
            pths = [n for n in names if n.lower().endswith(".pth")]
            if not pths:
                return False

            # largest pth
            def _sz(n):
                try:
                    return zf.getinfo(n).file_size
                except Exception:
                    return 0

            pths.sort(key=_sz, reverse=True)
            chosen_pth = pths[0]

            def _member_is_safe(name):
                info = zf.getinfo(name)
                if info.file_size < 0 or info.file_size > RVC_ARCHIVE_MAX_EXTRACTED_BYTES:
                    return False
                compressed = max(1, info.compress_size)
                return (info.file_size / compressed) <= RVC_ARCHIVE_MAX_COMPRESSION_RATIO

            if not _member_is_safe(chosen_pth):
                return False

            # Extract through temporary files so a failed/cancelled operation
            # never leaves a truncated checkpoint under its final name.
            os.makedirs(os.path.dirname(dest_pth), exist_ok=True)
            temp_pth = dest_pth + ".extracting"
            with zf.open(chosen_pth) as src, open(temp_pth, "wb") as dst:
                shutil.copyfileobj(src, dst)
            os.replace(temp_pth, dest_pth)

            # index
            dest_idx = os.path.splitext(dest_pth)[0] + ".index"
            pth_stem = os.path.splitext(os.path.basename(chosen_pth))[0].lower()
            idxs = [n for n in names if n.lower().endswith(".index")]
            chosen_idx = None
            for n in idxs:
                if os.path.splitext(os.path.basename(n))[0].lower() == pth_stem:
                    chosen_idx = n
                    break
            if not chosen_idx and idxs:
                idxs.sort(key=_sz, reverse=True)
                chosen_idx = idxs[0]
            if chosen_idx and _member_is_safe(chosen_idx):
                try:
                    temp_idx = dest_idx + ".extracting"
                    with zf.open(chosen_idx) as src, open(temp_idx, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    os.replace(temp_idx, dest_idx)
                except Exception:
                    _cleanup_tmp(dest_idx + ".extracting")
        return True
    except Exception:
        return False


def _download_is_html_error(path: str) -> bool:
    """True, если сервер вернул HTML/XML-страницу вместо архива или .pth."""
    try:
        with open(path, "rb") as f:
            head = f.read(4096).lstrip().lower()
    except Exception:
        return False
    return (
        head.startswith((b"<", b"&lt;", b"<!doctype", b"<?xml"))
        or b"<html" in head
        or b"<body" in head
    )


def download_model(entry: dict, progress_callback=None, cancelled_flag=None) -> bool:
    """
    Скачивает модель из каталога в models/rvc/.

    Поддерживает:
      - прямые URL (.pth / .zip), в т.ч. HuggingFace /resolve/
      - Google Drive file (best-effort; folder — нет)
      - zip → извлечение .pth (+ .index) рядом

    progress_callback(downloaded_bytes: int, total_bytes: int | None)

    SHA256 в entry["sha256"] опционален.

    Возвращает True при успехе, False при ошибке/отмене.
    """
    os.makedirs(RVC_MODELS_DIR, exist_ok=True)
    url = entry.get("url") or ""
    expected_sha256 = entry.get("sha256")
    dest_pth = local_model_path(entry)

    # Не downloadable (folder / только page) — честный отказ
    if entry.get("downloadable") is False or not _is_direct_downloadable(url):
        return False

    # Временный файл: по расширению URL
    path_ext = os.path.splitext(urllib.parse.urlparse(_clean_download_url(url)).path)[1].lower()
    if path_ext not in (".zip", ".pth"):
        # gdrive / unknown — качаем во временный .bin и определим по magic
        path_ext = ".bin"
    tmp = dest_pth + ".part" + path_ext

    try:
        _download_bytes_to_file(url, tmp, progress_callback, cancelled_flag)
        if _download_is_html_error(tmp):
            raise RuntimeError("сервер вернул HTML-страницу вместо файла модели")
    except InterruptedError:
        _cleanup_tmp(tmp)
        return False
    except Exception as e:
        print(f"[RVC] Ошибка скачивания {entry.get('name', entry.get('id'))}: {e}")
        _cleanup_tmp(tmp)
        return False

    if expected_sha256:
        actual = _sha256_of_file(tmp)
        if actual.lower() != expected_sha256.lower():
            print(
                f"[RVCCatalog] SHA256 не совпадает для {entry.get('name')}: "
                f"ожидалось {expected_sha256}, получено {actual}"
            )
            _cleanup_tmp(tmp)
            return False
    else:
        pass  # SHA256 у community-моделей обычно нет — не шумим

    # Определяем тип: zip или pth
    is_zip = False
    try:
        with open(tmp, "rb") as f:
            magic = f.read(4)
        if magic[:2] == b"PK":
            is_zip = True
        elif path_ext == ".zip":
            is_zip = True
        elif path_ext == ".pth":
            is_zip = False
    except Exception:
        is_zip = path_ext == ".zip"

    try:
        if is_zip:
            ok = _extract_rvc_from_zip(tmp, dest_pth)
            _cleanup_tmp(tmp)
            if not ok or not os.path.isfile(dest_pth):
                return False
            _save_local_model_metadata(entry, dest_pth)
            return True
        else:
            # прямой .pth
            if os.path.exists(dest_pth):
                os.remove(dest_pth)
            shutil.move(tmp, dest_pth)
            _save_local_model_metadata(entry, dest_pth)
            return True
    except Exception as e:
        print(f"[RVCCatalog] Ошибка финализации {entry.get('name')}: {e}")
        _cleanup_tmp(tmp)
        return False


def open_model_page(entry: dict) -> bool:
    """Открыть page_url модели в системном браузере (для folder / non-downloadable)."""
    url = entry.get("page_url") or entry.get("url") or ""
    if not url:
        return False
    try:
        import webbrowser

        webbrowser.open(url)
        return True
    except Exception:
        return False


def _cleanup_tmp(tmp: str):
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
    except Exception:
        pass
