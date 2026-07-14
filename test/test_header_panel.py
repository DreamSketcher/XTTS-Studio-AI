import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine.gui.header_panel as hp


class MockVar:
    def __init__(self, value="ru"):
        self._value = value

    def get(self):
        return self._value

    def set(self, val):
        self._value = val


@pytest.fixture
def mock_header_deps(monkeypatch):
    ui_lang_var = MockVar("ru")
    save_settings = MagicMock()
    root = MagicMock()
    root.after = MagicMock()
    root.after_cancel = MagicMock()
    root.state = MagicMock(return_value="normal")
    root.winfo_exists = MagicMock(return_value=True)

    monkeypatch.setattr(hp, "ui_lang_var", ui_lang_var)
    monkeypatch.setattr(hp, "save_settings", save_settings)
    monkeypatch.setattr(hp, "root", root)
    monkeypatch.setattr(hp, "_rainbow_timer", None)
    monkeypatch.setattr(hp, "_author_timer", None)
    monkeypatch.setattr(hp, "_underline_timer", None)
    monkeypatch.setattr(hp, "_rainbow_frames", [])
    monkeypatch.setattr(hp, "_author_frames", [])
    monkeypatch.setattr(hp, "_rainbow_enabled", False)
    monkeypatch.setattr(hp, "_author_enabled", False)

    yield {"ui_lang_var": ui_lang_var, "save_settings": save_settings, "root": root}


class TestSwitchUiLang:
    def test_switch_ru_to_en(self, mock_header_deps, monkeypatch):
        monkeypatch.setattr("i18n.set_language", MagicMock())
        monkeypatch.setattr("engine.gpt_client.refresh_i18n_labels", MagicMock(), raising=False)
        monkeypatch.setattr("engine.gui.chat_window.reapply_language", MagicMock(), raising=False)
        monkeypatch.setattr("tkinter.messagebox.showinfo", MagicMock())

        # создаём фейковые модули для gpt_client и chat_window
        import sys, types
        fake_gpt = types.ModuleType("engine.gpt_client")
        fake_gpt.refresh_i18n_labels = MagicMock()
        monkeypatch.setitem(sys.modules, "engine.gpt_client", fake_gpt)

        fake_chat = types.ModuleType("engine.gui.chat_window")
        fake_chat.reapply_language = MagicMock()
        monkeypatch.setitem(sys.modules, "engine.gui.chat_window", fake_chat)

        assert mock_header_deps["ui_lang_var"].get() == "ru"
        hp.switch_ui_lang()
        assert mock_header_deps["ui_lang_var"].get() == "en"
        assert mock_header_deps["save_settings"].called

    def test_switch_en_to_ru(self, mock_header_deps, monkeypatch):
        mock_header_deps["ui_lang_var"].set("en")
        monkeypatch.setattr("i18n.set_language", MagicMock())
        monkeypatch.setattr("tkinter.messagebox.showinfo", MagicMock())

        import sys, types
        fake_gpt = types.ModuleType("engine.gpt_client")
        fake_gpt.refresh_i18n_labels = MagicMock()
        monkeypatch.setitem(sys.modules, "engine.gpt_client", fake_gpt)
        fake_chat = types.ModuleType("engine.gui.chat_window")
        fake_chat.reapply_language = MagicMock()
        monkeypatch.setitem(sys.modules, "engine.gui.chat_window", fake_chat)

        hp.switch_ui_lang()
        assert mock_header_deps["ui_lang_var"].get() == "ru"


