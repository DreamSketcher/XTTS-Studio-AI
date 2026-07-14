import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine.gui.voice_panel as vp
from engine.voice_manager import VoiceProfile


@pytest.fixture
def tmp_library(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    yield lib


class TestVoiceDir:
    def test_path_attribute(self, tmp_library):
        voice_dir = tmp_library / "myvoice"
        voice_dir.mkdir()

        # mock voice object with path attribute that is dir
        voice = MagicMock()
        voice.path = str(voice_dir)

        result = vp._voice_dir(voice)
        assert result == str(voice_dir)

    def test_dir_attribute(self, tmp_library):
        voice_dir = tmp_library / "voice2"
        voice_dir.mkdir()

        voice = MagicMock()
        # no path, but dir
        del voice.path
        voice.dir = str(voice_dir)

        result = vp._voice_dir(voice)
        assert result == str(voice_dir)

    def test_no_valid_dir(self):
        voice = MagicMock()
        voice.path = "/nonexistent/path"
        voice.dir = None
        voice.folder = None

        result = vp._voice_dir(voice)
        assert result is None

    def test_prefers_first_valid(self, tmp_library):
        voice_dir = tmp_library / "voice"
        voice_dir.mkdir()

        voice = MagicMock()
        voice.path = str(voice_dir)
        voice.dir = str(voice_dir)
        voice.folder = str(voice_dir)

        result = vp._voice_dir(voice)
        # should return path (first in list)
        assert result == str(voice_dir)


class TestResolveNormalizedPath:
    def test_absolute_normalized_file(self, tmp_library):
        voice_dir = tmp_library / "voice"
        voice_dir.mkdir()
        norm_file = voice_dir / "normalized.wav"
        norm_file.write_text("fake")

        voice = MagicMock()
        voice.path = str(voice_dir)
        voice.normalized = str(norm_file)

        result = vp._resolve_normalized_path(voice)
        assert result == str(norm_file)

    def test_relative_normalized_in_voice_dir(self, tmp_library):
        voice_dir = tmp_library / "voice"
        voice_dir.mkdir()
        norm_file = voice_dir / "normalized.wav"
        norm_file.write_text("fake")

        voice = MagicMock()
        voice.path = str(voice_dir)
        voice.normalized = "normalized.wav"

        result = vp._resolve_normalized_path(voice)
        assert result == str(norm_file)

    def test_fallback_normalized_wav(self, tmp_library):
        voice_dir = tmp_library / "voice"
        voice_dir.mkdir()
        norm_file = voice_dir / "normalized.wav"
        norm_file.write_text("fake")

        voice = MagicMock()
        voice.path = str(voice_dir)
        voice.normalized = None

        result = vp._resolve_normalized_path(voice)
        assert result == str(norm_file)

    def test_fallback_any_wav(self, tmp_library):
        voice_dir = tmp_library / "voice"
        voice_dir.mkdir()
        # нет normalized.wav, но есть другой wav
        other = voice_dir / "my_audio.wav"
        other.write_text("fake")

        voice = MagicMock()
        voice.path = str(voice_dir)
        voice.normalized = None

        result = vp._resolve_normalized_path(voice)
        assert result == str(other)

    def test_skip_cache_extensions(self, tmp_library):
        voice_dir = tmp_library / "voice"
        voice_dir.mkdir()
        # только .pth и .json — должны игнорироваться
        (voice_dir / "model.pth").write_text("x")
        (voice_dir / "data.json").write_text("{}")

        voice = MagicMock()
        voice.path = str(voice_dir)
        voice.normalized = None

        result = vp._resolve_normalized_path(voice)
        # должен вернуться None, т.к. нет wav/mp3
        assert result is None

    def test_normalized_attribute_variants(self, tmp_library):
        voice_dir = tmp_library / "voice"
        voice_dir.mkdir()
        norm_file = voice_dir / "normalized.wav"
        norm_file.write_text("fake")

        voice = MagicMock()
        voice.path = str(voice_dir)
        # использует normalized_path вместо normalized
        voice.normalized = None
        voice.normalized_path = str(norm_file)

        result = vp._resolve_normalized_path(voice)
        assert result == str(norm_file)


class TestVoicePanelInit:
    def test_init_updates_globals(self):
        vp.init(root="fake_root", ref_var="fake_ref", voice_manager="fake_vm")
        assert vp.root == "fake_root"
        assert vp.ref_var == "fake_ref"
        assert vp.voice_manager == "fake_vm"


class TestRefreshVoiceList:
    def test_refresh(self, tmp_library):
        # создаём 2 голоса
        v1 = tmp_library / "voice1"
        v1.mkdir()
        (v1 / "normalized.wav").write_text("x")
        v2 = tmp_library / "voice2"
        v2.mkdir()
        (v2 / "normalized.wav").write_text("x")

        # мок voice_manager
        from engine.voice_manager import VoiceManager

        vm = VoiceManager(base_dir=str(tmp_library))

        # мок listbox
        mock_listbox = MagicMock()
        mock_listbox.delete = MagicMock()
        mock_listbox.insert = MagicMock()

        vp.voice_manager = vm
        vp.voice_listbox = mock_listbox
        vp.voice_map = {}

        vp.refresh_voice_list()

        assert mock_listbox.delete.called
        assert mock_listbox.insert.call_count == 2
        assert len(vp.voice_map) == 2
        assert "voice1" in vp.voice_map
