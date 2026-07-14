import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine.env_core.rvc_setup as rvc


@pytest.fixture
def tmp_env(tmp_path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir()
    site = base / "site"
    site.mkdir()
    temp_dir = base / "temp"
    cache_dir = base / "pip_cache"

    monkeypatch.setattr(rvc, "BASE_DIR", str(base))
    monkeypatch.setattr(rvc, "SITE_PACKAGES", str(site))
    monkeypatch.setattr(rvc, "PORTABLE_TEMP_DIR", str(temp_dir))
    monkeypatch.setattr(rvc, "PORTABLE_CACHE_DIR", str(cache_dir))

    yield {"base": base, "site": site}


class TestBuildConstraints:
    def test_build_with_installed(self, tmp_env, monkeypatch):
        # мок importlib.metadata.version
        def fake_version(name):
            if name.lower() == "torch":
                return "2.2.2+cu118"
            if name.lower() == "numpy":
                return "1.26.4"
            raise Exception("not installed")

        monkeypatch.setattr("importlib.metadata.version", fake_version)

        frozen = {
            "torch": "torch==2.2.2",
            "numpy": "numpy==1.26.4",
            "unknown_pkg": "unknown_pkg==1.0.0",
        }
        lines = rvc._build_rvc_constraints(frozen, tmp_env["site"])
        assert any("torch==2.2.2+cu118" in l for l in lines)
        assert any("numpy==1.26.4" in l for l in lines)
        # unknown остается как в requirements
        assert any("unknown_pkg==1.0.0" in l for l in lines)


class TestDetectTorchVariant:
    def test_from_metadata(self, tmp_env, monkeypatch):
        def fake_version(name):
            if name == "torch":
                return "2.2.2+cu118"
            raise Exception()

        monkeypatch.setattr("importlib.metadata.version", fake_version)

        variant = rvc._detect_installed_torch_variant(tmp_env["site"])
        assert variant == "cu118"

        def fake_version_cpu(name):
            if name == "torch":
                return "2.2.2+cpu"
            raise Exception()

        monkeypatch.setattr("importlib.metadata.version", fake_version_cpu)
        variant2 = rvc._detect_installed_torch_variant(tmp_env["site"])
        assert variant2 == "cpu"

    def test_not_installed(self, tmp_env, monkeypatch):
        monkeypatch.setattr(
            "importlib.metadata.version", lambda x: (_ for _ in ()).throw(Exception())
        )
        assert rvc._detect_installed_torch_variant(tmp_env["site"]) is None


class TestFallbackCuda:
    def test_nvidia_smi_ok(self, monkeypatch):
        def fake_run(*a, **kw):
            return MagicMock(returncode=0)

        monkeypatch.setattr(rvc.subprocess, "run", fake_run)
        assert rvc._fallback_cuda_available() is True

    def test_no_cuda(self, monkeypatch):
        def fake_run(*a, **kw):
            raise FileNotFoundError()

        monkeypatch.setattr(rvc.subprocess, "run", fake_run)
        assert rvc._fallback_cuda_available() is False


class TestDetectTorchBuild:
    def test_installed(self, tmp_env, monkeypatch):
        monkeypatch.setattr(rvc, "_detect_installed_torch_variant", lambda sp: "cu118")
        variant, url = rvc.detect_torch_build(tmp_env["site"])
        assert variant == "cu118"
        assert "cu118" in url

    def test_not_installed_fallback_cpu(self, tmp_env, monkeypatch):
        monkeypatch.setattr(rvc, "_detect_installed_torch_variant", lambda sp: None)
        # мок _pick_torch_variant
        monkeypatch.setattr(
            "engine.env_core.torch_setup._pick_torch_variant",
            lambda gpu: ("cpu", "https://download.pytorch.org/whl/cpu"),
        )
        monkeypatch.setattr("engine.env_core.cpu_gpu.detect_gpu", lambda: {"vendor": "unknown"})

        variant, url = rvc.detect_torch_build(tmp_env["site"])
        assert variant == "cpu"


class TestReadRequiresDist:
    def test_read(self, tmp_env):
        site = Path(tmp_env["site"])
        dist_info = site / "somepackage-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(
            'Name: somepackage\nRequires-Dist: numpy>=1.0\nRequires-Dist: torch==2.2.2; extra == "dev"\nRequires-Dist: librosa\n',
            encoding="utf-8",
        )

        deps = rvc._read_requires_dist("somepackage")
        assert "numpy>=1.0" in deps
        assert "librosa" in deps
        # extra == dev должен быть пропущен
        assert not any("extra ==" in d for d in deps)

    def test_no_dist(self, tmp_env):
        assert rvc._read_requires_dist("nonexistent") == []


class TestRunPipCapture:
    def test_capture(self, tmp_env, monkeypatch):
        # мок Popen и _read_pip_output
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0

        def fake_popen(*a, **kw):
            return mock_proc

        monkeypatch.setattr(rvc.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(
            "engine.env_core.diagnostics._read_pip_output",
            lambda proc, cb: cb("line1") if cb else None,
        )

        rc, output = rvc._run_pip_capture(["pip", "install"], {}, progress_cb=lambda x: None)
        assert rc == 0
        assert "line1" in output


class TestInstallWithRetry:
    def test_retry_on_permission_error(self, tmp_env, monkeypatch):
        calls = {"count": 0}

        def fake_capture(cmd, env, progress_cb=None):
            calls["count"] += 1
            if calls["count"] == 1:
                return 1, "PermissionError: WinError 5"
            return 0, "ok"

        monkeypatch.setattr(rvc, "_run_pip_capture", fake_capture)

        rc, out = rvc._install_with_retry(["pip", "install", "--upgrade", "pkg"], {})
        assert rc == 0
        assert calls["count"] == 2

    def test_no_retry_on_other_error(self, tmp_env, monkeypatch):
        monkeypatch.setattr(rvc, "_run_pip_capture", lambda *a, **kw: (1, "other error"))

        rc, out = rvc._install_with_retry(["pip", "install", "pkg"], {})
        assert rc == 1


class TestRvcStatus:
    def test_installed(self, monkeypatch):
        def fake_run(*a, **kw):
            return MagicMock(returncode=0, stdout="OK", stderr="")

        monkeypatch.setattr(rvc.subprocess, "run", fake_run)

        status = rvc.rvc_status()
        assert status["installed"] is True

    def test_not_installed(self, monkeypatch):
        def fake_run(*a, **kw):
            return MagicMock(returncode=1, stdout="FAIL=No module", stderr="")

        monkeypatch.setattr(rvc.subprocess, "run", fake_run)

        status = rvc.rvc_status()
        assert status["installed"] is False
