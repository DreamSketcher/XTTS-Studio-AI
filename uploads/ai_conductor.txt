"""
engine/ai_conductor.py — AI Conductor для XTTS Studio

Анализирует весь текст и список чанков одним API-вызовом,
возвращает список параметров для каждого чанка.

Когда AI Conductor активен:
  - prosody_engine.process_chunks() пропускается (чанки идут сырые)
  - pause_engine.get_pause_ms() заменяется на conductor_map[i]["pause_after_ms"]
  - _adjust_params_for_chunk() пропускается (AI управляет temperature schedule)

При любой ошибке (сеть, таймаут, плохой JSON) возвращает None —
генерация продолжается со стандартными параметрами без прерывания.
"""

import json
from typing import Optional


# =========================
# SYSTEM PROMPT
# =========================

_CONDUCTOR_SYSTEM = """\
Ты — AI Conductor для системы синтеза речи XTTS v2.
Твоя задача: проанализировать текст и для каждого чанка назначить оптимальные параметры озвучки.

ВАЖНО: не переписывай и не переводи текст. Твоя задача — только параметры
и corrections. Текст чанков передаётся тебе как контекст, не как задание на редактуру.

ПАРАМЕТРЫ (все обязательны для каждого чанка):

temperature (float, 0.50–0.90)
  Вариативность интонации. Ниже = монотоннее и стабильнее. Выше = живее, но риск артефактов.
  0.50–0.65 — нейтральное повествование, технический текст, списки
  0.65–0.75 — диалог, лёгкая эмоция, вопросы
  0.75–0.90 — восклицания, драма, кульминация

top_p (float, 0.70–0.95)
  Разнообразие выборки токенов. Обычно 0.80–0.85 для большинства чанков.
  Снижай до 0.70–0.75 для стабильности на технических терминах и аббревиатурах.

repetition_penalty (float, 5.0–12.0)
  Штраф за повторы. Выше = меньше риск зацикливания.
  5.0–7.0 — короткие чанки, поэзия, перечисления
  8.0–10.0 — стандартная проза
  10.0–12.0 — длинные монотонные чанки, технические термины

length_penalty (float, 0.5–2.0)
  Влияет на длину генерации. 1.0 — нейтрально. Меньше = короче, больше = длиннее.
  Обычно держи близко к 1.0. Снижай до 0.7–0.8 для коротких фраз с риском затяжки.

speed (float, 0.75–1.25)
  Скорость речи.
  0.75–0.90 — медленно: драматические паузы, важные факты, перечисления
  0.90–1.05 — нормальный темп
  1.05–1.25 — быстро: лёгкий диалог, вводные фразы, скобочные пояснения

pause_after_ms (int, 0–1200)
  Тишина после чанка в миллисекундах.
  0 — склейка без паузы (внутри предложения)
  150–300 — запятая, продолжение мысли
  400–600 — конец предложения
  700–1000 — смена темы, абзац
  1000–1200 — сильная драматическая пауза

КОНТЕКСТ ОБРАБОТКИ ТЕКСТА (важно для правильной оценки длины/веса фраз):
Текст, который ты получаешь, уже прошёл предварительную нормализацию:
  - Числа развёрнуты в слова ("2024" → "две тысячи двадцать четыре",
    "3.5" → "три целых пять десятых"). Учитывай это: фраза может казаться
    длиннее оригинала, но её смысловой вес не изменился — не назначай
    повышенный temperature или замедление только из-за длины числительных.
  - Сокращения раскрыты ("т.е." → "то есть", "и т.д." → "и так далее").
  - Символы %, №, &, @, * заменены словами или убраны — не ожидай их
    в тексте и не пытайся компенсировать их "резкость".
  - Слишком длинные предложения уже разбиты на части короче 20 слов —
    тебе не нужно самостоятельно решать, где разрезать длинную фразу,
    это уже сделано на уровне чанков, которые ты получаешь.
  - Короткие смешанные англоязычные вставки (1-2 слова) уже встроены
    в окружающий русский текст для стабильности синтеза — если видишь
    короткие латинские слова внутри русской фразы, это ожидаемо,
    не повод снижать temperature как для рискованного контента.

ТРАНСЛИТЕРАЦИЯ (необязательное поле corrections):
  Каждый чанк ты получаешь в двух вариантах:
    original — исходный текст (может содержать английские слова)
    processed — текст после автотранслитерации (английские слова заменены кириллицей)

  Поле corrections нужно ТОЛЬКО если автотранслит дал технически неверный результат.
  corrections — это словарь {английское_слово_латиницей: кириллица}.

  СТРОГИЕ ПРАВИЛА для corrections:
  - Ключ ВСЕГДА латиницей (оригинальное английское слово из original)
  - Значение ВСЕГДА кириллицей (как это слово должно звучать по-русски)
  - НИКОГДА не переводи слова по смыслу ("local" → "местный" — ЗАПРЕЩЕНО)
  - НИКОГДА не трогай русские слова
  - НИКОГДА не переписывай фразы — только точечная замена одного слова
  - Исправляй только явные фонетические ошибки транслита:
      cmake → "цмаке" (плохо) исправь на "си мэйк" ✓
      launcher → "лаанчер" (плохо, дифтонг au прочитан как два отдельных "а")
        исправь на "лаунчер" ✓
      numpy → "нампай" (приемлемо) — не трогай ✓
      local → "локал" (приемлемо) — не трогай ✓
  - "Приемлемо" значит результат узнаваем и не искажает звучание до неузнаваемости.
    Не путай это с "идеально" — если слышна явная ошибка в гласных/дифтонгах
    (слово звучит не так, как должно), это НЕ приемлемо, исправляй.

РЕЖИМ ПЕРЕРАБОТКИ ТЕКСТА (активируется отдельно):
  Если в запросе присутствует блок ЗАДАНИЕ НА СТИЛЬ — твоя первая задача:
  переработать исходный текст под заданный жанр/настроение/стиль.

  ПРАВИЛА ПЕРЕРАБОТКИ:
  - Смысл и факты оригинала сохраняются, форма подачи меняется полностью
  - Объём — умеренный, не длиннее двух оригиналов
  - Факты и названия из оригинала сохраняются, всё остальное подчинено заданию
  - Синтаксис, ритм, лексика, эмоциональная окраска — всё подчинено заданию
  - Запрещено только одно: искажать факты, названия и термины из оригинала
  - Текст должен звучать естественно при озвучке — короткие фразы, живой ритм
  - После переработки — назначь параметры чанков УЖЕ под новый текст

  Если блока ЗАДАНИЕ НА СТИЛЬ нет — не переписывай текст, только параметры.

ПРАВИЛА:
1. Учитывай контекст: что было до и что будет после чанка.
2. Следи за дугой напряжения: нарастание → кульминация → спад.
3. Для коротких чанков (менее 5 слов) снижай temperature и top_p для стабильности.
4. Для последнего чанка pause_after_ms = 0.
5. Отвечай ТОЛЬКО валидным JSON-массивом без markdown, без пояснений, без ```json.

ФОРМАТ ОТВЕТА — два варианта:

ВАЖНО: значения в примерах ниже показывают только структуру JSON
(ключи, типы данных). Это НЕ дефолты и НЕ образец для копирования —
реальные значения для каждого чанка считай заново по правилам выше,
исходя из контекста, эмоции и положения в тексте. Одинаковые параметры
у всех чанков подряд — почти всегда признак того, что анализ не был
проведён.

Если ЗАДАНИЕ НА СТИЛЬ присутствует:
{
  "rewritten_text": "переработанный текст целиком",
  "chunks": [
    {"temperature": 0.58, "top_p": 0.75, "repetition_penalty": 10.0, "length_penalty": 1.0, "speed": 0.85, "pause_after_ms": 700},
    {"temperature": 0.81, "top_p": 0.88, "repetition_penalty": 7.0,  "length_penalty": 1.1, "speed": 1.15, "pause_after_ms": 150},
    {"temperature": 0.66, "top_p": 0.80, "repetition_penalty": 9.5,  "length_penalty": 0.9, "speed": 1.0,  "pause_after_ms": 0}
  ]
}

Если ЗАДАНИЕ НА СТИЛЬ отсутствует:
[
  {"temperature": 0.58, "top_p": 0.75, "repetition_penalty": 10.0, "length_penalty": 1.0, "speed": 0.85, "pause_after_ms": 700},
  {"temperature": 0.81, "top_p": 0.88, "repetition_penalty": 7.0,  "length_penalty": 1.1, "speed": 1.15, "pause_after_ms": 150},
  {"temperature": 0.66, "top_p": 0.80, "repetition_penalty": 9.5,  "length_penalty": 0.9, "speed": 1.0,  "pause_after_ms": 0}
]
"""


