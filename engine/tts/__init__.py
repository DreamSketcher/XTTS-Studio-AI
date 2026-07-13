from typing import Any, List, Optional, Tuple
import re
import os
import sys
import time
from datetime import datetime
from engine.prosody_layer import create_prosody_layer
from engine.word_replacer import WordReplacer
from engine.text_utils import is_list_item as _is_list_item

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
from engine.normalizer import TextNormalizer
from engine.chunker import TextChunker
from engine.smart_pauses import SmartPauseEngine
from engine.reference_processor import ReferenceProcessor
from engine.de_esser import create_de_esser

# =========================
# BASE PATH
# =========================
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

def path(*args):
    return os.path.join(BASE_DIR, *args)

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




# Internal TTS Modules
from .device import detect_device
from .cache import _chunk_cache_key, _chunk_cache_path, _chunk_cache_get, _chunk_cache_set
from .qc import _wav_to_mono_float, _detect_repeats, _validate_duration, _adaptive_trim, _normalize_loudness, _normalize_numpy_audio
from .utils import path, _make_output_name, detect_lang_adaptive, _Cancelled, _is_dense_abbrev_chunk, _adjust_params_for_chunk, _count_real_words, _split_by_language, _normalize_lookup_text_with_map, _build_chunk_text_map, _get_embedding
from .export import export_audio


def _remove_with_retry(path_to_remove, attempts=6, delay=0.15):
    """Удаляет файл, устойчиво к временной блокировке (например,
    если чанк сейчас проигрывается через pygame.mixer.music в окне
    «Аудио»). Сначала пытается остановить/выгрузить mixer, если он
    держит именно этот файл, затем делает несколько повторных попыток
    с небольшой паузой — Windows снимает файловую блокировку не
    мгновенно после stop()/unload().
    """
    if not path_to_remove or not os.path.isfile(path_to_remove):
        return
    try:
        import pygame  # type: ignore
        if pygame.mixer.get_init():
            try:
                busy_file = getattr(pygame.mixer.music, "get_pos", None)
                # Не можем напрямую узнать путь текущего трека в pygame,
                # поэтому просто освобождаем поток на всякий случай —
                # unload() безопасен, даже если играет другой файл, т.к.
                # UI-плеер сам перезагружает трек при следующем play().
                pygame.mixer.music.stop()
                if hasattr(pygame.mixer.music, "unload"):
                    pygame.mixer.music.unload()
            except Exception:
                pass
    except Exception:
        pass

    for attempt in range(attempts):
        try:
            os.remove(path_to_remove)
            return
        except Exception:
            if attempt < attempts - 1:
                time.sleep(delay)
    print(f"[Cleanup] Не удалось удалить временный файл (занят): {path_to_remove}")


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


_rvc_processor = None
_rvc_lock = _threading.Lock()


def get_rvc_processor():
    """
    Ленивая инициализация RVCPostProcessor (engine/rvc_pipeline.py).
    Создаётся один раз и переиспользуется, аналогично get_tts().
    """
    global _rvc_processor
    with _rvc_lock:
        if _rvc_processor is None:
            from engine.rvc_pipeline import RVCPostProcessor
            device = detect_device()
            # RVCInference ожидает вид "cuda:0" для GPU или "cpu" для CPU.
            rvc_device = "cuda:0" if device == "cuda" else "cpu"
            _rvc_processor = RVCPostProcessor(
                models_dir=path("models", "rvc"),
                device=rvc_device,
            )
    return _rvc_processor


