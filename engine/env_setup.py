"""
engine/env_setup.py — анализ окружения и (пере)установка зависимостей
для локальных LLM (llama-cpp-python), с учётом набора инструкций CPU.

Без tkinter — чистая логика, чтобы её можно было гонять и из консоли/тестов.
Импорт llama_cpp проверяется в ОТДЕЛЬНОМ процессе (subprocess), а не в текущем —
если сборка несовместима с CPU (illegal instruction), крашится только проверочный
процесс, а не всё приложение.
"""

import os
import re
import sys
import subprocess
import shutil
import tempfile
import threading
import time
import json
import sysconfig
from typing import Optional

from engine.paths import BASE_DIR

_FALLBACK_SITE_PACKAGES = os.path.join(BASE_DIR, "python", "xtts_env", "Lib", "site-packages")
PYTHON_EXE = sys.executable  # тот же интерпретатор, что запустил приложение (python\runtime\python.exe)

PORTABLE_TEMP_DIR = os.path.join(BASE_DIR, "python", "temp")
PORTABLE_CACHE_DIR = os.path.join(BASE_DIR, "python", "pip_cache")


def _detect_site_packages() -> str:
    """Определяет реальную папку site-packages текущего интерпретатора.
    Если приложение запущено из bundled python — используем его site-packages.
    Иначе (системный python / venv) — то, что сообщает sysconfig."""
    if os.path.isdir(_FALLBACK_SITE_PACKAGES):
        return _FALLBACK_SITE_PACKAGES
    try:
        out = subprocess.run(
            [PYTHON_EXE, "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            path = out.stdout.strip()
            if os.path.isdir(path):
                return path
    except Exception:
        pass
    return _FALLBACK_SITE_PACKAGES


SITE_PACKAGES = _detect_site_packages()


def get_site_packages() -> list:
    """Возвращает список site-packages для текущего интерпретатора."""
    try:
        out = subprocess.run(
            [PYTHON_EXE, "-c", "import site; print(chr(10).join(site.getsitepackages() + [site.getusersitepackages()]))"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return [p.strip() for p in out.stdout.strip().splitlines() if p.strip()]
    except Exception:
        pass
    # Fallback
    return [SITE_PACKAGES]


def get_python_env_info() -> dict:
    """Диагностическая информация об окружении Python."""
    info = {
        "executable": PYTHON_EXE,
        "version": sys.version.replace("\n", " "),
        "site_packages": get_site_packages(),
        "target": SITE_PACKAGES,
        "pip_version": None,
        "pip_show": None,
        "import_probe": None,
    }

    # pip --version
    try:
        out = subprocess.run(
            [PYTHON_EXE, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            info["pip_version"] = out.stdout.strip()
    except Exception as e:
        info["pip_version"] = f"ошибка: {e}"

    # pip show llama-cpp-python
    try:
        out = subprocess.run(
            [PYTHON_EXE, "-m", "pip", "show", "llama-cpp-python"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            info["pip_show"] = out.stdout.strip()
        else:
            detail = out.stderr.strip() or ("код " + str(out.returncode))
            info["pip_show"] = f"не установлен ({detail})"
    except Exception as e:
        info["pip_show"] = f"ошибка: {e}"

    # Пробуем импортировать llama_cpp
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
            capture_output=True, text=True, timeout=15,
        )
        info["import_probe"] = (out.stdout.strip() + ("\nSTDERR: " + out.stderr.strip() if out.stderr.strip() else "")).strip()
    except Exception as e:
        info["import_probe"] = f"ошибка: {e}"

    return info


def format_env_info(info: dict) -> str:
    """Форматирует диагностику окружения для вывода в лог."""
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


def _ensure_cpuinfo() -> bool:
    """py-cpuinfo — чистый python-пакет, компиляция не нужна, ставится за секунды."""
    sys.path.insert(0, SITE_PACKAGES)
    try:
        import cpuinfo  # noqa: F401
        return True
    except ImportError:
        try:
            subprocess.run(
                [PYTHON_EXE, "-m", "pip", "install", "py-cpuinfo",
                 "--no-cache-dir", "--target", SITE_PACKAGES],
                check=True, capture_output=True, timeout=60, text=True,
            )
            return True
        except Exception:
            return False


def detect_cpu() -> dict:
    """
    {"name": str, "avx": bool, "avx2": bool, "fma": bool, "f16c": bool, "flags": set}
    Если флаги определить не удалось — считаем их отсутствующими (безопасный минимум,
    сборка получится медленнее, но не упадёт).
    """
    result = {"name": "не определено", "flags": set(),
              "avx": False, "avx2": False, "fma": False, "f16c": False}

    if _ensure_cpuinfo():
        try:
            import cpuinfo
            info = cpuinfo.get_cpu_info()
            result["name"] = info.get("brand_raw", "не определено")
            flags = set(info.get("flags", []))
            result["flags"] = flags
            result["avx"] = "avx" in flags
            result["avx2"] = "avx2" in flags
            result["fma"] = "fma" in flags or "fma3" in flags
            result["f16c"] = "f16c" in flags
        except Exception:
            pass

    return result


# Ключевые .py-файлы самого пакета (не путать с DLL из lib/ — их наличие
# ничего не говорит о том, докопировался ли Python-код). Если установка
# прервалась на середине копирования, в llama_cpp/ могут остаться только
# бинарники из lib/, а сам пакет будет нерабочим — ровно та картина,
# которую этот список и ловит.
_REQUIRED_PACKAGE_FILES = ("__init__.py", "llama.py", "llama_cache.py")


def check_package_integrity() -> dict:
    """
    Проверяет, что в llama_cpp/ реально лежат ключевые .py-файлы пакета,
    а не только скомпилированные DLL (типичная картина при установке,
    прерванной на середине копирования файлов).
    Возвращает {"present": bool, "complete": bool, "missing": [имена файлов]}.
    """
    target = os.path.join(SITE_PACKAGES, "llama_cpp")
    if not os.path.isdir(target):
        return {"present": False, "complete": False, "missing": list(_REQUIRED_PACKAGE_FILES)}
    missing = [f for f in _REQUIRED_PACKAGE_FILES if not os.path.isfile(os.path.join(target, f))]
    return {"present": True, "complete": not missing, "missing": missing}


def llama_cpp_status() -> dict:
    """Проверка импорта в ОТДЕЛЬНОМ процессе — изолирует возможный hard crash."""
    # Сначала быстрая проверка целостности файлов на диске — если пакет
    # явно неполный (например, только lib/ без .py-файлов, как бывает при
    # прерванной установке), сразу возвращаем понятную причину, не тратя
    # время на subprocess-проверку импорта с невнятным ImportError на выходе.
    integrity = check_package_integrity()
    if integrity["present"] and not integrity["complete"]:
        missing_str = ", ".join(integrity["missing"])
        return {
            "installed": False, "path": None,
            "error": f"пакет установлен не полностью — отсутствуют файлы: {missing_str} "
                     f"(похоже, установка была прервана; нужно удалить и поставить заново)",
        }

    # Пробуем сначала с целевой папкой, затем без неё (если модуль установлен в систему/venv)
    probes = [
        (
            "import sys; sys.path.insert(0, r'%s'); "
            "import llama_cpp; print('OK=' + llama_cpp.__file__)" % SITE_PACKAGES
        ),
        "import llama_cpp; print('OK=' + llama_cpp.__file__)",
    ]
    last_error = ""
    for probe in probes:
        try:
            proc = subprocess.run(
                [PYTHON_EXE, "-c", probe],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                line = proc.stdout.strip().splitlines()[0]
                if line.startswith("OK="):
                    return {"installed": True, "path": line[3:], "error": None}
            err = (proc.stderr or "").strip()
            if proc.returncode < 0:
                err = f"процесс завершён аварийно (код {proc.returncode}) — {err}"
            last_error = err or f"exit code {proc.returncode}"
        except subprocess.TimeoutExpired:
            last_error = "проверка не уложилась в таймаут"
        except Exception as e:
            last_error = str(e)
    return {"installed": False, "path": None, "error": last_error}




# ── Checkpoint / resume для длительной установки llama-cpp-python ────────────

CHECKPOINT_PATH = os.path.join(BASE_DIR, ".llama_install_checkpoint.json")

# Отдельный от чекпоинта файл — чекпоинт чистится после успешной установки
# (_clear_checkpoint), а нам нужно ПОСТОЯННО помнить, с каким backend'ом
# реально собралась текущая llama-cpp-python. Без этого local_llm_client.py
# не может отличить "GPU есть физически" от "GPU-инференс реально доступен":
# если каскад откатился на CPU-fallback (GPU-сборка не импортировалась),
# n_gpu_layers=-1 всё равно попытается выгрузить слои на GPU в сборке без
# единого GPU backend'а — это падает C++ исключением (0xE06D7363) мимо
# обычного Python try/except.
INSTALLED_BACKEND_PATH = os.path.join(BASE_DIR, ".llama_installed_backend.json")

# Backend'ы, для которых подтверждён нативный краш при реальной инициализации
# GPU (Llama(n_gpu_layers=-1)) — в отличие от INSTALLED_BACKEND_PATH (что
# сейчас стоит) это "чёрный список" того, что автовыбору больше НЕЛЬЗЯ
# предлагать на этой машине, пока файл не удалят вручную (например, после
# смены GPU/драйвера).
BROKEN_BACKENDS_PATH = os.path.join(BASE_DIR, ".llama_broken_backends.json")


def mark_backend_broken(backend: str):
    """Помечает backend как подтверждённо нерабочий на этой машине."""
    broken = get_broken_backends()
    broken.add(backend)
    try:
        with open(BROKEN_BACKENDS_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(broken), f)
    except Exception:
        pass


def get_broken_backends() -> set:
    try:
        with open(BROKEN_BACKENDS_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_installed_backend(backend: str):
    try:
        with open(INSTALLED_BACKEND_PATH, "w", encoding="utf-8") as f:
            json.dump({"backend": backend, "timestamp": time.time()}, f)
    except Exception:
        pass


def _clear_installed_backend():
    try:
        if os.path.exists(INSTALLED_BACKEND_PATH):
            os.remove(INSTALLED_BACKEND_PATH)
    except Exception:
        pass


def get_installed_backend() -> Optional[str]:
    """
    Backend, с которым реально собрана/установлена ТЕКУЩАЯ llama-cpp-python
    ('cuda' | 'vulkan' | 'cpu'), а не то, что теоретически мог бы поддержать
    GPU в системе. None — если неизвестно (например, установка была ещё до
    этого фикса, или файл не читается).
    """
    try:
        with open(INSTALLED_BACKEND_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("backend")
    except Exception:
        return None


def _load_checkpoint() -> dict:
    try:
        with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_checkpoint(stage: str, meta: dict = None):
    data = {"stage": stage, "timestamp": time.time(), "meta": meta or {}}
    try:
        with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _clear_checkpoint():
    try:
        if os.path.exists(CHECKPOINT_PATH):
            os.remove(CHECKPOINT_PATH)
    except Exception:
        pass


def _read_pip_output(proc: subprocess.Popen, progress_cb=None):
    """Читает stdout pip в реальном времени, включая строки-прогресс-бары
    с возвратом каретки (\r) и длинные статусные сообщения вида
    'Building wheel... still running...'. Одинаковые статусные строки
    заменяют предыдущую, а не накапливаются."""

    def _build_prefix(line: str) -> str:
        # Для строк сборки wheel возвращаем префикс, по которому можно
        # понять, что это одно и то же сообщение в разные моменты времени.
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
        if not progress_cb or not line:
            return
        prefix = _build_prefix(line)
        # Если строка относится к тому же этапу сборки, что и предыдущая,
        # отправляем с \r, чтобы UI заменил последнюю строку.
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
                # Прогресс-бар скачивания: перезаписать последнюю строку
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

def _cuda_index_from_version(cuda_version: str) -> str:
    """Преобразует строку вида '12.4' в индекс wheel 'cu124'."""
    if not cuda_version:
        return ""
    try:
        parts = cuda_version.strip().split(".")
        major = parts[0]
        minor = parts[1] if len(parts) > 1 else "0"
        return f"cu{major}{minor}"
    except Exception:
        return ""


def _pick_llama_backend(gpu_info: dict) -> tuple:
    """
    Выбирает backend для llama-cpp-python на основе GPU.
    Возвращает кортеж (backend_name, extra_index_url).
    backend_name: "cuda" | "vulkan" | "cpu"

    Учитывает BROKEN_BACKENDS_PATH: если backend уже подтверждённо крашился
    при реальной GPU-инициализации на этой машине (см. mark_backend_broken),
    автовыбор больше не предложит его повторно — сразу CPU.
    """
    vendor = (gpu_info or {}).get("vendor", "unknown")
    cuda_version = (gpu_info or {}).get("cuda_version")
    broken = get_broken_backends()

    if vendor == "nvidia" and cuda_version:
        index = _cuda_index_from_version(cuda_version)
        if index and "cuda" not in broken:
            return ("cuda", f"https://abetlen.github.io/llama-cpp-python/whl/{index}")

    if vendor in ("amd", "intel") and "vulkan" not in broken:
        # Vulkan — единственный realistic prebuilt путь для AMD/Intel на Windows
        # без установки ROCm/HIP SDK.
        return ("vulkan", "https://abetlen.github.io/llama-cpp-python/whl/vulkan")

    return ("cpu", "")


def _build_install_cmd(backend: str, extra_index: str, site_packages: str) -> list:
    """Формирует pip install под конкретный backend."""
    cmd = [
        PYTHON_EXE, "-m", "pip", "install", "llama-cpp-python",
        "--no-deps", "--target", site_packages,
        # --upgrade гарантирует перезапись файлов от предыдущей неудачной
        # попытки установки (иначе pip молча пропускает существующие
        # директории вроде bin/include/lib с предупреждением "already exists").
        "--upgrade",
    ]
    if backend in ("cuda", "vulkan"):
        cmd.extend(["--extra-index-url", extra_index, "--prefer-binary"])
    elif backend == "cpu":
        # -v — показывать реальный вывод cmake/компилятора вместо немого
        # "Building wheel... still running...", чтобы было видно, что
        # процесс действительно работает, а не завис.
        cmd.append("-v")
    return cmd


def _find_any_local_model() -> Optional[str]:
    """Ищет любой уже скачанный .gguf в models/ — не важно какой конкретно,
    лишь бы можно было реально попытаться создать Llama() для проверки
    backend'а. Если моделей ещё нет — smoke-тест на этапе установки просто
    пропускается (проверка тогда произойдёт при первой реальной загрузке,
    см. local_llm_client.py::_get_llm)."""
    models_dir = os.path.join(BASE_DIR, "models")
    if not os.path.isdir(models_dir):
        return None
    for name in sorted(os.listdir(models_dir)):
        if name.lower().endswith(".gguf"):
            return os.path.join(models_dir, name)
    return None


def smoke_test_gpu_init(backend: str, model_path: str = None, timeout: float = 60.0) -> dict:
    """
    Реальная проверка, что backend может проинициализировать GPU-контекст
    (а не просто импортируется — llama_cpp_status() это уже покрывает).
    Запускается в ИЗОЛИРОВАННОМ сабпроцессе: нативный краш вроде SEH
    0xE06D7363 убьёт только сабпроцесс, не основной процесс установки.

    model_path — явно выбранная пользователем модель (например, через кнопку
    "установить зависимости под выбранную модель" в интерфейсе). Если не
    передан — берём любую уже скачанную модель из models/ (универсальный
    авто-режим); если и такой нет — тест пропускается.

    Возвращает {"ok": bool, "skipped": bool, "error": str|None}.
    skipped=True — не нашлось ни одной модели для теста; в этом случае
    ok всегда True (нечего опровергать), а реальная проверка отложится на
    первую загрузку модели пользователем.
    """
    if backend == "cpu":
        return {"ok": True, "skipped": False, "error": None}

    if not model_path:
        model_path = _find_any_local_model()
    elif not os.path.isfile(model_path):
        # Явно передан путь, но файла там нет — не тихо переключаемся на
        # автопоиск (это скрыло бы ошибку пользователя), а честно считаем
        # тест пропущенным.
        model_path = None

    if not model_path:
        return {"ok": True, "skipped": True, "error": None}

    probe = (
        "import sys; sys.path.insert(0, r'%s'); "
        "from llama_cpp import Llama; "
        "m = Llama(model_path=r'%s', n_ctx=16, n_gpu_layers=-1, verbose=False); "
        "print('SMOKE_OK')"
    ) % (SITE_PACKAGES, model_path)

    try:
        proc = subprocess.run(
            [PYTHON_EXE, "-c", probe],
            capture_output=True, text=True, timeout=timeout,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0 and "SMOKE_OK" in out:
            return {"ok": True, "skipped": False, "error": None}
        if proc.returncode < 0:
            return {"ok": False, "skipped": False,
                     "error": f"процесс завершён аварийно (код {proc.returncode})"}
        return {"ok": False, "skipped": False, "error": out.strip()[-500:] or f"exit code {proc.returncode}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "skipped": False, "error": "smoke-тест не уложился в таймаут"}
    except Exception as e:
        return {"ok": False, "skipped": False, "error": str(e)}


def resolve_backend() -> dict:
    """
    Единая точка анализа среды для локальных LLM.
    Возвращает словарь с CPU, GPU, выбранным backend и готовой командой установки.
    """
    cpu = detect_cpu()
    gpu = detect_gpu()
    backend, extra_index = _pick_llama_backend(gpu)
    return {
        "cpu": cpu,
        "gpu": gpu,
        "backend": backend,
        "extra_index": extra_index,
        "can_gpu": backend in ("cuda", "vulkan"),
        "install_command": _build_install_cmd(backend, extra_index, SITE_PACKAGES),
    }


def cleanup_orphaned_checkpoint():
    """Если llama-cpp-python уже установлен, а чекпоинт остался в незавершённом
    состоянии — удаляем его, чтобы resume-логика не сработала ложно."""
    if not os.path.exists(CHECKPOINT_PATH):
        return
    checkpoint = _load_checkpoint()
    if checkpoint.get("stage") in (None, "", "done"):
        return
    try:
        if llama_cpp_status()["installed"]:
            _clear_checkpoint()
    except Exception:
        pass


def build_cmake_args(cpu: dict) -> str:
    flags = []
    if not cpu.get("avx2"): flags.append("-DGGML_AVX2=OFF")
    if not cpu.get("fma"): flags.append("-DGGML_FMA=OFF")
    if not cpu.get("f16c"): flags.append("-DGGML_F16C=OFF")
    if not cpu.get("avx"): flags.append("-DGGML_AVX=OFF")
    return " ".join(flags)


def _clean_previous_install():
    """Сносит остатки предыдущей установки — иначе pip --target молча не перезаписывает файлы."""
    if not os.path.isdir(SITE_PACKAGES):
        return
    for name in os.listdir(SITE_PACKAGES):
        if name.startswith("llama_cpp"):
            full = os.path.join(SITE_PACKAGES, name)
            shutil.rmtree(full, ignore_errors=True) if os.path.isdir(full) else \
                (os.remove(full) if os.path.isfile(full) else None)
    # bin/include/lib — общие подпапки llama-cpp-python; трогаем, только если там его DLL
    for name in ("bin", "include", "lib"):
        full = os.path.join(SITE_PACKAGES, name)
        if os.path.isdir(full):
            try:
                if any(f.lower().startswith(("ggml", "llama")) for f in os.listdir(full)):
                    shutil.rmtree(full, ignore_errors=True)
            except Exception:
                pass


# ── Автодогрузка недостающих зависимостей ────────────────────────────────────
# llama-cpp-python ставится с --no-deps (чтобы не трогать существующие
# torch/numpy в окружении), но у него есть собственные лёгкие зависимости
# (diskcache, typing-extensions, jinja2 и т.д.), которых при этом не будет.
# Вместо хардкода списка — определяем недостающий модуль прямо из текста
# ModuleNotFoundError и доустанавливаем его точечно, в цикле, пока импорт
# не заработает (или не кончится лимит попыток).

_MISSING_MODULE_RE = re.compile(r"No module named ['\"]([\w.]+)['\"]")

# На случай если имя импортируемого модуля не совпадает с именем pip-пакета.
_MODULE_TO_PACKAGE = {
    "yaml": "PyYAML",
    "PIL": "Pillow",
    "cv2": "opencv-python",
}


def _extract_missing_module(error_text: str) -> Optional[str]:
    """Достаёт имя недостающего пакета из текста ModuleNotFoundError."""
    if not error_text:
        return None
    match = _MISSING_MODULE_RE.search(error_text)
    if not match:
        return None
    module = match.group(1).split(".")[0]  # берём корневой пакет, не подмодуль
    return _MODULE_TO_PACKAGE.get(module, module)


def _install_single_dependency(package: str, progress_cb=None) -> bool:
    """Ставит один недостающий пакет через --no-deps --target, не трогая остальное окружение."""
    def emit(line):
        if progress_cb:
            progress_cb(line)

    emit(f"Ставлю недостающую зависимость: {package}...")
    try:
        proc = subprocess.run(
            [PYTHON_EXE, "-m", "pip", "install", "--no-deps", "--target", SITE_PACKAGES,
             "--no-cache-dir", package],
            capture_output=True, text=True, timeout=180,
        )
    except Exception as e:
        emit(f"⚠️ Не удалось установить {package}: {e}")
        return False
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip()[-500:]
        emit(f"⚠️ Не удалось установить {package}: {detail}")
        return False
    return True


# ── Диагностика "жив ли процесс установки" по реальным файлам на диске ──────
# Идея: не гадать по выводу pip (он может молчать долго и легитимно), а
# смотреть, пишутся ли реально файлы на диск — во временных папках, которые
# pip создаёт при сборке пакета из исходников, и в целевой site-packages.
# Если файлы недавно менялись — процесс точно жив, даже если лог молчит.

def _find_pip_build_activity(max_scan_seconds: float = 0.5) -> Optional[float]:
    """
    Ищет временные папки, которые pip создаёт при сборке пакета из исходников
    (pip-install-*, pip-req-build-*, pip-build-env-*), и возвращает unix-время
    последнего изменения файла внутри них. None, если таких папок не нашлось
    (например, установка ещё не началась или уже завершилась и pip их удалил).
    Ограничена по времени сканирования, чтобы не тормозить на большом /Temp.
    """
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
            if not (name.startswith("pip-install-") or name.startswith("pip-req-build-")
                    or name.startswith("pip-build-env-")):
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
    """
    Снимок "жив ли процесс установки прямо сейчас", основанный на реальных
    файлах на диске, а не на выводе pip.
    Возвращает:
      {
        "last_activity_seconds_ago": float|None,  # None = не нашли следов активности вообще
        "target_dir_files": int,                   # сколько файлов уже лежит в целевой llama_cpp
      }
    """
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
            if result["last_activity_seconds_ago"] is None or ago < result["last_activity_seconds_ago"]:
                result["last_activity_seconds_ago"] = ago

    return result


def _install_watchdog(stop_event: threading.Event, progress_cb, interval: float = 20.0, stall_threshold: float = 90.0):
    """Фоновый поток: раз в `interval` секунд проверяет активность файлов на
    диске и пишет однозначный статус в лог — идёт сборка или похоже на
    зависание. Работает параллельно с чтением вывода pip, не блокирует его."""
    def emit(line):
        if progress_cb:
            progress_cb(line)

    while not stop_event.wait(interval):
        info = get_install_activity_status()
        ago = info["last_activity_seconds_ago"]
        if ago is None:
            emit("🔧 Сборка идёт (файлы сборки ещё не появились на диске — это нормально на старте)...")
        elif ago < stall_threshold:
            emit(f"🔧 Сборка идёт — файлы менялись {int(ago)} сек назад, процесс жив.")
        else:
            emit(f"⚠️ Файлы не менялись уже {int(ago)} сек — процесс, возможно, завис.")


def get_startup_install_state() -> dict:
    """
    Проверка при запуске приложения: была ли прошлая установка прервана,
    и в каком она состоянии на самом деле (не только по чекпоинту, но и
    по факту наличия файлов и импортируемости).
    Возвращает одно из:
      {"state": "clean"}                    — чекпоинта нет, ничего не висит
      {"state": "installed", ...}            — уже установлено и импортируется
      {"state": "interrupted", "stage": ..., "age_seconds": ...} — есть недоделанный чекпоинт
    """
    checkpoint = _load_checkpoint()
    stage = checkpoint.get("stage")

    if not stage or stage in ("", "done"):
        return {"state": "clean"}

    status = llama_cpp_status()
    if status["installed"]:
        return {"state": "installed", "path": status["path"]}

    age = None
    ts = checkpoint.get("timestamp")
    if ts:
        age = max(0.0, time.time() - ts)

    activity = get_install_activity_status()
    return {
        "state": "interrupted",
        "stage": stage,
        "age_seconds": age,
        "target_dir_files": activity["target_dir_files"],
        "meta": checkpoint.get("meta", {}),
    }


def install_llama_cpp(progress_cb=None, resume: bool = False, backend: str = None, model_path: str = None) -> dict:
    """
    Устанавливает llama-cpp-python с автовыбором backend:
      - NVIDIA + CUDA  → prebuilt CUDA wheel
      - AMD/Intel      → prebuilt Vulkan wheel
      - остальное      → CPU-сборка из исходников (fallback)
    progress_cb(line: str) — вызывается на каждую строку вывода.
    resume=True — продолжить прерванную установку с тем же backend.
    backend="cuda"|"vulkan"|"cpu" — принудительный выбор (иначе авто).
    model_path — явно выбранная пользователем модель для smoke-теста GPU-
    инициализации (кнопка "установить зависимости под выбранную модель" в
    интерфейсе). Если не передан — smoke-тест берёт любую модель из models/
    (универсальный авто-режим) либо пропускается, если моделей ещё нет.
    Бросает RuntimeError при неуспехе. Возвращает llama_cpp_status() при успехе.
    """
    def emit(line):
        if progress_cb:
            progress_cb(line)

    checkpoint = _load_checkpoint()
    is_resume = resume and checkpoint.get("stage") not in (None, "", "done")

    cpu = detect_cpu()
    gpu = detect_gpu()

    # Определяем backend
    if is_resume:
        backend = checkpoint.get("meta", {}).get("backend") or backend or "cpu"
    if backend is None:
        backend, extra_index = _pick_llama_backend(gpu)
    else:
        _, extra_index = _pick_llama_backend(gpu) if backend == "cpu" else (backend, {
            "cuda": f"https://abetlen.github.io/llama-cpp-python/whl/{_cuda_index_from_version(gpu.get('cuda_version'))}",
            "vulkan": "https://abetlen.github.io/llama-cpp-python/whl/vulkan",
        }.get(backend, ""))

    emit(f"CPU: {cpu['name']}")
    if gpu.get("vendor") != "unknown":
        emit(f"GPU: {gpu.get('vendor', 'unknown').upper()} {gpu.get('name', '')} (VRAM: {gpu.get('vram_gb') or '?'} GB)")

    if backend == "cpu":
        emit("Backend: CPU (сборка из исходников)")
    elif backend == "cuda":
        emit(f"Backend: NVIDIA CUDA {gpu.get('cuda_version')} → prebuilt wheel")
    elif backend == "vulkan":
        emit("Backend: Vulkan → prebuilt wheel")

    # Выводим диагностику окружения до установки
    emit(format_env_info(get_python_env_info()))

    if is_resume:
        stage = checkpoint.get("stage", "unknown")
        emit(f"Продолжаю прерванную установку (этап: {stage}, backend: {backend})...")
    else:
        emit("Удаляю предыдущую установку (если была)...")
        _clean_previous_install()
        _save_checkpoint("cleaned", {"backend": backend, "cpu": cpu, "gpu": gpu})

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # Изолируем временные файлы и кэш pip внутри папки проекта (портативный режим)
    os.makedirs(PORTABLE_TEMP_DIR, exist_ok=True)
    os.makedirs(PORTABLE_CACHE_DIR, exist_ok=True)
    env["TMPDIR"] = PORTABLE_TEMP_DIR
    env["TEMP"] = PORTABLE_TEMP_DIR
    env["TMP"] = PORTABLE_TEMP_DIR
    env["PIP_CACHE_DIR"] = PORTABLE_CACHE_DIR

    # CPU-сборка требует CMAKE_ARGS; GPU prebuilt wheels — нет.
    if backend == "cpu":
        cmake_args = build_cmake_args(cpu)
        emit(f"Отключаемые наборы инструкций: {cmake_args or '(нет — CPU поддерживает всё нужное)'}")
        if cmake_args:
            env["CMAKE_ARGS"] = cmake_args
        # Используем все ядра CPU для компиляции — может заметно ускорить сборку.
        env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(os.cpu_count() or 4)

    cmd = _build_install_cmd(backend, extra_index, SITE_PACKAGES)
    emit(f"Команда установки: {' '.join(cmd)}")
    # При продолжении используем pip cache, чтобы не перекачивать заново
    if not is_resume:
        cmd.append("--no-cache-dir")

    emit("Устанавливаю (это может занять несколько минут)...")
    _save_checkpoint("downloading", {"backend": backend, "cpu": cpu, "gpu": gpu})

    proc = subprocess.Popen(
        cmd, cwd=BASE_DIR, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        bufsize=0,
    )

    # Для долгой CPU-сборки запускаем сторожевой поток, который параллельно
    # с чтением вывода pip проверяет реальные файлы на диске и раз в ~20 сек
    # однозначно сообщает: сборка идёт или, похоже, зависла.
    watchdog_stop = threading.Event()
    watchdog_thread = None
    if backend == "cpu":
        watchdog_thread = threading.Thread(
            target=_install_watchdog, args=(watchdog_stop, progress_cb), daemon=True,
        )
        watchdog_thread.start()

    try:
        _read_pip_output(proc, progress_cb)
        proc.wait()
    finally:
        watchdog_stop.set()
        if watchdog_thread:
            watchdog_thread.join(timeout=2)

    if proc.returncode != 0:
        _save_checkpoint("failed", {"returncode": proc.returncode, "backend": backend})
        # GPU-установка не удалась → fallback на CPU, если это был не CPU
        if backend != "cpu":
            emit(f"❌ {backend}-сборка не установилась (код {proc.returncode}). Перехожу на CPU-fallback...")
            return install_llama_cpp(progress_cb=progress_cb, resume=False, backend="cpu", model_path=model_path)
        raise RuntimeError(f"pip завершился с кодом {proc.returncode}")

    _save_checkpoint("building", {"backend": backend, "cpu": cpu, "gpu": gpu})
    emit("Проверяю импорт (в отдельном процессе)...")
    status = llama_cpp_status()

    # Самовосстановление: если импорт падает из-за отсутствующего модуля
    # (llama-cpp-python ставился с --no-deps) — определяем его имя прямо
    # из текста ошибки, доустанавливаем и пробуем снова. Так закрываются
    # любые его лёгкие зависимости (diskcache, jinja2, ...) без хардкода
    # конкретного списка, который может устареть в новой версии пакета.
    MAX_DEP_ATTEMPTS = 6
    attempts = 0
    seen_packages = set()
    while not status["installed"] and attempts < MAX_DEP_ATTEMPTS:
        missing = _extract_missing_module(status.get("error"))
        if not missing or missing in seen_packages:
            break  # не ModuleNotFoundError или уже пытались это ставить — не зацикливаемся
        seen_packages.add(missing)
        attempts += 1
        if not _install_single_dependency(missing, progress_cb):
            break
        status = llama_cpp_status()

    if not status["installed"]:
        _save_checkpoint("failed", {"error": status.get("error"), "backend": backend})
        if backend != "cpu":
            emit(f"❌ {backend}-сборка установилась, но не импортируется. Перехожу на CPU-fallback...")
            return install_llama_cpp(progress_cb=progress_cb, resume=False, backend="cpu", model_path=model_path)
        raise RuntimeError(f"Установка прошла, но импорт не удался: {status['error']}")

    _clear_checkpoint()

    # Финальная проверка: пакет импортируется — это ещё не значит, что GPU
    # реально инициализируется на этой карте (см. историю с Vulkan на RX 570).
    # Если в models/ уже лежит скачанная модель — пробуем реально её
    # загрузить с n_gpu_layers=-1 в изолированном сабпроцессе. Если backend
    # не проходит эту проверку — сразу помечаем его broken и откатываемся
    # на CPU, не дожидаясь краха у пользователя в проде.
    if backend != "cpu":
        if model_path:
            emit(f"Проверяю реальную GPU-инициализацию на выбранной модели ({os.path.basename(model_path)})...")
        else:
            emit("Проверяю реальную GPU-инициализацию...")
        smoke = smoke_test_gpu_init(backend, model_path=model_path)
        if smoke["skipped"]:
            emit("⚠️ Нет модели для проверки — GPU-инициализация будет проверена при первой загрузке модели.")
        elif not smoke["ok"]:
            emit(f"❌ {backend}-backend не проходит реальную GPU-инициализацию: {smoke['error']}")
            mark_backend_broken(backend)
            emit("Перехожу на CPU-fallback...")
            return install_llama_cpp(progress_cb=progress_cb, resume=False, backend="cpu", model_path=model_path)
        else:
            emit(f"✅ GPU-инициализация ({backend}) подтверждена на реальной модели.")

    _save_installed_backend(backend)
    backend_msg = {"cuda": "CUDA", "vulkan": "Vulkan", "cpu": "CPU"}.get(backend, backend)
    emit(f"✅ Готово — llama-cpp-python ({backend_msg}) установлен и работает.")
    return status


def uninstall_llama_cpp(progress_cb=None) -> bool:
    """Удаляет llama-cpp-python из окружения приложения."""
    def emit(line):
        if progress_cb:
            progress_cb(line)

    emit("Удаляю llama-cpp-python...")
    _clean_previous_install()
    _clear_checkpoint()
    _clear_installed_backend()
    emit("✅ llama-cpp-python удалён.")
    return True

def _get_vram_gb_from_registry(name_hint: str) -> Optional[float]:
    """
    Win32_VideoController.AdapterRAM в WMI — 32-битное поле (DWORD). Для видеокарт
    с VRAM >= 4GB оно либо переполняется, либо Windows обрезает значение ровно
    до 4 294 967 295 байт (~4.0 GB) — известное ограничение, не связано с
    реальным объёмом памяти карты.
    Реальное значение Windows хранит отдельно, в 64-битном поле реестра
    'HardwareInformation.qwMemorySize' у ключа драйвера видеокарты — читаем его.
    Возвращает None, если не удалось прочитать (тогда вызывающий код падает
    обратно на WMI AdapterRAM как менее точный, но рабочий fallback).
    """
    try:
        ps_cmd = (
            "Get-ItemProperty 'HKLM:\\SYSTEM\\ControlSet001\\Control\\Class\\"
            "{4d36e968-e325-11ce-bfc1-08002be10318}\\00*' "
            "-Name 'HardwareInformation.qwMemorySize','DriverDesc' -ErrorAction SilentlyContinue | "
            "Select-Object DriverDesc, 'HardwareInformation.qwMemorySize' | ConvertTo-Json -Compress"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return None
        data = json.loads(proc.stdout.strip())
        if isinstance(data, dict):
            data = [data]
        hint_low = (name_hint or "").lower()
        exact_match_gb = None
        best_gb = None
        for entry in data:
            desc = str(entry.get("DriverDesc") or "")
            size = entry.get("HardwareInformation.qwMemorySize")
            if not size:
                continue
            try:
                size = int(size)
            except Exception:
                continue
            gb = size / (1024 ** 3)
            if hint_low and desc.strip().lower() == hint_low:
                exact_match_gb = gb
                break
            if best_gb is None or gb > best_gb:
                best_gb = gb
        chosen = exact_match_gb if exact_match_gb is not None else best_gb
        return round(chosen, 2) if chosen else None
    except Exception:
        return None


def detect_gpu() -> dict:
    """
    {"vendor": "nvidia" | "amd" | "intel" | "unknown",
     "name": str,
     "cuda_version": str | None,   # только для vendor == "nvidia"
     "vram_gb": float | None}      # доступная видеопамять в GB (best-effort)

    Порядок проверки: сначала nvidia-smi (ставится вместе с драйвером NVIDIA,
    отдельно ничего просить не надо). Если его нет — смотрим на любой
    видеоадаптер через WMI (PowerShell CIM), там же выцепляем AMD/Intel.
    Если ничего не нашли — считаем "unknown", это ведёт к CPU-варианту.
    VRAM определяется best-effort: для NVIDIA — точно через nvidia-smi,
    для AMD/Intel — через AdapterRAM из WMI (может быть неточным/устаревшим).
    """
    result = {"vendor": "unknown", "name": "не определено", "cuda_version": None, "vram_gb": None}

    # ── NVIDIA ──────────────────────────────────────────────────────────────
    try:
        proc = subprocess.run(
            ["nvidia-smi"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0 and proc.stdout:
            out = proc.stdout
            result["vendor"] = "nvidia"

            # Имя карты: строка вида "| N%   xx°C  ...  NVIDIA GeForce RTX 3060 ..."
            for line in out.splitlines():
                if "NVIDIA" in line and ("GeForce" in line or "RTX" in line or "GTX" in line or "Quadro" in line or "Tesla" in line):
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 2:
                        result["name"] = parts[1].split("  ")[0].strip()
                    break

            # Версия CUDA: строка вида "CUDA Version: 12.4"
            for line in out.splitlines():
                if "CUDA Version" in line:
                    try:
                        result["cuda_version"] = line.split("CUDA Version:")[1].strip().split()[0].rstrip("|").strip()
                    except Exception:
                        pass
                    break

            # Объём VRAM (MB) через nvidia-smi
            try:
                vram_proc = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10,
                )
                if vram_proc.returncode == 0 and vram_proc.stdout.strip():
                    vram_mb = float(vram_proc.stdout.strip().splitlines()[0].strip())
                    result["vram_gb"] = round(vram_mb / 1024, 2)
            except Exception:
                pass

            return result
    except FileNotFoundError:
        pass  # nvidia-smi отсутствует — не NVIDIA-система (или драйвер не установлен)
    except Exception:
        pass

    # ── AMD / Intel через WMI ────────────────────────────────────────────────
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode == 0 and proc.stdout:
            names = [n.strip() for n in proc.stdout.splitlines() if n.strip()]
            for name in names:
                low = name.lower()
                if "amd" in low or "radeon" in low:
                    result["vendor"] = "amd"
                    result["name"] = name
                    vram_gb = _get_vram_gb_from_registry(name)
                    if vram_gb is not None:
                        result["vram_gb"] = vram_gb
                    else:
                        # Fallback: WMI AdapterRAM — ненадёжно для карт >=4GB
                        # (32-битное поле, обрезается до ~4.0 GB), но лучше,
                        # чем совсем ничего, если реестр почему-то недоступен.
                        try:
                            ram_proc = subprocess.run(
                                ["powershell", "-NoProfile", "-Command",
                                 "(Get-CimInstance Win32_VideoController | Where-Object {$_.Name -eq '%s'}).AdapterRAM" % name],
                                capture_output=True, text=True, timeout=15,
                            )
                            if ram_proc.returncode == 0 and ram_proc.stdout.strip():
                                ram_bytes = int(ram_proc.stdout.strip().splitlines()[0].strip())
                                result["vram_gb"] = round(ram_bytes / (1024 ** 3), 2)
                        except Exception:
                            pass
                    return result
                if "intel" in low:
                    result["vendor"] = "intel"
                    result["name"] = name
                    vram_gb = _get_vram_gb_from_registry(name)
                    if vram_gb is not None:
                        result["vram_gb"] = vram_gb
                    else:
                        try:
                            ram_proc = subprocess.run(
                                ["powershell", "-NoProfile", "-Command",
                                 "(Get-CimInstance Win32_VideoController | Where-Object {$_.Name -eq '%s'}).AdapterRAM" % name],
                                capture_output=True, text=True, timeout=15,
                            )
                            if ram_proc.returncode == 0 and ram_proc.stdout.strip():
                                ram_bytes = int(ram_proc.stdout.strip().splitlines()[0].strip())
                                result["vram_gb"] = round(ram_bytes / (1024 ** 3), 2)
                        except Exception:
                            pass
                    return result
            if names:
                result["name"] = names[0]
    except Exception:
        pass

    return result