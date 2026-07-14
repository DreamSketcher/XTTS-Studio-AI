import os
import re
import tkinter as tk
from unittest.mock import MagicMock, patch

import pytest

try:
    import pygame
except ImportError:
    pytest.skip("pygame not installed", allow_module_level=True)

try:
    import engine.gui.generation as gen
except ImportError as e:
    pytest.skip(f"generation import failed: {e}", allow_module_level=True)

from engine.task_models import Task


class MockVar:
    def __init__(self, value=False):
        self._value = value

    def get(self):
        return self._value

    def set(self, v):
        self._value = v

    def is_set(self):
        return bool(self._value)

    def clear(self):
        self._value = False


@pytest.fixture
def mock_gen_deps(monkeypatch):
    class MockVarLocal:
        def __init__(self, value=None):
            self._value = value

        def get(self):
            return self._value

        def set(self, v):
            self._value = v

        def is_set(self):
            return bool(self._value)

        def clear(self):
            self._value = False

    monkeypatch.setattr(gen.tk, "BooleanVar", lambda value=False: MockVarLocal(value))
    monkeypatch.setattr(gen.tk, "StringVar", lambda value="": MockVarLocal(value))
    monkeypatch.setattr(gen.tk, "DoubleVar", lambda value=0.0: MockVarLocal(value))
    monkeypatch.setattr(gen.tk, "IntVar", lambda value=0: MockVarLocal(value))

    root = MagicMock()
    root.after = lambda delay, func: func() if callable(func) else None
    root.after_idle = lambda func: func() if callable(func) else None
    root.update_idletasks = lambda: None

    text_box = MagicMock()
    text_box.get.return_value = "Привет мир"
    text_box.config = MagicMock()
    text_box.delete = MagicMock()
    text_box.insert = MagicMock()
    text_box.update_idletasks = MagicMock()

    task_manager = MagicMock()
    task_manager.add_task = MagicMock()
    task_manager.cancel_task = MagicMock()
    task_manager.get_queue = MagicMock(return_value=[])

    ref_var = MagicMock()
    ref_var.get.return_value = "/tmp/ref.wav"

    lang_var = MagicMock()
    lang_var.get.return_value = "ru"

    quality_var = MagicMock()
    quality_var.get.return_value = "Высокое качество"
    quality_var.set = MagicMock()

    word_replacer_enabled = MagicMock()
    word_replacer_enabled.get.return_value = True

    lang_split_enabled = MagicMock()
    lang_split_enabled.get.return_value = True

    use_gpt = MagicMock()
    use_gpt.get.return_value = False

    _textbox_updated = MockVar(False)

    quality_params = {
        "Высокое качество": {
            "speed": MockVar(1.0),
            "ai_conductor_enabled": MockVar(False),
            "ai_conductor_context": MockVar(""),
        }
    }

    monkeypatch.setattr(gen, "root", root)
    monkeypatch.setattr(gen, "text_box", text_box)
    monkeypatch.setattr(gen, "task_manager", task_manager)
    monkeypatch.setattr(gen, "ref_var", ref_var)
    monkeypatch.setattr(gen, "lang_var", lang_var)
    monkeypatch.setattr(gen, "quality_var", quality_var)
    monkeypatch.setattr(gen, "word_replacer_enabled", word_replacer_enabled)
    monkeypatch.setattr(gen, "lang_split_enabled", lang_split_enabled)
    monkeypatch.setattr(gen, "use_gpt", use_gpt)
    monkeypatch.setattr(gen, "_textbox_updated", _textbox_updated)
    monkeypatch.setattr(gen, "quality_params", quality_params)
    monkeypatch.setattr(gen, "clean_path", lambda x: x)
    monkeypatch.setattr(gen, "save_settings", MagicMock())
    monkeypatch.setattr(gen, "set_ai_pulse", MagicMock())
    monkeypatch.setattr(gen, "update_queue_view", MagicMock())
    monkeypatch.setattr(gen, "refresh_voice_list", MagicMock())
    monkeypatch.setattr(gen, "update_gen_btn", MagicMock())
    monkeypatch.setattr(gen, "current_task", None)
    monkeypatch.setattr(gen, "model_ready", False)
    monkeypatch.setattr(gen, "PYGAME_OK", False)
    monkeypatch.setattr(gen, "normalize_text", lambda x: x.strip())
    monkeypatch.setattr(gen, "set_status", MagicMock())
    monkeypatch.setattr(gen, "set_stage", MagicMock())
    monkeypatch.setattr(gen, "set_progress", MagicMock())
    monkeypatch.setattr(gen, "lock_textbox", MagicMock())
    monkeypatch.setattr(gen, "unlock_textbox", MagicMock())
    monkeypatch.setattr(gen, "clear_chunk_highlight", MagicMock())
    monkeypatch.setattr(gen, "hide_placeholder", MagicMock())
    monkeypatch.setattr(gen, "_highlight_chunk", MagicMock())
    monkeypatch.setattr(gen, "_highlight_chunk_by_text", MagicMock())

    yield {
        "root": root,
        "text_box": text_box,
        "task_manager": task_manager,
        "ref_var": ref_var,
    }


class TestRegex:
    def test_collecting_re(self):
        m = gen._torch_collecting_re.match("Collecting torch==2.2.2")
        assert m is not None

    def test_downloading_re(self):
        m = gen._torch_downloading_re.match("Downloading torch-2.2.2+cpu-....whl (200.8 MB)")
        assert m is not None

    def test_installing_re(self):
        assert gen._torch_installing_re.match("Installing collected packages") is not None

    def test_percent_re(self):
        m = gen._torch_percent_re.search("45% downloaded")
        assert m is not None
        assert m.group(1) == "45"

    def test_ratio_re(self):
        m = gen._torch_ratio_re.search("90.5/200.8 MB")
        assert m is not None


