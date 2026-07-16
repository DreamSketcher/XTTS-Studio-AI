import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine.env_core.llama_setup as ls


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    base = tmp_path / "llama_test"
    base.mkdir()
    site = base / "site"
    site.mkdir()
    models = base / "models"
    models.mkdir()

    monkeypatch.setattr(ls, "PROJECT_ROOT", str(base))
    monkeypatch.setattr(ls, "SITE_PACKAGES", str(site))
    monkeypatch.setattr(ls, "CHECKPOINT_PATH", str(base / ".llama_install_checkpoint.json"))
    monkeypatch.setattr(ls, "INSTALLED_BACKEND_PATH", str(base / ".llama_installed_backend.json"))
    monkeypatch.setattr(ls, "BROKEN_BACKENDS_PATH", str(base / ".llama_broken_backends.json"))

    yield {"base": base, "site": site, "models": models}


class TestBrokenBackends:
    def test_mark_and_get(self, tmp_paths):
        assert ls.get_broken_backends() == set()
        ls.mark_backend_broken("cuda")
        assert "cuda" in ls.get_broken_backends()
        ls.mark_backend_broken("vulkan")
        assert ls.get_broken_backends() == {"cuda", "vulkan"}

    def test_installed_backend(self, tmp_paths):
        assert ls.get_installed_backend() is None
        ls._save_installed_backend("cuda")
        assert ls.get_installed_backend() == "cuda"
        ls._clear_installed_backend()
        assert ls.get_installed_backend() is None


class TestCheckpoint:
    def test_save_load_clear(self, tmp_paths):
        ls._save_checkpoint("downloading", {"backend": "cuda"})
        data = ls._load_checkpoint()
        assert data["stage"] == "downloading"
        assert data["meta"]["backend"] == "cuda"

        ls._clear_checkpoint()
        assert ls._load_checkpoint() == {}


class TestPackageIntegrity:
    def test_not_present(self, tmp_paths):
        result = ls.check_package_integrity()
        assert result["present"] is False
        assert not result["complete"]

    def test_present_incomplete(self, tmp_paths):
        site = tmp_paths["site"]
        pkg_dir = site / "llama_cpp"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        # остальные файлы отсутствуют
        result = ls.check_package_integrity()
        assert result["present"] is True
        assert result["complete"] is False
        assert len(result["missing"]) > 0

    def test_present_complete(self, tmp_paths):
        site = tmp_paths["site"]
        pkg_dir = site / "llama_cpp"
        pkg_dir.mkdir(exist_ok=True)
        for fname in ls._REQUIRED_PACKAGE_FILES:
            (pkg_dir / fname).write_text("")

        result = ls.check_package_integrity()
        assert result["present"] is True
        assert result["complete"] is True
        assert result["missing"] == []


class TestCudaIndex:
    def test_cuda_index(self):
        assert ls._cuda_index_from_version("12.2") == "cu122"
        assert ls._cuda_index_from_version("11.8") == "cu118"
        assert ls._cuda_index_from_version("") == ""
        assert ls._cuda_index_from_version(None) == ""


class TestPickBackend:
    def test_nvidia_ok(self, tmp_paths, monkeypatch):
        monkeypatch.setattr(ls, "get_broken_backends", lambda: set())
        gpu_info = {"vendor": "nvidia", "cuda_version": "12.2"}
        backend, url = ls._pick_llama_backend(gpu_info)
        assert backend == "cuda"
        assert "cu122" in url

    def test_nvidia_broken(self, tmp_paths, monkeypatch):
        monkeypatch.setattr(ls, "get_broken_backends", lambda: {"cuda"})
        gpu_info = {"vendor": "nvidia", "cuda_version": "12.2"}
        backend, url = ls._pick_llama_backend(gpu_info)
        assert backend == "cpu"

    def test_amd_vulkan(self, tmp_paths, monkeypatch):
        monkeypatch.setattr(ls, "get_broken_backends", lambda: set())
        gpu_info = {"vendor": "amd"}
        backend, url = ls._pick_llama_backend(gpu_info)
        assert backend == "vulkan"

    def test_unknown_cpu(self, tmp_paths, monkeypatch):
        monkeypatch.setattr(ls, "get_broken_backends", lambda: set())
        gpu_info = {"vendor": "unknown"}
        backend, url = ls._pick_llama_backend(gpu_info)
        assert backend == "cpu"


