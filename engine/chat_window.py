# C:\XTTS Studio\engine\gui\chat_window.py

from __future__ import annotations
import tkinter as tk

import engine.gui.chat_window.state as state
from engine.gui.chat_window.custom_widgets import TkFrame, TkLabel, TkRawFrame

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

    # === [ЗДЕСЬ ТОЛЬКО ИНИЦИАЛИЗАЦИЯ ROOT ЛЕЙАУТА] ===
    # (Остальной 250-строчный блок упаковки Tkinter UI-виджетов тоже здесь
    # и привязывает компоненты напрямую в state, например state.chat_input = ...)

    def on_close():
        _hide_new_message_indicator()
        _stop_generation(silent=True)
        _save_sessions()
        
        # [Очистка окон и стейтов из state.py вынесена сюда]
        try:
            win.destroy()
        except Exception:
            pass

    win.protocol("WM_DELETE_WINDOW", on_close)

# Импорты всех разделенных модулей (загружаются внизу во избежание circular-зависимостей)
from engine.gui.chat_window.chat_window_engine.sessions import _load_sessions, _save_sessions
from engine.gui.chat_window.ui_utils import _c, _widget_exists, _set_dark_titlebar, _show_window
from engine.gui.chat_window.chat_history import _refresh_session_list, new_chat, delete_current_chat
from engine.gui.chat_window.chat_scroll import _hide_new_message_indicator, _scroll_chat_to_bottom
from engine.gui.chat_window.chat_input import _focus_chat_input, send_chat_message
from engine.gui.chat_window.chat_actions import _stop_generation
# ... и так далее.

def main():
    """Точка входа для запуска чата отдельно."""
    root = tk.Tk()
    root.withdraw()
    init(root, {}, lambda *args, **kwargs: None, lambda: "", lambda x: None, "test")
    open_chat_window()
    root.mainloop()

if __name__ == "__main__":
    main()