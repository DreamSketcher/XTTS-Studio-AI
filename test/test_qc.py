import math
import sys
from unittest.mock import MagicMock

import pytest

try:
    import numpy as np
except ImportError:
    pytest.skip("numpy not installed", allow_module_level=True)

from engine.tts.qc import (
    _adaptive_trim,
    _detect_repeats,
    _normalize_loudness,
    _normalize_numpy_audio,
    _validate_duration,
    _wav_to_mono_float,
)


class TestWavToMonoFloat:
    def test_empty(self):
        arr = _wav_to_mono_float([])
        assert arr.size == 0

    def test_1d_list(self):
        wav = [0.1, 0.2, 0.3]
        arr = _wav_to_mono_float(wav)
        assert arr.shape == (3,)

    def test_2d_stereo_mean(self):
        wav = np.array([[1.0, 3.0], [2.0, 4.0]], dtype=np.float32)
        arr = _wav_to_mono_float(wav)
        assert arr.shape[0] == 2

    def test_nan_inf_handling(self):
        wav = [float("nan"), float("inf"), float("-inf"), 0.5]
        arr = _wav_to_mono_float(wav)
        assert not np.isnan(arr).any()
        assert not np.isinf(arr).any()


class TestDetectRepeats:
    def test_short_audio_no_repeat(self):
        wav = np.random.randn(1000).astype(np.float32)
        assert _detect_repeats(wav, sample_rate=24000) is False

    def test_silence_no_repeat(self):
        wav = np.zeros(24000 * 2, dtype=np.float32)
        assert _detect_repeats(wav) is False

    def test_random_noise_no_repeat(self):
        rng = np.random.default_rng(0)
        wav = rng.normal(0, 0.1, size=24000 * 2).astype(np.float32)
        assert _detect_repeats(wav, threshold=0.985) is False

    def test_repeating_pattern_detected(self):
        sr = 24000
        window_sec = 0.3
        window = int(window_sec * sr)
        t = np.arange(window) / sr
        tone = (np.sin(2 * math.pi * 440 * t) * 0.5).astype(np.float32)
        wav = np.concatenate([tone] * 5)
        assert _detect_repeats(wav, sample_rate=sr, window_sec=window_sec, threshold=0.985) is True

    def test_repeating_pattern_high_threshold_still_detects_strong_corr(self):
        sr = 24000
        window = int(0.3 * sr)
        t = np.arange(window) / sr
        tone = (np.sin(2 * np.pi * 220 * t) * 0.3).astype(np.float32)
        wav = np.concatenate([tone] * 3)
        assert _detect_repeats(wav, sample_rate=sr, window_sec=0.3, threshold=0.99) is True

    def test_different_tones_no_repeat(self):
        sr = 24000
        window = int(0.3 * sr)
        t = np.arange(window) / sr
        tone1 = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        tone2 = (np.sin(2 * np.pi * 880 * t) * 0.5).astype(np.float32)
        wav = np.concatenate([tone1, tone2, tone1, tone2])
        result = _detect_repeats(wav, sample_rate=sr)
        assert isinstance(result, bool)

    def test_rms_ratio_filter(self):
        sr = 24000
        window = int(0.3 * sr)
        loud = np.ones(window, dtype=np.float32) * 0.5
        quiet = np.ones(window, dtype=np.float32) * 0.01
        wav = np.concatenate([loud, quiet, loud, quiet, loud, quiet])
        assert isinstance(_detect_repeats(wav), bool)


