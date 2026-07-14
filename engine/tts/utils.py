from .device import detect_device
from engine.text_utils import is_list_item as _is_list_item
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


if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def path(*args):
    return os.path.join(BASE_DIR, *args)


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


def detect_lang_adaptive(text: str) -> str:
    return "ru" if any("\u0400" <= c <= "\u04FF" for c in text) else "en"


class _Cancelled(Exception):
    pass


def _is_dense_abbrev_chunk(text: str, threshold: float = 0.5) -> bool:
    """
    Экспериментальная проверка: высокая плотность коротких токенов
    (слогов аббревиатур типа 'цэ', 'пи', 'ю') в чанке. Такие чанки
    лишены естественных речевых якорей (глаголов, союзов), из-за чего
    модель быстрее "устаёт" к концу — артикуляция размывается.
    Срабатывает только на нетипичный контент: для обычной прозы
    такая плотность практически недостижима.
    """
    words = re.findall(r"\S+", text)
    if not words:
        return False
    short_words = sum(1 for w in words if len(w.strip(",.!?")) <= 3)
    return (short_words / len(words)) > threshold


def _adjust_params_for_chunk(
    base_params: dict, chunk_idx: int, total_chunks: int, chunk_text: str
) -> dict:
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


def _count_real_words(chunk: str) -> int:
    return sum(1 for w in re.findall(r"[A-Za-zА-Яа-яЁё]+", chunk) if len(w) >= 1)


_TOKEN_RE = re.compile(
    r"(?P<en>[A-Za-z][A-Za-z0-9\-]*)"
    r"|(?P<ru>[А-Яа-яЁё]+)"
    r"|(?P<num>\d+)"
    r"|(?P<punct>[^\w\s])"
    r"|(?P<space>\s+)",
    re.UNICODE,
)


def _split_by_language(text: str, base_lang: str = "ru") -> List[Tuple[str, str]]:
    if not text.strip():
        return []

    raw_tokens = [(m.group(0), m.lastgroup) for m in _TOKEN_RE.finditer(text)]
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
    classified = [(tok, lang if lang is not None else base_lang) for tok, lang in classified]

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

            should_absorb = lang == "en" and _count_real_words(chunk) <= 3

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

    return [(re.sub(r" {2,}", " ", chunk).strip(), lang) for chunk, lang in merged if chunk.strip()]


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


def _get_embedding(tts, ref_wav, cache_path):
    if torch is None:
        raise RuntimeError("torch not available")

    device = detect_device()

    if os.path.exists(cache_path):
        try:
            data = torch.load(cache_path, map_location=device)
            print("[XTTS] Embedding loaded from cache")
            return data["gpt_cond_latent"], data["speaker_embedding"]
        except Exception as e:
            print(f"[XTTS] Cache load failed, recomputing: {e}")

    print("[XTTS] Computing embedding...")
    gpt_cond_latent, speaker_embedding = tts.synthesizer.tts_model.get_conditioning_latents(
        audio_path=ref_wav
    )
    gpt_cond_latent = gpt_cond_latent.to(device)
    speaker_embedding = speaker_embedding.to(device)
    try:
        torch.save(
            {"gpt_cond_latent": gpt_cond_latent, "speaker_embedding": speaker_embedding}, cache_path
        )
        print("[XTTS] Embedding saved to cache")
    except Exception as e:
        print(f"[XTTS] Cache save failed: {e}")

    return gpt_cond_latent, speaker_embedding
