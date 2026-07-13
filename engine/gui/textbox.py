# -*- coding: utf-8 -*-
"""engine/gui/textbox.py — текстовое поле, плейсхолдер, подсветка чанков,
контекстное меню и горячие клавиши
"""

import os
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from tkinterdnd2 import DND_FILES
from i18n import t
from engine.logging_utils import write_log
from engine.text_tools import normalize_text
from engine.gui.colors import Colors
from engine.gui.tooltip import ToolTip
from engine.gui.widgets import create_card, create_button
from engine.gui import theme_manager

# Внедряются из main_window
root = None
use_gpt = None
textbox_updated = None
clean_path = None
show_help = None
# НОВОЕ: callback открытия конструктора темы + layout preset
on_open_theme_settings = None
_layout_preset = {}

# Состояние
highlight_pos = 0

# Виджеты
text_card = None
text_header = None
text_box = None
gpt_checkbox = None

# Размер текста в окне ввода
text_font_size = {"v": 12}
FONT_SIZE_MIN = 9
FONT_SIZE_MAX = 22
font_panel = {"btn": None, "panel": None, "open": False, "scale_var": None}


def init(**deps):
    """Внедрение зависимостей из main_window.
    Поддерживает: root, use_gpt, textbox_updated, clean_path, show_help,
    а также on_open_theme_settings, layout_preset
    """
    global on_open_theme_settings, _layout_preset
    # вытаскиваем новые ключи отдельно, чтобы globals().update не затирал функцию apply_layout
    on_open_theme_settings = deps.pop("on_open_theme_settings", None)
    _layout_preset = deps.pop("layout_preset", {}) or {}
    globals().update(deps)


def apply_layout(preset: dict) -> bool:
    """Live-применение геометрии из пресета раскладки.
    Возвращает True если применилось.
    """
    global _layout_preset
    _layout_preset = preset.copy()
    try:
        if text_box is not None:
            padx = preset.get("textbox_padx", 10)
            pady = preset.get("textbox_pady", 7)
            # text_box.pack_configure работает только после build_text_card
            text_box.pack_configure(padx=padx, pady=pady)
            return True
    except Exception:
        pass
    return False


def apply_text_font_size(size):
    try:
        size = max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, int(round(float(size)))))
    except Exception:
        return
    text_font_size["v"] = size
    try:
        text_box.configure(font=("Consolas", size))
    except Exception:
        pass


def restore_text_font_size(size):
    try:
        size = max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, int(round(float(size)))))
    except Exception:
        return
    text_font_size["v"] = size
    try:
        if text_box is not None:
            text_box.configure(font=("Consolas", size))
        var = font_panel.get("scale_var")
        if var is not None:
            var.set(size)
    except Exception:
        pass


def save_font_size_setting(_e=None):
    try:
        from engine.gui import settings_ui as settings_ui

        settings_ui.save_settings()
    except Exception:
        pass


def toggle_font_panel(event=None):
    if font_panel["open"]:
        hide_font_panel()
    else:
        show_font_panel()


def hide_font_panel(event=None):
    panel = font_panel.get("panel")
    if panel is not None:
        try:
            panel.place_forget()
        except Exception:
            pass
    font_panel["open"] = False
    btn = font_panel.get("btn")
    if btn is not None:
        try:
            btn.configure(text="Aa")
        except Exception:
            pass


def show_font_panel():
    panel = font_panel.get("panel")
    if panel is None:
        return
    panel.place(relx=1.0, rely=0.5, anchor="e", x=-34)
    panel.lift()
    font_panel["open"] = True
    btn = font_panel.get("btn")
    if btn is not None:
        try:
            btn.configure(text="✕")
        except Exception:
            pass


