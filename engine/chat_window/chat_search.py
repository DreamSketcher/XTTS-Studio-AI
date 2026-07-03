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

def open_search(event=None):


    if not _widget_exists(state._chat_window):
        return "break"

    if _widget_exists(state._search_window):
        _show_window(state._search_window)
        return "break"

    # Если открыто модальное окно настроек, временно снимаем grab,
    # чтобы поиск мог получить фокус.
    try:
        if state._root is not None:
            grab = state._root.grab_current()
            if grab is not None:
                grab.grab_release()
    except Exception:
        pass

    win = tk.Toplevel(state._chat_window)
    _set_dark_titlebar(win)
    state._search_window = win
    win.title("Поиск по истории")
    win.geometry("560x430")
    win.minsize(420, 300)
    win.configure(bg=_c("BG_DARK"))
    win.transient(state._chat_window)


    TkLabel(
        win,
        text="Поиск по истории чатов",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 12, "bold"),
    ).pack(anchor="w", padx=14, pady=(14, 6))

    TkLabel(
        win,
        text="Enter — поиск · Double click / Enter — открыть · Esc — закрыть · Ctrl+F — фокус в строке поиска",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MUTED"),
        font=("Segoe UI", 8),
    ).pack(anchor="w", padx=14, pady=(0, 10))

    entry = tk.Entry(
        win,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        insertbackground=_c("TEXT_MAIN"),
        relief="flat",
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
        highlightcolor=_c("ACCENT"),
        font=("Segoe UI", 10),
    )
    entry.pack(fill="x", padx=14, pady=(0, 10), ipady=7)

    frame = TkFrame(win, bg=_c("BORDER"), padx=1, pady=1)
    frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    scroll = tk.Scrollbar(frame)
    scroll.pack(side="right", fill="y")

    results = tk.Listbox(
        frame,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        selectbackground=_c("ACCENT"),
        selectforeground="#ffffff",
        activestyle="none",
        relief="flat",
        highlightthickness=0,
        font=("Segoe UI", 9),
        yscrollcommand=scroll.set,
    )
    results.pack(fill="both", expand=True)
    scroll.config(command=results.yview)

    status = TkLabel(
        win,
        text="Введите запрос",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        anchor="w",
    )
    status.pack(fill="x", padx=14, pady=(0, 10))

    state._search_results = []

    def do_search(event=None):


        query = entry.get().strip().lower()
        results.delete(0, tk.END)
        state._search_results = []

        if not query:
            status.config(text="Введите запрос")
            return "break"

        for s in state._sessions:
            title = s.get("title", "Новый чат")
            for idx, m in enumerate(s.get("messages", [])):
                content = m.get("content", "")
                role = "Вы" if m.get("role") == "user" else "AI"
                content_l = content.lower()
                title_l = title.lower()

                if query in content_l or query in title_l:
                    snippet = content.replace("\n", " ").strip()
                    if not snippet:
                        snippet = f"Совпадение в названии: {title}"
                    elif len(snippet) > 90:
                        pos = max(0, snippet.lower().find(query) - 20)
                        snippet = snippet[pos:pos + 90]
                    label = f"{title} · {m.get('ts', '')} · {role}: {snippet}"
                    results.insert(tk.END, label)
                    state._search_results.append((s.get("id"), idx))

        status.config(text=f"Найдено: {len(state._search_results)}")
        return "break"

    def open_result(event=None):


        sel = results.curselection()
        if not sel:
            if len(state._search_results) == 1:
                sel = (0,)
            else:
                return "break"

        idx = sel[0]
        if idx >= len(state._search_results):
            return "break"

        sid, _msg_idx = state._search_results[idx]
        state._current_session_id = sid
        _render_current_session()
        _refresh_session_list()
        set_chat_status("Открыт чат из результатов поиска")
        _show_window(state._chat_window)
        close_search()
        return "break"

    def focus_query(event=None):
        try:
            entry.focus_set()
            entry.select_range(0, tk.END)
            entry.icursor(tk.END)
        except Exception:
            pass
        return "break"

    def close_search(event=None):

        try:
            win.destroy()
        except Exception:
            pass
        state._search_window = None
        return "break"

    entry.bind("<Return>", do_search)
    entry.bind("<KeyRelease>", lambda e: do_search())
    _bind_text_hotkeys(entry, {"f": focus_query})

    results.bind("<Double-Button-1>", open_result)
    results.bind("<Return>", open_result)

    win.bind("<Control-Return>", do_search)
    win.bind("<Control-Shift-Return>", open_result)
    win.bind("<Escape>", close_search)
    _bind_window_hotkeys(win, {"f": focus_query})

    win.protocol("WM_DELETE_WINDOW", close_search)

    entry.focus_set()
    return "break"



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
from engine.gui.chat_window.chat_settings import open_gpt_settings
from engine.gui.chat_window.chat_editor import _show_editor_preview, _hide_editor_preview, open_editor_text_window, _get_selected_or_all_text, _show_editor_window
from engine.gui.chat_window import init, open_chat_window
