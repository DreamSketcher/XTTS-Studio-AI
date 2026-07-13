# -*- coding: utf-8 -*-
"""
engine/env_core/diagnostics.py — диагностика, сканирование мусора, карантин и автовосстановление пакетов с кэшированием результатов.
"""
import os
import sys
import json
import re
import subprocess
import shutil
import threading
import time
import tempfile
from typing import Optional

from engine.logging_utils import write_log

# Вычисляем корень проекта динамически
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_CORE_DIR))

PYTHON_EXE = sys.executable
SITE_PACKAGES = os.path.join(PROJECT_ROOT, "python", "xtts_env", "Lib", "site-packages")
PORTABLE_TEMP_DIR = os.path.join(PROJECT_ROOT, "python", "temp")
PORTABLE_CACHE_DIR = os.path.join(PROJECT_ROOT, "python", "pip_cache")
QUARANTINE_DIR = os.path.join(PROJECT_ROOT, "python", "xtts_env", "Quarantine")
SAFE_FILES_CACHE_PATH = os.path.join(PROJECT_ROOT, ".known_safe_files.json")
DIAG_CACHE_PATH = os.path.join(PROJECT_ROOT, ".env_diagnostics_cache.json")

# ── Классификация компонентов диагностики ──
# КРИТИЧНЫЕ: без них невозможен вывод аудио TTS или запуск GUI как такового.
# Именно ЭТИ компоненты имеет смысл считать "неисправными" в смысле,
# требующем аварийного восстановления/предупреждения пользователя.
CRITICAL_COMPONENTS = {
    "numpy",
    "torch",
    "torchaudio",
    "torchvision",
    "tts",
    "soundfile",
    "pygame",
    "customtkinter",
    "num2words",
}
# ОПЦИОНАЛЬНЫЕ: дополнительные фичи (локальный LLM-чат, конвертация голоса).
# Их отсутствие — это НОРМАЛЬНОЕ состояние по умолчанию (пользователь просто
# ещё не устанавливал их), а не поломка. Не должны помечаться как
# "неисправный компонент" только потому что не установлены.
OPTIONAL_COMPONENTS = {"llama_cpp", "rvc_python"}


def get_broken_critical(results: dict) -> list:
    """
    Возвращает список ДЕЙСТВИТЕЛЬНО неисправных критичных компонентов из
    результата run_full_diagnostics(): исключает опциональные модули
    (llama_cpp, rvc_python) и компоненты со статусом SKIPPED (ожидают
    починки numpy, а не сломаны сами по себе).
    Использовать вместо ручного дублирования критериев "что считать
    сломанным" в разных окнах GUI.
    """
    return [
        k
        for k, v in results.items()
        if k in CRITICAL_COMPONENTS
        and v is not True
        and not (isinstance(v, str) and v.startswith("SKIPPED"))
    ]


def get_optional_status(results: dict) -> dict:
    """
    Возвращает статус опциональных компонентов (llama_cpp, rvc_python) в
    удобном для отображения виде — три состояния вместо True/False/строка:
    "ok" — работает; "not_installed" — не установлен (нормальное состояние
    по умолчанию, НЕ ошибка); "broken" — установлен, но не импортируется
    (вот это уже стоит показывать как реальную проблему).
    """
    status = {}
    for name in OPTIONAL_COMPONENTS:
        v = results.get(name)
        if v is True:
            status[name] = "ok"
        elif isinstance(v, str) and ("No module named" in v or "ModuleNotFoundError" in v):
            status[name] = "not_installed"
        else:
            status[name] = "broken"
    return status


def clear_diagnostics_cache():
    """Принудительно удаляет файл кэша диагностики для форсирования перепроверки."""
    if os.path.exists(DIAG_CACHE_PATH):
        try:
            os.remove(DIAG_CACHE_PATH)
            write_log("[Diagnostics] Кэш диагностики успешно очищен.")
            return True
        except Exception as e:
            write_log(f"[Diagnostics] Не удалось удалить кэш: {e}")
    return False


def clean_pip_download_cache() -> bool:
    """
    Полностью очищает скачанный pip-кэш и временные файлы сборки
    (python/pip_cache и python/temp).

    Это ОБЩИЙ кэш для ВСЕХ install_* функций окружения — torch_setup.py,
    rvc_setup.py, llama_setup.py и любых будущих модулей установки —
    все они используют одни и те же PORTABLE_CACHE_DIR/PORTABLE_TEMP_DIR.
    Поэтому очистка живёт здесь, в модуле диагностики/очистки, а не в
    отдельных модулях установки библиотек: так есть одно место, которое
    подчищает мусор, накопленный от ЛЮБОЙ из установок, а не только от
    той, что вызывалась последней.
    """
    cleaned = False
    for path in (PORTABLE_TEMP_DIR, PORTABLE_CACHE_DIR):
        if os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
                cleaned = True
                write_log(f"[Diagnostics] Очищен путь: {path}")
            except Exception as e:
                write_log(f"[Diagnostics] Ошибка при очистке {path}: {e}")
    return cleaned


