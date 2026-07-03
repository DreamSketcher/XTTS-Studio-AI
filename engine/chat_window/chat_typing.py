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

def _show_typing():


    if not _widget_exists(state.chat_messages_frame):
        return

    _hide_typing()
    state._typing_step = 0

    row = TkFrame(state.chat_messages_frame, bg=_c("BG_DARK"))
    row._is_message_row = True
    row.pack(fill="x", padx=12, pady=6)

    avatar = TkLabel(
        row,
        text="🤖",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI Emoji", 18),
        width=2,
    )
    avatar.pack(side="left", anchor="n")

    bubble = TkFrame(
        row,
        bg=_c("BG_CARD"),
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
        padx=12,
        pady=10,
    )
    bubble.pack(side="left", padx=(8, 60), anchor="w")

    lbl = TkLabel(
        bubble,
        text="AI печатает",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 10, "italic"),
    )
    lbl.pack()

    state._typing_frame = row
    state._typing_label = lbl

    _animate_typing()
    if _is_chat_near_bottom():
        _scroll_chat_to_bottom()


def _animate_typing():


    if not state._generation_running or not _widget_exists(state._typing_label):
        return

    dots = "." * ((state._typing_step % 3) + 1)
    state._typing_step += 1

    try:
        state._typing_label.config(text=f"AI печатает{dots}")
    except Exception:
        return

    state._typing_after_id = _safe_after(350, _animate_typing)


def _hide_typing():


    if state._typing_after_id is not None and state._root is not None:
        try:
            state._root.after_cancel(state._typing_after_id)
        except Exception:
            pass

    state._typing_after_id = None

    if _widget_exists(state._typing_frame):
        try:
            state._typing_frame.destroy()
        except Exception:
            pass

    state._typing_frame = None
    state._typing_label = None



# Inter-module imports
from engine.gui.chat_window.engine.utils import _now_ts, _now_full, _approx_tokens, _ai_display_name, _build_editor_compose_prompt
from engine.gui.chat_window.engine.sessions import _load_sessions, _save_sessions, _enforce_limits, _create_session_dict, _get_current_session, _update_session_title_if_needed, _messages_for_api
from engine.gui.chat_window.engine.generation import _run_generation
from engine.gui.chat_window.ui_utils import _c, _safe_after, _widget_exists, _set_dark_titlebar, _get_app_parent, _show_window, _call_and_break, _ask_simple_text, _make_button, _set_button_text, _set_button_state, _is_descendant, _get_widget_text, _select_all_widget, _paste_clipboard_into_widget, _copy_to_clipboard
from engine.gui.chat_window.hotkeys import _event_has_ctrl, _event_has_shift, _match_hotkey, _on_ctrl_keypress, _handle_text_ctrl, _handle_window_ctrl, _bind_window_hotkeys, _bind_text_hotkeys
from engine.gui.chat_window.placeholders import _create_placeholder_overlay, _sync_text_placeholder, _refresh_placeholder_state, _update_input_placeholder_text
from engine.gui.chat_window.chat_scroll import _is_chat_near_bottom, _scroll_chat_to_bottom, _show_new_message_indicator, _hide_new_message_indicator, _scroll_to_new_message, _chat_mousewheel
from engine.gui.chat_window.chat_history import _refresh_session_list, _on_session_select, new_chat, delete_current_chat, clear_chat_history
from engine.gui.chat_window.chat_messages import _add_message_bubble, _add_system_message, _resize_bubble_text, content_lines_estimate, _lighten_color, _selected_bubble_frame_get, _select_bubble, _on_bubble_text_click, _show_bubble_context_menu, _update_wraplengths, _render_current_session, _add_empty_state, _destroy_empty_state_if_any, _clear_messages_ui
from engine.gui.chat_window.chat_input import _focus_chat_input, _reset_editor_mode, _input_has_placeholder, _set_input_placeholder, _clear_input_placeholder, _get_input_text, _clear_input_text, _resize_input, _update_token_counter, _paste_into_input, _on_input_focus_in, _on_input_focus_out, _on_input_key_release, _on_enter, _submit_prompt, send_chat_message, _insert_prompt_into_chat_input
from engine.gui.chat_window.chat_actions import _send_to_main_editor, _stop_generation, _set_generation_ui, improve_text_with_gpt, paste_from_editor, set_chat_status, append_chat_message
from engine.gui.chat_window.chat_export import export_current_chat
from engine.gui.chat_window.chat_search import open_search
from engine.gui.chat_window.chat_settings import open_gpt_settings
from engine.gui.chat_window.chat_editor import _show_editor_preview, _hide_editor_preview, open_editor_text_window, _get_selected_or_all_text, _show_editor_window
from engine.gui.chat_window import init, open_chat_window
