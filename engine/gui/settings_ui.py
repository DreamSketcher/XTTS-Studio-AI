# -*- coding: utf-8 -*-
"""engine/gui/settings_ui.py — сохранение и применение настроек GUI
(перенесено из gui.py: save_settings, apply_settings)."""
import json
import os
import tkinter as tk

from i18n import LANGUAGES, set_language

from engine.settings_store import SETTINGS_PATH
from engine.gui.colors import Colors

# Внедряются из main_window: lang_var, quality_var, ref_var, use_gpt,
# word_replacer_enabled, lang_split_enabled, ui_lang_var, quality_params, ai_btn
lang_var = None
quality_var = None
ref_var = None
use_gpt = None
word_replacer_enabled = None
lang_split_enabled = None
ui_lang_var = None
quality_params = {}


def init(**deps):
    """Внедрение зависимостей из engine.gui.main_window (имена совпадают с
    именами глобальных переменных исходного gui.py)."""
    globals().update(deps)


def save_settings(extra=None):
    from engine.gui import textbox as _textbox

    data = {
        "language": lang_var.get(),
        "quality": quality_var.get(),
        "ref_path": ref_var.get(),
        "use_gpt": use_gpt.get(),
        "word_replacer_enabled": word_replacer_enabled.get(),
        "lang_split_enabled": lang_split_enabled.get(),
        "ui_language": ui_lang_var.get(),
        "text_font_size": _textbox.text_font_size["v"],
        "ai_conductor_enabled": any(
            params.get("ai_conductor_enabled", tk.BooleanVar()).get()
            for params in quality_params.values()
        ),
        "ai_conductor_context": next(
            (
                params["ai_conductor_context"].get()
                for params in quality_params.values()
                if "ai_conductor_context" in params
            ),
            "",
        ),
        "quality_params": {
            preset: {k: (v.get() if hasattr(v, "get") else v) for k, v in params.items()}
            for preset, params in quality_params.items()
        },
    }
    if extra:
        data.update(extra)
    # ИСПРАВЛЕНО (БАГ №8, КРИТИЧНЫЙ — "смена языка/др. настроек сбрасывает
    # тему после перезапуска"): раньше эта функция строила словарь `data`
    # С НУЛЯ и полностью ПЕРЕЗАПИСЫВАЛА settings.json, стирая любые ключи,
    # которые сама не знает — в частности "ui_theme", который пишет ТОЛЬКО
    # engine/gui/theme.py: save_theme() (в отдельном месте, с собственным
    # read-modify-write). save_settings() вызывается очень часто — явно из
    # switch_ui_lang() и через tk.Variable.trace_add("write", ...) на
    # lang_var/quality_var/use_gpt/... в main_window.py — то есть почти
    # любое действие пользователя (включая переключение языка) тихо
    # стирало "ui_theme" из файла. Эффект был НЕ мгновенным (в памяти
    # тема оставалась верной, ctk.set_appearance_mode() не трогался),
    # поэтому проявлялся только на СЛЕДУЮЩЕМ запуске приложения — theme.py:
    # load_saved_theme() не находил "ui_theme" в файле и откатывался на
    # дефолт "dark". Раньше выглядело так, будто "смена языка меняет
    # тему" — на самом деле она портила файл настроек, а эффект был виден
    # только после перезапуска.
    # Решение — read-modify-write вместо overwrite: сначала читаем то, что
    # уже лежит в settings.json (если файл валиден), сливаем поверх новые
    # значения из `data`, и только затем сохраняем объединённый словарь.
    # Так любые ключи, которыми управляют другие модули (ui_theme из
    # theme.py, возможные будущие ключи других панелей), не теряются.
    try:
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}
        existing.update(data)
        atomic_write_json(SETTINGS_PATH, existing, ensure_ascii=False, indent=2)
    except Exception:
        pass


def apply_settings(data):
    import traceback

    if not isinstance(data, dict):
        return
    if "text_font_size" in data:
        try:
            from engine.gui import textbox as _textbox

            _textbox.restore_text_font_size(data["text_font_size"])
        except Exception:
            pass
    if "language" in data:
        lang_var.set(data["language"])
    if "use_gpt" in data:
        use_gpt.set(data["use_gpt"])
    if "quality" in data:
        q = data["quality"]
        quality_var.set(q if q in quality_params else "Высокое качество")
    if "ref_path" in data:
        path = data["ref_path"]
        if path and os.path.isfile(path):
            ref_var.set(path)
    if "word_replacer_enabled" in data:
        word_replacer_enabled.set(data["word_replacer_enabled"])
    if "lang_split_enabled" in data:
        lang_split_enabled.set(data["lang_split_enabled"])
    if "ui_language" in data:
        lang_code = data["ui_language"]
        if lang_code in LANGUAGES:
            ui_lang_var.set(lang_code)
            set_language(lang_code)
    if "ai_conductor_enabled" in data:
        for preset_name, params in quality_params.items():
            params["ai_conductor_enabled"].set(data["ai_conductor_enabled"])
        try:
            ai_btn.config(
                bg=Colors.BG_INPUT,
                fg=Colors.AI_ACCENT if data["ai_conductor_enabled"] else Colors.TEXT_DIM,
            )
        except NameError:
            pass
    if "ai_rewrite_enabled" in data:
        for preset_name, params in quality_params.items():
            if "ai_rewrite_enabled" in params:
                params["ai_rewrite_enabled"].set(data["ai_rewrite_enabled"])
    if "ai_rewrite_context" in data:
        for preset_name, params in quality_params.items():
            if "ai_rewrite_context" in params:
                params["ai_rewrite_context"].set(data["ai_rewrite_context"])
    if "ai_rewrite_negative" in data:
        for preset_name, params in quality_params.items():
            if "ai_rewrite_negative" in params:
                params["ai_rewrite_negative"].set(data["ai_rewrite_negative"])
    if "quality_params" in data:
        for preset, params in data["quality_params"].items():
            if preset in quality_params:
                for key, value in params.items():
                    if key in quality_params[preset]:
                        try:
                            quality_params[preset][key].set(value)
                        except Exception:
                            traceback.print_exc()
                            pass