def parse_requirements_txt() -> dict:
    """
    Парсит requirements.txt в корне проекта для определения
    точных зафиксированных версий пакетов в портативном окружении.
    """
    req_path = os.path.join(PROJECT_ROOT, "requirements.txt")
    reqs = {}
    if os.path.exists(req_path):
        try:
            with open(req_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith("-"):
                        continue
                    # Вычленяем имя пакета до знаков сравнения (==, >=, <=)
                    match = re.match(r"^([A-Za-z0-9_\-]+)", line)
                    if match:
                        name = match.group(1).lower()
                        reqs[name] = line
        except Exception as e:
            write_log(f"[Diagnostics] Ошибка парсинга requirements.txt: {e}")
    return reqs


def get_python_env_info() -> dict:
    from engine.env_core.llama_setup import get_site_packages

    info = {
        "executable": PYTHON_EXE,
        "version": sys.version.replace("\n", " "),
        "site_packages": get_site_packages(),
        "target": SITE_PACKAGES,
        "pip_version": None,
        "pip_show": None,
        "import_probe": None,
    }

    try:
        out = subprocess.run(
            [PYTHON_EXE, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0:
            info["pip_version"] = out.stdout.strip()
    except Exception as e:
        info["pip_version"] = f"ошибка: {e}"

    try:
        out = subprocess.run(
            [PYTHON_EXE, "-m", "pip", "show", "llama-cpp-python"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0:
            info["pip_show"] = out.stdout.strip()
        else:
            detail = out.stderr.strip() or ("код " + str(out.returncode))
            info["pip_show"] = f"не установлен ({detail})"
    except Exception as e:
        info["pip_show"] = f"ошибка: {e}"

    probe_script = """import sys
try:
    import llama_cpp
    print('OK=' + llama_cpp.__file__)
except ImportError as e:
    print('FAIL=' + str(e))
print('SYS_PATH=' + repr(sys.path))
"""
    try:
        out = subprocess.run(
            [PYTHON_EXE, "-c", probe_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        info["import_probe"] = (
            out.stdout.strip() + ("\nSTDERR: " + out.stderr.strip() if out.stderr.strip() else "")
        ).strip()
    except Exception as e:
        info["import_probe"] = f"ошибка: {e}"

    return info


def format_env_info(info: dict) -> str:
    lines = [
        "Диагностика окружения:",
        f"  Python: {info['executable']}",
        f"  Версия: {info['version']}",
        f"  Целевая папка (--target): {info['target']}",
        "  Site-packages:",
    ]
    for p in info["site_packages"]:
        lines.append(f"    - {p}")
    lines.append(f"  pip: {info['pip_version'] or 'не определён'}")
    lines.append("  pip show llama-cpp-python:")
    for line in (info["pip_show"] or "—").splitlines():
        lines.append(f"    {line}")
    lines.append("  Проверка импорта llama_cpp:")
    for line in (info["import_probe"] or "—").splitlines():
        lines.append(f"    {line}")
    return "\n".join(lines)


def _read_pip_output(proc: subprocess.Popen, progress_cb=None):
    def _build_prefix(line: str) -> str:
        prefixes = [
            "Building wheels for collected packages",
            "Building wheel for",
            "Running setup.py",
        ]
        for p in prefixes:
            if line.startswith(p):
                return p
        return ""

    def _is_progress_status(line: str) -> bool:
        return "still running" in line or "Running setup.py" in line

    last_prefix = [""]

    def emit(line):
        if not line:
            return
        write_log(line)
        if not progress_cb:
            return
        prefix = _build_prefix(line)
        if prefix and prefix == last_prefix[0]:
            progress_cb("\r" + line)
        elif _is_progress_status(line):
            progress_cb("\r" + line)
        else:
            progress_cb(line)
            last_prefix[0] = prefix

    buf = ""
    try:
        while True:
            byte = proc.stdout.read(1)
            if not byte:
                if buf:
                    emit(buf.rstrip())
                break
            char = byte.decode("utf-8", errors="replace")
            if char == "\r":
                emit("\r" + buf)
                buf = ""
            elif char == "\n":
                emit(buf.rstrip())
                buf = ""
            else:
                buf += char
    except Exception as e:
        if buf:
            emit(buf.rstrip())
        emit(f"[ошибка чтения вывода: {e}]")


def _install_watchdog(
    stop_event: threading.Event, progress_cb, interval: float = 20.0, stall_threshold: float = 90.0
):
    def emit(line):
        if progress_cb:
            progress_cb(line)

    while not stop_event.wait(interval):
        info = get_install_activity_status()
        ago = info["last_activity_seconds_ago"]
        if ago is None:
            emit(
                "🔧 Сборка идёт (файлы сборки ещё не появились на диске — это нормально на старте)..."
            )
        elif ago < stall_threshold:
            emit(f"🔧 Сборка идёт — файлы менялись {int(ago)} сек назад, процесс жив.")
        else:
            emit(f"⚠️ Файлы не менялись уже {int(ago)} сек — процесс, возможно, завис.")


_MISSING_MODULE_RE = re.compile(r"No module named ['\"]([\w.]+)['\"]")
_MODULE_TO_PACKAGE = {
    "yaml": "PyYAML",
    "PIL": "Pillow",
    "cv2": "opencv-python",
}


def _extract_missing_module(error_text: str) -> Optional[str]:
    if not error_text:
        return None
    match = _MISSING_MODULE_RE.search(error_text)
    if not match:
        return None
    module = match.group(1).split(".")[0]
    return _MODULE_TO_PACKAGE.get(module, module)


def _install_single_dependency(package: str, progress_cb=None) -> bool:
    def emit(line):
        if progress_cb:
            progress_cb(line)

    emit(f"Ставлю недостающую зависимость: {package}...")
    try:
        proc = subprocess.run(
            [
                PYTHON_EXE,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                SITE_PACKAGES,
                "--no-cache-dir",
                package,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception as e:
        emit(f"⚠️ Не удалось установить {package}: {e}")
        return False
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-500:]
        emit(f"⚠️ Не удалось установить {package}: {detail}")
        return False
    return True


def _find_pip_build_activity(max_scan_seconds: float = 0.5) -> Optional[float]:
    tmp_root = PORTABLE_TEMP_DIR if os.path.exists(PORTABLE_TEMP_DIR) else tempfile.gettempdir()
    start = time.monotonic()
    newest = None
    try:
        for entry in os.scandir(tmp_root):
            if time.monotonic() - start > max_scan_seconds:
                break
            if not entry.is_dir(follow_symlinks=False):
                continue
            name = entry.name.lower()
            if not (
                name.startswith("pip-install-")
                or name.startswith("pip-req-build-")
                or name.startswith("pip-build-env-")
            ):
                continue
            for root, _dirs, files in os.walk(entry.path):
                for fname in files:
                    try:
                        mtime = os.path.getmtime(os.path.join(root, fname))
                        if newest is None or mtime > newest:
                            newest = mtime
                    except Exception:
                        continue
                    if time.monotonic() - start > max_scan_seconds:
                        return newest
    except Exception:
        pass
    return newest


def get_install_activity_status() -> dict:
    now = time.time()
    result = {"last_activity_seconds_ago": None, "target_dir_files": 0}

    build_mtime = _find_pip_build_activity()
    if build_mtime is not None:
        result["last_activity_seconds_ago"] = max(0.0, now - build_mtime)

    target = os.path.join(SITE_PACKAGES, "llama_cpp")
    if os.path.isdir(target):
        newest = None
        count = 0
        try:
            for root, _dirs, files in os.walk(target):
                for fname in files:
                    count += 1
                    try:
                        mtime = os.path.getmtime(os.path.join(root, fname))
                        if newest is None or mtime > newest:
                            newest = mtime
                    except Exception:
                        continue
        except Exception:
            pass
        result["target_dir_files"] = count
        if newest is not None:
            ago = max(0.0, now - newest)
            if (
                result["last_activity_seconds_ago"] is None
                or ago < result["last_activity_seconds_ago"]
            ):
                result["last_activity_seconds_ago"] = ago

    return result


def _clean_dataclasses_backport():
    """
    Удаляет бэкпорт `dataclasses` из site-packages, если он случайно попал
    туда (обычно как транзитивная зависимость fairseq/sacrebleu при установке
    RVC). На Python >=3.7 dataclasses уже входит в stdlib, а бэкпорт ТЕНЕВЫМ
    образом перекрывает стандартный модуль и ломает сам pip
    (AttributeError: module 'typing' has no attribute '_ClassVar') и импорт
    torch/torchvision и т.п. Удаление с диска гарантирует, что новые процессы
    (в т.ч. подпроцессы pip и следующий запуск приложения) импортируют
    стандартный dataclasses, а не теневой бэкпорт.

    Без этой очистки восстановление torch/torchvision могло бы «чинить»
    пакет, но импорт всё равно падал бы на следующем запуске (и в подпроцессах
    pip) из-за теневого перекрытия — отсюда и возникал эффект «ошибка
    появляется каждый раз перед запуском».
    """
    removed = []
    try:
        if not os.path.isdir(SITE_PACKAGES):
            return removed
        for name in os.listdir(SITE_PACKAGES):
            low = name.lower()
            # Сам модуль/пакет (dataclasses.py либо папка dataclasses) либо
            # его dist-info/egg-info (dataclasses-0.8.dist-info и т.п.).
            if low in ("dataclasses", "dataclasses.py") or low.startswith("dataclasses-"):
                full = os.path.join(SITE_PACKAGES, name)
                try:
                    if os.path.isdir(full):
                        shutil.rmtree(full, ignore_errors=True)
                    elif os.path.isfile(full):
                        os.remove(full)
                    removed.append(name)
                except Exception:
                    pass
    except Exception:
        pass
    if removed:
        write_log(f"[Diagnostics] Удалён теневой бэкпорт dataclasses из site-packages: {removed}")
    return removed


def run_full_diagnostics(force_refresh=False) -> dict:
    """
    Выполняет полную проверку работоспособности всех 11 ключевых компонентов.
    Использует гибридное интеллектуальное кэширование.

    ВСЕ проверки (включая numpy/torch/torchaudio/torchvision/tts/soundfile/
    pygame/customtkinter/num2words) идут в ОДНОМ изолированном сабпроцессе —
    ни один импорт не происходит в текущем процессе приложения.

    Раньше "лёгкие" библиотеки импортировались прямо здесь, в текущем
    процессе (обходя Windows DLL Loader/_pth ограничения портативного
    питона) — но Python не выгружает модули из памяти, поэтому один раз
    импортированный torchvision (или torch/tts/...) оставался залоченным
    (.pyd/.dll) до самого закрытия приложения. Это ломало run_error_recovery
    изнутри: сама проверка "надо ли чинить X?" залочивала файл, который
    затем pip не мог переустановить (PermissionError/WinError 5 на
    shutil.rmtree внутри _handle_target_dir). Полная изоляция в сабпроцессе
    убирает эту проблему в принципе — диагностика больше никогда не держит
    лок в процессе приложения.
    """
    # ── 0. Самолечение: убираем теневой бэкпорт dataclasses, который
    # теневым образом перекрывает stdlib и ломает импорт torch/torchvision
    # и сами подпроцессы pip. Очистка с диска гарантирует, что свежие
    # процессы (включая подпроцесс диагностики и следующий запуск)
    # используют стандартный dataclasses. ──
    _clean_dataclasses_backport()

    # ── 1. Проверяем и валидируем кэш ──
    if not force_refresh:
        try:
            if os.path.exists(DIAG_CACHE_PATH):
                with open(DIAG_CACHE_PATH, "r", encoding="utf-8") as f:
                    cache = json.load(f)

                current_mtime = (
                    os.path.getmtime(SITE_PACKAGES) if os.path.exists(SITE_PACKAGES) else 0.0
                )
                current_count = (
                    len(os.listdir(SITE_PACKAGES)) if os.path.exists(SITE_PACKAGES) else 0
                )

                if (
                    cache.get("python_exe") == PYTHON_EXE
                    and cache.get("site_packages_mtime") == current_mtime
                    and cache.get("site_packages_count") == current_count
                    and "results" in cache
                ):
                    return cache["results"]
        except Exception as e:
            write_log(f"[Diagnostics] Ошибка проверки кэша диагностики: {e}")

    write_log("[Diagnostics] Запуск полного сканирования библиотек в изолированном процессе...")
    clean_site_packages = SITE_PACKAGES.replace("\\", "/")

    probe_script = (
        """import sys, json
sys.path.insert(0, r'%s')
results = {}
_SKIP_MSG = "SKIPPED: ожидает починки numpy (зависит от него на импорте)"

# 1. numpy
try:
    import numpy as np
    a = np.array([1, 2, 3])
    results['numpy'] = bool(a.sum() == 6)
except Exception as e:
    results['numpy'] = str(e)

numpy_ok = results['numpy'] is True

# 2. torch
if not numpy_ok:
    results['torch'] = _SKIP_MSG
else:
    try:
        import torch
        x = torch.tensor([1.0, 2.0])
        results['torch'] = (x.sum().item() == 3.0)
    except Exception as e:
        results['torch'] = str(e)

# 3. torchaudio
if not numpy_ok:
    results['torchaudio'] = _SKIP_MSG
else:
    try:
        import torchaudio
        results['torchaudio'] = True
    except Exception as e:
        results['torchaudio'] = str(e)

# 4. torchvision
if not numpy_ok:
    results['torchvision'] = _SKIP_MSG
else:
    try:
        import torchvision
        results['torchvision'] = True
    except Exception as e:
        results['torchvision'] = str(e)

# 5. tts
if not numpy_ok:
    results['tts'] = _SKIP_MSG
else:
    try:
        from TTS.api import TTS
        results['tts'] = True
    except Exception as e:
        results['tts'] = str(e)

# 6. soundfile
try:
    import soundfile as sf
    results['soundfile'] = True
except Exception as e:
    results['soundfile'] = str(e)

# 7. pygame
try:
    import pygame
    results['pygame'] = True
except Exception as e:
    results['pygame'] = str(e)

# 8. customtkinter
try:
    import customtkinter
    results['customtkinter'] = True
except Exception as e:
    results['customtkinter'] = str(e)

# 9. num2words
try:
    from num2words import num2words
    results['num2words'] = (num2words(123, lang='ru') != '')
except Exception as e:
    results['num2words'] = str(e)

# 10. llama_cpp
try:
    import llama_cpp
    results['llama_cpp'] = True
except Exception as e:
    results['llama_cpp'] = str(e)

# 11. rvc_python
try:
    from rvc_python.infer import RVCInference
    results['rvc_python'] = True
except Exception as e:
    results['rvc_python'] = str(e)

print("SUB_RESULT=" + json.dumps(results))
"""
        % clean_site_packages
    )

    _ALL_KEYS = (
        "numpy",
        "torch",
        "torchaudio",
        "torchvision",
        "tts",
        "soundfile",
        "pygame",
        "customtkinter",
        "num2words",
        "llama_cpp",
        "rvc_python",
    )
    results = {}
    try:
        env = os.environ.copy()
        # Таймаут увеличен относительно прежнего (30с хватало только на
        # лёгкие llama_cpp/rvc_python) — здесь же в холодном сабпроцессе
        # с нуля импортируются torch/TTS, это заметно дольше.
        proc = subprocess.run(
            [PYTHON_EXE, "-c", probe_script], capture_output=True, text=True, timeout=90, env=env
        )
        out = proc.stdout or ""
        found = False
        for line in out.splitlines():
            if line.startswith("SUB_RESULT="):
                results = json.loads(line.split("=", 1)[1])
                found = True
                break

        if not found:
            err_text = f"Subprocess failed: {proc.stderr or out}"
            for k in _ALL_KEYS:
                results[k] = err_text
    except Exception as e:
        err_text = str(e)
        for k in _ALL_KEYS:
            results[k] = err_text

    is_all_ok = results and all(v is True for v in results.values())

    if is_all_ok:
        try:
            current_mtime = (
                os.path.getmtime(SITE_PACKAGES) if os.path.exists(SITE_PACKAGES) else 0.0
            )
            current_count = len(os.listdir(SITE_PACKAGES)) if os.path.exists(SITE_PACKAGES) else 0

            cache_data = {
                "python_exe": PYTHON_EXE,
                "site_packages_mtime": current_mtime,
                "site_packages_count": current_count,
                "timestamp": time.time(),
                "results": results,
            }
            with open(DIAG_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            write_log("[Diagnostics] Результаты диагностики успешно закэшированы.")
        except Exception as e:
            write_log(f"[Diagnostics] Ошибка записи кэша диагностики: {e}")
    else:
        clear_diagnostics_cache()

    return results


def load_safe_files_cache() -> dict:
    """
    Безопасно загружает кэш истории удалений и файлов, гарантируя наличие
    всех необходимых полей, включая deleted_files (поддержка старых кэшей).
    """
    cache = {"safe_files": {}, "unsafe_files": {}, "deleted_files": []}
    if os.path.exists(SAFE_FILES_CACHE_PATH):
        try:
            with open(SAFE_FILES_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    cache.update(data)
                    # Гарантируем, что deleted_files является валидным списком!
                    if "deleted_files" not in cache or not isinstance(cache["deleted_files"], list):
                        cache["deleted_files"] = []
        except Exception:
            pass
    return cache


def save_safe_files_cache(data: dict):
    try:
        with open(SAFE_FILES_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        write_log(f"[Cache Manager] Ошибка сохранения кэша безопасных файлов: {e}")


def scan_for_garbage(mode="fast", progress_cb=None) -> dict:
    def emit(line):
        if progress_cb:
            progress_cb(line)

    cache = load_safe_files_cache()
    os.makedirs(QUARANTINE_DIR, exist_ok=True)

    EXCLUDED_FILENAMES = {
        "checksums.txt",
        "requirements.txt",
        "settings.json",
        "theme_settings.json",
        "version.json",
        "chat_history.json",
        "word_rules.json",
        "gpt_settings.json",
        "env_cache.cfg",
        ".known_safe_files.json",
        ".torch_install_checkpoint.json",
    }

    ZERO_BYTE_SAFE_EXT = {".whl", ".tmp", ".log", ".bak", ".part", ".crdownload", ".old"}

    emit("Выполняю предварительную диагностику до перемещения файлов...")
    baseline_res = run_full_diagnostics(force_refresh=True)
    if "error" in baseline_res:
        write_log(f"[Garbage Scan] Ошибка предварительной диагностики: {baseline_res['error']}")
        baseline_failed = set()
    else:
        baseline_failed = {k for k, v in baseline_res.items() if v is not True}

    all_files = []

    emit("🔍 Начинаю сканирование временных папок...")
    paths_to_scan_directly = [PORTABLE_TEMP_DIR, os.path.join(PROJECT_ROOT, "logs")]
    if os.path.exists(PORTABLE_CACHE_DIR):
        paths_to_scan_directly.append(PORTABLE_CACHE_DIR)

    for base_path in paths_to_scan_directly:
        folder_name = os.path.basename(base_path)
        emit(f"Сканирую папку: {folder_name} ...")
        if not os.path.exists(base_path):
            emit(f"   [Папка {folder_name} отсутствует или уже пуста]")
            continue
        for root_dir, dirs, files in os.walk(base_path):
            for file in files:
                if file in EXCLUDED_FILENAMES:
                    continue
                abs_path = os.path.join(root_dir, file)
                rel_path = os.path.relpath(abs_path, PROJECT_ROOT).replace("\\", "/")
                if "python/xtts_env/Quarantine" in rel_path:
                    continue
                try:
                    stat = os.stat(abs_path)
                    all_files.append(
                        {
                            "rel_path": rel_path,
                            "abs_path": abs_path,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                        }
                    )
                except Exception:
                    pass

    emit(
        f"🔍 Сканирую всю директорию {PROJECT_ROOT} на наличие кэша, временных и мусорных файлов..."
    )
    excluded_dirs = {"models", "outputs", "library", "reference", ".git", "Quarantine"}

    for root_dir, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in excluded_dirs and d != "Quarantine"]

        if os.path.basename(root_dir) in ("__pycache__", ".pytest_cache"):
            for file in files:
                if file in EXCLUDED_FILENAMES:
                    continue
                abs_path = os.path.join(root_dir, file)
                rel_path = os.path.relpath(abs_path, PROJECT_ROOT).replace("\\", "/")
                try:
                    stat = os.stat(abs_path)
                    all_files.append(
                        {
                            "rel_path": rel_path,
                            "abs_path": abs_path,
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                        }
                    )
                except Exception:
                    pass
            continue

        for file in files:
            if file in EXCLUDED_FILENAMES:
                continue
            abs_path = os.path.join(root_dir, file)
            rel_path = os.path.relpath(abs_path, PROJECT_ROOT).replace("\\", "/")
            ext = os.path.splitext(file)[1].lower()

            try:
                stat = os.stat(abs_path)
                size = stat.st_size
                mtime = stat.st_mtime
                is_zero_byte = size == 0
            except Exception:
                continue

            is_garbage = False

            if is_zero_byte:
                if ext in ZERO_BYTE_SAFE_EXT:
                    is_garbage = True
                else:
                    emit(
                        f"   [!] Внимание: Обнаружен 0-байтовый системный файл (не трогаем): {rel_path}"
                    )
                    continue
            else:
                if ext in (".bak", ".log"):
                    # .bak/.log вне temp/cache/логов — это, как правило, пользовательские
                    # бэкапы (например word_rules_backups), а не мусор. Настоящие временные
                    # логи и кэш уже покрываются отдельным сканированием paths_to_scan_directly выше,
                    # поэтому здесь трогаем такие файлы только если они физически лежат
                    # в одной из известных temp/cache/pycache-папок.
                    rel_parts_lower = rel_path.lower().split("/")
                    in_temp_or_cache = any(
                        p in ("temp", "logs", "pip_cache", "__pycache__", ".pytest_cache")
                        for p in rel_parts_lower
                    )
                    if not in_temp_or_cache:
                        continue
                    is_garbage = True
                elif ext in (".tmp", ".pyc", ".pyo") or file.endswith("~") or file.startswith("~$"):
                    # Питон в python/ — обычная установка (скопирована из AppData), а не
                    # embeddable-сборка без .py-исходников, поэтому .pyc/.pyo — это просто
                    # регенерируемый байткод-кэш, безопасный для удаления где угодно в дереве.
                    is_garbage = True

            if is_garbage:
                all_files.append(
                    {"rel_path": rel_path, "abs_path": abs_path, "size": size, "mtime": mtime}
                )

    safe_all_files = []
    for f in all_files:
        if f["rel_path"] in cache.get("unsafe_files", {}):
            continue
        safe_all_files.append(f)

    emit(f"Всего обнаружено кэша и временных файлов в проекте: {len(safe_all_files)}")

    quarantined_files = []
    total_size = 0
    to_quarantine = []
    skipped_new = []

    if mode == "fast":
        emit("Выполняю быстрое сканирование (сверяю с кэшем безопасности)...")
        for f in safe_all_files:
            rel = f["rel_path"]
            cached = cache.get("safe_files", {}).get(rel)
            if (
                cached
                and cached.get("size") == f["size"]
                and abs(cached.get("mtime", 0) - f["mtime"]) < 1.0
            ):
                to_quarantine.append(f)
            else:
                skipped_new.append(f)
        emit(
            f"Быстрое сканирование завершено. Будет перемещено в карантин: {len(to_quarantine)}. Пропущено новых файлов: {len(skipped_new)}"
        )
    else:
        emit("Выполняю глубокое сканирование (полная проверка всех файлов)...")
        to_quarantine = safe_all_files.copy()

    if not to_quarantine:
        return {
            "quarantined_count": 0,
            "size_mb": 0.0,
            "restored_count": 0,
            "restored_list": [],
            "mode": mode,
            "quarantined_list": [],
        }

    for f in to_quarantine:
        if not os.path.exists(f["abs_path"]):
            continue
        q_path = os.path.join(QUARANTINE_DIR, f["rel_path"])
        os.makedirs(os.path.dirname(q_path), exist_ok=True)
        try:
            shutil.move(f["abs_path"], q_path)
            f["quarantine_path"] = q_path
            quarantined_files.append(f)
            total_size += f["size"]
        except Exception as e:
            write_log(f"[Garbage Scan] Ошибка перемещения {f['rel_path']}: {e}")

    emit("Выполняю диагностику работоспособности компонентов после изоляции...")
    diag_res = run_full_diagnostics(force_refresh=True)  # Форсируем обход кэша

    if "error" in diag_res:
        new_failed = {"diagnostic_script_crash"}
    else:
        post_failed = {k for k, v in diag_res.items() if v is not True}
        new_failed = post_failed - baseline_failed

    restored = []
    if new_failed:
        emit(
            f"⚠️ Сбой диагностики компонентов из-за перемещенных файлов: {', '.join(new_failed)}. Запускаю автоматический возврат..."
        )
        for f in quarantined_files:
            try:
                os.makedirs(os.path.dirname(f["abs_path"]), exist_ok=True)
                shutil.move(f["quarantine_path"], f["abs_path"])
                restored.append(f["rel_path"])
                cache["unsafe_files"][f["rel_path"]] = {"size": f["size"], "mtime": f["mtime"]}
            except Exception as e:
                write_log(f"[Garbage Scan] Ошибка возврата {f['rel_path']}: {e}")
        quarantined_files.clear()
        total_size = 0
        emit("Все файлы были автоматически возвращены из карантина в целях безопасности.")
    else:
        for f in quarantined_files:
            if "safe_files" not in cache:
                cache["safe_files"] = {}
            cache["safe_files"][f["rel_path"]] = {
                "size": f["size"],
                "mtime": f["mtime"],
                "safe": True,
            }
        emit("Диагностика успешна! Все изолированные файлы подтверждены как безопасные.")

    save_safe_files_cache(cache)
    size_mb = total_size / (1024 * 1024)

    return {
        "quarantined_count": len(quarantined_files),
        "size_mb": size_mb,
        "restored_count": len(restored),
        "restored_list": restored,
        "mode": mode,
        "quarantined_list": quarantined_files,
    }


def finalize_deletion(quarantined_list: list) -> int:
    cache = load_safe_files_cache()
    deleted_count = 0
    now = time.time()

    for f in quarantined_list:
        q_path = f.get("quarantine_path")
        if q_path and os.path.exists(q_path):
            try:
                if os.path.isdir(q_path):
                    shutil.rmtree(q_path, ignore_errors=True)
                else:
                    os.remove(q_path)
                deleted_count += 1

                package_name = "unknown"
                parts = f["rel_path"].split("/")
                if "site-packages" in parts:
                    idx = parts.index("site-packages")
                    if idx + 1 < len(parts):
                        package_name = parts[idx + 1]

                if "deleted_files" not in cache:
                    cache["deleted_files"] = []
                cache["deleted_files"].append(
                    {
                        "path": f["rel_path"],
                        "size": f["size"],
                        "package": package_name,
                        "timestamp": now,
                    }
                )
            except Exception as e:
                write_log(f"[Garbage Scan] Ошибка удаления {f['rel_path']}: {e}")

    if os.path.exists(QUARANTINE_DIR):
        try:
            shutil.rmtree(QUARANTINE_DIR, ignore_errors=True)
        except Exception:
            pass

    save_safe_files_cache(cache)

    # Сбрасываем кэш диагностики, чтобы форсировать перепроверку при следующем открытии окна
    clear_diagnostics_cache()

    return deleted_count


def _detect_installed_torch_suffix() -> Optional[str]:
    """
    Определяет фактически установленный вариант torch (cu118/cpu) по METADATA
    в site-packages — БЕЗ импорта torch (он может быть сломан при восстановлении).
    Возвращает 'cu118', 'cpu' или None (если torch не установлен / нет METADATA).
    """
    try:
        if not os.path.isdir(SITE_PACKAGES):
            return None
        for name in os.listdir(SITE_PACKAGES):
            low = name.lower()
            if low.startswith("torch-") and low.endswith(".dist-info"):
                meta = os.path.join(SITE_PACKAGES, name, "METADATA")
                if not os.path.isfile(meta):
                    continue
                with open(meta, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.lower().startswith("version:"):
                            ver = line.split(":", 1)[1].strip().lower()
                            if "+cu118" in ver:
                                return "cu118"
                            if "+cpu" in ver:
                                return "cpu"
                            # Нейтральная версия без суффикса — трактуем как
                            # cpu (безопасный вариант по умолчанию).
                            return "cpu"
    except Exception:
        pass
    return None


def _resolve_recovery_torch_variant() -> tuple:
    """
    Возвращает (variant, index_url) для адаптивного восстановления torch:
      1) по фактически установленному torch (METADATA в site-packages);
      2) по последней успешно установленной записи (.torch_installed_variant.json);
      3) фолбэк — предпочтение GPU/настроек (как при обычной установке).
    Так восстановление НЕ тянет 2.7 ГБ cu118, когда в окружении стоит cpu-сборка.
    """
    suffix = _detect_installed_torch_suffix()
    if suffix:
        try:
            from engine.env_core.torch_setup import _TORCH_INDEX_URLS

            return suffix, _TORCH_INDEX_URLS.get(suffix, _TORCH_INDEX_URLS["cpu"])
        except Exception:
            return suffix, "https://download.pytorch.org/whl/" + suffix

    try:
        from engine.env_core import torch_setup

        v = torch_setup.get_installed_torch_variant()
        if v in ("cu118", "cpu"):
            return v, torch_setup._TORCH_INDEX_URLS[v]
    except Exception:
        pass

    try:
        from engine.env_core import torch_setup
        from engine.env_core.cpu_gpu import detect_gpu

        return torch_setup._pick_torch_variant(detect_gpu())
    except Exception:
        pass

    return "cpu", "https://download.pytorch.org/whl/cpu"


def _torch_already_ok(variant: str) -> bool:
    """
    True, если torch уже импортируется и соответствует нужному варианту
    (cpu/cu118). Позволяет пропустить переустановку и не качать torch зря
    (например, когда чиним soundfile, а torch и так работает).
    """
    try:
        from engine.env_core.torch_setup import torch_status

        st = torch_status()
    except Exception:
        return False
    if not st.get("installed"):
        return False
    ver = (st.get("version") or "").lower()
    if variant == "cu118":
        return "+cu118" in ver
    # cpu: подходит и нейтральная, и +cpu версия; cu118 — нет.
    return "+cu118" not in ver


def _get_av_pin() -> str:
    """
    Версия PyAV, совместимая с torchvision 0.17.2 проекта.
    Приоритет: requirements.txt → rvc_setup.AV_PIN → av==12.3.0.
    """
    try:
        frozen = parse_requirements_txt()
        if frozen.get("av"):
            return frozen["av"]
    except Exception:
        pass
    try:
        from engine.env_core.rvc_setup import AV_PIN

        if AV_PIN:
            return AV_PIN
    except Exception:
        pass
    return "av==12.3.0"


def _av_is_compatible() -> bool:
    """
    True, если av импортируется И имеет атрибут logging — ровно то, что
    torchvision 0.17.2 (io/video.py) вызывает на import-time:
        av.logging.set_level(av.logging.ERROR)
    Ловится только ImportError, поэтому AttributeError (нет logging)
    валит весь import torchvision.
    """
    probe = (
        "import sys\n"
        f"sys.path.insert(0, r'{SITE_PACKAGES}')\n"
        "try:\n"
        "    import av\n"
        "    ok = hasattr(av, 'logging') and hasattr(av.logging, 'set_level')\n"
        "    print('AV_COMPAT=' + ('1' if ok else '0'))\n"
        "    print('AV_VER=' + str(getattr(av, '__version__', '?')))\n"
        "except Exception as e:\n"
        "    print('AV_COMPAT=0')\n"
        "    print('AV_ERR=' + str(e))\n"
    )
    try:
        proc = subprocess.run(
            [PYTHON_EXE, "-c", probe],
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = proc.stdout or ""
        return "AV_COMPAT=1" in out
    except Exception:
        return False


def _repair_av_for_torchvision(progress_cb=None) -> bool:
    """
    Переустанавливает совместимый av (AV_PIN) и проверяет av.logging.
    Вызывается:
      - при восстановлении torchvision, если live-ошибка указывает на av;
      - если av сам попал в deleted_files / matched_specs.
    """
    av_pin = _get_av_pin()

    def emit(line):
        if progress_cb:
            try:
                progress_cb(line)
            except Exception:
                pass
        write_log(line)

    if _av_is_compatible():
        emit(f"⏭️ PyAV уже совместим с torchvision ({av_pin}) — не трогаю.")
        return True

    emit(f"🔧 Чиню PyAV ({av_pin}) — torchvision 0.17.2 требует av.logging на import...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    os.makedirs(PORTABLE_TEMP_DIR, exist_ok=True)
    os.makedirs(PORTABLE_CACHE_DIR, exist_ok=True)
    env["TMPDIR"] = PORTABLE_TEMP_DIR
    env["TEMP"] = PORTABLE_TEMP_DIR
    env["TMP"] = PORTABLE_TEMP_DIR
    env["PIP_CACHE_DIR"] = PORTABLE_CACHE_DIR

    cmd = [
        PYTHON_EXE,
        "-m",
        "pip",
        "install",
        av_pin,
        "--target",
        SITE_PACKAGES,
        "--upgrade",
        "--force-reinstall",
        "--no-deps",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,
        )
        output_lines = []
        for line in iter(proc.stdout.readline, ""):
            if line:
                output_lines.append(line)
                emit(line.strip())
        proc.wait()
        output_text = "".join(output_lines)
        if proc.returncode != 0 and (
            "PermissionError" in output_text
            or "WinError 5" in output_text
            or "Access is denied" in output_text
            or "Отказано" in output_text
        ):
            emit(
                "⚠️ pip не смог перезаписать залоченные файлы av. "
                "Повторяю без --force-reinstall/--upgrade..."
            )
            cmd_retry = [c for c in cmd if c not in ("--force-reinstall", "--upgrade")]
            proc = subprocess.Popen(
                cmd_retry,
                cwd=PROJECT_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
            )
            for line in iter(proc.stdout.readline, ""):
                if line:
                    emit(line.strip())
            proc.wait()
    except Exception as e:
        emit(f"❌ Не удалось переустановить {av_pin}: {e}")
        return False

    ok = _av_is_compatible()
    if ok:
        emit(f"✅ PyAV восстановлен и совместим с torchvision ({av_pin}).")
    else:
        emit(
            f"❌ После установки {av_pin} probe av.logging всё ещё не проходит. "
            f"Возможно, файлы залочены — нужен полный перезапуск приложения."
        )
    return ok


def _torchvision_error_is_av_related(err_text) -> bool:
    """
    True, если ошибка импорта torchvision указывает на несовместимый/битый av
    (типично: AttributeError: module 'av' has no attribute 'logging').
    """
    if not isinstance(err_text, str):
        return False
    low = err_text.lower()
    if "module 'av' has no attribute 'logging'" in low:
        return True
    if "av.logging" in low:
        return True
    # Более общий случай: AttributeError/ImportError вокруг av при импорте video.
    if "av" in low and ("logging" in low or "pyav" in low):
        return True
    return False


def run_error_recovery(progress_cb=None) -> list:
    """
    Устранение ошибок: сканирует историю удалений в кэше,
    определяет пострадавшие питоновские пакеты и запускает их переустановку через pip.
    Автоматически сопоставляет версии с requirements.txt для идеальной совместимости!

    Обработка torch — АДАПТИВНАЯ: берётся вариант, уже стоящий в окружении
    (cpu/cu118), и переустановка пропускается, если torch уже работает.
    Это исключает повторную закачку 2.7 ГБ cu118 при восстановлении других
    пакетов (например soundfile), когда фактически установлен cpu-вариант.
    """
    log_path = os.path.join(PROJECT_ROOT, "logs", "recovery_pip_output.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
    except Exception:
        pass

    def emit(line):
        # Всегда пишем в файл ПЕРЕД попыткой обновить UI — если UI упадёт
        # (например Tkinter-окно уже не в mainloop), реальный текст ошибки
        # pip всё равно останется на диске, а не потеряется в трейсбеке.
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(str(line) + "\n")
        except Exception:
            pass
        if progress_cb:
            try:
                progress_cb(line)
            except Exception as ui_err:
                # Сбой обновления интерфейса не должен прерывать восстановление
                # и не должен маскировать реальную ошибку pip.
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"[UI callback error, продолжаю без UI]: {ui_err}\n")
                except Exception:
                    pass

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(
                f"\n===== run_error_recovery запущен: {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
            )
    except Exception:
        pass

    # ── Самолечение: убираем теневой бэкпорт dataclasses ДО любых вызовов
    # pip/torch_status. Иначе подпроцессы pip (и импорт torch/torchvision)
    # продолжают падать из-за теневого перекрытия stdlib, и «исправление»
    # torch/torchvision не держится между запусками (ошибка возвращается
    # каждый раз перед стартом). ──
    cleaned = _clean_dataclasses_backport()
    if cleaned:
        emit(
            f"🧹 Удалён теневой бэкпорт dataclasses (мешал импорту torch/torchvision и pip): {cleaned}"
        )

    cache = load_safe_files_cache()
    deleted = cache.get("deleted_files", [])
    if not deleted:
        emit("История удалений пуста. Все файлы на своих местах.")
        return []

    # Загружаем точные зафиксированные версии из requirements.txt!
    frozen_reqs = parse_requirements_txt()

    # Дефолтная таблица сопоставления (зафиксирована жестко на стабильные версии из вашего requirements.txt)
    package_mapping = {
        "torch": "torch==2.2.2+cu118 torchaudio==2.2.2+cu118 torchvision==0.17.2+cu118",
        "torchaudio": "torchaudio==2.2.2+cu118",
        "torchvision": "torchvision==0.17.2+cu118",
        "tts": "TTS==0.22.0",
        "numpy": "numpy==1.26.4",
        "pygame": "pygame==2.6.1",
        "customtkinter": "customtkinter==6.0.0",
        "num2words": "num2words==0.5.14",
        "llama_cpp": "llama-cpp-python",
        "soundfile": "soundfile==0.14.0",
        "rvc_python": "rvc-python",
        # av — транзитивная зависимость rvc-python, но критична для
        # import torchvision 0.17.2 (av.logging). Без отдельного ключа
        # recovery не чинил av, когда из карантина/удалений страдала
        # только папка av, а torchvision «ломался» как симптом.
        "av": _get_av_pin(),
    }

    # Интеллектуальный перезаброс версий: если пакет найден в requirements.txt,
    # мы берем точную зафиксированную версию пользователя для 100% совместимости!
    for key, spec in package_mapping.items():
        if key == "torch":
            t_spec = frozen_reqs.get("torch")
            ta_spec = frozen_reqs.get("torchaudio")
            tv_spec = frozen_reqs.get("torchvision")
            if t_spec and ta_spec and tv_spec:
                package_mapping["torch"] = f"{t_spec} {ta_spec} {tv_spec}"
        else:
            frozen_spec = frozen_reqs.get(key) or frozen_reqs.get(key.replace("_", "-"))
            if frozen_spec:
                package_mapping[key] = frozen_spec

    # ── Сопоставляем удалённые файлы пакетам (ключ диагностики -> pip-спецификация).
    # key_to_files позволяет потом вычистить из кэша удалений ровно те записи,
    # что были обработаны (восстановлены ИЛИ признаны уже работающими). ──
    matched_specs = {}
    key_to_files = {}
    for f in deleted:
        pkg_folder = f.get("package", "unknown").lower()
        for key, pip_spec in package_mapping.items():
            # Учитываем оба варианта разделителя: ключ словаря использует
            # подчёркивание (rvc_python), а поле package — дефис (rvc-python)
            # либо наоборот, в зависимости от того, кто заполнял кэш удалений.
            if key in pkg_folder or key.replace("_", "-") in pkg_folder:
                matched_specs[key] = pip_spec
                key_to_files.setdefault(key, []).append(f)
                break

    if not matched_specs:
        emit("Не обнаружено ключевых зависимостей в истории удалений.")
        return []

    # ── ВАЛИДАЦИЯ ПО ЖИВОЙ ДИАГНОСТИКЕ ──
    # run_error_recovery слепо доверяет кэшу удалений (deleted_files). Если
    # запись устарела (файл уже вернулся из карантина, пакет починен вручную
    # или это ложное срабатывание сканировщика мусора), метод начнёт
    # «чинить» РАБОЧИЙ пакет (например TTS) — возникает видимость ошибки
    # «будто TTS отсутствует, хотя он есть в системе». Поэтому перед
    # переустановкой сверяемся с реальным состоянием окружения: если
    # компонент и так импортируется, пропускаем его и вычищаем запись из
    # кэша удалений, чтобы не «восстанавливать» рабочие пакеты при каждом
    # запуске. Если живая диагностика недоступна (live is None), откатываемся
    # к прежнему поведению — переустанавливаем всё из кэша.
    live = None
    try:
        live = run_full_diagnostics(force_refresh=False)
    except Exception as e:
        write_log(f"[Recovery] Не удалось получить живую диагностику для валидации: {e}")
        live = None

    emit(
        f"Обнаружены удаленные зависимости, требующие восстановления: {', '.join(sorted(set(matched_specs.values())))}"
    )

    restored = []
    # Записи кэша удалений, которые мы либо успешно восстановили, либо
    # признали уже работающими (пропущены) — их убираем из истории удалений,
    # чтобы не «восстанавливать» рабочие пакеты при каждом запуске.
    resolved_ids = set()
    seen_specs = set()

    for key, pkg in sorted(matched_specs.items()):
        if pkg in seen_specs:
            continue
        seen_specs.add(pkg)

        files = key_to_files.get(key, [])

        # ── RVC: специальная процедура установки ──
        # rvc-python нельзя ставить обычным `pip install ... --no-deps`: это
        # не доставит его реальные зависимости (torchcrepe/av/faiss-cpu/...),
        # не поставит fairseq через prebuilt wheel и не учтёт уже стоящий
        # torch. Делегируем специализированному установщику
        # engine.env_core.rvc_setup.install_rvc(), который делает всё это
        # корректно и адаптивно (в т.ч. самолечение при блокировках файлов
        # Windows — retry без --upgrade внутри install_rvc). Вызов происходит
        # на старте, ДО импорта тяжёлых модулей, поэтому блокировок .pyd
        # со стороны работающего приложения не возникает.
        if key == "rvc_python":
            # ВАЛИДАЦИЯ: rvc уже импортируется — не трогаем (устаревшая запись).
            if live is not None and live.get("rvc_python") is True:
                emit(
                    "⏭️ rvc-python уже импортируется — пропускаю восстановление "
                    "(устаревшая запись в кэше удалений)."
                )
                resolved_ids.update(id(f) for f in files)
                continue

            try:
                from engine.env_core import rvc_setup

                status = rvc_setup.install_rvc(progress_cb=progress_cb)
                if status and status.get("installed"):
                    emit("✅ RVC (rvc-python + зависимости) успешно восстановлен.")
                    restored.append(pkg)
                    resolved_ids.update(id(f) for f in files)
                else:
                    emit("❌ Не удалось восстановить RVC: импорт не прошёл после установки.")
            except Exception as e:
                emit(f"❌ Ошибка восстановления RVC: {e}")
            continue

        # ── av (PyAV): отдельный путь, не через torch-семейство ──
        # av не входит в CRITICAL_COMPONENTS, но без совместимого av
        # torchvision 0.17.2 не импортируется (av.logging). Если в кэше
        # удалений есть av — чиним его специализированной процедурой
        # (пин + probe av.logging), а не общим pip --no-deps без пина.
        if key == "av":
            if _av_is_compatible():
                emit(
                    "⏭️ PyAV уже совместим с torchvision — пропускаю восстановление "
                    "(устаревшая запись в кэше удалений)."
                )
                resolved_ids.update(id(f) for f in files)
                continue
            if _repair_av_for_torchvision(progress_cb=progress_cb):
                restored.append(pkg)
                resolved_ids.update(id(f) for f in files)
            continue

        # Общая ВАЛИДАЦИЯ: любой не-torch компонент, который и так
        # импортируется (True), пропускаем и вычищаем из кэша удалений.
        # torch обрабатывается отдельно ниже (семейство из 3 пакетов,
        # проверяем каждый под-компонент по отдельности).
        if key != "torch" and live is not None and live.get(key) is True:
            emit(
                f"⏭️ {key} уже работает в системе — пропускаю восстановление "
                f"(устаревшая запись в кэше удалений)."
            )
            resolved_ids.update(id(f) for f in files)
            continue

        emit(f"Восстанавливаю пакет {pkg} через pip...")

        pkg_specs = pkg.split()
        first_spec = pkg_specs[0].lower()

        # ── АДАПТИВНАЯ обработка torch-семейства (torch / torchaudio / torchvision) ──
        # Берём вариант, УЖЕ стоящий в окружении (cpu/cu118), и ставим
        # соответствующий wheel, чтобы не перекачивать 2.7 ГБ cu118, когда
        # фактически установлен cpu.
        # Триггер — ЯВНЫЕ префиксы torch-семейства (torch== / torchaudio== /
        # torchvision==), а НЕ подстрока "torch": иначе "torchvision" попадал
        # в эту ветку и тормозил восстановление самого torchvision (он
        # проверял бы импорт torch, а не torchvision, и пропускал починку).
        # Каждый под-компонент пропускаем переустановку, ТОЛЬКО если ОН САМ
        # уже работает (torch — экономим до 2.7 ГБ; torchaudio/torchvision —
        # они небольшие, но тоже незачем «чинить» рабочее).
        specs_lower = [s.lower() for s in pkg_specs]
        is_torch_family = (
            any(s.startswith("torch==") for s in specs_lower)
            or any(s.startswith("torchaudio==") for s in specs_lower)
            or any(s.startswith("torchvision==") for s in specs_lower)
        )
        if is_torch_family:
            tvariant, tindex = _resolve_recovery_torch_variant()

            try:
                from engine.env_core.torch_setup import (
                    TORCH_VERSION,
                    TORCHAUDIO_VERSION,
                    TORCHVISION_VERSION,
                )
            except Exception as imp_err:
                emit(
                    f"⚠️ Не удалось получить версии torch из torch_setup: {imp_err} "
                    f"— использую значения по умолчанию."
                )
                TORCH_VERSION, TORCHAUDIO_VERSION, TORCHVISION_VERSION = "2.2.2", "2.2.2", "0.17.2"

            suffix = "+cu118" if tvariant == "cu118" else "+cpu"
            # torch пропускаем переустановку, только если он сам уже в норме
            # (чтобы не перекачивать 2.7 ГБ зря при починке torchvision/soundfile).
            torch_ok = False
            if any(s.startswith("torch==") for s in specs_lower):
                torch_ok = _torch_already_ok(tvariant)
            # Подстраховка живой диагностикой: если torch и так импортируется,
            # точно не перекачиваем его.
            if live is not None and live.get("torch") is True:
                torch_ok = True

            # ── ПРЕД-ЛЕЧЕНИЕ av перед torchvision ──
            # Если torchvision «сломан» из-за av.logging, переустановка
            # самого torchvision ничего не даст (pip success + тот же
            # AttributeError). Сначала чиним av; если после этого
            # torchvision уже импортируется — не трогаем его wheel.
            needs_tv = any(s.startswith("torchvision==") for s in specs_lower)
            tv_live_err = live.get("torchvision") if live is not None else None
            if needs_tv and tv_live_err is not True:
                if _torchvision_error_is_av_related(tv_live_err) or not _av_is_compatible():
                    emit(
                        "🔎 torchvision не импортируется, причина связана с PyAV "
                        f"(детали: {tv_live_err!r}). Чиню av ДО torchvision..."
                    )
                    _repair_av_for_torchvision(progress_cb=progress_cb)
                    # Перепроверяем torchvision после починки av — возможно,
                    # сам torchvision-wheel цел и переустанавливать не нужно.
                    try:
                        recheck = run_full_diagnostics(force_refresh=True)
                        if recheck.get("torchvision") is True:
                            emit(
                                "✅ После починки PyAV torchvision снова импортируется — "
                                "wheel torchvision не трогаю."
                            )
                            # Обновляем live, чтобы ниже skip torchvision.
                            if live is not None:
                                live["torchvision"] = True
                            # Если в matched_specs был только torchvision и он
                            # уже ок — new_specs может стать пустым (см. ниже).
                    except Exception as re_err:
                        write_log(f"[Recovery] recheck после av-repair: {re_err}")

            new_specs = []
            for s in pkg_specs:
                sl = s.lower()
                if sl.startswith("torch=="):
                    if torch_ok:
                        continue  # torch уже работает — не перекачиваем (экономим до 2.7 ГБ)
                    new_specs.append(f"torch=={TORCH_VERSION}{suffix}")
                elif sl.startswith("torchaudio=="):
                    if live is not None and live.get("torchaudio") is True:
                        continue  # torchaudio уже работает — не трогаем
                    new_specs.append(f"torchaudio=={TORCHAUDIO_VERSION}{suffix}")
                elif sl.startswith("torchvision=="):
                    if live is not None and live.get("torchvision") is True:
                        continue  # torchvision уже работает — не трогаем
                    new_specs.append(f"torchvision=={TORCHVISION_VERSION}{suffix}")
                else:
                    new_specs.append(s)

            if not new_specs:
                # torch-семейство целиком уже в норме (напр. в спецификации
                # только torch и он работает) — пропускаем без скачивания.
                emit(
                    f"⏭️ torch-семейство ({tvariant}) уже установлено и работает — "
                    f"пропускаю переустановку (без повторного скачивания)."
                )
                restored.append(pkg)
                resolved_ids.update(id(f) for f in files)
                continue

            emit(f"🔧 Восстанавливаю torch-семейство ({tvariant}) адаптивно — индекс: {tindex}")
            # subprocess.Popen со списком аргументов НЕ делает shell-парсинг,
            # поэтому каждая спецификация — отдельный элемент списка.
            #
            # ВАЖНО: --upgrade обязателен. За --force-reinstall при
            # --target отвечает не он, а именно --upgrade — без него pip
            # видит уже существующую папку пакета в целевой директории и
            # печатает "Target directory ... already exists. Specify
            # --upgrade to force replacement.", возвращает код 0 и НИЧЕГО
            # не меняет (буквальная формулировка предупреждения pip). Раньше
            # здесь стоял только --force-reinstall, из-за чего восстановление
            # битого/устаревшего torchvision структурно не могло сработать —
            # даже без единой блокировки файла команда сама по себе ничего
            # не заменяла.
            cmd = [
                PYTHON_EXE,
                "-m",
                "pip",
                "install",
                *new_specs,
                "--target",
                SITE_PACKAGES,
                "--upgrade",
                "--force-reinstall",
                "--no-deps",
                "--extra-index-url",
                tindex,
                # Без --no-cache-dir: --force-reinstall гарантирует
                # переустановку файлов, но pip возьмёт уже скачанный wheel
                # (например torch ~2.7 ГБ для cu118) из локального
                # PIP_CACHE_DIR вместо повторной закачки с сервера.
            ]
        else:
            # ВАЖНО: pkg может содержать НЕСКОЛЬКО спецификаций через пробел
            # (например "soundfile==0.14.0"). subprocess.Popen со списком
            # аргументов НЕ делает shell-парсинг, поэтому строку нужно
            # явно разбить на отдельные элементы, иначе pip получит один
            # невалидный requirement и install провалится.
            cmd = [
                PYTHON_EXE,
                "-m",
                "pip",
                "install",
                *pkg_specs,
                "--target",
                SITE_PACKAGES,
                "--upgrade",
                "--no-deps",
                "--force-reinstall",
            ]

        # Ключи для проверки результата живой диагностикой ПОСЛЕ install —
        # код возврата pip недостаточен (см. ниже), нужно знать, какие
        # именно компоненты реально пытались восстановить.
        if is_torch_family:
            verify_keys = []
            for s in new_specs:
                sl = s.lower()
                if sl.startswith("torch=="):
                    verify_keys.append("torch")
                elif sl.startswith("torchaudio=="):
                    verify_keys.append("torchaudio")
                elif sl.startswith("torchvision=="):
                    verify_keys.append("torchvision")
        else:
            verify_keys = [key]

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
            )
            output_lines = []
            for line in iter(proc.stdout.readline, ""):
                if line:
                    output_lines.append(line)
                    emit(line.strip())
            proc.wait()

            # Залоченные .pyd/.dll живым процессом (Windows) — pip успевает
            # фактически поставить пакет и только потом падает на этапе
            # перемещения файлов в --target (_handle_target_dir → rmtree
            # старой версии), т.к. --force-reinstall/--upgrade требуют
            # убрать старую папку перед копированием новой. Повторяем БЕЗ
            # этих флагов: раз нужная версия уже стоит, pip просто пропустит
            # пакет и не тронет залоченные файлы — тот же приём, что и в
            # rvc_setup._install_with_retry.
            output_text = "".join(output_lines)
            if proc.returncode != 0 and (
                "PermissionError" in output_text
                or "WinError 5" in output_text
                or "Access is denied" in output_text
                or "Отказано" in output_text
            ):
                emit(
                    "⚠️ pip не смог перезаписать залоченные файлы (процесс запущен). "
                    "Повторяю без --force-reinstall/--upgrade — уже стоящий пакет будет пропущен."
                )
                cmd_retry = [c for c in cmd if c not in ("--force-reinstall", "--upgrade")]
                proc = subprocess.Popen(
                    cmd_retry,
                    cwd=PROJECT_ROOT,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=0,
                )
                for line in iter(proc.stdout.readline, ""):
                    if line:
                        emit(line.strip())
                proc.wait()

            # pip может вернуть код 0, даже если реальной замены файлов не
            # произошло: при retry без --upgrade/--force-reinstall pip видит,
            # что папка в --target уже существует, пишет
            # "WARNING: Target directory ... already exists. Specify
            # --upgrade to force replacement." и завершается "успешно",
            # ничего не поменяв (залоченные файлы так и остаются старыми).
            # Поэтому код возврата pip не подтверждает восстановление сам по
            # себе — сверяемся с живой диагностикой импорта.
            verify_live = None
            try:
                verify_live = run_full_diagnostics(force_refresh=True)
            except Exception as diag_err:
                write_log(
                    f"[Recovery] Не удалось проверить результат живой диагностикой: {diag_err}"
                )

            if verify_live is not None:
                confirmed = all(verify_live.get(k) is True for k in verify_keys)
            else:
                # Живая диагностика недоступна — откатываемся к коду pip.
                confirmed = proc.returncode == 0

            if confirmed:
                emit(f"✅ Пакет {pkg} успешно восстановлен (подтверждено импортом).")
                restored.append(pkg)
                resolved_ids.update(id(f) for f in files)
            elif proc.returncode == 0:
                # Раньше здесь был жёстко зашитый текст "вероятно, залочены" —
                # но pip мог отработать и чисто (без WARNING/PermissionError),
                # а импорт всё равно не подтвердиться по совсем другой
                # причине (несовместимая версия, SKIPPED из-за сломанного
                # numpy и т.п.). Показываем РЕАЛЬНЫЙ ответ диагностики по
                # каждому непрошедшему компоненту вместо догадки.
                if verify_live is not None:
                    details = "; ".join(
                        f"{k}: {verify_live.get(k)!r}"
                        for k in verify_keys
                        if verify_live.get(k) is not True
                    )
                else:
                    details = "живая диагностика недоступна"
                emit(
                    f"❌ pip вернул успех, но живая диагностика не подтвердила импорт "
                    f"{', '.join(verify_keys)}. Детали: {details}"
                )

                # ── Пост-лечение: torchvision всё ещё падает на av ──
                # Даже после reinstall torchvision import может падать
                # из-за av.logging. Чиним av и перепроверяем — без этого
                # recovery «успешно» ставит torchvision, но импорт остаётся
                # сломанным, а пользователь видит ложную «блокировку файлов».
                if (
                    is_torch_family
                    and "torchvision" in verify_keys
                    and verify_live is not None
                    and verify_live.get("torchvision") is not True
                    and _torchvision_error_is_av_related(verify_live.get("torchvision"))
                ):
                    emit(
                        "🔎 Импорт torchvision всё ещё падает на PyAV — "
                        "запускаю пост-лечение av..."
                    )
                    if _repair_av_for_torchvision(progress_cb=progress_cb):
                        try:
                            post = run_full_diagnostics(force_refresh=True)
                        except Exception:
                            post = None
                        if post is not None and all(post.get(k) is True for k in verify_keys):
                            emit(f"✅ После починки PyAV пакет {pkg} подтверждён импортом.")
                            restored.append(pkg)
                            resolved_ids.update(id(f) for f in files)
                        else:
                            post_details = (
                                "; ".join(
                                    f"{k}: {post.get(k)!r}"
                                    for k in verify_keys
                                    if post is None or post.get(k) is not True
                                )
                                if post is not None
                                else "диагностика недоступна"
                            )
                            emit(
                                f"❌ После починки PyAV импорт всё ещё не подтверждён: {post_details}"
                            )
            else:
                emit(f"❌ Ошибка восстановления пакета {pkg} (код {proc.returncode}).")
        except Exception as e:
            emit(f"❌ Не удалось восстановровать пакет {pkg}: {e}")

    # ── Пересобираем историю удалений ──
    # Убираем записи, что были либо успешно восстановлены, либо признаны уже
    # работающими (пропущены по живой диагностике). Так рабочие пакеты
    # (например, TTS) перестают «восстанавливаться» при каждом запуске.
    if resolved_ids:
        new_deleted = [f for f in deleted if id(f) not in resolved_ids]
        cache["deleted_files"] = new_deleted
        save_safe_files_cache(cache)

    # ── Финальное самолечение: убираем теневой бэкпорт dataclasses ──
    # Любая установка в рамках восстановления (в т.ч. RVC через
    # fairseq/sacrebleu) теоретически могла вернуть бэкпорт dataclasses,
    # который ТЕНЕВЫМ образом перекрывает stdlib и на следующем запуске
    # ломает импорт torch/torchvision/TTS. Вычищаем его ПОСЛЕ всех
    # установок, чтобы приложение стартовало с чистым stdlib-dataclasses.
    final_cleaned = _clean_dataclasses_backport()
    if final_cleaned:
        emit(f"🧹 В конце восстановления удалён теневой бэкпорт dataclasses: {final_cleaned}")

    # Сбрасываем кэш диагностики, чтобы форсировать перепроверку
    clear_diagnostics_cache()

    return restored
