# -*- coding: utf-8 -*-
"""
engine/env_core/llama_setup.py — логика установки и проверки llama-cpp-python.
"""
import os
import sys
import json
import subprocess
import time
import shutil
from typing import Optional
from engine.env_core.cpu_gpu import detect_cpu, detect_gpu

# Вычисляем корень проекта динамически
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_CORE_DIR))

PYTHON_EXE = sys.executable
SITE_PACKAGES = os.path.join(PROJECT_ROOT, "python", "xtts_env", "Lib", "site-packages")
PORTABLE_TEMP_DIR = os.path.join(PROJECT_ROOT, "python", "temp")
PORTABLE_CACHE_DIR = os.path.join(PROJECT_ROOT, "python", "pip_cache")

_REQUIRED_PACKAGE_FILES = ("__init__.py", "llama.py", "llama_cache.py")

CHECKPOINT_PATH = os.path.join(PROJECT_ROOT, ".llama_install_checkpoint.json")
INSTALLED_BACKEND_PATH = os.path.join(PROJECT_ROOT, ".llama_installed_backend.json")
BROKEN_BACKENDS_PATH = os.path.join(PROJECT_ROOT, ".llama_broken_backends.json")


def mark_backend_broken(backend: str):
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


def check_package_integrity() -> dict:
    target = os.path.join(SITE_PACKAGES, "llama_cpp")
    if not os.path.isdir(target):
        return {"present": False, "complete": False, "missing": list(_REQUIRED_PACKAGE_FILES)}
    missing = [f for f in _REQUIRED_PACKAGE_FILES if not os.path.isfile(os.path.join(target, f))]
    return {"present": True, "complete": not missing, "missing": missing}


def llama_cpp_status() -> dict:
    integrity = check_package_integrity()
    if integrity["present"] and not integrity["complete"]:
        missing_str = ", ".join(integrity["missing"])
        return {
            "installed": False, "path": None,
            "error": f"пакет установлен не полностью — отсутствуют файлы: {missing_str} "
                     f"(похоже, установка была прервана; нужно удалить и поставить заново)",
        }

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


def _cuda_index_from_version(cuda_version: str) -> str:
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
    vendor = (gpu_info or {}).get("vendor", "unknown")
    cuda_version = (gpu_info or {}).get("cuda_version")
    broken = get_broken_backends()

    if vendor == "nvidia" and cuda_version:
        index = _cuda_index_from_version(cuda_version)
        if index and "cuda" not in broken:
            return ("cuda", f"https://abetlen.github.io/llama-cpp-python/whl/{index}")

    if vendor in ("amd", "intel") and "vulkan" not in broken:
        return ("vulkan", "https://abetlen.github.io/llama-cpp-python/whl/vulkan")

    return ("cpu", "")


def _build_install_cmd(backend: str, extra_index: str, site_packages: str) -> list:
    cmd = [
        PYTHON_EXE, "-m", "pip", "install", "llama-cpp-python",
        "--no-deps", "--target", site_packages,
        "--upgrade",
    ]
    if backend in ("cuda", "vulkan"):
        cmd.extend(["--extra-index-url", extra_index, "--prefer-binary"])
    elif backend == "cpu":
        cmd.append("-v")
    return cmd


def _find_any_local_model() -> Optional[str]:
    models_dir = os.path.join(PROJECT_ROOT, "models")
    if not os.path.isdir(models_dir):
        return None
    for name in sorted(os.listdir(models_dir)):
        if name.lower().endswith(".gguf"):
            return os.path.join(models_dir, name)
    return None


