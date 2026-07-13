# -*- coding: utf-8 -*-
"""
test_word_replacer.py — тесты для engine/word_replacer.py (WordReplacer).

Ничего не трогает реальный проект: WordReplacer принимает rules_path
напрямую в конструкторе, поэтому изоляция — это просто временный файл
pytest (tmp_path), без monkeypatch путей.

Запуск:
    pytest test_word_replacer.py -v
"""
import json
import os

import pytest

from engine import word_replacer
from engine.word_replacer import WordReplacer


@pytest.fixture
def rules_path(tmp_path):
    return str(tmp_path / "word_rules.json")


@pytest.fixture
def wr(rules_path):
    return WordReplacer(rules_path)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ───────────────────────── приоритет категорий ─────────────────────────


def test_higher_priority_category_wins_in_flat_rules(rules_path):
    wr = WordReplacer(rules_path)
    wr.add_rule("test", "старый вариант", category="builtin")
    wr.add_rule("test", "новый вариант", category="custom")

    assert wr.flat_rules["test"] == "новый вариант"


def test_unknown_category_outranks_custom(rules_path):
    wr = WordReplacer(rules_path)
    wr.add_rule("test", "из custom", category="custom")
    wr.add_rule("test", "из неизвестной категории", category="some_future_category")

    assert wr.flat_rules["test"] == "из неизвестной категории"


# ───────────────────────── add_rule: та же категория ─────────────────────────


def test_re_adding_same_word_same_category_increments_occurrences_and_keeps_added_at(rules_path):
    wr = WordReplacer(rules_path)
    wr.add_rule("gguf", "джи-джи-ю-эф", category="auto")
    first_added_at = wr.data["auto"]["gguf"]["added_at"]

    wr.add_rule("gguf", "джи джи ю эф", category="auto")
    entry = wr.data["auto"]["gguf"]

    assert entry["occurrences"] == 2
    assert entry["added_at"] == first_added_at
    assert entry["text"] == "джи джи ю эф"


# ───────────────────────── add_rule: смена категории ─────────────────────────


def test_moving_word_to_different_category_resets_occurrences(rules_path):
    """
    Фиксирую текущее поведение: при переносе слова в ДРУГУЮ категорию
    история (occurrences/added_at) не переносится, даже если слово там
    уже встречалось несколько раз — add_rule всегда создаёт свежую запись,
    если old_category != category.
    """
    wr = WordReplacer(rules_path)
    wr.add_rule("term", "вариант 1", category="auto")
    wr.add_rule("term", "вариант 2", category="auto")  # occurrences=2 в auto
    assert wr.data["auto"]["term"]["occurrences"] == 2

    wr.add_rule("term", "вариант 3", category="custom")  # переносим в custom

    assert "term" not in wr.data.get("auto", {}), "слово должно быть удалено из старой категории"
    assert wr.data["custom"]["term"]["occurrences"] == 1, "в новой категории история начинается заново"
    assert wr.data["custom"]["term"]["text"] == "вариант 3"


# ───────────────────────── remove_rule ─────────────────────────


def test_remove_rule_deletes_word_and_persists(rules_path):
    wr = WordReplacer(rules_path)
    wr.add_rule("obsolete", "устаревшее", category="custom")
    assert wr.get_category("obsolete") == "custom"

    wr.remove_rule("obsolete")

    assert wr.get_category("obsolete") is None
    assert "obsolete" not in wr.flat_rules
    # Перечитываем файл с диска — изменение должно быть сохранено, а не только в памяти
    on_disk = _read_json(rules_path)
    assert "obsolete" not in on_disk.get("custom", {})


# ───────────────────────── бэкапы ─────────────────────────


def test_no_backup_created_on_first_save_when_file_did_not_exist(rules_path):
    wr = WordReplacer(rules_path)
    wr.add_rule("first", "первое", category="custom")  # первый save()

    backup_dir = os.path.join(os.path.dirname(rules_path), "word_rules_backups")
    backups = os.listdir(backup_dir) if os.path.isdir(backup_dir) else []
    assert backups == [], "бэкапа быть не должно — до первой записи файла ещё не существовало"


def test_backup_created_on_subsequent_saves(rules_path):
    wr = WordReplacer(rules_path)
    wr.add_rule("first", "первое", category="custom")  # создаёт файл, бэкапа ещё нет
    wr.add_rule("second", "второе", category="custom")  # теперь файл уже существовал -> бэкап

    backup_dir = os.path.join(os.path.dirname(rules_path), "word_rules_backups")
    backups = os.listdir(backup_dir)
    assert len(backups) == 1


