from typing import List, Tuple
import re
import os
import sys
from datetime import datetime
from .prosody_layer import create_prosody_layer
from .word_replacer import WordReplacer
from .text_utils import is_list_item as _is_list_item

# =========================
# SAFE PYTHON ISOLATION
# =========================
os.environ["PYTHONHOME"] = ""
os.environ["PYTHONNOUSERSITE"] = "1"
os.environ["PYTHONEXECUTABLE"] = sys.executable

os.environ["PATH"] = (
    os.path.dirname(sys.executable)
    + os.pathsep
    + os.environ.get("PATH", "")
)

# =========================
# COQUI FIX (CRITICAL)
# =========================
os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["TTS_SKIP_UPDATE"] = "1"

# =========================
# OPTIONAL BACKEND
# =========================
try:
    from pydub import AudioSegment  # type: ignore
    PYDUB_OK = True
except ImportError:
    AudioSegment = None  # type: ignore
    PYDUB_OK = False

# =========================
# LOCAL MODULES
# =========================
from .normalizer import TextNormalizer
from .chunker import TextChunker
from .smart_pauses import SmartPauseEngine
from .reference_processor import ReferenceProcessor
from .de_esser import create_de_esser

# =========================
# BASE PATH
# =========================
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(__file__))

def path(*args):
    return os.path.join(BASE_DIR, *args)

# =========================
# OUTPUT NAMING
# =========================
import unicodedata as _unicodedata

def _make_output_name(text: str, output_dir: str) -> str:
    """Имя файла из первых слов исходного текста, защита от дублей."""
    snippet = (text or "").strip().replace("\n", " ").replace("\r", "")[:80]
    allowed = []
    for ch in snippet:
        cat = _unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("N") or ch == " ":
            allowed.append(ch)
    name = "".join(allowed).strip()
    if len(name) > 48:
        cut = name[:48].rsplit(" ", 1)
        name = cut[0] if len(cut) > 1 else name[:48]
    name = name.strip() or "output"
    base = os.path.join(output_dir, name)
    candidate = f"{base}.wav"
    counter = 1
    while os.path.exists(candidate):
        candidate = f"{base} ({counter}).wav"
        counter += 1
    return candidate

# =========================
# FFMPEG
# =========================
FFMPEG_DIR = path("ffmpeg", "bin")
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

if PYDUB_OK and AudioSegment is not None:
    AudioSegment.converter = path("ffmpeg", "bin", "ffmpeg.exe")
    AudioSegment.ffprobe   = path("ffmpeg", "bin", "ffprobe.exe")

# =========================
# COMPONENTS
# =========================
normalizer    = TextNormalizer()
chunker       = TextChunker()
pause_engine  = SmartPauseEngine()
ref_processor = ReferenceProcessor(backup_dir=path("library"))
word_replacer = WordReplacer(rules_path=path("word_rules.json"))

# =========================
# MODEL
# =========================
import threading as _threading

MODEL_DIR = path("models", "xtts_v2")

_tts_instance = None
_tts_lock = _threading.Lock()

def detect_lang_adaptive(text: str) -> str:
    return "ru" if any('\u0400' <= c <= '\u04FF' for c in text) else "en"

_device = None

def detect_device() -> str:
    global _device
    if _device is None:
        import torch  # type: ignore
        _device = "cuda" if torch.cuda.is_available() else "cpu"
    return _device


def get_tts():
    global _tts_instance

    with _tts_lock:
        if _tts_instance is None:
            print("[XTTS] Loading model...")

            from TTS.api import TTS  # type: ignore

            device = detect_device()

            _tts_instance = TTS(
                model_path=MODEL_DIR,
                config_path=os.path.join(MODEL_DIR, "config.json"),
            ).to(device)

            print(f"[XTTS] Model loaded ({device.upper()})")

    return _tts_instance

# =========================
# CANCELLATION EXCEPTION
# =========================
class _Cancelled(Exception):
    pass

