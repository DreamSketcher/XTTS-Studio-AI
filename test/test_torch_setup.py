import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine.env_core.torch_setup as ts


class TestParseCudaVersion:
    def test_valid(self):
        assert ts._parse_cuda_version("12.8") == (12, 8)
        assert ts._parse_cuda_version("11.8") == (11, 8)
        assert ts._parse_cuda_version("11") == (11, 0)

    def test_invalid(self):
        assert ts._parse_cuda_version("") is None
        assert ts._parse_cuda_version(None) is None
        assert ts._parse_cuda_version("invalid") is None


class TestPickTorchVariant:
    def test_pref_cpu(self, monkeypatch):
        monkeypatch.setattr(
            "engine.settings_store.load_settings", lambda: {"torch_device_preference": "cpu"}
        )
        gpu_info = {"vendor": "nvidia", "cuda_version": "12.8"}
        variant, url = ts._pick_torch_variant(gpu_info)
        assert variant == "cpu"

    def test_pref_gpu_not_broken(self, monkeypatch):
        monkeypatch.setattr(
            "engine.settings_store.load_settings", lambda: {"torch_device_preference": "gpu"}
        )
        monkeypatch.setattr(ts, "get_broken_torch_variants", lambda: set())
        gpu_info = {"vendor": "nvidia", "cuda_version": "12.8"}
        variant, url = ts._pick_torch_variant(gpu_info)
        assert variant == "cu128"

    def test_pref_gpu_broken(self, monkeypatch):
        monkeypatch.setattr(
            "engine.settings_store.load_settings", lambda: {"torch_device_preference": "gpu"}
        )
        monkeypatch.setattr(ts, "get_broken_torch_variants", lambda: {"cu128"})
        gpu_info = {"vendor": "nvidia", "cuda_version": "12.8"}
        # если cu128 сломан, но pref gpu, код всё равно вернёт cu128? В _pick_torch_variant проверяет broken только для pref gpu?
        # Давайте проверим логику: if pref=="gpu" and "cu128" not in broken -> cu128 else?
        # В коде: if pref=="gpu" and "cu128" not in broken: return cu128
        # Если broken содержит cu128, то падает в общий путь ниже, который тоже проверяет broken
        variant, url = ts._pick_torch_variant(gpu_info)
        # так как broken содержит cu128, должен вернуть cpu
        assert variant == "cpu"

    def test_nvidia_cuda_ok(self, monkeypatch):
        monkeypatch.setattr("engine.settings_store.load_settings", lambda: {})
        monkeypatch.setattr(ts, "get_broken_torch_variants", lambda: set())
        gpu_info = {"vendor": "nvidia", "cuda_version": "12.8"}
        variant, url = ts._pick_torch_variant(gpu_info)
        assert variant == "cu128"

    def test_nvidia_old_cuda(self, monkeypatch):
        monkeypatch.setattr("engine.settings_store.load_settings", lambda: {})
        monkeypatch.setattr(ts, "get_broken_torch_variants", lambda: set())
        gpu_info = {"vendor": "nvidia", "cuda_version": "10.1"}
        variant, url = ts._pick_torch_variant(gpu_info)
        assert variant == "cpu"  # т.к. < TORCH_MIN_CUDA (12,8)

    def test_amd_returns_cpu(self, monkeypatch):
        monkeypatch.setattr("engine.settings_store.load_settings", lambda: {})
        monkeypatch.setattr(ts, "get_broken_torch_variants", lambda: set())
        gpu_info = {"vendor": "amd", "cuda_version": None}
        variant, url = ts._pick_torch_variant(gpu_info)
        assert variant == "cpu"


class TestCheckpoint:
    def test_save_load_clear(self, tmp_path, monkeypatch):
        ckpt_path = tmp_path / "ckpt.json"
        monkeypatch.setattr(ts, "TORCH_CHECKPOINT_PATH", str(ckpt_path))

        ts.save_torch_checkpoint("downloading", {"variant": "cu128"})
        data = ts.load_torch_checkpoint()
        assert data["stage"] == "downloading"
        assert data["meta"]["variant"] == "cu128"

        ts.clear_torch_checkpoint()
        assert not ckpt_path.exists()
        assert ts.load_torch_checkpoint() == {}

    def test_broken_variants(self, tmp_path, monkeypatch):
        broken_path = tmp_path / "broken.json"
        monkeypatch.setattr(ts, "TORCH_BROKEN_VARIANTS_PATH", str(broken_path))

        assert ts.get_broken_torch_variants() == set()
        ts.mark_torch_variant_broken("cu128")
        assert "cu128" in ts.get_broken_torch_variants()

    def test_installed_variant(self, tmp_path, monkeypatch):
        inst_path = tmp_path / "installed.json"
        monkeypatch.setattr(ts, "TORCH_INSTALLED_VARIANT_PATH", str(inst_path))

        assert ts.get_installed_torch_variant() is None
        ts._save_installed_torch_variant("cpu")
        assert ts.get_installed_torch_variant() == "cpu"
        ts._clear_installed_torch_variant()
        assert not inst_path.exists()


class TestBuildCmd:
    def test_build_cmd(self, tmp_path):
        cmd = ts._build_torch_install_cmd("https://download.pytorch.org/whl/cpu", str(tmp_path))
        assert f"torch=={ts.TORCH_VERSION}" in cmd
        assert f"torchaudio=={ts.TORCHAUDIO_VERSION}" in cmd
        assert "--index-url" in cmd
        assert "--target" in cmd

    def test_clean_previous(self, tmp_path, monkeypatch):
        site = tmp_path / "site"
        site.mkdir()
        (site / "torch").mkdir()
        (site / "torchvision").mkdir()
        (site / "other").mkdir()
        monkeypatch.setattr(ts, "SITE_PACKAGES", str(site))

        failed = ts._clean_previous_torch_install()
        assert not (site / "torch").exists()
        assert not (site / "torchvision").exists()
        assert (site / "other").exists()
        assert failed == []


class TestTorchStatus:
    def test_status_installed(self, monkeypatch):
        script_output = "OK=/fake/torch/__init__.py\nVERSION=2.11.0+cpu\nCUDA_AVAILABLE=False\n"

        def fake_run(*a, **kw):
            return MagicMock(returncode=0, stdout=script_output, stderr="")

        monkeypatch.setattr(ts.subprocess, "run", fake_run)

        status = ts.torch_status()
        assert status["installed"] is True
        assert status["version"] == "2.11.0+cpu"
        assert status["cuda_available"] is False

    def test_status_not_installed(self, monkeypatch):
        def fake_run(*a, **kw):
            return MagicMock(returncode=1, stdout="", stderr="No module named torch")

        monkeypatch.setattr(ts.subprocess, "run", fake_run)

        status = ts.torch_status()
        assert status["installed"] is False
