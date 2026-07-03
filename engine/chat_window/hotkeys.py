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

def _event_has_ctrl(event) -> bool:
    try:
        return bool(int(getattr(event, "state", 0) or 0) & 0x0004)
    except Exception:
        return False


def _event_has_shift(event) -> bool:
    try:
        return bool(int(getattr(event, "state", 0) or 0) & 0x0001)
    except Exception:
        return False


def _match_hotkey(event, key: str) -> bool:
    data = state._HOTKEYS.get(key.lower())
    if not data:
        return False

    try:
        keysym = str(getattr(event, "keysym", "") or "").lower()
        char = str(getattr(event, "char", "") or "").lower()
    except Exception:
        return False

    return keysym in data["keysyms"] or char in data["chars"]


def _on_ctrl_keypress(event, widget=None):
    """
    Универсальный Ctrl-handler для Text/Entry.
    Работает на английской и русской раскладке:
      Ctrl+V / Ctrl+М — вставить
      Ctrl+A / Ctrl+Ф — выделить всё
    """
    if not _event_has_ctrl(event):
        return None

    target = widget or getattr(event, "widget", None)

    if _match_hotkey(event, "v"):
        return _paste_clipboard_into_widget(target)

    if _match_hotkey(event, "a"):
        return _select_all_widget(target)

    return None


def _handle_text_ctrl(event, extra_handlers: dict[str, callable] | None = None):
    """
    Ctrl-handler для Text/Entry:
      1) сначала текстовые операции Ctrl+A/Ctrl+V;
      2) затем дополнительные горячие клавиши окна.
    """
    if not _event_has_ctrl(event):
        return None

    target = getattr(event, "widget", None)

    if isinstance(target, (tk.Text, tk.Entry)):
        if _match_hotkey(event, "v"):
            return _paste_clipboard_into_widget(target)
        if _match_hotkey(event, "a"):
            return _select_all_widget(target)

    if extra_handlers:
        for key, handler in extra_handlers.items():
            if _match_hotkey(event, key):
                return handler(event)

    return None


def _handle_window_ctrl(event, handlers: dict[str, callable] | None = None):
    if not _event_has_ctrl(event):
        return None

    if handlers:
        for key, handler in handlers.items():
            if _match_hotkey(event, key):
                return handler(event)

    return None


def _bind_window_hotkeys(window, handlers: dict[str, callable] | None = None):
    """
    Привязка Ctrl-горячих клавиш к окну независимо от раскладки.
    """
    if not _widget_exists(window):
        return
    try:
        window.bind("<Control-KeyPress>", lambda e: _handle_window_ctrl(e, handlers), add="+")
    except Exception:
        pass


def _bind_text_hotkeys(widget, extra_handlers: dict[str, callable] | None = None):
    """
    Привязка Ctrl-горячих клавиш к Text/Entry независимо от раскладки.
    """
    if not _widget_exists(widget):
        return
    try:
        widget.bind("<Control-KeyPress>", lambda e: _handle_text_ctrl(e, extra_handlers), add="+")
    except Exception:
        pass



# Inter-module imports
from engine.gui.chat_window.chat_window_engine.utils import _now_ts, _now_full, _approx_tokens, _ai_display_name, _build_editor_compose_prompt
from engine.gui.chat_window.chat_window_engine.sessions import _load_sessions, _save_sessions, _enforce_limits, _create_session_dict, _get_current_session, _update_session_title_if_needed, _messages_for_api
from engine.gui.chat_window.chat_window_engine.generation import _run_generation
from engine.gui.chat_window.ui_utils import _c, _safe_after, _widget_exists, _set_dark_titlebar, _get_app_parent, _show_window, _call_and_break, _ask_simple_text, _make_button, _set_button_text, _set_button_state, _is_descendant, _get_widget_text, _select_all_widget, _paste_clipboard_into_widget, _copy_to_clipboard
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
