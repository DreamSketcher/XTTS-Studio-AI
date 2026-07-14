import json
import sys

import pytest

from engine.ai_conductor import _fallback_params, _validate_map, _word_count


class TestWordCount:
    def test_simple(self):
        assert _word_count("привет мир") == 2
        assert _word_count("one two three") == 3
        assert _word_count("") == 0
        assert _word_count("   ... !!! ") == 0

    def test_mixed_numbers(self):
        assert _word_count("тест 123") == 2
        assert _word_count("hello-привет 42") == 3  # hello, привет, 42

    def test_with_tags(self):
        # _word_count считает любые слова, даже внутри [NO_PAUSE]?
        # в conductor _word_count просто по regex, теги тоже могут считаться как слова без скобок
        assert _word_count("[NO_PAUSE]") == 2  # NO и PAUSE
        assert _word_count("hello [NO_PAUSE] world") == 4


class TestFallbackParams:
    def test_length_matches(self):
        chunks = ["a", "b c d", "e"]
        params = _fallback_params(chunks)
        assert len(params) == 3

    def test_last_pause_zero(self):
        chunks = ["first chunk here", "second", "last one"]
        params = _fallback_params(chunks)
        assert params[-1]["pause_after_ms"] == 0
        assert params[0]["pause_after_ms"] != 0
        assert params[1]["pause_after_ms"] != 0

    def test_short_chunks_pause_250(self):
        # wc <6 → 250
        chunks = ["привет", "короткий текст"]
        params = _fallback_params(chunks)
        # оба не последние
        assert params[0]["pause_after_ms"] == 250  # 1 word
        assert params[1]["pause_after_ms"] == 0  # last
        # проверим отдельно 2 чанка: первый короткий
        chunks2 = ["привет", "это второй чанк длиннее чем шесть слов точно да"]
        params2 = _fallback_params(chunks2)
        assert params2[0]["pause_after_ms"] == 250
        # второй — last → 0

    def test_long_chunks_pause_450(self):
        chunks = ["это достаточно длинный чанк из семи слов", "последний"]
        params = _fallback_params(chunks)
        assert params[0]["pause_after_ms"] == 450
        assert params[1]["pause_after_ms"] == 0

    def test_default_values_in_range(self):
        chunks = ["a"] * 5
        params = _fallback_params(chunks)
        for p in params:
            assert 0.50 <= p["temperature"] <= 0.90
            assert 0.70 <= p["top_p"] <= 0.95
            assert 5.0 <= p["repetition_penalty"] <= 12.0
            assert 0.5 <= p["length_penalty"] <= 2.0
            assert 0.75 <= p["speed"] <= 1.25
            assert 0 <= p["pause_after_ms"] <= 1200


