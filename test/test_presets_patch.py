import pytest

try:
    import customtkinter
except ImportError:
    pytest.skip("customtkinter not installed", allow_module_level=True)

try:
    import pygame
except ImportError:
    pass


from engine.gui.presets_patch import (
    DEFAULT_RVC_PRESET_VALUES,
    PresetManagerPatch,
    PresetWindowUIController,
)


class TestDefaultValues:
    def test_defaults(self):
        assert DEFAULT_RVC_PRESET_VALUES["rvc_enable"] is False
        assert DEFAULT_RVC_PRESET_VALUES["rvc_model"] == ""
        assert DEFAULT_RVC_PRESET_VALUES["rvc_index_rate"] == 0.75
        assert DEFAULT_RVC_PRESET_VALUES["rvc_pitch_shift"] == 0
        assert DEFAULT_RVC_PRESET_VALUES["rvc_f0_method"] == "rmvpe"


class TestGetDefaultPreset:
    def test_high(self):
        preset = PresetManagerPatch.get_default_preset("high")
        assert preset["temperature"] == 0.75
        assert preset["rvc_index_rate"] == 0.75
        assert preset["rvc_enable"] is False

    def test_narrative(self):
        preset = PresetManagerPatch.get_default_preset("narrative")
        assert preset["rvc_index_rate"] == 0.85
        assert preset["rvc_f0_method"] == "rmvpe"

    def test_dynamic(self):
        preset = PresetManagerPatch.get_default_preset("dynamic")
        assert preset["rvc_index_rate"] == 0.65
        assert preset["rvc_f0_method"] == "pm"

    def test_expressive(self):
        preset = PresetManagerPatch.get_default_preset("expressive")
        assert preset["rvc_index_rate"] == 0.75
        assert preset["rvc_f0_method"] == "harvest"

    def test_unknown_name_uses_defaults(self):
        preset = PresetManagerPatch.get_default_preset("unknown")
        assert preset["rvc_index_rate"] == 0.75


class TestSanitizePreset:
    def test_fills_missing(self):
        old = {"temperature": 0.7}
        sanitized = PresetManagerPatch.sanitize_preset(old)
        for key in DEFAULT_RVC_PRESET_VALUES:
            assert key in sanitized
        assert sanitized["temperature"] == 0.7  # original preserved
        assert sanitized["rvc_enable"] is False

    def test_already_has_rvc(self):
        preset = {
            "rvc_enable": True,
            "rvc_model": "model.pth",
            "rvc_index_rate": 0.9,
            "rvc_pitch_shift": 2,
            "rvc_f0_method": "crepe",
        }
        sanitized = PresetManagerPatch.sanitize_preset(preset)
        assert sanitized["rvc_enable"] is True
        assert sanitized["rvc_model"] == "model.pth"

    def test_copy(self):
        original = {"a": 1}
        sanitized = PresetManagerPatch.sanitize_preset(original)
        assert sanitized is not original


class MockWidget:
    def __init__(self, value=None):
        self._value = value
        self.selected = False
        self.configured = {}
        self.text = ""

    def select(self):
        self.selected = True

    def deselect(self):
        self.selected = False

    def get(self):
        return self._value

    def set(self, val):
        self._value = val

    def configure(self, **kw):
        self.configured.update(kw)
        if "text" in kw:
            self.text = kw["text"]

    def delete(self, *a, **kw):
        self._value = ""

    def insert(self, idx, val):
        self._value = val


class TestUIController:
    def test_load_preset_to_widgets(self):
        widgets = {
            "chk_rvc": MockWidget(),
            "combo_rvc_model": MockWidget(),
            "slider_rvc_index": MockWidget(),
            "lbl_rvc_index_val": MockWidget(),
            "spin_rvc_pitch": MockWidget(),
            "combo_rvc_f0": MockWidget(),
        }
        ctrl = PresetWindowUIController(widgets)
        preset = {
            "rvc_enable": True,
            "rvc_model": "my.pth",
            "rvc_index_rate": 0.88,
            "rvc_pitch_shift": 3,
            "rvc_f0_method": "harvest",
        }

        ctrl.load_preset_to_widgets(preset)

        assert widgets["chk_rvc"].selected is True
        assert widgets["combo_rvc_model"].get() == "my.pth"
        assert widgets["slider_rvc_index"].get() == 0.88
        assert widgets["combo_rvc_f0"].get() == "harvest"
        # pitch formatting
        assert "+3" in widgets["spin_rvc_pitch"].get()

    def test_load_preset_disabled(self):
        widgets = {"chk_rvc": MockWidget()}
        ctrl = PresetWindowUIController(widgets)
        preset = {
            "rvc_enable": False,
            "rvc_model": "",
            "rvc_index_rate": 0.75,
            "rvc_pitch_shift": 0,
            "rvc_f0_method": "rmvpe",
        }

        ctrl.load_preset_to_widgets(preset)
        assert widgets["chk_rvc"].selected is False

    def test_load_preset_model_not_chosen(self):
        widgets = {"combo_rvc_model": MockWidget()}
        ctrl = PresetWindowUIController(widgets)
        preset = {
            "rvc_enable": False,
            "rvc_model": "",
            "rvc_index_rate": 0.75,
            "rvc_pitch_shift": 0,
            "rvc_f0_method": "rmvpe",
        }
        ctrl.load_preset_to_widgets(preset)
        assert widgets["combo_rvc_model"].get() == "Не выбрана"

    def test_save_widgets_to_preset(self):
        widgets = {
            "chk_rvc": MockWidget(True),
            "combo_rvc_model": MockWidget("model.pth"),
            "slider_rvc_index": MockWidget(0.77),
            "spin_rvc_pitch": MockWidget("+2"),
            "combo_rvc_f0": MockWidget("pm"),
        }
        ctrl = PresetWindowUIController(widgets)
        result = ctrl.save_widgets_to_preset()

        assert result["rvc_enable"] is True
        assert result["rvc_model"] == "model.pth"
        assert result["rvc_index_rate"] == 0.77
        assert result["rvc_pitch_shift"] == 2
        assert result["rvc_f0_method"] == "pm"

    def test_save_model_not_chosen(self):
        widgets = {"combo_rvc_model": MockWidget("Не выбрана")}
        ctrl = PresetWindowUIController(widgets)
        result = ctrl.save_widgets_to_preset()
        assert result["rvc_model"] == ""

    def test_save_invalid_pitch(self):
        widgets = {"spin_rvc_pitch": MockWidget("invalid")}
        ctrl = PresetWindowUIController(widgets)
        result = ctrl.save_widgets_to_preset()
        assert result["rvc_pitch_shift"] == 0

    def test_toggle_state(self):
        widgets = {
            "combo_rvc_model": MockWidget(),
            "slider_rvc_index": MockWidget(),
            "lbl_rvc_model_title": MockWidget(),
        }
        ctrl = PresetWindowUIController(widgets)

        ctrl.toggle_rvc_widgets_state(True)
        assert widgets["combo_rvc_model"].configured.get("state") == "normal"
        assert widgets["lbl_rvc_model_title"].configured.get("text_color") == "#ffffff"

        ctrl.toggle_rvc_widgets_state(False)
        assert widgets["combo_rvc_model"].configured.get("state") == "disabled"
        assert widgets["lbl_rvc_model_title"].configured.get("text_color") == "#777777"
