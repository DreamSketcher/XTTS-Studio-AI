import hashlib
import json
import os
import shutil
import ssl
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PureWindowsPath

try:
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None  # если certifi не установлен — используем системное по умолчанию

REPO = "DreamSketcher/XTTS-Studio"
BRANCH = "main"

# Primary release channel: GitHub Release assets (stable). Clients never read
# raw content from the development branch.
RELEASE_BASE = f"https://github.com/{REPO}/releases/latest/download"
VERSION_URL = f"{RELEASE_BASE}/version.json"
SIGNATURE_URL = f"{RELEASE_BASE}/version.json.sig"
DEFAULT_ARCHIVE_URL = f"{RELEASE_BASE}/XTTS-Studio-portable.zip"

# ---------------------------------------------------------------------------
# Legacy shims (raw.githubusercontent.com + commits API).
# Kept for unit tests and older code paths that still pass commit_sha /
# raw_base. Production check_update / get_remote_version_info use RELEASE_BASE.
# ---------------------------------------------------------------------------
BRANCH_RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
COMMITS_API_URL = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"


def _raw_base_for(commit_sha: str = None) -> str:
    """
    URL-база для скачивания файлов релиза (legacy per-file path).

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
ARCHIVE_STAGING_NAME = "_update_payload.zip"

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
    raw.githubusercontent.com / github.com releases его не требуют, но
    лишним не будет.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "XTTS-Studio-Updater"})
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT)
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                print(
                    f"[Updater] Попытка {attempt}/{max_retries} не удалась для {url}: {e}. "
                    f"Повтор через {RETRY_DELAY_SEC * attempt:.1f}с..."
                )
                time.sleep(RETRY_DELAY_SEC * attempt)
            else:
                print(f"[Updater] Все {max_retries} попыток не удались для {url}: {e}")
    raise last_err


def _get_latest_commit_sha() -> str:
    """
    Legacy: узнаёт актуальный commit SHA ветки через api.github.com.

    Больше не используется production-путём обновления (Release assets),
    но сохраняется для unit-тестов и редких fallback-сценариев per-file.
    """
    try:
        with _urlopen_with_retry(COMMITS_API_URL, timeout=10, max_retries=2) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data.get("sha")
    except Exception as e:
        print(f"[Updater] Не удалось получить актуальный commit_sha (не критично): {e}")
        return None


def get_remote_version_info(commit_sha: str = None) -> dict:
    """Download and authenticate an immutable release manifest.

    Production path fetches version.json + version.json.sig from the latest
    GitHub Release. The optional *commit_sha* argument keeps the legacy
    raw.githubusercontent.com path for tests and older tooling. Authenticity
    always comes from the embedded offline Ed25519 release key.
    """
    from engine.update_signing import verify_manifest_signature

    if commit_sha:
        base = _raw_base_for(commit_sha)
        version_url = f"{base}/version.json"
        signature_url = f"{base}/version.json.sig"
    else:
        version_url = VERSION_URL
        signature_url = SIGNATURE_URL
    try:
        with _urlopen_with_retry(version_url, timeout=10) as response:
            manifest_bytes = response.read()
        with _urlopen_with_retry(signature_url, timeout=10) as response:
            signature_bytes = response.read()
        verify_manifest_signature(manifest_bytes, signature_bytes)
        info = json.loads(manifest_bytes.decode("utf-8"))
        if not isinstance(info, dict):
            raise ValueError("update manifest must be a JSON object")
        return info
    except Exception as e:
        raise RuntimeError(f"Не удалось проверить информацию об обновлении: {e}") from e


def _sha256_of_file(path: str, relative_path: str = "") -> str:
    if relative_path:
        from engine.release_hashing import release_sha256_file

        return release_sha256_file(path, relative_path)
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
        "archive_sha256": "...", "archive_url": "...",
        "min_app_version": "1.0.0" или None,
        "needs_manual_reinstall": True/False }

    needs_manual_reinstall=True означает, что текущая версия слишком старая
    для инкрементального автообновления (см. min_app_version в манифесте) —
    в этом случае нужно предложить пользователю скачать установщик целиком.
    """
    local = get_local_version()
    try:
        info = get_remote_version_info()
        remote = info.get("version", "0.0.0")
        available = _version_gt(remote, local)

        min_required = info.get("min_app_version")
        needs_manual = bool(min_required) and _version_lt(local, min_required)

        archive_sha256 = info.get("archive_sha256")
        archive_url = info.get("archive_url")
        if archive_sha256 and not archive_url:
            archive_url = DEFAULT_ARCHIVE_URL

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
            "archive_sha256": archive_sha256,
            "archive_url": archive_url,
            "archive_size": info.get("archive_size"),
            # legacy field retained so older GUI builds keep working
            "commit_sha": None,
        }
    except Exception as e:
        return {"available": False, "local": local, "remote": None, "error": str(e)}