def build_font_size_control():
    btn = tk.Button(
        text_box,
        text="Aa",
        command=toggle_font_panel,
        bg=Colors.BG_HOVER,
        fg=Colors.TEXT_MAIN,
        activebackground=Colors.ACCENT,
        activeforeground=Colors.TEXT_MAIN,
        relief="flat",
        bd=0,
        font=("Segoe UI", 9, "bold"),
        padx=6,
        pady=4,
        cursor="hand2",
    )
    btn.place(relx=1.0, rely=0.5, anchor="e", x=-6)
    ToolTip(btn, t("tip_font_size"))
    font_panel["btn"] = btn

    panel = tk.Frame(
        text_box,
        bg=Colors.BG_CARD,
        highlightthickness=1,
        highlightbackground=Colors.BORDER,
        bd=0,
    )
    scale_var = tk.IntVar(value=text_font_size["v"])
    font_panel["scale_var"] = scale_var

    tk.Label(
        panel, text="A", bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, font=("Segoe UI", 11, "bold")
    ).pack(pady=(6, 0))
    scale = tk.Scale(
        panel,
        variable=scale_var,
        from_=FONT_SIZE_MAX,
        to=FONT_SIZE_MIN,
        orient="vertical",
        length=140,
        showvalue=True,
        bg=Colors.BG_CARD,
        fg=Colors.ACCENT,
        troughcolor=Colors.BG_INPUT,
        highlightthickness=0,
        sliderrelief="flat",
        sliderlength=18,
        font=("Consolas", 8),
        bd=0,
        command=apply_text_font_size,
    )
    scale.bind("<ButtonRelease-1>", save_font_size_setting, add="+")
    scale.pack(padx=6, pady=(0, 2))
    tk.Label(panel, text="A", bg=Colors.BG_CARD, fg=Colors.TEXT_DIM, font=("Segoe UI", 8)).pack(
        pady=(0, 6)
    )
    font_panel["panel"] = panel
    font_panel["open"] = False


def lock_textbox():
    try:
        text_box.config(state="disabled")
    except Exception:
        pass


def unlock_textbox():
    try:
        text_box.config(state="normal")
    except Exception:
        pass


def set_textbox_content(content: str):
    unlock_textbox()
    text_box.delete("1.0", tk.END)
    if content:
        text_box.insert("1.0", content)
        text_box.config(fg=Colors.TEXT_MAIN)
    else:
        show_placeholder()


def update_textbox_normalized(text: str):
    try:
        unlock_textbox()
        text_box.delete("1.0", tk.END)
        text_box.insert("1.0", text)
        text_box.config(fg=Colors.TEXT_MAIN)
        lock_textbox()
        textbox_updated.set()
    except Exception as e:
        print(f"[TextBox update error]: {e}")


def clear_chunk_highlight():
    try:
        text_box.tag_remove("chunk_highlight", "1.0", tk.END)
    except Exception:
        pass


def highlight_chunk(start, end):
    try:
        clear_chunk_highlight()
        if start is None or end is None:
            return
        start = int(start)
        end = int(end)
        visible_text = text_box.get("1.0", "end-1c")
        text_len = len(visible_text)
        start = max(0, min(start, text_len))
        end = max(0, min(end, text_len))
        if end <= start:
            return
        start_idx = f"1.0+{start} chars"
        end_idx = f"1.0+{end} chars"
        text_box.tag_add("chunk_highlight", start_idx, end_idx)
        text_box.tag_configure(
            "chunk_highlight", background=Colors.CHUNK_BG, foreground=Colors.CHUNK_FG
        )
        text_box.tag_raise("chunk_highlight")
        text_box.see(start_idx)
    except Exception as e:
        print(f"[Highlight error]: {e}")


_highlight_chunk = highlight_chunk


