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

def _show_editor_preview(text: str):


    if not _widget_exists(state.composer_outer_ref[0]):
        state._editor_preview_content = text
        return

    if _widget_exists(state._editor_preview_frame):
        try:
            state._editor_preview_frame.destroy()
        except Exception:
            pass
    state._editor_preview_frame = None
    state._editor_preview_text = None
    state._editor_preview_content = text

    # ВАЖНО: чистый tk.Frame, не TkFrame
    state._editor_preview_frame = tk.Frame(
        state.composer_outer_ref[0],
        bg=_c("BG_CARD"),
        highlightthickness=1,
        highlightbackground=_c("ACCENT"),
    )
    state._editor_preview_frame.pack(fill="x", before=state.composer_card_ref[0], pady=(0, 4))

    header = tk.Frame(state._editor_preview_frame, bg=_c("BG_CARD"))
    header.pack(fill="x", padx=10, pady=(6, 3))

    tk.Label(
        header,
        text="📋 Текст из редактора",
        bg=_c("BG_CARD"),
        fg=_c("ACCENT"),
        font=("Segoe UI", 8, "bold"),
        anchor="w",
    ).pack(side="left")

    tk.Button(
        header,
        text="✕",
        command=lambda: (_hide_editor_preview(), _reset_editor_mode()),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        activebackground=_c("BG_CARD"),
        activeforeground=_c("TEXT_MAIN"),
        relief="flat", bd=0,
        font=("Segoe UI", 8),
        cursor="hand2",
        padx=4, pady=0,
    ).pack(side="right")

    preview_border = tk.Frame(
        state._editor_preview_frame,
        bg=_c("BORDER"),
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
    )
    preview_border.pack(fill="x", padx=10, pady=(0, 8))

    preview_inner = tk.Frame(preview_border, bg=_c("BG_INPUT"))
    preview_inner.pack(fill="x")

    def _sync_preview_content(event=None):

        try:
            state._editor_preview_content = state._editor_preview_text.get("1.0", "end-1c")
        except Exception:
            pass

    state._editor_preview_text = tk.Text(
        preview_inner,
        height=4,
        wrap="word",
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        insertbackground=_c("TEXT_MAIN"),
        relief="flat",
        highlightthickness=0,
        font=("Segoe UI", 9),
        padx=8, pady=6,
        undo=True,
    )
    state._editor_preview_text.insert("1.0", text)
    state._editor_preview_text.pack(fill="x")
    state._editor_preview_text.bind("<KeyRelease>", _sync_preview_content)
    _bind_text_hotkeys(state._editor_preview_text)

    _safe_after(0, _focus_chat_input)
    _safe_after(100, _focus_chat_input)


def _hide_editor_preview():

    if _widget_exists(state._editor_preview_frame):
        try:
            state._editor_preview_frame.destroy()
        except Exception:
            pass
    state._editor_preview_frame = None
    state._editor_preview_text = None
    state._editor_preview_content = ""


