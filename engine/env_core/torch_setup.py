# -*- coding: utf-8 -*-
"""
engine/env_core/torch_setup.py — логика установки и проверки PyTorch, Torchaudio, Torchvision.
"""
import os
import sys
import json
import subprocess
import time
from typing import Optional
from engine.env_core.cpu_gpu import detect_gpu

# Вычисляем корень проекта динамически
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_CORE_DIR))

PYTHON_EXE = sys.executable
SITE_PACKAGES = os.path.join(PROJECT_ROOT, "python", "xtts_env", "Lib", "site-packages")
PORTABLE_TEMP_DIR = os.path.join(PROJECT_ROOT, "python", "temp")
PORTABLE_CACHE_DIR = os.path.join(PROJECT_ROOT, "python", "pip_cache")

TORCH_VERSION = "2.2.2"
TORCHAUDIO_VERSION = "2.2.2"
TORCHVISION_VERSION = "0.17.2"

TORCH_MIN_CUDA = (11, 8)

_TORCH_INDEX_URLS = {
    "cu118": "https://download.pytorch.org/whl/cu118",
    "cpu": "https://download.pytorch.org/whl/cpu",
}

TORCH_CHECKPOINT_PATH = os.path.join(PROJECT_ROOT, ".torch_install_checkpoint.json")
TORCH_INSTALLED_VARIANT_PATH = os.path.join(PROJECT_ROOT, ".torch_installed_variant.json")
TORCH_BROKEN_VARIANTS_PATH = os.path.join(PROJECT_ROOT, ".torch_broken_variants.json")

active_proc = None


def mark_torch_variant_broken(variant: str):
    broken = get_broken_torch_variants()
    broken.add(variant)
    try:
        with open(TORCH_BROKEN_VARIANTS_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(broken), f)
    except Exception:
        pass


