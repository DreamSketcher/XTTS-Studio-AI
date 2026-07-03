from __future__ import annotations
import json
import os
import threading
import uuid
from datetime import datetime
from tkinter import filedialog, messagebox
import tkinter as tk

import engine.gui.chat_window.state as state
from engine.gui.chat_window.custom_widgets import CTK_AVAILABLE, CTkFrame, CTkLabel, CTkButton, TkFrame, TkLabel, TkButton, TkRawFrame

def _c(name: str) -> str:
    if state._colors is not None and hasattr(state._colors, name):
        return getattr(state._colors, name)
    return state._FALLBACK_COLORS.get(name, "#ffffff")


def _safe_after(delay: int, callback):
    try:
        if state._root is not None:
            return state._root.after(delay, callback)
    except Exception:
        return None
    return None


def _widget_exists(widget) -> bool:
    try:
        return widget is not None and bool(widget.winfo_exists())
    except Exception:
        return False


def _set_dark_titlebar(win):
    try:
        import ctypes
        win.update()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
        )
    except Exception:
        pass


def _get_app_parent():
    if _widget_exists(state._chat_window):
        return state._chat_window
    return state._root


def _show_window(win) -> bool:
    if not _widget_exists(win):
        return False
    try:
        win.deiconify()
    except Exception:
        pass
    try:
        win.lift()
    except Exception:
        pass
    try:
        win.focus_force()
    except Exception:
        pass
    return True


def _call_and_break(func, *args, **kwargs):
    func(*args, **kwargs)
    return "break"


def _ask_simple_text(parent, title: str, prompt: str, initial: str = "") -> str | None:
    """
    Лёгкое модальное окно с одним полем ввода. Возвращает строку или None при отмене.
    Не использует tkinter.simpledialog, чтобы выдержать общую тёмную тему окон.
    """
    result = {"value": None}

    dlg = tk.Toplevel(parent)
    _set_dark_titlebar(dlg)
    dlg.title(title)
    dlg.configure(bg=_c("BG_CARD"))
    dlg.resizable(False, False)
    dlg.transient(parent)
    dlg.grab_set()
    

    TkLabel(
        dlg, text=prompt, bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 9), wraplength=320, justify="left",
    ).pack(padx=16, pady=(16, 8), anchor="w")

    var = tk.StringVar(value=initial)
    entry = tk.Entry(
        dlg, textvariable=var, bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"),
        insertbackground=_c("TEXT_MAIN"), relief="flat",
        highlightthickness=1, highlightbackground=_c("BORDER"),
        highlightcolor=_c("ACCENT"), font=("Segoe UI", 10), width=36,
    )
    entry.pack(padx=16, pady=(0, 12), ipady=5)
    entry.select_range(0, tk.END)

    btn_row = TkFrame(dlg, bg=_c("BG_CARD"))
    btn_row.pack(padx=16, pady=(0, 16), fill="x")

    def confirm(event=None):
        result["value"] = var.get().strip()
        dlg.destroy()

    def cancel(event=None):
        result["value"] = None
        dlg.destroy()

    _make_button(
        btn_row, "Отмена", cancel, bg=_c("BG_INPUT"), font_size=8, height=1, padx=8, pady=3,
    ).pack(side="right", padx=(6, 0))
    _make_button(
        btn_row, "ОК", confirm, bg=_c("BG_ACTIVE"), font_size=8, height=1, padx=8, pady=3,
    ).pack(side="right")

    entry.bind("<Return>", confirm)
    dlg.bind("<Escape>", cancel)
    dlg.protocol("WM_DELETE_WINDOW", cancel)

    entry.focus_set()
    dlg.wait_window()

    return result["value"]


def _make_button(parent, text: str, command=None, **kwargs):
    if state._create_button is not None:
        attempts = (
            lambda: state._create_button(parent, text, command, **kwargs),
            lambda: state._create_button(parent, text, command),
        )
        for attempt in attempts:
            try:
                btn = attempt()
                if btn is not None:
                    return btn
            except TypeError:
                continue
            except Exception:
                break
    # fallback — создаём TkButton напрямую
    ...

    bg = kwargs.get("bg", _c("BG_CARD"))
    fg = kwargs.get("fg", _c("TEXT_MAIN"))
    width = kwargs.get("width", None)
    height = kwargs.get("height", 1)
    font_size = kwargs.get("font_size", 9)
    padx = kwargs.get("padx", 10)
    pady = kwargs.get("pady", 5)

    btn = TkButton(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=_c("BG_ACTIVE"),
        activeforeground=_c("TEXT_MAIN"),
        relief="flat",
        cursor="hand2",
        font=("Segoe UI", font_size, "bold"),
        padx=padx,
        pady=pady,
        height=height,
    )
    if width is not None:
        try:
            btn.config(width=width)
        except Exception:
            pass
    return btn


