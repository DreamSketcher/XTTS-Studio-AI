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


def init(root, colors, create_button_fn, get_text_fn, set_text_fn, placeholder, use_gpt_var=None):

    state._root = root
    state._colors = colors
    state._create_button = create_button_fn
    state._get_text = get_text_fn
    state._set_text = set_text_fn
    state._placeholder = placeholder
    state._use_gpt_var = use_gpt_var
    _load_sessions()


def open_chat_window():

    if state._root is None:
        raise RuntimeError("chat_window.init(...) must be called before open_chat_window().")

    _load_sessions()

    if _widget_exists(state._chat_window):
        _show_window(state._chat_window)
        return

    win = tk.Toplevel(state._root)
    win.title("💬 AI Чат — XTTS Studio")
    win.geometry("920x650")
    win.minsize(520, 540)
    win.resizable(True, True)
    win.configure(bg=_c("BG_DARK"))
    _set_dark_titlebar(win)

    state._chat_window = win

    # Root layout
    main = TkFrame(win, bg=_c("BG_DARK"))
    main.pack(fill="both", expand=True)

    # Sidebar
    sidebar = TkFrame(main, bg=_c("BG_CARD"), width=220)
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)

    TkLabel(
        sidebar,
        text="XTTS AI",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 13, "bold"),
        anchor="w",
    ).pack(fill="x", padx=12, pady=(14, 8))

    state.new_chat_btn = _make_button(
        sidebar,
        "＋ Новый чат",
        new_chat,
        bg=_c("BG_ACTIVE"),
        font_size=8,
        height=1,
        padx=8,
        pady=3,
    )
    state.new_chat_btn.pack(fill="x", padx=10, pady=(0, 6))

    state.delete_chat_btn = _make_button(
        sidebar,
        "🗑 Удалить чат",
        delete_current_chat,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        padx=8,
        pady=3,
    )
    state.delete_chat_btn.pack(fill="x", padx=10, pady=(0, 10))

    TkLabel(
        sidebar,
        text="Поиск: Ctrl+F",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MUTED"),
        font=("Segoe UI", 8),
        anchor="w",
    ).pack(fill="x", padx=12, pady=(0, 8))

    list_outer = TkFrame(sidebar, bg=_c("BORDER"), padx=1, pady=1)
    list_outer.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    list_scroll = tk.Scrollbar(list_outer)
    list_scroll.pack(side="right", fill="y")

    state.session_listbox = tk.Listbox(
        list_outer,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        selectbackground=_c("ACCENT"),
        selectforeground="#ffffff",
        activestyle="none",
        relief="flat",
        highlightthickness=0,
        font=("Segoe UI", 9),
        yscrollcommand=list_scroll.set,
    )
    state.session_listbox.pack(fill="both", expand=True)
    list_scroll.config(command=state.session_listbox.yview)
    state.session_listbox.bind("<<ListboxSelect>>", _on_session_select)

    # Chat area
    right = TkFrame(main, bg=_c("BG_DARK"))
    right.pack(side="left", fill="both", expand=True)

    header = TkFrame(right, bg=_c("BG_DARK"))
    header.pack(side="top", fill="x", padx=14, pady=(12, 8))

    TkLabel(
        header,
        text="AI Чат",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 14, "bold"),
    ).pack(side="left")

    scroll_bottom_btn = _make_button(
        header,
        "↓ Вниз",
        lambda: _scroll_chat_to_bottom(immediate=True),
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        padx=8,
        pady=2,
    )
    scroll_bottom_btn.pack(side="right", padx=(8, 0))

    state.export_btn = _make_button(
        header,
        "⬇ Экспорт",
        export_current_chat,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        padx=8,
        pady=2,
    )
    state.export_btn.pack(side="right", padx=(8, 0))

    state.settings_btn = _make_button(
        header,
        "⚙ Настройки",
        open_gpt_settings,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        padx=8,
        pady=2,
    )
    state.settings_btn.pack(side="right", padx=(8, 0))

    # Status row — bottom
    status_row = TkFrame(right, bg=_c("BG_DARK"))
    status_row.pack(side="bottom", fill="x", padx=14, pady=(0, 6))

    state.chat_status_label = TkLabel(
        status_row,
        text="Готов к работе",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        anchor="w",
    )
    state.chat_status_label.pack(side="left", fill="x", expand=True)

    state.chat_token_label = TkLabel(
        status_row,
        text="Ввод: ≈0 ток. · Чат: ≈0 ток.",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        anchor="e",
    )
    state.chat_token_label.pack(side="right")

    # Actions — bottom
    action_row = TkFrame(right, bg=_c("BG_DARK"))
    action_row.pack(side="bottom", fill="x", padx=14, pady=(0, 6))

    state.improve_btn = CTkButton(
        action_row,
        text="✨ Улучшить",
        command=improve_text_with_gpt,
        fg_color=_c("BG_INPUT"),
        text_color=_c("TEXT_MAIN"),
        hover_color=_c("BORDER"),
        corner_radius=10,
        height=40,
        font=("Segoe UI", 13),
        cursor="hand2",
    )
    state.improve_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

    state.paste_editor_btn = CTkButton(
        action_row,
        text="📋 Из редактора",
        command=paste_from_editor,
        fg_color=_c("BG_INPUT"),
        text_color=_c("TEXT_MAIN"),
        hover_color=_c("BORDER"),
        corner_radius=10,
        height=40,
        font=("Segoe UI", 13),
        cursor="hand2",
    )
    state.paste_editor_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

    state.clear_btn = CTkButton(
        action_row,
        text="🧹 Очистить",
        command=clear_chat_history,
        fg_color=_c("BG_INPUT"),
        text_color=_c("TEXT_MAIN"),
        hover_color=_c("BORDER"),
        corner_radius=10,
        height=40,
        font=("Segoe UI", 13),
        cursor="hand2",
    )
    state.clear_btn.pack(side="left", fill="x", expand=True)

    # Input card — bottom
    composer_outer = TkFrame(right, bg=_c("BG_DARK"))
    composer_outer.pack(side="bottom", fill="x", padx=14, pady=(0, 14))
    state.composer_outer_ref = [composer_outer]

    composer_card = TkRawFrame(
        composer_outer,
        bg=_c("BG_CARD"),
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
    )
    composer_card.pack(fill="x")
    state.composer_card_ref = [composer_card]

    hint_row = TkRawFrame(composer_card, bg=_c("BG_CARD"))
    hint_row.pack(fill="x", padx=12, pady=(9, 5))

    state._hint_text_var = tk.StringVar(
        value="Enter — отправить · Shift+Enter — новая строка · Ctrl+F — поиск"
    )
    _hint_label = TkLabel(
        hint_row,
        textvariable=state._hint_text_var,
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 11),
        anchor="w",
    )
    _hint_label.pack(side="left", fill="x", expand=True)

    def _toggle_free_chat():

        state._free_chat_mode = not state._free_chat_mode
        try:
            _free_chat_btn.config(
                text="💬 Свободный чат ✓" if state._free_chat_mode else "💬 Свободный чат",
                fg=_c("ACCENT") if state._free_chat_mode else _c("TEXT_DIM"),
            )
        except Exception:
            pass
        set_chat_status(
            "Режим: свободный чат" if state._free_chat_mode else "Режим: редактор текста"
        )
        _mode_label.config(
            text="режим: свободный чат" if state._free_chat_mode else "режим: редактор",
            fg=_c("ACCENT") if state._free_chat_mode else _c("TEXT_MUTED"),
        )

    _free_chat_btn = tk.Button(
        hint_row,
        text="💬 Свободный чат",
        command=_toggle_free_chat,
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        activebackground=_c("BG_CARD"),
        activeforeground=_c("ACCENT"),
        relief="flat",
        bd=0,
        font=("Segoe UI", 8),
        cursor="hand2",
        padx=6,
        pady=0,
    )
    _mode_label = tk.Label(
        hint_row,
        text="сменить режим",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MUTED"),
        font=("Segoe UI", 8, "italic"),
    )
    _mode_label.pack(side="right", padx=(0, 6))
    _free_chat_btn.pack(side="right")

    input_row = TkRawFrame(composer_card, bg=_c("BG_CARD"))
    input_row.pack(fill="x", padx=12, pady=(0, 12))

    input_border = TkRawFrame(
        input_row, bg=_c("BORDER"), highlightthickness=1, highlightbackground=_c("BORDER")
    )
    input_border.pack(side="left", fill="x", expand=True, padx=(0, 8))

    input_inner = TkRawFrame(input_border, bg=_c("BG_INPUT"))
    input_inner.pack(fill="x")

    state.chat_input = tk.Text(
        input_inner,
        height=3,
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
    )
    state.chat_input.pack(fill="x")
    state.chat_input.lift()

    state.chat_input_placeholder_label = _create_placeholder_overlay(
        input_inner,
        state.chat_input,
        "Напишите сообщение…",
        x=13,
        y=11,
        fg=_c("TEXT_DIM"),
        bg=_c("BG_INPUT"),
        font=("Segoe UI", 9, "italic"),
    )

    state.chat_send_btn = tk.Button(
        input_row,
        text="➤",
        command=send_chat_message,
        bg=_c("BG_ACTIVE"),
        fg="#ffffff",
        activebackground=_c("BG_ACTIVE"),
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        cursor="hand2",
        font=("Segoe UI", 12, "bold"),
        width=5,
        padx=8,
        pady=4,
    )
    state.chat_send_btn.pack(side="right")

    # Messages scrollable canvas — после всех bottom элементов, займёт оставшееся место
    canvas_outer = TkRawFrame(right, bg=_c("BORDER"), padx=1, pady=1)
    canvas_outer.pack(side="top", fill="both", expand=True, padx=14, pady=(0, 8))

    state.chat_scrollbar = tk.Scrollbar(canvas_outer)
    state.chat_scrollbar.pack(side="right", fill="y")

    state.chat_canvas = tk.Canvas(
        canvas_outer,
        bg=_c("BG_DARK"),
        highlightthickness=0,
        bd=0,
        yscrollcommand=state.chat_scrollbar.set,
    )
    state.chat_canvas.pack(side="left", fill="both", expand=True)
    state.chat_scrollbar.config(command=state.chat_canvas.yview)

    state.chat_messages_frame = TkFrame(state.chat_canvas, bg=_c("BG_DARK"), pady=50)
    state.chat_canvas_window = state.chat_canvas.create_window(
        (0, 0),
        window=state.chat_messages_frame,
        anchor="nw",
        width=1,
    )

    def on_frame_configure(event=None):
        try:
            state.chat_canvas.configure(scrollregion=state.chat_canvas.bbox("all"))
        except Exception:
            pass

    def on_canvas_configure(event):
        try:
            new_width = event.width
            old_width = getattr(state.chat_canvas, "_last_width", None)
            state.chat_canvas._last_width = new_width
            state.chat_canvas.itemconfig(state.chat_canvas_window, width=new_width)
            if old_width != new_width:
                _update_wraplengths()
        except Exception:
            pass

    state.chat_messages_frame.bind("<Configure>", on_frame_configure)
    state.chat_canvas.bind("<Configure>", on_canvas_configure)

    for target in (win, state.chat_canvas, state.chat_messages_frame):
        try:
            target.bind("<MouseWheel>", _chat_mousewheel, add="+")
            target.bind("<Button-4>", _chat_mousewheel, add="+")
            target.bind("<Button-5>", _chat_mousewheel, add="+")
        except Exception:
            pass

    state.chat_input.bind("<FocusIn>", _on_input_focus_in)
    state.chat_input.bind("<FocusOut>", _on_input_focus_out)
    state.chat_input.bind("<KeyRelease>", _on_input_key_release)
    state.chat_input.bind("<Return>", _on_enter)

    def _chat_input_context_menu(event):
        menu = tk.Menu(
            win,
            tearoff=0,
            bg=_c("BG_CARD"),
            fg=_c("TEXT_MAIN"),
            activebackground=_c("BORDER"),
            activeforeground=_c("TEXT_MAIN"),
            relief="flat",
            borderwidth=1,
            font=("Segoe UI", 9),
        )
        menu.add_command(
            label="Вырезать",
            command=lambda: state.chat_input.event_generate("<<Cut>>"),
        )
        menu.add_command(
            label="Копировать",
            command=lambda: state.chat_input.event_generate("<<Copy>>"),
        )
        menu.add_command(
            label="Вставить",
            command=lambda: _paste_clipboard_into_widget(state.chat_input),
        )
        menu.add_separator()
        menu.add_command(
            label="Выделить всё",
            command=lambda: _select_all_widget(state.chat_input),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    state.chat_input.bind("<Button-3>", _chat_input_context_menu)

    # Hotkeys
    def _send_shortcut(event=None):
        if event is not None and _event_has_shift(event):
            return None
        send_chat_message()
        return "break"

    def _new_chat_shortcut(event=None):
        new_chat()
        return "break"

    def _export_shortcut(event=None):
        export_current_chat()
        return "break"

    def _search_shortcut(event=None):
        return open_search(event)

    chat_handlers = {
        "f": _search_shortcut,
        "n": _new_chat_shortcut,
        "s": _export_shortcut,
    }

    _bind_window_hotkeys(win, chat_handlers)
    _bind_text_hotkeys(state.chat_input, chat_handlers)

    def _ctrl_enter(event=None):
        if state._editor_mode and state._editor_preview_content:
            _submit_prompt("", clear_input=True)
            _focus_chat_input()
            return "break"
        send_chat_message()
        return "break"

    win.bind("<Control-Return>", _ctrl_enter)
    state.chat_input.bind("<Control-Return>", _ctrl_enter)

    _refresh_session_list()
    _render_current_session()
    _set_input_placeholder()
    _focus_chat_input()

    def on_close():

        _hide_new_message_indicator()
        _stop_generation(silent=True)

        _stop_generation(silent=True)
        _save_sessions()

        try:
            if _widget_exists(state._search_window):
                state._search_window.destroy()
        except Exception:
            pass
        try:
            if _widget_exists(state._env_settings_window):
                state._env_settings_window.destroy()
        except Exception:
            pass
        try:
            if _widget_exists(state._editor_window):
                state._editor_window.destroy()
        except Exception:
            pass

        state._chat_window = None
        state._search_window = None
        state._env_settings_window = None
        state._editor_window = None

        state._hint_text_var = None
        state._editor_mode = False
        state._free_chat_mode = False
        state._editor_preview_frame = None
        state._editor_preview_text = None
        state._editor_preview_content = ""

        state.session_listbox = None
        state.chat_canvas = None
        state.chat_scrollbar = None
        state.chat_messages_frame = None
        state.chat_canvas_window = None

        state.chat_input = None
        state.chat_input_placeholder_label = None
        state.chat_send_btn = None
        state.chat_status_label = None
        state.chat_token_label = None

        state.improve_btn = None
        state.paste_editor_btn = None
        state.clear_btn = None
        state.export_btn = None
        state.settings_btn = None
        state.new_chat_btn = None
        state.delete_chat_btn = None

        state.editor_source_text = None
        state.editor_comment_text = None
        state.editor_stats_label = None
        state.editor_status_label = None

        try:
            win.destroy()
        except Exception:
            pass

    win.protocol("WM_DELETE_WINDOW", on_close)

    try:
        state.chat_input.focus_set()
    except Exception:
        pass


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


def main():
    root = tk.Tk()
    root.withdraw()
    init(root, {}, lambda *args, **kwargs: None, lambda: "", lambda x: None, "test")
    open_chat_window()
    root.mainloop()


if __name__ == "__main__":
    main()
