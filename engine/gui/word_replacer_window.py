# -*- coding: utf-8 -*-
"""
engine/gui/word_replacer_window.py — окно «Словарь произношений» в стиле Аудио/История

Редизайн 2026-07-09 единый стиль.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
import os

try:
    import customtkinter as ctk

    CTK_AVAILABLE = True
except Exception:
    CTK_AVAILABLE = False
    ctk = None

from engine.paths import BASE_DIR

try:
    from engine.paths import ICON_PATH
except ImportError:
    ICON_PATH = os.path.join(str(BASE_DIR), "icon.ico")

from engine.gui.colors import Colors, scaled_font_size, scaled_size
from engine.gui.widgets import CompatCTkFrame, CompatCTkButton, CompatCTkLabel
from engine.gui.tooltip import ToolTip

_root = None
_colors = None
_create_button = None
_word_replacer_enabled_var = None
_save_settings = None


def init(root, colors, create_button_fn, word_replacer_enabled_var, save_settings_fn):
    global _root, _colors, _create_button, _word_replacer_enabled_var, _save_settings
    _root = root
    _colors = colors
    _create_button = create_button_fn
    _word_replacer_enabled_var = word_replacer_enabled_var
    _save_settings = save_settings_fn


class _ToolTip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def show(self, event=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 15
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip,
            text=self.text() if callable(self.text) else self.text,
            bg=_colors.TOOLTIP_BG,
            fg=_colors.TEXT_MAIN,
            justify="left",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=7,
            font=("Segoe UI", scaled_font_size(11)),
            wraplength=320,
        ).pack()

    def hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


def _apply_window_icon(win: tk.Toplevel):
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
        photo = None
        png = os.path.join(str(BASE_DIR), "icon.png")
        if os.path.isfile(png):
            photo = tk.PhotoImage(file=png)
        if photo:
            win.iconphoto(True, photo)
            win._icon_photo_ref = photo
    except Exception:
        pass


def open_word_replacer():
    from engine.tts_runner import word_replacer

    colors = _colors

    win = tk.Toplevel(_root)
    win.title("📖 Словарь произношений")
    win.geometry("720x640")
    win.minsize(640, 540)
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    _apply_window_icon(win)
    win.grab_set()

    def _round_btn(parent, text, cmd, diameter=36, primary=False, danger=False):
        bg = Colors.BG_ACTIVE if primary else Colors.BG_INPUT
        hover = "#2ea043" if primary else (Colors.BG_DANGER if danger else Colors.BG_HOVER)
        sd = scaled_size(diameter, min_size=diameter)
        return CompatCTkButton(
            parent,
            text=text,
            command=cmd,
            width=sd,
            height=sd,
            corner_radius=sd // 2,
            fg_color=bg,
            text_color=Colors.TEXT_MAIN,
            hover_color=hover,
            border_width=0,
            font=("Segoe UI", scaled_font_size(15)),
        )

    # HEADER pill
    header = tk.Frame(win, bg=Colors.BG_DARK, pady=12)
    header.pack(fill="x", padx=16)

    pill = CompatCTkFrame(
        header,
        fg_color=Colors.BG_CARD,
        corner_radius=18,
        border_width=1,
        border_color=Colors.BORDER,
    )
    pill.pack(side="left")
    row = tk.Frame(pill, bg=Colors.BG_CARD)
    row.pack(padx=6, pady=6)

    count_var = tk.StringVar(value="0 правил")
    # будет обновляться в refresh

    # LIST - scrollable frame как в history
    list_frame = ctk.CTkScrollableFrame(win, fg_color=Colors.BG_DARK, corner_radius=12)
    list_frame.pack(fill="both", expand=True, padx=12, pady=(4, 6))

    _selected_word = {"word": None, "category": None}
    meta_var = tk.StringVar(value="")

    def _category_tag(cat: str) -> str:
        return {
            "builtin": "[встроено]",
            "auto": "[авто]",
            "ai_corrected": "[ai]",
            "custom": "[ручное]",
        }.get(cat, f"[{cat}]")

    # Для поиска/хранения маппинга карточек -> слово
    card_map = {}

    def _make_card(parent, word, text, category, entry_obj):
        tag = _category_tag(category)
        card = CompatCTkFrame(
            parent,
            fg_color=Colors.BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=Colors.BORDER,
        )
        card.pack(fill="x", padx=4, pady=5)

        badge = CompatCTkFrame(
            card, fg_color=Colors.BG_INPUT, corner_radius=20, width=44, height=44
        )
        badge.pack(side="left", padx=(14, 10), pady=12)
        badge.pack_propagate(False)
        CompatCTkLabel(
            badge,
            text=tag[:2],
            fg_color=Colors.BG_INPUT,
            text_color=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(11), "bold"),
        ).pack(expand=True)

        info = tk.Frame(card, bg=Colors.BG_CARD)
        info.pack(side="left", fill="both", expand=True, pady=10)
        CompatCTkLabel(
            info,
            text=f"{word}  →  {text}",
            fg_color=Colors.BG_CARD,
            text_color=Colors.TEXT_MAIN,
            font=("Consolas", scaled_font_size(13), "bold"),
            anchor="w",
        ).pack(fill="x")
        # мета
        if isinstance(entry_obj, dict) and entry_obj.get("added_at"):
            meta = f"Добавлено: {entry_obj.get('added_at','')} • встреч: {entry_obj.get('occurrences','')}"
            CompatCTkLabel(
                info,
                text=meta,
                fg_color=Colors.BG_CARD,
                text_color=Colors.TEXT_DIM,
                font=("Segoe UI", scaled_font_size(10)),
                anchor="w",
            ).pack(fill="x", pady=(2, 0))

        def on_card_click(e=None, w=word, cat=category):
            _selected_word["word"] = w
            _selected_word["category"] = cat
            entry_word.delete(0, tk.END)
            entry_word.insert(0, w)
            entry_replacement.delete(0, tk.END)
            entry_replacement.insert(0, text)
            if isinstance(entry_obj, dict):
                parts = []
                if entry_obj.get("added_at"):
                    parts.append(f"Добавлено: {entry_obj['added_at']}")
                if entry_obj.get("context"):
                    parts.append(f"«{entry_obj['context']}»")
                meta_var.set("  •  ".join(parts))
            else:
                meta_var.set("")

            # подсветка
            for c, _ in card_map.values():
                try:
                    c.configure(border_color=Colors.BORDER, border_width=1)
                except Exception:
                    pass
            try:
                card.configure(border_color=Colors.ACCENT, border_width=2)
            except Exception:
                pass

        card.bind("<Button-1>", on_card_click)
        info.bind("<Button-1>", on_card_click)
        for child in info.winfo_children():
            try:
                child.bind("<Button-1>", on_card_click)
            except Exception:
                pass
        card_map[word] = (card, entry_obj)

    def refresh():
        for w in list_frame.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        card_map.clear()
        total = 0
        for category, data in word_replacer.data.items():
            if category == "meta":
                continue
            for word, value in data.items():
                txt = value["text"] if isinstance(value, dict) else value
                _make_card(list_frame, word, txt, category, value)
                total += 1
        count_var.set(f"{total} правил")
        count_lbl.configure(text=count_var.get())
        meta_var.set("")

    # INPUT area - карточка снизу
    outer_wrap = tk.Frame(win, bg=Colors.BG_DARK)
    outer_wrap.pack(fill="x", side="bottom")
    input_card = CompatCTkFrame(
        outer_wrap,
        fg_color=Colors.BG_CARD,
        corner_radius=20,
        border_width=1,
        border_color=Colors.BORDER,
    )
    input_card.pack(fill="x", padx=14, pady=(6, 14))

    input_row = tk.Frame(input_card, bg=Colors.BG_CARD)
    input_row.pack(fill="x", padx=18, pady=(16, 6))

    tk.Label(
        input_row,
        text="Слово:",
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(11)),
    ).pack(side="left")
    entry_word = tk.Entry(
        input_row,
        width=18,
        font=("Segoe UI", scaled_font_size(12)),
        bg=Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        insertbackground=Colors.TEXT_MAIN,
        relief="flat",
        highlightthickness=1,
        highlightbackground=Colors.BORDER,
    )
    entry_word.pack(side="left", padx=8)

    tk.Label(
        input_row,
        text="Замена:",
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(11)),
    ).pack(side="left", padx=(8, 0))
    entry_replacement = tk.Entry(
        input_row,
        width=18,
        font=("Segoe UI", scaled_font_size(12)),
        bg=Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        insertbackground=Colors.TEXT_MAIN,
        relief="flat",
        highlightthickness=1,
        highlightbackground=Colors.BORDER,
    )
    entry_replacement.pack(side="left", padx=8, fill="x", expand=True)

    meta_lbl = CompatCTkLabel(
        input_card,
        textvariable=meta_var,
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(10)),
        anchor="w",
    )
    meta_lbl.pack(fill="x", padx=18, pady=(0, 10))

    ctrl_pill = CompatCTkFrame(input_card, fg_color=Colors.BG_INPUT, corner_radius=26)
    ctrl_pill.pack(pady=(2, 18))
    ctrl_row = tk.Frame(ctrl_pill, bg=Colors.BG_INPUT)
    ctrl_row.pack(padx=12, pady=8)

    def add_rule():
        word = entry_word.get().strip()
        replacement = entry_replacement.get().strip()
        if not word or not replacement:
            messagebox.showwarning("⚠ Поля пусты", "Заполните слово и замену", parent=win)
            return
        if word_replacer.get_category(word) is not None:
            messagebox.showwarning("⚠ Слово уже есть", f"«{word}» уже есть.", parent=win)
            return
        word_replacer.add_rule(word, replacement, category="custom")
        entry_word.delete(0, tk.END)
        entry_replacement.delete(0, tk.END)
        _selected_word["word"] = None
        refresh()

    def save_changes():
        original = _selected_word["word"]
        if not original:
            messagebox.showwarning("⚠ Ничего не выбрано", "Выберите слово в списке", parent=win)
            return
        new_word = entry_word.get().strip()
        new_text = entry_replacement.get().strip()
        if not new_word or not new_text:
            messagebox.showwarning("⚠ Поля пусты", "Заполните слово и замену", parent=win)
            return
        if new_word != original:
            word_replacer.remove_rule(original)
        word_replacer.add_rule(new_word, new_text, category="custom")
        entry_word.delete(0, tk.END)
        entry_replacement.delete(0, tk.END)
        _selected_word["word"] = None
        refresh()

    def remove_rule():
        word = _selected_word["word"] or entry_word.get().strip()
        if not word:
            return
        word_replacer.remove_rule(word)
        entry_word.delete(0, tk.END)
        entry_replacement.delete(0, tk.END)
        _selected_word["word"] = None
        refresh()

    def reset_pronunciation():
        word = _selected_word["word"]
        if not word:
            messagebox.showwarning("⚠ Ничего не выбрано", "Выберите слово", parent=win)
            return
        if not messagebox.askyesno("↺ Сбросить", f"Сбросить «{word}»?", parent=win):
            return
        word_replacer.remove_rule(word)
        entry_word.delete(0, tk.END)
        entry_replacement.delete(0, tk.END)
        _selected_word["word"] = None
        refresh()

    b_add = _round_btn(ctrl_row, "➕", add_rule, diameter=38)
    b_add.pack(side="left", padx=4)
    ToolTip(b_add, "Добавить новое правило")

    b_save = _round_btn(ctrl_row, "✏", save_changes, diameter=38)
    b_save.pack(side="left", padx=4)
    ToolTip(b_save, "Сохранить изменения")

    b_reset = _round_btn(ctrl_row, "↺", reset_pronunciation, diameter=38)
    b_reset.pack(side="left", padx=4)
    ToolTip(b_reset, "Сбросить произношение — читается как есть")

    b_del = _round_btn(ctrl_row, "🗑", remove_rule, diameter=38, danger=True)
    b_del.pack(side="left", padx=(16, 4))
    ToolTip(b_del, "Удалить правило")

    # bottom toggle
    toggle_row = tk.Frame(win, bg=Colors.BG_DARK, pady=6)
    toggle_row.pack(fill="x", side="bottom", padx=12, pady=6)
    count_lbl = CompatCTkLabel(
        toggle_row,
        textvariable=count_var,
        fg_color=Colors.BG_DARK,
        text_color=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(11)),
    )
    count_lbl.pack(side="left")

    wr_cb = ctk.CTkCheckBox(
        toggle_row,
        text="Словарь активен",
        variable=_word_replacer_enabled_var,
        fg_color=Colors.BG_ACTIVE,
        hover_color=Colors.BG_HOVER,
        border_color=Colors.BORDER,
        text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(12)),
    )
    wr_cb.pack(side="right")
    _ToolTip(wr_cb, "Включает замену слов перед синтезом")

    def close_window():
        _save_settings()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", close_window)
    refresh()
    try:
        win.after(150, lambda: _apply_window_icon(win))
    except Exception:
        pass
