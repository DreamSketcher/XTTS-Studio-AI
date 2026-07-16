from __future__ import annotations
import json
from engine.atomic_write import atomic_write_json
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

# i18n: дефолтное название сессии "Новый чат" и сообщение об ошибке сохранения
# истории показываются пользователю (в списке сессий / статус-баре), поэтому
# должны переключаться вместе с языком интерфейса, а не быть захардкожены.
from i18n import t


def _load_sessions():

    if state._sessions_loaded:
        return

    state._sessions_loaded = True
    state._sessions = []

    try:
        if os.path.exists(state.HISTORY_FILE):
            with open(state.HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_sessions = data.get("sessions", [])
            if isinstance(raw_sessions, list):
                for s in raw_sessions[: state.MAX_SESSIONS]:
                    if not isinstance(s, dict):
                        continue

                    sid = str(s.get("id") or uuid.uuid4())
                    title = str(s.get("title") or t("chat_new_chat_title"))
                    created = str(s.get("created") or _now_full())

                    messages = []
                    for m in s.get("messages", [])[: state.MAX_MESSAGES_PER_SESSION]:
                        if not isinstance(m, dict):
                            continue
                        role = m.get("role", "assistant")
                        content = m.get("content", "")
                        ts = m.get("ts", "")
                        if role not in ("user", "assistant", "system"):
                            role = "assistant"
                        messages.append(
                            {
                                "role": role,
                                "content": str(content),
                                "ts": str(ts or _now_ts()),
                            }
                        )

                    state._sessions.append(
                        {
                            "id": sid,
                            "title": title[:80],
                            "created": created,
                            "messages": messages,
                        }
                    )
    except Exception:
        state._sessions = []

    if not state._sessions:
        state._sessions.append(_create_session_dict())

    _enforce_limits()
    state._current_session_id = state._sessions[0]["id"]


def _save_sessions():
    try:
        _enforce_limits()
        data = {"sessions": state._sessions}
        tmp_path = state.HISTORY_FILE + ".tmp"
        atomic_write_json(tmp_path, data, ensure_ascii=False, indent=2)
        os.replace(tmp_path, state.HISTORY_FILE)
    except Exception as e:
        set_chat_status(t("chat_err_save_history", e))


def _enforce_limits():

    for s in state._sessions:
        msgs = s.get("messages", [])
        if len(msgs) > state.MAX_MESSAGES_PER_SESSION:
            s["messages"] = msgs[-state.MAX_MESSAGES_PER_SESSION :]

    if len(state._sessions) > state.MAX_SESSIONS:
        state._sessions = state._sessions[: state.MAX_SESSIONS]


def _create_session_dict() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "title": t("chat_new_chat_title"),
        "created": _now_full(),
        "messages": [],
    }


def _get_current_session() -> dict:

    _load_sessions()

    for s in state._sessions:
        if s.get("id") == state._current_session_id:
            return s

    if state._sessions:
        state._current_session_id = state._sessions[0]["id"]
        return state._sessions[0]

    s = _create_session_dict()
    state._sessions.append(s)
    state._current_session_id = s["id"]
    return s


def _update_session_title_if_needed(session: dict):
    if session.get("title") and session.get("title") != t("chat_new_chat_title"):
        return

    for m in session.get("messages", []):
        if m.get("role") == "user" and m.get("content", "").strip():
            title = m["content"].strip().replace("\n", " ")
            session["title"] = title[:40] if len(title) > 40 else title
            return


def _messages_for_api(session: dict) -> list[dict]:
    result = []
    for m in session.get("messages", []):
        if m.get("role") in ("user", "assistant"):
            result.append(
                {
                    "role": m.get("role", "assistant"),
                    "content": m.get("content", ""),
                }
            )
    return result


# Inter-module imports
from engine.gui.chat_window.services.utils import (
    _now_ts,
    _now_full,
    _approx_tokens,
    _ai_display_name,
    _build_editor_compose_prompt,
)
from engine.gui.chat_window.services.generation import _run_generation
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
from engine.gui.chat_window.chat_input import (
    _focus_chat_input,
    _reset_editor_mode,
    _input_has_placeholder,
    _set_input_placeholder,
    _clear_input_placeholder,
    _get_input_text,
    _clear_input_text,
    _resize_input,
    _update_token_counter,
    _paste_into_input,
    _on_input_focus_in,
    _on_input_focus_out,
    _on_input_key_release,
    _on_enter,
    _submit_prompt,
    send_chat_message,
    _insert_prompt_into_chat_input,
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
