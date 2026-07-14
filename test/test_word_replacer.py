import json
import os
import shutil
import time
from pathlib import Path

import pytest

from engine.word_replacer import (
    WordReplacer,
    _CATEGORY_PRIORITY,
    _MAX_BACKUPS,
    _auto_transliterate_abbrev,
    _letters_to_word_sound,
    _looks_like_abbrev,
    _looks_like_lowercase_term,
    _transliterate_term_word,
)


@pytest.fixture
def tmp_rules(tmp_path: Path) -> Path:
    """Пустой json файл правил во временной папке."""
    p = tmp_path / "word_rules.json"
    p.write_text("{}", encoding="utf-8")
    return p


@pytest.fixture
def replacer(tmp_rules: Path) -> WordReplacer:
    return WordReplacer(rules_path=str(tmp_rules))


class TestLoadAndBuild:
    def test_load_missing_file_creates_empty(self, tmp_path: Path):
        missing = tmp_path / "no_such.json"
        wr = WordReplacer(rules_path=str(missing))
        assert wr.flat_rules == {}
        assert wr.data == {}

    def test_load_corrupted_json_doesnt_crash(self, tmp_path: Path):
        p = tmp_path / "word_rules.json"
        p.write_text("{ invalid json", encoding="utf-8")
        wr = WordReplacer(rules_path=str(p))
        # при ошибке парсинга — пустой data
        assert wr.data == {}
        assert wr.flat_rules == {}

    def test_build_flat_rules_priority(self, tmp_rules: Path):
        data = {
            "builtin": {"hello": "builtin_hello", "only_builtin": "b"},
            "auto": {"hello": "auto_hello"},
            "ai_corrected": {"hello": "ai_hello"},
            "custom": {"hello": "custom_hello", "only_custom": "c"},
        }
        tmp_rules.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        wr = WordReplacer(rules_path=str(tmp_rules))
        # custom имеет наивысший приоритет среди штатных
        assert wr.flat_rules["hello"] == "custom_hello"
        assert wr.flat_rules["only_builtin"] == "b"
        assert wr.flat_rules["only_custom"] == "c"

    def test_unknown_category_higher_than_custom(self, tmp_rules: Path):
        # неизвестная категория должна оказаться выше custom по реализации
        data = {
            "custom": {"word": "from_custom"},
            "future_cat": {"word": "from_future"},
        }
        tmp_rules.write_text(json.dumps(data), encoding="utf-8")
        wr = WordReplacer(str(tmp_rules))
        assert wr.flat_rules["word"] == "from_future"

    def test_dict_value_uses_text_field(self, tmp_rules: Path):
        data = {
            "custom": {
                "gpu": {"text": "гэ пэ у", "weight": 1.0, "occurrences": 1},
                "cpu": "си пи ю",
                "empty": {"not_text": "oops"},
            }
        }
        tmp_rules.write_text(json.dumps(data), encoding="utf-8")
        wr = WordReplacer(str(tmp_rules))
        assert wr.flat_rules["gpu"] == "гэ пэ у"
        assert wr.flat_rules["cpu"] == "си пи ю"
        # если нет text -> ""
        assert wr.flat_rules["empty"] == ""

    def test_meta_ignored(self, tmp_rules: Path):
        data = {"meta": {"version": 1}, "custom": {"hi": "привет"}}
        tmp_rules.write_text(json.dumps(data), encoding="utf-8")
        wr = WordReplacer(str(tmp_rules))
        assert "version" not in wr.flat_rules
        assert wr.flat_rules["hi"] == "привет"