def _set_button_text(button, text: str):
    if not _widget_exists(button):
        return
    try:
        button.config(text=text)
    except Exception:
        try:
            button.configure(text=text)
        except Exception:
            pass


def _set_button_state(button, state: str):
    if not _widget_exists(button):
        return
    try:
        button.config(state=state)
    except Exception:
        pass


def _is_descendant(widget, ancestor) -> bool:
    try:
        while widget is not None:
            if widget == ancestor:
                return True
            widget = widget.master
    except Exception:
        return False
    return False


def _get_widget_text(widget) -> str:
    if not _widget_exists(widget):
        return ""
    try:
        if isinstance(widget, tk.Text):
            return widget.get("1.0", "end-1c")
        if isinstance(widget, tk.Entry):
            return widget.get()
    except Exception:
        return ""
    return ""


def _select_all_widget(widget):
    if not _widget_exists(widget):
        return "break"
    try:
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set(tk.INSERT, "1.0")
            widget.see(tk.INSERT)
            return "break"
        if isinstance(widget, tk.Entry):
            widget.selection_range(0, tk.END)
            widget.icursor(tk.END)
            return "break"
    except Exception:
        pass
    return "break"


def _paste_clipboard_into_widget(widget):
    if not _widget_exists(widget):
        return "break"

    try:
        text = (_get_app_parent() or state._root).clipboard_get()
    except Exception:
        return "break"

    try:
        if isinstance(widget, tk.Text):
            try:
                widget.delete("sel.first", "sel.last")
            except Exception:
                pass
            widget.insert(tk.INSERT, text)
        elif isinstance(widget, tk.Entry):
            try:
                widget.delete("sel.first", "sel.last")
            except Exception:
                pass
            widget.insert(tk.INSERT, text)
    except Exception:
        pass

    try:
        widget.event_generate("<<Modified>>")
    except Exception:
        pass

    return "break"


def _copy_to_clipboard(text: str):
    try:
        target = _get_app_parent() or state._root
        if target is None:
            return
        target.clipboard_clear()
        target.clipboard_append(text)
        set_chat_status("Сообщение скопировано")
    except Exception as e:
        set_chat_status(f"Не удалось скопировать: {e}")



# Inter-module imports
from engine.gui.chat_window.chat_window_engine.utils import _now_ts, _now_full, _approx_tokens, _ai_display_name, _build_editor_compose_prompt
from engine.gui.chat_window.chat_window_engine.sessions import _load_sessions, _save_sessions, _enforce_limits, _create_session_dict, _get_current_session, _update_session_title_if_needed, _messages_for_api
from engine.gui.chat_window.chat_window_engine.generation import _run_generation
from engine.gui.chat_window.hotkeys import _event_has_ctrl, _event_has_shift, _match_hotkey, _on_ctrl_keypress, _handle_text_ctrl, _handle_window_ctrl, _bind_window_hotkeys, _bind_text_hotkeys
from engine.gui.chat_window.placeholders import _create_placeholder_overlay, _sync_text_placeholder, _refresh_placeholder_state, _update_input_placeholder_text
from engine.gui.chat_window.chat_scroll import _is_chat_near_bottom, _scroll_chat_to_bottom, _show_new_message_indicator, _hide_new_message_indicator, _scroll_to_new_message, _chat_mousewheel
from engine.gui.chat_window.chat_history import _refresh_session_list, _on_session_select, new_chat, delete_current_chat, clear_chat_history
from engine.gui.chat_window.chat_messages import _add_message_bubble, _add_system_message, _resize_bubble_text, content_lines_estimate, _lighten_color, _selected_bubble_frame_get, _select_bubble, _on_bubble_text_click, _show_bubble_context_menu, _update_wraplengths, _render_current_session, _add_empty_state, _destroy_empty_state_if_any, _clear_messages_ui
from engine.gui.chat_window.chat_input import _focus_chat_input, _reset_editor_mode, _input_has_placeholder, _set_input_placeholder, _clear_input_placeholder, _get_input_text, _clear_input_text, _resize_input, _update_token_counter, _paste_into_input, _on_input_focus_in, _on_input_focus_out, _on_input_key_release, _on_enter, _submit_prompt, send_chat_message, _insert_prompt_into_chat_input
from engine.gui.chat_window.chat_typing import _show_typing, _animate_typing, _hide_typing
from engine.gui.chat_window.chat_actions import _send_to_main_editor, _stop_generation, _set_generation_ui, improve_text_with_gpt, paste_from_editor, set_chat_status, append_chat_message
from engine.gui.chat_window.chat_export import export_current_chat
from engine.gui.chat_window.chat_search import open_search
from engine.gui.chat_window.chat_settings import open_gpt_settings
from engine.gui.chat_window.chat_editor import _show_editor_preview, _hide_editor_preview, open_editor_text_window, _get_selected_or_all_text, _show_editor_window
from engine.gui.chat_window import init, open_chat_window
