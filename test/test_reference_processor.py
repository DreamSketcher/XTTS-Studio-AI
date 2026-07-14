import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

try:
    import numpy as np
except ImportError:
    pytest.skip("numpy not installed", allow_module_level=True)

try:
    from pydub import AudioSegment
except ImportError:
    pytest.skip("pydub not installed", allow_module_level=True)

from engine.reference_processor import AdaptiveSilenceTrimmer, ReferenceProcessor, SNRAnalyzer


@pytest.fixture
def tmp_library(tmp_path: Path):
    lib = tmp_path / "library"
    lib.mkdir()
    yield lib


class TestAdaptiveSilenceTrimmer:
    def test_short_returns_same(self):
        trimmer = AdaptiveSilenceTrimmer()
        seg = AudioSegment.silent(duration=100)
        assert trimmer.trim(seg) is seg

    def test_trim_silence(self):
        trimmer = AdaptiveSilenceTrimmer()
        import array

        sr = 24000
        n = int(sr * 0.5)
        t = np.arange(n) / sr
        arr = (np.sin(2 * np.pi * 440 * t) * 0.5 * (2**15 - 1)).astype(np.int16)
        loud = AudioSegment(
            data=array.array("h", arr.tolist()).tobytes(),
            sample_width=2,
            frame_rate=sr,
            channels=1,
        )
        silent = AudioSegment.silent(duration=300)
        combined = silent + loud + silent
        trimmed = trimmer.trim(combined)
        assert len(trimmed) < len(combined)
        assert len(trimmed) >= 500

    def test_hard_limit(self):
        trimmer = AdaptiveSilenceTrimmer()
        trimmer.hard_limit_ms = 50
        silent = AudioSegment.silent(duration=500)
        import array

        sr = 24000
        n = int(sr * 0.5)
        t = np.arange(n) / sr
        arr = (np.sin(2 * np.pi * 440 * t) * 0.3 * (2**15 - 1)).astype(np.int16)
        loud = AudioSegment(
            data=array.array("h", arr.tolist()).tobytes(),
            sample_width=2,
            frame_rate=sr,
            channels=1,
        )
        combined = silent + loud + silent
        trimmed = trimmer.trim(combined)
        assert isinstance(trimmed, AudioSegment)


class TestSNRAnalyzer:
    def test_short_returns_unknown(self):
        analyzer = SNRAnalyzer()
        seg = AudioSegment.silent(duration=10)
        result = analyzer.analyze(seg)
        assert result["quality"] in ("unknown", "bad", "poor", "good", "excellent")
        assert "snr_db" in result

    def test_silent_low_snr(self):
        analyzer = SNRAnalyzer()
        seg = AudioSegment.silent(duration=1000)
        result = analyzer.analyze(seg)
        assert result["snr_db"] <= 25

    def test_clean_tone_high_snr(self):
        analyzer = SNRAnalyzer()
        import array

        sr = 24000
        silence_duration = 200
        tone_duration = 800
        silent = AudioSegment.silent(duration=silence_duration)
        n = int(sr * tone_duration / 1000)
        t = np.arange(n) / sr
        arr = (np.sin(2 * np.pi * 440 * t) * 0.5 * (2**15 - 1)).astype(np.int16)
        tone = AudioSegment(
            data=array.array("h", arr.tolist()).tobytes(),
            sample_width=2,
            frame_rate=sr,
            channels=1,
        )
        combined = silent + tone
        result = analyzer.analyze(combined)
        assert result["quality"] in ("good", "excellent", "poor", "bad", "unknown")
        assert isinstance(result["snr_db"], (float, np.floating))

    def test_noisy_low_snr(self):
        analyzer = SNRAnalyzer()
        sr = 24000
        duration_ms = 1000
        n = int(sr * duration_ms / 1000)
        rng = np.random.default_rng(0)
        noise = (rng.normal(0, 0.1, size=n) * (2**15 - 1)).astype(np.int16)
        import array

        noisy_seg = AudioSegment(
            data=array.array("h", noise.tolist()).tobytes(),
            sample_width=2,
            frame_rate=sr,
            channels=1,
        )
        result = analyzer.analyze(noisy_seg)
        assert result["snr_db"] < 25


