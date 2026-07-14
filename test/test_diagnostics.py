import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine.env_core.diagnostics as diag


@pytest.fixture
def tmp_base(tmp_path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir()
    site = base / "site"
    site.mkdir()
    # патчим пути
    monkeypatch.setattr(diag, "PROJECT_ROOT", str(base))
    monkeypatch.setattr(diag, "SITE_PACKAGES", str(site))
    monkeypatch.setattr(diag, "SAFE_FILES_CACHE_PATH", str(base / ".known_safe_files.json"))
    monkeypatch.setattr(diag, "DIAG_CACHE_PATH", str(base / ".env_diagnostics_cache.json"))
    monkeypatch.setattr(diag, "QUARANTINE_DIR", str(base / "Quarantine"))
    monkeypatch.setattr(diag, "PORTABLE_TEMP_DIR", str(base / "temp"))
    monkeypatch.setattr(diag, "PORTABLE_CACHE_DIR", str(base / "pip_cache"))
    yield base


class TestBrokenCritical:
    def test_broken(self):
        results = {
            "numpy": True,
            "torch": "error",
            "tts": "SKIPPED: ожидает починки numpy",
            "llama_cpp": "error",  # optional
            "rvc_python": "error",  # optional
            "soundfile": True,
        }
        broken = diag.get_broken_critical(results)
        assert "torch" in broken
        assert "tts" not in broken  # SKIPPED
        assert "llama_cpp" not in broken  # optional
        assert "numpy" not in broken

    def test_optional_status(self):
        results = {
            "llama_cpp": True,
            "rvc_python": "No module named rvc_python",
        }
        status = diag.get_optional_status(results)
        assert status["llama_cpp"] == "ok"
        assert status["rvc_python"] == "not_installed"

        results2 = {"llama_cpp": "some import error"}
        status2 = diag.get_optional_status(results2)
        assert status2["llama_cpp"] == "broken"


class TestCache:
    def test_save_load(self, tmp_base):
        data = {"safe_files": {"a": {"size": 1}}, "unsafe_files": {}, "deleted_files": []}
        diag.save_safe_files_cache(data)
        loaded = diag.load_safe_files_cache()
        assert loaded["safe_files"]["a"]["size"] == 1

    def test_load_old_cache_missing_deleted(self, tmp_base):
        # старый кэш без deleted_files
        old = {"safe_files": {}, "unsafe_files": {}}
        (tmp_base / ".known_safe_files.json").write_text(json.dumps(old), encoding="utf-8")
        loaded = diag.load_safe_files_cache()
        assert "deleted_files" in loaded
        assert isinstance(loaded["deleted_files"], list)

    def test_clear_cache(self, tmp_base):
        (tmp_base / ".env_diagnostics_cache.json").write_text("{}", encoding="utf-8")
        assert diag.clear_diagnostics_cache() is True
        assert not (tmp_base / ".env_diagnostics_cache.json").exists()


class TestParseRequirements:
    def test_parse(self, tmp_base):
        (tmp_base / "requirements.txt").write_text(
            "numpy==1.26.4\ntorch==2.2.2\n# comment\n", encoding="utf-8"
        )
        reqs = diag.parse_requirements_txt()
        assert "numpy" in reqs
        assert "torch" in reqs
        assert reqs["numpy"] == "numpy==1.26.4"


class TestExtractMissing:
    def test_extract(self):
        assert diag._extract_missing_module("No module named 'yaml'") == "PyYAML"
        assert diag._extract_missing_module("No module named 'PIL'") == "Pillow"
        assert diag._extract_missing_module("No module named 'mymodule'") == "mymodule"
        assert diag._extract_missing_module("Some other error") is None


class TestPipOutput:
    def test_read_output(self):
        # мокаем proc.stdout.read
        mock_proc = MagicMock()
        # эмулируем байтовый стрим "line1\nline2\n"
        data = b"line1\nline2\n"
        mock_proc.stdout.read = MagicMock(side_effect=[bytes([b]) for b in data] + [b""])

        lines = []

        def cb(line):
            lines.append(line)

        diag._read_pip_output(mock_proc, cb)
        assert len(lines) >= 2


class TestDetectTorchSuffix:
    def test_detect_cu118(self, tmp_base):
        site = Path(tmp_base) / "site"
        dist_info = site / "torch-2.2.2+cu118.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text("Name: torch\nVersion: 2.2.2+cu118\n", encoding="utf-8")

        # патчим SITE_PACKAGES уже через fixture
        suffix = diag._detect_installed_torch_suffix()
        assert suffix == "cu118"

    def test_detect_cpu(self, tmp_base):
        site = Path(tmp_base) / "site"
        # очистим предыдущие
        for f in site.iterdir():
            if f.is_dir():
                import shutil

                shutil.rmtree(f)
        dist_info = site / "torch-2.2.2+cpu.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text("Name: torch\nVersion: 2.2.2+cpu\n", encoding="utf-8")

        suffix = diag._detect_installed_torch_suffix()
        assert suffix == "cpu"

    def test_no_torch(self, tmp_base):
        site = Path(tmp_base) / "site"
        for f in site.iterdir():
            if f.is_dir():
                import shutil

                shutil.rmtree(f)
        assert diag._detect_installed_torch_suffix() is None


class TestAvCompat:
    def test_torchvision_error_is_av_related(self):
        assert (
            diag._torchvision_error_is_av_related("module 'av' has no attribute 'logging'") is True
        )
        assert diag._torchvision_error_is_av_related("av.logging error") is True
        assert diag._torchvision_error_is_av_related("some other error") is False
        assert diag._torchvision_error_is_av_related(None) is False

    def test_get_av_pin(self, tmp_base, monkeypatch):
        # без requirements.txt и без rvc_setup → default
        monkeypatch.setattr(diag, "parse_requirements_txt", lambda: {})
        assert diag._get_av_pin() == "av==12.3.0"

        monkeypatch.setattr(diag, "parse_requirements_txt", lambda: {"av": "av==10.0.0"})
        assert diag._get_av_pin() == "av==10.0.0"


class TestCleanDataclasses:
    def test_clean(self, tmp_base):
        site = Path(tmp_base) / "site"
        (site / "dataclasses.py").write_text("fake")
        (site / "dataclasses-0.8.dist-info").mkdir()

        removed = diag._clean_dataclasses_backport()
        assert len(removed) >= 1
        assert not (site / "dataclasses.py").exists()
