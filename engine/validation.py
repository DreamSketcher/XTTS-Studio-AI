import os
import re
import wave
from typing import Tuple, List, Optional


class ValidationError(Exception):
    """Custom exception class for TTS validation errors."""

    pass


class TTSValidator:
    """
    Centralized validation service to deduplicate logic between:
    - engine/gui/ai_conductor.py (Early GUI-level validation before queuing)
    - engine/ai_conductor.py (Queue-level validation)
    - engine/tts_runner.py (Strict validation right before running inference)
    """

    SUPPORTED_LANGUAGES = {
        "en",
        "es",
        "fr",
        "de",
        "it",
        "pt",
        "pl",
        "tr",
        "ru",
        "nl",
        "cs",
        "ar",
        "zh-cn",
        "ja",
        "hu",
        "ko",
        "zh",
    }

    @classmethod
    def validate_text(cls, text: str, language: str) -> str:
        """
        Validates the text to generate.
        Returns the cleaned/normalized text.
        """
        if not text or not isinstance(text, str):
            raise ValidationError("Text input is empty or invalid.")

        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValidationError("Text input contains only whitespace.")

        # Length safety limit to prevent OOM
        if len(cleaned_text) > 10000:
            raise ValidationError(
                f"Text is too long ({len(cleaned_text)} characters). "
                "Please split it into smaller segments (max 10,000 chars per batch)."
            )

        return cleaned_text

    @classmethod
    def validate_language(cls, language: str) -> str:
        """Validates if the chosen language is officially supported by XTTS."""
        if not language or not isinstance(language, str):
            raise ValidationError("Language identifier must be a string.")

        lang_code = language.strip().lower()
        # Normalization (e.g. mapping "russian" -> "ru" or "english" -> "en")
        lang_map = {
            "english": "en",
            "spanish": "es",
            "french": "fr",
            "german": "de",
            "italian": "it",
            "portuguese": "pt",
            "polish": "pl",
            "turkish": "tr",
            "russian": "ru",
            "dutch": "nl",
            "czech": "cs",
            "arabic": "ar",
            "chinese": "zh-cn",
            "japanese": "ja",
            "hungarian": "hu",
            "korean": "ko",
        }

        if lang_code in lang_map:
            lang_code = lang_map[lang_code]

        if lang_code not in cls.SUPPORTED_LANGUAGES:
            raise ValidationError(
                f"Language '{language}' is not supported by XTTS v2.\n"
                f"Supported language codes: {', '.join(sorted(cls.SUPPORTED_LANGUAGES))}"
            )

        return lang_code

    @classmethod
    def validate_reference_audio(
        cls, audio_path: str, min_duration_sec: float = 2.0, max_duration_sec: float = 30.0
    ) -> str:
        """
        Validates the reference voice clone audio.
        Checks for path existence, format, duration, and integrity.
        """
        if not audio_path or not isinstance(audio_path, str):
            raise ValidationError("Reference audio path is missing or invalid.")

        abs_path = os.path.abspath(audio_path)
        if not os.path.exists(abs_path):
            raise ValidationError(f"Reference audio file does not exist: {audio_path}")

        if not os.path.isfile(abs_path):
            raise ValidationError(f"Reference audio path is not a file: {audio_path}")

        # Check for WAV file extension and header validity
        _, ext = os.path.splitext(abs_path.lower())
        if ext != ".wav":
            raise ValidationError(
                f"Unsupported format '{ext}'. Reference voice clone must be in WAV format (.wav)."
            )

        # Robust check using Python's standard `wave` module (to avoid loading heavy torch/librosa)
        try:
            with wave.open(abs_path, "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                channels = wav_file.getnchannels()

                if frames == 0 or rate == 0:
                    raise ValidationError("The reference WAV file seems empty or corrupted.")

                duration = frames / float(rate)

                if duration < min_duration_sec:
                    raise ValidationError(
                        f"Reference audio is too short ({duration:.2f}s). "
                        f"The file must be at least {min_duration_sec}s for stable voice cloning."
                    )
                if duration > max_duration_sec:
                    # Log a warning or truncate, here we raise error or warn
                    pass  # We can warningly allow or truncate during inference

        except wave.Error as e:
            raise ValidationError(
                f"Corrupted or invalid WAV format: {e}. Please supply a standard PCM WAV."
            )
        except Exception as e:
            raise ValidationError(f"Error reading reference audio file: {e}")

        return abs_path

    @classmethod
    def validate_output_directory(cls, output_path: str) -> str:
        """Checks if the output directory is writable."""
        if not output_path:
            raise ValidationError("Output audio path is empty.")

        abs_output = os.path.abspath(output_path)
        parent_dir = os.path.dirname(abs_output)

        if not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except Exception as e:
                raise ValidationError(f"Could not create output directory '{parent_dir}': {e}")

        if not os.access(parent_dir, os.W_OK):
            raise ValidationError(f"Output directory '{parent_dir}' is not writable.")

        return abs_output

    @classmethod
    def validate_all(
        cls, text: str, language: str, speaker_wav: str, output_path: str
    ) -> Tuple[str, str, str, str]:
        """
        Runs the full check pipeline. Returns a clean tuple of:
        (cleaned_text, cleaned_language, cleaned_speaker_wav, cleaned_output_path)
        """
        valid_text = cls.validate_text(text, language)
        valid_lang = cls.validate_language(language)
        valid_ref = cls.validate_reference_audio(speaker_wav)
        valid_out = cls.validate_output_directory(output_path)
        return valid_text, valid_lang, valid_ref, valid_out
