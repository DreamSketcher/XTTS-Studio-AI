import os
import sys
import json
import shutil
import ssl
import time
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None  # если certifi не установлен — используем системное по умолчанию

REPO = "DreamSketcher/XTTS-Studio-portable-"
BRANCH = "main"
# BRANCH_RAW_BASE используется ТОЛЬКО для version.json — нам всегда нужен
# HEAD ветки, чтобы вовремя увидеть новый релиз.
BRANCH_RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
VERSION_URL = f"{BRANCH_RAW_BASE}/version.json"


def _raw_base_for(commit_sha: str = None) -> str:
    """
    URL-база для скачивания файлов релиза.

    Если известен commit_sha (получен через _get_latest_commit_sha(),
    api.github.com) — используем его: у каждого коммита свой уникальный
    URL на raw.githubusercontent.com, поэтому Fastly-кеш GitHub не может
    подсунуть под ним контент от старого коммита (в отличие от /main/...,
    который переиспользует один и тот же URL и может некоторое время
    отдавать закешированную старую версию файла сразу после пуша).

    Без commit_sha (не удалось получить через API — сеть, rate limit)
    — откатываемся на ветку, как раньше.
    """
    if commit_sha:
        return f"https://raw.githubusercontent.com/{REPO}/{commit_sha}"
    return BRANCH_RAW_BASE

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_VERSION_PATH = os.path.join(BASE_DIR, "version.json")

# Обновление больше не пишет сразу в рабочие файлы.
# Сначала всё скачивается и проверяется в STAGING_DIR, и только если
# ВСЕ файлы прошли проверку SHA256 — делается backup рабочих файлов
# и staged-файлы переносятся на место.
STAGING_DIR = os.path.join(BASE_DIR, "_update_staging")
BACKUP_DIR = os.path.join(BASE_DIR, "_update_backup")
ROLLBACK_MARKER = os.path.join(BASE_DIR, "_update_pending.json")

MAX_RETRIES = 4
RETRY_DELAY_SEC = 1.5  # увеличивается с каждой попыткой (backoff)


