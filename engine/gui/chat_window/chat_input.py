from __future__ import annotations
import json
import os
import threading
import uuid
from datetime import datetime
from tkinter import filedialog, messagebox
import tkinter as tk

import engine.gui.chat_window.state as state
from engine.gui.chat_window.custom_widgets import (
    CTK_AVAILABLE,
    CTkFrame,
    CTkLabel,
    CTkButton,
    TkFrame,
    TkLabel,
    TkButton,
    TkRawFrame,
)
from i18n import t


def _focus_chat_input():
    if _widget_exists(state.chat_input):
        try:
            state.chat_input.focus_set()
        except Exception:
            pass


def _reset_editor_mode():

    state._editor_mode = False
    _hide_editor_preview()
    lbl = (
        getattr(state.chat_input, "_placeholder_label", None)
        if _widget_exists(state.chat_input)
        else None
    )
    if _widget_exists(lbl):
        try:
            lbl.config(text=t("chat_placeholder_input"))
        except Exception:
            pass
    if state._hint_text_var is not None:
        try:
            state._hint_text_var.set(t("chat_hint_default"))
        except Exception:
            pass


def _input_has_placeholder() -> bool:
    try:
        return _widget_exists(state.chat_input_placeholder_label) and bool(
            state.chat_input_placeholder_label.winfo_ismapped()
        )
    except Exception:
        return False


def _set_input_placeholder():
    if not _widget_exists(state.chat_input):
        return
    _sync_text_placeholder(state.chat_input)


def _clear_input_placeholder():
    if not _widget_exists(state.chat_input):
        return
    try:
        if _widget_exists(state.chat_input_placeholder_label):
            state.chat_input_placeholder_label.place_forget()
    except Exception:
        pass


def _get_input_text() -> str:
    if not _widget_exists(state.chat_input):
        return ""
    try:
        return state.chat_input.get("1.0", "end-1c")
    except Exception:
        return ""


def _clear_input_text():
    if not _widget_exists(state.chat_input):
        return
    try:
        state.chat_input.delete("1.0", tk.END)
        state.chat_input.config(fg=_c("TEXT_MAIN"))
        _resize_input()
        _update_token_counter()
        _sync_text_placeholder(state.chat_input)
        _reset_editor_mode()
        _safe_after(50, _focus_chat_input)
    except Exception:
        pass


