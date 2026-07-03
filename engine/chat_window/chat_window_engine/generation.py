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

def _run_generation(session: dict, prompt: str):
    """Запускает воркер генерации AI-ответа. prompt — то что уходит в API."""


    if state._generation_running:
        _stop_generation(silent=True)

    history_for_api = _messages_for_api(session)[:-1]

    cancel_event = threading.Event()
    token = str(uuid.uuid4())

    with state._generation_lock:
        state._generation_running = True
        state._generation_token = token
        state._generation_cancel_event = cancel_event

    _set_generation_ui(True)
    _show_typing()
    set_chat_status("AI печатает...")

    def _worker():
        try:
            import engine.gpt_client as _gpt

            system = _gpt._FREE_CHAT_SYSTEM if state._free_chat_mode else None
            response = _gpt.chat(prompt, history=history_for_api, system=system)

            if response is None:
                response = ""
            response = str(response)
            

            def _apply_response():


                if cancel_event.is_set() or token != state._generation_token:
                    return

                _hide_typing()

                assistant_msg = {
                    "role": "assistant",
                    "content": response,
                    "ts": _now_ts(),
                }

                s = _get_current_session()
                s.setdefault("messages", []).append(assistant_msg)
                _enforce_limits()
                _save_sessions()

                _add_message_bubble(assistant_msg, smooth_scroll=True, force_scroll=False)
                _refresh_session_list()
                _update_token_counter()
                # Скроллим вниз только если пользователь был у дна
                if _is_chat_near_bottom():
                    _safe_after(80, lambda: _scroll_chat_to_bottom(immediate=True) if (_widget_exists(state.chat_canvas) and _is_chat_near_bottom()) else None)

                with state._generation_lock:
                    state._generation_running = False
                    state._generation_token = None
                    state._generation_cancel_event = None

                _set_generation_ui(False)
                set_chat_status("Ответ получен")

            _safe_after(0, _apply_response)

        except Exception as e:
            import engine.gpt_client as _gpt
            is_unavailable = isinstance(e, getattr(_gpt, "AIUnavailable", ()))
            msg = str(e) or "Неизвестная ошибка"

            def _show_error():


                if cancel_event.is_set() or token != state._generation_token:
                    return

                _hide_typing()

                with state._generation_lock:
                    state._generation_running = False
                    state._generation_token = None
                    state._generation_cancel_event = None

                _set_generation_ui(False)

                if is_unavailable:
                    # ИИ временно недоступен (сеть или вся цепочка провайдеров) —
                    # это не баг, без messagebox, только статус.
                    set_chat_status("ИИ временно недоступен. Попробуйте позже.")
                else:
                    set_chat_status(f"Ошибка AI: {msg}")
                    messagebox.showerror("Ошибка AI", msg, parent=_get_app_parent() or state._root)

            _safe_after(0, _show_error)

        finally:
            def _final_cleanup():


                if token == state._generation_token and not cancel_event.is_set():
                    return

                if cancel_event.is_set():
                    _hide_typing()
                    with state._generation_lock:
                        if token == state._generation_token:
                            state._generation_running = False
                            state._generation_token = None
                            state._generation_cancel_event = None
                    _set_generation_ui(False)

            _safe_after(0, _final_cleanup)

    threading.Thread(target=_worker, daemon=True).start()



# Inter-module imports
from engine.gui.chat_window.chat_window_engine.utils import _now_ts, _now_full, _approx_tokens, _ai_display_name, _build_editor_compose_prompt
from engine.gui.chat_window.chat_window_engine.sessions import _load_sessions, _save_sessions, _enforce_limits, _create_session_dict, _get_current_session, _update_session_title_if_needed, _messages_for_api
from engine.gui.chat_window.ui_utils import _c, _safe_after, _widget_exists, _set_dark_titlebar, _get_app_parent, _show_window, _call_and_break, _ask_simple_text, _make_button, _set_button_text, _set_button_state, _is_descendant, _get_widget_text, _select_all_widget, _paste_clipboard_into_widget, _copy_to_clipboard
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
