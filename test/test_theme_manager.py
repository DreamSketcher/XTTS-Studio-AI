import json
import os
from pathlib import Path

import pytest

import engine.gui.theme_manager as tm


@pytest.fixture
def tmp_theme_file(tmp_path: Path, monkeypatch):
    file_path = tmp_path / "theme_settings.json"
    monkeypatch.setattr(tm, "THEME_FILE", str(file_path))
    # также через paths.BASE_DIR? уже переопределили через прямой атрибут
    yield file_path


class TestLoadAndSave:
    def test_load_returns_default_when_missing(self, tmp_theme_file: Path):
        assert not tmp_theme_file.exists()
        theme = tm.load_theme()
        assert theme["layout"] == tm.DEFAULT_THEME["layout"]
        assert "colors" in theme
        assert "presets" in theme

    def test_load_merges_existing(self, tmp_theme_file: Path):
        # запишем кастом
        tmp_theme_file.write_text(
            json.dumps({"font_base_size": 18, "sidebar_side": "right"}, ensure_ascii=False),
            encoding="utf-8",
        )
        theme = tm.load_theme()
        assert theme["font_base_size"] == 18
        assert theme["sidebar_side"] == "right"
        # дефолты остались
        assert "colors" in theme
        assert "presets" in theme

    def test_save_read_modify_write(self, tmp_theme_file: Path):
        tmp_theme_file.write_text(
            json.dumps({"ui_theme": "light", "custom_key": 123}, ensure_ascii=False),
            encoding="utf-8",
        )
        tm.save_theme({"font_base_size": 20})
        data = json.loads(tmp_theme_file.read_text(encoding="utf-8"))
        assert data["ui_theme"] == "light"  # сохранён
        assert data["custom_key"] == 123
        assert data["font_base_size"] == 20
        assert "presets" in data

    def test_save_syncs_layout_layout_preset(self, tmp_theme_file: Path):
        # preset -> layout sync (preset wins)
        tm.save_theme({"layout_preset": "compact"})
        data = json.loads(tmp_theme_file.read_text(encoding="utf-8"))
        assert data["layout_preset"] == "compact"
        assert data["layout"] == "compact"

        # если в файле уже есть preset, сохранение только layout не перетирает preset (preset приоритет)
        tm.save_theme({"layout": "wide"})
        data = json.loads(tmp_theme_file.read_text(encoding="utf-8"))
        # preset остался compact, layout перезаписан preset-ом обратно в compact
        assert data["layout_preset"] == "compact"
        assert data["layout"] == "compact"

        # чистый файл, только layout -> должен синхронизировать в preset
        tmp_theme_file.write_text(json.dumps({}), encoding="utf-8")
        tm.save_theme({"layout": "wide"})
        data = json.loads(tmp_theme_file.read_text(encoding="utf-8"))
        assert data["layout"] == "wide"
        assert data["layout_preset"] == "wide"

    def test_load_invalid_json_returns_default(self, tmp_theme_file: Path, capsys):
        tmp_theme_file.write_text("{ invalid", encoding="utf-8")
        theme = tm.load_theme()
        assert theme["font_base_size"] == tm.DEFAULT_THEME["font_base_size"]


class TestLayoutPresets:
    def test_get_layout_presets_merges(self, tmp_theme_file: Path):
        # дефолтные всегда есть
        presets = tm.get_layout_presets()
        assert "classic" in presets
        assert "compact" in presets
        assert "wide" in presets

        # добавим кастомный через файл
        tmp_theme_file.write_text(
            json.dumps({"presets": {"custom": {"left_panel_width": 999}}}), encoding="utf-8"
        )
        presets = tm.get_layout_presets()
        assert "custom" in presets
        assert presets["custom"]["left_panel_width"] == 999

    def test_current_preset_name_fallback(self, tmp_theme_file: Path):
        tmp_theme_file.write_text(json.dumps({"layout_preset": "nonexistent"}), encoding="utf-8")
        assert tm.get_current_layout_preset_name() == "classic"

        tmp_theme_file.write_text(json.dumps({"layout_preset": "compact"}), encoding="utf-8")
        assert tm.get_current_layout_preset_name() == "compact"

    def test_get_preset_copy(self, tmp_theme_file: Path):
        preset = tm.get_layout_preset("classic")
        assert isinstance(preset, dict)
        # копия, не ссылка
        preset["left_panel_width"] = 9999
        assert tm.get_layout_preset("classic")["left_panel_width"] != 9999

    def test_set_layout_preset(self, tmp_theme_file: Path):
        assert tm.set_layout_preset("compact") is True
        data = json.loads(tmp_theme_file.read_text(encoding="utf-8"))
        assert data["layout_preset"] == "compact"

        assert tm.set_layout_preset("nonexistent") is False

    def test_layout_hint(self, tmp_theme_file: Path):
        assert tm.is_layout_hint_shown() is False
        tm.mark_layout_hint_shown()
        assert tm.is_layout_hint_shown() is True


