import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Мокаем зависимости до импорта settings_ui
# settings_store.SETTINGS_PATH будет переопределён
# gui.colors и gui.textbox уже есть в workspace как стабы, но тоже подстрахуемся

import engine.gui.settings_ui as settings_ui


# Хелпер для создания мока tk var с get/set
class MockVar:
    def __init__(self, value=None):
        self._value = value
        self.set_calls = []
        self.get_calls = 0

    def get(self):
        self.get_calls += 1
        return self._value

    def set(self, value):
        self.set_calls.append(value)
        self._value = value


@pytest.fixture
def mock_deps(tmp_path: Path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    # Подменяем SETTINGS_PATH в модуле
    monkeypatch.setattr("engine.settings_store.SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr("engine.gui.settings_ui.SETTINGS_PATH", str(settings_path), raising=False)

    # Патчим tk.BooleanVar — в оригинале он создаётся как дефолтный аргумент в .get(), что требует root
    # Заменяем на MockVar чтобы не требовал Tk.
    monkeypatch.setattr(settings_ui.tk, "BooleanVar", lambda *a, **kw: MockVar(False))

    # Создаём моки переменных
    lang_var = MockVar("ru")
    quality_var = MockVar("Высокое качество")
    ref_var = MockVar("/tmp/ref.wav")
    use_gpt = MockVar(False)
    word_replacer_enabled = MockVar(True)
    lang_split_enabled = MockVar(True)
    ui_lang_var = MockVar("ru")
    ai_btn = MagicMock()

    # quality_params — dict preset -> dict param -> MockVar или значение
    quality_params = {
        "Высокое качество": {
            "temperature": MockVar(0.7),
            "top_p": MockVar(0.8),
            "ai_conductor_enabled": MockVar(False),
            "ai_conductor_context": MockVar(""),
        },
        "Нарратив": {
            "temperature": MockVar(0.6),
            "ai_conductor_enabled": MockVar(False),
        },
    }

    # textbox
    import engine.gui.textbox as textbox_mod

    textbox_mod.text_font_size = {"v": 14}

    # Инициализируем зависимости
    settings_ui.init(
        lang_var=lang_var,
        quality_var=quality_var,
        ref_var=ref_var,
        use_gpt=use_gpt,
        word_replacer_enabled=word_replacer_enabled,
        lang_split_enabled=lang_split_enabled,
        ui_lang_var=ui_lang_var,
        quality_params=quality_params,
        ai_btn=ai_btn,
    )

    yield {
        "settings_path": settings_path,
        "lang_var": lang_var,
        "quality_var": quality_var,
        "ref_var": ref_var,
        "use_gpt": use_gpt,
        "word_replacer_enabled": word_replacer_enabled,
        "lang_split_enabled": lang_split_enabled,
        "ui_lang_var": ui_lang_var,
        "quality_params": quality_params,
        "ai_btn": ai_btn,
        "textbox": textbox_mod,
    }


class TestSaveSettings:
    def test_save_creates_file(self, mock_deps):
        path = mock_deps["settings_path"]
        assert not path.exists()
        settings_ui.save_settings()
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["language"] == "ru"
        assert data["quality"] == "Высокое качество"

    def test_save_preserves_ui_theme(self, mock_deps):
        """Критичный баг №8 — смена языка стирала ui_theme."""
        path = mock_deps["settings_path"]
        # Предзапишем файл с ui_theme
        path.write_text(
            json.dumps({"ui_theme": "light", "some_other": 123}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        settings_ui.save_settings()

        data = json.loads(path.read_text(encoding="utf-8"))
        # ui_theme должен остаться
        assert data["ui_theme"] == "light"
        assert data["some_other"] == 123
        # и новые поля тоже
        assert "language" in data

    def test_save_with_extra(self, mock_deps):
        path = mock_deps["settings_path"]
        settings_ui.save_settings(extra={"custom_key": "custom_val", "ui_theme": "dark"})
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["custom_key"] == "custom_val"
        assert data["ui_theme"] == "dark"

    def test_save_handles_invalid_existing_json(self, mock_deps):
        path = mock_deps["settings_path"]
        path.write_text("{ invalid json", encoding="utf-8")
        # не должен падать
        settings_ui.save_settings()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "language" in data

    def test_save_handles_non_dict_existing(self, mock_deps):
        path = mock_deps["settings_path"]
        path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        settings_ui.save_settings()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data["language"] == "ru"

    def test_save_quality_params_unwrapped(self, mock_deps):
        path = mock_deps["settings_path"]
        settings_ui.save_settings()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "quality_params" in data
        # MockVar должны быть развернуты через .get() или оставлены как есть
        assert data["quality_params"]["Высокое качество"]["temperature"] == 0.7
        assert data["quality_params"]["Высокое качество"]["top_p"] == 0.8

    def test_save_text_font_size(self, mock_deps):
        path = mock_deps["settings_path"]
        mock_deps["textbox"].text_font_size = {"v": 18}
        settings_ui.save_settings()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["text_font_size"] == 18


class TestApplySettings:
    def test_non_dict_does_nothing(self, mock_deps):
        # не должен падать
        settings_ui.apply_settings(None)
        settings_ui.apply_settings("string")
        settings_ui.apply_settings(123)

    def test_text_font_size_restored(self, mock_deps):
        settings_ui.apply_settings({"text_font_size": 20})
        assert mock_deps["textbox"].text_font_size["v"] == 20

    def test_language_applied(self, mock_deps):
        settings_ui.apply_settings({"language": "en"})
        assert mock_deps["lang_var"]._value == "en"

    def test_use_gpt_applied(self, mock_deps):
        settings_ui.apply_settings({"use_gpt": True})
        assert mock_deps["use_gpt"]._value is True

    def test_quality_valid(self, mock_deps):
        settings_ui.apply_settings({"quality": "Нарратив"})
        assert mock_deps["quality_var"]._value == "Нарратив"

    def test_quality_invalid_fallback(self, mock_deps):
        settings_ui.apply_settings({"quality": "Несуществующий пресет"})
        assert mock_deps["quality_var"]._value == "Высокое качество"

    def test_ref_path_exists(self, mock_deps, tmp_path):
        fake_wav = tmp_path / "ref.wav"
        fake_wav.write_text("fake", encoding="utf-8")
        settings_ui.apply_settings({"ref_path": str(fake_wav)})
        assert mock_deps["ref_var"]._value == str(fake_wav)

    def test_ref_path_not_exists_ignored(self, mock_deps):
        original = mock_deps["ref_var"]._value
        settings_ui.apply_settings({"ref_path": "/non/existing/path.wav"})
        assert mock_deps["ref_var"]._value == original

    def test_word_replacer_and_lang_split(self, mock_deps):
        settings_ui.apply_settings({"word_replacer_enabled": False, "lang_split_enabled": False})
        assert mock_deps["word_replacer_enabled"]._value is False
        assert mock_deps["lang_split_enabled"]._value is False

    def test_ui_language_valid(self, mock_deps):
        settings_ui.apply_settings({"ui_language": "en"})
        assert mock_deps["ui_lang_var"]._value == "en"
        # set_language из i18n должен был вызваться — проверим через get_language
        from i18n import get_language

        assert get_language() == "en"
        # вернём обратно
        settings_ui.apply_settings({"ui_language": "ru"})

    def test_ui_language_invalid_ignored(self, mock_deps):
        original = mock_deps["ui_lang_var"]._value
        settings_ui.apply_settings({"ui_language": "fr"})
        assert mock_deps["ui_lang_var"]._value == original

    def test_ai_conductor_enabled_propagates(self, mock_deps):
        settings_ui.apply_settings({"ai_conductor_enabled": True})
        for preset in mock_deps["quality_params"].values():
            if "ai_conductor_enabled" in preset:
                assert preset["ai_conductor_enabled"]._value is True

    def test_quality_params_nested_applied(self, mock_deps):
        settings_ui.apply_settings({"quality_params": {"Высокое качество": {"temperature": 0.85}}})
        assert mock_deps["quality_params"]["Высокое качество"]["temperature"]._value == 0.85

    def test_quality_params_unknown_preset_ignored(self, mock_deps):
        # не должен падать если пресет неизвестен
        settings_ui.apply_settings({"quality_params": {"Unknown": {"temperature": 0.9}}})
        # существующие не тронуты (кроме тех что менялись в других тестах, но не должны упасть)
        assert True

    def test_ai_rewrite_fields(self, mock_deps):
        # Добавим поля для теста
        mock_deps["quality_params"]["Высокое качество"]["ai_rewrite_enabled"] = MockVar(False)
        mock_deps["quality_params"]["Высокое качество"]["ai_rewrite_context"] = MockVar("")
        mock_deps["quality_params"]["Высокое качество"]["ai_rewrite_negative"] = MockVar("")

        settings_ui.apply_settings(
            {
                "ai_rewrite_enabled": True,
                "ai_rewrite_context": "epic",
                "ai_rewrite_negative": "boring",
            }
        )
        assert mock_deps["quality_params"]["Высокое качество"]["ai_rewrite_enabled"]._value is True
        assert (
            mock_deps["quality_params"]["Высокое качество"]["ai_rewrite_context"]._value == "epic"
        )
        assert (
            mock_deps["quality_params"]["Высокое качество"]["ai_rewrite_negative"]._value
            == "boring"
        )
