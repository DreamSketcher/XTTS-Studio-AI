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

def _is_chat_near_bottom(threshold: float = 0.01) -> bool:
    if not _widget_exists(state.chat_canvas):
        return True
    try:
        _top, bottom = state.chat_canvas.yview()
        return bottom >= (1.0 - threshold)
    except Exception:
        return True


def _scroll_chat_to_bottom(immediate: bool = False):

    if not _widget_exists(state.chat_canvas):
        return

    if immediate:
        try:
            state.chat_canvas.update_idletasks()
            state.chat_canvas.configure(scrollregion=state.chat_canvas.bbox("all"))
            state.chat_canvas.yview_moveto(1.0)
        except Exception:
            pass
        return

    # Отменяем предыдущий запланированный скролл
    if state._scroll_debounce_id is not None:
        try:
            state._root.after_cancel(state._scroll_debounce_id)
        except Exception:
            pass
        state._scroll_debounce_id = None

    def _do_scroll():

        state._scroll_debounce_id = None
        if not _widget_exists(state.chat_canvas):
            return
        try:
            state.chat_canvas.update_idletasks()
            state.chat_canvas.configure(scrollregion=state.chat_canvas.bbox("all"))
            state.chat_canvas.yview_moveto(1.0)
        except Exception:
            pass

    state._scroll_debounce_id = _safe_after(80, _do_scroll)


def _show_new_message_indicator():


    if not _widget_exists(state.composer_outer_ref[0]):
        return

    if _widget_exists(state._new_message_btn):
        return  # уже показана

    state._new_message_btn = _make_button(
        state.composer_outer_ref[0],
        "↓ Новый ответ — нажмите, чтобы прокрутить",
        _scroll_to_new_message,
        bg=_c("ACCENT"),
        fg="#ffffff",
        font_size=9,
        height=1,
        padx=10,
        pady=5,
    )
    state._new_message_btn.pack(fill="x", pady=(0, 4), before=state.composer_card_ref[0])


def _hide_new_message_indicator():

    if _widget_exists(state._new_message_btn):
        try:
            state._new_message_btn.destroy()
        except Exception:
            pass
    state._new_message_btn = None


def _scroll_to_new_message():
    _hide_new_message_indicator()
    _scroll_chat_to_bottom(immediate=True)


def _chat_mousewheel(event):
    if not _widget_exists(state.chat_canvas):
        return None

    try:
        pointer = state._root.winfo_containing(event.x_root, event.y_root) if state._root is not None else None
        if pointer is None:
            return None

        if not _is_descendant(pointer, state.chat_canvas):
            return None

        if getattr(event, "num", None) == 4:
            units = -3
        elif getattr(event, "num", None) == 5:
            units = 3
        else:
            delta = int(getattr(event, "delta", 0) or 0)
            if delta == 0:
                return None
            units = -3 if delta > 0 else 3

        state.chat_canvas.yview_scroll(units, "units")

        # Если пользователь докрутил до низа сам — убираем индикатор
        _safe_after(50, lambda: _hide_new_message_indicator() if _is_chat_near_bottom() else None)

        return "break"
    except Exception:
        return None



# Inter-module imports
from engine.gui.chat_window.engine.utils import _now_ts, _now_full, _approx_tokens, _ai_display_name, _build_editor_compose_prompt
from engine.gui.chat_window.engine.sessions import _load_sessions, _save_sessions, _enforce_limits, _create_session_dict, _get_current_session, _update_session_title_if_needed, _messages_for_api
from engine.gui.chat_window.engine.generation import _run_generation
from engine.gui.chat_window.ui_utils import _c, _safe_after, _widget_exists, _set_dark_titlebar, _get_app_parent, _show_window, _call_and_break, _ask_simple_text, _make_button, _set_button_text, _set_button_state, _is_descendant, _get_widget_text, _select_all_widget, _paste_clipboard_into_widget, _copy_to_clipboard
from engine.gui.chat_window.hotkeys import _event_has_ctrl, _event_has_shift, _match_hotkey, _on_ctrl_keypress, _handle_text_ctrl, _handle_window_ctrl, _bind_window_hotkeys, _bind_text_hotkeys
from engine.gui.chat_window.placeholders import _create_placeholder_overlay, _sync_text_placeholder, _refresh_placeholder_state, _update_input_placeholder_text
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