def highlight_chunk_by_text(chunk_raw: str):
    global highlight_pos
    try:
        clear_chunk_highlight()
        content = text_box.get("1.0", "end-1c")
        if not content or content == PLACEHOLDER:
            return
        chunk = (chunk_raw or "").replace("[NO_PAUSE]", "").strip()
        if not chunk:
            return

        def make_lookup(s: str):
            norm_chars = []
            index_map = []
            prev_space = False
            for i, ch in enumerate(s or ""):
                if ch.isspace():
                    if prev_space:
                        continue
                    norm_chars.append(" ")
                    index_map.append(i)
                    prev_space = True
                else:
                    norm_chars.append(ch.lower())
                    index_map.append(i)
                    prev_space = False
            while norm_chars and norm_chars[0] == " ":
                norm_chars.pop(0)
                index_map.pop(0)
            while norm_chars and norm_chars[-1] == " ":
                norm_chars.pop()
                index_map.pop()
            return "".join(norm_chars), index_map

        norm_content, index_map = make_lookup(content)
        norm_chunk, _ = make_lookup(chunk)
        if not norm_content or not norm_chunk or not index_map:
            return
        norm_search_from = 0
        found_search_pos = False
        for np, op in enumerate(index_map):
            if op >= highlight_pos:
                norm_search_from = np
                found_search_pos = True
                break
        if not found_search_pos:
            norm_search_from = 0
        idx = norm_content.find(norm_chunk, norm_search_from)
        if idx == -1:
            idx = norm_content.find(norm_chunk)
        match_len = len(norm_chunk)
        if idx == -1:
            words = norm_chunk.split()
            for n in (10, 8, 6, 5, 4, 3, 2):
                if len(words) >= n:
                    probe = " ".join(words[:n])
                    idx = norm_content.find(probe, norm_search_from)
                    if idx == -1:
                        idx = norm_content.find(probe)
                    if idx != -1:
                        match_len = len(norm_chunk)
                        break
        if idx == -1:
            print(f"[HL] chunk not found: {repr(chunk[:80])}")
            return
        end_norm = min(idx + match_len, len(index_map))
        start_orig = index_map[idx]
        if end_norm > idx:
            end_orig = index_map[end_norm - 1] + 1
        else:
            end_orig = start_orig
        text_len = len(content)
        start_orig = max(0, min(start_orig, text_len))
        end_orig = max(start_orig, min(end_orig, text_len))
        if end_orig <= start_orig:
            return
        start_idx = f"1.0+{start_orig} chars"
        end_idx = f"1.0+{end_orig} chars"
        text_box.tag_add("chunk_highlight", start_idx, end_idx)
        text_box.tag_configure(
            "chunk_highlight", background=Colors.CHUNK_BG, foreground=Colors.CHUNK_FG
        )
        text_box.tag_raise("chunk_highlight")
        text_box.see(start_idx)
        highlight_pos = end_orig
    except Exception as e:
        print(f"[Highlight error]: {e}")


_highlight_chunk_by_text = highlight_chunk_by_text


PLACEHOLDER = t("placeholder")


def show_placeholder():
    unlock_textbox()
    if not text_box.get("1.0", "end-1c"):
        text_box.insert("1.0", PLACEHOLDER)
        text_box.config(fg=Colors.TEXT_DIM)


def hide_placeholder(event=None):
    unlock_textbox()
    if text_box.get("1.0", "end-1c") == PLACEHOLDER:
        text_box.delete("1.0", tk.END)
        text_box.config(fg=Colors.TEXT_MAIN)


def get_textbox_content():
    return text_box.get("1.0", "end-1c").strip()


_get_textbox_content = get_textbox_content


def paste_safe(event=None):
    hide_placeholder()
    try:
        text_box.insert(tk.INSERT, normalize_text(root.clipboard_get()))
        text_box.config(fg=Colors.TEXT_MAIN)
    except Exception:
        pass
    return "break"


def copy_text(event=None):
    try:
        if text_box.tag_ranges(tk.SEL):
            selected = text_box.get(tk.SEL_FIRST, tk.SEL_LAST)
            root.clipboard_clear()
            root.clipboard_append(selected)
    except Exception:
        pass
    return "break"


def cut_text(event=None):
    try:
        if text_box.tag_ranges(tk.SEL):
            selected = text_box.get(tk.SEL_FIRST, tk.SEL_LAST)
            root.clipboard_clear()
            root.clipboard_append(selected)
            text_box.delete(tk.SEL_FIRST, tk.SEL_LAST)
    except Exception:
        pass
    return "break"


def select_all_text(event=None):
    try:
        text_box.tag_add(tk.SEL, "1.0", tk.END)
        text_box.mark_set(tk.INSERT, tk.END)
        text_box.see(tk.INSERT)
    except Exception:
        pass
    return "break"


def on_text_key_press(event):
    if event.state & 0x4:
        if event.keycode == 65:
            return select_all_text(event)
        elif event.keycode == 67:
            return copy_text(event)
        elif event.keycode == 88:
            return cut_text(event)
        elif event.keycode == 86:
            return paste_safe(event)
    return None


