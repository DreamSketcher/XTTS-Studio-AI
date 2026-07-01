"""
engine/word_replacer_window.py — окно "Словарь произношений" для XTTS Studio

Управляет фонетическими заменами (engine.word_replacer.WordReplacer):
просмотр, добавление, редактирование и удаление правил, а также
переключатель "Словарь активен".

Архитектура:
    init(root, colors, create_button_fn, word_replacer_enabled_var, save_settings_fn)

Окно не импортирует ничего из gui.py напрямую — все зависимости
приходят через init().
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except Exception:
    CTK_AVAILABLE = False
    ctk = None


# ─────────────────────────────────────────────────────────────────────────────
# Dependency injection
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# ToolTip (лёгкая копия из gui.py — своя, чтобы не тянуть прямой импорт)
# ─────────────────────────────────────────────────────────────────────────────

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
            font=("Segoe UI", 9),
            wraplength=280
        ).pack()

    def hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


# ─────────────────────────────────────────────────────────────────────────────
# Window
# ─────────────────────────────────────────────────────────────────────────────

def open_word_replacer():
    """Открывает окно словаря произношений (фонетических замен)."""
    from engine.tts_runner import word_replacer

    colors = _colors
    win = tk.Toplevel(_root)
    win.title("📖 Словарь произношений")
    win.geometry("550x450")
    win.resizable(False, False)
    win.configure(bg=colors.BG_CARD)
    win.grab_set()

    list_frame = tk.Frame(win, bg=colors.BG_CARD)
    list_frame.pack(fill="both", expand=True, padx=15, pady=(15, 5))

    scrollbar = tk.Scrollbar(list_frame, bg=colors.BG_INPUT, troughcolor=colors.BG_DARK)
    scrollbar.pack(side="right", fill="y")

    listbox = tk.Listbox(
        list_frame, yscrollcommand=scrollbar.set,
        font=("Consolas", 10), selectmode="single",
        bg=colors.BG_INPUT, fg=colors.TEXT_MAIN,
        selectbackground=colors.ACCENT, selectforeground=colors.TEXT_MAIN,
        relief="flat", highlightthickness=0
    )
    listbox.pack(fill="both", expand=True)
    scrollbar.config(command=listbox.yview)

    _selected_word = {"word": None}

    def refresh():
        listbox.delete(0, tk.END)
        for category, data in word_replacer.data.items():
            if category == "meta":
                continue
            for word, value in data.items():
                text = value["text"] if isinstance(value, dict) else value
                listbox.insert(tk.END, f"{word}  →  {text}")

    def on_select(event=None):
        sel = listbox.curselection()
        if not sel:
            return
        item = listbox.get(sel[0])
        word, text = item.split("  →  ")
        word = word.strip()
        text = text.strip()
        _selected_word["word"] = word
        entry_word.delete(0, tk.END)
        entry_word.insert(0, word)
        entry_replacement.delete(0, tk.END)
        entry_replacement.insert(0, text)

    listbox.bind("<<ListboxSelect>>", on_select)
    refresh()

    input_frame = tk.Frame(win, bg=colors.BG_CARD)
    input_frame.pack(fill="x", padx=15, pady=10)

    tk.Label(
        input_frame, text="Слово:", bg=colors.BG_CARD, fg=colors.TEXT_MAIN,
        font=("Segoe UI", 10)
    ).grid(row=0, column=0, sticky="w", padx=(0, 10))

    entry_word = tk.Entry(
        input_frame, width=20, font=("Segoe UI", 10),
        bg=colors.BG_INPUT, fg=colors.TEXT_MAIN,
        insertbackground=colors.TEXT_MAIN, relief="flat",
        highlightthickness=1, highlightbackground=colors.BORDER
    )
    entry_word.grid(row=0, column=1, padx=5)

    tk.Label(
        input_frame, text="Замена:", bg=colors.BG_CARD, fg=colors.TEXT_MAIN,
        font=("Segoe UI", 10)
    ).grid(row=0, column=2, sticky="w", padx=(10, 10))

    entry_replacement = tk.Entry(
        input_frame, width=20, font=("Segoe UI", 10),
        bg=colors.BG_INPUT, fg=colors.TEXT_MAIN,
        insertbackground=colors.TEXT_MAIN, relief="flat",
        highlightthickness=1, highlightbackground=colors.BORDER
    )
    entry_replacement.grid(row=0, column=3, padx=5)

    btn_frame_wr = tk.Frame(win, bg=colors.BG_CARD)
    btn_frame_wr.pack(fill="x", padx=15, pady=(0, 15))

    def add_rule():
        word = entry_word.get().strip()
        replacement = entry_replacement.get().strip()
        if not word or not replacement:
            messagebox.showwarning("⚠ Поля пусты", "Заполните слово и замену", parent=win)
            return
        if word_replacer.get_category(word) is not None:
            messagebox.showwarning(
                "⚠ Слово уже есть",
                f"«{word}» уже есть в словаре.\nИспользуйте «✏ Сохранить изменения».",
                parent=win
            )
            return
        word_replacer.add_rule(word, replacement, category="custom")
        entry_word.delete(0, tk.END)
        entry_replacement.delete(0, tk.END)
        _selected_word["word"] = None
        refresh()

    def save_changes():
        original_word = _selected_word["word"]
        if not original_word:
            messagebox.showwarning(
                "⚠ Ничего не выбрано", "Выберите слово в списке для редактирования", parent=win
            )
            return
        new_word = entry_word.get().strip()
        new_text = entry_replacement.get().strip()
        if not new_word or not new_text:
            messagebox.showwarning("⚠ Поля пусты", "Заполните слово и замену", parent=win)
            return
        if new_word != original_word:
            word_replacer.remove_rule(original_word)
        word_replacer.add_rule(new_word, new_text, category="custom")
        entry_word.delete(0, tk.END)
        entry_replacement.delete(0, tk.END)
        _selected_word["word"] = None
        refresh()

    def remove_rule():
        sel = listbox.curselection()
        if sel:
            item = listbox.get(sel[0])
            word = item.split("  →  ")[0].strip()
            word_replacer.remove_rule(word)
            entry_word.delete(0, tk.END)
            entry_replacement.delete(0, tk.END)
            _selected_word["word"] = None
            refresh()

    _create_button(btn_frame_wr, "➕ Добавить", add_rule,
                    bg=colors.BG_INPUT).pack(side="left", padx=(0, 10))
    _create_button(btn_frame_wr, "✏ Сохранить изменения", save_changes,
                    bg=colors.BG_INPUT).pack(side="left", padx=(0, 10))
    _create_button(btn_frame_wr, "🗑 Удалить", remove_rule, bg=colors.BG_DANGER,
                    fg=colors.TEXT_MAIN).pack(side="left")

    wr_cb = ctk.CTkCheckBox(
        btn_frame_wr, text="Словарь активен", variable=_word_replacer_enabled_var,
        fg_color=colors.BG_ACTIVE, hover_color=colors.BG_HOVER,
        border_color=colors.BORDER, text_color=colors.TEXT_MAIN,
        font=("Segoe UI", 9)
    )
    wr_cb.pack(side="right")
    _ToolTip(
        wr_cb,
        "Включает замену слов по словарю перед синтезом.\n\n"
        "При отключении аббревиатуры, числа и иностранные\n"
        "термины могут читаться некорректно или вызывать\n"
        "артефакты — повторы, обрывы, «каша» в речи."
    )

    def close_window():
        _save_settings()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", close_window)