# =========================
# EMBEDDING CACHE
# =========================
def _get_embedding(tts, ref_wav, cache_path):
    import torch  # type: ignore
    device = detect_device()

    if os.path.exists(cache_path):
        try:
            data = torch.load(cache_path, map_location=device)
            print("[XTTS] Embedding loaded from cache")
            return data["gpt_cond_latent"], data["speaker_embedding"]
        except Exception as e:
            print(f"[XTTS] Cache load failed, recomputing: {e}")

    print("[XTTS] Computing embedding...")
    gpt_cond_latent, speaker_embedding = (
        tts.synthesizer.tts_model.get_conditioning_latents(audio_path=ref_wav)
    )
    gpt_cond_latent = gpt_cond_latent.to(device)
    speaker_embedding = speaker_embedding.to(device)
    try:
        torch.save({
            "gpt_cond_latent":   gpt_cond_latent,
            "speaker_embedding": speaker_embedding
        }, cache_path)
        print("[XTTS] Embedding saved to cache")
    except Exception as e:
        print(f"[XTTS] Cache save failed: {e}")

    return gpt_cond_latent, speaker_embedding

# =========================
# CHUNK CACHE
# =========================
import hashlib

def _chunk_cache_key(chunk: str, lang: str, preset: dict, speed: float) -> str:
    raw = f"v3_lang_split|{chunk}|{lang}|{speed}|{sorted(preset.items())}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

def _chunk_cache_path(output_dir: str, key: str) -> str:
    cache_dir = os.path.join(output_dir, "_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{key}.wav")

def _chunk_cache_get(output_dir: str, key: str):
    p = _chunk_cache_path(output_dir, key)
    if os.path.exists(p):
        print(f"[CACHE] Hit: {key[:8]}...")
        return p
    return None

def _chunk_cache_set(output_dir: str, key: str, wav_path: str):
    dst = _chunk_cache_path(output_dir, key)
    try:
        import shutil
        shutil.copy2(wav_path, dst)
    except Exception as e:
        print(f"[CACHE] Save failed: {e}")

# =========================
# LIST DETECTION (для #2)
# =========================

def _is_dense_abbrev_chunk(text: str, threshold: float = 0.5) -> bool:
    """
    Экспериментальная проверка: высокая плотность коротких токенов
    (слогов аббревиатур типа 'цэ', 'пи', 'ю') в чанке. Такие чанки
    лишены естественных речевых якорей (глаголов, союзов), из-за чего
    модель быстрее "устаёт" к концу — артикуляция размывается.
    Срабатывает только на нетипичный контент: для обычной прозы
    такая плотность практически недостижима.
    """
    words = re.findall(r'\S+', text)
    if not words:
        return False
    short_words = sum(1 for w in words if len(w.strip(',.!?')) <= 3)
    return (short_words / len(words)) > threshold

def _adjust_params_for_chunk(base_params: dict, chunk_idx: int,
                              total_chunks: int, chunk_text: str) -> dict:
    """
    #2: temperature schedule для перечислений.
    На мелких list-item чанках слегка повышаем temperature
    к концу списка, компенсируя угасание тона.
    """
    params = dict(base_params)
    if _is_list_item(chunk_text):
        fatigue_comp = 0.02 * (chunk_idx / max(total_chunks, 1))
        if "temperature" in params:
            params["temperature"] = min(params["temperature"] + fatigue_comp, 0.92)
    elif _is_dense_abbrev_chunk(chunk_text):
        # экспериментальная компенсация для плотных серий аббревиатур —
        # без естественных речевых якорей модель быстрее теряет артикуляцию
        if "temperature" in params:
            params["temperature"] = min(params["temperature"] + 0.03, 0.92)
        if "repetition_penalty" in params:
            params["repetition_penalty"] = max(params["repetition_penalty"] - 1.0, 5.0)
    return params

# =========================
# LANGUAGE SPLIT (v2 — fixed)
# =========================
import re
from typing import List, Tuple

# Примечание по архитектуре:
# word_replacer.apply() вызывается ДО _split_by_language() в раннере и уже
# транслитерирует ИЗВЕСТНЫЕ термины (built-in словарь, включая многословные
# фразы типа "speaker embedding", + авто-кэш капс-аббревиатур) в кириллицу.
#
# Всё, что остаётся латиницей и доходит до этой функции, — либо неизвестный
# словарю термин, либо случайное английское слово. Намеренное решение:
# короткие EN-сегменты (< 3 слов) ВСЕГДА поглощаются в соседний RU-текст,
# даже если это похоже на технический термин (pydub, wav, soundfile).
#
# Причина: изолированный inference-вызов XTTS на 1-2 словах статистически
# даёт значительно больше артефактов (повторы, обрывы, "билиберда"), чем
# чуть менее точное произношение термина русской фонетикой внутри потока
# речи. Стабильность синтеза приоритетнее идеального произношения коротких
# терминов. Только сегменты из 3+ слов остаются отдельным EN-вызовом —
# на такой длине inference достаточно стабилен, и разборчивость важнее.
#
# Если термин должен звучать по-английски даже будучи коротким — правильное
# место для этого фикса: BUILTIN_DICTIONARY в word_replacer.py (явная
# транслитерация), а не эта функция.