def get_local_version() -> str:
    try:
        with open(LOCAL_VERSION_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def _urlopen_with_retry(url: str, timeout: int = 15, max_retries: int = MAX_RETRIES):
    """urlopen с повторными попытками при временных SSL/сетевых обрывах.

    User-Agent обязателен для api.github.com (без него — 403 Forbidden).
    raw.githubusercontent.com его не требует, но лишним не будет.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "XTTS-Studio-Updater"})
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT)
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                print(f"[Updater] Попытка {attempt}/{max_retries} не удалась для {url}: {e}. Повтор через {RETRY_DELAY_SEC * attempt:.1f}с...")
                time.sleep(RETRY_DELAY_SEC * attempt)
            else:
                print(f"[Updater] Все {max_retries} попыток не удались для {url}: {e}")
    raise last_err


COMMITS_API_URL = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"


def _get_latest_commit_sha() -> str:
    """
    Узнаёт актуальный commit SHA ветки через api.github.com, а не через
    raw.githubusercontent.com. У raw-CDN (Fastly) после пуша бывает лаг
    в несколько минут, когда он ещё отдаёт закешированное старое содержимое
    файла по тому же URL ветки — из-за этого возникают ложные SHA256
    mismatch сразу после релиза. api.github.com — обычный REST-эндпоинт,
    отдаёт актуальный HEAD без этой проблемы.

    Если запрос не удался (сеть, rate limit и т.п.) — возвращает None,
    и вызывающий код просто откатывается на скачивание по ветке (как было
    раньше), т.е. без commit_sha ничего не ломается, просто теряется
    защита от гонки с кешем.
    """
    try:
        with _urlopen_with_retry(COMMITS_API_URL, timeout=10, max_retries=2) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data.get("sha")
    except Exception as e:
        print(f"[Updater] Не удалось получить актуальный commit_sha (не критично): {e}")
        return None


def get_remote_version_info() -> dict:
    try:
        with _urlopen_with_retry(VERSION_URL, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Не удалось получить информацию об обновлении: {e}")


def _sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _version_gt(a: str, b: str) -> bool:
    """Возвращает True если версия a новее b."""
    def parse(v):
        try:
            return tuple(int(x) for x in v.strip().split("."))
        except Exception:
            return (0, 0, 0)
    return parse(a) > parse(b)


def _version_lt(a: str, b: str) -> bool:
    return _version_gt(b, a)


def check_update() -> dict:
    """
    Возвращает:
      { "available": True/False, "local": "1.0.0", "remote": "1.0.1",
        "files": [...], "sha256": {...}, "changelog": "...",
        "min_app_version": "1.0.0" или None,
        "needs_manual_reinstall": True/False }

    needs_manual_reinstall=True означает, что текущая версия слишком старая
    для инкрементального автообновления (см. min_app_version в манифесте) —
    в этом случае нужно предложить пользователю скачать установщик целиком,
    а не тянуть файлы поштучно.
    """
    local = get_local_version()
    try:
        info = get_remote_version_info()
        remote = info.get("version", "0.0.0")
        available = _version_gt(remote, local)

        min_required = info.get("min_app_version")
        needs_manual = bool(min_required) and _version_lt(local, min_required)

        return {
            "available": available,
            "local": local,
            "remote": remote,
            "files": info.get("files", []),
            "sha256": info.get("sha256", {}),
            "removed_files": info.get("removed_files", []),
            "changelog": info.get("changelog", ""),
            "min_app_version": min_required,
            "needs_manual_reinstall": needs_manual,
            "commit_sha": _get_latest_commit_sha() if available else None,
        }
    except Exception as e:
        return {"available": False, "local": local, "remote": None, "error": str(e)}


def _clear_dir(path: str):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def _is_cancelled(cancelled_flag) -> bool:
    """Единый формат флага отмены — совместимо с engine/local_llm_client.py."""
    if cancelled_flag is None:
        return False
    if isinstance(cancelled_flag, dict):
        return bool(cancelled_flag.get("cancelled"))
    if isinstance(cancelled_flag, (list, tuple)) and len(cancelled_flag) > 0:
        return bool(cancelled_flag[0])
    return False


def _download_to_staging(relative_path: str, expected_sha256: str = None, cancelled_flag=None,
                          raw_base: str = None, sha_mismatch_retries: int = 3,
                          sha_mismatch_delay: float = 4.0) -> bool:
    """
    Скачивает файл во временный staging (НЕ в рабочую директорию) и
    проверяет его SHA256 перед тем как считать файл готовым к применению.

    ВАЖНО: expected_sha256 обязателен. Если в манифесте (version.json ->
    "sha256") для этого файла нет хэша — файл считается непрошедшим
    проверку и НЕ применяется, даже если скачался без ошибок. Раньше
    отсутствие хэша в манифесте тихо пропускало проверку — это было дырой:
    сломанный/неполный релизный манифест приводил к обновлению без
    проверки целостности вообще.

    Скачивание читается блоками и проверяет cancelled_flag на каждом блоке,
    чтобы отмена пользователем срабатывала быстро даже на крупном файле,
    а не только между файлами.

    SHA256-mismatch retry: даже с commit-pinned URL (см. _raw_base_for)
    изредка попадается прогретый под старый контент участок CDN Fastly —
    сам GitHub docs предупреждает, что инвалидация кеша не мгновенна.
    Это не сетевая ошибка (соединение прошло успешно), поэтому обычный
    _urlopen_with_retry тут не помогает — нужна отдельная пауза подольше
    и повторное скачивание, а не просто повтор запроса.
    """
    base = raw_base or BRANCH_RAW_BASE
    url = f"{base}/{urllib.parse.quote(relative_path)}"
    dst = os.path.join(STAGING_DIR, relative_path.replace("/", os.sep))
    tmp = dst + ".part"

    if not expected_sha256:
        print(f"[Updater] В манифесте нет SHA256 для {relative_path} — файл отклонён")
        return False

    attempt = 0
    while True:
        attempt += 1
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with _urlopen_with_retry(url, timeout=30) as resp:
                with open(tmp, "wb") as f:
                    while True:
                        if _is_cancelled(cancelled_flag):
                            raise InterruptedError("Обновление отменено пользователем")
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)

            actual = _sha256_of_file(tmp)
            if actual.lower() != expected_sha256.lower():
                print(f"[Updater] SHA256 не совпадает для {relative_path} "
                      f"(попытка {attempt}/{sha_mismatch_retries + 1}): "
                      f"ожидалось {expected_sha256}, получено {actual}")
                try:
                    os.remove(tmp)
                except Exception:
                    pass
                if attempt <= sha_mismatch_retries:
                    delay = sha_mismatch_delay * attempt  # backoff: 4с, 8с, 12с...
                    for _ in range(int(delay * 10)):
                        if _is_cancelled(cancelled_flag):
                            raise InterruptedError("Обновление отменено пользователем")
                        time.sleep(0.1)
                    continue
                return False

            if os.path.exists(dst):
                os.remove(dst)
            shutil.move(tmp, dst)
            return True
        except InterruptedError:
            try:
                os.remove(tmp)
            except Exception:
                pass
            raise
        except Exception as e:
            print(f"[Updater] Ошибка загрузки {relative_path}: {e}")
            try:
                os.remove(tmp)
            except Exception:
                pass
            return False


def _delete_removed_files(removed_files: list):
    """
    Удаляет файлы, которых больше нет в новом манифесте (переименованные,
    перенесённые или объединённые при рефакторинге на стороне разработчика).

    Файлы уже забэкаплены заранее (см. apply_update -> _backup_current_files),
    поэтому это безопасно откатывается через rollback_update() при необходимости.

    Ошибка удаления одного файла НЕ прерывает обновление — это уборка мусора,
    а не критический шаг; лучше оставить лишний файл на диске, чем откатить
    иначе успешное обновление.
    """
    for rel in removed_files:
        path = os.path.join(BASE_DIR, rel.replace("/", os.sep))
        try:
            if os.path.isfile(path):
                os.remove(path)
                print(f"[Updater] Удалён устаревший файл: {rel}")
        except Exception as e:
            print(f"[Updater] Не удалось удалить устаревший файл {rel}: {e}")

    # Подчищаем опустевшие после удаления директории (best-effort)
    dirs = {os.path.dirname(os.path.join(BASE_DIR, rel.replace("/", os.sep))) for rel in removed_files}
    for d in sorted(dirs, key=len, reverse=True):  # сначала самые глубокие
        try:
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                print(f"[Updater] Удалена опустевшая папка: {os.path.relpath(d, BASE_DIR)}")
        except Exception:
            pass


def _backup_current_files(files: list):
    """Копирует текущие рабочие версии файлов в BACKUP_DIR перед заменой."""
    _clear_dir(BACKUP_DIR)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for rel in files:
        src = os.path.join(BASE_DIR, rel.replace("/", os.sep))
        if os.path.exists(src):
            dst = os.path.join(BACKUP_DIR, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    if os.path.exists(LOCAL_VERSION_PATH):
        shutil.copy2(LOCAL_VERSION_PATH, os.path.join(BACKUP_DIR, "version.json"))


def _move_staged_to_live(files: list):
    for rel in files:
        staged = os.path.join(STAGING_DIR, rel.replace("/", os.sep))
        if not os.path.exists(staged):
            continue
        live = os.path.join(BASE_DIR, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(live), exist_ok=True)
        if os.path.exists(live):
            os.remove(live)
        shutil.move(staged, live)


def _write_rollback_marker(old_version: str, new_version: str, files: list, removed_files: list = None):
    data = {
        "old_version": old_version,
        "new_version": new_version,
        "files": files,
        "removed_files": removed_files or [],
        "attempt": 0,
        "timestamp": time.time(),
    }
    with open(ROLLBACK_MARKER, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def apply_update(files: list, sha256_map: dict = None, removed_files: list = None,
                  progress_callback=None, cancelled_flag=None, commit_sha: str = None) -> bool:
    """
    Безопасный цикл обновления:
      1. скачать ВСЕ файлы в staging, не трогая рабочую копию
      2. проверить SHA256 каждого файла (если хэш есть в манифесте)
      3. если хоть один файл не прошёл проверку/не скачался — отменить всё,
         рабочие файлы остаются как есть
      4. если всё ок — сделать backup рабочих файлов (включая те, что будут
         удалены как устаревшие)
      5. перенести staged-файлы поверх рабочих
      6. удалить файлы, которых больше нет в новом манифесте (removed_files) —
         переименованные/перенесённые/объединённые при рефакторинге; иначе
         они бы бесконечно копились на дисках уже обновившихся пользователей
      7. записать маркер "обновление ожидает подтверждения" (см.
         check_startup_health / confirm_update_success ниже)

    cancelled_flag — тот же формат, что и в engine/local_llm_client.py
    (dict с ключом "cancelled" или list/tuple с элементом [0]). Проверяется
    во время скачивания/проверки (шаги 1-3), а также ЕЩЁ РАЗ сразу после
    того как все файлы прошли проверку — то есть отмена успевает сработать
    даже если её выставили прямо на последнем файле. Настоящая точка
    невозврата — это момент, когда физически начинается backup+подмена
    рабочих файлов (шаг 4+): дальше cancelled_flag уже не проверяется,
    потому что прервать подмену на середине опаснее, чем просто её закончить.
    """
    sha256_map = sha256_map or {}
    removed_files = removed_files or []
    raw_base = _raw_base_for(commit_sha)
    _clear_dir(STAGING_DIR)
    os.makedirs(STAGING_DIR, exist_ok=True)

    def _cancel_cleanup() -> bool:
        print("[Updater] Обновление отменено пользователем — удаляю скачанные файлы...")
        _clear_dir(STAGING_DIR)
        return False

    total = len(files)
    failed = []
    for i, f in enumerate(files):
        if _is_cancelled(cancelled_flag):
            return _cancel_cleanup()
        try:
            ok = _download_to_staging(f, sha256_map.get(f), cancelled_flag=cancelled_flag, raw_base=raw_base)
        except InterruptedError:
            return _cancel_cleanup()
        if not ok:
            failed.append(f)
        if progress_callback:
            progress_callback(i + 1, total)

    if failed and not _is_cancelled(cancelled_flag):
        print(f"[Updater] Повторная попытка для {len(failed)} файлов после паузы...")
        time.sleep(2.0)
        still_failed = []
        for f in failed:
            if _is_cancelled(cancelled_flag):
                break
            try:
                ok = _download_to_staging(f, sha256_map.get(f), cancelled_flag=cancelled_flag, raw_base=raw_base)
            except InterruptedError:
                break
            if not ok:
                still_failed.append(f)
        failed = still_failed

    if _is_cancelled(cancelled_flag):
        return _cancel_cleanup()

    if failed:
        print(f"[Updater] Обновление отменено — не прошли скачивание/проверку: {failed}")
        _clear_dir(STAGING_DIR)
        return False

    # ── Точка невозврата ── дальше идёт backup + подмена рабочих файлов;
    # cancelled_flag больше не проверяется.
    old_version = get_local_version()

    try:
        _backup_current_files(files + removed_files)
    except Exception as e:
        print(f"[Updater] Не удалось создать backup, обновление отменено: {e}")
        _clear_dir(STAGING_DIR)
        return False

    try:
        _move_staged_to_live(files)
    except Exception as e:
        print(f"[Updater] Ошибка применения обновления, откатываю: {e}")
        rollback_update()
        return False

    if removed_files:
        _delete_removed_files(removed_files)

    try:
        info = get_remote_version_info()
        new_version = info.get("version", "?")
        with open(LOCAL_VERSION_PATH, "w", encoding="utf-8") as fp:
            json.dump(info, fp, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Updater] Не удалось сохранить version.json: {e}")
        new_version = "?"

    _write_rollback_marker(old_version, new_version, files, removed_files)
    _clear_dir(STAGING_DIR)
    return True


def has_pending_update_confirmation() -> bool:
    """True, если обновление применено, но ещё не подтверждено успешным запуском."""
    return os.path.exists(ROLLBACK_MARKER)


def check_startup_health() -> str:
    """
    Вызывать САМЫМ ПЕРВЫМ делом при старте приложения, до создания GUI.

    Возвращает:
      "ok"            — обновление не ожидает подтверждения, всё штатно
      "first_attempt" — это первый запуск после применения обновления,
                         можно продолжать грузить приложение как обычно
      "rolled_back"   — прошлый запуск после обновления не дошёл до
                         confirm_update_success() (упал/завис) — файлы
                         уже автоматически откачены на предыдущую версию

    После "first_attempt": как только главное окно успешно открылось,
    ОБЯЗАТЕЛЬНО вызвать confirm_update_success(), иначе при следующем
    запуске будет откат, даже если на самом деле всё было в порядке.
    """
    if not os.path.exists(ROLLBACK_MARKER):
        return "ok"

    try:
        with open(ROLLBACK_MARKER, "r", encoding="utf-8") as f:
            marker = json.load(f)
    except Exception:
        marker = {}

    attempt = marker.get("attempt", 0)
    if attempt >= 1:
        # Прошлый запуск не подтвердился успешным стартом — откатываемся
        rollback_update()
        return "rolled_back"

    marker["attempt"] = attempt + 1
    try:
        with open(ROLLBACK_MARKER, "w", encoding="utf-8") as f:
            json.dump(marker, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return "first_attempt"


def confirm_update_success():
    """
    Вызвать из gui.py сразу после того, как главное окно успешно открылось.
    Значит обновление прошло нормально — удаляем маркер и backup.
    """
    try:
        if os.path.exists(ROLLBACK_MARKER):
            os.remove(ROLLBACK_MARKER)
        _clear_dir(BACKUP_DIR)
    except Exception as e:
        print(f"[Updater] Не удалось подтвердить обновление: {e}")


def rollback_update() -> bool:
    """
    Восстанавливает файлы из backup. Вызывается автоматически из
    check_startup_health(), если прошлый запуск не подтвердился.
    Можно также вызвать вручную (например, из XTTS_DIAG.bat через
    отдельный python-вызов) для принудительного отката.
    """
    if not os.path.isdir(BACKUP_DIR):
        print("[Updater] Backup не найден, откат невозможен.")
        try:
            os.remove(ROLLBACK_MARKER)
        except Exception:
            pass
        return False
    try:
        marker = {}
        if os.path.exists(ROLLBACK_MARKER):
            with open(ROLLBACK_MARKER, "r", encoding="utf-8") as f:
                marker = json.load(f)
        files = marker.get("files", [])
        removed_files = marker.get("removed_files", [])
        for rel in files + removed_files:
            backup_src = os.path.join(BACKUP_DIR, rel.replace("/", os.sep))
            if os.path.exists(backup_src):
                live = os.path.join(BASE_DIR, rel.replace("/", os.sep))
                os.makedirs(os.path.dirname(live), exist_ok=True)
                shutil.copy2(backup_src, live)
        backup_version = os.path.join(BACKUP_DIR, "version.json")
        if os.path.exists(backup_version):
            shutil.copy2(backup_version, LOCAL_VERSION_PATH)
        print(f"[Updater] Откат выполнен, версия восстановлена: {marker.get('old_version', '?')}")
        return True
    except Exception as e:
        print(f"[Updater] Ошибка отката: {e}")
        return False
    finally:
        try:
            os.remove(ROLLBACK_MARKER)
        except Exception:
            pass
        _clear_dir(BACKUP_DIR)


def collect_update_diagnostics(check_result: dict = None) -> str:
    """
    Собирает контекст для отчёта об ошибке (см. error_report.py):
    версии, наличие маркеров/staging/backup, и последнюю ошибку check_update(),
    если она была передана.

    Не читает содержимое файлов и не логирует ничего нового — только
    текущее состояние апдейтера на момент вызова. Используется GUI-слоем
    при показе диалога "не удалось обновиться" — вызывающий код сам решает,
    когда и стоит ли предлагать пользователю отправить отчёт.
    """
    lines = [
        f"local_version = {get_local_version()}",
        f"staging_dir_exists = {os.path.isdir(STAGING_DIR)}",
        f"backup_dir_exists = {os.path.isdir(BACKUP_DIR)}",
        f"pending_confirmation = {has_pending_update_confirmation()}",
    ]
    if check_result:
        lines.append(f"check_update_result = {json.dumps(check_result, ensure_ascii=False)}")
    if os.path.exists(ROLLBACK_MARKER):
        try:
            with open(ROLLBACK_MARKER, "r", encoding="utf-8") as f:
                lines.append(f"rollback_marker = {f.read()}")
        except Exception:
            pass
    return "\n".join(lines)


def restart():
    python = sys.executable
    os.execv(python, [python] + sys.argv)