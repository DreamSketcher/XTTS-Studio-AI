# -*- coding: utf-8 -*-
"""engine/gui/theme.py — тема customtkinter и заголовок окна
(перенесено из gui.py: ctk.set_appearance_mode / set_dark_titlebar).

Дополнено поддержкой светлой темы: get_theme()/set_theme() читают и
сохраняют выбор в settings.json, apply_theme() настраивает customtkinter
и палитру Colors под текущую тему.
"""
import ctypes
import json
from engine.atomic_write import atomic_write_json
import os
import sys

import customtkinter as ctk

from engine.gui.colors import apply_palette, load_font_scale_from_settings

_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "settings.json",
)

_current_theme = "dark"


def get_theme() -> str:
    return _current_theme


def load_saved_theme() -> str:
    """Читает сохранённую тему из settings.json (до построения окон)."""
    global _current_theme
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        theme = data.get("ui_theme")
        if theme in ("dark", "light"):
            _current_theme = theme
    except Exception:
        pass
    return _current_theme


def save_theme(theme: str) -> None:
    """Сохраняет тему в settings.json (не трогая остальные ключи)."""
    try:
        try:
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data["ui_theme"] = theme
        atomic_write_json(_SETTINGS_PATH, data, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_theme(theme: str) -> None:
    """Устанавливает тему ('dark' | 'light'): палитра + ctk + сохранение."""
    global _current_theme
    if theme not in ("dark", "light"):
        return
    _current_theme = theme
    apply_palette(theme)
    try:
        ctk.set_appearance_mode("dark" if theme == "dark" else "light")
    except Exception:
        pass
    save_theme(theme)


def apply_theme():
    """Начальная настройка темы (вызывается до создания root)."""
    theme = load_saved_theme()
    apply_palette(theme)
    # Загружаем сохранённый базовый размер шрифта интерфейса (не относится
    # к textbox-редактору — у него свой отдельный механизм). Делается здесь,
    # рядом с apply_palette(), т.к. оба должны быть готовы ДО построения
    # первого окна — иначе первая партия виджетов отрисуется с дефолтным
    # размером шрифта, а не с пользовательским.
    load_font_scale_from_settings()
    ctk.set_appearance_mode("dark" if theme == "dark" else "light")
    ctk.set_default_color_theme("blue")


def set_dark_titlebar(root):
    """Тёмный/светлый заголовок окна (Windows) в зависимости от темы."""
    if sys.platform != "win32":
        return

    # Flush geometry only; update() would run a nested event loop and may
    # re-enter unrelated callbacks while the theme is half-applied.
    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(ctypes.c_int(1 if _current_theme == "dark" else 0)),
        ctypes.sizeof(ctypes.c_int),
    )
