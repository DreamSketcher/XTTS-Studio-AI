# -*- coding: utf-8 -*-
"""engine/gui/dialogs.py — диалоги «Язык озвучки» и «Справка» в стиле Аудио/История"""
import tkinter as tk
import os

import customtkinter as ctk

from i18n import t
from engine.paths import BASE_DIR

try:
    from engine.paths import ICON_PATH
except ImportError:
    ICON_PATH = os.path.join(str(BASE_DIR), "icon.ico")

from engine.gui.colors import Colors, scaled_font_size, scaled_size
from engine.gui.tooltip import ToolTip
from engine.gui.widgets import CompatCTkFrame, CompatCTkButton, CompatCTkLabel
import customtkinter as ctk

root = None
lang_var = None
lang_split_enabled = None
save_settings = None


def init(**deps):
    globals().update(deps)


def _apply_window_icon(win):
    try:
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XTTSStudio.App")
        except Exception:
            pass
    except Exception:
        pass
    ico = ICON_PATH if os.path.isfile(ICON_PATH) else os.path.join(str(BASE_DIR), "icon.ico")
    if os.path.isfile(ico):
        try:
            win.iconbitmap(default=ico)
            win.after(200, lambda: win.iconbitmap(default=ico))
        except Exception:
            pass
    try:
        png = os.path.join(str(BASE_DIR), "icon.png")
        if os.path.isfile(png):
            photo = tk.PhotoImage(file=png)
            win.iconphoto(True, photo)
            win._icon_photo_ref = photo
    except Exception:
        pass


def _round_btn(parent, text, cmd, diameter=36, primary=False, width=None):
    bg = Colors.BG_ACTIVE if primary else Colors.BG_INPUT
    hover = "#2ea043" if primary else Colors.BG_HOVER
    sd = scaled_size(diameter, min_size=diameter)
    btn = CompatCTkButton(
        parent,
        text=text,
        command=cmd,
        width=width if width else sd,
        height=sd,
        corner_radius=sd // 2,
        fg_color=bg,
        text_color=Colors.TEXT_MAIN,
        hover_color=hover,
        border_width=0,
        font=("Segoe UI", scaled_font_size(13)),
    )
    return btn


def pick_language():
    win = tk.Toplevel(root)
    win.title(t("lang_picker_title"))
    win.geometry("620x460")
    win.minsize(540, 400)
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    _apply_window_icon(win)
    win.grab_set()

    langs = [
        ("Авто", "auto"),
        ("RU", "ru"),
        ("EN", "en"),
        ("ES", "es"),
        ("FR", "fr"),
        ("DE", "de"),
        ("IT", "it"),
        ("PT", "pt"),
        ("PL", "pl"),
        ("TR", "tr"),
        ("NL", "nl"),
        ("CS", "cs"),
        ("AR", "ar"),
        ("ZH", "zh-cn"),
        ("HU", "hu"),
        ("KO", "ko"),
        ("JA", "ja"),
        ("HI", "hi"),
    ]

    # Header card
    header_card = CompatCTkFrame(
        win, fg_color=Colors.BG_CARD, corner_radius=20, border_width=1, border_color=Colors.BORDER
    )
    header_card.pack(fill="x", padx=14, pady=14)

    inner = tk.Frame(header_card, bg=Colors.BG_CARD)
    inner.pack(fill="x", padx=18, pady=16)

    CompatCTkLabel(
        inner,
        text=t("lang_picker_header"),
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(16), "bold"),
        anchor="w",
    ).pack(fill="x")

    # Languages grid inside scrollable? Use card pill
    grid_card = CompatCTkFrame(
        win, fg_color=Colors.BG_CARD, corner_radius=20, border_width=1, border_color=Colors.BORDER
    )
    grid_card.pack(fill="both", expand=True, padx=14, pady=(0, 10))

    grid_inner = tk.Frame(grid_card, bg=Colors.BG_CARD)
    grid_inner.pack(fill="both", expand=True, padx=12, pady=12)

    # Use CTkScrollableFrame for languages
    scroll = ctk.CTkScrollableFrame(grid_inner, fg_color=Colors.BG_DARK, corner_radius=12)
    scroll.pack(fill="both", expand=True)

    lang_frame = tk.Frame(scroll, bg=Colors.BG_DARK)
    lang_frame.pack(fill="both", expand=True, padx=6, pady=6)

    for i, (label, value) in enumerate(langs):
        is_active = lang_var.get() == value
        btn = CompatCTkButton(
            lang_frame,
            text=label,
            command=lambda v=value: lang_var.set(v),
            fg_color=Colors.ACCENT if is_active else Colors.BG_INPUT,
            text_color="#ffffff" if is_active else Colors.TEXT_MAIN,
            hover_color=Colors.ACCENT if is_active else Colors.BG_HOVER,
            corner_radius=18,
            height=scaled_size(38, min_size=36),
            width=scaled_size(84, min_size=80),
            font=("Segoe UI", scaled_font_size(13), "bold"),
        )
        btn.grid(row=i // 4, column=i % 4, padx=6, pady=6, sticky="nsew")

        # update visual when lang_var changes
        def make_updater(b=btn, v=value):
            def updater(*_):
                try:
                    active = lang_var.get() == v
                    b.configure(
                        fg_color=Colors.ACCENT if active else Colors.BG_INPUT,
                        text_color="#ffffff" if active else Colors.TEXT_MAIN,
                    )
                except Exception:
                    pass

            return updater

        try:
            lang_var.trace_add("write", lambda *_args, u=make_updater(): u())
        except Exception:
            pass

    for c in range(4):
        lang_frame.grid_columnconfigure(c, weight=1)

    # Bottom options card
    bottom_card = CompatCTkFrame(
        win, fg_color=Colors.BG_CARD, corner_radius=20, border_width=1, border_color=Colors.BORDER
    )
    bottom_card.pack(fill="x", padx=14, pady=(0, 14))

    bottom_inner = tk.Frame(bottom_card, bg=Colors.BG_CARD)
    bottom_inner.pack(fill="x", padx=18, pady=14)

    split_row = tk.Frame(bottom_inner, bg=Colors.BG_CARD)
    split_row.pack(fill="x", pady=(0, 10))

    cb = ctk.CTkCheckBox(
        split_row,
        text=t("lang_auto_switch"),
        variable=lang_split_enabled,
        fg_color=Colors.BG_ACTIVE,
        hover_color=Colors.BG_HOVER,
        border_color=Colors.BORDER,
        text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(13)),
    )
    cb.pack(side="left")
    ToolTip(cb, t("lang_auto_switch_tip"))

    btn_close = _round_btn(
        bottom_inner,
        t("btn_close"),
        lambda: [win.destroy(), save_settings()],
        diameter=44,
        primary=True,
        width=scaled_size(160, min_size=140),
    )
    btn_close.pack(pady=(6, 0))