def get_broken_torch_variants() -> set:
    try:
        with open(TORCH_BROKEN_VARIANTS_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_installed_torch_variant(variant: str):
    try:
        with open(TORCH_INSTALLED_VARIANT_PATH, "w", encoding="utf-8") as f:
            json.dump({"variant": variant, "timestamp": time.time()}, f)
    except Exception:
        pass


def _clear_installed_torch_variant():
    try:
        if os.path.exists(TORCH_INSTALLED_VARIANT_PATH):
            os.remove(TORCH_INSTALLED_VARIANT_PATH)
    except Exception:
        pass


def get_installed_torch_variant() -> Optional[str]:
    try:
        with open(TORCH_INSTALLED_VARIANT_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("variant")
    except Exception:
        return None


def load_torch_checkpoint() -> dict:
    try:
        with open(TORCH_CHECKPOINT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_torch_checkpoint(stage: str, meta: dict = None):
    data = {"stage": stage, "timestamp": time.time(), "meta": meta or {}}
    try:
        with open(TORCH_CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def clear_torch_checkpoint():
    try:
        if os.path.exists(TORCH_CHECKPOINT_PATH):
            os.remove(TORCH_CHECKPOINT_PATH)
    except Exception:
        pass


def _parse_cuda_version(cuda_version: str):
    if not cuda_version:
        return None
    try:
        parts = cuda_version.strip().split(".")
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    except Exception:
        return None


def _pick_torch_variant(gpu_info: dict) -> tuple:
    try:
        from engine.settings_store import load_settings
        pref = load_settings().get("torch_device_preference")
        if pref == "cpu":
            return ("cpu", _TORCH_INDEX_URLS["cpu"])
        elif pref == "gpu":
            broken = get_broken_torch_variants()
            if "cu118" not in broken:
                return ("cu118", _TORCH_INDEX_URLS["cu118"])
    except Exception:
        pass

    vendor = (gpu_info or {}).get("vendor", "unknown")
    cuda_version = (gpu_info or {}).get("cuda_version")
    broken = get_broken_torch_variants()

    if vendor == "nvidia" and cuda_version:
        parsed = _parse_cuda_version(cuda_version)
        if parsed and parsed >= TORCH_MIN_CUDA and "cu118" not in broken:
            return ("cu118", _TORCH_INDEX_URLS["cu118"])

    return ("cpu", _TORCH_INDEX_URLS["cpu"])


def _clean_previous_torch_install(progress_cb=None) -> list:
    """
    Удаляет папки предыдущей установки torch/torchaudio/torchvision/
    functorch/triton/nvidia_* из site-packages.

    Возвращает список путей, которые не удалось удалить (например,
    залоченные .pyd/.dll живым процессом). Раньше такие сбои проглатывались
    полностью молча: shutil.rmtree(..., ignore_errors=True) не поднимает
    исключение вообще, поэтому внешний try/except ничего не ловил —
    частично удалённая папка потом ломала последующую pip-установку с
    трудноотличимой на первый взгляд ошибкой (WinError 5 внутри
    _handle_target_dir, уже на стороне pip, а не здесь).
    """
    import shutil
    failed = []
    if not os.path.isdir(SITE_PACKAGES):
        return failed
    prefixes = ("torch", "functorch", "triton", "nvidia_")
    for name in os.listdir(SITE_PACKAGES):
        if name.lower().startswith(prefixes):
            full = os.path.join(SITE_PACKAGES, name)
            try:
                if os.path.isdir(full):
                    shutil.rmtree(full)
                elif os.path.isfile(full):
                    os.remove(full)
            except Exception as e:
                failed.append(name)
                if progress_cb:
                    progress_cb(f"⚠️ Не удалось удалить {name} (вероятно, залочен запущенным процессом): {e}")
    return failed


def _build_torch_install_cmd(index_url: str, site_packages: str) -> list:
    return [
        PYTHON_EXE, "-m", "pip", "install",
        f"torch=={TORCH_VERSION}",
        f"torchaudio=={TORCHAUDIO_VERSION}",
        f"torchvision=={TORCHVISION_VERSION}",
        "--index-url", index_url,
        "--target", site_packages,
        "--upgrade",
        "--no-deps",
    ]


def torch_status() -> dict:
    probe_script = """import sys
try:
    import torch
    print('OK=' + torch.__file__)
    print('VERSION=' + torch.__version__)
    try:
        print('CUDA_AVAILABLE=' + str(torch.cuda.is_available()))
    except Exception as e:
        print('CUDA_AVAILABLE=ERROR:' + str(e))
except ImportError as e:
    print('FAIL=' + str(e))
"""
    probes = [
        ("import sys; sys.path.insert(0, r'%s')\n" % SITE_PACKAGES) + probe_script,
        probe_script,
    ]
    last_error = ""
    for probe in probes:
        try:
            proc = subprocess.run(
                [PYTHON_EXE, "-c", probe],
                capture_output=True, text=True, timeout=30,
            )
            out = proc.stdout or ""
            if "OK=" in out:
                fields = dict(
                    line.split("=", 1) for line in out.strip().splitlines() if "=" in line
                )
                return {
                    "installed": True,
                    "path": fields.get("OK"),
                    "version": fields.get("VERSION"),
                    "cuda_available": fields.get("CUDA_AVAILABLE", "").strip() == "True",
                    "error": None,
                }
            err = (proc.stderr or "").strip()
            if proc.returncode < 0:
                err = f"процесс завершён аварийно (код {proc.returncode}) — {err}"
            last_error = err or out.strip() or f"exit code {proc.returncode}"
        except subprocess.TimeoutExpired:
            last_error = "проверка не уложилась в таймаут"
        except Exception as e:
            last_error = str(e)
    return {"installed": False, "path": None, "version": None, "cuda_available": False, "error": last_error}


def install_torch(progress_cb=None, resume: bool = False, variant: str = None) -> dict:
    from engine.env_core.diagnostics import _read_pip_output
    # Импортируем функции лока установки для предотвращения одновременных установок
    try:
        from engine.gui.env_settings import _acquire_install_lock, _release_install_lock, _get_current_install_type
    except ImportError:
        def _acquire_install_lock(install_type): return True
        def _release_install_lock(): pass
        def _get_current_install_type(): return "unknown"
    
    def emit(line):
        if progress_cb:
            progress_cb(line)

    # ── ЛОК УСТАНОВКИ: предотвращаем одновременные pip install ──
    install_type = f"torch:{variant or 'auto'}"
    if not _acquire_install_lock(install_type):
        emit(f"❌ Уже выполняется другая установка ({_get_current_install_type()}). Дождитесь её завершения.")
        raise RuntimeError(f"Установка отменена: уже выполняется {_get_current_install_type()}")

    checkpoint = load_torch_checkpoint()
    is_resume = resume and checkpoint.get("stage") not in (None, "", "done")

    gpu = detect_gpu()

    if variant == "cu118" and gpu.get("vendor") != "nvidia":
        emit("⚠️ Внимание: затребована установка GPU-версии (CUDA), но ваша видеокарта не является NVIDIA.")
        emit("Установка CUDA невозможна. Принудительно переключаюсь на стабильный вариант: CPU.")
        variant = "cpu"
        index_url = _TORCH_INDEX_URLS["cpu"]

    if is_resume:
        variant = checkpoint.get("meta", {}).get("variant") or variant or "cpu"
    if variant is None:
        variant, index_url = _pick_torch_variant(gpu)
    else:
        index_url = _TORCH_INDEX_URLS.get(variant, _TORCH_INDEX_URLS["cpu"])

    if gpu.get("vendor") != "unknown":
        emit(f"GPU: {gpu.get('vendor', 'unknown').upper()} {gpu.get('name', '')} "
             f"(CUDA драйвера: {gpu.get('cuda_version') or '?'})")
    emit(f"Вариант torch: {variant} (index: {index_url})")

    if is_resume:
        stage = checkpoint.get("stage", "unknown")
        emit(f"Продолжаю прерванную установку torch (этап: {stage}, вариант: {variant})...")
    else:
        emit("Удаляю предыдущую установку torch/torchaudio/torchvision (если была)...")
        clean_failed = _clean_previous_torch_install(progress_cb=progress_cb)
        if clean_failed:
            emit(f"⚠️ Не удалось удалить {len(clean_failed)} элемент(ов) предыдущей установки "
                 f"(вероятно, залочены запущенным приложением): {', '.join(clean_failed)}. "
                 f"Установка продолжится — retry без --upgrade ниже подстрахует, если pip споткнётся об это же.")
        save_torch_checkpoint("cleaned", {"variant": variant, "gpu": gpu})

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    os.makedirs(PORTABLE_TEMP_DIR, exist_ok=True)
    os.makedirs(PORTABLE_CACHE_DIR, exist_ok=True)
    env["TMPDIR"] = PORTABLE_TEMP_DIR
    env["TEMP"] = PORTABLE_TEMP_DIR
    env["TMP"] = PORTABLE_TEMP_DIR
    env["PIP_CACHE_DIR"] = PORTABLE_CACHE_DIR

    cmd = _build_torch_install_cmd(index_url, SITE_PACKAGES)
    emit(f"Команда установки: {' '.join(cmd)}")

    emit("Устанавливаю torch/torchaudio/torchvision (это может занять несколько минут)...")
    save_torch_checkpoint("downloading", {"variant": variant, "gpu": gpu})

    global active_proc

    def _run(cmd_to_run):
        """Запускает pip, стримит вывод в progress_cb и возвращает (код, полный_текст)."""
        buf = []
        def _cb(line):
            buf.append(line)
            if progress_cb:
                progress_cb(line)
        global active_proc
        proc = subprocess.Popen(
            cmd_to_run, cwd=PROJECT_ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE, bufsize=0,
        )
        active_proc = proc
        try:
            _read_pip_output(proc, _cb)
            proc.wait()
        finally:
            active_proc = None
        return proc.returncode, "\n".join(buf)

    returncode, output = _run(cmd)

    # Залоченные .pyd/.dll живым процессом (Windows) — pip падает при
    # --upgrade на этапе перемещения файлов в --target (_handle_target_dir
    # → shutil.rmtree старой версии). Повторяем без --upgrade: раз нужная
    # версия уже фактически стоит, pip просто пропустит пакет и не тронет
    # залоченные файлы — тот же приём, что и в rvc_setup._install_with_retry.
    if returncode != 0 and (
        "PermissionError" in output
        or "WinError 5" in output
        or "Access is denied" in output
        or "Отказано" in output
    ):
        emit("⚠️ pip не смог перезаписать залоченные файлы (процесс запущен). "
             "Повторяю без --upgrade — уже стоящий пакет будет пропущен.")
        cmd_retry = [c for c in cmd if c != "--upgrade"]
        returncode, output = _run(cmd_retry)

    if returncode != 0:
        save_torch_checkpoint("failed", {"returncode": returncode, "variant": variant})
        if variant != "cpu":
            emit(f"❌ Установка torch ({variant}) не удалась (код {returncode}). Перехожу на CPU-fallback...")
            _release_install_lock()
            return install_torch(progress_cb=progress_cb, resume=False, variant="cpu")
        _release_install_lock()
        raise RuntimeError(f"pip завершился с кодом {returncode}")

    save_torch_checkpoint("verifying", {"variant": variant, "gpu": gpu})
    emit("Проверяю импорт torch (в отдельном процессе)...")
    status = torch_status()

    if not status["installed"]:
        save_torch_checkpoint("failed", {"error": status.get("error"), "variant": variant})
        if variant != "cpu":
            emit(f"❌ torch ({variant}) установился, но не импортируется. Перехожу на CPU-fallback...")
            mark_torch_variant_broken(variant)
            _release_install_lock()
            return install_torch(progress_cb=progress_cb, resume=False, variant="cpu")
        _release_install_lock()
        raise RuntimeError(f"Установка прошла, но импорт torch не удался: {status['error']}")

    if variant != "cpu" and not status.get("cuda_available"):
        emit(f"⚠️ torch ({variant}) импортировался, но torch.cuda.is_available() == False. "
             f"Перехожу на CPU-вариант...")
        mark_torch_variant_broken(variant)
        clear_torch_checkpoint()
        _release_install_lock()
        return install_torch(progress_cb=progress_cb, resume=False, variant="cpu")

    clear_torch_checkpoint()
    _save_installed_torch_variant(variant)
    variant_msg = {"cu118": "NVIDIA CUDA 11.8", "cpu": "CPU"}.get(variant, variant)
    emit(f"✅ Готово — torch ({variant_msg}) установлен и работает.")
    _release_install_lock()
    return status


def uninstall_torch(progress_cb=None) -> bool:
    def emit(line):
        if progress_cb:
            progress_cb(line)

    emit("Удаляю torch/torchaudio/torchvision...")
    clean_failed = _clean_previous_torch_install(progress_cb=progress_cb)
    clear_torch_checkpoint()
    _clear_installed_torch_variant()
    if clean_failed:
        emit(f"⚠️ Не удалось удалить: {', '.join(clean_failed)} — вероятно, залочены "
             f"запущенным приложением. Закройте приложение и повторите удаление.")
        return False
    emit("✅ torch удалён.")
    return True

def cancel_install_torch() -> bool:
    global active_proc
    # Также освобождаем лок установки, если он был захвачен
    try:
        from engine.gui.env_settings import _release_install_lock, _set_install_cancelled
        _set_install_cancelled()
        _release_install_lock()
    except ImportError:
        pass
    
    global active_proc
    if active_proc is not None:
        try:
            active_proc.terminate()
            active_proc.kill()
            print("[Torch Setup] Установка принудительно остановлена пользователем.")
            return True
        except Exception as e:
            print(f"[Torch Setup] Ошибка при остановке процесса: {e}")
    return False

def clean_torch_cache() -> bool:
    import shutil
    cleaned = False
    for path in (PORTABLE_TEMP_DIR, PORTABLE_CACHE_DIR):
        if os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
                cleaned = True
                print(f"[Torch Setup] Очищен путь: {path}")
            except Exception as e:
                print(f"[Torch Setup] Ошибка при очистке {path}: {e}")
    clear_torch_checkpoint()
    return cleaned
