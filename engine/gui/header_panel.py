# -*- coding: utf-8 -*-
"""engine/gui/header_panel.py — шапка левой панели (заголовок, кнопки
Обновить / AI статус / RU-EN) (перенесено из gui.py: секция LEFT PANEL header,
_switch_ui_lang)."""
import tkinter as tk
from tkinter import messagebox

from i18n import t, set_language

from engine.gui.colors import Colors
from engine.gui.tooltip import ToolTip
from engine.gui.widgets import CompatCTkFrame, create_button
from engine.gui.updates import check_and_update
from engine.gui.ai_status_window import open_ai_status_window

# Внедряются из main_window: root, ui_lang_var, save_settings
root = None
ui_lang_var = None
save_settings = None

# Виджеты (создаются в build_header)
header_frame = None
title_row = None
header_btn_row = None
upd_btn = None
ai_status_btn = None
ui_lang_btn = None


def init(**deps):
    """Внедрение зависимостей из engine.gui.main_window (имена совпадают с
    именами глобальных переменных исходного gui.py)."""
    globals().update(deps)


# ── UI Language Switcher ──
# Вынесено на уровень модуля, чтобы кнопку переключения языка можно было
# использовать и в шапке, и рядом с кнопкой «Справка» (engine/gui/textbox.py).
def switch_ui_lang():
    current = ui_lang_var.get()
    new_lang = "en" if current == "ru" else "ru"
    ui_lang_var.set(new_lang)
    set_language(new_lang)
    save_settings()
    # Подписи AI-провайдеров вычисляются при импорте gpt_client —
    # обновляем их под новый язык сразу
    try:
        from engine import gpt_client as _gpt
        _gpt.refresh_i18n_labels()
    except Exception:
        pass
    # Окно AI-чата строится динамически — применяем новый язык сразу,
    # без перезапуска (если окно открыто, оно пересоздаётся на новом языке).
    try:
        from engine.gui import chat_window as _chat_window
        _chat_window.reapply_language()
    except Exception:
        pass
    messagebox.showinfo(t("lang_ui_label"),
                        "Language changed. Restart the app to apply.\n"
                        "Язык изменён. Перезапустите приложение для применения.")


# Обратная совместимость со старым именем
_switch_ui_lang = switch_ui_lang


def build_header(left_panel):
    global header_frame, title_row, header_btn_row, upd_btn, ai_status_btn, ui_lang_btn
    header_frame = CompatCTkFrame(left_panel, fg_color="transparent", bg="transparent")
    header_frame.pack(fill="x", pady=(0, 8))
    title_row = tk.Frame(header_frame, bg=Colors.BG_DARK)
    title_row.pack(anchor="w")
    tk.Label(
        title_row,
        text=t("app_title"),
        bg=Colors.BG_DARK,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", 16, "bold")
    ).pack(side="left", padx=(4, 0))
    tk.Label(
        header_frame,
        text=t("app_author"),
        bg=Colors.BG_DARK,
        fg=Colors.TEXT_DIM,
        font=("Segoe UI", 9)
    ).pack(anchor="w")
    header_btn_row = tk.Frame(header_frame, bg=Colors.BG_DARK)
    header_btn_row.pack(anchor="w", pady=(4, 0))
    upd_btn = create_button(header_btn_row, t("btn_update"), check_and_update,
                            bg=Colors.BG_INPUT, font_size=10)
    upd_btn.pack(side="left")
    ai_status_btn = create_button(header_btn_row, t("btn_ai_status"), open_ai_status_window,
                                  bg=Colors.BG_INPUT, font_size=10)
    ai_status_btn.pack(side="left", padx=(6, 0))
    # ── UI Language Switcher (функция switch_ui_lang — на уровне модуля) ──
    ui_lang_btn = create_button(header_btn_row, "RU/EN", switch_ui_lang,
                                bg=Colors.BG_INPUT, font_size=10, width=50)
    ui_lang_btn.pack(side="left", padx=(6, 0))
    ToolTip(ui_lang_btn, "Switch UI language / Переключить язык интерфейса")
    left_panel.update_idletasks()