def show_help():
    win = tk.Toplevel(root)
    win.title(t("win_help_title"))
    win.geometry("720x620")
    win.minsize(600, 480)
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    _apply_window_icon(win)
    win.grab_set()

    header_card = CompatCTkFrame(
        win, fg_color=Colors.BG_CARD, corner_radius=20, border_width=1, border_color=Colors.BORDER
    )
    header_card.pack(fill="x", padx=14, pady=14)

    inner = tk.Frame(header_card, bg=Colors.BG_CARD)
    inner.pack(fill="x", padx=18, pady=14)

    CompatCTkLabel(
        inner,
        text="📖 " + t("win_help_title"),
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(16), "bold"),
        anchor="w",
    ).pack(fill="x")

    frame_card = CompatCTkFrame(
        win, fg_color=Colors.BG_CARD, corner_radius=20, border_width=1, border_color=Colors.BORDER
    )
    frame_card.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    frame = tk.Frame(frame_card, bg=Colors.BG_CARD)
    frame.pack(fill="both", expand=True, padx=8, pady=8)

    scrollbar = tk.Scrollbar(frame, bg=Colors.BG_INPUT, troughcolor=Colors.BG_DARK)
    scrollbar.pack(side="right", fill="y")
    text = tk.Text(
        frame,
        wrap="word",
        yscrollcommand=scrollbar.set,
        font=("Consolas", scaled_font_size(12)),
        bg=Colors.BG_DARK,
        fg=Colors.TEXT_MAIN,
        padx=14,
        pady=14,
        relief="flat",
        highlightthickness=0,
    )
    text.pack(fill="both", expand=True)
    scrollbar.config(command=text.yview)

    text.tag_configure(
        "header", foreground=Colors.ACCENT, font=("Consolas", scaled_font_size(13), "bold")
    )
    text.tag_configure("symbol", foreground="#ffd600", font=("Consolas", scaled_font_size(11)))
    text.tag_configure(
        "good", foreground=Colors.TEXT_SUCCESS, font=("Consolas", scaled_font_size(12))
    )
    text.tag_configure("bad", foreground=Colors.TEXT_ERROR)
    text.tag_configure(
        "normal", foreground=Colors.TEXT_MAIN, font=("Consolas", scaled_font_size(12))
    )
    text.tag_configure(
        "comment", foreground=Colors.TEXT_DIM, font=("Consolas", scaled_font_size(11))
    )

    content = [
        ("header", "\n🤖 AI ФУНКЦИИ\n"),
        ("good", "Флажок ✨ AI — улучшение текста перед генерацией\n"),
        ("comment", "Технический редактор: раскрывает сокращения, убирает спецсимволы.\n\n"),
        ("good", "Кнопка 🤖 AI — AI Conductor\n"),
        ("comment", "Анализирует весь текст и назначает параметры XTTS для каждого чанка.\n\n"),
        ("header", "🎯 АВТОМАТИЧЕСКАЯ ОБРАБОТКА\n"),
        ("good", "Числа → слова, аббревиатуры → словарь, паузы → авто\n"),
        ("comment", "Нормализация текста, контроль качества чанков → авто-перегенерация\n\n"),
        ("header", "\n⏸ ПАУЗЫ\n"),
        ("symbol", ".  "),
        ("normal", "стандартная пауза\n"),
        ("symbol", ",  "),
        ("normal", "короткая пауза\n"),
        ("symbol", "?  "),
        ("normal", "вопросительная интонация\n"),
        ("symbol", "!  "),
        ("normal", "восклицательная интонация\n\n"),
        ("header", "📋 СПИСКИ\n"),
        ("good", "1. Первый пункт → читается как «первый»\n"),
        ("comment", "Пункты 1–20 читаются порядковыми числительными.\n\n"),
        ("header", "🎨 ПРЕСЕТЫ\n"),
        ("normal", "⭐ Высокое качество — стабильный нейтральный голос\n"),
        ("normal", "📖 Нарратив — для книг и лекций\n"),
        ("normal", "⚡ Динамика — для рекламы\n"),
        ("normal", "🎭 Экспрессия — для драматичных сцен\n\n"),
        ("header", "🎤 РЕФЕРЕНС\n"),
        ("good", "Оптимальная длина: 10–20 секунд, тихая комната\n"),
    ]
    for tag, txt in content:
        text.insert("end", txt, tag)
    text.config(state="disabled")

    def close_window():
        win.destroy()
        try:
            save_settings()
        except Exception:
            pass

    win.protocol("WM_DELETE_WINDOW", close_window)
    win.after(150, lambda: _apply_window_icon(win))
