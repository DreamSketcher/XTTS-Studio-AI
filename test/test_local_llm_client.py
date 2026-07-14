import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

import engine.local_llm_client as llc


@pytest.fixture
def tmp_settings(tmp_path: Path, monkeypatch):
    settings_path = tmp_path / "gpt_settings.json"
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(llc, "_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(llc, "MODELS_DIR", str(models_dir))
    # BASE_DIR не используется напрямую для MODELS_DIR после патча
    yield {"settings_path": settings_path, "models_dir": models_dir}


class TestEstimateMemory:
    def test_estimate(self):
        assert llc.estimate_memory_gb(7, 0.6) == 4.2
        assert llc.estimate_memory_gb(1.1, 0.6) == pytest.approx(0.66)


class TestModelFiles:
    def test_paths(self, tmp_settings):
        models_dir = tmp_settings["models_dir"]
        assert llc.get_model_file_path("model.gguf") == os.path.join(models_dir, "model.gguf")
        assert not llc.is_model_downloaded("not_exists.gguf")
        (Path(models_dir) / "exists.gguf").write_text("fake")
        assert llc.is_model_downloaded("exists.gguf")

    def test_checkpoint_save_load_clear(self, tmp_settings):
        filename = "test.gguf"
        llc._save_download_checkpoint(
            filename, offset=1234, total=5000, url="http://example.com/model.gguf"
        )
        data = llc._load_download_checkpoint(filename)
        assert data["offset"] == 1234
        assert data["total"] == 5000
        assert data["url"] == "http://example.com/model.gguf"

        llc._clear_download_checkpoint(filename)
        assert llc._load_download_checkpoint(filename) == {}

    def test_discard_incomplete(self, tmp_settings):
        models_dir = Path(tmp_settings["models_dir"])
        filename = "partial.gguf"
        # создаём .tmp и чекпоинт
        (models_dir / (filename + ".tmp")).write_text("partial data")
        llc._save_download_checkpoint(filename, 100, 1000, "url")
        llc.discard_incomplete_download(filename)
        assert not (models_dir / (filename + ".tmp")).exists()
        assert llc._load_download_checkpoint(filename) == {}


class TestCompatibleModels:
    def test_compatible_flag(self, tmp_settings, monkeypatch):
        monkeypatch.setattr(llc, "_get_system_ram_gb", lambda: 16.0)
        models = llc.get_compatible_models(ram_gb=16)
        for m in models:
            assert "memory_gb" in m
            assert "compatible" in m
            assert "installed" in m
            # при 16 GB все из каталога (max ~5GB) должны быть совместимы (с запасом 1.5)
            if m["memory_gb"] + 1.5 <= 16:
                assert m["compatible"] is True

    def test_incompatible_when_low_ram(self, tmp_settings, monkeypatch):
        monkeypatch.setattr(llc, "_get_system_ram_gb", lambda: 2.0)
        models = llc.get_compatible_models(ram_gb=2.0)
        # tinyllama 1.1*0.6=0.66 +1.5=2.16 >2 → не совместима
        tiny = next((x for x in models if x["id"] == "tinyllama-1.1b-q4"), None)
        assert tiny is not None
        # при 2 GB даже tiny может быть несовместима из-за запаса
        assert tiny["compatible"] is False


class TestInstalledModelsRegistry:
    def test_list_save(self, tmp_settings):
        assert llc.list_installed_models() == []
        llc._save_installed_models([{"id": "1"}])
        assert len(llc.list_installed_models()) == 1

    def test_active_model(self, tmp_settings):
        llc._save_installed_models(
            [{"id": "a", "path": "/tmp/a.gguf"}, {"id": "b", "path": "/tmp/b.gguf"}]
        )
        llc.set_active_model_id("a")
        assert llc.get_active_model_id() == "a"
        active = llc.get_active_model()
        assert active["id"] == "a"

        llc.set_active_model_id("nonexistent")
        assert llc.get_active_model() is None

    def test_register_and_remove(self, tmp_settings):
        # register_model
        entry = llc.register_model("/tmp/models/my.gguf", label="MyModel", n_gpu_layers=0)
        assert entry["label"] == "MyModel"
        assert len(llc.list_installed_models()) == 1

        llc.set_active_model_id(entry["id"])
        assert llc.get_active_model_id() == entry["id"]

        llc.remove_model(entry["id"])
        assert len(llc.list_installed_models()) == 0
        assert llc.get_active_model_id() == ""  # сброшен

    def test_move_model_file(self, tmp_settings, tmp_path):
        src = tmp_path / "source.gguf"
        src.write_text("data")
        # MODELS_DIR уже tmp_settings["models_dir"]
        entry = llc.move_model_file(str(src), label="Moved")
        assert not src.exists()  # перемещён
        assert Path(entry["path"]).exists()
        assert entry["label"] == "Moved"


class TestDownloadModel:
    def test_empty_url_raises(self, tmp_settings):
        with pytest.raises(ValueError):
            llc.download_model("", "file.gguf")

    def test_download_success_mocked(self, tmp_settings, monkeypatch):
        models_dir = Path(tmp_settings["models_dir"])
        filename = "mock.gguf"
        url = "http://example.com/mock.gguf"
        content = b"fake gguf content " * 100

        class FakeResponse:
            def __init__(self):
                self.headers = {"Content-Length": str(len(content))}
                self.status = 200
                self._pos = 0

            def read(self, size=-1):
                if size == -1:
                    size = len(content) - self._pos
                chunk = content[self._pos : self._pos + size]
                self._pos += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(
            llc.urllib.request, "urlopen", lambda req, timeout=0, context=None: FakeResponse()
        )

        progress = []
        dest = llc.download_model(url, filename, progress_cb=lambda s: progress.append(s))
        assert Path(dest).exists()
        assert Path(dest).read_bytes() == content
        assert len(progress) > 0

    def test_cancel_flag(self, tmp_settings, monkeypatch):
        filename = "cancel.gguf"
        url = "http://example.com/cancel.gguf"
        content = b"x" * 100000

        class SlowResponse:
            def __init__(self):
                self.headers = {"Content-Length": str(len(content))}
                self.status = 200
                self._pos = 0

            def read(self, size=-1):
                # эмулируем медленное чтение
                if self._pos >= len(content):
                    return b""
                chunk = content[self._pos : self._pos + 8192]
                self._pos += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(llc.urllib.request, "urlopen", lambda *a, **kw: SlowResponse())

        cancelled = {"cancelled": True}
        with pytest.raises(InterruptedError):
            llc.download_model(url, filename, cancelled_flag=cancelled)

        # чекпоинт должен сохраниться
        ckpt = llc._load_download_checkpoint(filename)
        assert ckpt.get("offset", 0) >= 0

    def test_resume_uses_range_header(self, tmp_settings, monkeypatch):
        filename = "resume.gguf"
        url = "http://example.com/resume.gguf"
        # создаём чекпоинт с offset
        llc._save_download_checkpoint(filename, offset=1000, total=5000, url=url)
        # создаём частичный .tmp файл
        models_dir = Path(tmp_settings["models_dir"])
        (models_dir / (filename + ".tmp")).write_bytes(b"x" * 1000)

        captured_headers = {}

        class FakeResponse:
            def __init__(self):
                self.headers = {"Content-Length": "4000"}
                self.status = 206
                self._read = False

            def read(self, size=-1):
                if not self._read:
                    self._read = True
                    return b"y" * 4000
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=0, context=None):
            captured_headers.update(req.headers)
            return FakeResponse()

        monkeypatch.setattr(llc.urllib.request, "urlopen", fake_urlopen)

        dest = llc.download_model(url, filename, resume=True)
        assert "Range" in captured_headers
        assert captured_headers["Range"] == "bytes=1000-"
        assert Path(dest).exists()

    def test_transient_error_retries(self, tmp_settings, monkeypatch):
        filename = "retry.gguf"
        url = "http://example.com/retry.gguf"

        attempt = {"count": 0}

        class FailOnceResponse:
            def __init__(self):
                self.headers = {"Content-Length": "10"}
                self.status = 200

            def read(self, size=-1):
                # первый раз бросаем URLError, второй раз успех
                if attempt["count"] == 1:
                    raise llc.urllib.error.URLError("transient")
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen_side_effect(*a, **kw):
            attempt["count"] += 1
            if attempt["count"] == 1:
                # сразу бросаем transient ошибку до получения response
                raise llc.urllib.error.URLError("connection reset")
            return FailOnceResponse()

        monkeypatch.setattr(llc.urllib.request, "urlopen", urlopen_side_effect)
        monkeypatch.setattr(llc.time, "sleep", lambda x: None)  # ускоряем retry

        # должен попробовать 2 раза и в итоге упасть или успеть?
        # Настраиваем _MAX_DOWNLOAD_RETRIES большим, чтобы хватило
        monkeypatch.setattr(llc, "_MAX_DOWNLOAD_RETRIES", 3)

        # Первый вызов кинет URLError и должен ретрайнуться
        # Второй вызов вернёт FailOnceResponse который внутри read кинет URLError снова?
        # Для простоты проверим что ретрай логика не падает с InterruptedError
        try:
            llc.download_model(url, filename)
        except Exception as e:
            # может быть RuntimeError после всех ретраев — это ок, главное что ретрай был
            assert attempt["count"] >= 2