class TestValidateMap:
    def test_not_a_list_returns_none(self):
        assert _validate_map({"a": 1}, 2) is None
        assert _validate_map("string", 1) is None
        assert _validate_map(None, 1) is None

    def test_item_not_dict_returns_none(self):
        data = [{"temperature": 0.7}, "not a dict"]
        assert _validate_map(data, 2) is None

    def test_bad_value_returns_none(self):
        data = [{"temperature": "not-a-number"}]
        assert _validate_map(data, 1) is None

    def test_length_mismatch_truncates(self):
        # больше чем нужно → обрезается
        data = [
            {"temperature": 0.6, "top_p": 0.8},
            {"temperature": 0.7, "top_p": 0.8},
            {"temperature": 0.8, "top_p": 0.8},
        ]
        result = _validate_map(data, expected_len=2)
        assert result is not None
        assert len(result) == 2
        assert result[0]["temperature"] == 0.6
        assert result[1]["temperature"] == 0.7

    def test_length_mismatch_pads_with_fallback(self):
        data = [{"temperature": 0.6}]
        result = _validate_map(data, expected_len=3)
        assert result is not None
        assert len(result) == 3
        # первый — из data
        assert result[0]["temperature"] == 0.6
        # остальные — из fallback
        assert result[1]["temperature"] == 0.70
        assert result[2]["temperature"] == 0.70
        # последний pause должен быть 0 даже если из fallback
        assert result[-1]["pause_after_ms"] == 0

    def test_clamping_lower_bounds(self):
        data = [
            {
                "temperature": 0.1,  # <0.50
                "top_p": 0.1,  # <0.70
                "repetition_penalty": 1.0,  # <5.0
                "length_penalty": 0.1,  # <0.5
                "speed": 0.1,  # <0.75
                "pause_after_ms": -100,  # <0
            }
        ]
        result = _validate_map(data, 1)
        assert result is not None
        assert result[0]["temperature"] == 0.50
        assert result[0]["top_p"] == 0.70
        assert result[0]["repetition_penalty"] == 5.0
        assert result[0]["length_penalty"] == 0.5
        assert result[0]["speed"] == 0.75
        # last chunk → pause always 0 regardless
        assert result[0]["pause_after_ms"] == 0

    def test_clamping_upper_bounds(self):
        data = [
            {
                "temperature": 1.5,
                "top_p": 2.0,
                "repetition_penalty": 20,
                "length_penalty": 5,
                "speed": 2.0,
                "pause_after_ms": 5000,
            },
            {
                "temperature": 0.6,
                "top_p": 0.8,
                "repetition_penalty": 9,
                "length_penalty": 1.0,
                "speed": 1.0,
                "pause_after_ms": 5000,
            },
        ]
        result = _validate_map(data, 2)
        assert result is not None
        # первый не последний → clamping
        assert result[0]["temperature"] == 0.90
        assert result[0]["top_p"] == 0.95
        assert result[0]["repetition_penalty"] == 12.0
        assert result[0]["length_penalty"] == 2.0
        assert result[0]["speed"] == 1.25
        assert result[0]["pause_after_ms"] == 1200
        # второй — last → pause 0 даже если 5000
        assert result[1]["pause_after_ms"] == 0
        assert result[1]["temperature"] == 0.6  # внутри диапазона — не клампится

    def test_defaults_when_missing_keys(self):
        data = [{}]
        result = _validate_map(data, 1)
        assert result is not None
        assert result[0]["temperature"] == 0.70
        assert result[0]["top_p"] == 0.82
        assert result[0]["repetition_penalty"] == 9.0
        assert result[0]["length_penalty"] == 1.0
        assert result[0]["speed"] == 1.0
        assert result[0]["pause_after_ms"] == 0  # last

    def test_defaults_for_non_last(self):
        data = [{}, {}]
        result = _validate_map(data, 2)
        assert result is not None
        assert result[0]["pause_after_ms"] == 450  # default для не последнего
        assert result[1]["pause_after_ms"] == 0

    def test_corrections_preserved_if_dict(self):
        data = [
            {"temperature": 0.7, "corrections": {"cmake": "си мэйк"}},
            {"temperature": 0.7, "corrections": "not a dict"},
            {"temperature": 0.7},
        ]
        result = _validate_map(data, 3)
        assert result is not None
        assert "corrections" in result[0]
        assert result[0]["corrections"] == {"cmake": "си мэйк"}
        assert "corrections" not in result[1]  # не dict → игнорируется
        assert "corrections" not in result[2]

    def test_pause_int_conversion(self):
        # для не последнего чанка int("300.9") → ValueError → None
        assert _validate_map([{"pause_after_ms": "300.9"}, {"pause_after_ms": 0}], 2) is None
        # для последнего чанка pause всегда 0, даже если вход "300.9" — ошибка не вылетает
        assert _validate_map([{"pause_after_ms": "300.9"}], 1) is not None
        assert _validate_map([{"pause_after_ms": "300.9"}], 1)[0]["pause_after_ms"] == 0
        # int строка "300" должна работать
        assert _validate_map([{"pause_after_ms": "300"}], 1) is not None
        result = _validate_map([{"pause_after_ms": 300}, {"pause_after_ms": 300}], 2)
        assert result[0]["pause_after_ms"] == 300
        assert result[1]["pause_after_ms"] == 0

    def test_float_string_values(self):
        data = [{"temperature": "0.75", "top_p": "0.85"}]
        result = _validate_map(data, 1)
        assert result is not None
        assert result[0]["temperature"] == 0.75
        assert result[0]["top_p"] == 0.85

    def test_empty_list_expected_zero(self):
        # conduct возвращает None если chunks пустые, но _validate_map с 0 должен вернуть []
        result = _validate_map([], 0)
        assert result == []


class TestConductIntegrationWithMock:
    """Интеграционный дымовой тест conduct() с замоканным gpt_client."""

    def test_conduct_returns_fallback_on_invalid_json(self, monkeypatch):
        # создаём фейковый gpt_client модуль
        import types

        fake_gpt = types.ModuleType("fake_gpt")

        class AIUnavailable(Exception):
            pass

        def mock_call(messages, max_tokens=0):
            return "not a json at all"

        fake_gpt.AIUnavailable = AIUnavailable
        fake_gpt._call_with_chain = mock_call

        # подменяем engine.gpt_client
        monkeypatch.setitem(sys.modules, "engine.gpt_client", fake_gpt)
        # также для относительного импорта engine.ai_conductor -> .gpt_client
        # Нужно подсунуть модуль как engine.gpt_client уже есть, from .gpt_client попробует относительный,
        # но он найдёт через sys.modules

        from engine.ai_conductor import conduct

        chunks = ["привет мир", "как дела"]
        result = conduct("привет мир как дела", chunks, quality_params={})
        # при невалидном JSON conduct должен вернуть fallback
        assert result is not None
        assert len(result) == 2

    def test_conduct_returns_none_on_ai_unavailable(self, monkeypatch):
        import types

        fake_gpt = types.ModuleType("fake_gpt2")

        class AIUnavailable(Exception):
            pass

        def mock_call(messages, max_tokens=0):
            raise AIUnavailable("no key")

        fake_gpt.AIUnavailable = AIUnavailable
        fake_gpt._call_with_chain = mock_call

        monkeypatch.setitem(sys.modules, "engine.gpt_client", fake_gpt)

        from engine.ai_conductor import conduct

        chunks = ["test"]
        result = conduct("test", chunks, {})
        assert result is None
