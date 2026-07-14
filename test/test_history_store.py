import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import engine.history_store as hs


@pytest.fixture
def tmp_history_file(tmp_path: Path, monkeypatch):
    file_path = tmp_path / "history.json"
    monkeypatch.setattr(hs, "HISTORY_PATH", str(file_path))
    yield file_path


class Task:
    def __init__(self, text="", voice=None, quality="", output_path="", stats=None):
        self.text = text
        self.voice = voice
        self.quality = quality
        self.output_path = output_path
        self.stats = stats or {}


class TestSaveHistory:
    def test_creates_file(self, tmp_history_file: Path):
        assert not tmp_history_file.exists()
        task = Task(
            text="hello",
            voice="/path/to/voice123/ref.wav",
            quality="High",
            output_path="/out/file.wav",
            stats={"time_sec": 10, "chunks": 5},
        )
        hs._save_history(task)
        assert tmp_history_file.exists()
        data = json.loads(tmp_history_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["text"] == "hello"
        assert data[0]["quality"] == "High"
        assert data[0]["output"] == "/out/file.wav"
        assert data[0]["duration"] == 10
        assert data[0]["chunks"] == 5
        # voice is basename of dirname
        assert data[0]["voice"] == "voice123"

    def test_inserts_at_beginning(self, tmp_history_file: Path):
        hs._save_history(Task(text="first"))
        hs._save_history(Task(text="second"))
        data = json.loads(tmp_history_file.read_text(encoding="utf-8"))
        assert data[0]["text"] == "second"
        assert data[1]["text"] == "first"

    def test_truncates_to_100(self, tmp_history_file: Path):
        for i in range(105):
            hs._save_history(Task(text=f"task {i}"))
        data = json.loads(tmp_history_file.read_text(encoding="utf-8"))
        assert len(data) == 100
        assert data[0]["text"] == "task 104"
        assert data[-1]["text"] == "task 5"  # первые 5 вытеснены

    def test_handles_corrupted_existing(self, tmp_history_file: Path):
        tmp_history_file.write_text("{ invalid", encoding="utf-8")
        hs._save_history(Task(text="new"))
        data = json.loads(tmp_history_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["text"] == "new"

    def test_handles_missing_stats(self, tmp_history_file: Path):
        task = Task(text="no stats", stats=None)
        # stats None уже в Task -> {}, но проверим с явным None и без stats
        task.stats = None
        hs._save_history(task)
        data = json.loads(tmp_history_file.read_text(encoding="utf-8"))
        assert data[0]["duration"] == 0
        assert data[0]["chunks"] == 0

    def test_handles_none_fields(self, tmp_history_file: Path):
        task = Task(text=None, voice=None, quality=None, output_path=None, stats={})
        hs._save_history(task)
        data = json.loads(tmp_history_file.read_text(encoding="utf-8"))
        assert data[0]["text"] == ""
        assert isinstance(data[0]["date"], str)

    def test_voice_none(self, tmp_history_file: Path):
        task = Task(voice=None)
        hs._save_history(task)
        data = json.loads(tmp_history_file.read_text(encoding="utf-8"))
        assert data[0]["voice"] == ""

    def test_public_alias(self, tmp_history_file: Path):
        assert hs.save_history is hs._save_history
