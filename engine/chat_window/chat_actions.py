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

def _send_to_main_editor(content: str):
    if state._set_text is None or not content.strip():
        return
    try:
        state._set_text(content.strip())
        append_chat_message("system", f"Текст отправлен в редактор ({len(content.strip())} симв.)")
        set_chat_status("✅ Текст отправлен в редактор TTS")
    except Exception as e:
        set_chat_status(f"Ошибка: {e}")


def _stop_generation(silent: bool = False):


    with state._generation_lock:
        if state._generation_cancel_event is not None:
            try:
                state._generation_cancel_event.set()
            except Exception:
                pass
        state._generation_running = False
        state._generation_token = None
        state._generation_cancel_event = None

    _hide_typing()
    _set_generation_ui(False)

    if not silent:
        set_chat_status("Генерация остановлена")


def _set_generation_ui(running: bool):
    # Кнопка отправки/стоп
    if _widget_exists(state.chat_send_btn):
        try:
            state.chat_send_btn.config(
                text="⏹" if running else "➤",
                command=lambda: _stop_generation() if running else send_chat_message(),
            )
        except Exception:
            pass

    state = "disabled" if running else "normal"
    for btn in (state.improve_btn, state.paste_editor_btn, state.clear_btn,
                state.export_btn, state.settings_btn, state.new_chat_btn, state.delete_chat_btn):
        _set_button_state(btn, state)


def improve_text_with_gpt():
    if state._use_gpt_var is not None and not state._use_gpt_var.get():
        messagebox.showwarning(
            "AI edit выключен",
            "Включите флажок ✨ AI edit в главном окне.",
            parent=_get_app_parent() or state._root,
        )
        return
    
    try:
        raw = state._get_text()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось получить текст из редактора: {e}", parent=_get_app_parent() or state._root)
        return

    if not raw or raw == state._placeholder or not raw.strip():
        messagebox.showwarning("Пустой текст", "Текст в редакторе пустой.", parent=_get_app_parent() or state._root)
        return

    _set_button_state(state.improve_btn, "disabled")
    _set_button_state(state.chat_send_btn, "disabled")
    set_chat_status("Улучшаю текст для TTS...")

    def _worker():
        try:
            import engine.gpt_client as _gpt
            result = _gpt.improve_for_tts(raw)
            result = "" if result is None else str(result)

            def _apply():
                try:
                    state._set_text(result)
                    append_chat_message(
                        "system",
                        f"Текст улучшен для TTS: {len(raw)} → {len(result)} символов",
                    )
                    set_chat_status("Текст обновлён в редакторе")
                except Exception as e:
                    messagebox.showerror(
                        "Ошибка",
                        f"Не удалось вставить результат в редактор: {e}",
                        parent=_get_app_parent() or state._root,
                    )
                    set_chat_status("Ошибка вставки результата")
                finally:
                    _set_button_state(state.improve_btn, "normal")
                    _set_button_state(state.chat_send_btn, "normal")

            _safe_after(0, _apply)

        except Exception as e:
            msg = str(e) or "Неизвестная ошибка"

            def _show_error():
                _set_button_state(state.improve_btn, "normal")
                _set_button_state(state.chat_send_btn, "normal")
                set_chat_status(f"Ошибка улучшения текста: {msg}")
                messagebox.showerror("Ошибка AI", msg, parent=_get_app_parent() or state._root)

            _safe_after(0, _show_error)

    threading.Thread(target=_worker, daemon=True).start()


def paste_from_editor():
    if state._get_text is None:
        return
    try:
        text = state._get_text()
    except Exception:
        return
    if not text or text == state._placeholder or not text.strip():
        set_chat_status("Редактор пуст")
        return

    state._editor_mode = True

    _show_editor_preview(text)
    _update_input_placeholder_text("Добавьте комментарий… или нажмите Enter чтобы отправить как есть")
    if state._hint_text_var is not None:
        try:
            state._hint_text_var.set("Enter — отправить · Ctrl+Enter — без комментария · ✕ — отмена")
        except Exception:
            pass
    set_chat_status("Текст из редактора готов · добавьте комментарий или нажмите Enter")

    # Жёстко переводим фокус в поле ввода чата с несколькими попытками,
    # т.к. pack(before=...) в _show_editor_preview меняет геометрию
    # и фокус может временно "зависать" на других виджетах.
    _focus_chat_input()
    _safe_after(200, _focus_chat_input)


