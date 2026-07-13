import os
from pathlib import Path
from pydub import AudioSegment
import shutil
from datetime import datetime


# =========================
# ADAPTIVE SILENCE TRIMMER
# =========================
class AdaptiveSilenceTrimmer:
    def __init__(self):
        self.min_silence_db = -45
        self.hard_limit_ms = 250

    def trim(self, audio: AudioSegment) -> AudioSegment:
        if len(audio) < 300:
            return audio

        noise_floor = audio.dBFS
        silence_thresh = min(self.min_silence_db, noise_floor - 16)

        start_trim = self._find_start(audio, silence_thresh)
        end_trim = self._find_end(audio, silence_thresh)

        start_trim = min(start_trim, self.hard_limit_ms)
        end_trim = min(end_trim, self.hard_limit_ms)

        padding = 40

        start = max(0, start_trim - padding)
        end = len(audio) - max(0, end_trim - padding)

        if end <= start:
            return audio

        return audio[start:end]

    def _find_start(self, audio, silence_thresh):
        step = 10
        for i in range(0, len(audio), step):
            chunk = audio[i : i + step]
            if chunk.dBFS > silence_thresh:
                return i
        return 0

    def _find_end(self, audio, silence_thresh):
        step = 10
        for i in range(len(audio), 0, -step):
            chunk = audio[max(0, i - step) : i]
            if chunk.dBFS > silence_thresh:
                return len(audio) - i
        return 0


# =========================
# SNR ANALYZER
# =========================
class SNRAnalyzer:
    """
    Оценивает качество референсного аудио по SNR (signal-to-noise ratio).
    Использует только numpy — без внешних зависимостей.

    Метод: сравниваем RMS громких (речевых) и тихих (шумовых) участков.
    """

    # пороги оценки качества
    EXCELLENT_DB = 25.0  # отличный референс
    GOOD_DB = 15.0  # хороший
    POOR_DB = 8.0  # плохой — предупреждение
    BAD_DB = 3.0  # очень плохой — сильное предупреждение

    def analyze(self, audio: AudioSegment) -> dict:
        """
        Возвращает dict:
          snr_db    — оценка SNR в децибелах
          quality   — "excellent" / "good" / "poor" / "bad"
          warning   — текст предупреждения или None
        """
        import numpy as np

        samples = audio.get_array_of_samples()
        arr = np.array(samples, dtype=np.float32)

        if len(arr) < 100:
            return {"snr_db": 0.0, "quality": "unknown", "warning": None}

        # нормализуем в [-1, 1]
        max_val = float(2 ** (audio.sample_width * 8 - 1))
        arr = arr / (max_val + 1e-9)

        # делим на фреймы по 20ms
        frame_size = int(audio.frame_rate * 0.02)
        if frame_size < 1:
            frame_size = 1

        n_frames = len(arr) // frame_size
        if n_frames < 4:
            return {"snr_db": 0.0, "quality": "unknown", "warning": None}

        frames = arr[: n_frames * frame_size].reshape(n_frames, frame_size)
        rms_per_frame = np.sqrt(np.mean(frames**2, axis=1))

        # речевые фреймы — верхние 30% по громкости
        # шумовые фреймы — нижние 20% по громкости
        sorted_rms = np.sort(rms_per_frame)
        noise_rms = np.mean(sorted_rms[: max(1, int(n_frames * 0.20))]) + 1e-9
        speech_rms = np.mean(sorted_rms[int(n_frames * 0.70) :]) + 1e-9

        snr_db = 20 * np.log10(speech_rms / noise_rms)

        # оценка качества
        if snr_db >= self.EXCELLENT_DB:
            quality = "excellent"
            warning = None
        elif snr_db >= self.GOOD_DB:
            quality = "good"
            warning = None
        elif snr_db >= self.POOR_DB:
            quality = "poor"
            warning = (
                f"Референс зашумлён (SNR ≈ {snr_db:.1f} dB). "
                "Качество клонирования может снизиться. "
                "Рекомендуется более чистая запись (тихая комната, без эха)."
            )
        else:
            quality = "bad"
            warning = (
                f"Референс очень зашумлён (SNR ≈ {snr_db:.1f} dB). "
                "Клонирование голоса будет нестабильным. "
                "Используйте запись без фонового шума, музыки или эха."
            )

        print(f"[SNR] {snr_db:.1f} dB → {quality}")
        if warning:
            print(f"[SNR] ⚠ {warning}")

        return {
            "snr_db": round(snr_db, 1),
            "quality": quality,
            "warning": warning,
        }


