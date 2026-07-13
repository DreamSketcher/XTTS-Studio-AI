# -*- coding: utf-8 -*-
"""
test_chunker.py — тесты для engine/chunker.py (TextChunker).

Запуск:
    pytest test_chunker.py -v
"""
import pytest

from engine.chunker import TextChunker


@pytest.fixture
def chunker():
    return TextChunker()


# ───────────────────────── базовое поведение ─────────────────────────


def test_short_text_not_split(chunker):
    text = "Привет, как дела?"
    assert chunker.chunk_text(text) == [text]


def test_empty_text_returns_empty_list(chunker):
    assert chunker.chunk_text("") == []


def test_long_text_is_split_into_multiple_chunks(chunker):
    long_text = (
        "Это первое предложение, которое довольно длинное и содержит много слов для теста. "
        "И это продолжение мысли, которое не должно начинать отдельный чанк. "
        "Второе предложение здесь. Третье предложение тоже здесь, и оно длинное настолько, "
        "что точно превысит порог в сто пятьдесят символов при склейке с предыдущими частями текста."
    )
    chunks = chunker.chunk_text(long_text)
    assert len(chunks) > 1


# ───────────────────────── правила безопасности просодии ─────────────────────────

# ───────────────────────── правила безопасности просодии ─────────────────────────


def test_bad_start_fragment_produced_mid_loop_gets_merged_into_previous(chunker):
    # Текст с 2+ итерациями цикла, где ПРОМЕЖУТОЧНЫЕ разрезы дают фрагмент,
    # начинающийся с "и" — а финальный остаток текста начинается с обычного
    # слова, чтобы не задеть отдельный баг с хвостом (см. тест ниже).
    text = (
        "Мы разработали новую систему обработки данных, которая значительно ускоряет "
        "процесс работы всей команды в целом, и она также снижает нагрузку на сервер "
        "во время пиковых часов использования системы каждый день недели, и позволяет "
        "обрабатывать намного больше запросов одновременно без каких-либо сбоев в работе "
        "приложения. Команда довольна результатом работы над этим важным проектом в этом квартале."
    )
    chunks = chunker._split_long(text)
    for c in chunks:
        first_word = c.strip().split(" ", 1)[0].lower().strip(",.;:!?")
        assert (
            first_word not in chunker.bad_start_tokens
        ), f"Фрагмент, порождённый разрезом внутри цикла, не должен начинаться с запрещённого токена: {c!r}"


def test_trailing_remainder_after_loop_is_also_checked_for_bad_start(chunker):
    # Единственное предложение (без точек внутри) длиной чуть больше max_size,
    # где единственная точка разреза оставляет хвост, начинающийся с "и".
    text = (
        "Мы разработали новую систему обработки данных, которая значительно ускоряет процесс, "
        "и она также снижает нагрузку на сервер, и позволяет обрабатывать больше запросов "
        "одновременно без сбоев в работе приложения на любых нагрузках сейчас."
    )
    chunks = chunker._split_long(text)
    for c in chunks:
        first_word = c.strip().split(" ", 1)[0].lower().strip(",.;:!?")
        assert (
            first_word not in chunker.bad_start_tokens
        ), f"Хвостовой остаток начинается с запрещённого токена: {c!r}"


def test_merge_glues_tiny_fragments_together(chunker):
    # Фрагменты короче min_size должны склеиваться, а не оставаться отдельными чанками
    text = "Да. Нет. Может быть. Ну хорошо тогда."
    chunks = chunker.chunk_text(text)
    # ни один итоговый чанк не должен быть короче min_size, кроме последнего остатка
    for c in chunks[:-1]:
        assert len(c) >= chunker.min_size or len(chunks) == 1


# ───────────────────────── смешанный RU/EN текст ─────────────────────────


def test_mixed_ru_en_text_does_not_crash_and_splits_reasonably(chunker):
    text = (
        "Мы используем PyTorch и TensorFlow для обучения моделей. "
        "This is a mixed language sentence with English words inside. "
        "Функция process_data() принимает параметр batch_size и возвращает результат. "
        "Overall the pipeline works well across both languages without breaking apart unexpectedly here."
    )
    chunks = chunker.chunk_text(text)
    assert len(chunks) >= 1
    # весь текст (без учёта пробелов на стыках) должен сохраниться
    joined = "".join(chunks).replace(" ", "")
    original = text.replace(" ", "")
    assert joined == original


def test_chunks_respect_max_size_with_reasonable_tolerance(chunker):
    long_text = "Слово. " * 60  # много коротких предложений подряд
    chunks = chunker.chunk_text(long_text)
    for c in chunks:
        # небольшой допуск, т.к. merge может слегка превысить max_size на границе
        assert len(c) <= chunker.max_size + 20, f"Чанк слишком длинный ({len(c)}): {c!r}"