def test_backup_retention_respects_max_backups_limit(rules_path, monkeypatch):
    monkeypatch.setattr(word_replacer, "_MAX_BACKUPS", 3)
    wr = WordReplacer(rules_path)

    # Каждый add_rule — отдельный save(); первый save не бэкапит (файла не было),
    # следующие 5 — бэкапят, итого 5 бэкапов при лимите 3 -> должно остаться 3.
    for i in range(6):
        wr.add_rule(f"word{i}", f"замена{i}", category="custom")

    backup_dir = os.path.join(os.path.dirname(rules_path), "word_rules_backups")
    backups = os.listdir(backup_dir)
    assert len(backups) == 3, "должны остаться только последние _MAX_BACKUPS бэкапов"


# ───────────────────────── get_words_list ─────────────────────────


def test_get_words_list_is_sorted_and_excludes_meta(rules_path):
    wr = WordReplacer(rules_path)
    wr.add_rule("zebra", "зебра", category="custom")
    wr.add_rule("apple", "яблоко", category="builtin")
    wr.data["meta"] = {"version": 1}  # meta не должна попадать в список слов

    assert wr.get_words_list() == ["apple", "zebra"]


# ───────────────────────── apply(): базовая замена ─────────────────────────


def test_apply_replaces_known_word_respecting_word_boundaries(wr):
    wr.add_rule("кот", "коть", category="custom")

    result = wr.apply("Мой кот и котлета", persist_new=False)

    assert "коть" in result
    assert "котьлета" not in result, "замена не должна затрагивать часть другого слова"


def test_apply_custom_rule_overrides_builtin(wr):
    wr.add_rule("gpu", "джи пи ю встроенное", category="builtin")
    wr.add_rule("gpu", "жэ пэ у кастомное", category="custom")

    result = wr.apply("У меня gpu", persist_new=False)

    assert "жэ пэ у кастомное" in result
    assert "джи пи ю встроенное" not in result


def test_apply_prefers_longer_rule_over_substring_rule(wr):
    wr.add_rule("york", "йорк", category="custom")
    wr.add_rule("new york", "нью-йорк", category="custom")

    result = wr.apply("Еду в new york сегодня", persist_new=False)

    assert "нью-йорк" in result
    assert "йорк йорк" not in result, "короткое правило не должно было сработать поверх длинного"


# ───────────────────────── apply(): авто-детект аббревиатур ─────────────────────────


def test_apply_auto_transliterates_unknown_all_caps_abbreviation(wr):
    result = wr.apply("Работает XKQZ модуль", persist_new=False)

    # XKQZ нет в словаре -> должно транслитерироваться побуквенно через _LATIN_LETTER_MAP
    assert "XKQZ" not in result
    assert "икс" in result and "кей" in result


def test_apply_persists_new_auto_rule_when_persist_new_true(wr, rules_path):
    wr.apply("Работает XKQZ модуль", persist_new=True)

    assert wr.get_category("XKQZ") == "auto", "новое правило должно сохраниться в категорию auto"
    on_disk = _read_json(rules_path)
    assert "XKQZ" in on_disk.get("auto", {})


def test_apply_does_not_persist_when_persist_new_false(wr, rules_path):
    wr.apply("Работает XKQZ модуль", persist_new=False)

    assert wr.get_category("XKQZ") is None, "правило не должно было сохраниться"
    assert not os.path.exists(rules_path), "файл вообще не должен был создаться"


# ───────────────────────── apply(): авто-детект lowercase-термина ─────────────────────────


def test_apply_auto_transliterates_unknown_lowercase_term(wr):
    result = wr.apply("Использую pydub для аудио", persist_new=False)

    assert "pydub" not in result
    assert result != "Использую pydub для аудио."  # что-то реально заменилось


# ───────────────────────── apply(): guard связной английской прозы ─────────────────────────


def test_apply_skips_transliteration_when_neighbor_is_service_word(wr):
    # "XKQZ" рядом со служебным словом "the" — признак связной английской
    # фразы, транслитерация не должна применяться, чтобы не сломать
    # переключение языка в остальном пайплайне.
    result = wr.apply("this is the XKQZ file", persist_new=False)

    assert "XKQZ" in result, "рядом со служебным словом токен не должен транслитерироваться"