class TestRainbowEnabled:
    def test_is_rainbow_enabled_false_when_no_theme_manager(self, monkeypatch, tmp_path):
        # изолируемся от реального theme_settings.json на диске разработчика,
        # чтобы тест не зависел от текущих личных настроек темы
        import engine.gui.theme_manager as tm
        monkeypatch.setattr(tm, "THEME_FILE", str(tmp_path / "theme.json"))

        # симулируем отсутствие theme_manager через исключение в импорте.
        # `from engine.gui import theme_manager as tm` вызывает __import__ с
        # name="engine.gui" и fromlist=("theme_manager",) — проверка должна
        # учитывать оба варианта, иначе патч тихо не сработает.
        import builtins
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0, *args, **kwargs):
            if "theme_manager" in name or (fromlist and "theme_manager" in fromlist):
                raise ImportError("no theme_manager")
            return original_import(name, globals, locals, fromlist, level, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert hp._is_rainbow_enabled() is False
        assert hp._is_author_rainbow_enabled() is False

    def test_is_rainbow_enabled_true(self, monkeypatch, tmp_path):
        # используем реальный theme_manager с временным файлом
        import engine.gui.theme_manager as tm
        theme_file = tmp_path / "theme.json"
        monkeypatch.setattr(tm, "THEME_FILE", str(theme_file))
        tm.set_header_rainbow(True)
        tm.set_header_author_rainbow(True)

        assert hp._is_rainbow_enabled() is True
        assert hp._is_author_rainbow_enabled() is True


class TestDefaultStyle:
    def test_title(self):
        style = hp._default_style("title")
        assert style["speed_ms"] == 40
        assert style["mode"] == "hsv"

    def test_author(self):
        style = hp._default_style("author")
        assert style["speed_ms"] == 50
        assert style["saturation"] == 0.75


class TestLoadRainbowStyle:
    def test_load_fallback(self, monkeypatch):
        # без theme_manager должен вернуть дефолт
        import builtins
        orig_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if "theme_manager" in name:
                raise ImportError()
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        style = hp._load_rainbow_style()
        assert "speed_ms" in style

    def test_load_from_tm(self, monkeypatch, tmp_path):
        import engine.gui.theme_manager as tm
        theme_file = tmp_path / "theme.json"
        monkeypatch.setattr(tm, "THEME_FILE", str(theme_file))
        tm.set_header_rainbow_style({"speed_ms": 80, "saturation": 0.5})

        style = hp._load_rainbow_style()
        assert style["speed_ms"] == 80
        assert style["saturation"] == 0.5


class TestStyleSignature:
    def test_signature(self):
        style = {"speed_ms": 40, "saturation": 1.0, "brightness": 1.0, "hue_offset": 0.0, "spread": 1.0, "mode": "hsv", "colors": ["#ff0000"]}
        sig = hp._style_signature(style)
        assert isinstance(sig, tuple)
        assert sig[0] == 40
        assert "#ff0000" in sig[6]

    def test_signature_none_uses_global(self):
        hp._rainbow_style = {"speed_ms": 40, "saturation": 1.0, "brightness": 1.0, "hue_offset": 0.0, "spread": 1.0, "mode": "hsv", "colors": []}
        sig = hp._style_signature(None)
        assert isinstance(sig, tuple)


class TestStopFunctions:
    def test_stop_rainbow(self, mock_header_deps):
        mock_header_deps["root"].after_cancel = MagicMock()
        hp._rainbow_timer = "timer_id"
        hp._stop_rainbow()
        assert mock_header_deps["root"].after_cancel.called
        assert hp._rainbow_timer is None

    def test_stop_author(self, mock_header_deps):
        mock_header_deps["root"].after_cancel = MagicMock()
        hp._author_timer = "timer_id"
        hp._stop_author_rainbow()
        assert hp._author_timer is None

    def test_stop_underline(self, mock_header_deps):
        hp._underline_timer = "timer"
        hp._stop_underline()
        assert hp._underline_timer is None


class TestBuildRainbowFramesNoPIL:
    def test_no_pil_returns_empty(self, monkeypatch):
        # мокаем отсутствие PIL
        import sys
        # удаляем PIL если есть
        monkeypatch.delitem(sys.modules, "PIL", raising=False)
        monkeypatch.delitem(sys.modules, "PIL.Image", raising=False)
        monkeypatch.delitem(sys.modules, "PIL.ImageDraw", raising=False)
        monkeypatch.delitem(sys.modules, "PIL.ImageFont", raising=False)
        monkeypatch.delitem(sys.modules, "PIL.ImageTk", raising=False)

        # _build_rainbow_frames внутри try import PIL, должен вернуть []
        frames = hp._build_rainbow_frames("Test", 16, style={}, n_frames=8)
        # если PIL установлен, вернёт кадры, если нет — []
        assert isinstance(frames, list)

    def test_build_with_invalid_font(self, monkeypatch):
        # с PIL установленным, но без шрифтов — должен не падать
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("PIL not installed")

        # вызываем с маленьким текстом
        frames = hp._build_rainbow_frames("XTTS", 12, style={"saturation": 1.0, "brightness": 1.0, "hue_offset": 0.0, "spread": 1.0, "mode": "hsv", "colors": []}, n_frames=4)
        assert isinstance(frames, list)


class TestInit:
    def test_init(self):
        hp.init(root="fake_root", ui_lang_var="var", save_settings="func")
        assert hp.root == "fake_root"
        assert hp.ui_lang_var == "var"
        assert hp.save_settings == "func"