def open_editor_text_window(event=None):



    if state._get_text is None or state._set_text is None:
        messagebox.showerror(
            "Ошибка",
            "Функции доступа к редактору не инициализированы.",
            parent=_get_app_parent() or state._root,
        )
        return "break"

    if _widget_exists(state._editor_window):
        _show_window(state._editor_window)
        return "break"

    try:
        text = state._get_text()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось получить текст из редактора: {e}", parent=_get_app_parent() or state._root)
        return "break"

    if not text or text == state._placeholder or not text.strip():
        messagebox.showwarning("Пустой текст", "В редакторе нет текста.", parent=_get_app_parent() or state._root)
        return "break"

    win = tk.Toplevel(_get_app_parent() or state._root)
    _set_dark_titlebar(win)
    state._editor_window = win
    win.title("📋 Текст из редактора")
    win.geometry("900x720")
    win.minsize(700, 560)
    win.resizable(True, True)
    win.configure(bg=_c("BG_DARK"))
    win.transient(_get_app_parent() or state._root)

    main = TkFrame(win, bg=_c("BG_DARK"))
    main.pack(fill="both", expand=True, padx=14, pady=14)

    TkLabel(
        main,
        text="Текст из редактора",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 14, "bold"),
        anchor="w",
    ).pack(fill="x")

    TkLabel(
        main,
        text="Выделите фрагмент сверху и нажмите «В редактор». Ниже можно написать комментарий для AI.",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        anchor="w",
        justify="left",
    ).pack(fill="x", pady=(4, 8))

    TkLabel(
        main,
        text="Enter — отправить и закрыть · Shift+Enter — новая строка · Ctrl+Enter — отправить и закрыть · Ctrl+Shift+Enter — вставить в поле ввода · Ctrl+F — поиск",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MUTED"),
        font=("Segoe UI", 8),
        anchor="w",
        justify="left",
    ).pack(fill="x", pady=(0, 10))

    panes = tk.PanedWindow(
        main,
        orient="vertical",
        bg=_c("BG_DARK"),
        sashrelief="flat",
        sashwidth=8,
        bd=0,
        opaqueresize=True,
    )
    panes.pack(fill="both", expand=True)

    # Source card
    source_card = TkFrame(
        panes,
        bg=_c("BG_CARD"),
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
    )

    src_header = TkFrame(source_card, bg=_c("BG_CARD"))
    src_header.pack(fill="x", padx=12, pady=(10, 8))

    TkLabel(
        src_header,
        text="Источник",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 10, "bold"),
    ).pack(side="left")

    def refresh_source():
        if state._get_text is None:
            return
        try:
            src = state._get_text()
            if not src or src == state._placeholder or not src.strip():
                messagebox.showwarning("Пустой текст", "В редакторе нет текста.", parent=win)
                return
            state.editor_source_text.delete("1.0", tk.END)
            state.editor_source_text.insert("1.0", src)
            _update_editor_stats()
            set_chat_status("Источник обновлён из редактора")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обновить текст: {e}", parent=win)

    def copy_source():
        selected = _get_selected_or_all_text(state.editor_source_text)
        if not selected.strip():
            return
        _copy_to_clipboard(selected)

    def overwrite_editor_from_selection():
        if state._set_text is None:
            return
        selected = _get_selected_or_all_text(state.editor_source_text).strip()
        if not selected:
            messagebox.showwarning("Пустое выделение", "Выделите фрагмент текста в верхнем окне.", parent=win)
            return
        try:
            state._set_text(selected)
            append_chat_message("system", f"Редактор перезаписан выделенным фрагментом ({len(selected)} символов)")
            set_chat_status("Редактор перезаписан выделением")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось перезаписать редактор: {e}", parent=win)

    src_btn_row = TkFrame(src_header, bg=_c("BG_CARD"))
    src_btn_row.pack(side="right")

    _make_button(
        src_btn_row,
        "⟳",
        refresh_source,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        width=3,
        padx=6,
        pady=2,
    ).pack(side="left", padx=(0, 5))

    _make_button(
        src_btn_row,
        "📎",
        copy_source,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        width=3,
        padx=6,
        pady=2,
    ).pack(side="left", padx=(0, 5))

    _make_button(
        src_btn_row,
        "↩ В редактор",
        overwrite_editor_from_selection,
        bg=_c("BG_ACTIVE"),
        font_size=8,
        height=1,
        padx=7,
        pady=2,
    ).pack(side="left")

    source_body = TkRawFrame(source_card, bg=_c("BORDER"),
                          highlightthickness=1, highlightbackground=_c("BORDER"))
    source_inner = TkRawFrame(source_body, bg=_c("BG_INPUT"))
    comment_body = TkRawFrame(comment_send_row, bg=_c("BORDER"),
                            highlightthickness=1, highlightbackground=_c("BORDER"))
    comment_inner = TkRawFrame(comment_body, bg=_c("BG_INPUT"))

    src_scroll = tk.Scrollbar(source_inner)
    src_scroll.pack(side="right", fill="y")

    state.editor_source_text = tk.Text(
        source_inner,
        wrap="word",
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        insertbackground=_c("TEXT_MAIN"),
        relief="flat",
        highlightthickness=0,
        font=("Segoe UI", 10),
        padx=10,
        pady=10,
        undo=True,
        yscrollcommand=src_scroll.set,
    )
    state.editor_source_text.pack(fill="both", expand=True)
    state.editor_source_text.lift() 
    src_scroll.config(command=state.editor_source_text.yview)

    state.editor_source_text.insert("1.0", text)

    # Comment card
    comment_card = TkFrame(
        panes,
        bg=_c("BG_CARD"),
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
    )

    comment_header = TkFrame(comment_card, bg=_c("BG_CARD"))
    comment_header.pack(fill="x", padx=12, pady=(10, 8))

    TkLabel(
        comment_header,
        text="Комментарий к тексту",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 10, "bold"),
    ).pack(side="left")

    TkLabel(
        comment_header,
        text="Что сделать с текстом?",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 8),
        anchor="e",
    ).pack(side="right")

    comment_send_row = TkFrame(comment_card, bg=_c("BG_CARD"))
    comment_send_row.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    comment_body = TkFrame(comment_send_row, bg=_c("BORDER"), padx=1, pady=1)
    comment_body.pack(side="left", fill="both", expand=True)

    comment_inner = TkFrame(comment_body, bg=_c("BG_INPUT"))
    comment_inner.pack(fill="both", expand=True)

    comment_scroll = tk.Scrollbar(comment_inner)
    comment_scroll.pack(side="right", fill="y")

    state.editor_comment_text = tk.Text(
        comment_inner,
        wrap="word",
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        insertbackground=_c("TEXT_MAIN"),
        relief="flat",
        highlightthickness=0,
        font=("Segoe UI", 10),
        padx=10,
        pady=10,
        undo=True,
        height=5,
        yscrollcommand=comment_scroll.set,
    )
    state.editor_comment_text.pack(fill="both", expand=True)
    comment_scroll.config(command=state.editor_comment_text.yview)

    _create_placeholder_overlay(
        comment_inner,
        state.editor_comment_text,
        "Комментарий к тексту…",
        x=13,
        y=11,
        fg=_c("TEXT_DIM"),
        bg=_c("BG_INPUT"),
        font=("Segoe UI", 9, "italic"),
    )

    send_side = TkFrame(comment_send_row, bg=_c("BG_CARD"))
    send_side.pack(side="left", fill="y", padx=(6, 0))

    panes.add(source_card, minsize=250)
    panes.add(comment_card, minsize=180)

    # Stats + status
    info_row = TkFrame(main, bg=_c("BG_DARK"))
    info_row.pack(fill="x", pady=(10, 8))

    state.editor_stats_label = TkLabel(
        info_row,
        text="Источник: 0 симв. · Комментарий: 0 симв. · Итого: 0 симв.",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 8),
        anchor="w",
    )
    state.editor_stats_label.pack(side="left", fill="x", expand=True)

    state.editor_status_label = TkLabel(
        info_row,
        text="Enter — отправить и закрыть · Esc — закрыть",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MUTED"),
        font=("Segoe UI", 8),
        anchor="e",
    )
    state.editor_status_label.pack(side="right")

    btn_row = TkFrame(main, bg=_c("BG_DARK"))
    btn_row.pack(fill="x")

    def build_prompt() -> str:
        return _build_editor_compose_prompt(
            _get_widget_text(state.editor_source_text),
            _get_widget_text(state.editor_comment_text),
        )

    def close_editor():

        try:
            win.destroy()
        except Exception:
            pass
        state._editor_window = None
        state.editor_source_text = None
        state.editor_comment_text = None
        state.editor_stats_label = None
        state.editor_status_label = None

    def insert_into_chat_input():
        prompt = build_prompt()
        if not prompt.strip():
            messagebox.showwarning("Пустой текст", "Источник и комментарий пустые.", parent=win)
            return "break"
        _insert_prompt_into_chat_input(prompt)
        set_chat_status("Текст вставлен в поле ввода")
        return "break"

    def send_to_chat(close_after: bool = True):
        prompt = build_prompt()
        if not prompt.strip():
            messagebox.showwarning("Пустой текст", "Источник и комментарий пустые.", parent=win)
            return "break"
        send_chat_message(prompt)
        set_chat_status("Текст отправлен в чат")
        if close_after:
            close_editor()
        return "break"

    _make_button(
        send_side,
        "➤",
        lambda: send_to_chat(True),
        bg=_c("BG_ACTIVE"),
        font_size=12,
        width=3,
        height=3,
        padx=6,
        pady=4,
    ).pack(fill="y", expand=True)

    def improve_source_text():
        """Улучшить текст из source через improve_for_tts (с авто-fallback на слабую модель)."""
        src = _get_widget_text(state.editor_source_text).strip()
        if not src:
            messagebox.showwarning("Пустой текст", "Нет текста в верхнем окне.", parent=win)
            return

        _set_button_state(improve_editor_btn, "disabled")
        if _widget_exists(state.editor_status_label):
            try:
                state.editor_status_label.config(text="Улучшаю текст… (авто-fallback при лимите)")
            except Exception:
                pass

        def _worker():
            try:
                import engine.gpt_client as _gpt
                result = _gpt.improve_for_tts(src)

                def _apply():
                    if _widget_exists(state.editor_source_text):
                        state.editor_source_text.delete("1.0", tk.END)
                        state.editor_source_text.insert("1.0", result or "")
                    _update_editor_stats()
                    _set_button_state(improve_editor_btn, "normal")
                    if _widget_exists(state.editor_status_label):
                        try:
                            state.editor_status_label.config(
                                text=f"Готово: {len(src)} → {len(result or '')} симв."
                            )
                        except Exception:
                            pass

                _safe_after(0, _apply)

            except Exception as e:
                msg = str(e) or "Неизвестная ошибка"

                def _show_err():
                    _set_button_state(improve_editor_btn, "normal")
                    if _widget_exists(state.editor_status_label):
                        try:
                            state.editor_status_label.config(text=f"Ошибка: {msg[:80]}")
                        except Exception:
                            pass
                    messagebox.showerror("Ошибка AI", msg, parent=win)

                _safe_after(0, _show_err)

        threading.Thread(target=_worker, daemon=True).start()

    improve_editor_btn = _make_button(
        btn_row,
        "✨ Улучшить",
        improve_source_text,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        padx=8,
        pady=3,
    )
    improve_editor_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

    _make_button(
        btn_row,
        "➤ Отправить",
        lambda: send_to_chat(True),
        bg=_c("BG_ACTIVE"),
        font_size=8,
        height=1,
        padx=8,
        pady=3,
    ).pack(side="left", fill="x", expand=True, padx=(0, 6))

    _make_button(
        btn_row,
        "↪ В поле ввода",
        insert_into_chat_input,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        padx=8,
        pady=3,
    ).pack(side="left", fill="x", expand=True, padx=(0, 6))

    _make_button(
        btn_row,
        "✕ Закрыть",
        close_editor,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        padx=8,
        pady=3,
    ).pack(side="left", fill="x", expand=True)

    def _update_editor_stats():
        if not _widget_exists(state.editor_stats_label):
            return
        src = _get_widget_text(state.editor_source_text)
        cmt = _get_widget_text(state.editor_comment_text)
        total = len((src or "").strip()) + len((cmt or "").strip())
        try:
            state.editor_stats_label.config(
                text=f"Источник: {len(src)} симв. · Комментарий: {len(cmt)} симв. · Итого: {total} симв."
            )
        except Exception:
            pass
        _sync_text_placeholder(state.editor_comment_text)

    def _ctrl_send(event=None):
        if event is not None and _event_has_shift(event):
            return None
        return send_to_chat(True)

    def _ctrl_shift_insert(event=None):
        return insert_into_chat_input()

    def _ctrl_search(event=None):
        return open_search(event)

    def _ctrl_overwrite(event=None):
        overwrite_editor_from_selection()
        return "break"

    def _escape(event=None):
        close_editor()
        return "break"

    def _comment_enter(event):
        if _event_has_shift(event):
            return None
        return send_to_chat(True)

    extra_handlers = {
        "f": _ctrl_search,
        "r": _ctrl_overwrite,
    }

    state.editor_source_text.bind("<KeyRelease>", lambda e: _update_editor_stats())
    state.editor_comment_text.bind("<FocusIn>", lambda e: _sync_text_placeholder(state.editor_comment_text))
    state.editor_comment_text.bind("<FocusOut>", lambda e: _sync_text_placeholder(state.editor_comment_text))
    state.editor_comment_text.bind("<KeyRelease>", lambda e: _update_editor_stats())
    state.editor_comment_text.bind("<Return>", _comment_enter)

    _bind_text_hotkeys(state.editor_source_text, extra_handlers)
    _bind_text_hotkeys(state.editor_comment_text, extra_handlers)

    win.bind("<Control-Return>", _ctrl_send)
    win.bind("<Control-Shift-Return>", _ctrl_shift_insert)
    win.bind("<Escape>", _escape)

    _bind_window_hotkeys(win, {
        "f": _ctrl_search,
        "r": _ctrl_overwrite,
    })

    win.protocol("WM_DELETE_WINDOW", close_editor)

    _update_editor_stats()
    _show_window(win)
    try:
        state.editor_comment_text.focus_set()
    except Exception:
        pass

    return "break"


def _get_selected_or_all_text(text_widget) -> str:
    if not _widget_exists(text_widget):
        return ""
    try:
        return text_widget.get("sel.first", "sel.last")
    except Exception:
        try:
            return text_widget.get("1.0", "end-1c")
        except Exception:
            return ""


def _show_editor_window():
    return open_editor_text_window()


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
from engine.gui.chat_window.chat_typing import _show_typing, _animate_typing, _hide_typing
from engine.gui.chat_window.chat_actions import _send_to_main_editor, _stop_generation, _set_generation_ui, improve_text_with_gpt, paste_from_editor, set_chat_status, append_chat_message
from engine.gui.chat_window.chat_export import export_current_chat
from engine.gui.chat_window.chat_search import open_search
from engine.gui.chat_window.chat_settings import open_gpt_settings
from engine.gui.chat_window import init, open_chat_window