class TestAudioRepeat:
    def test_get_set(self, tmp_theme_file: Path):
        assert tm.get_audio_repeat() is False
        assert tm.set_audio_repeat(True) is True
        assert tm.get_audio_repeat() is True
        assert tm.get_audio_repeat_state() is True
        assert tm.is_audio_repeat() is True
        assert tm.set_audio_repeat(False) is True
        assert tm.get_audio_repeat() is False


class TestCustomColors:
    def test_set_get_reset(self, tmp_theme_file: Path):
        assert tm.get_custom_colors("dark") == {}
        assert tm.set_custom_colors("dark", {"BG_MAIN": "#000000"}) is True
        assert tm.get_custom_colors("dark") == {"BG_MAIN": "#000000"}
        assert tm.reset_custom_colors("dark") is True
        assert tm.get_custom_colors("dark") == {}

    def test_invalid_theme_name(self, tmp_theme_file: Path):
        assert tm.set_custom_colors("invalid", {}) is False


class TestFontSize:
    def test_get_default(self, tmp_theme_file: Path):
        assert tm.get_font_base_size() == 10

    def test_set_clamping(self, tmp_theme_file: Path):
        assert tm.set_font_base_size(100) is True  # clamps to 24
        assert tm.get_font_base_size() == 24
        assert tm.set_font_base_size(-5) is True  # clamps to 6
        assert tm.get_font_base_size() == 6
        assert tm.set_font_base_size("not a number") is False


class TestSidebarAndToolbar:
    def test_sidebar_side(self, tmp_theme_file: Path):
        assert tm.get_sidebar_side() == "left"
        assert tm.set_sidebar_side("right") is True
        assert tm.get_sidebar_side() == "right"
        assert tm.set_sidebar_side("invalid") is False
        # файл с битым значением → fallback left
        tmp_theme_file.write_text(json.dumps({"sidebar_side": "middle"}), encoding="utf-8")
        assert tm.get_sidebar_side() == "left"

    def test_toolbar_order_validation(self, tmp_theme_file: Path):
        assert tm.get_toolbar_order() == tm.DEFAULT_TOOLBAR_ORDER

        # дубликаты и мусор фильтруются, недостающие добавляются
        tmp_theme_file.write_text(
            json.dumps({"toolbar_order": ["file", "file", "invalid", "ai"]}), encoding="utf-8"
        )
        order = tm.get_toolbar_order()
        assert order.count("file") == 1
        assert "invalid" not in order
        assert set(order) == set(tm.TOOLBAR_PANELS)
        assert len(order) == 4

        assert tm.set_toolbar_order(["action", "file"]) is True
        data = json.loads(tmp_theme_file.read_text(encoding="utf-8"))
        # должен дополниться до 4
        assert len(data["toolbar_order"]) == 4
        assert data["toolbar_order"][0] == "action"

        assert tm.set_toolbar_order("not a list") is False


