"""
engine/chat_window.py — AI Chat window for XTTS Studio

Тёмное окно AI-чата с несколькими сессиями, сохранением истории,
экспортом, поиском, улучшением текста для TTS и настройками GPT-клиента.

Архитектура:
    init(root, colors, create_button_fn, get_text_fn, set_text_fn, placeholder)

Все обращения к основному GUI выполняются только через _get_text() / _set_text().
Прямых импортов из gui.py нет.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from tkinter import filedialog, messagebox
import tkinter as tk

# --- CTk compat, copied from gui.py ---
try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except Exception:
    CTK_AVAILABLE = False
    ctk = None

if CTK_AVAILABLE:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    class CTkFrame(ctk.CTkFrame):
        def __init__(self, *args, bg=None, highlightthickness=None, highlightbackground=None, bd=None, cursor=None, padx=None, pady=None, **kwargs):
            if bg is not None: kwargs.setdefault("fg_color", bg)
            if highlightbackground is not None: kwargs.setdefault("border_color", highlightbackground)
            if highlightthickness is not None: kwargs.setdefault("border_width", highlightthickness)
            kwargs.setdefault("corner_radius", 0)
            super().__init__(*args, **kwargs)
        def configure(self, cnf=None, **kwargs):
            if cnf: kwargs.update(cnf)
            if "bg" in kwargs: kwargs["fg_color"] = kwargs.pop("bg")
            if "highlightbackground" in kwargs: kwargs["border_color"] = kwargs.pop("highlightbackground")
            kwargs.pop("bd", None); kwargs.pop("cursor", None); kwargs.pop("padx", None); kwargs.pop("pady", None)
            return super().configure(**kwargs)
        config = configure

    class CTkLabel(ctk.CTkLabel):
        def __init__(self, *args, bg=None, fg=None, **kwargs):
            if bg is not None: kwargs.setdefault("fg_color", bg)
            if fg is not None: kwargs.setdefault("text_color", fg)
            kwargs.setdefault("corner_radius", 0)
            super().__init__(*args, **kwargs)
        def configure(self, cnf=None, **kwargs):
            if cnf: kwargs.update(cnf)
            if "bg" in kwargs: kwargs["fg_color"] = kwargs.pop("bg")
            if "fg" in kwargs: kwargs["text_color"] = kwargs.pop("fg")
            return super().configure(**kwargs)
        config = configure

    class CTkButton(ctk.CTkButton):
        def __init__(self, *args, bg=None, fg=None, activebackground=None, activeforeground=None, borderwidth=None, relief=None, padx=None, pady=None, bd=None, cursor=None, **kwargs):
            if bg is not None: kwargs.setdefault("fg_color", bg)
            if fg is not None: kwargs.setdefault("text_color", fg)
            if activebackground is not None: kwargs.setdefault("hover_color", activebackground)
            kwargs.setdefault("corner_radius", 10)
            if "height" in kwargs:
                try: h=int(kwargs["height"]); kwargs["height"]=max(28,h*28)
                except: pass
            super().__init__(*args, **kwargs)
        def configure(self, cnf=None, **kwargs):
            if cnf: kwargs.update(cnf)
            if "bg" in kwargs: kwargs["fg_color"] = kwargs.pop("bg")
            if "fg" in kwargs: kwargs["text_color"] = kwargs.pop("fg")
            if "activebackground" in kwargs: kwargs["hover_color"] = kwargs.pop("activebackground")
            kwargs.pop("activeforeground", None); kwargs.pop("borderwidth", None); kwargs.pop("relief", None); kwargs.pop("bd", None); kwargs.pop("cursor", None)
            return super().configure(**kwargs)
        config = configure

    TkFrame = CTkFrame
    TkLabel = CTkLabel
    TkButton = CTkButton
else:
    TkFrame = tk.Frame
    TkLabel = tk.Label
    TkButton = tk.Button

def TkRawFrame(parent, bg=None, highlightthickness=None,
            highlightbackground=None, bd=None, **kwargs):
    kwargs.pop("padx", None)
    kwargs.pop("pady", None)
    f = tk.Frame(parent, **kwargs)
    if bg is not None: f.configure(bg=bg)
    if highlightthickness is not None: f.configure(highlightthickness=highlightthickness)
    if highlightbackground is not None: f.configure(highlightbackground=highlightbackground)
    if bd is not None: f.configure(bd=bd)
    return f

# ─────────────────────────────────────────────────────────────────────────────
# TkRawFrame
# ─────────────────────────────────────────────────────────────────────────────
def TkRawFrame(*args, bg=None, highlightthickness=None, highlightbackground=None,
               highlightcolor=None, bd=None, padx=None, pady=None, **kwargs):
    """
    Обычный tk.Frame для случаев, когда внутрь кладутся stdlib tk-виджеты
    (Text/Entry/Listbox/Scrollbar). CTkFrame в режиме CTK имеет собственный
    canvas для отрисовки fg_color/border, который перекрывает обычные
    tk-виджеты по z-order — отсюда "поглощение" поля ввода фоном карточки.
    """
    f = tk.Frame(*args, **kwargs)
    if bg is not None: f.configure(bg=bg)
    if highlightthickness is not None: f.configure(highlightthickness=highlightthickness)
    if highlightbackground is not None: f.configure(highlightbackground=highlightbackground)
    if highlightcolor is not None: f.configure(highlightcolor=highlightcolor)
    if bd is not None: f.configure(bd=bd)
    return f

# ─────────────────────────────────────────────────────────────────────────────
# Dependency injection
# ─────────────────────────────────────────────────────────────────────────────

_root = None
_colors = None
_create_button = None
_get_text = None
_set_text = None
_placeholder = None

_use_gpt_var = None

def init(root, colors, create_button_fn, get_text_fn, set_text_fn, placeholder, use_gpt_var=None):
    global _root, _colors, _create_button, _get_text, _set_text, _placeholder, _use_gpt_var
    _root = root
    _colors = colors
    _create_button = create_button_fn
    _get_text = get_text_fn
    _set_text = set_text_fn
    _placeholder = placeholder
    _use_gpt_var = use_gpt_var
    _load_sessions()


# ─────────────────────────────────────────────────────────────────────────────
# Constants / State
# ─────────────────────────────────────────────────────────────────────────────

HISTORY_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "chat_history.json")
)
os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)

MAX_SESSIONS = 50
MAX_MESSAGES_PER_SESSION = 100

_chat_window = None
_search_window = None
_settings_window = None
_editor_window = None

_sessions: list[dict] = []
_current_session_id: str | None = None
_sessions_loaded = False

_scroll_debounce_id = None

# Widgets
session_listbox = None
chat_canvas = None
chat_scrollbar = None
chat_messages_frame = None
chat_canvas_window = None

chat_input = None
chat_input_placeholder_label = None
chat_send_btn = None
chat_status_label = None
chat_token_label = None

improve_btn = None
paste_editor_btn = None
clear_btn = None
export_btn = None
settings_btn = None
new_chat_btn = None
delete_chat_btn = None

_typing_frame = None
_typing_label = None
_typing_after_id = None
_typing_step = 0

_new_message_btn = None

_generation_lock = threading.Lock()
_generation_running = False
_generation_token = None
_generation_cancel_event: threading.Event | None = None

_message_labels: list = []
_selected_bubble_frame = None
_selected_bubble_content = ""
_search_results: list[tuple[str, int]] = []

# Editor helper window widgets
editor_source_text = None
editor_comment_text = None
editor_stats_label = None
editor_status_label = None

_editor_mode = False
_free_chat_mode = False
_hint_text_var = None
_editor_preview_frame = None
_editor_preview_text = None
_editor_preview_content = ""

composer_outer_ref = [None]
composer_card_ref = [None]


# ─────────────────────────────────────────────────────────────────────────────
# Colors / Helpers
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_COLORS = {
    "BG_DARK": "#0d1117",
    "BG_CARD": "#161b22",
    "BG_INPUT": "#010409",
    "BG_ACTIVE": "#238636",
    "BORDER": "#30363d",
    "TEXT_MAIN": "#e6edf3",
    "TEXT_DIM": "#8b949e",
    "TEXT_MUTED": "#6e7681",
    "ACCENT": "#2f81f7",
    "TEXT_SUCCESS": "#3fb950",
    "TEXT_ERROR": "#f85149",
    "WARNING": "#d29922",
}


def _c(name: str) -> str:
    if _colors is not None and hasattr(_colors, name):
        return getattr(_colors, name)
    return _FALLBACK_COLORS.get(name, "#ffffff")


def _now_ts() -> str:
    return datetime.now().strftime("%H:%M")


def _now_full() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _approx_tokens(text: str) -> int:
    return max(1, len(text or "") // 4) if text else 0

def _ai_display_name() -> str:
    _SHORT_NAMES = {
        "groq": "Groq",
        "openrouter": "OpenRouter",
        "proxy": "AI",
    }
    try:
        import engine.gpt_client as _gpt
        get_provider = getattr(_gpt, "get_provider", None)
        provider = get_provider() if callable(get_provider) else None
        return _SHORT_NAMES.get(provider, provider or "AI")
    except Exception:
        return "AI"


def _safe_after(delay: int, callback):
    try:
        if _root is not None:
            return _root.after(delay, callback)
    except Exception:
        return None
    return None


def _widget_exists(widget) -> bool:
    try:
        return widget is not None and bool(widget.winfo_exists())
    except Exception:
        return False
    
def _set_dark_titlebar(win):
    try:
        import ctypes
        win.update()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
        )
    except Exception:
        pass


def _get_app_parent():
    if _widget_exists(_chat_window):
        return _chat_window
    return _root


def _show_window(win) -> bool:
    if not _widget_exists(win):
        return False
    try:
        win.deiconify()
    except Exception:
        pass
    try:
        win.lift()
    except Exception:
        pass
    try:
        win.focus_force()
    except Exception:
        pass
    return True


def _call_and_break(func, *args, **kwargs):
    func(*args, **kwargs)
    return "break"

def _ask_simple_text(parent, title: str, prompt: str, initial: str = "") -> str | None:
    """
    Лёгкое модальное окно с одним полем ввода. Возвращает строку или None при отмене.
    Не использует tkinter.simpledialog, чтобы выдержать общую тёмную тему окон.
    """
    result = {"value": None}

    dlg = tk.Toplevel(parent)
    _set_dark_titlebar(dlg)
    dlg.title(title)
    dlg.configure(bg=_c("BG_CARD"))
    dlg.resizable(False, False)
    dlg.transient(parent)
    dlg.grab_set()
    

    TkLabel(
        dlg, text=prompt, bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 9), wraplength=320, justify="left",
    ).pack(padx=16, pady=(16, 8), anchor="w")

    var = tk.StringVar(value=initial)
    entry = tk.Entry(
        dlg, textvariable=var, bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"),
        insertbackground=_c("TEXT_MAIN"), relief="flat",
        highlightthickness=1, highlightbackground=_c("BORDER"),
        highlightcolor=_c("ACCENT"), font=("Segoe UI", 10), width=36,
    )
    entry.pack(padx=16, pady=(0, 12), ipady=5)
    entry.select_range(0, tk.END)

    btn_row = TkFrame(dlg, bg=_c("BG_CARD"))
    btn_row.pack(padx=16, pady=(0, 16), fill="x")

    def confirm(event=None):
        result["value"] = var.get().strip()
        dlg.destroy()

    def cancel(event=None):
        result["value"] = None
        dlg.destroy()

    _make_button(
        btn_row, "Отмена", cancel, bg=_c("BG_INPUT"), font_size=8, height=1, padx=8, pady=3,
    ).pack(side="right", padx=(6, 0))
    _make_button(
        btn_row, "ОК", confirm, bg=_c("BG_ACTIVE"), font_size=8, height=1, padx=8, pady=3,
    ).pack(side="right")

    entry.bind("<Return>", confirm)
    dlg.bind("<Escape>", cancel)
    dlg.protocol("WM_DELETE_WINDOW", cancel)

    entry.focus_set()
    dlg.wait_window()

    return result["value"]


def _make_button(parent, text: str, command=None, **kwargs):
    if _create_button is not None:
        attempts = (
            lambda: _create_button(parent, text, command, **kwargs),
            lambda: _create_button(parent, text, command),
        )
        for attempt in attempts:
            try:
                btn = attempt()
                if btn is not None:
                    return btn
            except TypeError:
                continue
            except Exception:
                break
    # fallback — создаём TkButton напрямую
    ...

    bg = kwargs.get("bg", _c("BG_CARD"))
    fg = kwargs.get("fg", _c("TEXT_MAIN"))
    width = kwargs.get("width", None)
    height = kwargs.get("height", 1)
    font_size = kwargs.get("font_size", 9)
    padx = kwargs.get("padx", 10)
    pady = kwargs.get("pady", 5)

    btn = TkButton(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=_c("BG_ACTIVE"),
        activeforeground=_c("TEXT_MAIN"),
        relief="flat",
        cursor="hand2",
        font=("Segoe UI", font_size, "bold"),
        padx=padx,
        pady=pady,
        height=height,
    )
    if width is not None:
        try:
            btn.config(width=width)
        except Exception:
            pass
    return btn


def _set_button_text(button, text: str):
    if not _widget_exists(button):
        return
    try:
        button.config(text=text)
    except Exception:
        try:
            button.configure(text=text)
        except Exception:
            pass


def _set_button_state(button, state: str):
    if not _widget_exists(button):
        return
    try:
        button.config(state=state)
    except Exception:
        pass


def _is_descendant(widget, ancestor) -> bool:
    try:
        while widget is not None:
            if widget == ancestor:
                return True
            widget = widget.master
    except Exception:
        return False
    return False


def _get_widget_text(widget) -> str:
    if not _widget_exists(widget):
        return ""
    try:
        if isinstance(widget, tk.Text):
            return widget.get("1.0", "end-1c")
        if isinstance(widget, tk.Entry):
            return widget.get()
    except Exception:
        return ""
    return ""


def _select_all_widget(widget):
    if not _widget_exists(widget):
        return "break"
    try:
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set(tk.INSERT, "1.0")
            widget.see(tk.INSERT)
            return "break"
        if isinstance(widget, tk.Entry):
            widget.selection_range(0, tk.END)
            widget.icursor(tk.END)
            return "break"
    except Exception:
        pass
    return "break"


def _paste_clipboard_into_widget(widget):
    if not _widget_exists(widget):
        return "break"

    try:
        text = (_get_app_parent() or _root).clipboard_get()
    except Exception:
        return "break"

    try:
        if isinstance(widget, tk.Text):
            try:
                widget.delete("sel.first", "sel.last")
            except Exception:
                pass
            widget.insert(tk.INSERT, text)
        elif isinstance(widget, tk.Entry):
            try:
                widget.delete("sel.first", "sel.last")
            except Exception:
                pass
            widget.insert(tk.INSERT, text)
    except Exception:
        pass

    try:
        widget.event_generate("<<Modified>>")
    except Exception:
        pass

    return "break"


# ─────────────────────────────────────────────────────────────────────────────
# Universal hotkeys, EN/RU layout independent
# ─────────────────────────────────────────────────────────────────────────────

_HOTKEYS = {
    "a": {
        "keysyms": {"a", "cyrillic_ef"},
        "chars": {"a", "ф", "\x01"},
    },
    "v": {
        "keysyms": {"v", "cyrillic_em"},
        "chars": {"v", "м", "\x16"},
    },
    "f": {
        "keysyms": {"f", "cyrillic_a"},
        "chars": {"f", "а", "\x06"},
    },
    "n": {
        "keysyms": {"n", "cyrillic_te"},
        "chars": {"n", "т", "\x0e"},
    },
    "s": {
        "keysyms": {"s", "cyrillic_yeru"},
        "chars": {"s", "ы", "\x13"},
    },
    "r": {
        "keysyms": {"r", "cyrillic_ka"},
        "chars": {"r", "к", "\x12"},
    },
}


def _event_has_ctrl(event) -> bool:
    try:
        return bool(int(getattr(event, "state", 0) or 0) & 0x0004)
    except Exception:
        return False


def _event_has_shift(event) -> bool:
    try:
        return bool(int(getattr(event, "state", 0) or 0) & 0x0001)
    except Exception:
        return False


def _match_hotkey(event, key: str) -> bool:
    data = _HOTKEYS.get(key.lower())
    if not data:
        return False

    try:
        keysym = str(getattr(event, "keysym", "") or "").lower()
        char = str(getattr(event, "char", "") or "").lower()
    except Exception:
        return False

    return keysym in data["keysyms"] or char in data["chars"]


def _on_ctrl_keypress(event, widget=None):
    """
    Универсальный Ctrl-handler для Text/Entry.
    Работает на английской и русской раскладке:
      Ctrl+V / Ctrl+М — вставить
      Ctrl+A / Ctrl+Ф — выделить всё
    """
    if not _event_has_ctrl(event):
        return None

    target = widget or getattr(event, "widget", None)

    if _match_hotkey(event, "v"):
        return _paste_clipboard_into_widget(target)

    if _match_hotkey(event, "a"):
        return _select_all_widget(target)

    return None


def _handle_text_ctrl(event, extra_handlers: dict[str, callable] | None = None):
    """
    Ctrl-handler для Text/Entry:
      1) сначала текстовые операции Ctrl+A/Ctrl+V;
      2) затем дополнительные горячие клавиши окна.
    """
    if not _event_has_ctrl(event):
        return None

    target = getattr(event, "widget", None)

    if isinstance(target, (tk.Text, tk.Entry)):
        if _match_hotkey(event, "v"):
            return _paste_clipboard_into_widget(target)
        if _match_hotkey(event, "a"):
            return _select_all_widget(target)

    if extra_handlers:
        for key, handler in extra_handlers.items():
            if _match_hotkey(event, key):
                return handler(event)

    return None


def _handle_window_ctrl(event, handlers: dict[str, callable] | None = None):
    if not _event_has_ctrl(event):
        return None

    if handlers:
        for key, handler in handlers.items():
            if _match_hotkey(event, key):
                return handler(event)

    return None


def _bind_window_hotkeys(window, handlers: dict[str, callable] | None = None):
    """
    Привязка Ctrl-горячих клавиш к окну независимо от раскладки.
    """
    if not _widget_exists(window):
        return
    try:
        window.bind("<Control-KeyPress>", lambda e: _handle_window_ctrl(e, handlers), add="+")
    except Exception:
        pass


def _bind_text_hotkeys(widget, extra_handlers: dict[str, callable] | None = None):
    """
    Привязка Ctrl-горячих клавиш к Text/Entry независимо от раскладки.
    """
    if not _widget_exists(widget):
        return
    try:
        widget.bind("<Control-KeyPress>", lambda e: _handle_text_ctrl(e, extra_handlers), add="+")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Placeholder overlay
# ─────────────────────────────────────────────────────────────────────────────

def _create_placeholder_overlay(parent, text_widget, text: str, *, x=12, y=10, fg=None, bg=None, font=None):
    if not _widget_exists(parent) or not _widget_exists(text_widget):
        return None

    label = TkLabel(
        parent,
        text=text,
        bg=bg or parent.cget("bg"),
        fg=fg or _c("TEXT_DIM"),
        font=font or ("Segoe UI", 9, "italic"),
        anchor="w",
        justify="left",
    )
    label.place(x=x, y=y)
    label.bind("<Button-1>", lambda e: (text_widget.focus_set(), "break"))

    text_widget._placeholder_label = label
    text_widget._placeholder_pos = (x, y)
    text_widget._placeholder_parent = parent
    text_widget._placeholder_text = text
    return label


def _sync_text_placeholder(text_widget):
    if not _widget_exists(text_widget):
        return

    label = getattr(text_widget, "_placeholder_label", None)
    if not _widget_exists(label):
        return

    try:
        content = _get_widget_text(text_widget).strip()
        focused = text_widget == text_widget.focus_get()
        x, y = getattr(text_widget, "_placeholder_pos", (12, 10))

        if content or focused:
            label.place_forget()
        else:
            label.place(x=x, y=y)
    except Exception:
        pass


def _refresh_placeholder_state(text_widget):
    _sync_text_placeholder(text_widget)


def _focus_chat_input():
    if _widget_exists(chat_input):
        try:
            chat_input.focus_set()
        except Exception:
            pass

def _update_input_placeholder_text(text: str):
    global _editor_mode
    _editor_mode = True
    lbl = getattr(chat_input, "_placeholder_label", None) if _widget_exists(chat_input) else None
    if _widget_exists(lbl):
        try:
            lbl.config(text=text)
        except Exception:
            pass
    if _hint_text_var is not None:
        try:
            _hint_text_var.set("Enter — отправить · Ctrl+Enter — отправить без комментария · Shift+Enter — новая строка")
        except Exception:
            pass
    
def _reset_editor_mode():
    global _editor_mode
    _editor_mode = False
    _hide_editor_preview()
    lbl = getattr(chat_input, "_placeholder_label", None) if _widget_exists(chat_input) else None
    if _widget_exists(lbl):
        try:
            lbl.config(text="Напишите сообщение…")
        except Exception:
            pass
    if _hint_text_var is not None:
        try:
            _hint_text_var.set("Enter — отправить · Shift+Enter — новая строка · Ctrl+F — поиск")
        except Exception:
            pass


def _show_editor_preview(text: str):
    global _editor_preview_frame, _editor_preview_text, _editor_preview_content

    if not _widget_exists(composer_outer_ref[0]):
        _editor_preview_content = text
        return

    if _widget_exists(_editor_preview_frame):
        try:
            _editor_preview_frame.destroy()
        except Exception:
            pass
    _editor_preview_frame = None
    _editor_preview_text = None
    _editor_preview_content = text

    # ВАЖНО: чистый tk.Frame, не TkFrame
    _editor_preview_frame = tk.Frame(
        composer_outer_ref[0],
        bg=_c("BG_CARD"),
        highlightthickness=1,
        highlightbackground=_c("ACCENT"),
    )
    _editor_preview_frame.pack(fill="x", before=composer_card_ref[0], pady=(0, 4))

    header = tk.Frame(_editor_preview_frame, bg=_c("BG_CARD"))
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
        _editor_preview_frame,
        bg=_c("BORDER"),
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
    )
    preview_border.pack(fill="x", padx=10, pady=(0, 8))

    preview_inner = tk.Frame(preview_border, bg=_c("BG_INPUT"))
    preview_inner.pack(fill="x")

    def _sync_preview_content(event=None):
        global _editor_preview_content
        try:
            _editor_preview_content = _editor_preview_text.get("1.0", "end-1c")
        except Exception:
            pass

    _editor_preview_text = tk.Text(
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
    _editor_preview_text.insert("1.0", text)
    _editor_preview_text.pack(fill="x")
    _editor_preview_text.bind("<KeyRelease>", _sync_preview_content)
    _bind_text_hotkeys(_editor_preview_text)

    _safe_after(0, _focus_chat_input)
    _safe_after(100, _focus_chat_input)

def _hide_editor_preview():
    global _editor_preview_frame, _editor_preview_text, _editor_preview_content
    if _widget_exists(_editor_preview_frame):
        try:
            _editor_preview_frame.destroy()
        except Exception:
            pass
    _editor_preview_frame = None
    _editor_preview_text = None
    _editor_preview_content = ""

# ─────────────────────────────────────────────────────────────────────────────
# Scroll helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_chat_near_bottom(threshold: float = 0.01) -> bool:
    if not _widget_exists(chat_canvas):
        return True
    try:
        _top, bottom = chat_canvas.yview()
        return bottom >= (1.0 - threshold)
    except Exception:
        return True


_scroll_debounce_id = None

def _scroll_chat_to_bottom(immediate: bool = False):
    global _scroll_debounce_id
    if not _widget_exists(chat_canvas):
        return

    if immediate:
        try:
            chat_canvas.update_idletasks()
            chat_canvas.configure(scrollregion=chat_canvas.bbox("all"))
            chat_canvas.yview_moveto(1.0)
        except Exception:
            pass
        return

    # Отменяем предыдущий запланированный скролл
    if _scroll_debounce_id is not None:
        try:
            _root.after_cancel(_scroll_debounce_id)
        except Exception:
            pass
        _scroll_debounce_id = None

    def _do_scroll():
        global _scroll_debounce_id
        _scroll_debounce_id = None
        if not _widget_exists(chat_canvas):
            return
        try:
            chat_canvas.update_idletasks()
            chat_canvas.configure(scrollregion=chat_canvas.bbox("all"))
            chat_canvas.yview_moveto(1.0)
        except Exception:
            pass

    _scroll_debounce_id = _safe_after(80, _do_scroll)

def _show_new_message_indicator():
    global _new_message_btn

    if not _widget_exists(composer_outer_ref[0]):
        return

    if _widget_exists(_new_message_btn):
        return  # уже показана

    _new_message_btn = _make_button(
        composer_outer_ref[0],
        "↓ Новый ответ — нажмите, чтобы прокрутить",
        _scroll_to_new_message,
        bg=_c("ACCENT"),
        fg="#ffffff",
        font_size=9,
        height=1,
        padx=10,
        pady=5,
    )
    _new_message_btn.pack(fill="x", pady=(0, 4), before=composer_card_ref[0])


def _hide_new_message_indicator():
    global _new_message_btn
    if _widget_exists(_new_message_btn):
        try:
            _new_message_btn.destroy()
        except Exception:
            pass
    _new_message_btn = None


def _scroll_to_new_message():
    _hide_new_message_indicator()
    _scroll_chat_to_bottom(immediate=True)


def _chat_mousewheel(event):
    if not _widget_exists(chat_canvas):
        return None

    try:
        pointer = _root.winfo_containing(event.x_root, event.y_root) if _root is not None else None
        if pointer is None:
            return None

        if not _is_descendant(pointer, chat_canvas):
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

        chat_canvas.yview_scroll(units, "units")
        return "break"
    except Exception:
        return None

def _chat_mousewheel(event):
    if not _widget_exists(chat_canvas):
        return None

    try:
        pointer = _root.winfo_containing(event.x_root, event.y_root) if _root is not None else None
        if pointer is None:
            return None

        if not _is_descendant(pointer, chat_canvas):
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

        chat_canvas.yview_scroll(units, "units")

        # Если пользователь докрутил до низа сам — убираем индикатор
        _safe_after(50, lambda: _hide_new_message_indicator() if _is_chat_near_bottom() else None)

        return "break"
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Text compose helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_editor_compose_prompt(source_text: str, comment_text: str) -> str:
    source = (source_text or "").strip()
    comment = (comment_text or "").strip()

    if source and comment:
        return f"Текст из редактора:\n{source}\n\nКомментарий:\n{comment}"
    if source:
        return source
    return comment


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


# ─────────────────────────────────────────────────────────────────────────────
# History persistence
# ─────────────────────────────────────────────────────────────────────────────

def _load_sessions():
    global _sessions, _current_session_id, _sessions_loaded

    if _sessions_loaded:
        return

    _sessions_loaded = True
    _sessions = []

    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            raw_sessions = data.get("sessions", [])
            if isinstance(raw_sessions, list):
                for s in raw_sessions[:MAX_SESSIONS]:
                    if not isinstance(s, dict):
                        continue

                    sid = str(s.get("id") or uuid.uuid4())
                    title = str(s.get("title") or "Новый чат")
                    created = str(s.get("created") or _now_full())

                    messages = []
                    for m in s.get("messages", [])[:MAX_MESSAGES_PER_SESSION]:
                        if not isinstance(m, dict):
                            continue
                        role = m.get("role", "assistant")
                        content = m.get("content", "")
                        ts = m.get("ts", "")
                        if role not in ("user", "assistant", "system"):
                            role = "assistant"
                        messages.append({
                            "role": role,
                            "content": str(content),
                            "ts": str(ts or _now_ts()),
                        })

                    _sessions.append({
                        "id": sid,
                        "title": title[:80],
                        "created": created,
                        "messages": messages,
                    })
    except Exception:
        _sessions = []

    if not _sessions:
        _sessions.append(_create_session_dict())

    _enforce_limits()
    _current_session_id = _sessions[0]["id"]


def _save_sessions():
    try:
        _enforce_limits()
        data = {"sessions": _sessions}
        tmp_path = HISTORY_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, HISTORY_FILE)
    except Exception as e:
        set_chat_status(f"Не удалось сохранить историю: {e}")


def _enforce_limits():
    global _sessions

    for s in _sessions:
        msgs = s.get("messages", [])
        if len(msgs) > MAX_MESSAGES_PER_SESSION:
            s["messages"] = msgs[-MAX_MESSAGES_PER_SESSION:]

    if len(_sessions) > MAX_SESSIONS:
        _sessions = _sessions[:MAX_SESSIONS]


def _create_session_dict() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "title": "Новый чат",
        "created": _now_full(),
        "messages": [],
    }


def _get_current_session() -> dict:
    global _current_session_id

    _load_sessions()

    for s in _sessions:
        if s.get("id") == _current_session_id:
            return s

    if _sessions:
        _current_session_id = _sessions[0]["id"]
        return _sessions[0]

    s = _create_session_dict()
    _sessions.append(s)
    _current_session_id = s["id"]
    return s


def _update_session_title_if_needed(session: dict):
    if session.get("title") and session.get("title") != "Новый чат":
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
            result.append({
                "role": m.get("role", "assistant"),
                "content": m.get("content", ""),
            })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Status / public compatibility helpers
# ─────────────────────────────────────────────────────────────────────────────

def set_chat_status(message: str):
    if not _widget_exists(chat_status_label):
        return
    try:
        chat_status_label.config(text=message)
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


def clear_chat_history():
    session = _get_current_session()

    if not messagebox.askyesno(
        "Очистить чат",
        "Очистить сообщения текущего чата?",
        parent=_get_app_parent() or _root,
    ):
        return

    session["messages"] = []
    session["title"] = "Новый чат"
    _save_sessions()
    _render_current_session()
    _refresh_session_list()
    set_chat_status("История текущего чата очищена")


# ─────────────────────────────────────────────────────────────────────────────
# Session list
# ─────────────────────────────────────────────────────────────────────────────

def _refresh_session_list():
    if not _widget_exists(session_listbox):
        return

    try:
        session_listbox.delete(0, tk.END)

        for s in _sessions:
            title = s.get("title") or "Новый чат"
            count = len(s.get("messages", []))
            marker = "• " if s.get("id") == _current_session_id else "  "
            label = f"{marker}{title}"
            if count:
                label += f"  ({count})"
            session_listbox.insert(tk.END, label)

        for i, s in enumerate(_sessions):
            if s.get("id") == _current_session_id:
                session_listbox.selection_clear(0, tk.END)
                session_listbox.selection_set(i)
                session_listbox.activate(i)
                break
    except Exception:
        pass


def _on_session_select(event=None):
    global _current_session_id

    if not _widget_exists(session_listbox):
        return

    try:
        sel = session_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(_sessions):
            return

        _save_sessions()
        _current_session_id = _sessions[idx]["id"]
        _render_current_session()
        _refresh_session_list()
        set_chat_status("Сессия загружена")
    except Exception as e:
        set_chat_status(f"Ошибка переключения сессии: {e}")


def new_chat():
    global _current_session_id

    _stop_generation(silent=True)

    s = _create_session_dict()
    _sessions.insert(0, s)
    _current_session_id = s["id"]

    _enforce_limits()
    _save_sessions()

    _render_current_session()
    _refresh_session_list()
    set_chat_status("Создан новый чат")
    _focus_chat_input()


def delete_current_chat():
    global _sessions, _current_session_id

    session = _get_current_session()
    title = session.get("title") or "Новый чат"

    if not messagebox.askyesno(
        "Удалить чат",
        f"Удалить чат «{title}» без возможности восстановления?",
        parent=_get_app_parent() or _root,
    ):
        return

    _stop_generation(silent=True)

    _sessions = [s for s in _sessions if s.get("id") != _current_session_id]

    if not _sessions:
        new_session = _create_session_dict()
        _sessions.append(new_session)
        _current_session_id = new_session["id"]
    else:
        _current_session_id = _sessions[0]["id"]

    _save_sessions()
    _render_current_session()
    _refresh_session_list()
    set_chat_status("Чат удалён")
    _focus_chat_input()


# ─────────────────────────────────────────────────────────────────────────────
# Chat rendering
# ─────────────────────────────────────────────────────────────────────────────

def _clear_messages_ui():
    global _typing_frame, _typing_label, _message_labels
    global _selected_bubble_frame, _selected_bubble_content

    _message_labels = []
    _typing_frame = None
    _typing_label = None
    _selected_bubble_frame = None
    _selected_bubble_content = ""

    if not _widget_exists(chat_messages_frame):
        return

    for child in chat_messages_frame.winfo_children():
        try:
            child.destroy()
        except Exception:
            pass

def _resize_bubble_text(text_widget):
    if not _widget_exists(text_widget):
        return
    try:
        text_widget.update_idletasks()
        n = int(text_widget.tk.call(
            text_widget._w, "count", "-displaylines", "1.0", "end"
        ))
        text_widget.config(height=max(1, n))
    except Exception:
        try:
            content = text_widget.get("1.0", "end-1c")
            text_widget.config(height=max(1, content.count("\n") + 1))
        except Exception:
            pass


def content_lines_estimate(text_widget) -> int:
    try:
        content = text_widget.get("1.0", "end-1c")
        return max(1, content.count("\n") + 1)
    except Exception:
        return 1

def _render_current_session():
    _hide_new_message_indicator()
    _clear_messages_ui()
    session = _get_current_session()

    messages = session.get("messages", [])
    if not messages:
        _add_empty_state()
    else:
        for m in messages:
            _add_message_bubble(m, smooth_scroll=False)

    # Откладываем до того как канвас получит реальные размеры
    _safe_after(0, _update_wraplengths)
    _safe_after(150, _update_wraplengths)
    _scroll_chat_to_bottom(immediate=True)
    _safe_after(200, lambda: _scroll_chat_to_bottom(immediate=True))
    _update_token_counter()


def _add_empty_state():
    if not _widget_exists(chat_messages_frame):
        return

    box = TkFrame(chat_messages_frame, bg=_c("BG_DARK"))
    box._is_empty_state = True
    box.pack(fill="both", expand=True, padx=24, pady=60)

    TkLabel(
        box,
        text="💬",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI Emoji", 42),
    ).pack(pady=(0, 10))

    TkLabel(
        box,
        text="Новый чат",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 16, "bold"),
    ).pack()

    TkLabel(
        box,
        text="Спросите AI о тексте, дикторе, TTS или улучшите текст для озвучки.",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 10),
        wraplength=420,
        justify="center",
    ).pack(pady=(8, 0))


def _destroy_empty_state_if_any():
    if not _widget_exists(chat_messages_frame):
        return

    for child in chat_messages_frame.winfo_children():
        try:
            if getattr(child, "_is_empty_state", False):
                child.destroy()
        except Exception:
            pass


def _lighten_color(hex_color: str, factor: float = 0.1) -> str:
    try:
        h = hex_color.lstrip("#")
        if len(h) != 6:
            return hex_color
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return hex_color


def _add_message_bubble(message: dict, smooth_scroll: bool = True, force_scroll: bool = False):
    if not _widget_exists(chat_messages_frame):
        return

    role = message.get("role", "assistant")
    content = message.get("content", "")
    ts = message.get("ts", _now_ts())
    tokens = _approx_tokens(content)

    _destroy_empty_state_if_any()
    # Запоминаем позицию ДО добавления пузыря
    _was_near_bottom = _is_chat_near_bottom()

    if role == "system":
        _add_system_message(content, ts)
        if smooth_scroll and (_is_chat_near_bottom() or force_scroll):
            _scroll_chat_to_bottom(immediate=force_scroll)
        return

    is_user = role == "user"

    row = TkFrame(chat_messages_frame, bg=_c("BG_DARK"))
    row._is_message_row = True
    row.pack(fill="x", padx=12, pady=6)

    avatar_text = "🧑" if is_user else "🤖"
    avatar = TkLabel(
        row,
        text=avatar_text,
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI Emoji", 18),
        width=2,
    )

    bubble_bg = _c("ACCENT") if is_user else _c("BG_CARD")
    bubble_fg = "#ffffff" if is_user else _c("TEXT_MAIN")
    bubble_hover = _lighten_color(bubble_bg, 0.10)

    bubble = tk.Frame(
        row,
        bg=bubble_bg,
        highlightthickness=1,
        highlightbackground=_c("BORDER") if not is_user else bubble_bg,
        padx=10,
        pady=8,
    )

    meta = tk.Frame(bubble, bg=bubble_bg)
    meta.pack(fill="x")

    author = "Вы" if is_user else _ai_display_name()
    meta_fg = "#dbeafe" if is_user else _c("TEXT_DIM")

    tk.Label(
        meta,
        text=f"{author} · {ts} · ≈{tokens} ток.",
        bg=bubble_bg,
        fg=meta_fg,
        font=("Segoe UI", 8),
        anchor="w",
    ).pack(side="left")

    btn_box = tk.Frame(meta, bg=bubble_bg)
    btn_box.pack(side="right")

    def _send_selected_or_full(lbl=None):
        if lbl is not None and _widget_exists(lbl):
            try:
                sel = lbl.get("sel.first", "sel.last").strip()
                if sel:
                    _send_to_main_editor(sel)
                    return
            except Exception:
                pass
        _send_to_main_editor(content)

    # to_editor_btn
    to_editor_btn = tk.Button(
        btn_box,
        text="→",
        command=lambda: _send_selected_or_full(text_label),
        bg=bubble_bg,
        fg=meta_fg,
        activebackground=bubble_hover,
        activeforeground=_c("TEXT_MAIN"),
        relief="flat",
        bd=0,
        cursor="hand2",
        font=("Segoe UI", 8, "bold"),
        width=3,
        padx=2,
        pady=0,
    )
    to_editor_btn.pack(side="right", padx=(4, 0))

    # copy_btn
    copy_btn = tk.Button(
        btn_box,
        text="",
        command=lambda t=content: _copy_to_clipboard(t),
        bg=bubble_bg,
        fg=meta_fg,
        activebackground=bubble_hover,
        activeforeground=_c("TEXT_MAIN"),
        relief="flat",
        bd=0,
        cursor="hand2",
        font=("Segoe UI", 8),
        width=7,
        padx=2,
        pady=0,
    )
    copy_btn.pack(side="right")

    # ── Текст сообщения как read-only Text, чтобы поддержать выделение мышкой ──
    text_label = tk.Text(
        bubble,
        bg=bubble_bg,
        fg=bubble_fg,
        font=("Segoe UI", 10),
        relief="flat",
        highlightthickness=0,
        bd=0,
        wrap="word",
        padx=0,
        pady=0,
        cursor="arrow",
        takefocus=0,
    )
    text_label.insert("1.0", content)
    # state остаётся "normal", иначе в некоторых сборках Tk выделение мышью
    # в disabled Text работает нестабильно. Редактирование блокируем явно:
    text_label.bind("<Key>", lambda e: "break")
    text_label.bind("<<Paste>>", lambda e: "break")
    text_label.bind("<<Cut>>", lambda e: "break")
    text_label.bind("<Button-2>", lambda e: "break")  # средняя кнопка мыши = paste в X11

    # Выделение текста должно остаться возможным, даже когда state="disabled" —
    # для этого разрешаем тег "sel" работать независимо от read-only режима.
    text_label.bind("<Button-1>", lambda e: _on_bubble_text_click(e))
    text_label.bind("<B1-Motion>", lambda e: "ignore_disabled_drag" or None)

    # Высота Text подбирается по контенту динамически (см. _resize_bubble_text)
    text_label.pack(fill="x", pady=(4, 0))
    text_label._bubble_content = content
    text_label._bubble_bg = bubble_bg
    _message_labels.append(text_label)
    def _send_selected_or_full():
        try:
            ranges = text_label.tag_ranges("sel")
            if ranges:
                sel = text_label.get(ranges[0], ranges[1]).strip()
                if sel:
                    _send_to_main_editor(sel)
                    return
        except Exception:
            pass
        _send_to_main_editor(content)

    to_editor_btn.config(command=_send_selected_or_full)
    _resize_bubble_text(text_label)

    text_label.bind("<Button-3>", lambda e, c=content: _show_bubble_context_menu(e, c, text_label))
    bubble.bind("<Button-3>", lambda e, c=content: _show_bubble_context_menu(e, c, text_label))

    spacer_left = tk.Frame(row, bg=_c("BG_DARK"))
    spacer_right = tk.Frame(row, bg=_c("BG_DARK"))

    if is_user:
        spacer_left.pack(side="left", fill="x", expand=True)
        bubble.pack(side="left", padx=(60, 8), anchor="e")
        avatar.pack(side="left", anchor="n")
    else:
        avatar.pack(side="left", anchor="n")
        bubble.pack(side="left", padx=(8, 60), anchor="w")
        spacer_right.pack(side="left", fill="x", expand=True)

    # ── Подсветка пузыря по клику (если не было выделения текста) ──────────
    def _select_this_bubble(_event=None):
        _select_bubble(bubble, content, bubble_bg)

    for w in (row, bubble, meta):
        try:
            w.bind("<Button-1>", _select_this_bubble)
        except Exception:
            pass

    def on_enter(_event=None):
        if bubble is _selected_bubble_frame_get():
            return  # выбранный пузырь не теряет свою подсветку при hover
        try:
            bubble.config(bg=bubble_hover)
            meta.config(bg=bubble_hover)
            text_label.config(bg=bubble_hover)
            copy_btn.config(text="Copy", bg=bubble_hover)
            for child in meta.winfo_children():
                try:
                    child.config(bg=bubble_hover)
                except Exception:
                    pass
        except Exception:
            pass

    def on_leave(_event=None):
        if bubble is _selected_bubble_frame_get():
            return
        try:
            bubble.config(bg=bubble_bg)
            meta.config(bg=bubble_bg)
            text_label.config(bg=bubble_bg)
            copy_btn.config(text="", bg=bubble_bg)
            to_editor_btn.config(bg=bubble_bg)
            for child in meta.winfo_children():
                try:
                    child.config(bg=bubble_bg)
                except Exception:
                    pass
        except Exception:
            pass

    bubble._on_select_colors = (bubble_bg, bubble_hover, meta, text_label, copy_btn, to_editor_btn)

    for w in (row, bubble, meta, text_label, avatar):
        try:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
        except Exception:
            pass

    # Сначала задаём правильную ширину, потом пересчитываем высоту
    _safe_after(50, lambda: _resize_bubble_text(text_label) if _widget_exists(text_label) else None)

    # Проверяем позицию ПОСЛЕ того как пузырь отрисован и scrollregion обновился
    def _check_and_scroll():
        if not _widget_exists(chat_canvas):
            return
        if _was_near_bottom:
            _scroll_chat_to_bottom(immediate=False)
            _hide_new_message_indicator()
        elif role == "assistant" and smooth_scroll:
            _show_new_message_indicator()

    _safe_after(150, _check_and_scroll)

def _add_system_message(content: str, ts: str):
    row = tk.Frame(chat_messages_frame, bg=_c("BG_DARK"))
    row._is_message_row = True
    row.pack(fill="x", padx=18, pady=8)

    label = TkLabel(
        row,
        text=f"{ts} · {content}",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9, "italic"),
        wraplength=540,
        justify="center",
        padx=12,
        pady=8,
    )
    label.pack(anchor="center")
    _message_labels.append(label)


def _copy_to_clipboard(text: str):
    try:
        target = _get_app_parent() or _root
        if target is None:
            return
        target.clipboard_clear()
        target.clipboard_append(text)
        set_chat_status("Сообщение скопировано")
    except Exception as e:
        set_chat_status(f"Не удалось скопировать: {e}")

def _selected_bubble_frame_get():
    return _selected_bubble_frame


def _select_bubble(bubble_frame, content: str, base_bg: str):
    """
    Подсветить пузырь как выбранный. Повторный клик по тому же пузырю — снять выбор.
    """
    global _selected_bubble_frame, _selected_bubble_content

    # Снимаем подсветку с предыдущего выбранного пузыря (если был и существует)
    if _widget_exists(_selected_bubble_frame) and _selected_bubble_frame is not bubble_frame:
        try:
            prev_bg, _hover, prev_meta, prev_text, prev_copy, prev_to_editor = _selected_bubble_frame._on_select_colors
            _selected_bubble_frame.config(bg=prev_bg, highlightbackground=_c("BORDER"))
            prev_meta.config(bg=prev_bg)
            prev_text.config(bg=prev_bg)
            prev_copy.config(bg=prev_bg)
            prev_to_editor.config(bg=prev_bg)
            for child in prev_meta.winfo_children():
                try:
                    child.config(bg=prev_bg)
                except Exception:
                    pass
        except Exception:
            pass

    if _selected_bubble_frame is bubble_frame:
        # Повторный клик по уже выбранному — снимаем выбор
        try:
            _, _hover, meta, text_w, copy_b, to_editor_b = bubble_frame._on_select_colors
            bubble_frame.config(bg=base_bg, highlightbackground=_c("BORDER"))
            meta.config(bg=base_bg)
            text_w.config(bg=base_bg)
            copy_b.config(bg=base_bg)
            to_editor_b.config(bg=base_bg)
        except Exception:
            pass
        _selected_bubble_frame = None
        _selected_bubble_content = ""
        set_chat_status("Выбор снят")
        return

    # Подсвечиваем новый выбранный пузырь акцентной рамкой
    try:
        bubble_frame.config(highlightbackground=_c("ACCENT"), highlightthickness=2)
    except Exception:
        pass

    _selected_bubble_frame = bubble_frame
    _selected_bubble_content = content
    set_chat_status("Сообщение выбрано · нажмите «→» на нём, чтобы отправить в редактор")


def _on_bubble_text_click(event):
    """
    Клик по тексту внутри пузыря: если это просто клик (не начало выделения),
    подсветка пузыря сработает через биндинг на родителе (bubble/meta/row),
    который тоже получит это же событие по умолчанию в Tkinter (bubbling
    в tk идёт по виджетам, а не по DOM-дереву, поэтому верхний bind на bubble
    сработает независимо). Здесь только гарантируем, что клик не блокируется
    discard-логикой disabled Text, и что повторное растягивание выделения
    мышью (B1-Motion) не цепляет подсветку повторно — это естественно, т.к.
    выделение текста — отдельный, не привязанный к подсветке жест.
    """
    return None  # пропускаем штатную обработку Text (выделение работает само)

def _send_to_main_editor(content: str):
    if _set_text is None or not content.strip():
        return
    try:
        _set_text(content.strip())
        append_chat_message("system", f"Текст отправлен в редактор ({len(content.strip())} симв.)")
        set_chat_status("✅ Текст отправлен в редактор TTS")
    except Exception as e:
        set_chat_status(f"Ошибка: {e}")


def _show_bubble_context_menu(event, content: str, text_widget=None):
    if not _widget_exists(_chat_window):
        return

    def _get_sel_or_full():
        if text_widget is not None and _widget_exists(text_widget):
            try:
                ranges = text_widget.tag_ranges("sel")
                if ranges:
                    sel = text_widget.get(ranges[0], ranges[1]).strip()
                    if sel:
                        return sel
            except Exception:
                pass
        return content

    menu = tk.Menu(
        _chat_window, tearoff=0,
        bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
        activebackground=_c("BG_HOVER") if hasattr(_colors, "BG_HOVER") else _c("BORDER"),
        activeforeground=_c("TEXT_MAIN"),
        relief="flat", borderwidth=1,
        font=("Segoe UI", 9),
    )
    menu.add_command(
        label="📋 Копировать",
        command=lambda: _copy_to_clipboard(_get_sel_or_full()),
    )
    menu.add_separator()
    menu.add_command(
        label="📝 В редактор TTS",
        command=lambda: _send_to_main_editor(_get_sel_or_full()),
    )
    menu.add_command(
        label="↩ В поле ввода чата",
        command=lambda: _insert_prompt_into_chat_input(_get_sel_or_full()),
    )
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def _update_wraplengths(event=None):
    if not _widget_exists(chat_canvas):
        return
    try:
        width = chat_canvas.winfo_width()
        if width < 50:
            return
        wrap_px = max(260, min(720, int(width * 0.62)))
        char_width = max(30, wrap_px // 7)
        
        # Собираем все изменения, применяем за один проход без update_idletasks внутри цикла
        for widget in list(_message_labels):
            if not _widget_exists(widget):
                continue
            try:
                if isinstance(widget, tk.Text):
                    widget.config(width=char_width)
                else:
                    widget.config(wraplength=wrap_px)
            except Exception:
                pass
        
        # update_idletasks только один раз в конце
        try:
            chat_canvas.update_idletasks()
            chat_canvas.configure(scrollregion=chat_canvas.bbox("all"))
        except Exception:
            pass
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Typing animation
# ─────────────────────────────────────────────────────────────────────────────

def _show_typing():
    global _typing_frame, _typing_label, _typing_step

    if not _widget_exists(chat_messages_frame):
        return

    _hide_typing()
    _typing_step = 0

    row = TkFrame(chat_messages_frame, bg=_c("BG_DARK"))
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

    _typing_frame = row
    _typing_label = lbl

    _animate_typing()
    if _is_chat_near_bottom():
        _scroll_chat_to_bottom()


def _animate_typing():
    global _typing_after_id, _typing_step

    if not _generation_running or not _widget_exists(_typing_label):
        return

    dots = "." * ((_typing_step % 3) + 1)
    _typing_step += 1

    try:
        _typing_label.config(text=f"AI печатает{dots}")
    except Exception:
        return

    _typing_after_id = _safe_after(350, _animate_typing)


def _hide_typing():
    global _typing_frame, _typing_label, _typing_after_id

    if _typing_after_id is not None and _root is not None:
        try:
            _root.after_cancel(_typing_after_id)
        except Exception:
            pass

    _typing_after_id = None

    if _widget_exists(_typing_frame):
        try:
            _typing_frame.destroy()
        except Exception:
            pass

    _typing_frame = None
    _typing_label = None


# ─────────────────────────────────────────────────────────────────────────────
# Input helpers
# ─────────────────────────────────────────────────────────────────────────────

def _input_has_placeholder() -> bool:
    try:
        return _widget_exists(chat_input_placeholder_label) and bool(chat_input_placeholder_label.winfo_ismapped())
    except Exception:
        return False


def _set_input_placeholder():
    if not _widget_exists(chat_input):
        return
    _sync_text_placeholder(chat_input)


def _clear_input_placeholder():
    if not _widget_exists(chat_input):
        return
    try:
        if _widget_exists(chat_input_placeholder_label):
            chat_input_placeholder_label.place_forget()
    except Exception:
        pass


def _get_input_text() -> str:
    if not _widget_exists(chat_input):
        return ""
    try:
        return chat_input.get("1.0", "end-1c")
    except Exception:
        return ""


def _clear_input_text():
    if not _widget_exists(chat_input):
        return
    try:
        chat_input.delete("1.0", tk.END)
        chat_input.config(fg=_c("TEXT_MAIN"))
        _resize_input()
        _update_token_counter()
        _sync_text_placeholder(chat_input)
        _reset_editor_mode()
        _safe_after(50, _focus_chat_input)
    except Exception:
        pass


def _resize_input(event=None):
    if not _widget_exists(chat_input):
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
        chat_input.config(height=height)
    except Exception:
        pass


def _update_token_counter(event=None):
    if not _widget_exists(chat_token_label):
        return

    text = _get_input_text()
    input_tokens = _approx_tokens(text)

    session = _get_current_session()
    chat_tokens = sum(_approx_tokens(m.get("content", "")) for m in session.get("messages", []))

    try:
        chat_token_label.config(text=f"Ввод: ≈{input_tokens} ток. · Чат: ≈{chat_tokens} ток.")
    except Exception:
        pass


def _paste_into_input(event=None):
    if not _widget_exists(chat_input):
        return "break"
    return _paste_clipboard_into_widget(chat_input)


def _on_input_focus_in(event=None):
    _clear_input_placeholder()


def _on_input_focus_out(event=None):
    _sync_text_placeholder(chat_input)


def _on_input_key_release(event=None):
    _resize_input()
    _update_token_counter()
    _sync_text_placeholder(chat_input)


def _on_enter(event):
    if _event_has_shift(event):
        return None
    if _event_has_ctrl(event):
        return None
    if _editor_mode and _editor_preview_content:
        comment = _get_input_text().strip()
        _submit_prompt(comment, clear_input=True)
        return "break"
    send_chat_message()
    return "break"


# ─────────────────────────────────────────────────────────────────────────────
# Sending / generation
# ─────────────────────────────────────────────────────────────────────────────

def _run_generation(session: dict, prompt: str):
    """Запускает воркер генерации AI-ответа. prompt — то что уходит в API."""
    global _generation_running, _generation_token, _generation_cancel_event

    if _generation_running:
        _stop_generation(silent=True)

    history_for_api = _messages_for_api(session)[:-1]

    cancel_event = threading.Event()
    token = str(uuid.uuid4())

    with _generation_lock:
        _generation_running = True
        _generation_token = token
        _generation_cancel_event = cancel_event

    _set_generation_ui(True)
    _show_typing()
    set_chat_status("AI печатает...")

    def _worker():
        try:
            import engine.gpt_client as _gpt

            system = _gpt._FREE_CHAT_SYSTEM if _free_chat_mode else None
            response = _gpt.chat(prompt, history=history_for_api, system=system)

            if response is None:
                response = ""
            response = str(response)
            

            def _apply_response():
                global _generation_running, _generation_token, _generation_cancel_event

                if cancel_event.is_set() or token != _generation_token:
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
                    _safe_after(80, lambda: _scroll_chat_to_bottom(immediate=True) if (_widget_exists(chat_canvas) and _is_chat_near_bottom()) else None)

                with _generation_lock:
                    _generation_running = False
                    _generation_token = None
                    _generation_cancel_event = None

                _set_generation_ui(False)
                set_chat_status("Ответ получен")

            _safe_after(0, _apply_response)

        except Exception as e:
            import engine.gpt_client as _gpt
            is_unavailable = isinstance(e, getattr(_gpt, "AIUnavailable", ()))
            msg = str(e) or "Неизвестная ошибка"

            def _show_error():
                global _generation_running, _generation_token, _generation_cancel_event

                if cancel_event.is_set() or token != _generation_token:
                    return

                _hide_typing()

                with _generation_lock:
                    _generation_running = False
                    _generation_token = None
                    _generation_cancel_event = None

                _set_generation_ui(False)

                if is_unavailable:
                    # ИИ временно недоступен (сеть или вся цепочка провайдеров) —
                    # это не баг, без messagebox, только статус.
                    set_chat_status("ИИ временно недоступен. Попробуйте позже.")
                else:
                    set_chat_status(f"Ошибка AI: {msg}")
                    messagebox.showerror("Ошибка AI", msg, parent=_get_app_parent() or _root)

            _safe_after(0, _show_error)

        finally:
            def _final_cleanup():
                global _generation_running, _generation_token, _generation_cancel_event

                if token == _generation_token and not cancel_event.is_set():
                    return

                if cancel_event.is_set():
                    _hide_typing()
                    with _generation_lock:
                        if token == _generation_token:
                            _generation_running = False
                            _generation_token = None
                            _generation_cancel_event = None
                    _set_generation_ui(False)

            _safe_after(0, _final_cleanup)

    threading.Thread(target=_worker, daemon=True).start()


def _submit_prompt(prompt: str, *, clear_input: bool = False):
    global _generation_running, _generation_token, _generation_cancel_event, _free_chat_mode

    prompt = (prompt or "").strip()

        # В режиме свободного чата — игнорируем editor_mode, отправляем как обычный чат
    if _free_chat_mode and not _editor_mode:
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
    if _editor_mode and _editor_preview_content:
        src = _editor_preview_content.strip()
        comment = prompt

        _reset_editor_mode()

        if clear_input:
            _clear_input_text()

        if comment:
            display_content = f"{src}\n\nКомментарий:\n{comment}"
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
        _safe_after(80, lambda: _scroll_chat_to_bottom(immediate=True) if _widget_exists(chat_canvas) else None)

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
        if not prompt and not (_editor_mode and _editor_preview_content):
            return
        _submit_prompt(prompt, clear_input=True)
        return

    prompt = str(prompt).strip()
    if not prompt:
        return
    _submit_prompt(prompt, clear_input=False)


def _stop_generation(silent: bool = False):
    global _generation_running, _generation_token, _generation_cancel_event

    with _generation_lock:
        if _generation_cancel_event is not None:
            try:
                _generation_cancel_event.set()
            except Exception:
                pass
        _generation_running = False
        _generation_token = None
        _generation_cancel_event = None

    _hide_typing()
    _set_generation_ui(False)

    if not silent:
        set_chat_status("Генерация остановлена")


def _set_generation_ui(running: bool):
    # Кнопка отправки/стоп
    if _widget_exists(chat_send_btn):
        try:
            chat_send_btn.config(
                text="⏹" if running else "➤",
                command=lambda: _stop_generation() if running else send_chat_message(),
            )
        except Exception:
            pass

    state = "disabled" if running else "normal"
    for btn in (improve_btn, paste_editor_btn, clear_btn,
                export_btn, settings_btn, new_chat_btn, delete_chat_btn):
        _set_button_state(btn, state)


# ─────────────────────────────────────────────────────────────────────────────
# Actions
# ─────────────────────────────────────────────────────────────────────────────

def improve_text_with_gpt():
    if _use_gpt_var is not None and not _use_gpt_var.get():
        messagebox.showwarning(
            "AI edit выключен",
            "Включите флажок ✨ AI edit в главном окне.",
            parent=_get_app_parent() or _root,
        )
        return
    
    try:
        raw = _get_text()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось получить текст из редактора: {e}", parent=_get_app_parent() or _root)
        return

    if not raw or raw == _placeholder or not raw.strip():
        messagebox.showwarning("Пустой текст", "Текст в редакторе пустой.", parent=_get_app_parent() or _root)
        return

    _set_button_state(improve_btn, "disabled")
    _set_button_state(chat_send_btn, "disabled")
    set_chat_status("Улучшаю текст для TTS...")

    def _worker():
        try:
            import engine.gpt_client as _gpt
            result = _gpt.improve_for_tts(raw)
            result = "" if result is None else str(result)

            def _apply():
                try:
                    _set_text(result)
                    append_chat_message(
                        "system",
                        f"Текст улучшен для TTS: {len(raw)} → {len(result)} символов",
                    )
                    set_chat_status("Текст обновлён в редакторе")
                except Exception as e:
                    messagebox.showerror(
                        "Ошибка",
                        f"Не удалось вставить результат в редактор: {e}",
                        parent=_get_app_parent() or _root,
                    )
                    set_chat_status("Ошибка вставки результата")
                finally:
                    _set_button_state(improve_btn, "normal")
                    _set_button_state(chat_send_btn, "normal")

            _safe_after(0, _apply)

        except Exception as e:
            msg = str(e) or "Неизвестная ошибка"

            def _show_error():
                _set_button_state(improve_btn, "normal")
                _set_button_state(chat_send_btn, "normal")
                set_chat_status(f"Ошибка улучшения текста: {msg}")
                messagebox.showerror("Ошибка AI", msg, parent=_get_app_parent() or _root)

            _safe_after(0, _show_error)

    threading.Thread(target=_worker, daemon=True).start()


def open_editor_text_window(event=None):
    global _editor_window
    global editor_source_text, editor_comment_text, editor_stats_label, editor_status_label

    if _get_text is None or _set_text is None:
        messagebox.showerror(
            "Ошибка",
            "Функции доступа к редактору не инициализированы.",
            parent=_get_app_parent() or _root,
        )
        return "break"

    if _widget_exists(_editor_window):
        _show_window(_editor_window)
        return "break"

    try:
        text = _get_text()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось получить текст из редактора: {e}", parent=_get_app_parent() or _root)
        return "break"

    if not text or text == _placeholder or not text.strip():
        messagebox.showwarning("Пустой текст", "В редакторе нет текста.", parent=_get_app_parent() or _root)
        return "break"

    win = tk.Toplevel(_get_app_parent() or _root)
    _set_dark_titlebar(win)
    _editor_window = win
    win.title("📋 Текст из редактора")
    win.geometry("900x720")
    win.minsize(700, 560)
    win.resizable(True, True)
    win.configure(bg=_c("BG_DARK"))
    win.transient(_get_app_parent() or _root)

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
        if _get_text is None:
            return
        try:
            src = _get_text()
            if not src or src == _placeholder or not src.strip():
                messagebox.showwarning("Пустой текст", "В редакторе нет текста.", parent=win)
                return
            editor_source_text.delete("1.0", tk.END)
            editor_source_text.insert("1.0", src)
            _update_editor_stats()
            set_chat_status("Источник обновлён из редактора")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обновить текст: {e}", parent=win)

    def copy_source():
        selected = _get_selected_or_all_text(editor_source_text)
        if not selected.strip():
            return
        _copy_to_clipboard(selected)

    def overwrite_editor_from_selection():
        if _set_text is None:
            return
        selected = _get_selected_or_all_text(editor_source_text).strip()
        if not selected:
            messagebox.showwarning("Пустое выделение", "Выделите фрагмент текста в верхнем окне.", parent=win)
            return
        try:
            _set_text(selected)
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

    editor_source_text = tk.Text(
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
    editor_source_text.pack(fill="both", expand=True)
    editor_source_text.lift() 
    src_scroll.config(command=editor_source_text.yview)

    editor_source_text.insert("1.0", text)

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

    editor_comment_text = tk.Text(
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
    editor_comment_text.pack(fill="both", expand=True)
    comment_scroll.config(command=editor_comment_text.yview)

    _create_placeholder_overlay(
        comment_inner,
        editor_comment_text,
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

    editor_stats_label = TkLabel(
        info_row,
        text="Источник: 0 симв. · Комментарий: 0 симв. · Итого: 0 симв.",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 8),
        anchor="w",
    )
    editor_stats_label.pack(side="left", fill="x", expand=True)

    editor_status_label = TkLabel(
        info_row,
        text="Enter — отправить и закрыть · Esc — закрыть",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MUTED"),
        font=("Segoe UI", 8),
        anchor="e",
    )
    editor_status_label.pack(side="right")

    btn_row = TkFrame(main, bg=_c("BG_DARK"))
    btn_row.pack(fill="x")

    def build_prompt() -> str:
        return _build_editor_compose_prompt(
            _get_widget_text(editor_source_text),
            _get_widget_text(editor_comment_text),
        )

    def close_editor():
        global _editor_window, editor_source_text, editor_comment_text, editor_stats_label, editor_status_label
        try:
            win.destroy()
        except Exception:
            pass
        _editor_window = None
        editor_source_text = None
        editor_comment_text = None
        editor_stats_label = None
        editor_status_label = None

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
        src = _get_widget_text(editor_source_text).strip()
        if not src:
            messagebox.showwarning("Пустой текст", "Нет текста в верхнем окне.", parent=win)
            return

        _set_button_state(improve_editor_btn, "disabled")
        if _widget_exists(editor_status_label):
            try:
                editor_status_label.config(text="Улучшаю текст… (авто-fallback при лимите)")
            except Exception:
                pass

        def _worker():
            try:
                import engine.gpt_client as _gpt
                result = _gpt.improve_for_tts(src)

                def _apply():
                    if _widget_exists(editor_source_text):
                        editor_source_text.delete("1.0", tk.END)
                        editor_source_text.insert("1.0", result or "")
                    _update_editor_stats()
                    _set_button_state(improve_editor_btn, "normal")
                    if _widget_exists(editor_status_label):
                        try:
                            editor_status_label.config(
                                text=f"Готово: {len(src)} → {len(result or '')} симв."
                            )
                        except Exception:
                            pass

                _safe_after(0, _apply)

            except Exception as e:
                msg = str(e) or "Неизвестная ошибка"

                def _show_err():
                    _set_button_state(improve_editor_btn, "normal")
                    if _widget_exists(editor_status_label):
                        try:
                            editor_status_label.config(text=f"Ошибка: {msg[:80]}")
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
        if not _widget_exists(editor_stats_label):
            return
        src = _get_widget_text(editor_source_text)
        cmt = _get_widget_text(editor_comment_text)
        total = len((src or "").strip()) + len((cmt or "").strip())
        try:
            editor_stats_label.config(
                text=f"Источник: {len(src)} симв. · Комментарий: {len(cmt)} симв. · Итого: {total} симв."
            )
        except Exception:
            pass
        _sync_text_placeholder(editor_comment_text)

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

    editor_source_text.bind("<KeyRelease>", lambda e: _update_editor_stats())
    editor_comment_text.bind("<FocusIn>", lambda e: _sync_text_placeholder(editor_comment_text))
    editor_comment_text.bind("<FocusOut>", lambda e: _sync_text_placeholder(editor_comment_text))
    editor_comment_text.bind("<KeyRelease>", lambda e: _update_editor_stats())
    editor_comment_text.bind("<Return>", _comment_enter)

    _bind_text_hotkeys(editor_source_text, extra_handlers)
    _bind_text_hotkeys(editor_comment_text, extra_handlers)

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
        editor_comment_text.focus_set()
    except Exception:
        pass

    return "break"


def _insert_prompt_into_chat_input(prompt: str):
    if not _widget_exists(chat_input):
        return

    prompt = (prompt or "").strip()
    if not prompt:
        return

    _clear_input_placeholder()
    try:
        current = _get_input_text().strip()
        if current:
            sep = "\n" if current.endswith("\n") else "\n\n"
            chat_input.insert(tk.END, sep + prompt)
        else:
            chat_input.insert(tk.END, prompt)
        chat_input.focus_set()
        _resize_input()
        _update_token_counter()
        _sync_text_placeholder(chat_input)
    except Exception as e:
        set_chat_status(f"Ошибка вставки: {e}")


def paste_from_editor():
    if _get_text is None:
        return
    try:
        text = _get_text()
    except Exception:
        return
    if not text or text == _placeholder or not text.strip():
        set_chat_status("Редактор пуст")
        return

    global _editor_mode
    _editor_mode = True

    _show_editor_preview(text)
    _update_input_placeholder_text("Добавьте комментарий… или нажмите Enter чтобы отправить как есть")
    if _hint_text_var is not None:
        try:
            _hint_text_var.set("Enter — отправить · Ctrl+Enter — без комментария · ✕ — отмена")
        except Exception:
            pass
    set_chat_status("Текст из редактора готов · добавьте комментарий или нажмите Enter")

    # Жёстко переводим фокус в поле ввода чата с несколькими попытками,
    # т.к. pack(before=...) в _show_editor_preview меняет геометрию
    # и фокус может временно "зависать" на других виджетах.
    _focus_chat_input()
    _safe_after(200, _focus_chat_input)


def export_current_chat():
    session = _get_current_session()
    messages = session.get("messages", [])

    if not messages:
        messagebox.showinfo("Экспорт", "В текущем чате нет сообщений.", parent=_get_app_parent() or _root)
        return

    safe_title = "".join(
        ch for ch in session.get("title", "chat")
        if ch.isalnum() or ch in (" ", "_", "-")
    ).strip()
    if not safe_title:
        safe_title = "chat"

    default_name = f"{safe_title[:40]}.txt"

    path = filedialog.asksaveasfilename(
        parent=_get_app_parent() or _root,
        title="Экспорт текущего чата",
        defaultextension=".txt",
        initialfile=default_name,
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
    )

    if not path:
        return

    try:
        lines = [
            "XTTS Studio AI Chat",
            f"Title: {session.get('title', 'Новый чат')}",
            f"Created: {session.get('created', '')}",
            "",
            "-" * 60,
            "",
        ]

        for m in messages:
            role = m.get("role", "assistant")
            role_name = {
                "user": "Вы",
                "assistant": "AI",
                "system": "Система",
            }.get(role, role)
            ts = m.get("ts", "")
            content = m.get("content", "")
            lines.append(f"[{ts}] {role_name}:")
            lines.append(content)
            lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        set_chat_status(f"Чат экспортирован: {os.path.basename(path)}")

    except Exception as e:
        messagebox.showerror("Ошибка экспорта", str(e), parent=_get_app_parent() or _root)
        set_chat_status("Ошибка экспорта")


# ─────────────────────────────────────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────────────────────────────────────

def open_search(event=None):
    global _search_window, _search_results

    if not _widget_exists(_chat_window):
        return "break"

    if _widget_exists(_search_window):
        _show_window(_search_window)
        return "break"

    # Если открыто модальное окно настроек, временно снимаем grab,
    # чтобы поиск мог получить фокус.
    try:
        if _root is not None:
            grab = _root.grab_current()
            if grab is not None:
                grab.grab_release()
    except Exception:
        pass

    win = tk.Toplevel(_chat_window)
    _set_dark_titlebar(win)
    _search_window = win
    win.title("Поиск по истории")
    win.geometry("560x430")
    win.minsize(420, 300)
    win.configure(bg=_c("BG_DARK"))
    win.transient(_chat_window)


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

    _search_results = []

    def do_search(event=None):
        global _search_results

        query = entry.get().strip().lower()
        results.delete(0, tk.END)
        _search_results = []

        if not query:
            status.config(text="Введите запрос")
            return "break"

        for s in _sessions:
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
                    _search_results.append((s.get("id"), idx))

        status.config(text=f"Найдено: {len(_search_results)}")
        return "break"

    def open_result(event=None):
        global _current_session_id

        sel = results.curselection()
        if not sel:
            if len(_search_results) == 1:
                sel = (0,)
            else:
                return "break"

        idx = sel[0]
        if idx >= len(_search_results):
            return "break"

        sid, _msg_idx = _search_results[idx]
        _current_session_id = sid
        _render_current_session()
        _refresh_session_list()
        set_chat_status("Открыт чат из результатов поиска")
        _show_window(_chat_window)
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
        global _search_window
        try:
            win.destroy()
        except Exception:
            pass
        _search_window = None
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


# ─────────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────────

def open_gpt_settings(event=None):
    global _settings_window

    try:
        from engine import gpt_client
    except Exception as e:
        messagebox.showerror("Настройки AI", f"Не удалось загрузить engine.gpt_client: {e}", parent=_get_app_parent() or _root)
        return "break"

    if _widget_exists(_settings_window):
        _show_window(_settings_window)
        return "break"

    import webbrowser
    _prov_list_ref = [None]

    win = tk.Toplevel(_get_app_parent() or _root)
    _set_dark_titlebar(win)
    _settings_window = win
    win.title("⚙ Настройки AI")
    win.geometry("600x680")
    win.minsize(520, 420)
    win.resizable(True, True)
    win.configure(bg=_c("BG_CARD"))
    win.transient(_get_app_parent() or _root)
    

# ── Скроллируемый каркас ────────────────────────────────────────────────
    settings_canvas = tk.Canvas(
        win, bg=_c("BG_CARD"), highlightthickness=0, bd=0,
    )
    settings_scrollbar = tk.Scrollbar(win, orient="vertical", command=settings_canvas.yview)

    _scroll_save_id = [None]

    def _save_scroll_pos():
        try:
            gpt_client.set_ui_state(scroll_y=settings_canvas.yview()[0])
        except Exception:
            pass

    def _debounced_save_scroll():
        if _scroll_save_id[0] is not None:
            try:
                win.after_cancel(_scroll_save_id[0])
            except Exception:
                pass
        _scroll_save_id[0] = win.after(400, _save_scroll_pos)

    def _on_settings_yscroll(*args):
        settings_scrollbar.set(*args)
        _debounced_save_scroll()

    settings_canvas.configure(yscrollcommand=_on_settings_yscroll)

    settings_scrollbar.pack(side="right", fill="y")
    settings_canvas.pack(side="left", fill="both", expand=True)

    settings_scroll_frame = TkFrame(settings_canvas, bg=_c("BG_CARD"))

    # Принудительно обновляем геометрию ДО создания canvas-window, чтобы
    # winfo_width() вернул реальную ширину, а не 1px по умолчанию —
    # иначе при первом открытии содержимое "залипает" в узкой колонке слева
    # или съезжает, т.к. canvas_window получает неверную стартовую ширину.
    win.update_idletasks()
    initial_width = settings_canvas.winfo_width() or 580

    settings_canvas_window = settings_canvas.create_window(
        (0, 0), window=settings_scroll_frame, anchor="nw", width=initial_width,
    )

    def _on_settings_frame_configure(event=None):
        try:
            settings_canvas.configure(scrollregion=settings_canvas.bbox("all"))
        except Exception:
            pass

    def _on_settings_canvas_configure(event):
        try:
            settings_canvas.itemconfig(settings_canvas_window, width=event.width)
        except Exception:
            pass

    settings_scroll_frame.bind("<Configure>", _on_settings_frame_configure)
    settings_canvas.bind("<Configure>", _on_settings_canvas_configure)

    def _settings_mousewheel(event):
        try:
            if getattr(event, "num", None) == 4:
                units = -3
            elif getattr(event, "num", None) == 5:
                units = 3
            else:
                delta = int(getattr(event, "delta", 0) or 0)
                if delta == 0:
                    return None
                units = -3 if delta > 0 else 3
            settings_canvas.yview_scroll(units, "units")
            return "break"
        except Exception:
            return None

    for _target in (win, settings_canvas, settings_scroll_frame):
        try:
            _target.bind("<MouseWheel>", _settings_mousewheel, add="+")
            _target.bind("<Button-4>", _settings_mousewheel, add="+")
            _target.bind("<Button-5>", _settings_mousewheel, add="+")
        except Exception:
            pass

    # Финальная синхронизация ширины после того, как весь контент окна
    # будет создан и упакован (вызывается в самом конце функции, см. ниже).
    def _finalize_settings_layout():
        try:
            win.update_idletasks()
            settings_canvas.itemconfig(settings_canvas_window, width=settings_canvas.winfo_width())
            settings_canvas.configure(scrollregion=settings_canvas.bbox("all"))
        except Exception:
            pass
    

    get_provider = getattr(gpt_client, "get_provider", None)
    set_provider = getattr(gpt_client, "set_provider", None)
    get_provider_info = getattr(gpt_client, "get_provider_info", None)
    providers_map = getattr(gpt_client, "PROVIDERS", None)

    get_api_key = getattr(gpt_client, "get_api_key", None)
    set_api_key = getattr(gpt_client, "set_api_key", None)
    validate_key = getattr(gpt_client, "validate_key", None)
    get_model = getattr(gpt_client, "get_model", None)
    set_model = getattr(gpt_client, "set_model", None)

    multi_provider = callable(get_provider) and callable(get_provider_info) and isinstance(providers_map, dict)

    try:
        current_provider = get_provider() if multi_provider else "groq"
    except Exception:
        current_provider = "groq"

    def _models_for(provider: str) -> list:
        if multi_provider:
            try:
                return list(get_provider_info(provider).get("models", []) or [])
            except Exception:
                return []
        return list(getattr(gpt_client, "AVAILABLE_MODELS", []) or [])

    def _default_model_for(provider: str) -> str:
        if multi_provider:
            try:
                return get_provider_info(provider).get("default_model", "")
            except Exception:
                return ""
        return getattr(gpt_client, "DEFAULT_MODEL", "")

    try:
        current_key = (get_api_key(current_provider) if multi_provider else get_api_key()) if callable(get_api_key) else ""
    except Exception:
        current_key = ""

    try:
        current_model = (get_model(current_provider) if multi_provider else get_model()) if callable(get_model) else _default_model_for(current_provider)
    except Exception:
        current_model = _default_model_for(current_provider)

    # ── Провайдер ────────────────────────────────────────────────────────────
    provider_var = tk.StringVar(value=current_provider)

    list_custom_providers = getattr(gpt_client, "list_custom_providers", None)
    add_custom_provider = getattr(gpt_client, "add_custom_provider", None)
    update_custom_provider = getattr(gpt_client, "update_custom_provider", None)
    delete_custom_provider = getattr(gpt_client, "delete_custom_provider", None)
    has_custom_providers = callable(list_custom_providers) and callable(add_custom_provider)

    def _open_provider_form(edit_pid: str = None):
        """Форма добавления/редактирования кастомного провайдера."""
        is_edit = edit_pid is not None
        existing = {}
        if is_edit and callable(list_custom_providers):
            for p in list_custom_providers():
                if p.get("id") == edit_pid:
                    existing = p
                    break

        form = tk.Toplevel(win)
        _set_dark_titlebar(form)
        form.title("Редактировать провайдер" if is_edit else "Добавить провайдер")
        form.geometry("480x540")
        form.minsize(400, 460)
        form.resizable(True, True)
        form.configure(bg=_c("BG_CARD"))
        form.transient(win)
        form.grab_set()

        def _field(parent, label_text, initial="", height=1):
            TkLabel(
                parent, text=label_text,
                bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
                font=("Segoe UI", 9), anchor="w",
            ).pack(fill="x", padx=16, pady=(10, 3))
            if height == 1:
                var = tk.StringVar(value=initial)
                e = tk.Entry(
                    parent, textvariable=var,
                    bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"),
                    insertbackground=_c("TEXT_MAIN"),
                    relief="flat", highlightthickness=1,
                    highlightbackground=_c("BORDER"),
                    highlightcolor=_c("ACCENT"),
                    font=("Segoe UI", 9),
                )
                e.pack(fill="x", padx=16, ipady=5)
                _bind_text_hotkeys(e)
                return var, e
            else:
                frame = TkFrame(parent, bg=_c("BORDER"), padx=1, pady=1)
                frame.pack(fill="x", padx=16)
                inner = TkFrame(frame, bg=_c("BG_INPUT"))
                inner.pack(fill="x")
                t = tk.Text(
                    inner, height=height, wrap="word",
                    bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"),
                    insertbackground=_c("TEXT_MAIN"),
                    relief="flat", highlightthickness=0,
                    font=("Segoe UI", 9), padx=6, pady=6,
                )
                t.insert("1.0", initial)
                t.pack(fill="x")
                _bind_text_hotkeys(t)
                return t, t

        label_var, _ = _field(form, "Название", existing.get("label", ""))
        url_var, _ = _field(form, "URL эндпоинта (/v1/chat/completions)", existing.get("url", ""))

        models_initial = "\n".join(existing.get("models", []))
        models_text, _ = _field(form, "Модели (каждая с новой строки)", models_initial, height=4)

        fallback_var, _ = _field(form, "Fallback модель (при лимите)", existing.get("fallback_model", ""))

        headers_initial = "\n".join(
            f"{k}: {v}" for k, v in (existing.get("extra_headers") or {}).items()
        )
        headers_text, _ = _field(form, "Доп. заголовки (необязательно, формат «Key: Value», каждый с новой строки)", headers_initial, height=3)

        if is_edit:
            try:
                id_entry.config(state="disabled")
            except Exception:
                pass

        form_status = TkLabel(
            form, text="",
            bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
            font=("Segoe UI", 9), anchor="w",
        )
        form_status.pack(fill="x", padx=16, pady=(8, 0))

        btn_row_f = TkFrame(form, bg=_c("BG_CARD"))
        btn_row_f.pack(fill="x", padx=16, pady=(6, 16))

        def _save_form():
            if is_edit:
                pid_val = edit_pid
            else:
                lbl_raw = (label_var.get() if isinstance(label_var, tk.StringVar) else label_var).strip()
                pid_val = lbl_raw.lower().replace(" ", "_")
                # убираем всё кроме латиницы, цифр и _
                import re as _re
                pid_val = _re.sub(r"[^a-z0-9_]", "", pid_val) or "custom"
            lbl_val = (label_var.get() if isinstance(label_var, tk.StringVar) else label_var).strip()
            url_val = (url_var.get() if isinstance(url_var, tk.StringVar) else url_var).strip()

            raw_models = models_text.get("1.0", "end-1c") if isinstance(models_text, tk.Text) else ""
            models_list = [m.strip() for m in raw_models.splitlines() if m.strip()]

            fb_val = (fallback_var.get() if isinstance(fallback_var, tk.StringVar) else fallback_var).strip()
            if not fb_val and models_list:
                fb_val = models_list[0]

            raw_headers = headers_text.get("1.0", "end-1c") if isinstance(headers_text, tk.Text) else ""
            extra_h = {}
            for line in raw_headers.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    k, v = k.strip(), v.strip()
                    if k:
                        extra_h[k] = v

            if not url_val:
                form_status.config(text="URL не может быть пустым", fg=_c("TEXT_ERROR"))
                return
            if not models_list:
                form_status.config(text="Укажите хотя бы одну модель", fg=_c("TEXT_ERROR"))
                return

            try:
                if is_edit:
                    update_custom_provider(edit_pid, label=lbl_val, url=url_val,
                                           models=models_list, default_model=models_list[0],
                                           fallback_model=fb_val, extra_headers=extra_h)
                else:
                    add_custom_provider(pid_val, lbl_val, url_val, models_list, fb_val, extra_h)
                _rebuild_accordion()
                form.destroy()
            except Exception as e:
                form_status.config(text=str(e), fg=_c("TEXT_ERROR"))

        def _close_form(event=None):
            try:
                form.grab_release()
                form.destroy()
            except Exception:
                pass

        _make_button(
            btn_row_f, "✕ Отмена", _close_form,
            bg=_c("BG_INPUT"), font_size=9, height=1, padx=8, pady=3,
        ).pack(side="right", padx=(6, 0))
        _make_button(
            btn_row_f, "💾 Сохранить", _save_form,
            bg=_c("BG_ACTIVE"), font_size=9, height=1, padx=8, pady=3,
        ).pack(side="right")

        form.bind("<Escape>", _close_form)
        form.protocol("WM_DELETE_WINDOW", _close_form)

    def _open_catalogue():
        cat = getattr(gpt_client, "PROVIDER_CATALOGUE", [])
        fetch_models = getattr(gpt_client, "fetch_models_from_url", None)
        if not cat:
            messagebox.showinfo("Каталог", "Каталог провайдеров недоступен.", parent=win)
            return

        dlg = tk.Toplevel(win)
        _set_dark_titlebar(dlg)
        dlg.title("Каталог провайдеров")
        dlg.geometry("560x520")
        dlg.minsize(460, 400)
        dlg.resizable(True, True)
        dlg.configure(bg=_c("BG_CARD"))
        dlg.transient(win)
        dlg.grab_set()

        TkLabel(
            dlg, text="Выберите провайдера из каталога",
            bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        TkLabel(
            dlg, text="Двойной клик или «Добавить» — подключить провайдера",
            bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=16, pady=(0, 8))

        list_outer = TkFrame(dlg, bg=_c("BORDER"), padx=1, pady=1)
        list_outer.pack(fill="both", expand=True, padx=16)

        cat_scroll = tk.Scrollbar(list_outer)
        cat_scroll.pack(side="right", fill="y")

        cat_listbox = tk.Listbox(
            list_outer,
            bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"),
            selectbackground=_c("ACCENT"), selectforeground="#ffffff",
            activestyle="none", relief="flat", highlightthickness=0,
            font=("Segoe UI", 9),
            yscrollcommand=cat_scroll.set,
        )
        cat_listbox.pack(fill="both", expand=True)
        cat_scroll.config(command=cat_listbox.yview)

        already = set(pid for pid, _, _ in _all_provider_entries())
        for entry in cat:
            pid = entry.get("id", "")
            lbl = entry.get("label", pid)
            notes = entry.get("notes", "")
            suffix = "  ✓ уже добавлен" if pid in already else ""
            cat_listbox.insert(tk.END, f"{lbl}{suffix}  —  {notes}")

        info_lbl = TkLabel(
            dlg, text="Выберите провайдера из списка",
            bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
            font=("Segoe UI", 8), anchor="w", wraplength=500,
        )
        info_lbl.pack(fill="x", padx=16, pady=(8, 0))

        status_lbl_cat = TkLabel(
            dlg, text="",
            bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
            font=("Segoe UI", 8), anchor="w",
        )
        status_lbl_cat.pack(fill="x", padx=16, pady=(2, 0))

        def _on_cat_select(event=None):
            sel = cat_listbox.curselection()
            if not sel:
                return
            entry = cat[sel[0]]
            hint = entry.get("key_hint", "")
            notes = entry.get("notes", "")
            info_lbl.config(text=f"{notes}  |  Ключ: {hint}")

        cat_listbox.bind("<<ListboxSelect>>", _on_cat_select)

        def _add_from_catalogue(event=None):
            sel = cat_listbox.curselection()
            if not sel:
                messagebox.showinfo("Каталог", "Выберите провайдера.", parent=dlg)
                return

            entry = cat[sel[0]]
            pid = entry.get("id", "")

            existing_ids = set(pid for pid, _, _ in _all_provider_entries())
            if pid in existing_ids:
                messagebox.showinfo("Каталог", f"Провайдер «{entry.get('label')}» уже добавлен.", parent=dlg)
                return

            models_url = entry.get("models_url")
            api_key = key_var.get().strip()

            status_lbl_cat.config(text="Загружаю список моделей...", fg=_c("ACCENT"))
            dlg.update_idletasks()

            def _worker():
                models = []
                if callable(fetch_models) and models_url:
                    models = fetch_models(models_url, api_key)
                if not models:
                    models = entry.get("models", [])

                def _apply():
                    if not models:
                        status_lbl_cat.config(
                            text="Модели не загрузились — добавлю провайдера без списка моделей. Введите вручную.",
                            fg=_c("WARNING"),
                        )
                    else:
                        status_lbl_cat.config(
                            text=f"Загружено моделей: {len(models)}",
                            fg=_c("TEXT_SUCCESS"),
                        )

                    try:
                        add_custom_provider(
                            pid,
                            entry.get("label", pid),
                            entry.get("url", ""),
                            models,
                            models[0] if models else "",
                            entry.get("extra_headers", {}),
                            key_hint=entry.get("key_hint", ""),
                        )
                        _rebuild_accordion()
                        # Открываем форму редактирования чтобы пользователь
                        # мог выбрать primary/fallback модель и ввести ключ
                        dlg.destroy()
                        _open_provider_form(edit_pid=pid)
                    except Exception as e:
                        status_lbl_cat.config(text=str(e), fg=_c("TEXT_ERROR"))

                _safe_after(0, _apply)

            import threading as _threading
            _threading.Thread(target=_worker, daemon=True).start()

        btn_row_cat = TkFrame(dlg, bg=_c("BG_CARD"))
        btn_row_cat.pack(fill="x", padx=16, pady=(8, 16))

        _make_button(
            btn_row_cat, "✕ Закрыть",
            lambda: (dlg.grab_release(), dlg.destroy()),
            bg=_c("BG_INPUT"), font_size=9, height=1, padx=8, pady=3,
        ).pack(side="right", padx=(6, 0))

        _make_button(
            btn_row_cat, "＋ Добавить", _add_from_catalogue,
            bg=_c("BG_ACTIVE"), font_size=9, height=1, padx=8, pady=3,
        ).pack(side="right")

        cat_listbox.bind("<Double-Button-1>", _add_from_catalogue)
        dlg.bind("<Escape>", lambda e: (dlg.grab_release(), dlg.destroy()))
        dlg.protocol("WM_DELETE_WINDOW", lambda: (dlg.grab_release(), dlg.destroy()))

    # ── Провайдеры (аккордеон) ──────────────────────────────────────────────
    _ui_state = gpt_client.get_ui_state() if multi_provider else {}
    accordion_state = {"expanded": _ui_state.get("expanded_provider")}
    if multi_provider:
        prov_header_row = TkFrame(settings_scroll_frame, bg=_c("BG_CARD"))
        prov_header_row.pack(fill="x", padx=20, pady=(18, 6))
        TkLabel(
            prov_header_row, text="Провайдеры AI",
            bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), font=("Segoe UI", 10),
        ).pack(side="left")
        accordion_container = TkFrame(settings_scroll_frame, bg=_c("BG_CARD"))
        accordion_container.pack(fill="x", padx=20)
        def _all_provider_entries():
            entries = []
            hidden = gpt_client.get_hidden_providers()
            for pid, info in providers_map.items():
                if pid in hidden:
                    continue
                entries.append((pid, info, False))
            if callable(list_custom_providers):
                for p in list_custom_providers():
                    entries.append((p.get("id"), p, True))
            return entries
        def _toggle_card(pid):
            accordion_state["expanded"] = None if accordion_state["expanded"] == pid else pid
            try:
                gpt_client.set_ui_state(expanded_provider=accordion_state["expanded"])
            except Exception:
                pass
            _rebuild_accordion()
        def _rebuild_accordion():
            for child in accordion_container.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass
            active_pid = get_provider()
            for pid, info, is_custom in _all_provider_entries():
                is_expanded = accordion_state["expanded"] == pid
                is_active = pid == active_pid
                card_outer = tk.Frame(accordion_container, bg=_c("BORDER"))
                card_outer.pack(fill="x", pady=(0, 6))
                card = tk.Frame(card_outer, bg=_c("BG_CARD"))
                card.pack(fill="x", padx=1, pady=1)
                header = tk.Frame(card, bg=_c("BG_CARD"), cursor="hand2")
                header.pack(fill="x", padx=12, pady=10)
                arrow = "▾" if is_expanded else "▸"
                dot = "🟢" if is_active else ("🔧" if is_custom else "⚪")
                tk.Label(header, text=arrow, bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
                         font=("Segoe UI", 9), width=2).pack(side="left")
                tk.Label(header, text=dot, bg=_c("BG_CARD"),
                         font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))
                title_box = tk.Frame(header, bg=_c("BG_CARD"))
                title_box.pack(side="left", fill="x", expand=True)
                tk.Label(title_box, text=info.get("label", pid), bg=_c("BG_CARD"),
                         fg=_c("TEXT_MAIN"), font=("Segoe UI", 10),
                         anchor="w").pack(anchor="w")
                try:
                    cur_model = get_model(pid) if callable(get_model) else ""
                except Exception:
                    cur_model = ""
                has_key = bool(get_api_key(pid)) if callable(get_api_key) else False
                sub = f"{'✅ ключ задан' if has_key else '❌ нет ключа'} · {cur_model or '—'}"
                tk.Label(title_box, text=sub, bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
                         font=("Segoe UI", 8), anchor="w").pack(anchor="w")
                if is_active:
                    tk.Label(header, text="АКТИВНЫЙ", bg=_c("BG_CARD"),
                             fg=_c("TEXT_SUCCESS"), font=("Segoe UI", 8, "bold")
                             ).pack(side="right")
                for w in [header, title_box] + list(header.winfo_children()) + list(title_box.winfo_children()):
                    try:
                        w.bind("<Button-1>", lambda e, p=pid: _toggle_card(p))
                    except Exception:
                        pass
                if not is_expanded:
                    continue
                body = tk.Frame(card, bg=_c("BG_CARD"))
                body.pack(fill="x", padx=12, pady=(0, 12))
                tk.Frame(body, bg=_c("BORDER"), height=1).pack(fill="x", pady=(0, 10))
                TkLabel(body, text="API Key", bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
                        font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(0, 4))
                card_key_var = tk.StringVar(value=get_api_key(pid) if callable(get_api_key) else "")
                key_row = tk.Frame(body, bg=_c("BG_CARD"))
                key_row.pack(fill="x")
                ke = tk.Entry(
                    key_row, textvariable=card_key_var, show="•",
                    bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"), insertbackground=_c("TEXT_MAIN"),
                    relief="flat", highlightthickness=1, highlightbackground=_c("BORDER"),
                    highlightcolor=_c("ACCENT"), font=("Consolas", 9),
                )
                ke.pack(side="left", fill="x", expand=True, ipady=5)
                _bind_text_hotkeys(ke)
                show_v = tk.BooleanVar(value=False)
                tk.Checkbutton(
                    key_row, text="👁", variable=show_v,
                    command=lambda e=ke, v=show_v: e.config(show="" if v.get() else "•"),
                    bg=_c("BG_CARD"), fg=_c("TEXT_DIM"), selectcolor=_c("BG_INPUT"),
                    activebackground=_c("BG_CARD"), relief="flat", font=("Segoe UI", 8),
                ).pack(side="left", padx=(6, 0))
                hint = info.get("key_hint", "")
                if hint:
                    url = hint if hint.startswith("http") else f"https://{hint}"
                    link_lbl = tk.Label(
                        body, text=hint, bg=_c("BG_CARD"), fg=_c("ACCENT"),
                        font=("Segoe UI", 10), cursor="hand2", anchor="w",
                    )
                    link_lbl.pack(fill="x", pady=(3, 8))
                    link_lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                TkLabel(body, text="Модель", bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
                        font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(4, 4))
                models = list(info.get("models", []) or [])
                card_model_var = tk.StringVar(value=cur_model or (models[0] if models else ""))
                if models:
                    for m in models:
                        tk.Radiobutton(
                            body, text=m, variable=card_model_var, value=m,
                            bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), selectcolor=_c("BG_INPUT"),
                            activebackground=_c("BG_CARD"), font=("Segoe UI", 9),
                            anchor="w", cursor="hand2",
                        ).pack(fill="x", anchor="w")
                else:
                    TkLabel(body, text="Список моделей пуст.", bg=_c("BG_CARD"),
                            fg=_c("TEXT_DIM"), font=("Segoe UI", 9)).pack(anchor="w")
                card_status = TkLabel(body, text="", bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
                                      font=("Segoe UI", 8), anchor="w")
                card_status.pack(fill="x", pady=(8, 4))
                def _save_card(p=pid, kv=card_key_var, mv=card_model_var, st=card_status):
                    try:
                        if callable(set_api_key):
                            set_api_key(kv.get().strip(), p)
                        if callable(set_model) and mv.get():
                            set_model(mv.get(), p)
                        st.config(text="💾 Сохранено", fg=_c("TEXT_SUCCESS"))
                        _rebuild_accordion()
                    except Exception as e:
                        st.config(text=str(e), fg=_c("TEXT_ERROR"))
                def _test_card(p=pid, kv=card_key_var, st=card_status):
                    if not callable(validate_key):
                        st.config(text="Проверка недоступна", fg=_c("WARNING"))
                        return
                    st.config(text="Проверка ключа...", fg=_c("TEXT_DIM"))
                    def worker():
                        try:
                            ok, msg = validate_key(kv.get().strip(), p)
                            _safe_after(0, lambda: st.config(
                                text=str(msg),
                                fg=_c("TEXT_SUCCESS") if ok else _c("TEXT_ERROR"),
                            ))
                        except Exception as e:
                            _safe_after(0, lambda err=e: st.config(text=str(err), fg=_c("TEXT_ERROR")))
                    threading.Thread(target=worker, daemon=True).start()
                def _activate_card(p=pid, st=card_status):
                    try:
                        if callable(set_provider):
                            set_provider(p)
                        _rebuild_accordion()
                    except Exception as e:
                        st.config(text=str(e), fg=_c("TEXT_ERROR"))
                btn_row = TkFrame(body, bg=_c("BG_CARD"))
                btn_row.pack(fill="x", pady=(2, 0))
                _make_button(btn_row, "🔑 Проверить", _test_card, bg=_c("BG_INPUT"),
                            font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True, padx=(0, 4))
                _make_button(btn_row, "💾 Сохранить", _save_card, bg=_c("BG_INPUT"),
                            font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True, padx=(0, 4))
                if not is_active:
                    _make_button(btn_row, "✓ Активным", _activate_card, bg=_c("BG_ACTIVE"),
                                font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True, padx=(0, 4))
                if is_custom:
                    def _edit_this(p=pid):
                        _open_provider_form(edit_pid=p)
                    def _delete_this(p=pid, lbl=info.get("label", pid)):
                        if not messagebox.askyesno(
                            "Удалить провайдер",
                            f"Удалить «{lbl}» без возможности восстановления?",
                            parent=win,
                        ):
                            return
                        try:
                            delete_custom_provider(p)
                            if accordion_state["expanded"] == p:
                                accordion_state["expanded"] = None
                                gpt_client.set_ui_state(expanded_provider=None)
                            _rebuild_accordion()
                        except Exception as e:
                            messagebox.showerror("Ошибка", str(e), parent=win)
                    _make_button(btn_row, "✎", _edit_this, bg=_c("BG_INPUT"),
                                font_size=8, height=1, width=3, padx=4, pady=2).pack(side="left", padx=(0, 4))
                    _make_button(btn_row, "🗑", _delete_this, bg=_c("BG_INPUT"),
                                font_size=8, height=1, width=3, padx=4, pady=2).pack(side="left")
                else:
                    def _hide_this(p=pid, lbl=info.get("label", pid)):
                        if not messagebox.askyesno(
                            "Скрыть провайдер",
                            f"Скрыть «{lbl}»? Ключ и модель будут забыты.",
                            parent=win,
                        ):
                            return
                        try:
                            gpt_client.hide_provider(p)
                            if accordion_state["expanded"] == p:
                                accordion_state["expanded"] = None
                                gpt_client.set_ui_state(expanded_provider=None)
                            _rebuild_accordion()
                        except Exception as e:
                            messagebox.showerror("Ошибка", str(e), parent=win)
                    _make_button(btn_row, "🚫 Скрыть", _hide_this, bg=_c("BG_INPUT"),
                                font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True)
            _finalize_settings_layout()
        prov_btn_row = TkFrame(settings_scroll_frame, bg=_c("BG_CARD"))
        prov_btn_row.pack(fill="x", padx=20, pady=(6, 0))
        def _add_provider():
            if has_custom_providers:
                _open_provider_form()
        _make_button(prov_btn_row, "＋ Добавить", _add_provider, bg=_c("BG_ACTIVE"),
                    font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True, padx=(0, 4))
        _make_button(prov_btn_row, "🌐 Каталог", lambda: _open_catalogue(), bg=_c("BG_INPUT"),
                    font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True)
        _rebuild_accordion()

    status_lbl = TkLabel(
        settings_scroll_frame,
        text="",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        anchor="w",
    )
    status_lbl.pack(fill="x", padx=20, pady=(8, 18))

    def close_settings(event=None):
        global _settings_window
        _settings_window = None
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            win.after(0, win.destroy)
        except Exception:
            pass
        return "break"

    def _open_search_shortcut(event=None):
        return open_search(event)

    win.bind("<Escape>", close_settings)
    _bind_window_hotkeys(win, {
        "f": _open_search_shortcut,
    })

    win.protocol("WM_DELETE_WINDOW", close_settings)
    win.focus_set()

    # Контент создан полностью — синхронизируем геометрию канваса в самом конце,
    # это убирает гонку, когда <Configure> срабатывает раньше, чем все виджеты
    # внутри settings_scroll_frame созданы.
    _safe_after(0, _finalize_settings_layout)
    _safe_after(50, _finalize_settings_layout)

    _saved_scroll_y = gpt_client.get_ui_state().get("scroll_y", 0.0)
    _safe_after(120, lambda: settings_canvas.yview_moveto(_saved_scroll_y))

    return "break"

# ─────────────────────────────────────────────────────────────────────────────
# Window
# ─────────────────────────────────────────────────────────────────────────────

def open_chat_window():
    global composer_outer_ref, composer_card_ref
    global _chat_window
    global session_listbox, chat_canvas, chat_scrollbar, chat_messages_frame, chat_canvas_window
    global chat_input, chat_input_placeholder_label, chat_send_btn, chat_status_label, chat_token_label
    global improve_btn, paste_editor_btn, clear_btn, export_btn, settings_btn, new_chat_btn, delete_chat_btn
    global _search_window, _settings_window, _editor_window
    global editor_source_text, editor_comment_text, editor_stats_label, editor_status_label

    if _root is None:
        raise RuntimeError("chat_window.init(...) must be called before open_chat_window().")

    _load_sessions()

    if _widget_exists(_chat_window):
        _show_window(_chat_window)
        return

    win = tk.Toplevel(_root)
    win.title("💬 AI Чат — XTTS Studio")
    win.geometry("920x650")
    win.minsize(520, 540)
    win.resizable(True, True)
    win.configure(bg=_c("BG_DARK"))
    _set_dark_titlebar(win)
    

    _chat_window = win

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

    new_chat_btn = _make_button(
        sidebar,
        "＋ Новый чат",
        new_chat,
        bg=_c("BG_ACTIVE"),
        font_size=8,
        height=1,
        padx=8,
        pady=3,
    )
    new_chat_btn.pack(fill="x", padx=10, pady=(0, 6))

    delete_chat_btn = _make_button(
        sidebar,
        "🗑 Удалить чат",
        delete_current_chat,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        padx=8,
        pady=3,
    )
    delete_chat_btn.pack(fill="x", padx=10, pady=(0, 10))

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

    session_listbox = tk.Listbox(
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
    session_listbox.pack(fill="both", expand=True)
    list_scroll.config(command=session_listbox.yview)
    session_listbox.bind("<<ListboxSelect>>", _on_session_select)

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

    export_btn = _make_button(
        header,
        "⬇ Экспорт",
        export_current_chat,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        padx=8,
        pady=2,
    )
    export_btn.pack(side="right", padx=(8, 0))

    settings_btn = _make_button(
        header,
        "⚙ Настройки",
        open_gpt_settings,
        bg=_c("BG_INPUT"),
        font_size=8,
        height=1,
        padx=8,
        pady=2,
    )
    settings_btn.pack(side="right", padx=(8, 0))

    # Status row — bottom
    status_row = TkFrame(right, bg=_c("BG_DARK"))
    status_row.pack(side="bottom", fill="x", padx=14, pady=(0, 6))

    chat_status_label = TkLabel(
        status_row,
        text="Готов к работе",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        anchor="w",
    )
    chat_status_label.pack(side="left", fill="x", expand=True)

    chat_token_label = TkLabel(
        status_row,
        text="Ввод: ≈0 ток. · Чат: ≈0 ток.",
        bg=_c("BG_DARK"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        anchor="e",
    )
    chat_token_label.pack(side="right")

    # Actions — bottom
    action_row = TkFrame(right, bg=_c("BG_DARK"))
    action_row.pack(side="bottom", fill="x", padx=14, pady=(0, 6))

    improve_btn = ctk.CTkButton(
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
    improve_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

    paste_editor_btn = ctk.CTkButton(
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
    paste_editor_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

    clear_btn = ctk.CTkButton(
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
    clear_btn.pack(side="left", fill="x", expand=True)

    # Input card — bottom
    composer_outer = TkFrame(right, bg=_c("BG_DARK"))
    composer_outer.pack(side="bottom", fill="x", padx=14, pady=(0, 14))
    composer_outer_ref = [composer_outer]

    composer_card = TkRawFrame(
        composer_outer,
        bg=_c("BG_CARD"),
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
    )
    composer_card.pack(fill="x")
    composer_card_ref = [composer_card]

    hint_row = TkRawFrame(composer_card, bg=_c("BG_CARD"))
    hint_row.pack(fill="x", padx=12, pady=(9, 5))

    global _hint_text_var
    _hint_text_var = tk.StringVar(value="Enter — отправить · Shift+Enter — новая строка · Ctrl+F — поиск")
    _hint_label = TkLabel(
        hint_row,
        textvariable=_hint_text_var,
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 11),
        anchor="w",
    )
    _hint_label.pack(side="left", fill="x", expand=True)

    def _toggle_free_chat():
        global _free_chat_mode
        _free_chat_mode = not _free_chat_mode
        try:
            _free_chat_btn.config(
                text="💬 Свободный чат ✓" if _free_chat_mode else "💬 Свободный чат",
                fg=_c("ACCENT") if _free_chat_mode else _c("TEXT_DIM"),
            )
        except Exception:
            pass
        set_chat_status("Режим: свободный чат" if _free_chat_mode else "Режим: редактор текста")
        _mode_label.config(
            text="режим: свободный чат" if _free_chat_mode else "режим: редактор",
            fg=_c("ACCENT") if _free_chat_mode else _c("TEXT_MUTED"),
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

    input_border = TkRawFrame(input_row, bg=_c("BORDER"),
                           highlightthickness=1, highlightbackground=_c("BORDER"))
    input_border.pack(side="left", fill="x", expand=True, padx=(0, 8))

    input_inner = TkRawFrame(input_border, bg=_c("BG_INPUT"))
    input_inner.pack(fill="x")

    chat_input = tk.Text(
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
    chat_input.pack(fill="x")
    chat_input.lift() 

    chat_input_placeholder_label = _create_placeholder_overlay(
        input_inner,
        chat_input,
        "Напишите сообщение…",
        x=13,
        y=11,
        fg=_c("TEXT_DIM"),
        bg=_c("BG_INPUT"),
        font=("Segoe UI", 9, "italic"),
    )

    chat_send_btn = tk.Button(
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
    chat_send_btn.pack(side="right")

    # Messages scrollable canvas — после всех bottom элементов, займёт оставшееся место
    canvas_outer = TkRawFrame(right, bg=_c("BORDER"), padx=1, pady=1)
    canvas_outer.pack(side="top", fill="both", expand=True, padx=14, pady=(0, 8))

    chat_scrollbar = tk.Scrollbar(canvas_outer)
    chat_scrollbar.pack(side="right", fill="y")

    chat_canvas = tk.Canvas(
        canvas_outer,
        bg=_c("BG_DARK"),
        highlightthickness=0,
        bd=0,
        yscrollcommand=chat_scrollbar.set,
    )
    chat_canvas.pack(side="left", fill="both", expand=True)
    chat_scrollbar.config(command=chat_canvas.yview)

    chat_messages_frame = TkFrame(chat_canvas, bg=_c("BG_DARK"), pady=50)
    chat_canvas_window = chat_canvas.create_window(
        (0, 0),
        window=chat_messages_frame,
        anchor="nw",
        width=1,
    )

    def on_frame_configure(event=None):
        try:
            chat_canvas.configure(scrollregion=chat_canvas.bbox("all"))
        except Exception:
            pass

    def on_canvas_configure(event):
        try:
            new_width = event.width
            old_width = getattr(chat_canvas, "_last_width", None)
            chat_canvas._last_width = new_width
            chat_canvas.itemconfig(chat_canvas_window, width=new_width)
            if old_width != new_width:
                _update_wraplengths()
        except Exception:
            pass

    chat_messages_frame.bind("<Configure>", on_frame_configure)
    chat_canvas.bind("<Configure>", on_canvas_configure)

    for target in (win, chat_canvas, chat_messages_frame):
        try:
            target.bind("<MouseWheel>", _chat_mousewheel, add="+")
            target.bind("<Button-4>", _chat_mousewheel, add="+")
            target.bind("<Button-5>", _chat_mousewheel, add="+")
        except Exception:
            pass

    chat_input.bind("<FocusIn>", _on_input_focus_in)
    chat_input.bind("<FocusOut>", _on_input_focus_out)
    chat_input.bind("<KeyRelease>", _on_input_key_release)
    chat_input.bind("<Return>", _on_enter)

    def _chat_input_context_menu(event):
        menu = tk.Menu(
            win, tearoff=0,
            bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
            activebackground=_c("BORDER"),
            activeforeground=_c("TEXT_MAIN"),
            relief="flat", borderwidth=1,
            font=("Segoe UI", 9),
        )
        menu.add_command(
            label="Вырезать",
            command=lambda: chat_input.event_generate("<<Cut>>"),
        )
        menu.add_command(
            label="Копировать",
            command=lambda: chat_input.event_generate("<<Copy>>"),
        )
        menu.add_command(
            label="Вставить",
            command=lambda: _paste_clipboard_into_widget(chat_input),
        )
        menu.add_separator()
        menu.add_command(
            label="Выделить всё",
            command=lambda: _select_all_widget(chat_input),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    chat_input.bind("<Button-3>", _chat_input_context_menu)

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
    _bind_text_hotkeys(chat_input, chat_handlers)

    def _ctrl_enter(event=None):
        if _editor_mode and _editor_preview_content:
            _submit_prompt("", clear_input=True)
            _focus_chat_input()
            return "break"
        send_chat_message()
        return "break"

    win.bind("<Control-Return>", _ctrl_enter)
    chat_input.bind("<Control-Return>", _ctrl_enter)

    _refresh_session_list()
    _render_current_session()
    _set_input_placeholder()
    _focus_chat_input()

    def on_close():
        global _chat_window
        _hide_new_message_indicator()
        _stop_generation(silent=True)
        global session_listbox, chat_canvas, chat_scrollbar, chat_messages_frame, chat_canvas_window
        global chat_input, chat_input_placeholder_label, chat_send_btn, chat_status_label, chat_token_label
        global improve_btn, paste_editor_btn, clear_btn, export_btn, settings_btn, new_chat_btn, delete_chat_btn
        global _search_window, _settings_window, _editor_window
        global editor_source_text, editor_comment_text, editor_stats_label, editor_status_label

        _stop_generation(silent=True)
        _save_sessions()

        try:
            if _widget_exists(_search_window):
                _search_window.destroy()
        except Exception:
            pass
        try:
            if _widget_exists(_settings_window):
                _settings_window.destroy()
        except Exception:
            pass
        try:
            if _widget_exists(_editor_window):
                _editor_window.destroy()
        except Exception:
            pass

        _chat_window = None
        _search_window = None
        _settings_window = None
        _editor_window = None
        global _hint_text_var, _editor_mode, _free_chat_mode, _editor_preview_frame, _editor_preview_text, _editor_preview_content
        _hint_text_var = None
        _editor_mode = False
        _free_chat_mode = False
        _editor_preview_frame = None
        _editor_preview_text = None
        _editor_preview_content = ""

        session_listbox = None
        chat_canvas = None
        chat_scrollbar = None
        chat_messages_frame = None
        chat_canvas_window = None

        chat_input = None
        chat_input_placeholder_label = None
        chat_send_btn = None
        chat_status_label = None
        chat_token_label = None

        improve_btn = None
        paste_editor_btn = None
        clear_btn = None
        export_btn = None
        settings_btn = None
        new_chat_btn = None
        delete_chat_btn = None

        editor_source_text = None
        editor_comment_text = None
        editor_stats_label = None
        editor_status_label = None

        try:
            win.destroy()
        except Exception:
            pass
        
    win.protocol("WM_DELETE_WINDOW", on_close)

    try:
        chat_input.focus_set()
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatible names / helpers
# ─────────────────────────────────────────────────────────────────────────────

def _show_editor_window():
    return open_editor_text_window()