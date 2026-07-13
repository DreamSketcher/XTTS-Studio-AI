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
CATALOG_CACHE_PATH = os.path.join(RVC_MODELS_DIR, "catalog_cache.json")

CATALOG_RAW_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/rvc_catalog.json"

# voice-models.com — community-индекс RVC-моделей (не официальный API,
# reverse-engineered из публичного UI сайта; при поломке — фоллбэк на seed).
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
VM_SEARCH_TIMEOUT = 8  # сек; voice-models часто тормозит из РФ/на медленном канале
VM_SEARCH_ATTEMPTS = 1  # без ретраев: KeyRelease и так шлёт много запросов

# Не долбим GitHub 4×1.5–4.5с на каждый open dropdown / search.
# rvc_catalog.json на main сейчас 404 — после первого фейла ждём cooldown.
_GITHUB_CATALOG_COOLDOWN_SEC = 6 * 60 * 60  # 6 часов после 404/ошибки
_github_catalog_fail_until = 0.0
_github_catalog_fail_logged = False
_local_catalog_cache = None  # in-memory: seed/кэш без повторного disk+network


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
    if path.endswith(".zip") or "huggingface.co" in (url or "") or "drive.google.com" in (url or ""):
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
        rows.append({
            "mid": mid,
            "path": path,
            "title": title,
            "author": creator or "Community",
            "size": size,
            "download": _clean_download_url(dl or ""),
        })
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
                entry = _row_to_entry({
                    "mid": mid,
                    "title": title,
                    "author": "Community",
                    "size": None,
                    "download": link if _is_direct_downloadable(link) else "",
                })
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


def search_catalog(query: str, max_results: int = SEARCH_MAX_RESULTS,
                   live: bool = True) -> list:
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
            blob = " ".join([
                str(entry.get("name") or ""),
                str(entry.get("author") or ""),
                str(entry.get("description") or ""),
                str(entry.get("id") or ""),
            ]).lower()
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
    filename = entry.get("filename") or os.path.basename(
        urllib.parse.urlparse(entry["url"]).path
    )
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
    removed_any = False
    for p in (pth, idx):
        try:
            if os.path.isfile(p):
                os.remove(p)
                removed_any = True
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


def _download_bytes_to_file(url: str, tmp_path: str, progress_callback=None,
                            cancelled_flag=None) -> None:
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


def _download_gdrive(uc_url: str, tmp_path: str, progress_callback=None,
                     cancelled_flag=None) -> None:
    """Best-effort скачивание Google Drive file (с confirm-cookie для больших файлов)."""
    # Первый запрос
    req = urllib.request.Request(uc_url, headers={"User-Agent": VOICE_MODELS_UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        data = resp.read()
        # Если сразу бинарник
        if "text/html" not in ctype and not data[:200].lstrip().startswith(b"<!DOCTYPE") \
                and not data[:200].lstrip().lower().startswith(b"<html"):
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
            names = [n for n in zf.namelist() if not n.endswith("/")]
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
            # extract pth
            os.makedirs(os.path.dirname(dest_pth), exist_ok=True)
            with zf.open(chosen_pth) as src, open(dest_pth, "wb") as dst:
                shutil.copyfileobj(src, dst)

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
            if chosen_idx:
                try:
                    with zf.open(chosen_idx) as src, open(dest_idx, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                except Exception:
                    pass
        return True
    except Exception:
        return False


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
    except InterruptedError:
        _cleanup_tmp(tmp)
        return False
    except Exception as e:
        print(f"[RVCCatalog] Ошибка скачивания {entry.get('name', entry.get('id'))}: {e}")
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
            if not ok:
                return False
            return os.path.isfile(dest_pth)
        else:
            # прямой .pth
            if os.path.exists(dest_pth):
                os.remove(dest_pth)
            shutil.move(tmp, dest_pth)
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