def load_txt():
    hide_placeholder()
    path = filedialog.askopenfilename(filetypes=[("TXT", "*.txt")])
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = normalize_text(f.read())
            set_textbox_content(content)
        except Exception:
            write_log(traceback.format_exc())
            messagebox.showerror("❌", t("dlg_error_open_file"))


def show_text_context_menu(event):
    hide_placeholder()
    menu = tk.Menu(
        root,
        tearoff=0,
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        activebackground=Colors.BG_HOVER,
        activeforeground=Colors.TEXT_MAIN,
        relief="flat",
        borderwidth=1,
    )
    menu.add_command(
        label=t("ctx_copy"),
        command=lambda: (
            (root.clipboard_clear(), root.clipboard_append(text_box.get(tk.SEL_FIRST, tk.SEL_LAST)))
            if text_box.tag_ranges(tk.SEL)
            else None
        ),
    )
    menu.add_command(label=t("ctx_paste"), command=paste_safe)
    menu.add_command(
        label=t("ctx_cut"),
        command=lambda: (
            (
                root.clipboard_clear(),
                root.clipboard_append(text_box.get(tk.SEL_FIRST, tk.SEL_LAST)),
                text_box.delete(tk.SEL_FIRST, tk.SEL_LAST),
            )
            if text_box.tag_ranges(tk.SEL)
            else None
        ),
    )
    menu.add_separator()
    menu.add_command(
        label=t("ctx_select_all"), command=lambda: text_box.tag_add(tk.SEL, "1.0", tk.END)
    )
    menu.add_command(
        label=t("ctx_clear"),
        command=lambda: (text_box.delete("1.0", tk.END), text_box.config(fg=Colors.TEXT_MAIN)),
    )
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def paste_clipboard():
    hide_placeholder()
    try:
        text_box.insert("insert", normalize_text(root.clipboard_get()))
        text_box.config(fg=Colors.TEXT_MAIN)
    except Exception:
        messagebox.showwarning("⚠", t("dlg_clipboard_empty"))


def drop_handler(event):
    hide_placeholder()
    path = clean_path(event.data)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = normalize_text(f.read())
            set_textbox_content(content)
        except Exception:
            write_log(traceback.format_exc())
            messagebox.showerror("❌", t("dlg_error_open_file"))


def _open_theme_customizer_fallback():
    """Fallback, если on_open_theme_settings не передан из main_window"""
    try:
        from engine.gui.chat_window.theme_settings import open_theme_customizer

        open_theme_customizer(root)
    except Exception:
        pass


