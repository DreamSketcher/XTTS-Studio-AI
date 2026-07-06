# -*- coding: utf-8 -*-
"""
test_smart_pauses.py — тесты для engine/smart_pauses.py (SmartPauseEngine).

Запуск:
    pytest test_smart_pauses.py -v
"""
import pytest

from engine.smart_pauses import SmartPauseEngine


@pytest.fixture
def engine():
    return SmartPauseEngine()


# ───────────────────────── базовые паузы по пунктуации ─────────────────────────

def test_period_gives_medium_pause(engine):
    assert engine.get_pause_ms("Короткая фраза.") == engine.base_medium


def test_question_mark_gives_longer_pause_than_period(engine):
    pause = engine.get_pause_ms("Это вопрос?")
    assert pause > engine.base_medium
    assert pause == engine.base_long + 60


def test_exclamation_gives_pause_between_medium_and_question(engine):
    pause = engine.get_pause_ms("Восклицание!")
    assert pause == engine.base_long - 20


def test_ellipsis_gives_dramatic_pause(engine):
    assert engine.get_pause_ms("Многоточие...") == engine.base_dramatic


def test_comma_gives_short_pause(engine):
    assert engine.get_pause_ms("Просто запятая,") == engine.base_short


def test_empty_chunk_gives_short_pause(engine):
    assert engine.get_pause_ms("") == engine.base_short


# ───────────────────────── пункты списка ─────────────────────────

def test_list_item_gets_dedicated_long_pause(engine):
    assert engine.get_pause_ms("1. Пункт списка отдельный") == engine.list_item_pause


def test_pause_before_upcoming_list_item_is_also_long(engine):
    # если СЛЕДУЮЩИЙ чанк — пункт списка, текущая пауза тоже удлиняется
    pause = engine.get_pause_ms("Обычная фраза без пунктов.", next_chunk="2. Следующий пункт")
    assert pause == engine.list_item_pause


# ───────────────────────── модификатор длины и клэмп ─────────────────────────

def test_long_chunk_gets_extra_pause_from_length_modifier(engine):
    short_pause = engine.get_pause_ms("Раз два три.")
    long_pause = engine.get_pause_ms(
        "Очень длинное предложение с большим количеством слов для проверки модификатора длины пауз здесь."
    )
    assert long_pause > short_pause


def test_pause_is_always_clamped_between_50_and_450(engine):
    # искусственно длинный чанк с многоточием — не должен вылезти за верхнюю границу
    huge = ("слово " * 100) + "..."
    pause = engine.get_pause_ms(huge)
    assert 50 <= pause <= 450


# ───────────────────────── детекция эмоции ─────────────────────────

def test_detect_emotion_excited(engine):
    assert engine.detect_emotion("Это было потрясающе!") == "excited"


def test_detect_emotion_uncertain(engine):
    assert engine.detect_emotion("Может быть, не уверен точно") == "uncertain"


def test_detect_emotion_normal_by_default(engine):
    assert engine.detect_emotion("Обычный текст без эмоций") == "normal"


def test_detect_emotion_is_case_insensitive(engine):
    assert engine.detect_emotion("ПОТРЯСАЮЩЕ, это сработало!") == "excited"