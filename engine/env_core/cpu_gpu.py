# -*- coding: utf-8 -*-
"""
engine/env_core/cpu_gpu.py — логика анализа аппаратного обеспечения (CPU и GPU).
"""
import os
import sys
import json
import subprocess
from typing import Optional

# Вычисляем корень проекта динамически, так как env_core лежит в engine/env_core/
_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_CORE_DIR))

PYTHON_EXE = sys.executable
SITE_PACKAGES = os.path.join(PROJECT_ROOT, "python", "xtts_env", "Lib", "site-packages")


def _ensure_cpuinfo() -> bool:
    """py-cpuinfo — чистый python-пакет, компиляция не нужна, ставится за секунды."""
    sys.path.insert(0, SITE_PACKAGES)
    try:
        import cpuinfo  # noqa: F401

        return True
    except ImportError:
        try:
            subprocess.run(
                [
                    PYTHON_EXE,
                    "-m",
                    "pip",
                    "install",
                    "py-cpuinfo",
                    "--no-cache-dir",
                    "--target",
                    SITE_PACKAGES,
                ],
                check=True,
                capture_output=True,
                timeout=60,
                text=True,
            )
            return True
        except Exception:
            return False


def detect_cpu() -> dict:
    """Определяет параметры CPU."""
    result = {
        "name": "не определено",
        "flags": set(),
        "avx": False,
        "avx2": False,
        "fma": False,
        "f16c": False,
    }

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


def _get_vram_gb_from_registry(name_hint: str) -> Optional[float]:
    """Считывает объем VRAM из реестра Windows (обход 32-битного лимита WMI)."""
    try:
        ps_cmd = (
            "Get-ItemProperty 'HKLM:\\SYSTEM\\ControlSet001\\Control\\Class\\"
            "{4d36e968-e325-11ce-bfc1-08002be10318}\\00*' "
            "-Name 'HardwareInformation.qwMemorySize','DriverDesc' -ErrorAction SilentlyContinue | "
            "Select-Object DriverDesc, 'HardwareInformation.qwMemorySize' | ConvertTo-Json -Compress"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=15,
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
            gb = size / (1024**3)
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
    """Определяет параметры GPU (NVIDIA / AMD / Intel)."""
    result = {"vendor": "unknown", "name": "не определено", "cuda_version": None, "vram_gb": None}

    # NVIDIA
    try:
        proc = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout:
            out = proc.stdout
            result["vendor"] = "nvidia"

            for line in out.splitlines():
                if "NVIDIA" in line and (
                    "GeForce" in line
                    or "RTX" in line
                    or "GTX" in line
                    or "Quadro" in line
                    or "Tesla" in line
                ):
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 2:
                        result["name"] = parts[1].split("  ")[0].strip()
                    break

            for line in out.splitlines():
                if "CUDA Version" in line:
                    try:
                        result["cuda_version"] = (
                            line.split("CUDA Version:")[1].strip().split()[0].rstrip("|").strip()
                        )
                    except Exception:
                        pass
                    break

            try:
                vram_proc = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if vram_proc.returncode == 0 and vram_proc.stdout.strip():
                    vram_mb = float(vram_proc.stdout.strip().splitlines()[0].strip())
                    result["vram_gb"] = round(vram_mb / 1024, 2)
            except Exception:
                pass

            return result
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # AMD / Intel через WMI
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
            ],
            capture_output=True,
            text=True,
            timeout=15,
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
                        try:
                            ram_proc = subprocess.run(
                                [
                                    "powershell",
                                    "-NoProfile",
                                    "-Command",
                                    "(Get-CimInstance Win32_VideoController | Where-Object {$_.Name -eq '%s'}).AdapterRAM"
                                    % name,
                                ],
                                capture_output=True,
                                text=True,
                                timeout=15,
                            )
                            if ram_proc.returncode == 0 and ram_proc.stdout.strip():
                                ram_bytes = int(ram_proc.stdout.strip().splitlines()[0].strip())
                                result["vram_gb"] = round(ram_bytes / (1024**3), 2)
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
                                [
                                    "powershell",
                                    "-NoProfile",
                                    "-Command",
                                    "(Get-CimInstance Win32_VideoController | Where-Object {$_.Name -eq '%s'}).AdapterRAM"
                                    % name,
                                ],
                                capture_output=True,
                                text=True,
                                timeout=15,
                            )
                            if ram_proc.returncode == 0 and ram_proc.stdout.strip():
                                ram_bytes = int(ram_proc.stdout.strip().splitlines()[0].strip())
                                result["vram_gb"] = round(ram_bytes / (1024**3), 2)
                        except Exception:
                            pass
                    return result
            if names:
                result["name"] = names[0]
    except Exception:
        pass

    return result