def build_text_card(right_panel):
    global text_card, text_header, text_box, gpt_checkbox
    text_card = create_card(right_panel, "")
    text_card.pack(fill="both", expand=True, pady=(0, 10))
    text_header = tk.Frame(text_card, bg=Colors.BG_CARD)
    text_header.pack(fill="x", padx=10, pady=(7, 0))
    tk.Label(
        text_header,
        text=t("card_text"),
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", 11, "bold"),
        anchor="w",
    ).pack(side="left")
    create_button(text_header, t("btn_help"), show_help, bg=Colors.BG_INPUT).pack(side="right")
    from engine.gui import header_panel as header_panel

    ui_lang_btn = create_button(
        text_header, "RU/EN", header_panel.switch_ui_lang, bg=Colors.BG_INPUT, width=50
    )
    ui_lang_btn.pack(side="right", padx=(0, 6))
    ToolTip(ui_lang_btn, "Switch UI language / Переключить язык интерфейса")
    from engine.gui import theme as _theme

    # --- Theme button: click = toggle, long-press / double-click / right-click = open settings ---
    # Robust version: works with both tk.Button and CTkButton / custom create_button
    _theme_btn_state = {
        "long_timer": None,
        "long_fired": False,
        "suppress_click": False,
        "press_x": 0,
        "press_y": 0,
    }

    def _do_toggle_theme():
        """Переключение темы"""
        try:
            new_theme = "light" if _theme.get_theme() == "dark" else "dark"
            _theme.set_theme(new_theme)
            try:
                theme_btn.configure(text="☀" if new_theme == "dark" else "🌙")
            except Exception:
                pass
            try:
                from engine.gui import chat_window as _cw

                _cw.reapply_language()
            except Exception:
                pass
            try:
                from engine.gui import statusbar as _sb

                _sb.set_status(t("theme_title"))
            except Exception:
                pass
        except Exception:
            # ИЗМЕНЕНО (по просьбе пользователя): убран debug-вывод в консоль
            # (print + traceback.print_exc()) — оставлен от диагностики
            # давно найденного и исправленного бага открытия окна
            # конструктора темы. Ошибка по-прежнему тихо пишется в лог.
            try:
                write_log(traceback.format_exc())
            except Exception:
                pass

    def _open_theme_settings_action(source="unknown"):
        """Открыть конструктор темы.

        ИЗМЕНЕНО (по просьбе пользователя): убран весь debug-вывод в
        консоль (print(...) на каждый шаг + traceback.print_exc() + окно
        messagebox.showerror с полным текстом трейсбека) — всё это было
        добавлено временно для диагностики давно найденного и исправленного
        бага открытия окна конструктора темы. Ошибки по-прежнему тихо
        пишутся в лог-файл через write_log(), чтобы не терялись совсем,
        но больше не засоряют консоль/экран пользователя при каждом клике.
        """
        # 1. Пробуем callback из main_window
        cb = on_open_theme_settings
        if callable(cb):
            try:
                cb()
                return True
            except Exception:
                try:
                    write_log(traceback.format_exc())
                except Exception:
                    pass
        # 2. Fallback — напрямую
        try:
            from engine.gui.chat_window.theme_settings import open_theme_customizer

            open_theme_customizer(root)
            return True
        except Exception:
            try:
                write_log(traceback.format_exc())
            except Exception:
                pass
        return False

    def _theme_click_handler():
        """Обработчик штатного клика кнопки (command=)"""
        # Если только что был long-press — подавляем toggle
        import time

        now = time.time()
        if _theme_btn_state.get("long_fired_time", 0) > now - 0.5:
            return
        if _theme_btn_state.get("suppress_click"):
            _theme_btn_state["suppress_click"] = False
            return
        _do_toggle_theme()

    def _long_press_start(event=None):
        _theme_btn_state["long_fired"] = False
        try:
            _theme_btn_state["press_x"] = event.x_root if event else 0
            _theme_btn_state["press_y"] = event.y_root if event else 0
        except Exception:
            pass

        def _fire():
            _theme_btn_state["long_timer"] = None
            _theme_btn_state["long_pressed"] = True
            _theme_btn_state["long_fired"] = True
            import time

            _theme_btn_state["long_fired_time"] = time.time()
            _theme_btn_state["suppress_click"] = True
            # визуальный фидбек
            try:
                # пробуем CTk-style и tk-style
                try:
                    theme_btn.configure(fg_color=Colors.ACCENT)
                    root.after(150, lambda: theme_btn.configure(fg_color=Colors.BG_INPUT))
                except Exception:
                    theme_btn.configure(bg=Colors.ACCENT)
                    root.after(150, lambda: theme_btn.configure(bg=Colors.BG_INPUT))
            except Exception:
                pass
            _open_theme_settings_action("long-press")

        # отменяем старый таймер
        if _theme_btn_state["long_timer"] is not None:
            try:
                root.after_cancel(_theme_btn_state["long_timer"])
            except Exception:
                pass
        _theme_btn_state["long_timer"] = root.after(800, _fire)
        return None

    def _long_press_cancel(event=None):
        if _theme_btn_state["long_timer"] is not None:
            try:
                root.after_cancel(_theme_btn_state["long_timer"])
            except Exception:
                pass
            _theme_btn_state["long_timer"] = None
        return None

    def _long_press_move(event=None):
        if _theme_btn_state["long_timer"] is None:
            return
        try:
            dx = abs(event.x_root - _theme_btn_state["press_x"])
            dy = abs(event.y_root - _theme_btn_state.get("press_y", event.y_root))
            if dx > 25 or dy > 25:
                _long_press_cancel()
        except Exception:
            pass

    # Кнопка темы — command = toggle, чтобы клик работал даже если bind'ы не доходят (CTkButton)
    theme_btn = create_button(
        text_header,
        "☀" if _theme.get_theme() == "dark" else "🌙",
        _theme_click_handler,
        bg=Colors.BG_INPUT,
        width=34,
    )
    theme_btn.pack(side="right", padx=(0, 6))

    # Рекурсивная привязка long-press ко всем вложенным виджетам (нужно для CTkButton)
    def _bind_recursive(widget, sequence, func):
        try:
            widget.bind(sequence, func, add="+")
        except Exception:
            pass
        try:
            for child in widget.winfo_children():
                _bind_recursive(child, sequence, func)
        except Exception:
            pass

    for seq, fn in [
        ("<ButtonPress-1>", _long_press_start),
        ("<ButtonRelease-1>", lambda e: _long_press_cancel(e)),
        ("<B1-Motion>", _long_press_move),
        ("<Leave>", _long_press_cancel),
        # Fallback-триггеры, если long-press не сработал в окружении пользователя:
        ("<Double-Button-1>", lambda e: (_open_theme_settings_action("double-click"), "break")[1]),
        ("<Button-3>", lambda e: (_open_theme_settings_action("right-click"), "break")[1]),
    ]:
        _bind_recursive(theme_btn, seq, fn)

    # ToolTip — явно указываем все способы открытия
    tip_text = (
        "Клик — смена темы | Удерживайте 0,8с / двойной клик / ПКМ — настройки темы и раскладки"
    )
    try:
        i18n_tip = t("theme_tooltip_advanced")
        if i18n_tip and i18n_tip != "theme_tooltip_advanced":
            tip_text = i18n_tip + " | " + tip_text
    except Exception:
        pass
    _theme_btn_tooltip = ToolTip(theme_btn, tip_text)

    # ── Разовая ненавязчивая подсказка про Double-Click (Конструктор темы) ──
    # Показывается один раз при первом старте приложения (или пока
    # пользователь ни разу не открывал окно конструктора темы), затем
    # флаг сохраняется в theme_settings.json — при следующих запусках
    # подсказка больше не появляется сама. Обычный hover-тултип (ToolTip
    # выше) продолжает работать всегда, независимо от этого разового показа.
    def _show_layout_hint_once():
        try:
            if theme_manager.is_layout_hint_shown():
                return
            _theme_btn_tooltip.show()
            # Автоматически прячем через 4 секунды — не блокирует интерфейс,
            # пользователь может продолжать работать как обычно.
            root.after(4000, _theme_btn_tooltip.hide)
            theme_manager.mark_layout_hint_shown()
        except Exception:
            pass

    # Небольшая задержка (1.5с после построения интерфейса), чтобы окно
    # успело отрисоваться и подсказка не «прыгала» поверх недостроенного UI.
    root.after(1500, _show_layout_hint_once)

    # Геометрия textbox из пресета раскладки
    _padx = _layout_preset.get("textbox_padx", 10)
    _pady = _layout_preset.get("textbox_pady", 7)

    text_box = tk.Text(
        text_card,
        bg=Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        insertbackground=Colors.TEXT_MAIN,
        relief="flat",
        highlightthickness=0,
        font=("Consolas", text_font_size["v"]),
        padx=10,
        pady=10,
        wrap="word",
        undo=True,
    )
    text_box.pack(fill="both", expand=True, padx=_padx, pady=_pady)
    build_font_size_control()
    gpt_checkbox = ctk.CTkCheckBox(
        text_box,
        text=t("chk_ai_edit"),
        variable=use_gpt,
        fg_color=Colors.AI_ACCENT,
        hover_color=Colors.AI_ACCENT_HOVER,
        border_color=Colors.BORDER,
        text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", 11),
    )
    gpt_checkbox.place(x=8, rely=1.0, anchor="sw", y=-8)
    ToolTip(gpt_checkbox, t("tip_ai_edit"))
    text_box.bind("<FocusIn>", hide_placeholder)
    text_box.bind("<FocusOut>", lambda e: show_placeholder())
    text_box.drop_target_register(DND_FILES)
    text_box.dnd_bind("<<Drop>>", drop_handler)
    text_box.bind("<Button-3>", show_text_context_menu)
    text_box.bind("<Key>", on_text_key_press, add="+")
    text_box.tag_configure(
        "chunk_highlight", background=Colors.CHUNK_BG, foreground=Colors.CHUNK_FG
    )
    show_placeholder()