def _clear_dir(path: str):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def _safe_relative_path(relative_path: str) -> str:
    """Validate and normalize an update-manifest path.

    Manifest paths are always portable POSIX-style paths relative to BASE_DIR.
    Reject traversal, absolute/drive/UNC paths and ambiguous Windows syntax even
    when the updater is tested on a non-Windows host.
    """
    if not isinstance(relative_path, str):
        raise ValueError("Путь обновления должен быть строкой")

    value = relative_path.strip()
    if not value or "\x00" in value:
        raise ValueError("Пустой или некорректный путь обновления")

    windows_path = PureWindowsPath(value)
    if windows_path.is_absolute() or windows_path.drive or windows_path.root:
        raise ValueError(f"Абсолютный путь запрещён: {relative_path!r}")

    # Backslashes are separators on Windows. Normalize them before validating
    # components so a manifest cannot behave differently across platforms.
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Некорректный относительный путь: {relative_path!r}")
    if any(":" in part for part in parts):
        raise ValueError(f"Двоеточие в пути обновления запрещено: {relative_path!r}")

    return "/".join(parts)


def _safe_path_under(root: str, relative_path: str) -> str:
    """Return a resolved path guaranteed to stay below *root*.

    Path.resolve(strict=False) also follows existing parent symlinks, preventing
    a junction/symlink inside staging or the app directory from escaping root.
    """
    rel = _safe_relative_path(relative_path)
    root_path = Path(root).resolve()
    candidate = (root_path / Path(*rel.split("/"))).resolve(strict=False)
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(
            f"Путь выходит за пределы разрешённого каталога: {relative_path!r}"
        ) from exc
    return str(candidate)


def _validate_manifest_paths(files: list, removed_files: list = None) -> tuple[list, list]:
    """Fail closed before an update performs network or filesystem actions."""
    if not isinstance(files, list) or not isinstance(removed_files or [], list):
        raise ValueError("files и removed_files должны быть списками")

    safe_files = [_safe_relative_path(item) for item in files]
    safe_removed = [_safe_relative_path(item) for item in (removed_files or [])]
    if len(set(safe_files)) != len(safe_files) or len(set(safe_removed)) != len(safe_removed):
        raise ValueError("Манифест содержит повторяющиеся пути")
    if set(safe_files) & set(safe_removed):
        raise ValueError("Один путь нельзя одновременно обновлять и удалять")
    return safe_files, safe_removed


def _is_cancelled(cancelled_flag) -> bool:
    """Единый формат флага отмены — совместимо с engine/local_llm_client.py."""
    if cancelled_flag is None:
        return False
    if isinstance(cancelled_flag, dict):
        return bool(cancelled_flag.get("cancelled"))
    if isinstance(cancelled_flag, (list, tuple)) and len(cancelled_flag) > 0:
        return bool(cancelled_flag[0])
    return False


def _download_to_staging(
    relative_path: str,
    expected_sha256: str = None,
    cancelled_flag=None,
    raw_base: str = None,
    sha_mismatch_retries: int = 3,
    sha_mismatch_delay: float = 4.0,
) -> bool:
    """
    Скачивает файл во временный staging (НЕ в рабочую директорию) и
    проверяет его SHA256 перед тем как считать файл готовым к применению.

    Legacy per-file path. Production updates prefer a single signed archive
    via _download_archive_to_staging + _extract_archive_safely.

    ВАЖНО: expected_sha256 обязателен. Если в манифесте (version.json ->
    "sha256") для этого файла нет хэша — файл считается непрошедшим
    проверку и НЕ применяется, даже если скачался без ошибок.
    """
    relative_path = _safe_relative_path(relative_path)
    base = raw_base or BRANCH_RAW_BASE
    url = f"{base}/{urllib.parse.quote(relative_path)}"
    dst = _safe_path_under(STAGING_DIR, relative_path)
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

            actual = _sha256_of_file(tmp, relative_path)
            if actual.lower() != expected_sha256.lower():
                print(
                    f"[Updater] SHA256 не совпадает для {relative_path} "
                    f"(попытка {attempt}/{sha_mismatch_retries + 1}): "
                    f"ожидалось {expected_sha256}, получено {actual}"
                )
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