_TOKEN_RE = re.compile(
    r'(?P<en>[A-Za-z][A-Za-z0-9\-]*)'
    r'|(?P<ru>[А-Яа-яЁё]+)'
    r'|(?P<num>\d+)'
    r'|(?P<punct>[^\w\s])'
    r'|(?P<space>\s+)',
    re.UNICODE
)


def _count_real_words(chunk: str) -> int:
    return sum(
        1 for w in re.findall(r'[A-Za-zА-Яа-яЁё]+', chunk)
        if len(w) >= 1
    )



def _split_by_language(text: str) -> List[Tuple[str, str]]:
    if not text.strip():
        return []

    raw_tokens = [
        (m.group(0), m.lastgroup) for m in _TOKEN_RE.finditer(text)
    ]
    if not raw_tokens:
        return []

    classified = []
    for tok, kind in raw_tokens:
        if kind == "space":
            classified.append((tok, "space"))
        elif kind == "en":
            classified.append((tok, "en"))
        elif kind == "ru":
            classified.append((tok, "ru"))
        else:
            classified.append((tok, None))

    if not classified:
        return []

    last_lang = None
    for i, (tok, lang) in enumerate(classified):
        if lang is not None and lang != "space":
            last_lang = lang
        elif lang is None:
            classified[i] = (tok, last_lang)

    next_lang = None
    for i in range(len(classified) - 1, -1, -1):
        _, lang = classified[i]
        if lang is not None and lang != "space":
            next_lang = lang
        elif lang is None and next_lang is not None:
            classified[i] = (classified[i][0], next_lang)
    classified = [
        (tok, lang if lang is not None else "ru")
        for tok, lang in classified
    ]

    merged = []
    for tok, lang in classified:
        if lang == "space":
            # Пробел наследует язык контекста, не создаёт новую границу
            if merged:
                merged[-1][0] += tok
            continue
        if merged and merged[-1][1] == lang:
            merged[-1][0] += tok
        else:
            merged.append([tok, lang])

    changed = True
    max_iterations = len(merged) + 1
    iteration = 0

    while changed and iteration < max_iterations:
        changed = False
        iteration += 1
        result = []
        i = 0

        while i < len(merged):
            chunk, lang = merged[i]

            should_absorb = (
                lang == "en"
                and _count_real_words(chunk) < 3
            )

            if not should_absorb:
                result.append([chunk, lang])
                i += 1
                continue

            absorbed = False

            if result and result[-1][1] == "ru":
                result[-1][0] += " " + chunk
                changed = True
                absorbed = True
            elif i + 1 < len(merged) and merged[i + 1][1] == "ru":
                merged[i + 1][0] = chunk + " " + merged[i + 1][0]
                changed = True
                absorbed = True

            if not absorbed:
                result.append([chunk, lang])

            i += 1

        merged = result

    return [
        (re.sub(r' {2,}', ' ', chunk).strip(), lang)
        for chunk, lang in merged
        if chunk.strip()
    ]

# =========================
# TEXT -> GUI CHUNK MAP
# =========================
def _normalize_lookup_text_with_map(text: str):
    norm_chars = []
    index_map = []
    prev_space = False

    for i, ch in enumerate(text or ""):
        if ch.isspace():
            if prev_space:
                continue
            norm_chars.append(" ")
            index_map.append(i)
            prev_space = True
        else:
            norm_chars.append(ch.lower())
            index_map.append(i)
            prev_space = False

    while norm_chars and norm_chars[0] == " ":
        norm_chars.pop(0)
        index_map.pop(0)

    while norm_chars and norm_chars[-1] == " ":
        norm_chars.pop()
        index_map.pop()

    return "".join(norm_chars), index_map