PROSODY_PRESETS = {
    "Высокое качество": dict(mode="balanced",     intensity=0.1),
    "Нарратив":         dict(mode="balanced",     intensity=0.5),
    "Динамика":         dict(mode="balanced",     intensity=1.1),
    "Экспрессия":       dict(mode="studio_ultra", intensity=1.3),
}

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
            _remove_with_retry(f)


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
        # GPT PREPROCESS — на сыром тексте, ДО normalize().
        # Иначе normalizer успевает развернуть числа в слова
        # ("2024" → "две тысячи двадцать четыре"), и в GPT улетает
        # раздутый по токенам текст — лишний расход дневной квоты Groq.
        # =========================
        if cancelled(): raise _Cancelled()
        use_gpt = quality_params.get("use_gpt", False) if quality_params else False

        if use_gpt:
            from ..gpt_client import preprocess_for_tts

            send("LLM", 12, "LLM обработка текста...")
            # preprocess_for_tts (через improve_for_tts) сама гасит недоступность
            # ИИ внутри себя и возвращает исходный текст без изменений —
            # никаких исключений сюда не долетает, try/except не нужен.
            text = preprocess_for_tts(text, mode="assistant")
            # показываем в GUI именно результат GPT — это то, что зрителю
            # интересно увидеть. Финальная normalize-косметика для движка
            # дальше остаётся "под капотом", в text_box её не выводим.
            send("normalized_text", 18, text_msg=text)

        # =========================
        # NORMALIZE (10–20%)
        # =========================
        if cancelled(): raise _Cancelled()
        send("normalize", 15, "Нормализация текста...")
        text = normalizer.normalize(text)
        text = normalizer.safe_character_filter(text)

        if not use_gpt:
            # без GPT — показываем в GUI финальный normalize-текст, как раньше
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
        ai_conductor_enabled = bool((quality_params or {}).get("ai_conductor_enabled", False))

        if ai_conductor_enabled:
            chunks = chunks_before_prosody  # prosody пропускается
        else:
            chunks = prosody_engine.process_chunks(chunks_before_prosody, lang=lang_detected)

        send("chunking", 30)

        # AI Conductor — один вызов на весь текст до старта генерации
        conductor_map = None
        if ai_conductor_enabled:
            from ..ai_conductor import conduct
            send("ai_conductor_on", None)   # ← пульсация сразу при старте
            send("generate", 30, "AI Conductor анализирует текст...")
            chunks_wr = [word_replacer.apply(c) if (quality_params is None or quality_params.get("word_replacer_enabled", True)) else c for c in chunks]
            rewrite_enabled = bool((quality_params or {}).get("ai_rewrite_enabled", False))
            rewrite_context = str((quality_params or {}).get("ai_rewrite_context", "")).strip()
            rewrite_negative = str((quality_params or {}).get("ai_rewrite_negative", "")).strip()

            conductor_result = conduct(
                text, chunks, quality_params, chunks_wr=chunks_wr,
                rewrite_enabled=rewrite_enabled,
                rewrite_context=rewrite_context,
                rewrite_negative=rewrite_negative,
            )

            # Если кондуктор вернул rewrite — перестраиваем текст и чанки.
            # ВАЖНО: применяем rewritten_text ТОЛЬКО если rewrite_enabled=True —
            # не полагаемся на одну лишь форму ответа conduct(), чтобы уровень 1
            # (параметры) и уровень 2 (rewrite) оставались независимыми даже если
            # conduct() когда-нибудь снова начнёт возвращать rewritten_text не по флагу.
            if rewrite_enabled and isinstance(conductor_result, dict) and "rewritten_text" in conductor_result:
                text = conductor_result["rewritten_text"]
                send("normalized_text", None, text_msg=text)
                chunks_before_prosody = chunker.chunk_text(text)
                chunk_map = _build_chunk_text_map(text, chunks_before_prosody)
                chunks = chunks_before_prosody
                chunks_wr = [word_replacer.apply(c) if (quality_params is None or quality_params.get("word_replacer_enabled", True)) else c for c in chunks]
                conductor_map = conductor_result["chunks"]
                # Если длина чанков изменилась — кондуктор переназначает параметры
                if len(conductor_map) != len(chunks):
                    print(f"[Conductor] Rewrite changed chunk count {len(conductor_map)}→{len(chunks)}, re-conducting")
                    from ..ai_conductor import _fallback_params
                    conductor_map = _fallback_params(chunks)
            elif isinstance(conductor_result, dict) and "chunks" in conductor_result:
                # rewrite_enabled=False, но conduct() всё же вернул словарь —
                # берём только параметры чанков, rewritten_text игнорируем.
                conductor_map = conductor_result["chunks"]
            else:
                conductor_map = conductor_result

            if conductor_map is None:
                send("ai_conductor_off", None)

        output_dir = path("outputs")
        os.makedirs(output_dir, exist_ok=True)

        override_path = (quality_params or {}).get("output_path_override")
        final_path = override_path if override_path else _make_output_name(raw_text or text, output_dir)

        total = max(len(chunks), 1)
        chunk_items = []

        # =========================
        # GENERATION (30–90%)
        # =========================
        send("generate", 30, "Генерация аудио...")

        import hashlib as _hashlib
        _ref_hash = _hashlib.md5(ref_path.encode("utf-8")).hexdigest()[:8]
        cache_path = os.path.splitext(ref_wav)[0] + f"_{_ref_hash}_embedding.pth"
        gpt_cond_latent, speaker_embedding = _get_embedding(tts, ref_wav, cache_path)

        for i, chunk in enumerate(chunks):

            if cancelled():
                raise _Cancelled()

            if len(chunk.strip()) < 5:
                print(f"[SKIP] chunk {i} too short: {repr(chunk)}")
                continue

            start, end = chunk_map[i] if i < len(chunk_map) else (0, 0)

            if status_callback:
                status_callback({
                    "stage": "chunk",
                    "chunk_index": i,
                    "chunk_start": start,
                    "chunk_end": end,
                    "chunk_raw": map_text[start:end] if start is not None and end is not None else "",
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
                # их нельзя передавать в XTTS inference.
                preset.pop("prosody_intensity", None)
                preset.pop("trim_range_ms", None)
                preset.pop("silence_thresh_db", None)
                preset.pop("qc_enabled", None)
                preset.pop("de_esser_intensity", None)
                preset.pop("word_replacer_enabled", None)
                preset.pop("lang_split_enabled", None)
                preset.pop("export_format", None)
                preset.pop("use_gpt", None)
                preset.pop("ai_conductor_enabled", None)
                preset.pop("ai_conductor_context", None)
                preset.pop("ai_rewrite_enabled", None)
                preset.pop("ai_rewrite_context", None)
                preset.pop("ai_rewrite_negative", None)

                # RVC — это постобработка уже сгенерированного аудио
                # (voice conversion поверх готового wav), а НЕ параметр
                # самой генерации XTTS. transformers.generate() не знает
                # эти ключи и падает с ValueError, если они попадают в
                # **sub_preset → inference(). Вынимаем их здесь и
                # применяем RVC-конвертацию отдельным шагом ниже, уже
                # после того как XTTS сгенерирует wav.
                rvc_enable = bool(preset.pop("rvc_enable", False))
                rvc_model = preset.pop("rvc_model", None)
                rvc_index_rate = preset.pop("rvc_index_rate", 0.75)
                rvc_pitch_shift = preset.pop("rvc_pitch_shift", 0)
                rvc_f0_method = preset.pop("rvc_f0_method", "rmvpe")

                # #2: temperature schedule — компенсация угасания на перечислениях
                if ai_conductor_enabled and conductor_map and i < len(conductor_map):
                    cmap = conductor_map[i]
                    # AI управляет temperature schedule — _adjust пропускаем
                    for k in ("temperature", "top_p", "repetition_penalty", "length_penalty"):
                        if k in cmap:
                            preset[k] = cmap[k]
                    if "speed" in cmap:
                        speed_value = cmap["speed"]
                else:
                    preset = _adjust_params_for_chunk(preset, i, total, chunk)

                # Эти строки СНАРУЖИ любого if — всегда выполняются
                no_pause_flag = "[NO_PAUSE]" in chunk
                clean_chunk = chunk.replace("[NO_PAUSE]", "").strip()

                raw_chunk_before_wr = clean_chunk  # сохраняем до WR
                if quality_params is None or quality_params.get("word_replacer_enabled", True):
                    clean_chunk = word_replacer.apply(clean_chunk)

                # Corrections — тоже снаружи, но проверяем условие внутри
                if ai_conductor_enabled and conductor_map and i < len(conductor_map):
                    cmap = conductor_map[i]
                    if "corrections" in cmap:
                        for original_word, corrected in cmap["corrections"].items():
                            word_replacer.add_rule(original_word, corrected, category="ai_corrected")
                            print(f"[WR] AI correction: {original_word} → {corrected}")
                        clean_chunk = word_replacer.apply(raw_chunk_before_wr)

                import soundfile as sf  # type: ignore

                # =========================
                # CHUNK CACHE — проверяем до генерации
                # =========================
                # ВАЖНО: rvc_* уже вынуты из preset (нельзя передавать в
                # XTTS inference), поэтому для кэша собираем ОТДЕЛЬНЫЙ
                # словарь с их учётом — иначе кэш не отличит "тот же
                # текст, но с другой моделью/настройками RVC (или вообще
                # без RVC)" и подставит чужой результат.
                cache_preset = dict(preset)
                cache_preset["_rvc_enable"] = rvc_enable
                cache_preset["_rvc_model"] = rvc_model
                cache_preset["_rvc_index_rate"] = rvc_index_rate
                cache_preset["_rvc_pitch_shift"] = rvc_pitch_shift
                cache_preset["_rvc_f0_method"] = rvc_f0_method
                cache_key = _chunk_cache_key(chunk, lang, cache_preset, speed_value, ref_path, conductor_active=ai_conductor_enabled)
                cached = _chunk_cache_get(output_dir, cache_key)

                if cached:
                    import shutil
                    try:
                        shutil.copy2(cached, chunk_path)
                        if not os.path.isfile(chunk_path):
                            cached = None
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
                    subchunks = _split_by_language(clean_chunk, base_lang=lang)
                else:
                    subchunks = [(clean_chunk, lang)]

                import numpy as np  # type: ignore
                wav_parts = []

                for sub_text, sub_lang in subchunks:
                    sub_preset = dict(preset)
                    sub_wav = None
                    candidate = None

                    for attempt in range(max_attempts):
                        _infer_result: List[Any] = [None]
                        _infer_error: List[Optional[Exception]] = [None]
                        _infer_done   = _threading.Event()

                        def _infer_thread():
                            try:
                                _infer_result[0] = tts.synthesizer.tts_model.inference(
                                    text=sub_text,
                                    language=sub_lang,
                                    gpt_cond_latent=gpt_cond_latent,
                                    speaker_embedding=speaker_embedding,
                                    speed=speed_value,
                                    **sub_preset
                                )
                            except Exception as _e:
                                _infer_error[0] = _e
                            finally:
                                _infer_done.set()

                        t = _threading.Thread(target=_infer_thread, daemon=True)
                        t.start()

                        while not _infer_done.wait(timeout=0.1):
                            if cancelled():
                                raise _Cancelled()

                        if cancelled():
                            raise _Cancelled()

                        if _infer_error[0] is not None:
                            raise _infer_error[0]

                        out = _infer_result[0]
                        if out is None or not isinstance(out, dict) or "wav" not in out:
                            raise RuntimeError(f"Inference returned invalid result: {out!r}")

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

                # =========================
                # RVC (voice conversion) — постобработка ГОТОВОГО аудио.
                # =========================
                # RVC — это конвертация уже сгенерированного XTTS-звука,
                # а не параметр самой генерации, поэтому применяется
                # здесь, к уже записанному wav-файлу чанка, а не внутри
                # tts_model.inference().
                if rvc_enable and rvc_model:
                    try:
                        from engine.rvc_pipeline import RVCPipelineError
                        rvc_processor = get_rvc_processor()
                        rvc_processor.run_inference_via_lib(
                            input_path=chunk_path,
                            output_path=chunk_path,
                            model_name=rvc_model,
                            index_rate=rvc_index_rate,
                            pitch_shift=rvc_pitch_shift,
                            f0_method=rvc_f0_method,
                        )
                    except RVCPipelineError as rvc_err:
                        # Не роняем всю генерацию из-за RVC — отдаём
                        # чистый XTTS-звук и явно предупреждаем в консоли.
                        print(f"[RVC] Конвертация не применена: {rvc_err}")
                    except Exception as rvc_err:
                        print(f"[RVC] Неожиданная ошибка постобработки: {rvc_err}")

                # сохраняем в кэш
                _chunk_cache_set(output_dir, cache_key, chunk_path)

                chunk_items.append({
                    "path": chunk_path,
                    "source_text": chunks_before_prosody[i] if i < len(chunks_before_prosody) else chunk,
                    "processed_text": chunks[i] if i < len(chunks) else chunk,
                    "no_pause": no_pause_flag,
                })

            except _Cancelled:
                raise
            except Exception as e:
                import traceback
                print(f"[Chunk {i} error]: {e}")
                print(traceback.format_exc())
                raise RuntimeError(f"Chunk {i} failed: {e}") from e

            progress = 30 + int((i + 1) / total * 60)
            send("generate", progress)

        # проверка после завершения цикла
        if not chunk_items:
            raise RuntimeError("No chunks were generated")

        # =========================
        # MERGE / EXPORT
        # =========================
        final_path = export_audio(
            chunk_items=chunk_items,
            quality_params=quality_params,
            final_path=final_path,
            ai_conductor_enabled=ai_conductor_enabled,
            conductor_map=conductor_map,
            pause_engine=pause_engine,
            cleanup=cleanup,
            send=send,
            cancelled=cancelled
        )
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