def smoke_test_gpu_init(backend: str, model_path: str = None, timeout: float = 60.0) -> dict:
    if backend == "cpu":
        return {"ok": True, "skipped": False, "error": None}

    if not model_path:
        model_path = _find_any_local_model()
    elif not os.path.isfile(model_path):
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
    if not os.path.isdir(SITE_PACKAGES):
        return
    for name in os.listdir(SITE_PACKAGES):
        if name.startswith("llama_cpp"):
            full = os.path.join(SITE_PACKAGES, name)
            shutil.rmtree(full, ignore_errors=True) if os.path.isdir(full) else \
                (os.remove(full) if os.path.isfile(full) else None)
    for name in ("bin", "include", "lib"):
        full = os.path.join(SITE_PACKAGES, name)
        if os.path.isdir(full):
            try:
                if any(f.lower().startswith(("ggml", "llama")) for f in os.listdir(full)):
                    shutil.rmtree(full, ignore_errors=True)
            except Exception:
                pass


def get_startup_install_state() -> dict:
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

    from engine.env_core.diagnostics import get_install_activity_status
    activity = get_install_activity_status()
    return {
        "state": "interrupted",
        "stage": stage,
        "age_seconds": age,
        "target_dir_files": activity["target_dir_files"],
        "meta": checkpoint.get("meta", {}),
    }


def install_llama_cpp(progress_cb=None, resume: bool = False, backend: str = None, model_path: str = None) -> dict:
    from engine.env_core.diagnostics import _read_pip_output, _install_watchdog, _extract_missing_module, _install_single_dependency
    def emit(line):
        if progress_cb:
            progress_cb(line)

    checkpoint = _load_checkpoint()
    is_resume = resume and checkpoint.get("stage") not in (None, "", "done")

    cpu = detect_cpu()
    gpu = detect_gpu()

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

    from engine.env_core.diagnostics import get_python_env_info, format_env_info
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

    os.makedirs(PORTABLE_TEMP_DIR, exist_ok=True)
    os.makedirs(PORTABLE_CACHE_DIR, exist_ok=True)
    env["TMPDIR"] = PORTABLE_TEMP_DIR
    env["TEMP"] = PORTABLE_TEMP_DIR
    env["TMP"] = PORTABLE_TEMP_DIR
    env["PIP_CACHE_DIR"] = PORTABLE_CACHE_DIR

    if backend == "cpu":
        cmake_args = build_cmake_args(cpu)
        emit(f"Отключаемые наборы инструкций: {cmake_args or '(нет — CPU поддерживает всё нужное)'}")
        if cmake_args:
            env["CMAKE_ARGS"] = cmake_args
        env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(os.cpu_count() or 4)

    cmd = _build_install_cmd(backend, extra_index, SITE_PACKAGES)
    emit(f"Команда установки: {' '.join(cmd)}")
    if not is_resume:
        cmd.append("--no-cache-dir")

    emit("Устанавливаю (это может занять несколько минут)...")
    _save_checkpoint("downloading", {"backend": backend, "cpu": cpu, "gpu": gpu})

    proc = subprocess.Popen(
        cmd, cwd=PROJECT_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        bufsize=0,
    )

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
        if backend != "cpu":
            emit(f"❌ {backend}-сборка не установилась (код {proc.returncode}). Перехожу на CPU-fallback...")
            return install_llama_cpp(progress_cb=progress_cb, resume=False, backend="cpu", model_path=model_path)
        raise RuntimeError(f"pip завершился с кодом {proc.returncode}")

    _save_checkpoint("building", {"backend": backend, "cpu": cpu, "gpu": gpu})
    emit("Проверяю импорт (в отдельном процессе)...")
    status = llama_cpp_status()

    MAX_DEP_ATTEMPTS = 6
    attempts = 0
    seen_packages = set()
    while not status["installed"] and attempts < MAX_DEP_ATTEMPTS:
        missing = _extract_missing_module(status.get("error"))
        if not missing or missing in seen_packages:
            break
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
    def emit(line):
        if progress_cb:
            progress_cb(line)

    emit("Удаляю llama-cpp-python...")
    _clean_previous_install()
    _clear_checkpoint()
    _clear_installed_backend()
    emit("✅ llama-cpp-python удалён.")
    return True