def _resize_input(event=None):
    if not _widget_exists(state.chat_input):
        return

    text = _get_input_text()
    if not text.strip():
        height = 3
    else:
        lines = text.count("\n") + 1
        for line in text.splitlines() or [""]:
            lines += max(0, len(line) // 90)
        height = min(7, max(3, lines))

    try:
        state.chat_input.config(height=height)
    except Exception:
        pass


def _update_token_counter(event=None):
    if not _widget_exists(state.chat_token_label):
        return

    text = _get_input_text()
    input_tokens = _approx_tokens(text)

    session = _get_current_session()
    chat_tokens = sum(_approx_tokens(m.get("content", "")) for m in session.get("messages", []))

    try:
        state.chat_token_label.config(text=t("chat_token_counter", input_tokens, chat_tokens))
    except Exception:
        pass


def _paste_into_input(event=None):
    if not _widget_exists(state.chat_input):
        return "break"
    return _paste_clipboard_into_widget(state.chat_input)


def _on_input_focus_in(event=None):
    _clear_input_placeholder()


def _on_input_focus_out(event=None):
    _sync_text_placeholder(state.chat_input)


def _on_input_key_release(event=None):
    _resize_input()
    _update_token_counter()
    _sync_text_placeholder(state.chat_input)


def _on_enter(event):
    if _event_has_shift(event):
        return None
    if _event_has_ctrl(event):
        return None
    if state._editor_mode and state._editor_preview_content:
        comment = _get_input_text().strip()
        _submit_prompt(comment, clear_input=True)
        return "break"
    send_chat_message()
    return "break"


def _submit_prompt(prompt: str, *, clear_input: bool = False):

    prompt = (prompt or "").strip()

    # В режиме свободного чата — игнорируем editor_mode, отправляем как обычный чат
    if state._free_chat_mode and not state._editor_mode:
        if not prompt:
            return
        session = _get_current_session()
        user_msg = {"role": "user", "content": prompt, "ts": _now_ts()}
        session.setdefault("messages", []).append(user_msg)
        _enforce_limits()
        _update_session_title_if_needed(session)
        _save_sessions()
        _add_message_bubble(user_msg, smooth_scroll=True, force_scroll=False)
        _refresh_session_list()
        if clear_input:
            _clear_input_text()
        _run_generation(session, prompt)
        return

    # ── Режим редактора: один пузырь, текст + комментарий склеены ────────────
    if state._editor_mode and state._editor_preview_content:
        src = state._editor_preview_content.strip()
        comment = prompt

        _reset_editor_mode()

        if clear_input:
            _clear_input_text()

        if comment:
            display_content = t("chat_display_with_comment", src, comment)
        else:
            display_content = src

        session = _get_current_session()

        user_msg = {"role": "user", "content": display_content, "ts": _now_ts()}
        session.setdefault("messages", []).append(user_msg)
        _enforce_limits()
        _update_session_title_if_needed(session)
        _save_sessions()
        _add_message_bubble(user_msg, smooth_scroll=True, force_scroll=False)
        _refresh_session_list()
        # Ждём пока scrollregion обновится после добавления пузыря, затем скроллим
        _safe_after(
            80,
            lambda: (
                _scroll_chat_to_bottom(immediate=True)
                if _widget_exists(state.chat_canvas)
                else None
            ),
        )

        _run_generation(session, display_content)
        _safe_after(100, _focus_chat_input)
        _safe_after(300, _focus_chat_input)
        return

    # ── Обычный режим ────────────────────────────────────────────────────────
    if not prompt:
        return

    session = _get_current_session()

    user_msg = {"role": "user", "content": prompt, "ts": _now_ts()}
    session.setdefault("messages", []).append(user_msg)
    _enforce_limits()
    _update_session_title_if_needed(session)
    _save_sessions()

    _add_message_bubble(user_msg, smooth_scroll=True, force_scroll=False)
    _refresh_session_list()

    if clear_input:
        _clear_input_text()

    _run_generation(session, prompt)


def send_chat_message(prompt: str | None = None):
    if prompt is None:
        prompt = _get_input_text().strip()
        if not prompt and not (state._editor_mode and state._editor_preview_content):
            return
        _submit_prompt(prompt, clear_input=True)
        return

    prompt = str(prompt).strip()
    if not prompt:
        return
    _submit_prompt(prompt, clear_input=False)


def _insert_prompt_into_chat_input(prompt: str):
    if not _widget_exists(state.chat_input):
        return

    prompt = (prompt or "").strip()
    if not prompt:
        return

    _clear_input_placeholder()
    try:
        current = _get_input_text().strip()
        if current:
            sep = "\n" if current.endswith("\n") else "\n\n"
            state.chat_input.insert(tk.END, sep + prompt)
        else:
            state.chat_input.insert(tk.END, prompt)
        state.chat_input.focus_set()
        _resize_input()
        _update_token_counter()
        _sync_text_placeholder(state.chat_input)
    except Exception as e:
        set_chat_status(t("chat_err_paste", e))


# Inter-module imports
from engine.gui.chat_window.engine.utils import (
    _now_ts,
    _now_full,
    _approx_tokens,
    _ai_display_name,
    _build_editor_compose_prompt,
)
from engine.gui.chat_window.engine.sessions import (
    _load_sessions,
    _save_sessions,
    _enforce_limits,
    _create_session_dict,
    _get_current_session,
    _update_session_title_if_needed,
    _messages_for_api,
)
from engine.gui.chat_window.engine.generation import _run_generation
from engine.gui.chat_window.ui_utils import (
    _c,
    _safe_after,
    _widget_exists,
    _set_dark_titlebar,
    _get_app_parent,
    _show_window,
    _call_and_break,
    _ask_simple_text,
    _make_button,
    _set_button_text,
    _set_button_state,
    _is_descendant,
    _get_widget_text,
    _select_all_widget,
    _paste_clipboard_into_widget,
    _copy_to_clipboard,
)
from engine.gui.chat_window.hotkeys import (
    _event_has_ctrl,
    _event_has_shift,
    _match_hotkey,
    _on_ctrl_keypress,
    _handle_text_ctrl,
    _handle_window_ctrl,
    _bind_window_hotkeys,
    _bind_text_hotkeys,
)
from engine.gui.chat_window.placeholders import (
    _create_placeholder_overlay,
    _sync_text_placeholder,
    _refresh_placeholder_state,
    _update_input_placeholder_text,
)
from engine.gui.chat_window.chat_scroll import (
    _is_chat_near_bottom,
    _scroll_chat_to_bottom,
    _show_new_message_indicator,
    _hide_new_message_indicator,
    _scroll_to_new_message,
    _chat_mousewheel,
)
from engine.gui.chat_window.chat_history import (
    _refresh_session_list,
    _on_session_select,
    new_chat,
    delete_current_chat,
    clear_chat_history,
)
from engine.gui.chat_window.chat_messages import (
    _add_message_bubble,
    _add_system_message,
    _resize_bubble_text,
    content_lines_estimate,
    _lighten_color,
    _selected_bubble_frame_get,
    _select_bubble,
    _on_bubble_text_click,
    _show_bubble_context_menu,
    _update_wraplengths,
    _render_current_session,
    _add_empty_state,
    _destroy_empty_state_if_any,
    _clear_messages_ui,
)
from engine.gui.chat_window.chat_typing import _show_typing, _animate_typing, _hide_typing
from engine.gui.chat_window.chat_actions import (
    _send_to_main_editor,
    _stop_generation,
    _set_generation_ui,
    improve_text_with_gpt,
    paste_from_editor,
    set_chat_status,
    append_chat_message,
)
from engine.gui.chat_window.chat_export import export_current_chat
from engine.gui.chat_window.chat_search import open_search
from engine.gui.chat_window.chat_settings import open_gpt_settings
from engine.gui.chat_window.chat_editor import (
    _show_editor_preview,
    _hide_editor_preview,
    open_editor_text_window,
    _get_selected_or_all_text,
    _show_editor_window,
)
from engine.gui.chat_window import init, open_chat_window
