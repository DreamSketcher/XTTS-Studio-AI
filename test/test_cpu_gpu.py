import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine.env_core.cpu_gpu as cg


class TestEnsureCpuinfo:
    def test_ensure_when_already_installed(self, monkeypatch):
        # мок cpuinfo импорт успешен
        fake_cpuinfo = MagicMock()
        monkeypatch.setitem(sys.modules, "cpuinfo", fake_cpuinfo)
        monkeypatch.setattr(sys, "path", ["/fake"])
        # должен вернуть True без pip install
        # _ensure_cpuinfo вставляет SITE_PACKAGES в sys.path и пробует import
        # если импорт уже есть, вернёт True
        result = cg._ensure_cpuinfo()
        assert result is True

    def test_ensure_installs_when_missing(self, monkeypatch):
        # убираем cpuinfo из sys.modules
        monkeypatch.delitem(sys.modules, "cpuinfo", raising=False)

        def fail_run(*a, **kw):
            raise Exception("pip fail")

        monkeypatch.setattr(subprocess, "run", fail_run)
        result = cg._ensure_cpuinfo()
        assert isinstance(result, bool)


class TestDetectCpu:
    def test_detect_with_cpuinfo(self, monkeypatch):
        fake_info = {
            "brand_raw": "Intel(R) Core(TM) i7",
            "flags": ["fpu", "avx", "avx2", "fma", "f16c", "sse"],
        }
        fake_cpuinfo = MagicMock()
        fake_cpuinfo.get_cpu_info.return_value = fake_info
        monkeypatch.setitem(sys.modules, "cpuinfo", fake_cpuinfo)
        monkeypatch.setattr(cg, "_ensure_cpuinfo", lambda: True)

        result = cg.detect_cpu()
        assert result["name"] == "Intel(R) Core(TM) i7"
        assert result["avx"] is True
        assert result["avx2"] is True
        assert result["fma"] is True
        assert result["f16c"] is True
        assert "avx" in result["flags"]

    def test_detect_without_cpuinfo(self, monkeypatch):
        monkeypatch.setattr(cg, "_ensure_cpuinfo", lambda: False)
        result = cg.detect_cpu()
        assert result["name"] == "не определено"
        assert result["avx"] is False


class TestDetectGpuNvidia:
    def test_nvidia_detected(self, monkeypatch):
        # упрощённый вывод, где вторая колонка после '|' — имя GPU (как парсит код: parts[1])
        nvidia_smi_output = """
|   0  | NVIDIA GeForce RTX 3060    Off  | 00000000:01:00.0 Off |
|   CUDA Version: 12.2     |
"""

        def fake_run(args, capture_output=True, text=True, timeout=10, **kw):
            cmd = args[0] if isinstance(args, list) else args
            if cmd == "nvidia-smi" and len(args) == 1:
                return MagicMock(returncode=0, stdout=nvidia_smi_output)
            if "memory.total" in str(args):
                return MagicMock(returncode=0, stdout="12288\n")
            raise FileNotFoundError()

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = cg.detect_gpu()
        assert result["vendor"] == "nvidia"
        assert "RTX 3060" in result["name"] or "GeForce" in result["name"]
        assert result["vram_gb"] == 12.0

    def test_nvidia_cuda_version_parse(self, monkeypatch):
        out = "|   CUDA Version: 11.8     |"

        def fake_run(*a, **kw):
            return MagicMock(returncode=0, stdout=out)

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = cg.detect_gpu()
        assert result["cuda_version"] == "11.8"

    def test_no_gpu_fallback_amd(self, monkeypatch):
        # nvidia-smi не найдена
        def fake_run(args, **kw):
            args_str = str(args)
            if args == ["nvidia-smi"] or (isinstance(args, list) and args[0] == "nvidia-smi"):
                raise FileNotFoundError()
            # WMI для AMD
            if "Get-CimInstance Win32_VideoController" in args_str:
                if "Select-Object -ExpandProperty Name" in args_str:
                    return MagicMock(returncode=0, stdout="AMD Radeon RX 580\n")
                if "AdapterRAM" in args_str:
                    return MagicMock(returncode=0, stdout="8589934592\n")  # 8GB
            # registry
            if "HardwareInformation" in args_str:
                return MagicMock(returncode=1, stdout="")

            return MagicMock(returncode=0, stdout="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(cg, "_get_vram_gb_from_registry", lambda hint: None)

        result = cg.detect_gpu()
        assert result["vendor"] == "amd"
        assert "Radeon" in result["name"]

    def test_get_vram_from_registry(self, monkeypatch):
        registry_json = json.dumps(
            [
                {
                    "DriverDesc": "NVIDIA GeForce RTX 3060",
                    "HardwareInformation.qwMemorySize": 12884901888,
                },
                {"DriverDesc": "Intel UHD", "HardwareInformation.qwMemorySize": 1073741824},
            ]
        )

        def fake_run(*a, **kw):
            return MagicMock(returncode=0, stdout=registry_json)

        monkeypatch.setattr(subprocess, "run", fake_run)

        gb = cg._get_vram_gb_from_registry("NVIDIA GeForce RTX 3060")
        assert gb == 12.0

        # без хинта — берёт максимальный
        gb2 = cg._get_vram_gb_from_registry("")
        assert gb2 == 12.0

    def test_detect_gpu_unknown(self, monkeypatch):
        def fail_run(*a, **kw):
            raise Exception("fail")

        monkeypatch.setattr(subprocess, "run", fail_run)

        result = cg.detect_gpu()
        assert result["vendor"] == "unknown"