def _download_archive_to_staging(
    expected_sha256: str,
    archive_url: str = None,
    cancelled_flag=None,
) -> str:
    """Download a single release archive into staging and verify its SHA-256.

    Returns the absolute path of the verified archive inside STAGING_DIR.
    Raises InterruptedError on cancel; RuntimeError on network/hash failure.
    """
    if not expected_sha256:
        raise RuntimeError("archive_sha256 отсутствует в манифесте")
    url = archive_url or DEFAULT_ARCHIVE_URL
    os.makedirs(STAGING_DIR, exist_ok=True)
    dst = os.path.join(STAGING_DIR, ARCHIVE_STAGING_NAME)
    tmp = dst + ".part"

    try:
        with _urlopen_with_retry(url, timeout=60) as resp:
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
            raise RuntimeError(
                f"SHA256 архива не совпадает: ожидалось {expected_sha256}, получено {actual}"
            )
        if os.path.exists(dst):
            os.remove(dst)
        shutil.move(tmp, dst)
        return dst
    except InterruptedError:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


def _extract_archive_safely(archive_path: str, dest_dir: str = None) -> list:
    """Extract a zip into staging with zip-slip protection.

    Does NOT use ZipFile.extract / extractall. Every member is validated via
    _safe_relative_path + _safe_path_under; absolute paths, ``../``, drive
    letters and colon-bearing segments are rejected.
    Returns the list of extracted relative paths (POSIX style).
    """
    dest = dest_dir or STAGING_DIR
    extracted: list[str] = []
    with zipfile.ZipFile(archive_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename
            if not name or name.endswith("/"):
                # Directory entries — skip; parents are created for files.
                continue
            # Zip members may use backslashes on some Windows-produced archives.
            relative = _safe_relative_path(name)
            target = _safe_path_under(dest, relative)
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, length=1024 * 1024)
            extracted.append(relative)
    if not extracted:
        raise RuntimeError("архив обновления пуст")
    return extracted


