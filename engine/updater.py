import os
import sys
import json
import shutil
import threading
import urllib.request
from pathlib import Path

REPO = "DreamSketcher/XTTS-Studio-portable-"
BRANCH = "main"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
VERSION_URL = f"{RAW_BASE}/version.json"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_VERSION_PATH = os.path.join(BASE_DIR, "version.json")


def get_local_version() -> str:
    try:
        with open(LOCAL_VERSION_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def get_remote_version_info() -> dict:
    try:
        with urllib.request.urlopen(VERSION_URL, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Не удалось получить информацию об обновлении: {e}")


def download_file(relative_path: str) -> bool:
    url = f"{RAW_BASE}/{relative_path}"
    dst = os.path.join(BASE_DIR, relative_path.replace("/", os.sep))
    tmp = dst + ".tmp"
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        urllib.request.urlretrieve(url, tmp)
        if os.path.exists(dst):
            os.remove(dst)
        shutil.move(tmp, dst)
        return True
    except Exception as e:
        print(f"[Updater] Ошибка загрузки {relative_path}: {e}")
        try:
            os.remove(tmp)
        except Exception:
            pass
        return False


def check_update() -> dict:
    """
    Возвращает:
      { "available": True/False, "local": "1.0.0", "remote": "1.0.1",
        "files": [...], "changelog": "..." }
    """
    local = get_local_version()
    try:
        info = get_remote_version_info()
        remote = info.get("version", "0.0.0")
        available = _version_gt(remote, local)
        return {
            "available": available,
            "local": local,
            "remote": remote,
            "files": info.get("files", []),
            "changelog": info.get("changelog", ""),
        }
    except Exception as e:
        return {"available": False, "local": local, "remote": None, "error": str(e)}


def apply_update(files: list, progress_callback=None) -> bool:
    """
    Скачивает файлы из списка.
    progress_callback(current, total) — опциональный колбэк прогресса.
    """
    total = len(files)
    failed = []
    for i, f in enumerate(files):
        ok = download_file(f)
        if not ok:
            failed.append(f)
        if progress_callback:
            progress_callback(i + 1, total)

    # обновляем локальный version.json
    try:
        info = get_remote_version_info()
        with open(LOCAL_VERSION_PATH, "w", encoding="utf-8") as fp:
            json.dump(info, fp, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Updater] Не удалось сохранить version.json: {e}")

    if failed:
        print(f"[Updater] Не удалось обновить: {failed}")
        return False
    return True


def restart():
    python = sys.executable
    os.execv(python, [python] + sys.argv)


def _version_gt(a: str, b: str) -> bool:
    """Возвращает True если версия a новее b."""
    def parse(v):
        try:
            return tuple(int(x) for x in v.strip().split("."))
        except Exception:
            return (0, 0, 0)
    return parse(a) > parse(b)