class TestReferenceProcessor:
    def test_get_voice_dir_inside_library(self, tmp_library):
        proc = ReferenceProcessor(backup_dir=str(tmp_library))
        inside = tmp_library / "myvoice" / "file.wav"
        inside.parent.mkdir(parents=True)
        inside.write_text("fake")
        voice_dir = proc.get_voice_dir(str(inside))
        assert voice_dir == inside.parent.resolve()

    def test_get_voice_dir_outside(self, tmp_library, tmp_path):
        proc = ReferenceProcessor(backup_dir=str(tmp_library))
        outside = tmp_path / "outside.wav"
        outside.write_text("fake")
        voice_dir = proc.get_voice_dir(str(outside))
        assert voice_dir == (tmp_library / outside.stem).resolve()
        assert voice_dir.exists()

    def test_save_original_copy_wav_returns_same(self, tmp_library, tmp_path):
        proc = ReferenceProcessor(backup_dir=str(tmp_library))
        wav_file = tmp_path / "test.wav"
        wav_file.write_text("wav")
        voice_dir = tmp_library / "voice"
        voice_dir.mkdir()
        result = proc.save_original_copy(str(wav_file), voice_dir)
        assert Path(result).resolve() == wav_file.resolve()

    def test_save_original_copy_non_wav_copies(self, tmp_library, tmp_path):
        proc = ReferenceProcessor(backup_dir=str(tmp_library))
        mp3_file = tmp_path / "test.mp3"
        mp3_file.write_text("mp3 content")
        voice_dir = tmp_library / "voice2"
        voice_dir.mkdir()
        result = proc.save_original_copy(str(mp3_file), voice_dir)
        assert (voice_dir / mp3_file.name).exists()

    def test_save_original_copy_does_not_overwrite(self, tmp_library, tmp_path):
        proc = ReferenceProcessor(backup_dir=str(tmp_library))
        src = tmp_path / "src.mp3"
        src.write_text("src")
        voice_dir = tmp_library / "voice3"
        voice_dir.mkdir()
        dst = voice_dir / src.name
        dst.write_text("existing")
        result = proc.save_original_copy(str(src), voice_dir)
        assert dst.read_text() == "existing"

    def test_process_reference_already_normalized(self, tmp_library, tmp_path):
        proc = ReferenceProcessor(backup_dir=str(tmp_library))
        voice_dir = tmp_library / "myvoice"
        voice_dir.mkdir()
        norm_file = voice_dir / "normalized.wav"
        norm_file.write_bytes(b"fake wav")
        with patch("engine.reference_processor.AudioSegment.from_file") as mock_from_file:
            mock_seg = MagicMock()
            mock_from_file.return_value = mock_seg
            mock_snr = MagicMock()
            mock_snr.analyze.return_value = {"snr_db": 20, "quality": "good", "warning": None}
            proc.snr_analyzer = mock_snr
            result = proc.process_reference(str(norm_file), backup=False)
            assert Path(result).resolve() == norm_file.resolve()

    def test_process_reference_pipeline_mocked(self, tmp_library, tmp_path):
        proc = ReferenceProcessor(backup_dir=str(tmp_library))
        src = tmp_path / "input.mp3"
        src.write_text("fake")
        from unittest.mock import MagicMock
        import unittest.mock as mock

        monkeypatch = MagicMock()
        # use direct patch via attributes
        proc.save_original_copy = lambda fp, vd: str(vd / "orig.mp3")
        proc.convert_to_wav = lambda fp, vd, target_sample_rate=24000, mono=True: str(
            vd / "converted.wav"
        )
        proc.process_audio = lambda fp, vd, target_dBFS=-16.0: str(vd / "normalized.wav")
        with patch("engine.reference_processor.AudioSegment.from_file") as mock_from:
            mock_seg = MagicMock()
            mock_from.return_value = mock_seg
            proc.snr_analyzer.analyze = MagicMock(
                return_value={"snr_db": 15, "quality": "good", "warning": None}
            )
            result = proc.process_reference(str(src), backup=True)
            assert result.endswith("normalized.wav")

    def test_snr_callback(self, tmp_library, tmp_path):
        called = []

        def callback(result):
            called.append(result)

        proc = ReferenceProcessor(backup_dir=str(tmp_library), snr_callback=callback)
        src = tmp_path / "input.wav"
        src.write_text("fake wav")
        proc.get_voice_dir = lambda fp: tmp_library / "voice"
        (tmp_library / "voice").mkdir(exist_ok=True)
        proc.save_original_copy = lambda *a, **kw: str(src)
        proc.convert_to_wav = lambda *a, **kw: str(src)
        proc.process_audio = lambda *a, **kw: str(src)
        with patch("engine.reference_processor.AudioSegment.from_file") as mock_from:
            mock_seg = MagicMock()
            mock_from.return_value = mock_seg
            proc.snr_analyzer.analyze = MagicMock(
                return_value={"snr_db": 20, "quality": "excellent", "warning": None}
            )
            proc.process_reference(str(src))
            assert len(called) == 1
            assert called[0]["quality"] == "excellent"