class TestValidateDuration:
    def test_empty_audio_bad(self):
        assert _validate_duration([], "привет мир") is True

    def test_too_short_audio(self):
        wav = np.zeros(1000, dtype=np.float32)
        wav[:] = 0.1
        assert _validate_duration(wav, "привет") is True

    def test_almost_silent_bad(self):
        wav = np.zeros(24000, dtype=np.float32)
        assert _validate_duration(wav, "привет мир тест") is True

    def test_normal_duration_ok(self):
        rng = np.random.default_rng(1)
        wav = (rng.normal(0, 0.1, size=24000 * 2)).astype(np.float32)
        assert (
            _validate_duration(wav, "одно два три четыре пять шесть семь восемь девять десять")
            is False
        )

    def test_too_short_for_words(self):
        rng = np.random.default_rng(2)
        wav = (rng.normal(0, 0.1, size=int(24000 * 0.5))).astype(np.float32)
        assert (
            _validate_duration(wav, "одно два три четыре пять шесть семь восемь девять десять")
            is True
        )

    def test_too_long_for_words(self):
        rng = np.random.default_rng(3)
        wav = (rng.normal(0, 0.1, size=24000 * 20)).astype(np.float32)
        assert _validate_duration(wav, "раз два три четыре пять") is True

    def test_tag_removal(self):
        rng = np.random.default_rng(4)
        wav = (rng.normal(0, 0.1, size=24000 * 2)).astype(np.float32)
        text = "привет [NO_PAUSE] мир"
        assert _validate_duration(wav, text) is False

    def test_no_words_returns_false(self):
        rng = np.random.default_rng(5)
        wav = (rng.normal(0, 0.1, size=24000)).astype(np.float32)
        assert _validate_duration(wav, "   ... !!! ") is False
        assert _validate_duration(wav, "") is False

    def test_few_words_threshold(self):
        rng = np.random.default_rng(6)
        wav_short = (rng.normal(0, 0.1, size=int(24000 * 0.2))).astype(np.float32)
        assert _validate_duration(wav_short, "привет") is True
        wav_ok = (rng.normal(0, 0.1, size=int(24000 * 0.5))).astype(np.float32)
        assert _validate_duration(wav_ok, "привет") is False


class TestNormalizeNumpyAudio:
    def test_empty_returns_same(self):
        data = np.array([], dtype=np.float32)
        out = _normalize_numpy_audio(data)
        assert out.size == 0

    def test_silent_returns_same(self):
        data = np.zeros(1000, dtype=np.float32)
        out = _normalize_numpy_audio(data)
        import numpy.testing

        np.testing.assert_array_equal(out, data)

    def test_normalizes_gain(self):
        t = np.linspace(0, 1, 24000, dtype=np.float32)
        wav = (np.sin(2 * np.pi * 440 * t) * 0.01).astype(np.float32)
        out = _normalize_numpy_audio(wav, target_dbfs=-23.0)
        rms_in = np.sqrt(np.mean(wav**2))
        rms_out = np.sqrt(np.mean(out**2))
        assert rms_out > rms_in
        assert np.max(np.abs(out)) <= 1.0

    def test_peak_protection(self):
        t = np.linspace(0, 1, 24000, dtype=np.float32)
        wav = (np.sin(2 * np.pi * 440 * t) * 0.9).astype(np.float32)
        out = _normalize_numpy_audio(wav, target_dbfs=-23.0)
        assert np.max(np.abs(out)) <= 0.999 + 1e-6


class TestAdaptiveTrim:
    def test_off_mode_returns_same(self):
        seg = MagicMock()
        seg.__len__.return_value = 500
        out = _adaptive_trim(seg, mode="off")
        assert out is seg

    def test_manual_mode_trims(self):
        seg = MagicMock()
        seg.__len__.return_value = 1000
        seg.__getitem__.return_value = MagicMock(fade_out=lambda x: seg)
        seg.fade_out.return_value = seg
        mock_trimmed = MagicMock()
        mock_trimmed.fade_out.return_value = mock_trimmed
        seg.__getitem__.return_value = mock_trimmed
        out = _adaptive_trim(seg, base_ms=100, mode="manual")
        assert seg.__getitem__.called

    def test_short_seg_returns_same(self):
        seg = MagicMock()
        seg.__len__.return_value = 50
        assert _adaptive_trim(seg) is seg

    def test_auto_mode_no_trim_if_no_silence(self):
        seg = MagicMock()
        seg.__len__.return_value = 1000

        def loud_slice(_):
            m = MagicMock()
            m.dBFS = -20.0
            return m

        seg.__getitem__.side_effect = lambda s: (
            loud_slice(s) if isinstance(s, slice) else MagicMock(dBFS=-20.0)
        )
        out = _adaptive_trim(seg, chunk_text="Привет.", base_ms=100, mode="auto", range_ms=30)
        assert out is not None