def _verify_staged_files(files: list, sha256_map: dict) -> list:
    """Return list of relative paths that failed per-file SHA-256 checks."""
    failed = []
    for rel in files:
        expected = (sha256_map or {}).get(rel)
        if not expected:
            # version.json / version.json.sig may be inside the archive without
            # being members of the payload hash map — skip only those two.
            if rel in ("version.json", "version.json.sig"):
                continue
            print(f"[Updater] В манифесте нет SHA256 для {rel} — файл отклонён")
            failed.append(rel)
            continue
        staged = _safe_path_under(STAGING_DIR, rel)
        if not os.path.isfile(staged):
            print(f"[Updater] В staging нет файла {rel}")
            failed.append(rel)
            continue
        actual = _sha256_of_file(staged, rel)
        if actual.lower() != expected.lower():
            print(
                f"[Updater] SHA256 не совпадает для {rel}: "
                f"ожидалось {expected}, получено {actual}"
            )
            failed.append(rel)
    return failed


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
        path = _safe_path_under(BASE_DIR, rel)
        try:
            if os.path.isfile(path):
                os.remove(path)
                print(f"[Updater] Удалён устаревший файл: {rel}")
        except Exception as e:
            print(f"[Updater] Не удалось удалить устаревший файл {rel}: {e}")

    # Подчищаем опустевшие после удаления директории (best-effort)
    dirs = {os.path.dirname(_safe_path_under(BASE_DIR, rel)) for rel in removed_files}
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
        src = _safe_path_under(BASE_DIR, rel)
        if os.path.exists(src):
            dst = _safe_path_under(BACKUP_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
    if os.path.exists(LOCAL_VERSION_PATH):
        shutil.copy2(LOCAL_VERSION_PATH, os.path.join(BACKUP_DIR, "version.json"))


def _move_staged_to_live(files: list):
    for rel in files:
        staged = _safe_path_under(STAGING_DIR, rel)
        if not os.path.exists(staged):
            continue
        live = _safe_path_under(BASE_DIR, rel)
        os.makedirs(os.path.dirname(live), exist_ok=True)
        if os.path.exists(live):
            os.remove(live)
        shutil.move(staged, live)


def _write_rollback_marker(
    old_version: str, new_version: str, files: list, removed_files: list = None
):
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


def _persist_remote_manifest(info: dict) -> str:
    """Write the authenticated remote manifest as the local version.json."""
    new_version = info.get("version", "?") if isinstance(info, dict) else "?"
    try:
        with open(LOCAL_VERSION_PATH, "w", encoding="utf-8") as fp:
            json.dump(info, fp, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Updater] Не удалось сохранить version.json: {e}")
    return new_version


def _apply_from_staging(
    files: list,
    removed_files: list,
    remote_info: dict = None,
    commit_sha: str = None,
) -> bool:
    """Shared post-download path: backup → move → delete → marker."""
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

    if remote_info is not None:
        new_version = _persist_remote_manifest(remote_info)
    else:
        try:
            info = get_remote_version_info(commit_sha)
            new_version = _persist_remote_manifest(info)
        except Exception as e:
            print(f"[Updater] Не удалось сохранить version.json: {e}")
            new_version = "?"

    _write_rollback_marker(old_version, new_version, files, removed_files)
    _clear_dir(STAGING_DIR)
    return True


def _apply_update_from_archive(
    files: list,
    sha256_map: dict,
    removed_files: list,
    archive_sha256: str,
    archive_url: str = None,
    progress_callback=None,
    cancelled_flag=None,
    remote_info: dict = None,
) -> bool:
    """Archive-mode update: one zip download + safe extract + optional per-file hashes."""

    def _cancel_cleanup() -> bool:
        print("[Updater] Обновление отменено пользователем — удаляю скачанные файлы...")
        _clear_dir(STAGING_DIR)
        return False

    _clear_dir(STAGING_DIR)
    os.makedirs(STAGING_DIR, exist_ok=True)

    if _is_cancelled(cancelled_flag):
        return _cancel_cleanup()

    try:
        archive_path = _download_archive_to_staging(
            expected_sha256=archive_sha256,
            archive_url=archive_url,
            cancelled_flag=cancelled_flag,
        )
    except InterruptedError:
        return _cancel_cleanup()
    except Exception as e:
        print(f"[Updater] Не удалось скачать архив обновления: {e}")
        _clear_dir(STAGING_DIR)
        return False

    if progress_callback:
        progress_callback(1, 3)

    if _is_cancelled(cancelled_flag):
        return _cancel_cleanup()

    try:
        extracted = _extract_archive_safely(archive_path)
    except Exception as e:
        print(f"[Updater] Не удалось безопасно распаковать архив: {e}")
        _clear_dir(STAGING_DIR)
        return False

    # Drop the zip itself from staging so it is not moved into the live tree.
    try:
        os.remove(archive_path)
    except Exception:
        pass

    if progress_callback:
        progress_callback(2, 3)

    # Prefer the authenticated manifest's file list when present; otherwise use
    # whatever the archive actually contained (minus self-describing metadata
    # that is handled separately).
    payload_files = [
        p for p in (files or extracted) if p not in ("version.json", "version.json.sig")
    ]
    # Always include any extra payload members that the archive brought in so
    # newly-added files are installed even if the caller's list is stale.
    for rel in extracted:
        if rel not in payload_files and rel not in ("version.json", "version.json.sig"):
            payload_files.append(rel)

    try:
        payload_files, removed_files = _validate_manifest_paths(payload_files, removed_files)
    except ValueError as exc:
        print(f"[Updater] Небезопасный манифест отклонён: {exc}")
        _clear_dir(STAGING_DIR)
        return False

    if sha256_map:
        failed = _verify_staged_files(payload_files, sha256_map)
        if failed:
            print(f"[Updater] Обновление отменено — не прошли проверку: {failed}")
            _clear_dir(STAGING_DIR)
            return False

    if progress_callback:
        progress_callback(3, 3)

    if _is_cancelled(cancelled_flag):
        return _cancel_cleanup()

    # Prefer the authenticated Release-asset manifest (has archive_* fields).
    # Fall back to the copy embedded in the zip, then to a bare version string.
    if remote_info is None:
        try:
            remote_info = get_remote_version_info()
        except Exception:
            staged_manifest = os.path.join(STAGING_DIR, "version.json")
            if os.path.isfile(staged_manifest):
                try:
                    with open(staged_manifest, "r", encoding="utf-8") as fp:
                        remote_info = json.load(fp)
                except Exception:
                    remote_info = None

    # version.json is written by _apply_from_staging from remote_info; do not
    # also move a staged copy as a regular payload file (would race).
    move_files = [p for p in payload_files if p != "version.json"]
    # But still move version.json.sig if present.
    if os.path.isfile(os.path.join(STAGING_DIR, "version.json.sig")):
        if "version.json.sig" not in move_files:
            move_files.append("version.json.sig")

    return _apply_from_staging(
        move_files,
        removed_files,
        remote_info=remote_info,
    )


def _apply_update_per_file(
    files: list,
    sha256_map: dict,
    removed_files: list,
    progress_callback=None,
    cancelled_flag=None,
    commit_sha: str = None,
    sha_mismatch_retries: int = 3,
    sha_mismatch_delay: float = 4.0,
) -> bool:
    """Legacy per-file update path (raw.githubusercontent.com)."""
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
            ok = _download_to_staging(
                f,
                sha256_map.get(f),
                cancelled_flag=cancelled_flag,
                raw_base=raw_base,
                sha_mismatch_retries=sha_mismatch_retries,
                sha_mismatch_delay=sha_mismatch_delay,
            )
        except InterruptedError:
            return _cancel_cleanup()
        if not ok:
            failed.append(f)
        if progress_callback:
            progress_callback(i + 1, total)

    if failed and not _is_cancelled(cancelled_flag):
        print(f"[Updater] Повторная попытка для {len(failed)} файлов после паузы...")
        # Пауза перед повторным проходом масштабируется от sha_mismatch_delay,
        # чтобы тесты (sha_mismatch_delay=0) не ждали реального времени.
        if sha_mismatch_delay:
            time.sleep(2.0)
        still_failed = []
        for f in failed:
            if _is_cancelled(cancelled_flag):
                break
            try:
                ok = _download_to_staging(
                    f,
                    sha256_map.get(f),
                    cancelled_flag=cancelled_flag,
                    raw_base=raw_base,
                    sha_mismatch_retries=sha_mismatch_retries,
                    sha_mismatch_delay=sha_mismatch_delay,
                )
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

    return _apply_from_staging(files, removed_files, commit_sha=commit_sha)


def apply_update(
    files: list,
    sha256_map: dict = None,
    removed_files: list = None,
    progress_callback=None,
    cancelled_flag=None,
    commit_sha: str = None,
    sha_mismatch_retries: int = 3,
    sha_mismatch_delay: float = 4.0,
    archive_sha256: str = None,
    archive_url: str = None,
    remote_info: dict = None,
) -> bool:
    """
    Безопасный цикл обновления.

    Archive mode (preferred, when archive_sha256 is provided):
      1. download one zip into staging
      2. verify archive SHA-256
      3. extract with zip-slip protection
      4. optionally verify per-file SHA-256 from the manifest
      5. backup → move staged → delete removed → save version.json → marker

    Legacy per-file mode (fallback when archive_sha256 is absent):
      download each file from raw.githubusercontent.com (commit-pinned when
      commit_sha is known), verify SHA-256, then the same apply path.

    cancelled_flag — тот же формат, что и в engine/local_llm_client.py
    (dict с ключом "cancelled" или list/tuple с элементом [0]). Проверяется
    во время скачивания/проверки. Точка невозврата — backup+подмена.
    """
    sha256_map = sha256_map or {}
    removed_files = removed_files or []
    try:
        files, removed_files = _validate_manifest_paths(files or [], removed_files)
    except ValueError as exc:
        print(f"[Updater] Небезопасный манифест отклонён: {exc}")
        return False

    if archive_sha256:
        return _apply_update_from_archive(
            files=files,
            sha256_map=sha256_map,
            removed_files=removed_files,
            archive_sha256=archive_sha256,
            archive_url=archive_url,
            progress_callback=progress_callback,
            cancelled_flag=cancelled_flag,
            remote_info=remote_info,
        )

    return _apply_update_per_file(
        files=files,
        sha256_map=sha256_map,
        removed_files=removed_files,
        progress_callback=progress_callback,
        cancelled_flag=cancelled_flag,
        commit_sha=commit_sha,
        sha_mismatch_retries=sha_mismatch_retries,
        sha_mismatch_delay=sha_mismatch_delay,
    )


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
        files, removed_files = _validate_manifest_paths(
            marker.get("files", []), marker.get("removed_files", [])
        )
        for rel in files + removed_files:
            backup_src = _safe_path_under(BACKUP_DIR, rel)
            if os.path.exists(backup_src):
                live = _safe_path_under(BASE_DIR, rel)
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