# =========================
# MAIN PROCESSOR
# =========================
class ReferenceProcessor:
    def __init__(self, backup_dir="library", snr_callback=None):
        self.backup_dir = Path(backup_dir).resolve()
        self.backup_dir.mkdir(exist_ok=True)

        self.trimmer = AdaptiveSilenceTrimmer()
        self.snr_analyzer = SNRAnalyzer()

        # опциональный колбэк для GUI: snr_callback(snr_result: dict)
        self.snr_callback = snr_callback

    # =========================
    # VOICE FOLDER
    # =========================
    def get_voice_dir(self, filepath: str) -> Path:
        src = Path(filepath).resolve()

        try:
            src.relative_to(self.backup_dir)
            return src.parent
        except ValueError:
            pass

        voice_dir = self.backup_dir / src.stem
        voice_dir.mkdir(parents=True, exist_ok=True)
        return voice_dir

    # =========================
    # SAVE ORIGINAL
    # =========================
    def save_original_copy(self, filepath: str, voice_dir: Path) -> str:
        src = Path(filepath).resolve()
        if src.suffix.lower() == ".wav":
            return str(src)

        dst = voice_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)

        return str(dst)

    # =========================
    # CONVERT TO WAV
    # =========================
    def convert_to_wav(
        self, filepath: str, voice_dir: Path, target_sample_rate=24000, mono=True
    ) -> str:

        import gc
        import time
        from pydub import AudioSegment

        audio = AudioSegment.from_file(filepath)

        if mono:
            audio = audio.set_channels(1)

        audio = audio.set_frame_rate(target_sample_rate)

        out_path = voice_dir / "converted.wav"

        if out_path.exists():
            for _ in range(20):
                try:
                    out_path.unlink()
                    break
                except PermissionError:
                    time.sleep(0.05)

        audio.export(out_path, format="wav")

        del audio
        gc.collect()

        return str(out_path)

    # =========================
    # PROCESS AUDIO (CLEAN + NORMALIZE)
    # =========================
    def process_audio(self, filepath: str, voice_dir: Path, target_dBFS=-16.0) -> str:

        import gc
        import time
        from pydub import AudioSegment
        from pydub.effects import compress_dynamic_range

        audio = AudioSegment.from_file(filepath)

        audio = self.trimmer.trim(audio)

        duration_sec = len(audio) / 1000

        if duration_sec > 30:
            audio = audio[:30000]

        audio = compress_dynamic_range(audio, threshold=-24.0, ratio=3.0, attack=5.0, release=50.0)

        gain = target_dBFS - audio.dBFS
        audio = audio.apply_gain(gain)

        out_path = voice_dir / "normalized.wav"
        tmp_path = voice_dir / "normalized_tmp.wav"

        audio.export(tmp_path, format="wav")

        if out_path.exists():
            for _ in range(30):
                try:
                    out_path.unlink()
                    break
                except PermissionError:
                    time.sleep(0.05)

        for _ in range(30):
            try:
                tmp_path.replace(out_path)
                break
            except PermissionError:
                time.sleep(0.05)

        del audio
        gc.collect()

        return str(out_path)

    # =========================
    # PIPELINE
    # =========================
    def process_reference(self, filepath: str, backup=True) -> str:

        filepath = str(Path(filepath).resolve())

        # =========================
        # ALREADY-NORMALIZED CHECK
        # Если на вход подан уже готовый normalized.wav из библиотеки —
        # не прогоняем повторно через compress_dynamic_range + gain,
        # иначе каждый повтор накопительно "сжимает" файл и завышает SNR.
        # =========================
        if Path(filepath).name == "normalized.wav" and Path(filepath).is_relative_to(
            self.backup_dir
        ):
            try:
                raw_audio = AudioSegment.from_file(filepath)
                snr_result = self.snr_analyzer.analyze(raw_audio)
                if self.snr_callback and callable(self.snr_callback):
                    self.snr_callback(snr_result)
            except Exception as e:
                print(f"[SNR] Analysis failed (non-critical): {e}")

            print("[Reference] Уже нормализован — повторная обработка пропущена")
            return filepath

        voice_dir = self.get_voice_dir(filepath)

        if backup:
            self.save_original_copy(filepath, voice_dir)

        working = self.convert_to_wav(filepath, voice_dir)

        # =========================
        # SNR ANALYSIS — до нормализации, на сыром аудио
        # =========================
        try:
            raw_audio = AudioSegment.from_file(working)
            snr_result = self.snr_analyzer.analyze(raw_audio)
            if self.snr_callback and callable(self.snr_callback):
                self.snr_callback(snr_result)
        except Exception as e:
            print(f"[SNR] Analysis failed (non-critical): {e}")

        working = self.process_audio(working, voice_dir)

        return str(Path(working).resolve())