def set_chat_status(message: str):
    if not _widget_exists(state.chat_status_label):
        return
    try:
        state.chat_status_label.config(text=message)
    except Exception:
        pass


def append_chat_message(role: str, message: str):
    session = _get_current_session()
    entry = {
        "role": role if role in ("user", "assistant", "system") else "assistant",
        "content": message or "",
        "ts": _now_ts(),
    }
    session.setdefault("messages", []).append(entry)
    _enforce_limits()
    _update_session_title_if_needed(session)
    _save_sessions()

    if _is_chat_near_bottom():
        _safe_after(150, lambda: _scroll_chat_to_bottom(immediate=False))
        _hide_new_message_indicator()
    elif role == "assistant":
        _show_new_message_indicator()

    _refresh_session_list()
    _update_token_counter()



# Inter-module imports
from engine.gui.chat_window.chat_window_engine.utils import _now_ts, _now_full, _approx_tokens, _ai_display_name, _build_editor_compose_prompt
from engine.gui.chat_window.chat_window_engine.sessions import _load_sessions, _save_sessions, _enforce_limits, _create_session_dict, _get_current_session, _update_session_title_if_needed, _messages_for_api
from engine.gui.chat_window.chat_window_engine.generation import _run_generation
from engine.gui.chat_window.ui_utils import _c, _safe_after, _widget_exists, _set_dark_titlebar, _get_app_parent, _show_window, _call_and_break, _ask_simple_text, _make_button, _set_button_text, _set_button_state, _is_descendant, _get_widget_text, _select_all_widget, _paste_clipboard_into_widget, _copy_to_clipboard
from engine.gui.chat_window.hotkeys import _event_has_ctrl, _event_has_shift, _match_hotkey, _on_ctrl_keypress, _handle_text_ctrl, _handle_window_ctrl, _bind_window_hotkeys, _bind_text_hotkeys
from engine.gui.chat_window.placeholders import _create_placeholder_overlay, _sync_text_placeholder, _refresh_placeholder_state, _update_input_placeholder_text
from engine.gui.chat_window.chat_scroll import _is_chat_near_bottom, _scroll_chat_to_bottom, _show_new_message_indicator, _hide_new_message_indicator, _scroll_to_new_message, _chat_mousewheel
from engine.gui.chat_window.chat_history import _refresh_session_list, _on_session_select, new_chat, delete_current_chat, clear_chat_history
from engine.gui.chat_window.chat_messages import _add_message_bubble, _add_system_message, _resize_bubble_text, content_lines_estimate, _lighten_color, _selected_bubble_frame_get, _select_bubble, _on_bubble_text_click, _show_bubble_context_menu, _update_wraplengths, _render_current_session, _add_empty_state, _destroy_empty_state_if_any, _clear_messages_ui
from engine.gui.chat_window.chat_input import _focus_chat_input, _reset_editor_mode, _input_has_placeholder, _set_input_placeholder, _clear_input_placeholder, _get_input_text, _clear_input_text, _resize_input, _update_token_counter, _paste_into_input, _on_input_focus_in, _on_input_focus_out, _on_input_key_release, _on_enter, _submit_prompt, send_chat_message, _insert_prompt_into_chat_input
from engine.gui.chat_window.chat_typing import _show_typing, _animate_typing, _hide_typing
from engine.gui.chat_window.chat_export import export_current_chat
from engine.gui.chat_window.chat_search import open_search
from engine.gui.chat_window.chat_settings import open_gpt_settings
from engine.gui.chat_window.chat_editor import _show_editor_preview, _hide_editor_preview, open_editor_text_window, _get_selected_or_all_text, _show_editor_window
from engine.gui.chat_window import init, open_chat_window
