# -*- coding: utf-8 -*-
"""
test_normalizer.py — тесты для engine/normalizer.py (TextNormalizer).

Запуск:
    pip install pytest num2words --break-system-packages
    pytest test_normalizer.py -v
"""
import pytest

from engine.normalizer import TextNormalizer


@pytest.fixture
def norm():
    return TextNormalizer()


# ───────────────────────── числа → слова ─────────────────────────

def test_simple_integer_to_words(norm):
    assert norm.normalize("У меня 5 яблок") == "У меня пять яблок."


def test_percent_to_words(norm):
    assert norm.normalize("Показатель вырос на 87%") == \
        "Показатель вырос на восемьдесят семь процентов."


def test_decimal_number_to_words(norm):
    result = norm.normalize("3,14 это число пи")
    assert "три целых четырнадцать сотых" in result


def test_decimal_with_dot_is_converted_to_comma_then_words(norm):
    # 3.14 (через точку) должно распознаваться так же, как 3,14
    result = norm.normalize("Число 3.14 известно всем")
    assert "три целых четырнадцать сотых" in result


def test_ordinal_list_marker(norm):
    assert norm.normalize("1) Пункт первый") == "первое, Пункт первый."


# ───────────────────────── аббревиатуры ─────────────────────────

def test_known_cyrillic_abbreviation_from_dict(norm):
    result = norm.normalize("РФ и СНГ подписали договор")
    assert "эр эф" in result
    assert "эс эн гэ" in result
    # аббревиатуры не должны остаться как есть
    assert "РФ" not in result
    assert "СНГ" not in result


def test_latin_abbreviation_series_gets_comma_dot_rhythm(norm):
    result = norm.normalize("CPU GPU RAM работают быстро")
    assert result == "CPU, GPU. RAM. работают быстро."


def test_mixed_case_brand_series_gets_rhythm(norm):
    result = norm.normalize("OpenAI ChatGPT PyTorch отличные библиотеки")
    assert result == "OpenAI, ChatGPT. PyTorch. отличные библиотеки."


def test_single_latin_abbreviation_is_left_alone(norm):
    # одна аббревиатура (не серия из 2+) не должна обрастать пунктуацией
    result = norm.normalize("Использую CPU для расчётов")
    assert "CPU для" in result
    assert "CPU," not in result
    assert "CPU." not in result


# ───────────────────────── финальная пунктуация ─────────────────────────

def test_adds_trailing_period_if_missing(norm):
    assert norm.normalize("Просто текст без точки") == "Просто текст без точки."


def test_keeps_existing_question_mark(norm):
    assert norm.normalize("Вопрос уже с знаком?") == "Вопрос уже с знаком?"


def test_empty_string_returns_empty(norm):
    assert norm.normalize("") == ""


# ───────────────────────── safe_character_filter ─────────────────────────

def test_safe_character_filter_removes_unsupported_symbols(norm):
    result = norm.safe_character_filter("Привет @мир# $100")
    assert "@" not in result
    assert "#" not in result
    assert "$" not in result


def test_safe_character_filter_adds_final_period(norm):
    result = norm.safe_character_filter("Текст без точки")
    assert result.endswith(".")