class TestBuildInstallCmd:
    def test_cpu(self, tmp_paths):
        cmd = ls._build_install_cmd("cpu", "", str(tmp_paths["site"]))
        assert "llama-cpp-python" in cmd
        assert "--no-deps" in cmd
        assert "cpu" in str(cmd) or "-v" in cmd

    def test_cuda(self, tmp_paths):
        cmd = ls._build_install_cmd(
            "cuda", "https://abetlen.github.io/llama-cpp-python/whl/cu122", str(tmp_paths["site"])
        )
        assert "--extra-index-url" in cmd
        assert "cu122" in " ".join(cmd)


class TestFindModel:
    def test_find_model(self, tmp_paths):
        base = tmp_paths["base"]
        models_dir = base / "models"
        (models_dir / "a.txt").write_text("not gguf")
        (models_dir / "model.gguf").write_text("fake gguf")

        found = ls._find_any_local_model()
        assert found is not None
        assert found.endswith("model.gguf")

    def test_no_model(self, tmp_paths):
        base = tmp_paths["base"]
        models_dir = base / "models"
        # очистим
        for f in models_dir.iterdir():
            f.unlink()
        assert ls._find_any_local_model() is None


class TestSmokeTest:
    def test_cpu_skipped(self):
        result = ls.smoke_test_gpu_init("cpu")
        assert result["ok"] is True
        assert result["skipped"] is False

    def test_no_model_skipped(self, tmp_paths, monkeypatch):
        monkeypatch.setattr(ls, "_find_any_local_model", lambda: None)
        result = ls.smoke_test_gpu_init("cuda", model_path=None)
        assert result["skipped"] is True

    def test_smoke_success_mocked(self, tmp_paths, monkeypatch):
        def fake_run(*a, **kw):
            return MagicMock(returncode=0, stdout="SMOKE_OK", stderr="")

        monkeypatch.setattr(ls.subprocess, "run", fake_run)
        result = ls.smoke_test_gpu_init(
            "cuda", model_path=str(tmp_paths["base"] / "models" / "model.gguf")
        )
        assert result["ok"] is True

    def test_smoke_failure_mocked(self, tmp_paths, monkeypatch):
        # создаём dummy модель чтобы не было skipped
        model_path = tmp_paths["base"] / "models" / "model.gguf"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text("fake")

        def fake_run(*a, **kw):
            return MagicMock(returncode=1, stdout="", stderr="CUDA error")

        monkeypatch.setattr(ls.subprocess, "run", fake_run)
        result = ls.smoke_test_gpu_init("cuda", model_path=str(model_path))
        assert result["ok"] is False


class TestBuildCmakeArgs:
    def test_all_supported(self):
        cpu = {"avx": True, "avx2": True, "fma": True, "f16c": True}
        assert ls.build_cmake_args(cpu) == ""

    def test_none_supported(self):
        cpu = {"avx": False, "avx2": False, "fma": False, "f16c": False}
        args = ls.build_cmake_args(cpu)
        assert "-DGGML_AVX2=OFF" in args
        assert "-DGGML_FMA=OFF" in args
        assert "-DGGML_F16C=OFF" in args
        assert "-DGGML_AVX=OFF" in args


class TestStartupState:
    def test_clean(self, tmp_paths):
        ls._clear_checkpoint()
        state = ls.get_startup_install_state()
        assert state["state"] == "clean"

    def test_interrupted(self, tmp_paths, monkeypatch):
        ls._save_checkpoint("downloading", {"backend": "cuda"})
        monkeypatch.setattr(ls, "llama_cpp_status", lambda: {"installed": False})
        monkeypatch.setattr(
            "engine.env_core.diagnostics.get_install_activity_status",
            lambda: {"target_dir_files": 10},
        )

        state = ls.get_startup_install_state()
        assert state["state"] == "interrupted"
        assert state["stage"] == "downloading"

    def test_installed(self, tmp_paths, monkeypatch):
        ls._save_checkpoint("downloading")
        monkeypatch.setattr(
            ls, "llama_cpp_status", lambda: {"installed": True, "path": "/fake/path"}
        )

        state = ls.get_startup_install_state()
        assert state["state"] == "installed"