class TestAddRemove:
    def test_add_rule_creates_category(self, replacer: WordReplacer, tmp_rules: Path):
        replacer.add_rule("hello", "привет", category="custom")
        assert replacer.get_category("hello") == "custom"
        assert replacer.flat_rules["hello"] == "привет"
        # файл на диске сохранился
        assert (
            json.loads(tmp_rules.read_text(encoding="utf-8"))["custom"]["hello"]["text"] == "привет"
        )

    def test_add_rule_occurrences_increment_same_category(self, replacer: WordReplacer):
        replacer.add_rule("test", "тест1", category="custom")
        first = replacer.data["custom"]["test"]
        assert first["occurrences"] == 1
        first_added = first["added_at"]

        time.sleep(0.01)
        replacer.add_rule("test", "тест2", category="custom")
        second = replacer.data["custom"]["test"]
        assert second["occurrences"] == 2
        assert second["added_at"] == first_added  # не теряем историю
        assert second["text"] == "тест2"
        assert second["updated_at"] >= first["updated_at"]

    def test_add_rule_move_between_categories_resets_occurrences(self, replacer: WordReplacer):
        replacer.add_rule("word", "v1", category="auto")
        assert replacer.get_category("word") == "auto"
        replacer.add_rule("word", "v1", category="auto")
        assert replacer.data["auto"]["word"]["occurrences"] == 2

        replacer.add_rule("word", "v2", category="custom")
        # старая категория удалена
        assert "word" not in replacer.data.get("auto", {})
        assert replacer.get_category("word") == "custom"
        # occurrences сброшен, т.к. категория сменилась
        assert replacer.data["custom"]["word"]["occurrences"] == 1

    def test_add_rule_context_truncated(self, replacer: WordReplacer):
        long_ctx = "x" * 200
        replacer.add_rule("w", "rep", category="custom", context=long_ctx)
        assert len(replacer.data["custom"]["w"]["context"]) == 120

    def test_add_rule_strip(self, replacer: WordReplacer):
        replacer.add_rule("  spaced  ", "  rep  ")
        assert replacer.get_category("spaced") == "custom"
        assert replacer.flat_rules["spaced"] == "rep"

    def test_remove_rule(self, replacer: WordReplacer):
        replacer.add_rule("todelete", "x", category="custom")
        assert "todelete" in replacer.flat_rules
        replacer.remove_rule("todelete")
        assert "todelete" not in replacer.flat_rules
        assert replacer.get_category("todelete") is None

    def test_get_words_list_sorted(self, replacer: WordReplacer):
        replacer.add_rule("zebra", "z", category="custom")
        replacer.add_rule("apple", "a", category="custom")
        replacer.add_rule("monkey", "m", category="auto")
        lst = replacer.get_words_list()
        assert lst == sorted(lst)
        assert lst == ["apple", "monkey", "zebra"]

    def test_get_category_none(self, replacer: WordReplacer):
        assert replacer.get_category("no_such") is None


class TestBackups:
    def test_backup_created_on_save(self, tmp_path: Path):
        rules = tmp_path / "word_rules.json"
        rules.write_text(json.dumps({"custom": {"a": "b"}}), encoding="utf-8")
        wr = WordReplacer(str(rules))
        wr.add_rule("new", "val", category="custom")
        backup_dir = tmp_path / "word_rules_backups"
        assert backup_dir.exists()
        backups = list(backup_dir.glob("word_rules_*.json"))
        assert len(backups) == 1

    def test_backup_limit_30(self, tmp_path: Path):
        rules = tmp_path / "word_rules.json"
        rules.write_text("{}", encoding="utf-8")
        wr = WordReplacer(str(rules))
        # делаем 35 сохранений
        for i in range(35):
            wr.add_rule(f"w{i}", f"r{i}", category="custom")
        backup_dir = tmp_path / "word_rules_backups"
        backups = sorted(backup_dir.glob("word_rules_*.json"))
        assert len(backups) == _MAX_BACKUPS
        # старые удалены, остались самые свежие
        assert len(backups) <= 30

    def test_backup_no_crash_if_rules_missing(self, tmp_path: Path):
        missing = tmp_path / "not_exists.json"
        wr = WordReplacer(str(missing))
        # _make_backup должен тихо выйти, если файла нет
        wr._make_backup()  # не падает