def _build_chunk_text_map(full_text: str, chunks: list) -> list:
    """
    Строит карту start/end для подсветки чанков в GUI.
    Индексы возвращаются относительно текста, который отправляется в GUI
    через stage='normalized_text'.
    """
    full_text = full_text or ""
    norm_text, text_map = _normalize_lookup_text_with_map(full_text)

    chunk_map = []
    search_from = 0
    last_end = 0
    text_len = len(full_text)

    for chunk in chunks:
        chunk_clean = (chunk or "").replace("[NO_PAUSE]", "").strip()
        norm_chunk, _ = _normalize_lookup_text_with_map(chunk_clean)

        if not norm_chunk or not norm_text or not text_map:
            chunk_map.append((last_end, last_end))
            continue

        idx = norm_text.find(norm_chunk, search_from)

        if idx == -1:
            idx = norm_text.find(norm_chunk)

        match_len = len(norm_chunk)

        if idx == -1:
            words = norm_chunk.split()
            for n in (10, 8, 6, 5, 4, 3, 2):
                if len(words) >= n:
                    probe = " ".join(words[:n])
                    idx = norm_text.find(probe, search_from)
                    if idx == -1:
                        idx = norm_text.find(probe)
                    if idx != -1:
                        match_len = len(norm_chunk)
                        break

        if idx == -1:
            chunk_map.append((last_end, last_end))
            continue

        end_norm = min(idx + match_len, len(text_map))
        start_orig = text_map[idx]

        if end_norm > idx:
            end_orig = text_map[end_norm - 1] + 1
        else:
            end_orig = start_orig

        start_orig = max(0, min(start_orig, text_len))
        end_orig = max(start_orig, min(end_orig, text_len))

        chunk_map.append((start_orig, end_orig))

        search_from = max(idx + 1, end_norm)
        last_end = end_orig

    return chunk_map