# =========================
# WORD COUNT HELPER
# =========================

def _word_count(text: str) -> int:
    import re
    return len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text))


# =========================
# FALLBACK PARAMS
# =========================

def _fallback_params(chunks: list) -> list:
    """Дефолтные параметры если AI недоступен."""
    result = []
    for i, chunk in enumerate(chunks):
        wc = _word_count(chunk)
        is_last = (i == len(chunks) - 1)
        result.append({
            "temperature":       0.70,
            "top_p":             0.82,
            "repetition_penalty": 9.0,
            "length_penalty":    1.0,
            "speed":             1.0,
            "pause_after_ms":    0 if is_last else (250 if wc < 6 else 450),
        })
    return result


# =========================
# JSON VALIDATOR
# =========================

def _validate_map(data, expected_len: int) -> Optional[list]:
    """
    Проверяет и зажимает параметры в допустимые диапазоны.
    Возвращает список или None если структура сломана.
    """
    if not isinstance(data, list):
        return None
    if len(data) != expected_len:
        print(f"[Conductor] JSON length mismatch: got {len(data)}, expected {expected_len}")
        fallback = _fallback_params([""] * expected_len)
        if len(data) > expected_len:
            data = data[:expected_len]
        else:
            data = data + fallback[len(data):]

    result = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return None
        is_last = (i == expected_len - 1)
        try:
            entry = {
                "temperature":        max(0.50, min(0.90, float(item.get("temperature",       0.70)))),
                "top_p":              max(0.70, min(0.95, float(item.get("top_p",              0.82)))),
                "repetition_penalty": max(5.0,  min(12.0, float(item.get("repetition_penalty", 9.0)))),
                "length_penalty":     max(0.5,  min(2.0,  float(item.get("length_penalty",     1.0)))),
                "speed":              max(0.75, min(1.25, float(item.get("speed",              1.0)))),
                "pause_after_ms":     0 if is_last else max(0, min(1200, int(item.get("pause_after_ms", 450)))),
            }
            # ← ДОБАВЛЕНО: пробрасываем corrections если есть и это словарь
            if "corrections" in item and isinstance(item["corrections"], dict):
                entry["corrections"] = item["corrections"]

            result.append(entry)
        except (TypeError, ValueError) as e:
            print(f"[Conductor] Bad value in chunk {i}: {e}")
            return None

    return result