class TestApply:
    def test_apply_simple_replacement(self, replacer: WordReplacer):
        replacer.add_rule("hello", "привет", category="custom")
        # "world" сам по себе транслитерируется в "ворлд", это фича — проверяем что hello заменён
        result = replacer.apply("hello the", persist_new=False)
        # "the" — service word, не транслитерируется, остаётся
        assert result == "привет the"
        # IGNORECASE
        result2 = replacer.apply("HELLO the", persist_new=False)
        assert result2 == "привет the"

    def test_apply_word_boundaries(self, replacer: WordReplacer):
        replacer.add_rule("cat", "кот", category="custom")
        # "concatenate" не должен затронуться правилом cat (границы), но сам транслитерируется как неизвестный термин
        # поэтому проверяем что внутри не появляется "кот" из-за подстроки
        res_concat = replacer.apply("concatenate", persist_new=False)
        assert "кот" not in res_concat  # cat внутри не должен матчиться как отдельное слово
        assert "конкатенате" in res_concat or "кон" in res_concat  # eвристика сработала

        assert replacer.apply("cat!", persist_new=False) == "кот!"
        # "the cat, sat" — "the" и "sat"? sat — не service, но "and"? Используем service word "and"
        # cat — в flat_rules, поэтому вернёт замену даже внутри прозы
        res = replacer.apply("the cat and the dog", persist_new=False)
        # dog тоже lowercase term, но если persist_new=False — он транслитерируется, но cat точно заменён
        assert "кот" in res
        assert "cat" not in res.lower()

    def test_apply_longer_first(self, replacer: WordReplacer):
        replacer.add_rule("test", "тест", category="custom")
        replacer.add_rule("test case", "тест кейс", category="custom")
        # длиннее правило должно сработать первым
        result = replacer.apply("test case")
        assert result == "тест кейс"

    def test_apply_prose_protection_blocks_abbrev(self, replacer: WordReplacer):
        # "CPU is fast" — после CPU идет service word "is", должно защитить от транслитерации
        # без правил flat_rules — CPU должен остаться как есть
        text = "This is CPU"
        result = replacer.apply(text, persist_new=False)
        assert "CPU" in result

    def test_apply_abbrev_list_transliterates(self, replacer: WordReplacer):
        # список аббревиатур через пробел — не считается прозой, должен транслитерироваться
        result = replacer.apply("CPU GPU RAM", persist_new=False)
        # должен замениться, т.е. не содержать оригиналов
        assert "CPU" not in result or "си" in result.lower()
        # проверим что транслит сработал хотя бы для одного
        assert "пи" in result or "си" in result

    def test_apply_abbrev_auto_persist(self, tmp_path: Path):
        rules = tmp_path / "word_rules.json"
        rules.write_text("{}", encoding="utf-8")
        wr = WordReplacer(str(rules))
        # применим аббревиатуру, которой нет в словаре
        res = wr.apply("CPU GPU", persist_new=True)
        # после persist — правила появились в auto
        assert wr.get_category("CPU") == "auto"
        assert "CPU" in wr.flat_rules

    def test_apply_lowercase_term_transliterates(self, replacer: WordReplacer):
        # pydub — не служебное, ascii, нижний регистр — кандидат на транслит
        res = replacer.apply("pydub", persist_new=False)
        # должен вернуть непустой транслит (эвристика)
        assert res != "pydub"
        assert len(res) > 0

    def test_apply_service_words_not_transliterated(self, replacer: WordReplacer):
        for w in ["the", "and", "is", "fast"]:
            assert replacer.apply(w, persist_new=False) == w

    def test_apply_persist_new_false_does_not_save(self, tmp_path: Path):
        rules = tmp_path / "word_rules.json"
        rules.write_text("{}", encoding="utf-8")
        wr = WordReplacer(str(rules))
        wr.apply("XYZ", persist_new=False)
        assert wr.get_category("XYZ") is None

    def test_circular_blocking_no_infinite_loop(self, replacer: WordReplacer):
        # потенциальный цикл A->B, B->A не должен зациклить apply
        replacer.add_rule("foo", "bar", category="custom")
        replacer.add_rule("bar", "foo", category="auto")
        # priority custom > auto? Проверим: priority list builtin,auto,ai_corrected,custom -> custom выше auto, значит foo->bar остаётся
        # Но даже если оба есть — apply не должен зависнуть
        result = replacer.apply("foo bar", persist_new=False)
        # не падает и возвращает строку
        assert isinstance(result, str)
        assert len(result) > 0


class TestHelpers:
    def test_looks_like_abbrev(self):
        assert _looks_like_abbrev("CPU") is True
        assert _looks_like_abbrev("GPU") is True
        assert _looks_like_abbrev("XTTS") is True
        assert _looks_like_abbrev("a") is False  # <2
        assert _looks_like_abbrev("TOOLONGABBR") is False  # >6
        assert _looks_like_abbrev("Cpu") is False  # не все upper
        assert _looks_like_abbrev("CPU1") is False  # не alpha
        assert _looks_like_abbrev("ЦПУ") is False  # не ascii

    def test_auto_transliterate_abbrev(self):
        assert _auto_transliterate_abbrev("CPU") == "си пи ю"
        assert _auto_transliterate_abbrev("AI") == "эй ай"

    def test_looks_like_lowercase_term(self):
        assert _looks_like_lowercase_term("pydub") is True
        assert _looks_like_lowercase_term("ffmpeg") is True
        assert _looks_like_lowercase_term("GPU") is False
        assert _looks_like_lowercase_term("the") is False  # service word
        assert _looks_like_lowercase_term("a") is False  # слишком коротко
        assert _looks_like_lowercase_term("Привет") is False  # не ascii

    def test_transliterate_term_word(self):
        res = _transliterate_term_word("pydub")
        assert isinstance(res, str)
        assert len(res) > 0

    def test_letters_to_word_sound(self):
        res = _letters_to_word_sound("test")
        assert isinstance(res, str)
        assert len(res) > 0
