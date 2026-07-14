import os
import wave
from pathlib import Path

import pytest

from engine.validation import TTSValidator, ValidationError


class TestValidateText:
    def test_empty(self):
        with pytest.raises(ValidationError, match="empty or invalid"):
            TTSValidator.validate_text("", "en")
        with pytest.raises(ValidationError):
            TTSValidator.validate_text(None, "en")

    def test_whitespace(self):
        with pytest.raises(ValidationError, match="only whitespace"):
            TTSValidator.validate_text("   \n  ", "ru")

    def test_too_long(self):
        long_text = "a" * 10001
        with pytest.raises(ValidationError, match="too long"):
            TTSValidator.validate_text(long_text, "en")

    def test_valid(self):
        cleaned = TTSValidator.validate_text("  hello world  ", "en")
        assert cleaned == "hello world"

    def test_exact_limit(self):
        text = "a" * 10000
        cleaned = TTSValidator.validate_text(text, "en")
        assert len(cleaned) == 10000


class TestValidateLanguage:
    def test_empty(self):
        with pytest.raises(ValidationError):
            TTSValidator.validate_language(
                "",
            )

    def test_not_string(self):
        with pytest.raises(ValidationError):
            TTSValidator.validate_language(None)

    def test_supported(self):
        assert TTSValidator.validate_language("ru") == "ru"
        assert TTSValidator.validate_language("EN") == "en"
        assert TTSValidator.validate_language("russian") == "ru"
        assert TTSValidator.validate_language("english") == "en"
        assert TTSValidator.validate_language("  Ru  ") == "ru"

    def test_unsupported(self):
        with pytest.raises(ValidationError, match="not supported"):
            TTSValidator.validate_language("xx")

    def test_all_supported(self):
        for lang in TTSValidator.SUPPORTED_LANGUAGES:
            assert TTSValidator.validate_language(lang) == lang


class TestValidateReferenceAudio:
    def test_missing_path(self):
        with pytest.raises(ValidationError, match="missing or invalid"):
            TTSValidator.validate_reference_audio("")

    def test_not_exists(self, tmp_path):
        with pytest.raises(ValidationError, match="does not exist"):
            TTSValidator.validate_reference_audio(str(tmp_path / "no.wav"))

    def test_not_file(self, tmp_path):
        with pytest.raises(ValidationError, match="not a file"):
            TTSValidator.validate_reference_audio(str(tmp_path))

    def test_unsupported_format(self, tmp_path):
        mp3 = tmp_path / "ref.mp3"
        mp3.write_text("fake")
        with pytest.raises(ValidationError, match="Unsupported format"):
            TTSValidator.validate_reference_audio(str(mp3))

    def test_corrupted_wav(self, tmp_path):
        bad_wav = tmp_path / "bad.wav"
        bad_wav.write_bytes(b"not a wav file")
        with pytest.raises(ValidationError, match="Corrupted|Error reading"):
            TTSValidator.validate_reference_audio(str(bad_wav))

    def test_valid_wav(self, tmp_path):
        # создаём валидный wav 3 секунды
        wav_path = tmp_path / "good.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\x00\x00" * 24000 * 3)  # 3 sec silence

        result = TTSValidator.validate_reference_audio(str(wav_path))
        assert os.path.exists(result)

    def test_too_short(self, tmp_path):
        wav_path = tmp_path / "short.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\x00\x00" * 24000 * 1)  # 1 sec

        with pytest.raises(ValidationError, match="too short"):
            TTSValidator.validate_reference_audio(str(wav_path), min_duration_sec=2.0)

    def test_empty_wav(self, tmp_path):
        wav_path = tmp_path / "empty.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            # no frames

        with pytest.raises(ValidationError):
            TTSValidator.validate_reference_audio(str(wav_path))


class TestValidateOutputDirectory:
    def test_empty(self):
        with pytest.raises(ValidationError):
            TTSValidator.validate_output_directory("")

    def test_creates_dir(self, tmp_path):
        out_file = tmp_path / "nonexistent_dir" / "out.wav"
        result = TTSValidator.validate_output_directory(str(out_file))
        assert os.path.exists(os.path.dirname(result))

    def test_not_writable(self, tmp_path, monkeypatch):
        # мокаем os.access чтобы вернуть False
        out_file = tmp_path / "out.wav"
        monkeypatch.setattr(os, "access", lambda path, mode: False)
        with pytest.raises(ValidationError, match="not writable"):
            TTSValidator.validate_output_directory(str(out_file))


class TestValidateAll:
    def test_all_valid(self, tmp_path):
        wav_path = tmp_path / "ref.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(b"\x00\x00" * 24000 * 3)

        out_path = tmp_path / "out" / "result.wav"

        text, lang, ref, out = TTSValidator.validate_all(
            text="  hello  ",
            language="en",
            speaker_wav=str(wav_path),
            output_path=str(out_path),
        )
        assert text == "hello"
        assert lang == "en"
        assert ref == str(wav_path.resolve()) or os.path.exists(ref)

    def test_all_invalid(self, tmp_path):
        with pytest.raises(ValidationError):
            TTSValidator.validate_all("", "xx", "/nonexistent.wav", "")