class TestHeaderRainbow:
    def test_get_set(self, tmp_theme_file: Path):
        assert tm.get_header_rainbow() is False
        assert tm.set_header_rainbow(True) is True
        assert tm.get_header_rainbow() is True

        assert tm.get_header_author_rainbow() is False
        assert tm.set_header_author_rainbow(True) is True
        assert tm.get_header_author_rainbow() is True

    def test_normalize_rainbow_style(self):
        # speed clamping 16-200
        style = tm._normalize_rainbow_style({"speed_ms": 5}, tm.DEFAULT_HEADER_RAINBOW_STYLE)
        assert style["speed_ms"] == 16
        style = tm._normalize_rainbow_style({"speed_ms": 500}, tm.DEFAULT_HEADER_RAINBOW_STYLE)
        assert style["speed_ms"] == 200

        # saturation 0-1
        style = tm._normalize_rainbow_style({"saturation": 2.0}, tm.DEFAULT_HEADER_RAINBOW_STYLE)
        assert style["saturation"] == 1.0

        # mode fallback
        style = tm._normalize_rainbow_style({"mode": "invalid"}, tm.DEFAULT_HEADER_RAINBOW_STYLE)
        assert style["mode"] == "hsv"

        # colors dedup and hex normalization
        style = tm._normalize_rainbow_style(
            {"colors": ["#FF0000", "ff0000", " #00ff00 ", "invalid", "#0000ff"]},
            tm.DEFAULT_HEADER_RAINBOW_STYLE,
        )
        assert len(style["colors"]) == 3  # dedup после lower, invalid отброшен
        assert "#ff0000" in style["colors"]

        # max 12 colors
        many = [f"#{i:06x}" for i in range(20)]
        style = tm._normalize_rainbow_style({"colors": many}, tm.DEFAULT_HEADER_RAINBOW_STYLE)
        assert len(style["colors"]) == 12

    def test_set_get_style(self, tmp_theme_file: Path):
        assert tm.set_header_rainbow_style({"speed_ms": 80, "saturation": 0.5}) is True
        style = tm.get_header_rainbow_style()
        assert style["speed_ms"] == 80
        assert style["saturation"] == 0.5

        assert tm.reset_header_rainbow_style() is True
        style = tm.get_header_rainbow_style()
        assert style["speed_ms"] == tm.DEFAULT_HEADER_RAINBOW_STYLE["speed_ms"]

    def test_author_style(self, tmp_theme_file: Path):
        assert tm.set_header_author_rainbow_style({"brightness": 0.9}) is True
        style = tm.get_header_author_rainbow_style()
        assert style["brightness"] == 0.9

    def test_norm_hex(self):
        assert tm._norm_hex("#ff0000") == "#ff0000"
        assert tm._norm_hex("ff0000") == "#ff0000"
        assert tm._norm_hex(" #FF0000 ") == "#ff0000"
        assert tm._norm_hex("invalid") is None
        assert tm._norm_hex(123) is None


class TestNeonButtons:
    def test_get_default(self, tmp_theme_file: Path):
        buttons = tm.get_neon_buttons()
        assert set(buttons.keys()) == set(tm.NEON_BUTTON_IDS)
        for bid in tm.NEON_BUTTON_IDS:
            assert "enabled" in buttons[bid]
            assert "style" in buttons[bid]

    def test_set_and_get_enabled(self, tmp_theme_file: Path):
        assert tm.set_neon_button_enabled("chat", False) is True
        assert tm.get_neon_button_enabled("chat") is False
        assert tm.set_neon_button_enabled("invalid", True) is False

    def test_set_style(self, tmp_theme_file: Path):
        assert tm.set_neon_button_style("ai", {"saturation": 0.3}) is True
        style = tm.get_neon_button_style("ai")
        assert style["saturation"] == 0.3
        assert tm.set_neon_button_style("invalid", {}) is False

    def test_normalize_legacy_bool(self):
        # legacy bool → normalized
        raw = {"chat": True, "ai": False}
        norm = tm._normalize_neon_buttons(raw)
        assert norm["chat"]["enabled"] is True
        assert norm["ai"]["enabled"] is False


class TestSavedPresets:
    def test_save_get_delete(self, tmp_theme_file: Path):
        assert tm.get_saved_presets() == {}
        snapshot = {"theme_name": "dark", "font_base_size": 12, "layout_preset": "compact"}
        assert tm.save_named_preset("my_preset", snapshot) is True
        assert "my_preset" in tm.get_saved_presets()
        assert tm.delete_named_preset("my_preset") is True
        assert "my_preset" not in tm.get_saved_presets()
        assert tm.delete_named_preset("nonexistent") is False
        assert tm.save_named_preset("", {}) is False

    def test_apply_preset(self, tmp_theme_file: Path):
        snapshot = {
            "theme_name": "dark",
            "custom_colors": {"BG_MAIN": "#111"},
            "font_base_size": 11,
            "layout_preset": "compact",
            "sidebar_side": "right",
            "toolbar_order": ["ai", "file", "output", "action"],
            "header_rainbow": True,
            "header_rainbow_style": {"speed_ms": 60},
        }
        tm.save_named_preset("test", snapshot)
        result = tm.apply_named_preset("test")
        assert result is not None
        assert result["theme_name"] == "dark"
        # проверим что side и toolbar применились
        assert tm.get_sidebar_side() == "right"
        assert tm.get_toolbar_order()[0] == "ai"
        assert tm.get_header_rainbow() is True

        assert tm.apply_named_preset("nonexistent") is None