# =========================
# MAIN FUNCTION
# =========================

def conduct(
    text: str,
    chunks: list,
    quality_params: dict = None,
    chunks_wr: list = None,
    rewrite_enabled: bool = False,
    rewrite_context: str = "",
    rewrite_negative: str = "",
) -> Optional[list]:
    """
    Анализирует текст и возвращает список параметров для каждого чанка.

    Args:
        text:          нормализованный текст (после normalizer, до chunker)
        chunks:        список чанков из chunker.chunk_text() (оригинал)
        quality_params: словарь параметров задачи (для выбора провайдера)
        chunks_wr:     список чанков после word replacer (для проверки транслита)

    Returns:
        list[dict] с параметрами для каждого чанка
        или None при любой ошибке (caller использует стандартные параметры)
    """
    if not chunks:
        return None

    # ← ДОБАВЛЕНО: fallback если chunks_wr не передали
    chunks_wr = chunks_wr or chunks

    # Строим user-сообщение — теперь каждый чанк показан в двух вариантах
    # ← ИЗМЕНЕНО: было просто f"[{i}] {chunk}", теперь original + processed
    chunks_block = "\n".join(
        f"[{i}] original: {chunk!r} | processed: {chunks_wr[i]!r}"
        for i, chunk in enumerate(chunks)
    )

    if rewrite_enabled and rewrite_context.strip():
        negative_line = f"\nИЗБЕГАТЬ:\n{rewrite_negative.strip()}\n" if rewrite_negative.strip() else ""
        rewrite_block = f"\nЗАДАНИЕ НА СТИЛЬ:\n{rewrite_context.strip()}\n{negative_line}"
        task_line = (
            f"Переработай текст согласно заданию на стиль, затем верни JSON-объект "
            f"с полями rewritten_text и chunks (массив из {len(chunks)} объектов)."
        )
    else:
        rewrite_block = ""
        task_line = f"Верни JSON-массив из {len(chunks)} объектов с параметрами для каждого чанка."

    user_msg = (
        f"ПОЛНЫЙ ТЕКСТ:\n{text}\n\n"
        f"ЧАНКИ ({len(chunks)} шт.):\n{chunks_block}\n\n"
        f"{rewrite_block}"
        f"{task_line}"
    )

    messages = [
        {"role": "system", "content": _CONDUCTOR_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    try:
        from .gpt_client import _call_with_chain, AIUnavailable
    except ImportError:
        from engine.gpt_client import _call_with_chain, AIUnavailable

    max_tokens = min(8192, max(512, len(chunks) * 70)) if not rewrite_enabled else min(8192, max(2048, len(text) * 3 + len(chunks) * 70))

    import re

    try:
        raw = _call_with_chain(messages, max_tokens=max_tokens)
    except AIUnavailable as e:
        print(f"[Conductor] ИИ недоступен ({e}), conductor отключается")
        return None

    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = raw.rstrip("`").strip()

    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"[Conductor] Invalid JSON from response: {e}, using default params")
        return _fallback_params(chunks)

    # Если rewrite — ответ обёрнут в объект с rewritten_text.
    # ВАЖНО: rewritten_text принимается ТОЛЬКО если rewrite_enabled=True.
    # Модель иногда сама решает вернуть объект с этим полем, даже если
    # блок "ЗАДАНИЕ НА СТИЛЬ" не запрашивался — не даём этому просочиться
    # дальше, если пользователь не включал уровень 2 явно.
    rewritten_text = None
    if isinstance(data, dict) and "chunks" in data:
        if rewrite_enabled:
            rewritten_text = data.get("rewritten_text", "").strip() or None
        else:
            print("[Conductor] Модель вернула rewritten_text при rewrite_enabled=False — игнорирую")
        data = data["chunks"]

    result = _validate_map(data, len(chunks))
    if result is None:
        print("[Conductor] Invalid JSON structure, using default params")
        return _fallback_params(chunks)

    print(f"[Conductor] OK — {len(result)} chunks" + (" + rewrite" if rewritten_text else ""))
    if rewritten_text:
        return {"rewritten_text": rewritten_text, "chunks": result}
    return result