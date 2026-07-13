from typing import Any, List, Optional, Tuple
import re
import os
import sys
import time
from datetime import datetime
import unicodedata as _unicodedata
import threading as _threading
import hashlib
import torch
import gc


def _wav_to_mono_float(wav):
    import numpy as np  # type: ignore

    arr = np.asarray(wav, dtype=np.float32)

    if arr.ndim > 1:
        arr = arr.mean(axis=1)

    arr = arr.reshape(-1)

    if arr.size == 0:
        return arr

    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def _detect_repeats(
    wav: list, sample_rate: int = 24000, window_sec: float = 0.3, threshold: float = 0.985
) -> bool:
    """
    Детектирует зацикливание/повторы.
    Возвращает True, если обнаружен брак.
    """
    import numpy as np  # type: ignore

    arr = _wav_to_mono_float(wav)
    sample_rate = int(sample_rate or 24000)

    window = max(1, int(window_sec * sample_rate))

    if arr.size < window * 3:
        return False

    global_rms = float(np.sqrt(np.mean(arr**2)))

    if global_rms < 1e-5:
        return False

    hop = max(1, window // 2)
    min_rms = max(global_rms * 0.25, 1e-5)
    hits = 0

    for pos in range(0, arr.size - window * 2, hop):
        a = arr[pos : pos + window]
        b = arr[pos + window : pos + window * 2]

        a_rms = float(np.sqrt(np.mean(a**2)))
        b_rms = float(np.sqrt(np.mean(b**2)))

        if a_rms < min_rms or b_rms < min_rms:
            hits = 0
            continue

        rms_ratio = min(a_rms, b_rms) / max(a_rms, b_rms)

        if rms_ratio < 0.75:
            hits = 0
            continue

        a = a - float(np.mean(a))
        b = b - float(np.mean(b))

        denom = float(np.linalg.norm(a) * np.linalg.norm(b))

        if denom < 1e-8:
            hits = 0
            continue

        corr = float(np.dot(a, b) / denom)

        if corr > threshold:
            hits += 1

            if hits >= 2 or corr > 0.995:
                print(f"[QC] Repeat detected at {pos / sample_rate:.1f}s (corr={corr:.3f})")
                return True
        else:
            hits = 0

    return False


def _validate_duration(
    wav: list, chunk_text: str, sample_rate: int = 24000, min_sec_per_word: float = 0.16
) -> bool:
    """
    Проверяет базовую валидность длительности и сигнала.
    Возвращает True, если чанк подозрительный/бракованный.
    """
    import re
    import numpy as np  # type: ignore

    arr = _wav_to_mono_float(wav)
    sample_rate = int(sample_rate or 24000)

    if arr.size == 0:
        print("[QC] Empty audio")
        return True

    duration = arr.size / float(sample_rate)

    if duration < 0.12:
        print(f"[QC] Audio too short: {duration:.2f}s")
        return True

    peak = float(np.max(np.abs(arr)))
    rms = float(np.sqrt(np.mean(arr**2)))

    if peak < 1e-4 or rms < 2e-5:
        print(f"[QC] Audio is almost silent: peak={peak:.6f}, rms={rms:.6f}")
        return True

    clean_text = re.sub(r"\[[A-Z_]+\]", " ", chunk_text or "")
    words = len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", clean_text))

    if words <= 0:
        return False

    if words <= 3:
        min_expected = max(0.25, words * 0.12)
    else:
        min_expected = max(0.45, words * min_sec_per_word)

    if duration < min_expected:
        print(
            f"[QC] Duration too short: {duration:.2f}s for {words} words "
            f"(min {min_expected:.2f}s)"
        )
        return True

    max_expected = max(8.0, words * 1.25 + 2.0)

    if duration > max_expected:
        print(
            f"[QC] Duration too long: {duration:.2f}s for {words} words "
            f"(max {max_expected:.2f}s)"
        )
        return True

    return False


def _adaptive_trim(
    seg, chunk_text="", base_ms=100, mode="auto", range_ms=30, silence_thresh_db=-35.0
):
    if len(seg) < 100:
        return seg

    mode = str(mode or "auto").lower()

    if mode in ("off", "none", "disable", "disabled", "false", "0"):
        return seg

    base_ms = int(base_ms or 0)
    range_ms = int(range_ms or 0)

    if base_ms <= 0:
        return seg

    if mode == "manual":
        if len(seg) > base_ms:
            return seg[:-base_ms].fade_out(min(40, base_ms))
        return seg

    text = chunk_text.strip()

    if text and text[-1] in ".!?":
        keep_silence_ms = 120
    elif text and text[-1] == ",":
        keep_silence_ms = 60
    else:
        keep_silence_ms = 80

    speech_thresh_db = silence_thresh_db
    tail_silence_thresh = silence_thresh_db - 10

    step = 10
    max_trim = base_ms + range_ms

    artifact_end = len(seg)

    # Ищем последнюю речь в хвосте
    for pos in range(len(seg), max(0, len(seg) - 300), -step):
        chunk = seg[max(0, pos - step) : pos]
        if chunk.dBFS > speech_thresh_db:
            artifact_end = pos
            break

    artifact_start = artifact_end

    # Ищем тишину перед артефактом/хвостом
    for pos in range(artifact_end, max(0, artifact_end - 500), -step):
        chunk = seg[max(0, pos - step) : pos]
        if chunk.dBFS <= tail_silence_thresh:
            artifact_start = pos
            break

    silence_start = artifact_start

    # Ищем последнюю речь перед тишиной
    for pos in range(artifact_start, max(0, artifact_start - 500), -step):
        chunk = seg[max(0, pos - step) : pos]
        if chunk.dBFS > speech_thresh_db:
            silence_start = pos
            break

    cut_point = silence_start + keep_silence_ms
    trim_ms = len(seg) - cut_point

    # Важно: не заставляем auto-trim резать минимум всегда.
    # Иначе он может съедать окончания слов, если тишина не найдена.
    if trim_ms <= 0:
        return seg

    trim_ms = min(trim_ms, max_trim)

    if trim_ms > 0 and len(seg) > trim_ms:
        return seg[: -int(trim_ms)].fade_out(min(40, int(trim_ms)))

    return seg


def _normalize_loudness(seg, target_lufs: float = -23.0):
    """
    Выравнивание громкости чанков по активной речи.
    Используется RMS-gate + защита от клиппинга.
    """
    import numpy as np  # type: ignore

    if seg is None or len(seg) <= 0:
        return seg

    if seg.dBFS == float("-inf"):
        return seg

    samples = seg.get_array_of_samples()
    arr = np.asarray(samples, dtype=np.float32)

    if arr.size == 0:
        return seg

    channels = max(1, int(getattr(seg, "channels", 1) or 1))

    if channels > 1 and arr.size % channels == 0:
        arr = arr.reshape((-1, channels)).mean(axis=1)

    full_scale = float(2 ** (seg.sample_width * 8 - 1))

    if full_scale <= 0:
        return seg

    arr = arr / full_scale
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)

    peak = float(np.max(np.abs(arr)))

    if peak < 1e-6:
        return seg

    gate = 10 ** (-45.0 / 20.0)
    active = arr[np.abs(arr) >= gate]

    if active.size < max(32, int(arr.size * 0.01)):
        active = arr

    rms = float(np.sqrt(np.mean(active**2)))

    if rms < 1e-8:
        return seg

    current_db = 20.0 * np.log10(rms + 1e-12)
    target_db = float(target_lufs)

    gain_db = target_db - current_db

    # Не даём слишком сильно разгонять тихие чанки и слишком давить громкие.
    gain_db = max(-12.0, min(10.0, gain_db))

    peak_db = 20.0 * np.log10(peak + 1e-12)
    max_peak_db = -1.0

    if peak_db + gain_db > max_peak_db:
        gain_db = max_peak_db - peak_db

    if abs(gain_db) < 0.1:
        return seg

    return seg.apply_gain(gain_db)


def _normalize_numpy_audio(data, target_dbfs: float = -23.0):
    """
    Fallback-нормализация для режима без pydub.
    """
    import numpy as np  # type: ignore

    arr = np.asarray(data, dtype=np.float32)

    if arr.size == 0:
        return data

    mono = arr.mean(axis=1) if arr.ndim > 1 else arr
    mono = np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0)

    peak = float(np.max(np.abs(mono)))

    if peak < 1e-6:
        return data

    gate = 10 ** (-45.0 / 20.0)
    active = mono[np.abs(mono) >= gate]

    if active.size < max(32, int(mono.size * 0.01)):
        active = mono

    rms = float(np.sqrt(np.mean(active**2)))

    if rms < 1e-8:
        return data

    current_db = 20.0 * np.log10(rms + 1e-12)
    gain_db = float(target_dbfs) - current_db
    gain_db = max(-12.0, min(10.0, gain_db))

    peak_db = 20.0 * np.log10(peak + 1e-12)

    if peak_db + gain_db > -1.0:
        gain_db = -1.0 - peak_db

    gain = 10.0 ** (gain_db / 20.0)
    out = arr * gain

    return np.clip(out, -0.999, 0.999).astype(np.float32)
