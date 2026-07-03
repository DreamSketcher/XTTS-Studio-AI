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

def _refresh_session_list():
    if not _widget_exists(state.session_listbox):
        return

    try:
        state.session_listbox.delete(0, tk.END)

        for s in state._sessions:
            title = s.get("title") or "Новый чат"
            count = len(s.get("messages", []))
            marker = "• " if s.get("id") == state._current_session_id else "  "
            label = f"{marker}{title}"
            if count:
                label += f"  ({count})"
            state.session_listbox.insert(tk.END, label)

        for i, s in enumerate(state._sessions):
            if s.get("id") == state._current_session_id:
                state.session_listbox.selection_clear(0, tk.END)
                state.session_listbox.selection_set(i)
                state.session_listbox.activate(i)
                break
    except Exception:
        pass


def _on_session_select(event=None):


    if not _widget_exists(state.session_listbox):
        return

    try:
        sel = state.session_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(state._sessions):
            return

        _save_sessions()
        state._current_session_id = state._sessions[idx]["id"]
        _render_current_session()
        _refresh_session_list()
        set_chat_status("Сессия загружена")
    except Exception as e:
        set_chat_status(f"Ошибка переключения сессии: {e}")


def new_chat():


    _stop_generation(silent=True)

    s = _create_session_dict()
    state._sessions.insert(0, s)
    state._current_session_id = s["id"]

    _enforce_limits()
    _save_sessions()

    _render_current_session()
    _refresh_session_list()
    set_chat_status("Создан новый чат")
    _focus_chat_input()


def delete_current_chat():


    session = _get_current_session()
    title = session.get("title") or "Новый чат"

    if not messagebox.askyesno(
        "Удалить чат",
        f"Удалить чат «{title}» без возможности восстановления?",
        parent=_get_app_parent() or state._root,
    ):
        return

    _stop_generation(silent=True)

    state._sessions = [s for s in state._sessions if s.get("id") != state._current_session_id]

    if not state._sessions:
        new_session = _create_session_dict()
        state._sessions.append(new_session)
        state._current_session_id = new_session["id"]
    else:
        state._current_session_id = state._sessions[0]["id"]

    _save_sessions()
    _render_current_session()
    _refresh_session_list()
    set_chat_status("Чат удалён")
    _focus_chat_input()


def clear_chat_history():
    session = _get_current_session()

    if not messagebox.askyesno(
        "Очистить чат",
        "Очистить сообщения текущего чата?",
        parent=_get_app_parent() or state._root,
    ):
        return

    session["messages"] = []
    session["title"] = "Новый чат"
    _save_sessions()
    _render_current_session()
    _refresh_session_list()
    set_chat_status("История текущего чата очищена")



# Inter-module imports
from engine.gui.chat_window.engine.utils import _now_ts, _now_full, _approx_tokens, _ai_display_name, _build_editor_compose_prompt
from engine.gui.chat_window.engine.sessions import _load_sessions, _save_sessions, _enforce_limits, _create_session_dict, _get_current_session, _update_session_title_if_needed, _messages_for_api
from engine.gui.chat_window.engine.generation import _run_generation
from engine.gui.chat_window.ui_utils import _c, _safe_after, _widget_exists, _set_dark_titlebar, _get_app_parent, _show_window, _call_and_break, _ask_simple_text, _make_button, _set_button_text, _set_button_state, _is_descendant, _get_widget_text, _select_all_widget, _paste_clipboard_into_widget, _copy_to_clipboard
from engine.gui.chat_window.hotkeys import _event_has_ctrl, _event_has_shift, _match_hotkey, _on_ctrl_keypress, _handle_text_ctrl, _handle_window_ctrl, _bind_window_hotkeys, _bind_text_hotkeys
from engine.gui.chat_window.placeholders import _create_placeholder_overlay, _sync_text_placeholder, _refresh_placeholder_state, _update_input_placeholder_text
from engine.gui.chat_window.chat_scroll import _is_chat_near_bottom, _scroll_chat_to_bottom, _show_new_message_indicator, _hide_new_message_indicator, _scroll_to_new_message, _chat_mousewheel
from engine.gui.chat_window.chat_messages import _add_message_bubble, _add_system_message, _resize_bubble_text, content_lines_estimate, _lighten_color, _selected_bubble_frame_get, _select_bubble, _on_bubble_text_click, _show_bubble_context_menu, _update_wraplengths, _render_current_session, _add_empty_state, _destroy_empty_state_if_any, _clear_messages_ui
from engine.gui.chat_window.chat_input import _focus_chat_input, _reset_editor_mode, _input_has_placeholder, _set_input_placeholder, _clear_input_placeholder, _get_input_text, _clear_input_text, _resize_input, _update_token_counter, _paste_into_input, _on_input_focus_in, _on_input_focus_out, _on_input_key_release, _on_enter, _submit_prompt, send_chat_message, _insert_prompt_into_chat_input
from engine.gui.chat_window.chat_typing import _show_typing, _animate_typing, _hide_typing
from engine.gui.chat_window.chat_actions import _send_to_main_editor, _stop_generation, _set_generation_ui, improve_text_with_gpt, paste_from_editor, set_chat_status, append_chat_message
from engine.gui.chat_window.chat_export import export_current_chat
from engine.gui.chat_window.chat_search import open_search
from engine.gui.chat_window.chat_settings import open_gpt_settings
from engine.gui.chat_window.chat_editor import _show_editor_preview, _hide_editor_preview, open_editor_text_window, _get_selected_or_all_text, _show_editor_window
from engine.gui.chat_window import init, open_chat_window