class TestOnTaskUpdate:
    def test_none(self, mock_gen_deps):
        gen.on_task_update(None)

    def test_queue_update(self, mock_gen_deps):
        gen.on_task_update({"stage": "queue_update"})

    def test_chunk(self, mock_gen_deps):
        gen.on_task_update(
            {"stage": "chunk", "chunk_raw": "test", "chunk_start": 0, "chunk_end": 4}
        )

    def test_ai_conductor_on_off(self, mock_gen_deps):
        gen.on_task_update({"stage": "ai_conductor_on"})
        gen.on_task_update({"stage": "ai_conductor_off"})

    def test_normalized_text(self, mock_gen_deps):
        gen.on_task_update({"stage": "normalized_text", "text": "нормализованный текст"})

    def test_check_textbox_ready(self, mock_gen_deps):
        gen._textbox_updated.set(True)
        result = gen.on_task_update({"stage": "check_textbox_ready"})
        assert result is True

    def test_task_queued(self, mock_gen_deps):
        task = Task(text="test", status="queued", progress=0)
        gen.on_task_update(task)

    def test_task_running(self, mock_gen_deps):
        task = Task(text="test", status="running", progress=50)
        gen.on_task_update(task)

    def test_task_done(self, mock_gen_deps, monkeypatch):
        monkeypatch.setattr(gen, "_on_task_done", MagicMock())
        task = Task(
            text="test",
            status="done",
            progress=100,
            stats={"time_sec": 10, "chunks": 2, "voice": "test"},
        )
        task.id = "1"
        task.output_path = "/tmp/out.wav"
        gen.current_task = task
        gen.on_task_update(task)

    def test_task_error(self, mock_gen_deps, monkeypatch):
        monkeypatch.setattr(gen, "_on_task_error", MagicMock())
        task = Task(text="test", status="error", progress=0)
        task.error = "Some error"
        task.id = "1"
        gen.current_task = task
        gen.on_task_update(task)

    def test_task_cancelled(self, mock_gen_deps):
        task = Task(text="test", status="cancelled", progress=0)
        task.id = "1"
        task.raw_text = "original"
        gen.current_task = task
        gen.on_task_update(task)

    def test_unknown_status(self, mock_gen_deps):
        task = Task(text="test", status="unknown_status", progress=10)
        gen.on_task_update(task)


class TestRestoreRawText:
    def test_restore(self, mock_gen_deps):
        mock_box = mock_gen_deps["text_box"]
        task = Task(text="normalized", raw_text="original raw", status="done")
        gen._restore_raw_text(task)
        assert mock_box.delete.called

    def test_restore_no_raw(self, mock_gen_deps):
        task = Task(text="test", raw_text="", status="done")
        gen._restore_raw_text(task)

    def test_restore_exception(self, mock_gen_deps):
        mock_gen_deps["text_box"].delete.side_effect = Exception("fail")
        task = Task(text="test", raw_text="raw", status="done")
        gen._restore_raw_text(task)


class TestPreloadModel:
    def test_preload_updates_mode(self, mock_gen_deps, monkeypatch):
        monkeypatch.setattr(gen, "set_status", MagicMock())
        monkeypatch.setattr(gen, "set_stage", MagicMock())
        monkeypatch.setenv("OPEN_UPDATES_ON_STARTUP", "1")
        gen._preload_model()
        assert gen.model_ready is False

    def test_preload_success(self, mock_gen_deps, monkeypatch):
        monkeypatch.delenv("OPEN_UPDATES_ON_STARTUP", raising=False)
        mock_get_tts = MagicMock(return_value=object())
        monkeypatch.setitem(
            __import__("sys").modules, "engine.tts_runner", MagicMock(get_tts=mock_get_tts)
        )
        gen._preload_model()

    def test_preload_failure(self, mock_gen_deps, monkeypatch):
        monkeypatch.delenv("OPEN_UPDATES_ON_STARTUP", raising=False)

        def failing_get_tts():
            raise Exception("model fail")

        monkeypatch.setitem(
            __import__("sys").modules, "engine.tts_runner", MagicMock(get_tts=failing_get_tts)
        )
        gen._preload_model()
        assert gen.model_ready is False


class TestGenerateAndCancel:
    def test_generate_calls_task_manager(self, mock_gen_deps, monkeypatch, tmp_path):
        ref_file = tmp_path / "ref.wav"
        ref_file.write_text("fake")
        mock_gen_deps["ref_var"].get.return_value = str(ref_file)
        monkeypatch.setattr(os.path, "isfile", lambda x: True)
        gen.generate()
        assert mock_gen_deps["task_manager"].add_task.called

    def test_generate_empty_text(self, mock_gen_deps, monkeypatch):
        mock_gen_deps["text_box"].get.return_value = "   "
        monkeypatch.setattr(gen, "normalize_text", lambda x: "")
        with patch("engine.gui.generation.messagebox.showerror") as mock_err:
            gen.generate()
            assert mock_err.called

    def test_generate_no_ref(self, mock_gen_deps, monkeypatch, tmp_path):
        mock_gen_deps["text_box"].get.return_value = "Привет"
        monkeypatch.setattr(gen, "normalize_text", lambda x: "Привет")
        mock_gen_deps["ref_var"].get.return_value = "/nonexistent/ref.wav"
        monkeypatch.setattr(os.path, "isfile", lambda x: False)
        with patch("engine.gui.generation.messagebox.showerror") as mock_err:
            gen.generate()
            assert mock_err.called

    def test_cancel_task(self, mock_gen_deps):
        task = Task(text="test")
        task.id = "123"
        gen.current_task = task
        gen.cancel_task()
        assert mock_gen_deps["task_manager"].cancel_task.called