# =========================
# CHUNK QUALITY VALIDATORS
# =========================
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
    wav: list,
    sample_rate: int = 24000,
    window_sec: float = 0.3,
    threshold: float = 0.985
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

    global_rms = float(np.sqrt(np.mean(arr ** 2)))

    if global_rms < 1e-5:
        return False

    hop = max(1, window // 2)
    min_rms = max(global_rms * 0.25, 1e-5)
    hits = 0

    for pos in range(0, arr.size - window * 2, hop):
        a = arr[pos:pos + window]
        b = arr[pos + window:pos + window * 2]

        a_rms = float(np.sqrt(np.mean(a ** 2)))
        b_rms = float(np.sqrt(np.mean(b ** 2)))

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
    wav: list,
    chunk_text: str,
    sample_rate: int = 24000,
    min_sec_per_word: float = 0.16
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
    rms = float(np.sqrt(np.mean(arr ** 2)))

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

# =========================
# QUALITY PRESETS
# =========================

PROSODY_PRESETS = {
    "Высокое качество": dict(mode="balanced",     intensity=0.1),
    "Нарратив":         dict(mode="balanced",     intensity=0.5),
    "Динамика":         dict(mode="balanced",     intensity=1.1),
    "Экспрессия":       dict(mode="studio_ultra", intensity=1.3),
}

# =========================
# ADAPTIVE TRIM
# =========================
def _adaptive_trim(
    seg,
    chunk_text="",
    base_ms=100,
    mode="auto",
    range_ms=30,
    silence_thresh_db=-35.0
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
        chunk = seg[max(0, pos - step):pos]
        if chunk.dBFS > speech_thresh_db:
            artifact_end = pos
            break

    artifact_start = artifact_end

    # Ищем тишину перед артефактом/хвостом
    for pos in range(artifact_end, max(0, artifact_end - 500), -step):
        chunk = seg[max(0, pos - step):pos]
        if chunk.dBFS <= tail_silence_thresh:
            artifact_start = pos
            break

    silence_start = artifact_start

    # Ищем последнюю речь перед тишиной
    for pos in range(artifact_start, max(0, artifact_start - 500), -step):
        chunk = seg[max(0, pos - step):pos]
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
        return seg[:-int(trim_ms)].fade_out(min(40, int(trim_ms)))

    return seg

# =========================
# LOUDNESS NORMALIZATION (numpy, no deps)
# =========================
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

    rms = float(np.sqrt(np.mean(active ** 2)))

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

    rms = float(np.sqrt(np.mean(active ** 2)))

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

# =========================
# ENGINE
# =========================
def run_tts(
    text,
    ref_path,
    raw_text=None,
    model_key=None,
    status_callback=None,
    is_cancelled=None,
    speed=1.0,
    language="auto",
    quality="Высокое качество",
    quality_params=None
):
    def cancelled() -> bool:
        return bool(callable(is_cancelled) and is_cancelled())

    def send(stage, progress=None, text_msg=None, final=None):
        if status_callback:
            status_callback({
                "stage":    stage,
                "progress": progress,
                "text":     text_msg,
                "final":    final,
            })

    def cleanup(files: list):
        for f in files:
            try:
                os.remove(f)
            except Exception:
                pass
            

    import time
    gen_start = time.time()

    try:
        tts = get_tts()

        # =========================
        # REFERENCE (0–10%)
        # =========================
        if cancelled(): raise _Cancelled()
        send("reference", 0, "Обработка reference...")
        ref_wav = ref_processor.process_reference(ref_path)
        send("reference", 10)

        # =========================
        # NORMALIZE (10–20%)
        # =========================
        if cancelled(): raise _Cancelled()
        send("normalize", 10, "Нормализация текста...")
        text = normalizer.normalize(text)
        text = normalizer.safe_character_filter(text)

        # отправляем финальный текст в GUI для обновления text_box
        send("normalized_text", 20, text_msg=text)
        send("normalize", 20)

        # ждём подтверждения от GUI что text_box обновлён
        import time as _time
        if status_callback:
            textbox_ready = False
            for _ in range(10):
                try:
                    textbox_ready = bool(status_callback({"stage": "check_textbox_ready"}))
                except Exception:
                    textbox_ready = False
                    break

                if textbox_ready:
                    break

                _time.sleep(0.03)

            if not textbox_ready:
                _time.sleep(0.1)
        else:
            _time.sleep(0.1)

        # =========================
        # CHUNKING (20–30%)
        # =========================
        if cancelled(): raise _Cancelled()
        send("chunking", 20, "Разбиение текста...")

        chunks_before_prosody = chunker.chunk_text(text)
        map_text = text
        chunk_map = _build_chunk_text_map(map_text, chunks_before_prosody)

        lang_detected = detect_lang_adaptive(text)
        prosody_preset = PROSODY_PRESETS.get(
            quality,
            PROSODY_PRESETS["Высокое качество"]
        )
        prosody_intensity = quality_params.get("prosody_intensity", prosody_preset["intensity"]) if quality_params else prosody_preset["intensity"]
        prosody_engine = create_prosody_layer(
            mode=str(prosody_preset["mode"]),
            intensity=float(prosody_intensity),
            breath_length="medium"
        )
        # #4: process_chunks учитывает контекст серий list-item чанков
        chunks = prosody_engine.process_chunks(chunks_before_prosody, lang=lang_detected)

        send("chunking", 30)

        output_dir = path("outputs")
        os.makedirs(output_dir, exist_ok=True)

        final_path = _make_output_name(raw_text or text, output_dir)

        total = max(len(chunks), 1)
        chunk_items = []

        # =========================
        # GENERATION (30–90%)
        # =========================
        send("generate", 30, "Генерация аудио...")

        cache_path = os.path.splitext(ref_wav)[0] + "_embedding.pth"
        gpt_cond_latent, speaker_embedding = _get_embedding(tts, ref_wav, cache_path)

        for i, chunk in enumerate(chunks):

            if cancelled():
                cleanup([item["path"] for item in chunk_items])
                raise _Cancelled()

            if len(chunk.strip()) < 5:
                print(f"[SKIP] chunk {i} too short: {repr(chunk)}")
                continue

            start, end = chunk_map[i] if i < len(chunk_map) else (0, 0)
            print(f"[MAP] chunk={i} start={start} end={end} map_text[start:start+40]={repr(map_text[start:start+40])}")

            if status_callback:
                raw_chunk = chunks_before_prosody[i] if i < len(chunks_before_prosody) else chunk
                status_callback({
                    "stage": "chunk",
                    "chunk_index": i,
                    "chunk_start": start,
                    "chunk_end": end,
                    "chunk_raw": raw_chunk,
                })

            chunk_path = os.path.join(output_dir, f"_chunk_{i}.wav")
            lang = detect_lang_adaptive(chunk) if language == "auto" else language

            print(f"[Chunk {i+1}/{total}] {chunk}")

            try:
                preset = dict(quality_params or {})

                speed_value = preset.pop("speed", speed)

                trim_ms = int(preset.pop("trim_ms", 80) or 0)
                trim_mode = str(preset.pop("trim_mode", "auto") or "auto").lower()

                # их нельзя передавать в XTTS inference.
                preset.pop("prosody_intensity", None)
                preset.pop("trim_range_ms", None)
                preset.pop("silence_thresh_db", None)
                preset.pop("qc_enabled", None)
                preset.pop("de_esser_intensity", None)
                preset.pop("word_replacer_enabled", None)
                preset.pop("lang_split_enabled", None)

                # #2: temperature schedule — компенсация угасания на перечислениях
                preset = _adjust_params_for_chunk(preset, i, total, chunk)

                no_pause_flag = "[NO_PAUSE]" in chunk
                clean_chunk = chunk.replace("[NO_PAUSE]", "").strip()

                print(f"[WR] word_replacer_enabled={quality_params.get('word_replacer_enabled') if quality_params else None}")
                if quality_params is None or quality_params.get("word_replacer_enabled", True):
                    clean_chunk = word_replacer.apply(clean_chunk)

                import soundfile as sf  # type: ignore

                # =========================
                # CHUNK CACHE — проверяем до генерации
                # =========================
                cache_key = _chunk_cache_key(chunk, lang, preset, speed_value)
                cached = _chunk_cache_get(output_dir, cache_key)
                print(f"[CACHE CHECK] key={cache_key[:8]} cached={cached}")

                if cached:
                    import shutil
                    try:
                        shutil.copy2(cached, chunk_path)
                    except Exception as ce:
                        print(f"[CACHE COPY ERROR] {ce}")
                        cached = None

                if cached:
                    chunk_items.append({
                        "path": chunk_path,
                        "source_text": chunks_before_prosody[i] if i < len(chunks_before_prosody) else chunk,
                        "processed_text": chunks[i] if i < len(chunks) else chunk,
                        "no_pause": no_pause_flag,
                    })
                    progress = 30 + int((i + 1) / total * 60)
                    send("generate", progress)
                    continue

                # Перегенерация при браке (повторы / слишком короткое)
                qc_enabled = bool(quality_params.get("qc_enabled", True)) if quality_params else True
                max_attempts = 3 if qc_enabled else 1
                wav = None

                # Разбиваем на подчанки по языку только если язык auto
                lang_split = quality_params.get("lang_split_enabled", True) if quality_params else True
                if language == "auto" and lang_split:
                    subchunks = _split_by_language(clean_chunk)
                else:
                    subchunks = [(clean_chunk, lang)]
                print(f"[LANG] lang_split={lang_split} language={language} subchunks={[(t[:20], l) for t, l in subchunks]}")

                import numpy as np  # type: ignore
                wav_parts = []

                for sub_text, sub_lang in subchunks:
                    sub_preset = dict(preset)
                    sub_wav = None
                    candidate = None

                    for attempt in range(max_attempts):
                        out = tts.synthesizer.tts_model.inference(
                            text=sub_text,
                            language=sub_lang,
                            gpt_cond_latent=gpt_cond_latent,
                            speaker_embedding=speaker_embedding,
                            speed=speed_value,
                            **sub_preset
                        )

                        candidate = out["wav"]
                        if hasattr(candidate, 'device'):
                            candidate = candidate.cpu()

                        has_repeats = _detect_repeats(candidate)
                        bad_duration = _validate_duration(candidate, sub_text)

                        if not has_repeats and not bad_duration:
                            sub_wav = candidate
                            break

                        print(
                            f"[QC] Chunk {i+1} sub '{sub_text}' attempt {attempt+1}/{max_attempts} rejected"
                            f" (repeats={has_repeats}, bad_duration={bad_duration})"
                        )

                        if "temperature" in sub_preset:
                            sub_preset["temperature"] = min(sub_preset["temperature"] + 0.05, 0.95)

                    if sub_wav is None:
                        print(f"[QC] sub '{sub_text}' — all attempts failed, using last result")
                        sub_wav = candidate

                    if sub_wav is not None:
                        wav_parts.append(np.array(sub_wav, dtype=np.float32))

                if wav_parts:
                    wav = np.concatenate(wav_parts).tolist()
                else:
                    wav = []

                # Не режем здесь, если доступен pydub.
                if not PYDUB_OK:
                    if trim_mode not in ("off", "none", "disable", "disabled", "false", "0"):
                        trim_samples = int(24000 * trim_ms / 1000)
                        if trim_samples > 0 and len(wav) > trim_samples:
                            wav = wav[:-trim_samples]

                sf.write(chunk_path, wav, 24000)

                # сохраняем в кэш
                _chunk_cache_set(output_dir, cache_key, chunk_path)

                chunk_items.append({
                    "path": chunk_path,
                    "source_text": chunks_before_prosody[i] if i < len(chunks_before_prosody) else chunk,
                    "processed_text": chunks[i] if i < len(chunks) else chunk,
                    "no_pause": no_pause_flag,
                })

            except Exception as e:
                import traceback
                print(f"[Chunk {i} error]: {e}")
                print(traceback.format_exc())

            progress = 30 + int((i + 1) / total * 60)
            send("generate", progress)

        # проверка после завершения цикла
        if not chunk_items:
            raise RuntimeError("No chunks were generated")

        # =========================
        # MERGE (90–100%)
        # =========================
        if cancelled():
            cleanup([item["path"] for item in chunk_items])
            raise _Cancelled()

        send("merge", 90, "Сборка аудио...")

        if PYDUB_OK and chunk_items:
            combined = AudioSegment.empty()  # type: ignore

            valid_segments = []
            valid_chunks = []
            valid_no_pause_flags = []

            trim_ms = int(quality_params.get("trim_ms", 80)) if quality_params else 80
            trim_mode = quality_params.get("trim_mode", "auto") if quality_params else "auto"
            trim_range_ms = int(quality_params.get("trim_range_ms", 15)) if quality_params else 15
            silence_thresh_db = float(quality_params.get("silence_thresh_db", -35.0)) if quality_params else -35.0

            for i, item in enumerate(chunk_items):
                try:
                    seg = AudioSegment.from_wav(item["path"])  # type: ignore

                    if len(seg) < 50:
                        continue

                    seg = _adaptive_trim(
                        seg,
                        chunk_text=item["source_text"],
                        base_ms=trim_ms,
                        mode=trim_mode,
                        range_ms=trim_range_ms,
                        silence_thresh_db=silence_thresh_db
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
                        pause_ms = pause_engine.get_pause_ms(valid_chunks[i], next_chunk)
                        combined += AudioSegment.silent(pause_ms)  # type: ignore

            # De-essing — подавление избыточных шипящих на финальном файле
            de_esser_intensity = quality_params.get("de_esser_intensity", 1.0) if quality_params else 1.0
            if de_esser_intensity > 0:
                try:
                    de_esser = create_de_esser(intensity=de_esser_intensity, sample_rate=24000)
                    combined = de_esser.process_segment(combined)
                except Exception as e:
                    print(f"[De-esser] Failed, skipping: {e}")

            combined += AudioSegment.silent(200)  # type: ignore
            combined = combined.fade_out(80)

            if combined.dBFS != float("-inf"):
                combined = combined.apply_gain(-18.0 - combined.dBFS)

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
                        next_text = chunk_items[i + 1]["processed_text"] if i + 1 < len(chunk_items) else ""
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

        send("generate", 100)

        # статистика
        gen_elapsed = int(time.time() - gen_start)
        voice_name = os.path.basename(os.path.dirname(ref_wav))
        if voice_name.replace("-", "").replace("_", "").isdigit() or "output_" in voice_name:
            voice_name = os.path.splitext(os.path.basename(ref_path))[0]

        if status_callback:
            status_callback({
                "stage":    "stats",
                "progress": 100,
                "time_sec": gen_elapsed,
                "chunks": len(chunk_items),
                "speed":    speed,
                "voice":    voice_name,
                "quality":  quality,
                "text_len": len(text),
            })

        return final_path

    except _Cancelled:
        return None

    except Exception as e:
        raise RuntimeError(f"XTTS ENGINE ERROR: {str(e)}") from e