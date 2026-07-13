"""
de_esser.py — подавление избыточных шипящих/свистящих частот (С/Ш/Ц/Щ/Ть)
в синтезированной речи.

Работает поверх pydub.AudioSegment, без scipy/librosa — только numpy,
по аналогии с SNRAnalyzer из reference_processor.py.

Принцип: split-band dynamic shelving.
  1. Бьём сигнал на фреймы (~20ms, как в SNRAnalyzer).
  2. Для каждого фрейма считаем energy в "сибилянтной" полосе (4-9 kHz)
     относительно энергии всего фрейма.
  3. Если доля сибилянтной энергии превышает порог — ослабляем именно
     высокочастотную часть этого фрейма (а не весь сигнал), пропорционально
     превышению (мягкий gain reduction, не hard cut).
  4. Высокочастотная составляющая выделяется простым FFT-фильтром
     (без IIR, без scipy.signal) — берём rfft фрейма, зануляем/ослабляем
     бины вне полосы, обратное преобразование, вычитаем из оригинала
     остаток-усиление.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pydub import AudioSegment


class DeEsser:
    def __init__(
        self,
        sample_rate: int = 24000,
        low_hz: float = 4000.0,
        high_hz: float = 9000.0,
        frame_ms: float = 20.0,
        threshold: float = 0.35,
        intensity: float = 1.0,
        max_reduction_db: float = 9.0,
    ):
        self.sample_rate = sample_rate
        self.low_hz = low_hz
        self.high_hz = high_hz
        self.frame_ms = frame_ms
        self.threshold = threshold
        self.intensity = max(0.0, intensity)
        self.max_reduction_db = max_reduction_db

    def process_array(self, arr: "np.ndarray", sample_rate: int) -> "np.ndarray":
        if self.intensity <= 0.0:
            return arr

        if arr.ndim != 1:
            arr = arr.reshape(-1)

        frame_size = max(int(sample_rate * self.frame_ms / 1000.0), 64)
        n = len(arr)
        if n < frame_size * 2:
            return arr

        hop = frame_size // 2
        window = np.hanning(frame_size).astype(np.float32)

        out = np.zeros(n, dtype=np.float32)
        weight = np.zeros(n, dtype=np.float32)

        freqs = np.fft.rfftfreq(frame_size, d=1.0 / sample_rate)
        band_mask = (freqs >= self.low_hz) & (freqs <= self.high_hz)

        if not np.any(band_mask):
            return arr

        pos = 0
        while pos + frame_size <= n:
            frame = arr[pos : pos + frame_size] * window

            spec = np.fft.rfft(frame)
            mag = np.abs(spec)

            total_energy = float(np.sum(mag**2)) + 1e-9
            band_energy = float(np.sum(mag[band_mask] ** 2))
            band_ratio = band_energy / total_energy

            if band_ratio > self.threshold:
                excess = band_ratio - self.threshold
                reduction_db = min(excess * 40.0 * self.intensity, self.max_reduction_db)
                gain = 10.0 ** (-reduction_db / 20.0)
                spec[band_mask] *= gain

            processed_frame = np.fft.irfft(spec, n=frame_size).astype(np.float32)

            out[pos : pos + frame_size] += processed_frame
            weight[pos : pos + frame_size] += window

            pos += hop

        weight[weight < 1e-6] = 1.0
        out = out / weight

        if pos < n:
            out[pos:] = arr[pos:]

        return out

    def process_segment(self, seg: "AudioSegment") -> "AudioSegment":
        if self.intensity <= 0.0:
            return seg

        import array

        from pydub import AudioSegment

        if len(seg) < 50:
            return seg

        channels = seg.channels
        sample_width = seg.sample_width
        frame_rate = seg.frame_rate
        max_val = float(2 ** (sample_width * 8 - 1))

        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)

        if channels > 1:
            samples = samples.reshape(-1, channels)
            processed_channels = []
            for ch in range(channels):
                ch_arr = samples[:, ch] / max_val
                ch_processed = self.process_array(ch_arr, frame_rate)
                processed_channels.append(ch_processed)
            processed = np.stack(processed_channels, axis=1).reshape(-1)
        else:
            arr = samples / max_val
            processed = self.process_array(arr, frame_rate)

        processed = np.clip(processed, -1.0, 1.0)
        processed_int = (processed * max_val).astype(np.int16 if sample_width == 2 else np.int32)

        out_seg = AudioSegment(
            data=array.array("h" if sample_width == 2 else "i", processed_int.tolist()).tobytes(),
            sample_width=sample_width,
            frame_rate=frame_rate,
            channels=channels,
        )
        return out_seg


def create_de_esser(intensity: float = 1.0, sample_rate: int = 24000) -> DeEsser:
    return DeEsser(sample_rate=sample_rate, intensity=intensity)
