from typing import Any, List, Optional, Tuple
import re
import os
import sys
import time

try:
    from pydub import AudioSegment  # type: ignore

    PYDUB_OK = True
except ImportError:
    AudioSegment = None  # type: ignore
    PYDUB_OK = False

from ..de_esser import create_de_esser
from .utils import _Cancelled
from .qc import _adaptive_trim, _normalize_loudness, _normalize_numpy_audio


def export_audio(
    chunk_items,
    quality_params,
    final_path,
    ai_conductor_enabled,
    conductor_map,
    pause_engine,
    cleanup,
    send,
    cancelled,
):
    # =========================
    # MERGE (90–100%)
    # =========================
    if cancelled():
        raise _Cancelled()

    send("merge", 90, "Сборка аудио...")

    if PYDUB_OK and chunk_items:
        assert AudioSegment is not None
        combined = AudioSegment.empty()  # type: ignore

        valid_segments = []
        valid_chunks = []
        valid_no_pause_flags = []

        trim_ms = int(quality_params.get("trim_ms", 80)) if quality_params else 80
        trim_mode = quality_params.get("trim_mode", "auto") if quality_params else "auto"
        trim_range_ms = int(quality_params.get("trim_range_ms", 15)) if quality_params else 15
        silence_thresh_db = (
            float(quality_params.get("silence_thresh_db", -35.0)) if quality_params else -35.0
        )

        for i, item in enumerate(chunk_items):
            if not os.path.isfile(item["path"]):
                print(f"[Merge] Skipping missing chunk: {item['path']}")
                continue
            try:
                seg = AudioSegment.from_wav(item["path"])

                if len(seg) < 50:
                    continue

                seg = _adaptive_trim(
                    seg,
                    chunk_text=item["source_text"],
                    base_ms=trim_ms,
                    mode=trim_mode,
                    range_ms=trim_range_ms,
                    silence_thresh_db=silence_thresh_db,
                )

                # Loudness normalization (RMS-based, выравнивает воспринимаемую громкость)
                if seg.dBFS != float("-inf"):
                    seg = _normalize_loudness(seg, target_lufs=-23.0)

                valid_segments.append(seg)
                valid_chunks.append(item["processed_text"])
                valid_no_pause_flags.append(item.get("no_pause", False))

            except Exception as e:
                print(f"[Merge chunk load error {i}]: {e}")

        for i, seg in enumerate(valid_segments):
            combined += seg
            if i != len(valid_segments) - 1:
                if valid_no_pause_flags[i]:
                    pass
                else:
                    next_chunk = valid_chunks[i + 1] if i + 1 < len(valid_chunks) else ""
                    if ai_conductor_enabled and conductor_map and i < len(conductor_map):
                        pause_ms = conductor_map[i].get("pause_after_ms", 350)
                    else:
                        pause_ms = pause_engine.get_pause_ms(valid_chunks[i], next_chunk)
                    combined += AudioSegment.silent(pause_ms)  # type: ignore

        # De-essing — подавление избыточных шипящих на финальном файле
        de_esser_intensity = (
            quality_params.get("de_esser_intensity", 1.0) if quality_params else 1.0
        )
        if de_esser_intensity > 0:
            try:
                de_esser = create_de_esser(intensity=de_esser_intensity, sample_rate=24000)
                combined = de_esser.process_segment(combined)
            except Exception as e:
                print(f"[De-esser] Failed, skipping: {e}")

        combined += AudioSegment.silent(300)  # type: ignore
        combined = combined.fade_out(200)

        if combined.dBFS != float("-inf"):
            combined = combined.apply_gain(-18.0 - combined.dBFS)

        export_format = (quality_params or {}).get("export_format", "wav")
        if export_format == "mp3":
            mp3_path = os.path.splitext(final_path)[0] + ".mp3"
            combined.export(mp3_path, format="mp3", bitrate="192k")
            final_path = mp3_path
        else:
            combined.export(final_path, format="wav")

        cleanup([item["path"] for item in chunk_items])

    else:
        if not chunk_items:
            raise RuntimeError("No audio chunks generated")

        try:
            import soundfile as sf  # type: ignore

            import numpy as np  # type: ignore

            audio_parts = []
            sample_rate = None

            for i, item in enumerate(chunk_items):
                data, sr = sf.read(item["path"], dtype="float32")

                if sample_rate is None:
                    sample_rate = sr
                elif sr != sample_rate:
                    raise RuntimeError(f"Sample rate mismatch: {sr} != {sample_rate}")

                data = _normalize_numpy_audio(data, target_dbfs=-23.0)
                audio_parts.append(data)

                if i != len(chunk_items) - 1:
                    next_text = (
                        chunk_items[i + 1]["processed_text"] if i + 1 < len(chunk_items) else ""
                    )
                    if ai_conductor_enabled and conductor_map and i < len(conductor_map):
                        pause_ms = conductor_map[i].get("pause_after_ms", 350)
                    else:
                        pause_ms = pause_engine.get_pause_ms(item["processed_text"], next_text)
                    silence_samples = int(sample_rate * pause_ms / 1000)

                    if data.ndim == 1:
                        silence = np.zeros((silence_samples,), dtype="float32")
                    else:
                        silence = np.zeros((silence_samples, data.shape[1]), dtype="float32")

                    audio_parts.append(silence)

            combined = np.concatenate(audio_parts, axis=0)
            sf.write(final_path, combined, sample_rate)

            cleanup([item["path"] for item in chunk_items])

        except Exception as e:
            cleanup([item["path"] for item in chunk_items])
            raise RuntimeError(f"Fallback merge failed: {e}") from e

    return final_path
