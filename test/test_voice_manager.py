import os
import time
from pathlib import Path

import pytest

from engine.voice_manager import VoiceManager, VoiceProfile


@pytest.fixture
def tmp_library(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    yield lib


class TestVoiceManagerScan:
    def test_scan_empty(self, tmp_library):
        vm = VoiceManager(base_dir=str(tmp_library))
        voices = vm.scan_voices()
        assert voices == []
        assert vm.list_voices() == []

    def test_scan_with_voices(self, tmp_library):
        # создаём 2 голоса
        v1 = tmp_library / "voice1"
        v1.mkdir()
        (v1 / "original.wav").write_text("orig")
        (v1 / "converted.wav").write_text("conv")
        (v1 / "normalized.wav").write_text("norm")
        (v1 / "embedding.pth").write_text("emb")

        time.sleep(0.01)
        v2 = tmp_library / "voice2"
        v2.mkdir()
        (v2 / "original_input.mp3").write_text("orig2")

        vm = VoiceManager(base_dir=str(tmp_library))
        voices = vm.scan_voices()
        assert len(voices) == 2
        # сортировка по last_modified desc — voice2 новее voice1
        assert voices[0].name == "voice2"

        # проверка _find_file
        voice1 = vm.get_voice("voice1")
        assert voice1.original == "original.wav"
        assert voice1.converted == "converted.wav"
        assert voice1.normalized == "normalized.wav"
        assert voice1.embedding == "embedding.pth"

        voice2 = vm.get_voice("voice2")
        assert voice2.original == "original_input.mp3"
        assert voice2.converted is None

    def test_find_file(self, tmp_library):
        vm = VoiceManager(base_dir=str(tmp_library))
        assert vm._find_file(["original.wav", "converted.wav"], "original") == "original.wav"
        assert vm._find_file(["ORIGINAL.WAV"], "original") == "ORIGINAL.WAV"  # case insensitive
        assert vm._find_file(["a.txt", "b.txt"], "original") is None
        assert vm._find_file(None, "original") is None  # handles exception

    def test_scan_ignores_files(self, tmp_library):
        (tmp_library / "not_a_dir.txt").write_text("file")
        subdir = tmp_library / "voice"
        subdir.mkdir()
        (subdir / "file.wav").write_text("x")

        vm = VoiceManager(base_dir=str(tmp_library))
        voices = vm.scan_voices()
        assert len(voices) == 1
        assert voices[0].name == "voice"

    def test_scan_handles_list_error(self, tmp_library, monkeypatch):
        vm = VoiceManager(base_dir=str(tmp_library))
        monkeypatch.setattr(
            os, "listdir", lambda x: (_ for _ in ()).throw(PermissionError("no access"))
        )
        voices = vm.scan_voices()
        assert voices == []


class TestVoiceManagerGetActive:
    def test_get_set_active(self, tmp_library):
        v1 = tmp_library / "voice1"
        v1.mkdir()
        (v1 / "normalized.wav").write_text("x")

        vm = VoiceManager(base_dir=str(tmp_library))
        vm.scan_voices()

        assert vm.get_voice("voice1") is not None
        assert vm.get_voice("nonexistent") is None

        assert vm.set_active("voice1") is True
        assert vm.get_active().name == "voice1"

        assert vm.set_active("nonexistent") is False


class TestDeleteVoice:
    def test_delete_existing(self, tmp_library):
        v1 = tmp_library / "voice1"
        v1.mkdir()
        (v1 / "file.wav").write_text("x")

        vm = VoiceManager(base_dir=str(tmp_library))
        vm.scan_voices()
        assert len(vm.list_voices()) == 1

        assert vm.delete_voice("voice1") is True
        assert not v1.exists()
        assert len(vm.list_voices()) == 0

    def test_delete_nonexistent(self, tmp_library):
        vm = VoiceManager(base_dir=str(tmp_library))
        vm.scan_voices()
        assert vm.delete_voice("no_such") is False


class TestRenameVoice:
    def test_rename_success(self, tmp_library):
        v1 = tmp_library / "old_name"
        v1.mkdir()
        (v1 / "file.wav").write_text("x")

        vm = VoiceManager(base_dir=str(tmp_library))
        vm.scan_voices()

        assert vm.rename_voice("old_name", "new_name") is True
        assert not (tmp_library / "old_name").exists()
        assert (tmp_library / "new_name").exists()
        assert vm.get_voice("new_name") is not None
        assert vm.get_voice("old_name") is None

    def test_rename_nonexistent(self, tmp_library):
        vm = VoiceManager(base_dir=str(tmp_library))
        vm.scan_voices()
        assert vm.rename_voice("nope", "new") is False

    def test_rename_failure(self, tmp_library, monkeypatch):
        v1 = tmp_library / "voice"
        v1.mkdir()
        (v1 / "a.wav").write_text("x")

        vm = VoiceManager(base_dir=str(tmp_library))
        vm.scan_voices()

        # мок os.rename чтобы кидал исключение
        monkeypatch.setattr(os, "rename", lambda a, b: (_ for _ in ()).throw(OSError("fail")))

        assert vm.rename_voice("voice", "new_voice") is False


class TestRelativeBaseDir:
    def test_relative_dir_resolved(self, tmp_path, monkeypatch):
        # base_dir не абсолютный — должен резолвиться относительно engine/__file__
        # Проверим что создаётся папка
        rel_dir = "test_library_rel"
        # временно меняем cwd и проверяем что VoiceManager создаёт папку рядом с engine
        # Проще: создаём VoiceManager с абсолютным путём и проверяем что относительный тоже работает
        import engine.voice_manager as vm_mod

        base_path = os.path.join(os.path.dirname(os.path.abspath(vm_mod.__file__)), rel_dir)
        # очистим если существует
        import shutil

        if os.path.exists(base_path):
            shutil.rmtree(base_path)

        vm = vm_mod.VoiceManager(base_dir=rel_dir)
        vm.scan_voices()
        assert os.path.exists(base_path)
        # cleanup
        shutil.rmtree(base_path, ignore_errors=True)
