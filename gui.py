import os
import re
import sys
import json
import traceback
def _global_exception_handler(exc_type, exc_value, exc_tb):
    traceback.print_exception(exc_type, exc_value, exc_tb)
    input("Press Enter to exit...")

sys.excepthook = _global_exception_handler
import engine.chat_window as chat_window
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
import ntpath
import datetime as _dt
from datetime import datetime
import pygame
import threading
import threading as _threading_gui
import unicodedata
try:
    import soundfile as sf
except ImportError:
    sf = None
from typing import Optional

from engine.voice_manager import VoiceManager
from engine.task_manager import TaskManager
from engine.task_models import Task

# =========================
# BASE DIR & PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
REF_DIR = os.path.join(BASE_DIR, "reference")
BACKUP_DIR = os.path.join(BASE_DIR, "library")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

for folder in (LOG_DIR, REF_DIR, BACKUP_DIR, OUTPUT_DIR):
    os.makedirs(folder, exist_ok=True)


def write_log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = os.path.join(LOG_DIR, f"xtts_gui_{ts}.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(text + "\n\n")

# =========================
# COLORS
# =========================
class Colors:
    BG_DARK = "#0d1117"
    BG_CARD = "#161b22"
    BG_INPUT = "#21262d"
    BG_HOVER = "#30363d"
    BG_ACTIVE = "#238636"
    BG_DANGER = "#da3633"
    TEXT_MAIN = "#f0f6fc"
    TEXT_DIM = "#8b949e"
    TEXT_SUCCESS = "#3fb950"
    TEXT_WARNING = "#d29922"
    TEXT_ERROR = "#f85149"
    ACCENT = "#58a6ff"
    BORDER = "#30363d"
    PROGRESS_BG = "#21262d"
    PROGRESS_FG = "#238636"
    CHUNK_BG = "#2d5a8e"
    CHUNK_FG = "#ffffff"
    TOOLTIP_BG = "#30363d"
    MENU_BG = "#1c2330"
    MENU_HOVER = "#2a3142"
    MENU_ACTIVE = "#1f6feb"
# =========================
# TOOLTIP
# =========================
class ToolTip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def show(self, event=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 15
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip,
            text=self.text() if callable(self.text) else self.text,
            bg=Colors.TOOLTIP_BG,
            fg=Colors.TEXT_MAIN,
            justify="left",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=7,
            font=("Segoe UI", 9),
            wraplength=280
        ).pack()

    def hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None

# =========================
# ROOT
# =========================

import ctypes

def set_dark_titlebar(root):
    root.update()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    # Windows 11
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(ctypes.c_int(1)),
        ctypes.sizeof(ctypes.c_int)
    )

root = TkinterDnD.Tk()
set_dark_titlebar(root)

ICON_PATH = os.path.join(BASE_DIR, "icon.ico")

try:
    if os.path.isfile(ICON_PATH):
        root.iconbitmap(ICON_PATH)
except Exception as e:
    print(f"[ICON ERROR] {e}")

root.title("XTTS Studio")
root.geometry("1160x820")
root.minsize(920, 680)
root.configure(bg=Colors.BG_DARK)

try:
    from ctypes import windll
    #windll.shcore.SetProcessDpiAwareness(2)  # per-monitor DPI вместо system DPI
except Exception:
    pass

# =========================
# LAYOUT
# =========================
main_container = tk.Frame(root, bg=Colors.BG_DARK)
main_container.pack(fill="both", expand=True, padx=8, pady=14)

left_panel = tk.Frame(main_container, bg=Colors.BG_DARK, width=260)
left_panel.pack(side="left", fill="y", padx=(0, 14))
left_panel.pack_propagate(False)

right_panel = tk.Frame(main_container, bg=Colors.BG_DARK)
right_panel.pack(side="left", fill="both", expand=True)

# =========================
# CONSOLE REDIRECT
# =========================
class ConsoleRedirect:
    def __init__(self):
        self.widget = None
        self._buffer = []

    def attach(self, widget):
        self.widget = widget
        for line in self._buffer:
            try:
                widget.after(0, self._write_to_widget, line)
            except Exception:
                pass
        self._buffer.clear()

    def _write_to_widget(self, text):
        if self.widget is None:
            return
        low = text.lower()
        if "error" in low or "ошибка" in low:
            tag = "error"
        elif "warn" in low or "warning" in low:
            tag = "warn"
        elif "done" in low or "готово" in low or "✔" in text:
            tag = "ok"
        else:
            tag = "info"
        self.widget.insert(tk.END, text, tag)
        self.widget.see(tk.END)

    def write(self, text):
        if self.widget is None:
            self._buffer.append(text)
        else:
            try:
                self.widget.after(0, self._write_to_widget, text)
            except Exception:
                pass

    def flush(self):
        pass

console_redirect = ConsoleRedirect()
sys.stdout = console_redirect
sys.stderr = console_redirect

def _log(msg):
    with open(r"C:\XTTS Studio\boot.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# =========================
# PYGAME
# =========================
PYGAME_OK = False
try:
    pygame.mixer.init()
    PYGAME_OK = True
except Exception as e:
    PYGAME_OK = False
    print(f"[GUI] pygame.mixer init failed: {e}")

# =========================
# STATE
# =========================
current_pos = 0
play_btn = None
_highlight_pos = 0  # текущая позиция курсора подсветки в text_box
import threading as _threading_gui
_textbox_updated = _threading_gui.Event()

word_replacer_enabled = tk.BooleanVar(value=True)
lang_split_enabled = tk.BooleanVar(value=True)

ref_var = tk.StringVar()
status_var = tk.StringVar(value="🔄 Инициализация модели...")
stage_var = tk.StringVar(value="STARTUP")
progress_value = tk.IntVar(value=0)
console_visible = tk.BooleanVar(value=True)

lang_var = tk.StringVar(value="auto")
quality_var = tk.StringVar(value="Высокое качество")

current_task: Optional[Task] = None
voice_map = {}
current_text_snapshot = ""
model_ready = False

voice_manager = VoiceManager(BACKUP_DIR)
voice_manager.scan_voices()

use_gpt = tk.BooleanVar(value=False)

# Chat interface state
chat_history = None
chat_input = None
_chat_window = None
chat_send_btn = None
chat_status_label = None
chat_btn = None
improve_btn = None

# =========================
# WIDGETS
# =========================
def create_card(parent, title="", bg=Colors.BG_CARD, padx=10, pady=10):
    card = tk.Frame(parent, bg=bg, highlightthickness=0)
    if title:
        tk.Label(
            card,
            text=title,
            bg=bg,
            fg=Colors.TEXT_MAIN,
            font=("Segoe UI", 11, "bold"),
            anchor="w"
        ).pack(fill="x", padx=padx, pady=(pady, 5))
    return card

def create_button(parent, text, command, bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
                  active_bg=Colors.BG_HOVER, width=None, height=1, font_size=10):
    is_bold = "ГЕНЕРИРОВАТЬ" in text or "ОТМЕНА" in text
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg, fg=fg,
        activebackground=active_bg, activeforeground=fg,
        relief="flat", borderwidth=0,
        font=("Segoe UI", font_size, "bold" if is_bold else "normal"),
        cursor="hand2",
        padx=4, pady=2
    )
    if width:
        btn.config(width=width)
    if height:
        btn.config(height=height)

    def on_enter(e):
        btn.config(bg=active_bg)
    def on_leave(e):
        btn.config(bg=bg)
    btn.bind("<Enter>", on_enter, add="+")
    btn.bind("<Leave>", on_leave, add="+")
    return btn

def create_entry(parent, textvariable, bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN):
    return tk.Entry(
        parent,
        textvariable=textvariable,
        bg=bg, fg=fg,
        insertbackground=Colors.TEXT_MAIN,
        relief="flat", borderwidth=0,
        font=("Segoe UI", 10),
        highlightthickness=1,
        highlightbackground=Colors.BORDER,
        highlightcolor=Colors.ACCENT
    )

# =========================
# SAFE UI UPDATE
# =========================
def set_status(text):
    root.after(0, lambda: status_var.set(text))

def set_stage(text):
    root.after(0, lambda: stage_var.set(text))

def set_progress(value):
    try:
        value = max(0, min(100, int(value)))
    except Exception:
        return
    root.after(0, lambda: progress_value.set(value))

def lock_textbox():
    try:
        text_box.config(state="disabled")
    except Exception:
        pass

def unlock_textbox():
    try:
        text_box.config(state="normal")
    except Exception:
        pass

# =========================
# HELPERS
# =========================
def clean_path(p: str) -> str:
    p = (p or "").strip()
    try:
        if p.startswith("{") or "} {" in p:
            parts = root.tk.splitlist(p)
            if parts:
                p = parts[0]
    except Exception:
        pass
    p = p.strip("{}")
    p = p.replace("/", "\\")
    return ntpath.normpath(p)

def normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)


    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r",([A-ZА-ЯЁa-zа-яё])", r", \1", text)

    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{2,}", "\n", text)

    text = re.sub(r"(\.)([A-ZА-ЯЁ])", r"\1 \2", text)

    text = re.sub(r"\s+", " ", text).strip()

    return text

def set_textbox_content(content: str):
    unlock_textbox()
    text_box.delete("1.0", tk.END)
    if content:
        text_box.insert("1.0", content)
        text_box.config(fg=Colors.TEXT_MAIN)
    else:
        show_placeholder()

def _update_textbox_normalized(text: str):
    """Обновляет text_box финальным нормализованным текстом из runner."""
    try:
        unlock_textbox()
        text_box.delete("1.0", tk.END)
        text_box.insert("1.0", text)
        text_box.config(fg=Colors.TEXT_MAIN)
        lock_textbox()
        _textbox_updated.set()
    except Exception as e:
        print(f"[TextBox update error]: {e}")

def clear_chunk_highlight():
    try:
        text_box.tag_remove("chunk_highlight", "1.0", tk.END)
    except Exception:
        pass

def open_outputs_folder():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    win = tk.Toplevel(root)
    win.title("🎵 Аудио файлы")
    win.geometry("720x560")
    win.minsize(600, 440)
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    win.grab_set()

    # ── внутреннее состояние плеера ──────────────────────────────────────────
    _p = {
        "playing": False,
        "path": None,
        "pos": 0.0,
        "duration": 0.0,
        "after_id": None,
    }

    # ── helpers ──────────────────────────────────────────────────────────────
    def _fmt(sec):
        sec = max(0, int(sec))
        return f"{sec // 60}:{sec % 60:02d}"

    def _get_duration(path):
        try:
            if sf is None:
                return 0.0
            return sf.info(path).duration
        except Exception:
            return 0.0

    def _file_date(path):
        try:
            ts = os.path.getmtime(path)
            d = _dt.datetime.fromtimestamp(ts)
            today = _dt.date.today()
            if d.date() == today:
                return f"сегодня {d.strftime('%H:%M')}"
            elif (today - d.date()).days == 1:
                return f"вчера {d.strftime('%H:%M')}"
            return d.strftime("%d.%m.%Y %H:%M")
        except Exception:
            return ""

    def _collect_files():
        try:
            files = [f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".wav")]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR, f)), reverse=True)
            return files
        except Exception:
            return []

    # ── tick / playback ──────────────────────────────────────────────────────
    def _tick():
        if not PYGAME_OK:
            return
        try:
            if pygame.mixer.music.get_busy():
                _p["pos"] += 0.2
                pct = min(100, _p["pos"] / max(_p["duration"], 0.1) * 100)
                seek_var.set(pct)
                pos_lbl.config(text=_fmt(_p["pos"]))
                _p["after_id"] = win.after(200, _tick)
            else:
                _p["playing"] = False
                _p["after_id"] = None
                btn_play.config(text="▶")
                seek_var.set(0)
                pos_lbl.config(text="0:00")
        except Exception:
            pass

    def _stop_ticker():
        if _p["after_id"]:
            try:
                win.after_cancel(_p["after_id"])
            except Exception:
                pass
            _p["after_id"] = None

    def _load_play(path, from_pos=0.0):
        if not PYGAME_OK or not path or not os.path.isfile(path):
            return
        _stop_ticker()
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(path)
            pygame.mixer.music.play(start=from_pos)
            dur = _get_duration(path)
            _p.update(playing=True, path=path, pos=from_pos, duration=dur)
            dur_lbl.config(text=_fmt(dur))
            btn_play.config(text="⏸")
            now_lbl.config(text=os.path.basename(path), fg=Colors.TEXT_MAIN)
            seek_var.set(from_pos / max(dur, 0.1) * 100)
            pos_lbl.config(text=_fmt(from_pos))
            _tick()
            _highlight_active(path)
        except Exception as e:
            now_lbl.config(text=f"Ошибка: {e}", fg=Colors.TEXT_ERROR)

    def toggle_play():
        if not PYGAME_OK:
            return
        if _p["playing"]:
            pygame.mixer.music.pause()
            _p["playing"] = False
            _stop_ticker()
            btn_play.config(text="▶")
        else:
            if _p["path"] and os.path.isfile(_p["path"]):
                pygame.mixer.music.unpause()
                _p["playing"] = True
                btn_play.config(text="⏸")
                _tick()

    def seek_rel(delta):
        if not _p["path"]:
            return
        _load_play(_p["path"], max(0.0, _p["pos"] + delta))

    def on_seek_drag(val):
        if not _p["path"] or not _p["duration"]:
            return
        new_pos = float(val) / 100.0 * _p["duration"]
        _load_play(_p["path"], new_pos)

    # ── карточки файлов ──────────────────────────────────────────────────────
    _card_widgets = {}   # path → frame
    _active_path = {"v": None}

    def _highlight_active(path):
        prev = _active_path["v"]
        if prev and prev in _card_widgets:
            try:
                _card_widgets[prev].config(bg=Colors.BG_CARD,
                                           highlightbackground=Colors.BORDER)
            except Exception:
                pass
        _active_path["v"] = path
        if path in _card_widgets:
            try:
                _card_widgets[path].config(bg="#1c2330",
                                           highlightbackground=Colors.ACCENT)
            except Exception:
                pass

    def _make_card(parent, fname):
        path = os.path.join(OUTPUT_DIR, fname)
        dur = _get_duration(path)
        size_kb = os.path.getsize(path) // 1024
        date_str = _file_date(path)
        dur_str = _fmt(dur) if dur > 0 else "?"
        meta = f"{size_kb} KB · {dur_str} · {date_str}"

        card = tk.Frame(
            parent,
            bg=Colors.BG_CARD,
            highlightthickness=1,
            highlightbackground=Colors.BORDER,
            bd=0,
            cursor="hand2",
        )
        card.pack(fill="x", padx=8, pady=3)
        _card_widgets[path] = card

        # left: иконка
        ico = tk.Label(card, text="🎵", bg=Colors.BG_CARD,
                       font=("Segoe UI", 14), padx=10, pady=8)
        ico.pack(side="left")

        # mid: имя + мета
        info = tk.Frame(card, bg=Colors.BG_CARD)
        info.pack(side="left", fill="both", expand=True, pady=8)

        name_lbl = tk.Label(
            info, text=fname, bg=Colors.BG_CARD,
            fg=Colors.TEXT_MAIN, font=("Segoe UI", 10, "bold"),
            anchor="w", wraplength=360, justify="left"
        )
        name_lbl.pack(fill="x")

        meta_lbl = tk.Label(
            info, text=meta, bg=Colors.BG_CARD,
            fg=Colors.TEXT_DIM, font=("Segoe UI", 8),
            anchor="w"
        )
        meta_lbl.pack(fill="x")

        # right: кнопки (видны при наведении)
        btn_frame = tk.Frame(card, bg=Colors.BG_CARD)
        btn_frame.pack(side="right", padx=8)

        btn_pl = tk.Button(
            btn_frame, text="▶", bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
            relief="flat", bd=0, font=("Segoe UI", 10), padx=6, pady=3,
            cursor="hand2", activebackground=Colors.BG_ACTIVE,
            activeforeground=Colors.TEXT_MAIN,
            command=lambda p=path: _load_play(p)
        )
        btn_pl.pack(side="left", padx=(0, 4))

        btn_del = tk.Button(
            btn_frame, text="🗑", bg=Colors.BG_INPUT, fg=Colors.TEXT_ERROR,
            relief="flat", bd=0, font=("Segoe UI", 10), padx=6, pady=3,
            cursor="hand2", activebackground=Colors.BG_DANGER,
            activeforeground=Colors.TEXT_MAIN,
            command=lambda p=path, c=card: _delete_file(p, c)
        )
        btn_del.pack(side="left")

        # hover highlight
        def _enter(e, c=card, p=path):
            if _active_path["v"] != p:
                c.config(bg=Colors.BG_HOVER, highlightbackground=Colors.BORDER)
            for w in c.winfo_children():
                try:
                    w.config(bg=Colors.BG_HOVER if _active_path["v"] != p else "#1c2330")
                except Exception:
                    pass
            for w in btn_frame.winfo_children():
                try:
                    w.config(bg=Colors.BG_INPUT)
                except Exception:
                    pass

        def _leave(e, c=card, p=path):
            active_bg = "#1c2330" if _active_path["v"] == p else Colors.BG_CARD
            c.config(bg=active_bg,
                     highlightbackground=Colors.ACCENT if _active_path["v"] == p else Colors.BORDER)
            for w in c.winfo_children():
                try:
                    w.config(bg=active_bg)
                except Exception:
                    pass

        for widget in [card, ico, info, name_lbl, meta_lbl, btn_frame]:
            widget.bind("<Enter>", _enter)
            widget.bind("<Leave>", _leave)

        card.bind("<Double-Button-1>", lambda e, p=path: _load_play(p))
        ico.bind("<Double-Button-1>", lambda e, p=path: _load_play(p))
        name_lbl.bind("<Double-Button-1>", lambda e, p=path: _load_play(p))

    def _delete_file(path, card_widget):
        fname = os.path.basename(path)
        if not messagebox.askyesno("Удалить?", f"Удалить файл:\n{fname}?", parent=win):
            return
        if _p.get("path") == path:
            _stop_ticker()
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            _p.update(playing=False, path=None, pos=0.0, duration=0.0)
            btn_play.config(text="▶")
            pos_lbl.config(text="0:00")
            dur_lbl.config(text="0:00")
            seek_var.set(0)
            now_lbl.config(text="Нет файла", fg=Colors.TEXT_DIM)
        try:
            os.remove(path)
        except Exception as e:
            messagebox.showerror("❌", str(e), parent=win)
            return
        if path in _card_widgets:
            del _card_widgets[path]
        try:
            card_widget.destroy()
        except Exception:
            pass
        _update_count()

    def _delete_all():
        files = [f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".wav")]
        if not files:
            messagebox.showinfo("Пусто", "Нет файлов для удаления.", parent=win)
            return
        if not messagebox.askyesno("Удалить всё?",
                                   f"Удалить все {len(files)} WAV-файлов?", parent=win):
            return
        _stop_ticker()
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        _p.update(playing=False, path=None, pos=0.0, duration=0.0)
        btn_play.config(text="▶")
        pos_lbl.config(text="0:00")
        dur_lbl.config(text="0:00")
        seek_var.set(0)
        now_lbl.config(text="Нет файла", fg=Colors.TEXT_DIM)
        for f in files:
            try:
                os.remove(os.path.join(OUTPUT_DIR, f))
            except Exception:
                pass
        _card_widgets.clear()
        _active_path["v"] = None
        for w in list(scroll_inner.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        _update_count()

    def _clear_cache():
        cache_dirs = [
            os.path.join(BASE_DIR, "reference"),
            os.path.join(BASE_DIR, "cache"),
            os.path.join(OUTPUT_DIR, "_cache"),
        ]
        removed = 0
        for d in cache_dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.endswith((".pth", ".cache", ".wav")):
                    try:
                        os.remove(os.path.join(d, f))
                        removed += 1
                    except Exception:
                        pass
        messagebox.showinfo(
            "Кэш очищен",
            f"Удалено файлов кэша: {removed}" if removed else "Кэш уже пуст.",
            parent=win,
        )

    def _open_folder():
        try:
            os.startfile(OUTPUT_DIR)
        except Exception:
            messagebox.showinfo("Папка", OUTPUT_DIR, parent=win)

    def _update_count():
        try:
            n = len([f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".wav")])
        except Exception:
            n = 0
        count_lbl.config(text=f"{n} файлов")


    # ── LAYOUT ───────────────────────────────────────────────────────────────

    # — Тулбар —
    toolbar = tk.Frame(win, bg=Colors.BG_CARD, pady=6)
    toolbar.pack(fill="x", padx=0)

    def _tb_btn(parent, text, cmd, fg=Colors.TEXT_MAIN, active_bg=Colors.BG_HOVER):
        b = tk.Button(
            parent, text=text, command=cmd,
            bg=Colors.BG_INPUT, fg=fg,
            activebackground=active_bg, activeforeground=Colors.TEXT_MAIN,
            relief="flat", bd=0, font=("Segoe UI", 9),
            padx=10, pady=4, cursor="hand2"
        )
        b.bind("<Enter>", lambda e: b.config(bg=active_bg))
        b.bind("<Leave>", lambda e: b.config(bg=Colors.BG_INPUT))
        return b

    _tb_btn(toolbar, "📂 Открыть папку", _open_folder).pack(side="left", padx=(10, 4))

    sep1 = tk.Frame(toolbar, bg=Colors.BORDER, width=1, height=18)
    sep1.pack(side="left", padx=6)

    _tb_btn(toolbar, "🗑 Удалить все", _delete_all,
            fg=Colors.TEXT_ERROR, active_bg=Colors.BG_DANGER).pack(side="left", padx=(0, 4))
    _tb_btn(toolbar, "🧹 Очистить кэш", _clear_cache).pack(side="left")

    count_lbl = tk.Label(toolbar, text="", bg=Colors.BG_CARD,
                         fg=Colors.TEXT_DIM, font=("Segoe UI", 9))
    count_lbl.pack(side="right", padx=12)

    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x")

    # — Список файлов (прокручиваемый) —
    list_outer = tk.Frame(win, bg=Colors.BG_DARK)
    list_outer.pack(fill="both", expand=True)

    canvas = tk.Canvas(list_outer, bg=Colors.BG_DARK, bd=0,
                       highlightthickness=0)
    scrollbar = tk.Scrollbar(list_outer, orient="vertical",
                             command=canvas.yview,
                             bg=Colors.BG_INPUT, troughcolor=Colors.BG_DARK)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    scroll_inner = tk.Frame(canvas, bg=Colors.BG_DARK)
    canvas_window = canvas.create_window((0, 0), window=scroll_inner, anchor="nw")

    def _on_frame_configure(e):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(e):
        canvas.itemconfig(canvas_window, width=e.width)

    scroll_inner.bind("<Configure>", _on_frame_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    def _on_mousewheel(e):
        try:
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        except Exception:
            pass

    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    # — Разделитель перед плеером —
    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x")

    # — Плеер (прибит к низу) —
    player = tk.Frame(win, bg=Colors.BG_CARD, pady=10)
    player.pack(fill="x", side="bottom")

    # Имя файла
    now_lbl = tk.Label(
        player, text="Нет файла", bg=Colors.BG_CARD,
        fg=Colors.TEXT_DIM, font=("Segoe UI", 9),
        anchor="w", padx=14
    )
    now_lbl.pack(fill="x")

    # Seekbar
    seek_var = tk.DoubleVar(value=0)
    seek_style = ttk.Style()
    seek_style.configure("Seek.Horizontal.TScale", background=Colors.BG_CARD)

    seek_bar = ttk.Scale(
        player, from_=0, to=100, orient="horizontal",
        variable=seek_var, command=on_seek_drag
    )
    seek_bar.pack(fill="x", padx=14, pady=(6, 2))

    # Время
    time_row = tk.Frame(player, bg=Colors.BG_CARD)
    time_row.pack(fill="x", padx=14)
    pos_lbl = tk.Label(time_row, text="0:00", bg=Colors.BG_CARD,
                       fg=Colors.TEXT_DIM, font=("Consolas", 8))
    pos_lbl.pack(side="left")
    dur_lbl = tk.Label(time_row, text="0:00", bg=Colors.BG_CARD,
                       fg=Colors.TEXT_DIM, font=("Consolas", 8))
    dur_lbl.pack(side="right")

    # Кнопки управления
    ctrl = tk.Frame(player, bg=Colors.BG_CARD)
    ctrl.pack(pady=(8, 0))

    def _ctrl_btn(parent, text, cmd, primary=False):
        bg = Colors.BG_ACTIVE if primary else Colors.BG_INPUT
        ab = Colors.BG_HOVER if not primary else "#2ea043"
        b = tk.Button(
            parent, text=text, command=cmd,
            bg=bg, fg=Colors.TEXT_MAIN,
            activebackground=ab, activeforeground=Colors.TEXT_MAIN,
            relief="flat", bd=0, font=("Segoe UI", 11 if primary else 10),
            padx=10, pady=5, cursor="hand2", width=3
        )
        b.bind("<Enter>", lambda e: b.config(bg=ab))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    _ctrl_btn(ctrl, "⏪", lambda: seek_rel(-10)).pack(side="left", padx=3)
    _ctrl_btn(ctrl, "⏮", lambda: seek_rel(-5)).pack(side="left", padx=3)
    btn_play = _ctrl_btn(ctrl, "▶", toggle_play, primary=True)
    btn_play.pack(side="left", padx=3)
    _ctrl_btn(ctrl, "⏭", lambda: seek_rel(5)).pack(side="left", padx=3)
    _ctrl_btn(ctrl, "⏩", lambda: seek_rel(10)).pack(side="left", padx=3)


    # ── наполнение карточками ─────────────────────────────────────────────
    for fname in _collect_files():
        _make_card(scroll_inner, fname)

    _update_count()

    # ── закрытие ─────────────────────────────────────────────────────────────
    def on_close():
        canvas.unbind_all("<MouseWheel>")
        _stop_ticker()
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        win.destroy()

# =========================
# OUTPUT NAMING
# =========================
def _make_output_name(text: str) -> str:
    """Генерирует имя файла из первых слов текста с защитой от дублей."""
    # Берём первые ~40 символов текста
    snippet = text.strip()[:60]
    # Убираем переносы строк
    snippet = snippet.replace("\n", " ").replace("\r", "")
    # Оставляем буквы, цифры, пробелы
    allowed = []
    for ch in snippet:
        cat = unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("N") or ch == " ":
            allowed.append(ch)
    name = "".join(allowed).strip()
    # Обрезаем по последнему пробелу чтобы не резать слово
    if len(name) > 40:
        cut = name[:40].rsplit(" ", 1)
        name = cut[0] if len(cut) > 1 else name[:40]
    name = name.strip() or "output"
    # Защита от дублей: name.wav → name (1).wav → name (2).wav
    base = os.path.join(OUTPUT_DIR, name)
    candidate = f"{base}.wav"
    counter = 1
    while os.path.exists(candidate):
        candidate = f"{base} ({counter}).wav"
        counter += 1
    return candidate

# =========================
# QUEUE
# =========================
def update_queue_view():
    try:
        queue_listbox.delete(0, tk.END)
        status_icons = {
            "queued": "⏳", "running": "▶", "done": "✔",
            "error": "❌", "cancelled": "⛔",
        }
        queue = task_manager.get_queue()
        active_set = False
        for i, task in enumerate(queue):
            name = task.text[:30].replace("\n", " ")
            if not active_set and task.status in ("queued", "running"):
                icon = "▶"
                active_set = True
            else:
                icon = status_icons.get(task.status, "•")
            queue_listbox.insert(tk.END, f"{icon} {name} | {task.progress}%")
            if icon == "▶":
                queue_listbox.itemconfig(i, fg=Colors.TEXT_SUCCESS)
            elif task.status == "done":
                queue_listbox.itemconfig(i, fg=Colors.TEXT_DIM)
            elif task.status == "error":
                queue_listbox.itemconfig(i, fg=Colors.TEXT_ERROR)
    except Exception:
        pass

def queue_autorefresh():
    update_queue_view()
    root.after(500, queue_autorefresh)

HISTORY_PATH = os.path.join(BASE_DIR, "history.json")

def _save_history(task):
    try:
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

        entry = {
            "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "text": (task.text or "")[:120],
            "voice": os.path.basename(os.path.dirname(task.voice or "")),
            "quality": task.quality or "",
            "output": task.output_path or "",
            "duration": task.stats.get("time_sec", 0) if task.stats else 0,
            "chunks": task.stats.get("chunks", 0) if task.stats else 0,
        }

        history.insert(0, entry)
        history = history[:100]  # храним последние 100

        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[History] Save error: {e}")

def open_history():
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        history = []

    win = tk.Toplevel(root)
    win.title("📜 История генераций")
    win.geometry("720x500")
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    win.grab_set()

    # тулбар
    toolbar = tk.Frame(win, bg=Colors.BG_CARD, pady=6)
    toolbar.pack(fill="x")

    lbl_count = tk.Label(toolbar, text=f"{len(history)} записей",
                         bg=Colors.BG_CARD, fg=Colors.TEXT_DIM, font=("Segoe UI", 9))
    lbl_count.pack(side="left", padx=12)

    def clear_history():
        if not messagebox.askyesno("Очистить?", "Удалить всю историю генераций?", parent=win):
            return
        try:
            os.remove(HISTORY_PATH)
        except Exception:
            pass
        for w in list(scroll_inner.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        lbl_count.config(text="0 записей")

    tk.Button(
        toolbar, text="🗑 Очистить историю", command=clear_history,
        bg=Colors.BG_INPUT, fg=Colors.TEXT_ERROR,
        activebackground=Colors.BG_DANGER, activeforeground=Colors.TEXT_MAIN,
        relief="flat", bd=0, font=("Segoe UI", 9), padx=10, pady=4, cursor="hand2"
    ).pack(side="right", padx=10)

    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x")

    # прокручиваемый список
    list_outer = tk.Frame(win, bg=Colors.BG_DARK)
    list_outer.pack(fill="both", expand=True)

    canvas = tk.Canvas(list_outer, bg=Colors.BG_DARK, bd=0, highlightthickness=0)
    scrollbar = tk.Scrollbar(list_outer, orient="vertical", command=canvas.yview,
                             bg=Colors.BG_INPUT, troughcolor=Colors.BG_DARK)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    scroll_inner = tk.Frame(canvas, bg=Colors.BG_DARK)
    canvas_window = canvas.create_window((0, 0), window=scroll_inner, anchor="nw")

    def _on_frame_configure(e):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(e):
        canvas.itemconfig(canvas_window, width=e.width)

    scroll_inner.bind("<Configure>", _on_frame_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    def _on_mousewheel(e):
        try:
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        except Exception:
            pass

    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    # карточки
    for entry in history:
        card = tk.Frame(scroll_inner, bg=Colors.BG_CARD,
                        highlightthickness=1, highlightbackground=Colors.BORDER, bd=0)
        card.pack(fill="x", padx=8, pady=3)

        # левая часть — дата и мета
        left = tk.Frame(card, bg=Colors.BG_CARD)
        left.pack(side="left", padx=12, pady=8)

        tk.Label(left, text=entry.get("date", ""),
                 bg=Colors.BG_CARD, fg=Colors.ACCENT,
                 font=("Segoe UI", 8)).pack(anchor="w")

        tk.Label(left, text=f"🎤 {entry.get('voice', '?')}  ·  ⭐ {entry.get('quality', '?')}  ·  {entry.get('chunks', 0)} чанков",
                 bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

        # текст
        text_preview = entry.get("text", "").replace("\n", " ")
        tk.Label(card, text=text_preview,
                 bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
                 font=("Segoe UI", 9), anchor="w",
                 wraplength=480, justify="left").pack(side="left", fill="x",
                                                      expand=True, pady=8)

        # кнопка — вставить текст обратно
        def _reuse(t=entry.get("text", "")):
            set_textbox_content(t)
            win.destroy()

        tk.Button(
            card, text="↩", command=_reuse,
            bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
            relief="flat", bd=0, font=("Segoe UI", 11),
            padx=8, pady=4, cursor="hand2",
            activebackground=Colors.BG_HOVER
        ).pack(side="right", padx=8)

    def on_close():
        canvas.unbind_all("<MouseWheel>")
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)

    if not history:
        tk.Label(scroll_inner, text="История пуста",
                 bg=Colors.BG_DARK, fg=Colors.TEXT_DIM,
                 font=("Segoe UI", 10)).pack(pady=40)

# =========================
# UI CALLBACK
# =========================
def on_task_update(data):
    global current_task
    if data is None:
        return

    if isinstance(data, dict) and data.get("stage") == "queue_update":
        root.after(0, update_queue_view)
        return
    
    if isinstance(data, dict) and data.get("stage") == "chunk":
        chunk_raw = data.get("chunk_raw", "")
        chunk_start = data.get("chunk_start")
        chunk_end = data.get("chunk_end")

        def _do_chunk_highlight(s=chunk_start, e=chunk_end, t=chunk_raw):
            try:
                if s is not None and e is not None and int(e) > int(s):
                    _highlight_chunk(int(s), int(e))
                else:
                    _highlight_chunk_by_text(t)
            except Exception:
                _highlight_chunk_by_text(t)

        root.after_idle(_do_chunk_highlight)
        return
    
    if isinstance(data, dict) and data.get("stage") == "ai_conductor_on":
        root.after(0, lambda: set_ai_pulse(True))
        return

    if isinstance(data, dict) and data.get("stage") == "ai_conductor_off":
        root.after(0, lambda: set_ai_pulse(False))
        return

    if isinstance(data, dict) and data.get("stage") == "normalized_text":
        normalized = data.get("text", "")
        if normalized:
            def _apply_normalized_text(t=normalized):
                try:
                    text_box.config(state="normal")
                    text_box.delete("1.0", "end")
                    text_box.insert("1.0", t)
                    lock_textbox()
                    root.update_idletasks()
                    _textbox_updated.set()
                except Exception as e:
                    print(f"[TextBox sync error]: {e}")
            root.after(0, _apply_normalized_text)
            return

    if isinstance(data, dict) and data.get("stage") == "check_textbox_ready":
        return _textbox_updated.is_set()

    if isinstance(data, dict):
        return

    task = data
    set_progress(task.progress)

    if task.status == "queued":
        set_status("⏳ В очереди...")
        set_stage("QUEUED")
    elif task.status in ("running", "generate", "reference", "normalize", "chunking", "merge"):
        set_status(f"🔄 Генерация... {task.progress}%")
        set_stage("RUNNING")
    elif task.status == "done":
        root.after(0, lambda: set_ai_pulse(False))
        set_stage("DONE")
        unlock_textbox()
        if task.stats:
            t = task.stats.get("time_sec", 0)
            mins, secs = divmod(t, 60)
            time_str = f"{mins}м {secs}с" if mins else f"{secs}с"
            set_status(
                f"✅ Готово | {time_str} | "
                f"Чанков: {task.stats.get('chunks', '?')} | "
                f"Голос: {task.stats.get('voice', '?')}"
            )
        else:
            set_status("✅ Готово")
        root.after(0, lambda: _on_task_done(task))
    elif task.status == "error":
        set_stage("ERROR")
        unlock_textbox()
        set_status("❌ Ошибка")
        root.after(0, lambda: set_ai_pulse(False))
        root.after(0, lambda: _on_task_error(task))
    elif task.status == "cancelled":
        if current_task and current_task.id == task.id:
            current_task = None
        clear_chunk_highlight()
        unlock_textbox()
        set_stage("IDLE")
        set_status("⛔ Отменено")
        set_progress(0)
        root.after(0, lambda: set_ai_pulse(False))
    else:
        set_stage(task.status.upper())
        set_status(f"{task.status}... {task.progress}%")

def _highlight_chunk(start, end):
    try:
        clear_chunk_highlight()
        if start is None or end is None:
            return
        start = int(start)
        end = int(end)
        visible_text = text_box.get("1.0", "end-1c")
        text_len = len(visible_text)
        start = max(0, min(start, text_len))
        end = max(0, min(end, text_len))
        if end <= start:
            return
        start_idx = f"1.0+{start} chars"
        end_idx = f"1.0+{end} chars"
        text_box.tag_add("chunk_highlight", start_idx, end_idx)
        text_box.tag_configure("chunk_highlight",
                               background=Colors.CHUNK_BG,
                               foreground=Colors.CHUNK_FG)
        text_box.tag_raise("chunk_highlight")
        text_box.see(start_idx)


    except Exception as e:
        print(f"[Highlight error]: {e}")

def _highlight_chunk_by_text(chunk_raw: str):
    global _highlight_pos
    try:
        clear_chunk_highlight()

        content = text_box.get("1.0", "end-1c")
        if not content or content == PLACEHOLDER:
            return

        chunk = (chunk_raw or "").replace("[NO_PAUSE]", "").strip()
        if not chunk:
            return

        def _make_lookup(s: str):
            norm_chars = []
            index_map = []
            prev_space = False

            for i, ch in enumerate(s or ""):
                if ch.isspace():
                    if prev_space:
                        continue
                    norm_chars.append(" ")
                    index_map.append(i)
                    prev_space = True
                else:
                    norm_chars.append(ch.lower())
                    index_map.append(i)
                    prev_space = False

            while norm_chars and norm_chars[0] == " ":
                norm_chars.pop(0)
                index_map.pop(0)

            while norm_chars and norm_chars[-1] == " ":
                norm_chars.pop()
                index_map.pop()

            return "".join(norm_chars), index_map

        norm_content, index_map = _make_lookup(content)
        norm_chunk, _ = _make_lookup(chunk)

        if not norm_content or not norm_chunk or not index_map:
            return

        norm_search_from = 0
        found_search_pos = False

        for np, op in enumerate(index_map):
            if op >= _highlight_pos:
                norm_search_from = np
                found_search_pos = True
                break

        if not found_search_pos:
            norm_search_from = 0

        idx = norm_content.find(norm_chunk, norm_search_from)

        if idx == -1:
            idx = norm_content.find(norm_chunk)

        match_len = len(norm_chunk)

        if idx == -1:
            words = norm_chunk.split()
            for n in (10, 8, 6, 5, 4, 3, 2):
                if len(words) >= n:
                    probe = " ".join(words[:n])
                    idx = norm_content.find(probe, norm_search_from)
                    if idx == -1:
                        idx = norm_content.find(probe)
                    if idx != -1:
                        match_len = len(norm_chunk)
                        break

        if idx == -1:
            print(f"[HL] chunk not found: {repr(chunk[:80])}")
            return

        end_norm = min(idx + match_len, len(index_map))
        start_orig = index_map[idx]

        if end_norm > idx:
            end_orig = index_map[end_norm - 1] + 1
        else:
            end_orig = start_orig

        text_len = len(content)
        start_orig = max(0, min(start_orig, text_len))
        end_orig = max(start_orig, min(end_orig, text_len))

        if end_orig <= start_orig:
            return

        start_idx = f"1.0+{start_orig} chars"
        end_idx = f"1.0+{end_orig} chars"

        text_box.tag_add("chunk_highlight", start_idx, end_idx)
        text_box.tag_configure(
            "chunk_highlight",
            background=Colors.CHUNK_BG,
            foreground=Colors.CHUNK_FG
        )
        text_box.tag_raise("chunk_highlight")
        text_box.see(start_idx)

        _highlight_pos = end_orig

    except Exception as e:
        print(f"[Highlight error]: {e}")

def _on_task_done(task: Task):
    global current_task
    if current_task and current_task.id == task.id:
        current_task = None
    clear_chunk_highlight()
    unlock_textbox()
    _save_history(task)
    refresh_voice_list()
    messagebox.showinfo("✅ Готово", f"Файл сохранён:\n{task.output_path}")

def _on_task_error(task: Task):
    global current_task
    if current_task and current_task.id == task.id:
        current_task = None
    clear_chunk_highlight()
    unlock_textbox()
    write_log(task.error or "Unknown error")
    messagebox.showerror("❌ XTTS Error", task.error or "Неизвестная ошибка")

# =========================
# TASK MANAGER
# =========================
task_manager = TaskManager(ui_callback=on_task_update)
task_manager.start()

# =========================
# MODEL PRELOAD
# =========================
def _preload_model():
    global model_ready
    try:
        from engine.tts_runner import get_tts
        set_stage("STARTUP")
        set_status("🔄 Инициализация модели...")
        get_tts()
        model_ready = True
        set_stage("READY")
        set_status("✅ Модель готова")
    except Exception as e:
        print(f"[Preload] Модель будет загружена при генерации. ({e})")
        model_ready = False
        set_stage("IDLE")
        set_status("⏳ Ожидание...")

def start_preload_thread():
    threading.Thread(target=_preload_model, daemon=True).start()

# =========================
# REFERENCE
# =========================
def pick_reference():
    path = filedialog.askopenfilename(
        initialdir=REF_DIR,
        title="Выбор reference",
        filetypes=[("Audio", "*.wav *.mp3")]
    )
    if path:
        ref_var.set(path)

def pick_backup_reference():
    path = filedialog.askopenfilename(
        initialdir=BACKUP_DIR,
        title="Выбор reference из библиотеки",
        filetypes=[("Audio", "*.wav *.mp3")]
    )
    if path:
        ref_var.set(path)

def play_reference():
    global play_btn, current_pos
    if not PYGAME_OK:
        messagebox.showwarning("⚠️ Аудио", "Аудио-устройство недоступно")
        return
    ref = clean_path(ref_var.get().strip())
    if not ref or not os.path.isfile(ref):
        messagebox.showwarning("⚠️ Референс", "Сначала выберите референс")
        return
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
        play_btn.config(text="▶")
        current_pos = 0
        return
    try:
        pygame.mixer.music.load(ref)
        pygame.mixer.music.play(start=current_pos)
        play_btn.config(text="⏸")
        _check_playback()
    except Exception as e:
        play_btn.config(text="▶")
        messagebox.showerror("❌ Ошибка", f"Не удалось воспроизвести: {e}")

def _check_playback():
    global current_pos, play_btn
    if not PYGAME_OK:
        return
    try:
        if pygame.mixer.music.get_busy():
            current_pos += 0.2
            root.after(200, _check_playback)
        else:
            play_btn.config(text="▶")
            current_pos = 0
    except Exception:
        play_btn.config(text="▶")
        current_pos = 0

def seek_forward():
    global current_pos, play_btn
    if not PYGAME_OK:
        return
    ref = clean_path(ref_var.get().strip())
    if not ref or not os.path.isfile(ref):
        return
    try:
        current_pos += 5
        pygame.mixer.music.stop()
        pygame.mixer.music.load(ref)
        pygame.mixer.music.play(start=current_pos)
        play_btn.config(text="⏸")
        _check_playback()
    except Exception as e:
        messagebox.showerror("❌ Ошибка", f"Не удалось перемотать: {e}")

def seek_back():
    global current_pos, play_btn
    if not PYGAME_OK:
        return
    ref = clean_path(ref_var.get().strip())
    if not ref or not os.path.isfile(ref):
        return
    try:
        current_pos = max(0, current_pos - 5)
        pygame.mixer.music.stop()
        pygame.mixer.music.load(ref)
        pygame.mixer.music.play(start=current_pos)
        play_btn.config(text="⏸")
        _check_playback()
    except Exception as e:
        messagebox.showerror("❌ Ошибка", f"Не удалось перемотать: {e}")

# =========================
# VOICES
# =========================
def refresh_voice_list():
    voice_manager.scan_voices()
    voice_listbox.delete(0, tk.END)
    voice_map.clear()
    for voice in voice_manager.list_voices():
        voice_map[voice.name] = voice
        voice_listbox.insert(tk.END, f"🎤 {voice.name}")

def on_voice_select(event):
    selection = voice_listbox.curselection()
    if not selection:
        return
    raw_name = voice_listbox.get(selection[0])
    voice_name = raw_name.replace("🎤 ", "").strip()
    voice = voice_map.get(voice_name) or voice_manager.get_voice(voice_name)
    if not voice:
        return
    try:
        voice_manager.set_active(voice_name)
    except Exception:
        pass
    normalized_file = getattr(voice, "normalized", None)
    voice_path = getattr(voice, "path", None)
    if normalized_file and voice_path:
        normalized_path = os.path.join(voice_path, normalized_file)
        if os.path.isfile(normalized_path):
            ref_var.set(normalized_path)
            if PYGAME_OK and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            if PYGAME_OK:
                root.after(100, play_reference)
    set_status(f"🎤 Активный голос: {voice_name}")


# =========================
# PLACEHOLDER
# =========================
PLACEHOLDER = "Перетащите текстовый файл или введите текст..."

def show_placeholder():
    unlock_textbox()
    if not text_box.get("1.0", "end-1c"):
        text_box.insert("1.0", PLACEHOLDER)
        text_box.config(fg=Colors.TEXT_DIM)

def hide_placeholder(event=None):
    if text_box.get("1.0", "end-1c") == PLACEHOLDER:
        text_box.delete("1.0", tk.END)
        text_box.config(fg=Colors.TEXT_MAIN)

# =========================
# CHAT — делегируем в engine/chat_window.py
# =========================
def _get_textbox_content():
    return text_box.get("1.0", "end-1c").strip()

chat_window.init(
    root=root,
    colors=Colors,
    create_button_fn=create_button,
    get_text_fn=_get_textbox_content,
    set_text_fn=set_textbox_content,
    placeholder=PLACEHOLDER,
)

def toggle_chat_panel():
    chat_window.open_chat_window()

def append_chat_message(role, message):
    chat_window.append_chat_message(role, message)

def set_chat_status(message):
    chat_window.set_chat_status(message)
# =========================
# TEXT HELPERS
# =========================
def paste_safe(event=None):
    hide_placeholder()
    try:
        text_box.insert(tk.INSERT, normalize_text(root.clipboard_get()))
        text_box.config(fg=Colors.TEXT_MAIN)
    except Exception:
        pass
    return "break"

def copy_text(event=None):
    """Копировать выделенный текст в буфер обмена"""
    try:
        if text_box.tag_ranges(tk.SEL):
            selected = text_box.get(tk.SEL_FIRST, tk.SEL_LAST)
            root.clipboard_clear()
            root.clipboard_append(selected)
    except Exception:
        pass
    return "break"

def cut_text(event=None):
    """Вырезать выделенный текст (копировать и удалить)"""
    try:
        if text_box.tag_ranges(tk.SEL):
            selected = text_box.get(tk.SEL_FIRST, tk.SEL_LAST)
            root.clipboard_clear()
            root.clipboard_append(selected)
            text_box.delete(tk.SEL_FIRST, tk.SEL_LAST)
    except Exception:
        pass
    return "break"

def select_all_text(event=None):
    """Выделить весь текст"""
    try:
        text_box.tag_add(tk.SEL, "1.0", tk.END)
        text_box.mark_set(tk.INSERT, tk.END)
        text_box.see(tk.INSERT)
    except Exception:
        pass
    return "break"

def on_text_key_press(event):
    """Обработчик горячих клавиш для любой раскладки (физические коды клавиш)"""
    # event.state: 0x4 = Control, 0x1 = Shift
    # event.keycode - физический код клавиши, независимо от раскладки
    if event.state & 0x4:  # Ctrl нажат
        if event.keycode == 65:  # A
            return select_all_text(event)
        elif event.keycode == 67:  # C
            return copy_text(event)
        elif event.keycode == 88:  # X
            return cut_text(event)
        elif event.keycode == 86:  # V
            return paste_safe(event)
    return None

def load_txt():
    hide_placeholder()
    path = filedialog.askopenfilename(filetypes=[("TXT", "*.txt")])
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = normalize_text(f.read())
            set_textbox_content(content)
        except Exception:
            write_log(traceback.format_exc())
            messagebox.showerror("❌ Ошибка", "Не удалось открыть файл")

def show_text_context_menu(event):
    hide_placeholder()
    menu = tk.Menu(
        root, tearoff=0,
        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
        activebackground=Colors.BG_HOVER, activeforeground=Colors.TEXT_MAIN,
        relief="flat", borderwidth=1
    )
    menu.add_command(label="Копировать", command=lambda: (
        root.clipboard_clear(),
        root.clipboard_append(text_box.get(tk.SEL_FIRST, tk.SEL_LAST))
    ) if text_box.tag_ranges(tk.SEL) else None)
    menu.add_command(label="Вставить", command=paste_safe)
    menu.add_command(label="Вырезать", command=lambda: (
        root.clipboard_clear(),
        root.clipboard_append(text_box.get(tk.SEL_FIRST, tk.SEL_LAST)),
        text_box.delete(tk.SEL_FIRST, tk.SEL_LAST)
    ) if text_box.tag_ranges(tk.SEL) else None)
    menu.add_separator()
    menu.add_command(label="Выделить всё", command=lambda: text_box.tag_add(tk.SEL, "1.0", tk.END))
    menu.add_command(label="Очистить", command=lambda: (
        text_box.delete("1.0", tk.END),
        text_box.config(fg=Colors.TEXT_MAIN)
    ))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()

def paste_clipboard():
    hide_placeholder()
    try:
        text_box.insert("insert", normalize_text(root.clipboard_get()))
        text_box.config(fg=Colors.TEXT_MAIN)
    except Exception:
        messagebox.showwarning("⚠️ Буфер", "Нет текста")

def drop_handler(event):
    hide_placeholder()
    path = clean_path(event.data)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = normalize_text(f.read())
            set_textbox_content(content)
        except Exception:
            write_log(traceback.format_exc())
            messagebox.showerror("❌ Ошибка", "Не удалось открыть файл")

# =========================
# WORD REPLACER
# =========================
def open_word_replacer():
    from engine.tts_runner import word_replacer
    win = tk.Toplevel(root)
    win.title("📖 Словарь произношений")
    win.geometry("550x450")
    win.resizable(False, False)
    win.configure(bg=Colors.BG_CARD)
    win.grab_set()

    list_frame = tk.Frame(win, bg=Colors.BG_CARD)
    list_frame.pack(fill="both", expand=True, padx=15, pady=(15, 5))
    scrollbar = tk.Scrollbar(list_frame, bg=Colors.BG_INPUT, troughcolor=Colors.BG_DARK)
    scrollbar.pack(side="right", fill="y")
    listbox = tk.Listbox(
        list_frame, yscrollcommand=scrollbar.set,
        font=("Consolas", 10), selectmode="single",
        bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
        selectbackground=Colors.ACCENT, selectforeground=Colors.TEXT_MAIN,
        relief="flat", highlightthickness=0
    )
    listbox.pack(fill="both", expand=True)
    scrollbar.config(command=listbox.yview)

    _selected_word = {"word": None}

    def refresh():
        listbox.delete(0, tk.END)

        for category, data in word_replacer.data.items():
            if category == "meta":
                continue

            for word, value in data.items():
                text = value["text"] if isinstance(value, dict) else value
                listbox.insert(tk.END, f"{word}  →  {text}")

    def on_select(event=None):
        sel = listbox.curselection()
        if not sel:
            return
        item = listbox.get(sel[0])
        word, text = item.split("  →  ")
        word = word.strip()
        text = text.strip()
        _selected_word["word"] = word
        entry_word.delete(0, tk.END)
        entry_word.insert(0, word)
        entry_replacement.delete(0, tk.END)
        entry_replacement.insert(0, text)

    listbox.bind("<<ListboxSelect>>", on_select)

    refresh()

    input_frame = tk.Frame(win, bg=Colors.BG_CARD)
    input_frame.pack(fill="x", padx=15, pady=10)
    tk.Label(input_frame, text="Слово:", bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
             font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=(0, 10))
    entry_word = tk.Entry(
        input_frame, width=20, font=("Segoe UI", 10),
        bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
        insertbackground=Colors.TEXT_MAIN, relief="flat",
        highlightthickness=1, highlightbackground=Colors.BORDER
    )
    entry_word.grid(row=0, column=1, padx=5)
    tk.Label(input_frame, text="Замена:", bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
             font=("Segoe UI", 10)).grid(row=0, column=2, sticky="w", padx=(10, 10))
    entry_replacement = tk.Entry(
        input_frame, width=20, font=("Segoe UI", 10),
        bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
        insertbackground=Colors.TEXT_MAIN, relief="flat",
        highlightthickness=1, highlightbackground=Colors.BORDER
    )
    entry_replacement.grid(row=0, column=3, padx=5)

    btn_frame_wr = tk.Frame(win, bg=Colors.BG_CARD)
    btn_frame_wr.pack(fill="x", padx=15, pady=(0, 15))

    def add_rule():
        word = entry_word.get().strip()
        replacement = entry_replacement.get().strip()
        if not word or not replacement:
            messagebox.showwarning("⚠️ Поля пусты", "Заполните слово и замену", parent=win)
            return
        if word_replacer.get_category(word) is not None:
            messagebox.showwarning(
                "⚠️ Слово уже есть",
                f"«{word}» уже есть в словаре.\nИспользуйте «✏️ Сохранить изменения».",
                parent=win
            )
            return
        word_replacer.add_rule(word, replacement, category="custom")
        entry_word.delete(0, tk.END)
        entry_replacement.delete(0, tk.END)
        _selected_word["word"] = None
        refresh()

    def save_changes():
        original_word = _selected_word["word"]
        if not original_word:
            messagebox.showwarning("⚠️ Ничего не выбрано", "Выберите слово в списке для редактирования", parent=win)
            return
        new_word = entry_word.get().strip()
        new_text = entry_replacement.get().strip()
        if not new_word or not new_text:
            messagebox.showwarning("⚠️ Поля пусты", "Заполните слово и замену", parent=win)
            return

        if new_word != original_word:
            word_replacer.remove_rule(original_word)

        word_replacer.add_rule(new_word, new_text, category="custom")
        entry_word.delete(0, tk.END)
        entry_replacement.delete(0, tk.END)
        _selected_word["word"] = None
        refresh()

    def remove_rule():
        sel = listbox.curselection()
        if sel:
            item = listbox.get(sel[0])
            word = item.split("  →  ")[0].strip()
            word_replacer.remove_rule(word)
            entry_word.delete(0, tk.END)
            entry_replacement.delete(0, tk.END)
            _selected_word["word"] = None
            refresh()

    create_button(btn_frame_wr, "➕ Добавить", add_rule, bg=Colors.BG_INPUT).pack(side="left", padx=(0, 10))
    create_button(btn_frame_wr, "✏️ Сохранить изменения", save_changes, bg=Colors.BG_INPUT).pack(side="left", padx=(0, 10))
    create_button(btn_frame_wr, "🗑️ Удалить", remove_rule, bg=Colors.BG_DANGER, fg=Colors.TEXT_MAIN).pack(side="left")

    wr_cb = tk.Checkbutton(
        btn_frame_wr,
        text="Словарь активен",
        variable=word_replacer_enabled,
        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
        selectcolor=Colors.BG_INPUT,
        activebackground=Colors.BG_CARD,
        activeforeground=Colors.TEXT_MAIN,
        font=("Segoe UI", 9),
        cursor="hand2"
    )
    wr_cb.pack(side="right")
    ToolTip(wr_cb, "Включает замену слов по словарю перед синтезом.\n\nПри отключении аббревиатуры, числа и иностранные\nтермины могут читаться некорректно или вызывать\nартефакты — повторы, обрывы, «каша» в речи.")

    def close_window():
        save_settings()
        win.destroy()
    win.protocol("WM_DELETE_WINDOW", close_window)

# =========================
# BATCH PROCESSING
# =========================
def open_batch_window():
    win = tk.Toplevel(root)
    win.title("📦 Пакетная обработка")
    win.geometry("660x520")
    win.minsize(560, 400)
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    win.grab_set()

    _files = []        # list of (src_txt, dst_wav)
    _status_vars = []  # list of tk.StringVar

    def _unique_wav(base: str) -> str:
        candidate = os.path.join(OUTPUT_DIR, f"{base}.wav")
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(OUTPUT_DIR, f"{base} ({counter}).wav")
            counter += 1
        return candidate

    def _refresh_rows():
        for w in scroll_inner.winfo_children():
            w.destroy()
        _status_vars.clear()

        if not _files:
            tk.Label(scroll_inner, text="Выберите папку или файлы ⬆",
                     bg=Colors.BG_DARK, fg=Colors.TEXT_DIM,
                     font=("Segoe UI", 11)).pack(pady=60)
            count_lbl.config(text="0 файлов")
            btn_run.config(state="disabled")
            return

        for i, (src, dst) in enumerate(_files):
            sv = tk.StringVar(value="⏳ Ожидает")
            _status_vars.append(sv)

            row = tk.Frame(scroll_inner, bg=Colors.BG_CARD,
                           highlightthickness=1,
                           highlightbackground=Colors.BORDER)
            row.pack(fill="x", padx=8, pady=2)

            tk.Label(row, text=f"{i+1}.", width=3,
                     bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
                     font=("Consolas", 9)).pack(side="left", padx=(6, 2), pady=6)

            tk.Label(row, text=os.path.basename(src), anchor="w",
                     bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
                     font=("Segoe UI", 9)).pack(side="left", fill="x",
                                                expand=True, pady=6)

            tk.Label(row, textvariable=sv, width=14, anchor="e",
                     bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
                     font=("Consolas", 8)).pack(side="right", padx=8)

        count_lbl.config(text=f"{len(_files)} файлов")
        btn_run.config(state="normal")

    def _pick_folder():
        folder = filedialog.askdirectory(title="Выбрать папку с TXT-файлами")
        if not folder:
            return
        txts = sorted(f for f in os.listdir(folder) if f.lower().endswith(".txt"))
        if not txts:
            messagebox.showinfo("📂 Пусто", "В папке нет .txt файлов", parent=win)
            return
        _files.clear()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        for fname in txts:
            src = os.path.join(folder, fname)
            base = os.path.splitext(fname)[0]
            _files.append((src, _unique_wav(base)))
        _refresh_rows()

    def _pick_files():
        paths = filedialog.askopenfilenames(
            title="Выбрать TXT-файлы",
            filetypes=[("TXT", "*.txt")]
        )
        if not paths:
            return
        _files.clear()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        for p in sorted(paths):
            base = os.path.splitext(os.path.basename(p))[0]
            _files.append((p, _unique_wav(base)))
        _refresh_rows()

    def _start_status_tracker():
        def _tick():
            if not win.winfo_exists():
                return
            queue = task_manager.get_queue()
            for i, (src, dst) in enumerate(_files):
                if i >= len(_status_vars):
                    break
                sv = _status_vars[i]
                for t in queue:
                    if (t.quality_params or {}).get("output_path_override") == dst:
                        if t.status == "done":
                            win.after(0, lambda s=sv: s.set("✔ Готово"))
                        elif t.status == "error":
                            win.after(0, lambda s=sv: s.set("❌ Ошибка"))
                        elif t.status == "cancelled":
                            win.after(0, lambda s=sv: s.set("⛔ Отменено"))
                        elif t.status in ("running", "generate", "merge",
                                          "chunking", "normalize", "reference"):
                            win.after(0, lambda s=sv, p=t.progress: s.set(f"▶ {p}%"))
                        elif t.status == "queued":
                            win.after(0, lambda s=sv: s.set("▶ В очереди"))
                        break
            try:
                win.after(400, _tick)
            except Exception:
                pass
        _tick()

    def _run_batch():
        ref = clean_path(ref_var.get().strip())
        if not ref or not os.path.isfile(ref):
            messagebox.showerror("❌ Ошибка",
                                 "Сначала выберите голос-референс", parent=win)
            return
        if not _files:
            return

        quality_name = quality_var.get()
        if quality_name not in quality_params:
            quality_name = "Высокое качество"
        params = quality_params[quality_name]

        btn_run.config(state="disabled")
        btn_folder.config(state="disabled")
        btn_files.config(state="disabled")

        for i, (src, dst) in enumerate(_files):
            try:
                with open(src, "r", encoding="utf-8") as f:
                    raw = f.read()
            except Exception as e:
                if i < len(_status_vars):
                    _status_vars[i].set("❌ Ошибка")
                print(f"[Batch] Cannot read {src}: {e}")
                continue

            text = normalize_text(raw)
            if not text.strip():
                if i < len(_status_vars):
                    _status_vars[i].set("⚠ Пустой")
                continue

            if i < len(_status_vars):
                _status_vars[i].set("▶ В очереди")

            task = Task(
                text=text,
                raw_text=raw.strip(),
                voice=ref,
                speed=params["speed"].get(),
                language=lang_var.get(),
                quality=quality_name,
                quality_params={
                    **{k: v.get() for k, v in params.items()},
                    "word_replacer_enabled": word_replacer_enabled.get(),
                    "lang_split_enabled": lang_split_enabled.get(),
                    "use_gpt": use_gpt.get(),
                    "ai_conductor_enabled": params.get("ai_conductor_enabled", tk.BooleanVar()).get(),
                }
            )
            task_manager.add_task(task)

        win.after(500, lambda: (
            btn_folder.config(state="normal"),
            btn_files.config(state="normal"),
        ))
        _start_status_tracker()

    # ── LAYOUT ───────────────────────────────────────────────────────────────
    toolbar = tk.Frame(win, bg=Colors.BG_CARD, pady=6)
    toolbar.pack(fill="x")

    def _tb_btn(text, cmd):
        b = tk.Button(toolbar, text=text, command=cmd,
                      bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
                      activebackground=Colors.BG_HOVER,
                      activeforeground=Colors.TEXT_MAIN,
                      relief="flat", bd=0, font=("Segoe UI", 9),
                      padx=10, pady=4, cursor="hand2")
        b.bind("<Enter>", lambda e: b.config(bg=Colors.BG_HOVER))
        b.bind("<Leave>", lambda e: b.config(bg=Colors.BG_INPUT))
        return b

    btn_folder = _tb_btn("📂 Выбрать папку", _pick_folder)
    btn_folder.pack(side="left", padx=(10, 4))

    btn_files = _tb_btn("📄 Выбрать файлы", _pick_files)
    btn_files.pack(side="left", padx=(0, 4))

    count_lbl = tk.Label(toolbar, text="0 файлов",
                         bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
                         font=("Segoe UI", 9))
    count_lbl.pack(side="left", padx=8)

    # текущий голос — справа в тулбаре
    _batch_voice_var = tk.StringVar()

    def _update_batch_voice(*_):
        p = ref_var.get().strip()
        if not p:
            _batch_voice_var.set("")
            return
        folder = os.path.basename(os.path.dirname(p))
        name   = os.path.splitext(os.path.basename(p))[0]
        _batch_voice_var.set(folder if name.lower() == "normalized" else name)

    ref_var.trace_add("write", _update_batch_voice)
    _update_batch_voice()

    tk.Label(toolbar, text="Голос:", bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
             font=("Segoe UI", 8)).pack(side="right", padx=(0, 2))
    tk.Label(toolbar, textvariable=_batch_voice_var, bg=Colors.BG_CARD,
             fg=Colors.ACCENT, font=("Segoe UI", 8),
             width=18, anchor="e").pack(side="right", padx=(0, 10))

    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x")

    # список файлов (прокручиваемый)
    list_outer = tk.Frame(win, bg=Colors.BG_DARK)
    list_outer.pack(fill="both", expand=True)

    canvas = tk.Canvas(list_outer, bg=Colors.BG_DARK, bd=0, highlightthickness=0)
    scrollbar = tk.Scrollbar(list_outer, orient="vertical",
                             command=canvas.yview,
                             bg=Colors.BG_INPUT, troughcolor=Colors.BG_DARK)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    scroll_inner = tk.Frame(canvas, bg=Colors.BG_DARK)
    cw = canvas.create_window((0, 0), window=scroll_inner, anchor="nw")

    scroll_inner.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>",
                lambda e: canvas.itemconfig(cw, width=e.width))

    def _on_mousewheel(e):
        try:
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        except Exception:
            pass
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x")

    # нижняя панель
    bottom = tk.Frame(win, bg=Colors.BG_CARD, pady=8)
    bottom.pack(fill="x", side="bottom")

    tk.Label(bottom, text="Пресет:", bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
             font=("Segoe UI", 9)).pack(side="left", padx=(12, 4))
    tk.Label(bottom, textvariable=quality_var, bg=Colors.BG_CARD,
             fg=Colors.TEXT_MAIN,
             font=("Segoe UI", 9, "bold")).pack(side="left")

    btn_run = tk.Button(
        bottom, text="🚀 Запустить пакет",
        command=_run_batch,
        bg=Colors.BG_ACTIVE, fg=Colors.TEXT_MAIN,
        activebackground="#2ea043", activeforeground=Colors.TEXT_MAIN,
        relief="flat", bd=0, font=("Segoe UI", 10, "bold"),
        padx=18, pady=5, cursor="hand2", state="disabled"
    )
    btn_run.pack(side="right", padx=12)

    def _on_close():
        canvas.unbind_all("<MouseWheel>")
        win.destroy()
    win.protocol("WM_DELETE_WINDOW", _on_close)

    # начальный placeholder
    _refresh_rows()


# =========================
# CANCEL / GENERATE
# =========================
def cancel_task():
    global current_task
    if current_task is None:
        return
    task_manager.cancel_task(current_task.id)
    clear_chunk_highlight()
    unlock_textbox()
    set_status("⛔ Отмена задачи...")
    set_stage("CANCELLING")
    set_progress(0)
    root.after(0, lambda: set_ai_pulse(False))

def generate():
    global current_task, current_text_snapshot
    hide_placeholder()

    try:
        if PYGAME_OK and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        if PYGAME_OK:
            pygame.mixer.music.unload()
    except Exception:
        pass

    raw_text = text_box.get("1.0", "end-1c")
    text = normalize_text(raw_text)
    ref = clean_path(ref_var.get().strip())

    if not text:
        messagebox.showerror("❌ Ошибка", "Текст пустой")
        return
    if not ref or not os.path.isfile(ref):
        messagebox.showerror("❌ Ошибка", "Выберите reference audio")
        return

    current_text_snapshot = text

    global _highlight_pos
    _highlight_pos = 0
    try:
        _textbox_updated.clear()
    except Exception:
        pass
    clear_chunk_highlight()

    lock_textbox()
    text_box.update_idletasks()

    quality_name = quality_var.get()
    if quality_name not in quality_params:
        quality_name = "Высокое качество"
        quality_var.set(quality_name)
    params = quality_params[quality_name]

    current_task = Task(
        text=text,
        raw_text=raw_text.strip(),
        voice=ref,
        speed=params["speed"].get(),
        language=lang_var.get(),
        quality=quality_name,
        quality_params={
            **{k: v.get() for k, v in params.items()},
            "word_replacer_enabled": word_replacer_enabled.get(),
            "lang_split_enabled": lang_split_enabled.get(),
            "use_gpt": use_gpt.get(),
            "ai_conductor_enabled": params.get("ai_conductor_enabled", tk.BooleanVar()).get(),
            "ai_conductor_context": params.get("ai_conductor_context", tk.StringVar()).get(),
        }
    )

    set_status("📥 Добавлено в очередь...")
    set_stage("QUEUED")
    set_progress(0)

    task_manager.add_task(current_task)
    root.after(0, update_queue_view)
    save_settings()


# =========================
def toggle_console():
    if console_visible.get():
        console_inner.pack_forget()
        console_visible.set(False)
        toggle_btn.config(text="📋 Console ▲")
    else:
        console_inner.pack(fill="x", padx=8, pady=(0, 7))
        console_visible.set(True)
        toggle_btn.config(text="📋 Console ▼")

def show_context_menu(event):
    menu = tk.Menu(
        root, tearoff=0, bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
        activebackground=Colors.BG_HOVER, activeforeground=Colors.TEXT_MAIN,
        relief="flat", borderwidth=1
    )
    menu.add_command(
        label="Копировать",
        command=lambda: (
            root.clipboard_clear(),
            root.clipboard_append(console_text.get(tk.SEL_FIRST, tk.SEL_LAST))
        ) if console_text.tag_ranges(tk.SEL) else None
    )
    menu.add_separator()
    menu.add_command(label="🗑️ Очистить", command=clear_console)
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()

def clear_console():
    console_text.delete("1.0", tk.END)

# =========================
# LANGUAGE PICKER
# =========================
def pick_language():
    win = tk.Toplevel(root)
    win.title("🌐 Язык модели")
    win.resizable(False, False)
    win.configure(bg=Colors.BG_CARD)
    win.grab_set()

    langs = [
        ("Авто", "auto"), ("RU", "ru"), ("EN", "en"),
        ("ES", "es"), ("FR", "fr"), ("DE", "de"),
        ("IT", "it"), ("PT", "pt"), ("PL", "pl"),
        ("TR", "tr"), ("NL", "nl"), ("CS", "cs"),
        ("AR", "ar"), ("ZH", "zh-cn"), ("HU", "hu"),
        ("KO", "ko"), ("JA", "ja"), ("HI", "hi"),
    ]

    tk.Label(win, text="Выберите язык модели", bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
             font=("Segoe UI", 12, "bold")).pack(pady=(15, 10))
    grid = tk.Frame(win, bg=Colors.BG_CARD)
    grid.pack(padx=15, pady=(0, 15))

    for i, (label, value) in enumerate(langs):
        tk.Radiobutton(
            grid, text=label, variable=lang_var, value=value,
            indicatoron=False, width=6,
            bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
            selectcolor=Colors.ACCENT, activebackground=Colors.BG_HOVER,
            font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2"
        ).grid(row=i // 6, column=i % 6, padx=3, pady=3)

    tk.Frame(win, bg=Colors.BG_CARD, height=1).pack(fill="x", padx=15, pady=(5,0))
    split_row = tk.Frame(win, bg=Colors.BG_CARD)
    split_row.pack(fill="x", padx=15, pady=(8, 0))
    cb = tk.Checkbutton(
        split_row,
        text="🔀 Авто-переключение языка",
        variable=lang_split_enabled,
        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
        selectcolor=Colors.BG_INPUT,
        activebackground=Colors.BG_CARD,
        activeforeground=Colors.TEXT_MAIN,
        font=("Segoe UI", 9),
        cursor="hand2"
    )
    cb.pack(side="left")
    ToolTip(cb, "Английские слова от трёх и больше слов читаются на английском автоматически.\nОтключите если хотите поменять акцент.")

    tk.Button(
        win, text="✓ Закрыть", command=lambda: [win.destroy(), save_settings()],
        bg=Colors.BG_ACTIVE, fg=Colors.TEXT_MAIN, relief="flat",
        font=("Segoe UI", 10, "bold"), cursor="hand2", padx=20, pady=5
    ).pack(pady=(0, 15))

# =========================
# HELP
# =========================
def show_help():
    win = tk.Toplevel(root)
    win.title("❓ Справка")
    win.geometry("650x550")
    win.resizable(True, True)
    win.configure(bg=Colors.BG_CARD)
    win.grab_set()

    frame = tk.Frame(win, bg=Colors.BG_CARD)
    frame.pack(fill="both", expand=True, padx=15, pady=15)
    scrollbar = tk.Scrollbar(frame, bg=Colors.BG_INPUT, troughcolor=Colors.BG_DARK)
    scrollbar.pack(side="right", fill="y")
    text = tk.Text(
        frame, wrap="word", yscrollcommand=scrollbar.set,
        font=("Consolas", 12), bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN,
        padx=15, pady=15, state="normal", relief="flat", highlightthickness=0
    )
    text.pack(fill="both", expand=True)
    scrollbar.config(command=text.yview)

    text.tag_configure("header", foreground=Colors.ACCENT, font=("Consolas", 11))
    text.tag_configure("symbol", foreground="#ffd600", font=("Consolas", 9))
    text.tag_configure("good", foreground=Colors.TEXT_SUCCESS)
    text.tag_configure("bad", foreground=Colors.TEXT_ERROR)
    text.tag_configure("normal", foreground=Colors.TEXT_MAIN)
    text.tag_configure("comment", foreground=Colors.TEXT_DIM)

    content = [
        ("header", "\n🤖 AI ФУНКЦИИ\n"),

        ("good", "Флажок ✨ AI (главное окно) — улучшение текста перед генерацией\n"),
        ("comment", "Технический редактор: раскрывает сокращения, убирает спецсимволы,\nразбивает длинные предложения. Смысл и стиль не меняет.\n\n"),

        ("good", "Кнопка 🤖 AI — AI Conductor\n"),
        ("comment", "Анализирует весь текст и назначает параметры XTTS для каждого чанка.\nПросодия и смарт-паузы отключаются — AI управляет ими напрямую.\nЭкспериментальная функция: результат зависит от провайдера и модели.\n\n"),

        ("good", "AI Conductor — Уровень 1: параметры движка\n"),
        ("comment", "Temperature, speed, паузы и прочие параметры назначаются индивидуально\nдля каждого чанка на основе контекста и интонации.\n\n"),

        ("good", "AI Conductor — Уровень 2: стиль текста\n"),
        ("comment", "Включается отдельным переключателем внутри окна кондуктора.\nAI переписывает текст под заданный жанр или настроение перед генерацией.\nФакты и названия сохраняются — меняется форма подачи.\nМожно добавить negative prompt: чего избегать при переработке.\n\n"),

        ("normal", "Оба уровня работают независимо и могут комбинироваться\n"),
        ("comment", "Сначала текст переписывается (уровень 2), затем под новый текст\nназначаются параметры чанков (уровень 1).\n\n"),

        ("good", "Настроение референса влияет на результат не меньше параметров\n"),
        ("comment", "Если референс записан нейтрально — драматический стиль даст слабый эффект.\nДля лучшего результата подбирайте референс под заданный стиль.\n"),

        ("header", "🎯 АВТОМАТИЧЕСКАЯ ОБРАБОТКА\n"),

        ("good", "Числа → слова (авто)\n"),
        ("comment", "«2024» → «две тысячи двадцать четыре», «3.5» → «три целых пять»\n\n"),

        ("good", "Аббревиатуры → словарь произношений\n"),
        ("comment", "Английские слова автоматически распознаются и добавляются в словарь.\nНеизвестные термины читаются кириллицей по фонетике.\n\n"),

        ("good", "Пунктуационные и смысловые паузы → автоматически\n"),
        ("comment", "Модель сама расставляет паузы по знакам препинания и контексту.\n\n"),

        ("good", "Нормализация текста → автоматически\n"),
        ("comment", "Лишние пробелы, двойные знаки, артефакты — убираются до генерации.\n\n"),

        ("good", "Контроль качества чанков → авто-перегенерация\n"),
        ("comment", "Если модель выдала повторы или обрыв — чанк перегенерируется до 3 раз.\nВключается в настройках пресета (🛡 QC).\n\n"),

        ("header", "\n⏸️ ПАУЗЫ\n"),

        ("symbol", ".  "), ("normal", "стандартная пауза (~400 мс)\n"),
        ("symbol", ",  "), ("normal", "короткая пауза (~150 мс)\n"),
        ("symbol", "?  "), ("normal", "вопросительная интонация\n"),
        ("symbol", "!  "), ("normal", "восклицательная интонация\n"),
        ("symbol", "—  "), ("normal", "нормализуется в запятую\n"),
        ("symbol", ":  "), ("normal", "пауза перед пояснением\n"),
        ("symbol", "…  "), ("normal", "длинная пауза с затуханием\n\n"),

        ("header", "\n💬 СМЫСЛОВЫЕ ПАУЗЫ\n"),

        ("normal", "Перед «но», «однако», «хотя» → короткая пауза\n"),
        ("normal", "После «поэтому», «итак», «таким образом» → пауза вывода\n"),
        ("normal", "Перед «важно», «главное», «ключевое» → выделение\n"),
        ("normal", "Перед «например», «к примеру», «допустим» → пауза пояснения\n"),
        ("comment", "Паузы вставляются автоматически — вручную ничего расставлять не нужно.\n\n"),

        ("header", "\n📋 СПИСКИ\n"),

        ("good", "1. Первый пункт → читается как «первый»\n"),
        ("good", "2. Второй пункт → читается как «второй»\n"),
        ("comment", "Пункты 1–20 читаются порядковыми числительными, далее — цифрами.\nКаждый пункт получает паузу после номера автоматически.\n\n"),

        ("header", "\n🎨 ПРЕСЕТЫ\n"),

        ("normal", "⭐ Высокое качество — стабильный нейтральный голос\n"),
        ("normal", "📖 Нарратив — медленно, плавно, для книг и лекций\n"),
        ("normal", "⚡ Динамика — бодро, быстро, для рекламы и роликов\n"),
        ("normal", "🎭 Экспрессия — эмоционально, для драматичных сцен\n"),
        ("comment", "Двойной клик на пресете открывает тонкие настройки.\n\n"),

        ("header", "\n🎤 РЕФЕРЕНС\n"),

        ("good", "Оптимальная длина: 10–20 секунд\n"),
        ("good", "Тихая комната, без музыки и эха\n"),
        ("good", "Нейтральная эмоция, разборчивая речь\n"),
        ("good", "Автоматическая обрезка тишины и нормализация громкости\n"),
        ("good", "Файл сохраняется в библиотеку для повторного использования\n"),
        ("comment", "Чем чище референс — тем стабильнее клонирование.\nSNR ниже 8 dB даст заметные артефакты.\n\n"),

        ("header", "\n⚙️ СОВЕТЫ\n"),

        ("normal", "Длинный текст автоматически бьётся на чанки — ограничений нет\n"),
        ("normal", "Словарь произношений — первая помощь при артефактах на конкретном слове\n"),
        ("normal", "Если голос «плывёт» к концу — уменьши Temperature в настройках пресета\n"),
        ("normal", "Повторы и «каша» — увеличь Repetition Penalty\n"),
        ("comment", "Кэш чанков ускоряет повторную генерацию того же текста тем же голосом.\n"),
    ]

    for tag, content_text in content:
        text.insert("end", content_text, tag)
    text.config(state="disabled")

    def close_window():
        save_settings()
        win.destroy()
    win.protocol("WM_DELETE_WINDOW", close_window)

# =========================
# QUALITY PARAMS
# =========================
quality_params = {
    "Высокое качество": {
        "qc_enabled": tk.BooleanVar(value=True),
        "temperature": tk.DoubleVar(value=0.70),
        "top_p": tk.DoubleVar(value=0.30),
        "top_k": tk.IntVar(value=80),
        "repetition_penalty": tk.DoubleVar(value=13.0),
        "prosody_intensity": tk.DoubleVar(value=0.0),
        "de_esser_intensity": tk.DoubleVar(value=0.8),
        "trim_ms": tk.IntVar(value=100),
        "speed": tk.DoubleVar(value=1.0),
        "trim_mode": tk.StringVar(value="auto"),
        "export_format": tk.StringVar(value="wav"),
        "use_gpt": tk.BooleanVar(value=use_gpt.get()),
        "ai_conductor_enabled": tk.BooleanVar(value=False),
    },

    "Нарратив": {
        "qc_enabled": tk.BooleanVar(value=True),
        "temperature": tk.DoubleVar(value=0.75),
        "top_p": tk.DoubleVar(value=0.25),
        "top_k": tk.IntVar(value=85),
        "repetition_penalty": tk.DoubleVar(value=18.0),
        "prosody_intensity": tk.DoubleVar(value=0.5),
        "de_esser_intensity": tk.DoubleVar(value=0.7),
        "trim_ms": tk.IntVar(value=80),
        "speed": tk.DoubleVar(value=0.9),
        "trim_mode": tk.StringVar(value="auto"),
        "export_format": tk.StringVar(value="wav"),
        "use_gpt": tk.BooleanVar(value=use_gpt.get()),
        "ai_conductor_enabled": tk.BooleanVar(value=False),
    },

    "Динамика": {
        "qc_enabled": tk.BooleanVar(value=True),
        "temperature": tk.DoubleVar(value=0.82),
        "top_p": tk.DoubleVar(value=0.20),
        "top_k": tk.IntVar(value=100),
        "repetition_penalty": tk.DoubleVar(value=16.0),
        "prosody_intensity": tk.DoubleVar(value=1.1),
        "de_esser_intensity": tk.DoubleVar(value=1.0),
        "trim_ms": tk.IntVar(value=60),
        "speed": tk.DoubleVar(value=1.1),
        "trim_mode": tk.StringVar(value="auto"),
        "export_format": tk.StringVar(value="wav"),
        "use_gpt": tk.BooleanVar(value=use_gpt.get()),
        "ai_conductor_enabled": tk.BooleanVar(value=False),
    },

    "Экспрессия": {
        "qc_enabled": tk.BooleanVar(value=True),
        "temperature": tk.DoubleVar(value=0.88),
        "top_p": tk.DoubleVar(value=0.30),
        "top_k": tk.IntVar(value=90),
        "repetition_penalty": tk.DoubleVar(value=14.0),
        "prosody_intensity": tk.DoubleVar(value=1.3),
        "de_esser_intensity": tk.DoubleVar(value=1.3),
        "trim_ms": tk.IntVar(value=100),
        "speed": tk.DoubleVar(value=1.0),
        "trim_mode": tk.StringVar(value="auto"),
        "export_format": tk.StringVar(value="wav"),
        "use_gpt": tk.BooleanVar(value=use_gpt.get()),
        "ai_conductor_enabled": tk.BooleanVar(value=False),
    },
}
# =========================
# PRESET DESCRIPTIONS (для меню "Стили")
# =========================
PRESET_DESCRIPTIONS = {
    "Нарратив": "📖 Нарратив\nСпокойное, плавное чтение.\nМедленный темп, ровная интонация.\nИдеально для книг и озвучки текста\nНажмите чтобы открыть настройки.",
    "Динамика": "⚡ Динамика\nБодрый, энергичный голос.\nУскоренный темп, живые интонации.\nПодходит для рекламы и роликов\nНажмите чтобы открыть настройки.",
    "Экспрессия": "🎭 Экспрессия\nМаксимально эмоциональная подача.\nЯркие интонации и выразительность.\nДля драматичных сцен и эмоций\nНажмите чтобы открыть настройки.",
}

def open_quality_settings(preset_name):
    if preset_name not in quality_params:
        preset_name = "Высокое качество"
    win = tk.Toplevel(root)
    win.title(f"⚙ Настройки — {preset_name}")
    win.resizable(False, True)
    win.configure(bg=Colors.BG_CARD)
    win.grab_set()
    params = quality_params[preset_name]

    win.update_idletasks()
    screen_h = win.winfo_screenheight()
    max_h = int(screen_h * 0.85)
    win.maxsize(600, max_h)

    fields = [
        ("temperature", "Temperature", 0.1, 1.0, 0.05,
        "Случайность голоса.\n\nНизко — стабильно и ровно.\nВысоко — более живо, но менее предсказуемо."),

        ("top_p", "Top P", 0.1, 1.0, 0.05,
        "Ограничивает выбор вариантов.\n\nМеньше — стабильнее.\nБольше — естественнее."),

        ("top_k", "Top K", 10, 100, 5,
        "Сколько вариантов модель рассматривает.\n\nМеньше — чище.\nБольше — разнообразнее."),

        ("repetition_penalty", "Repetition Penalty", 1.0, 20.0, 0.5,
        "Убирает повторы.\n\nВыше — меньше артефактов.\nНиже — естественнее но рискованнее"),

        ("speed", "Скорость речи", 0.75, 2.25, 0.05,
        "Скорость озвучки.\n\nМедленно\Быстрее"),

        ("prosody_intensity", "Просодия", 0.0, 2.0, 0.1,
        "Выразительность речи.\n\n0 — ровно.\n1 — естественно.\n2 — очень эмоционально."),

        ("de_esser_intensity", "Де-эссер", 0.0, 2.0, 0.1,
        "Подавление избыточных шипящих/свистящих звуков (С/Ш/Ц/Щ).\n\n0 — выключено.\n1 — стандартно.\n2 — агрессивно."),

        ("trim_ms", "Trim конца (мс)", 0, 300, 10,
        "Обрезка хвоста аудио.\n\nУбирает шум и затухание в конце чанка."),
    ]

    trim_scale = None
    for key, label, from_, to, res, hint in fields:
        row = tk.Frame(win, bg=Colors.BG_CARD)
        row.pack(fill="x", padx=15, pady=5)
        lbl = tk.Label(row, text=label, width=20, anchor="w",
                       bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, font=("Segoe UI", 10))
        lbl.pack(side="left")
        ToolTip(lbl, hint)

        scale = tk.Scale(
            row, variable=params[key], from_=from_, to=to, resolution=res,
            orient="horizontal", length=240,
            bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, troughcolor=Colors.BG_INPUT,
            highlightthickness=0, sliderrelief="flat", sliderlength=20, font=("Segoe UI", 9)
        )
        scale.pack(side="left", padx=(10, 5))

        tk.Label(row, textvariable=params[key], width=6,
                 bg=Colors.BG_CARD, fg=Colors.ACCENT, font=("Consolas", 9)).pack(side="left")
        if key == "trim_ms":
            trim_scale = scale

    mode_row = tk.Frame(win, bg=Colors.BG_CARD)
    mode_row.pack(fill="x", padx=15, pady=5)
    trim_lbl = tk.Label(mode_row, text="Режим Trim:", width=20, anchor="w",
                        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, font=("Segoe UI", 10))
    trim_lbl.pack(side="left")
    ToolTip(trim_lbl, "Авто / Ручной / Выкл")

    tk.Radiobutton(mode_row, text="Авто", variable=params["trim_mode"], value="auto",
                   bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, selectcolor=Colors.BG_CARD,
                   activebackground=Colors.BG_CARD, font=("Segoe UI", 9)).pack(side="left", padx=5)
    tk.Radiobutton(mode_row, text="Ручной", variable=params["trim_mode"], value="manual",
                   bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, selectcolor=Colors.BG_CARD,
                   activebackground=Colors.BG_CARD, font=("Segoe UI", 9)).pack(side="left", padx=5)
    tk.Radiobutton(mode_row, text="Выкл", variable=params["trim_mode"], value="off",
                   bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, selectcolor=Colors.BG_CARD,
                   activebackground=Colors.BG_CARD, font=("Segoe UI", 9)).pack(side="left")
    
    fmt_row = tk.Frame(win, bg=Colors.BG_CARD)
    fmt_row.pack(fill="x", padx=15, pady=(5, 0))
    tk.Label(fmt_row, text="Формат экспорта:", width=20, anchor="w",
            bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, font=("Segoe UI", 10)).pack(side="left")
    tk.Radiobutton(fmt_row, text="WAV", variable=params["export_format"], value="wav",
                bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, selectcolor=Colors.BG_CARD,
                activebackground=Colors.BG_CARD, font=("Segoe UI", 9)).pack(side="left", padx=5)
    tk.Radiobutton(fmt_row, text="MP3 192k", variable=params["export_format"], value="mp3",
                bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, selectcolor=Colors.BG_CARD,
                activebackground=Colors.BG_CARD, font=("Segoe UI", 9)).pack(side="left", padx=5)
    

    def update_trim_state(*args):
        if trim_scale:
            try:
                if params["trim_mode"].get() == "manual":
                    trim_scale.config(state="normal", fg=Colors.TEXT_MAIN, troughcolor=Colors.BG_INPUT)
                else:
                    trim_scale.config(state="disabled", fg=Colors.TEXT_DIM, troughcolor=Colors.BG_DARK)
            except Exception:
                pass

    params["trim_mode"].trace_add("write", update_trim_state)
    update_trim_state()

    def reset():
            defaults = {
                "Высокое качество": (0.70, 0.30, 80, 13.0, 1.0, 100, "auto", 0.0, 0.8),
                "Нарратив":         (0.75, 0.25, 85,  18.0, 0.9, 80, "auto", 0.5, 0.7),
                "Динамика":         (0.82, 0.20, 100, 16.0, 1.1, 60, "auto", 1.1, 1.0),
                "Экспрессия":       (0.88, 0.30, 90,  14.0, 1.0, 100, "auto", 1.3, 1.3),
            }
            d = defaults.get(preset_name, (0.70, 0.30, 80, 13.0, 1.0, 80, "auto", 0.8, 1.0))
            params["temperature"].set(d[0])
            params["top_p"].set(d[1])
            params["top_k"].set(d[2])
            params["repetition_penalty"].set(d[3])
            params["speed"].set(d[4])
            params["trim_ms"].set(d[5])
            params["trim_mode"].set(d[6])
            params["prosody_intensity"].set(d[7])
            params["de_esser_intensity"].set(d[8])
            params["export_format"].set("wav")

    # QC чекбокс
    qc_row = tk.Frame(win, bg=Colors.BG_CARD)
    qc_row.pack(fill="x", padx=15, pady=(5, 0))
    qc_cb = tk.Checkbutton(
        qc_row,
        text="🛡 Контроль качества (авто-перегенерация бракованных чанков)",
        variable=params["qc_enabled"],
        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
        selectcolor=Colors.BG_INPUT,
        activebackground=Colors.BG_CARD,
        activeforeground=Colors.TEXT_MAIN,
        font=("Segoe UI", 9),
        cursor="hand2"
    )
    qc_cb.pack(side="left")
    ToolTip(qc_cb, "Включает детектор повторов и валидатор длительности.\nПри браке — автоматическая перегенерация чанка (до 3 попыток).\nНемного замедляет генерацию.")

    btn_frame = tk.Frame(win, bg=Colors.BG_CARD)
    btn_frame.pack(fill="x", padx=15, pady=(10, 15))
    create_button(btn_frame, "🔄 Сбросить", reset, bg=Colors.BG_INPUT).pack(side="left", padx=(0, 10))
    create_button(btn_frame, "✓ Закрыть", lambda: [win.destroy(), save_settings()], bg=Colors.BG_ACTIVE).pack(side="left")

# =========================
# SETTINGS
# =========================
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")

def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings():
    data = {
        "language": lang_var.get(),
        "quality": quality_var.get(),
        "ref_path": ref_var.get(),
        "use_gpt": use_gpt.get(),
        "word_replacer_enabled": word_replacer_enabled.get(),
        "lang_split_enabled": lang_split_enabled.get(),
        "ai_conductor_enabled": any(
            params.get("ai_conductor_enabled", tk.BooleanVar()).get()
            for params in quality_params.values()
        ),
        "ai_conductor_context": next(
            (params["ai_conductor_context"].get()
             for params in quality_params.values()
             if "ai_conductor_context" in params),
            ""
        ),
        "quality_params": {
            preset: {
                k: (v.get() if hasattr(v, "get") else v)
                for k, v in params.items()
            }
            for preset, params in quality_params.items()
        }
    }
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def apply_settings(data):
    import traceback
    if not isinstance(data, dict):
        return
    if "language" in data:
        lang_var.set(data["language"])
    if "use_gpt" in data:
        use_gpt.set(data["use_gpt"])
    if "quality" in data:
        q = data["quality"]
        quality_var.set(q if q in quality_params else "Высокое качество")
    if "ref_path" in data:
        path = data["ref_path"]
        if path and os.path.isfile(path):
            ref_var.set(path)
    if "word_replacer_enabled" in data:
        word_replacer_enabled.set(data["word_replacer_enabled"])
    if "lang_split_enabled" in data:
        lang_split_enabled.set(data["lang_split_enabled"])
    if "ai_conductor_enabled" in data:
        for preset_name, params in quality_params.items():
            params["ai_conductor_enabled"].set(data["ai_conductor_enabled"])
        try:
            ai_btn.config(bg=Colors.BG_ACTIVE if data["ai_conductor_enabled"] else Colors.BG_INPUT)
        except NameError:
            pass
    if "ai_rewrite_enabled" in data:
        for preset_name, params in quality_params.items():
            if "ai_rewrite_enabled" in params:
                params["ai_rewrite_enabled"].set(data["ai_rewrite_enabled"])
    if "ai_rewrite_context" in data:
        for preset_name, params in quality_params.items():
            if "ai_rewrite_context" in params:
                params["ai_rewrite_context"].set(data["ai_rewrite_context"])
    if "ai_rewrite_negative" in data:
        for preset_name, params in quality_params.items():
            if "ai_rewrite_negative" in params:
                params["ai_rewrite_negative"].set(data["ai_rewrite_negative"])
    if "quality_params" in data:
        for preset, params in data["quality_params"].items():
            if preset in quality_params:
                for key, value in params.items():
                    if key in quality_params[preset]:
                        try:
                            quality_params[preset][key].set(value)
                        except Exception:
                            traceback.print_exc()
                            pass

# =========================
# LEFT PANEL
# =========================
header_frame = tk.Frame(left_panel, bg=Colors.BG_DARK)
header_frame.pack(fill="x", pady=(0, 8))

title_row = tk.Frame(header_frame, bg=Colors.BG_DARK)
title_row.pack(anchor="w")

tk.Label(
    title_row,
    text="XTTS Studio",
    bg=Colors.BG_DARK,
    fg=Colors.TEXT_MAIN,
    font=("Segoe UI", 16, "bold")
).pack(side="left", padx=(4, 0))

tk.Label(
    header_frame,
    text=" by EXIZ10TION",
    bg=Colors.BG_DARK,
    fg=Colors.TEXT_DIM,
    font=("Segoe UI", 9)
).pack(anchor="w")
def check_and_update():
    from engine.updater import check_update, apply_update, restart
    import tkinter.messagebox as mb

    set_status("🔄 Проверка обновлений...")
    def _run():
        result = check_update()
        if result.get("error"):
            root.after(0, lambda: mb.showerror("❌ Ошибка", result["error"]))
            set_status("⏳ Ожидание...")
            return
        if not result["available"]:
            root.after(0, lambda: mb.showinfo(
                "✅ Обновлений нет",
                f"У вас актуальная версия {result['local']}"
            ))
            set_status("⏳ Ожидание...")
            return
        confirmed = [False]
        def ask():
            confirmed[0] = mb.askyesno(
                "🆕 Доступно обновление",
                f"Версия {result['remote']} доступна.\nСейчас у вас {result['local']}.\n\nОбновить?"
            )
        root.after(0, ask)
        root.after(200, lambda: _do_update(confirmed, result))

    def _do_update(confirmed, result):
        if not confirmed[0]:
            set_status("⏳ Ожидание...")
            return
        set_status("📥 Загрузка обновления...")
        def _apply():
            ok = apply_update(result["files"], progress_callback=lambda i, t: set_progress(int(i/t*100)))
            if ok:
                root.after(0, lambda: mb.showinfo(
                    "✅ Готово",
                    "Обновление установлено.\nПриложение перезапустится."
                ))
                root.after(500, restart)
            else:
                root.after(0, lambda: mb.showwarning(
                    "⚠️ Частичное обновление",
                    "Некоторые файлы не удалось обновить.\nПроверьте соединение."
                ))
                set_status("⏳ Ожидание...")
        threading.Thread(target=_apply, daemon=True).start()

    threading.Thread(target=_run, daemon=True).start()

upd_btn = create_button(header_frame, "🆕 Обновить", check_and_update, bg=Colors.BG_INPUT, font_size=8)
upd_btn.pack(anchor="w", pady=(4, 0))

left_panel.update_idletasks()


# Reference
ref_card = create_card(left_panel, "🎤 Голос-референс")
ref_card.pack(fill="x", pady=(0, 8))
create_entry(ref_card, ref_var).pack(fill="x", padx=10, pady=(3, 7))
ref_btn_row = tk.Frame(ref_card, bg=Colors.BG_CARD)
ref_btn_row.pack(fill="x", padx=10, pady=(0, 7))
create_button(ref_btn_row, "📁 Выбрать", pick_reference, bg=Colors.BG_INPUT).pack(side="left")
tk.Label(ref_card, text="✅ Конвертирован в WAV\n✅ Обрезан\n✅ Нормализован\n✅ Сохранён в библиотеку",
         bg=Colors.BG_CARD, fg=Colors.TEXT_DIM, font=("Consolas", 8), justify="left", anchor="w"
         ).pack(fill="x", padx=10, pady=(3, 7))

# Voice library
voice_card = create_card(left_panel, "")
voice_card.pack(fill="x", pady=(0, 8))

# заголовок с разделителем
voice_header = tk.Frame(voice_card, bg=Colors.BG_CARD)
voice_header.pack(fill="x", padx=10, pady=(8, 6))
tk.Label(
    voice_header, text="📚 Библиотека голосов",
    bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
    font=("Segoe UI", 9, "bold"), anchor="w"
).pack(side="left")
def _voice_display_name() -> str:
    p = ref_var.get().strip()
    if not p:
        return ""
    folder = os.path.basename(os.path.dirname(p))
    name   = os.path.splitext(os.path.basename(p))[0]
    # если имя файла — "normalized", показываем имя папки (имя голоса)
    return folder if name.lower() == "normalized" else name

_voice_label_var = tk.StringVar()

def _update_voice_label(*_):
    _voice_label_var.set(_voice_display_name())

ref_var.trace_add("write", _update_voice_label)
_update_voice_label()

tk.Label(
    voice_header, textvariable=_voice_label_var,
    bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
    font=("Segoe UI", 7), anchor="e",
    width=16
).pack(side="right")

tk.Frame(voice_card, bg=Colors.BORDER, height=1).pack(fill="x", padx=10, pady=(0, 4))

# listbox с рамкой
voice_list_frame = tk.Frame(
    voice_card,
    bg=Colors.BORDER,
    highlightthickness=0,
    padx=1, pady=1
)
voice_list_frame.pack(fill="x", padx=10, pady=(0, 6))

voice_listbox = tk.Listbox(
    voice_list_frame, height=6,
    bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
    selectbackground=Colors.ACCENT, selectforeground=Colors.TEXT_MAIN,
    relief="flat", highlightthickness=0,
    font=("Segoe UI", 9),
    activestyle="none", exportselection=False
)
voice_listbox.pack(fill="both")
voice_listbox.bind("<<ListboxSelect>>", on_voice_select)

tk.Frame(voice_card, bg=Colors.BORDER, height=1).pack(fill="x", padx=10, pady=(0, 6))

# кнопки плеера
voice_btn_row = tk.Frame(voice_card, bg=Colors.BG_CARD)
voice_btn_row.pack(fill="x", padx=10, pady=(0, 8))

lib_btn = create_button(voice_btn_row, "📂", pick_backup_reference,
                        bg=Colors.BG_INPUT, width=3)
lib_btn.pack(side="left", padx=(0, 3))
ToolTip(lib_btn, "Выбрать голос из библиотеки")

create_button(voice_btn_row, "⏪", seek_back,
              bg=Colors.BG_INPUT, width=3).pack(side="left", padx=(0, 3))

play_btn = create_button(voice_btn_row, "▶", play_reference,
                         bg=Colors.BG_ACTIVE, width=3)
play_btn.pack(side="left", padx=(0, 3))

create_button(voice_btn_row, "⏩", seek_forward,
              bg=Colors.BG_INPUT, width=3).pack(side="left")
# Queue
queue_card = create_card(left_panel, "")
queue_card.pack(fill="x", pady=(0, 8))

tk.Label(
    queue_card,
    text="📋 Очередь задач",
    bg=Colors.BG_CARD,
    fg=Colors.TEXT_MAIN,
    font=("Segoe UI", 9, "bold"),
    anchor="w"
).pack(fill="x", padx=10, pady=(7, 3))

queue_listbox = tk.Listbox(
    queue_card, height=7,
    bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
    selectbackground=Colors.ACCENT, selectforeground=Colors.TEXT_MAIN,
    relief="flat", highlightthickness=0, font=("Consolas", 8),
    activestyle="none", exportselection=False
)
queue_listbox.pack(fill="x", padx=10, pady=(0, 4))

batch_btn_row = tk.Frame(queue_card, bg=Colors.BG_CARD)
batch_btn_row.pack(fill="x", padx=10, pady=(0, 7))
create_button(batch_btn_row, "📦 Пакетная обработка", open_batch_window,
              bg=Colors.BG_INPUT).pack(fill="x")


# =========================
# CONSOLE (MOVED TO LEFT PANEL UNDER QUEUE)
# =========================
console_card = create_card(left_panel, "")
console_card.pack(fill="x", pady=(0, 8), after=queue_card)

console_header = tk.Frame(console_card, bg=Colors.BG_CARD)
console_header.pack(fill="x", padx=8, pady=(7, 3))
toggle_btn = tk.Button(
    console_header, text="📋 Console ▼", command=toggle_console,
    bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
    activebackground=Colors.BG_HOVER, activeforeground=Colors.TEXT_MAIN,
    relief="flat", borderwidth=0, font=("Segoe UI", 8),
    cursor="hand2", padx=5, pady=1
)
toggle_btn.bind("<Enter>", lambda e: toggle_btn.config(bg=Colors.BG_HOVER))
toggle_btn.bind("<Leave>", lambda e: toggle_btn.config(bg=Colors.BG_INPUT))
toggle_btn.pack(side="left")

_clr_btn = tk.Button(
    console_header, text="🗑️", command=clear_console,
    bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
    activebackground=Colors.BG_HOVER, activeforeground=Colors.TEXT_MAIN,
    relief="flat", borderwidth=0, font=("Segoe UI", 8),
    cursor="hand2", padx=5, pady=1
)
_clr_btn.bind("<Enter>", lambda e: _clr_btn.config(bg=Colors.BG_HOVER))
_clr_btn.bind("<Leave>", lambda e: _clr_btn.config(bg=Colors.BG_INPUT))
_clr_btn.pack(side="right")

console_inner = tk.Frame(console_card, bg=Colors.BG_CARD)
console_inner.pack(fill="x", padx=8, pady=(0, 7))

console_text = tk.Text(
    console_inner, height=12,
    bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN,
    font=("Consolas", 9,), state="normal", wrap="word", cursor="arrow",
    relief="flat", highlightthickness=1, highlightbackground=Colors.BORDER,
    padx=10, pady=10
)
console_text.bind("<Control-c>", lambda e: (
    root.clipboard_clear(),
    root.clipboard_append(console_text.get(tk.SEL_FIRST, tk.SEL_LAST)),
    "break"
)[-1] if console_text.tag_ranges(tk.SEL) else "break")
console_text.bind("<Control-C>", lambda e: (
    root.clipboard_clear(),
    root.clipboard_append(console_text.get(tk.SEL_FIRST, tk.SEL_LAST)),
    "break"
)[-1] if console_text.tag_ranges(tk.SEL) else "break")

console_scroll = tk.Scrollbar(console_inner, command=console_text.yview,
                              bg=Colors.BG_INPUT, troughcolor=Colors.BG_DARK)
console_text.configure(yscrollcommand=console_scroll.set)
console_scroll.pack(side="right", fill="y")
console_text.pack(fill="both", expand=True)
console_text.tag_configure("error", foreground=Colors.TEXT_ERROR)
console_text.tag_configure("warn", foreground=Colors.TEXT_WARNING)
console_text.tag_configure("ok", foreground=Colors.TEXT_SUCCESS)
console_text.tag_configure("info", foreground=Colors.TEXT_MAIN)
console_redirect.attach(console_text)
console_text.bind("<Button-3>", show_context_menu)

# Spacer
tk.Frame(left_panel, bg=Colors.BG_DARK).pack(fill="both", expand=True)

# =========================
# RIGHT PANEL
# =========================

# Text — НАВЕРХ
text_card = create_card(right_panel, "")
text_card.pack(fill="both", expand=True, pady=(0, 10))

text_header = tk.Frame(text_card, bg=Colors.BG_CARD)
text_header.pack(fill="x", padx=10, pady=(7, 0))

tk.Label(
    text_header,
    text="📝 Текст",
    bg=Colors.BG_CARD,
    fg=Colors.TEXT_MAIN,
    font=("Segoe UI", 11, "bold"),
    anchor="w"
).pack(side="left")

create_button(text_header, "❓ Справка", show_help, bg=Colors.BG_INPUT).pack(side="right")
text_box = tk.Text(
    text_card,
    bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN, insertbackground=Colors.TEXT_MAIN,
    relief="flat", highlightthickness=0, font=("Consolas", 11),
    padx=10, pady=10, wrap="word", undo=True
)
text_box.pack(fill="both", expand=True, padx=10, pady=7)
text_box.bind("<FocusIn>", hide_placeholder)
text_box.bind("<FocusOut>", lambda e: show_placeholder())
text_box.drop_target_register(DND_FILES)
text_box.dnd_bind("<<Drop>>", drop_handler)
text_box.bind("<Button-3>", show_text_context_menu)
# Горячие клавиши для любой раскладки (включая русскую)
text_box.bind("<Key>", on_text_key_press, add="+")
text_box.tag_configure("chunk_highlight", background=Colors.CHUNK_BG, foreground=Colors.CHUNK_FG)
show_placeholder()

# 1-я строка действий
text_btn_frame = tk.Frame(text_card, bg=Colors.BG_CARD)
text_btn_frame.pack(fill="x", padx=10, pady=(0, 4))
create_button(text_btn_frame, "📁 Загрузить", load_txt, bg=Colors.BG_INPUT).pack(side="left", padx=(0, 5))
create_button(text_btn_frame, "📋 Вставить", paste_clipboard, bg=Colors.BG_INPUT).pack(side="left", padx=(0, 5))
create_button(text_btn_frame, "🗑️Очистить", lambda: [set_textbox_content("")], bg=Colors.BG_INPUT).pack(side="left", padx=(0, 5))
chat_btn = create_button(text_btn_frame, "💬 AI Помощник", toggle_chat_panel, bg=Colors.BG_INPUT)
chat_btn.pack(side="left", padx=(0, 5))
ToolTip(chat_btn, "Открыть AI - чат-панель под редактором.\nТребует API-ключ (см. в ⚙ Настройки).")
chat_btn.pack(side="left", padx=(0, 5))
ToolTip(chat_btn, "Открыть окно Chat под текстовым полем.")
dict_btn = create_button(text_btn_frame, "📖 Словарь", open_word_replacer, bg=Colors.BG_INPUT)
dict_btn.pack(side="left", padx=(0, 5))
ToolTip(dict_btn, "Словарь произношений.\n\nАнглийские слова из текста автоматически\nраспознаются и добавляются — они будут\nчитаться кириллицей без артефактов.\n\nМожно добавлять и править — приоритет на пользовательское решение.")
create_button(text_btn_frame, "🎵 Аудио", open_outputs_folder, bg=Colors.BG_INPUT).pack(side="left", padx=(0, 5))

gpt_checkbox = tk.Checkbutton(
    text_btn_frame,
    text="✨ AI edit",
    variable=use_gpt,
    bg=Colors.BG_CARD,
    fg=Colors.TEXT_DIM,
    selectcolor=Colors.BG_INPUT,
    activebackground=Colors.BG_CARD,
    activeforeground=Colors.TEXT_MAIN,
    font=("Segoe UI", 9),
    cursor="hand2"
)
gpt_checkbox.pack(side="right")
ToolTip(gpt_checkbox, "Включает доработку текста через AI перед озвучкой")


# =========================
# 2-я строка действий: Язык/Справка слева, Стили/Высокое качество справа
# =========================
options_frame = tk.Frame(text_card, bg=Colors.BG_CARD)
options_frame.pack(fill="x", padx=10, pady=(0, 7))

# Левая часть (язык / справка)
left_opts = tk.Frame(options_frame, bg=Colors.BG_CARD)
left_opts.pack(side="left")
lang_btn = create_button(left_opts, "🌐 Язык генерации", pick_language, bg=Colors.BG_INPUT)
lang_btn.pack(side="left", padx=(0, 5))
ToolTip(lang_btn, lambda: f"Текущий язык: {lang_var.get()}\nМожно менять акцент")

create_button(left_opts, "📜 История", open_history, bg=Colors.BG_INPUT).pack(side="left", padx=(0, 5))

# Правая часть (стили / высокое качество)
right_opts = tk.Frame(options_frame, bg=Colors.BG_CARD)
right_opts.pack(side="right")

PRESET_HINT = "Режим по умолчанию.\nДвойной клик — открыть доп. параметры."
STYLES_HINT = "Открыть список стилей:\nНарратив / Динамика / Экспрессия.\nМногое зависит от референса"

# --- Кнопка "Стили" — открывает popup-меню с пресетами (ОТКРЫВАЕТСЯ ВВЕРХ) ---
def open_styles_menu(event=None):
    # Создаём кастомное popup
    menu = tk.Toplevel(root)
    menu.wm_overrideredirect(True)
    menu.configure(bg=Colors.MENU_BG, padx=4, pady=4)

    presets = [
        ("📖 Нарратив", "Нарратив"),
        ("⚡ Динамика", "Динамика"),
        ("🎭 Экспрессия", "Экспрессия"),
    ]

    default_desc = "Наведите на пресет —\nздесь появится его описание."

    def close_menu():
        try:
            menu.destroy()
        except Exception:
            pass

    def select_preset(name):
        quality_var.set(name)
        save_settings()
        # НЕ закрываем меню при одинарном клике, чтобы работал двойной

    def select_and_open(name):
        quality_var.set(name)
        save_settings()
        close_menu()
        open_quality_settings(name)

    # Создаём пункты пресетов
    for label, value in presets:
        is_active = (quality_var.get() == value)
        item_bg = Colors.MENU_ACTIVE if is_active else Colors.MENU_BG
        item = tk.Label(
            menu,
            text=label,
            bg=item_bg,
            fg=Colors.TEXT_MAIN,
            font=("Segoe UI", 10, "bold" if is_active else "normal"),
            padx=10, pady=5,
            anchor="w",
            cursor="hand2"
        )
        item.pack(fill="x", pady=1)

        def on_enter(e, w=item, active=is_active, name=value):
            if not active:
                w.config(bg=Colors.MENU_HOVER)
            desc_label.config(text=PRESET_DESCRIPTIONS.get(name, default_desc))
        def on_leave(e, w=item, active=is_active):
            if not active:
                w.config(bg=Colors.MENU_BG)

        item.bind("<Enter>", on_enter)
        item.bind("<Leave>", on_leave)
        # Одинарный клик - выбор
        item.bind("<Button-1>", lambda e, n=value: select_preset(n))
        # Двойной клик - выбор + открытие настроек
        item.bind("<Double-Button-1>", lambda e, n=value: select_and_open(n))


    # Разделитель
    sep = tk.Frame(menu, bg=Colors.BORDER, height=1)
    sep.pack(fill="x", padx=4, pady=(4, 4))

    # Описание пресета (внизу самого меню)
    desc_label = tk.Label(
        menu,
        text=default_desc,
        bg=Colors.MENU_BG,
        fg=Colors.TEXT_DIM,
        font=("Segoe UI", 8),
        justify="left",
        anchor="w",
        wraplength=200,
        padx=12, pady=6
    )
    desc_label.pack(fill="x")

    # Сбрасываем описание, когда курсор уходит с области описания
    def desc_leave(e):
        desc_label.config(text=default_desc)
    desc_label.bind("<Enter>", lambda e: None)
    desc_label.bind("<Leave>", desc_leave)

    # Позиционируем меню ВВЕРХ от кнопки
    menu.update_idletasks()
    menu_w = menu.winfo_reqwidth()
    menu_h = menu.winfo_reqheight()
    x = styles_btn.winfo_rootx()
    y = styles_btn.winfo_rooty() - menu_h - 4
    if y < 0:
        # если не помещается вверху — открываем вниз
        y = styles_btn.winfo_rooty() + styles_btn.winfo_height() + 4
    menu.wm_geometry(f"+{x}+{y}")

    # Закрытие при клике вне меню
    def click_outside(e):
        try:
            wx, wy = menu.winfo_rootx(), menu.winfo_rooty()
            ww, wh = menu.winfo_width(), menu.winfo_height()
            if not (wx <= e.x_root <= wx + ww and wy <= e.y_root <= wy + wh):
                close_menu()
                root.unbind_all("<Button-1>")
        except Exception:
            close_menu()

    # Привязываем глобальный обработчик с задержкой
    root.after(50, lambda: root.bind_all("<Button-1>", click_outside, add="+"))
    menu.bind("<FocusOut>", lambda e: close_menu())

styles_btn = create_button(right_opts, "🎨 Стили ▾", open_styles_menu, bg=Colors.BG_INPUT)
styles_btn.pack(side="left", padx=(0, 5))
ToolTip(styles_btn, STYLES_HINT)

def open_ai_conductor_window():
    s_check = load_settings()
    if not s_check.get("ai_conductor_warning_dismissed", False):
        def _show_conductor_warning():
            dlg = tk.Toplevel(root)
            dlg.title("AI Conductor")
            dlg.resizable(False, False)
            dlg.configure(bg=Colors.BG_CARD)
            dlg.grab_set()

            tk.Label(dlg, text="⚠ Экспериментальная функция",
                     bg=Colors.BG_CARD, fg="#d29922",
                     font=("Segoe UI", 12, "bold")).pack(padx=24, pady=(20, 8))

            tk.Label(dlg,
                     text="AI Conductor управляет параметрами каждого чанка.\n"
                          "Результат может быть неожиданным — особенно\n"
                          "если референсный голос записан в нейтральном\n"
                          "или неподходящем настроении.",
                     bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
                     font=("Segoe UI", 9), justify="center").pack(padx=24, pady=(0, 16))

            dont_show_var = tk.BooleanVar(value=False)
            tk.Checkbutton(dlg, text="Больше не показывать",
                           variable=dont_show_var,
                           bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
                           selectcolor=Colors.BG_INPUT,
                           activebackground=Colors.BG_CARD,
                           font=("Segoe UI", 9),
                           cursor="hand2").pack(pady=(0, 12))

            def _close_warning():
                if dont_show_var.get():
                    s2 = load_settings()
                    s2["ai_conductor_warning_dismissed"] = True
                    try:
                        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                            json.dump(s2, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        print(f"[Warning] ошибка сохранения: {e}")
                dlg.grab_release()
                dlg.destroy()
                root.after(50, open_ai_conductor_window)

            create_button(dlg, "Понятно", _close_warning,
                          bg=Colors.BG_ACTIVE).pack(pady=(0, 20))
            dlg.protocol("WM_DELETE_WINDOW", _close_warning)

        _show_conductor_warning()
        return
    

    win = tk.Toplevel(root)
    win.title("🤖 AI Conductor")
    win.resizable(False, False)
    win.configure(bg=Colors.BG_CARD)
    win.grab_set()

    # Состояние
    ai_enabled_var = tk.BooleanVar(value=False)
    ai_preset_var = tk.StringVar(value="Все пресеты")
    ai_rewrite_var = tk.BooleanVar(value=False)

    # Загружаем из settings если есть
    s = load_settings()
    ai_enabled_var.set(s.get("ai_conductor_enabled", False))
    ai_preset_var.set(s.get("ai_conductor_preset", "Все пресеты"))
    ai_rewrite_var.set(s.get("ai_rewrite_enabled", False))

    # Заголовок
    tk.Label(win, text="🤖 AI Conductor", bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
             font=("Segoe UI", 13, "bold")).pack(padx=20, pady=(18, 4))
    tk.Label(win,
             text="Анализирует весь текст одним вызовом и назначает\n"
                  "параметры XTTS для каждого чанка индивидуально.\n"
                  "Просодия, смарт-паузы и словарь отключаются — AI управляет ими.",
             bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
             font=("Segoe UI", 9), justify="left").pack(padx=20, pady=(0, 6))

    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x", padx=20, pady=(0, 12))

    # Включить/выключить
    enable_row = tk.Frame(win, bg=Colors.BG_CARD)
    enable_row.pack(fill="x", padx=20, pady=(0, 10))
    def toggle_enabled():
        ai_enabled_var.set(not ai_enabled_var.get())
        toggle_btn.config(
            text="✅ Включён — нажмите чтобы выключить" if ai_enabled_var.get()
                 else "❌ Выключен — нажмите чтобы включить",
            bg=Colors.BG_ACTIVE if ai_enabled_var.get() else Colors.BG_INPUT
        )

    toggle_btn = tk.Button(
        enable_row,
        text="✅ Включён — нажмите чтобы выключить" if ai_enabled_var.get()
             else "❌ Выключен — нажмите чтобы включить",
        command=toggle_enabled,
        bg=Colors.BG_ACTIVE if ai_enabled_var.get() else Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        activebackground=Colors.BG_HOVER,
        activeforeground=Colors.TEXT_MAIN,
        relief="flat", bd=0,
        font=("Segoe UI", 10, "bold"),
        cursor="hand2", padx=12, pady=5
    )
    toggle_btn.pack(side="left")

    # Применять к пресету
    preset_row = tk.Frame(win, bg=Colors.BG_CARD)
    preset_row.pack(fill="x", padx=20, pady=(0, 6))
    tk.Label(preset_row, text="Применять к:", bg=Colors.BG_CARD,
             fg=Colors.TEXT_MAIN, font=("Segoe UI", 9)).pack(side="left", padx=(0, 10))
    
    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x", padx=20, pady=(10, 10))
    
    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x", padx=20, pady=(10, 10))

    # --- Уровень 2: Стиль текста ---
    rewrite_row = tk.Frame(win, bg=Colors.BG_CARD)
    rewrite_row.pack(fill="x", padx=20, pady=(0, 6))

    def toggle_rewrite():
        ai_rewrite_var.set(not ai_rewrite_var.get())
        rewrite_btn.config(
            text="✅ Стиль текста — нажмите чтобы выключить" if ai_rewrite_var.get()
                 else "❌ Стиль текста — нажмите чтобы включить",
            bg=Colors.BG_ACTIVE if ai_rewrite_var.get() else Colors.BG_INPUT
        )
        rewrite_text.config(state="normal" if ai_rewrite_var.get() else "disabled")
        rewrite_negative_text.config(state="normal" if ai_rewrite_var.get() else "disabled")

    rewrite_btn = tk.Button(
        rewrite_row,
        text="✅ Стиль текста — нажмите чтобы выключить" if ai_rewrite_var.get()
             else "❌ Стиль текста — нажмите чтобы включить",
        command=toggle_rewrite,
        bg=Colors.BG_ACTIVE if ai_rewrite_var.get() else Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        activebackground=Colors.BG_HOVER,
        activeforeground=Colors.TEXT_MAIN,
        relief="flat", bd=0,
        font=("Segoe UI", 10, "bold"),
        cursor="hand2", padx=12, pady=5
    )
    rewrite_btn.pack(side="left")

    tk.Label(win,
             text="AI переработает текст под заданный жанр или настроение\n"
                  "перед генерацией. Параметры движка назначаются под новый текст.",
             bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
             font=("Segoe UI", 8), justify="left").pack(fill="x", padx=20, pady=(4, 6))

    tk.Label(win, text="Задание на стиль:",
             bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
             font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=20, pady=(0, 4))

    rewrite_text = tk.Text(
        win, height=4, width=48,
        bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
        insertbackground=Colors.TEXT_MAIN,
        relief="flat", font=("Segoe UI", 9),
        highlightthickness=1, highlightbackground=Colors.BORDER,
        padx=8, pady=6, wrap="word"
    )
    rewrite_text.pack(fill="x", padx=20, pady=(0, 4))

    _saved_rewrite = s.get("ai_rewrite_context", "")
    if _saved_rewrite:
        rewrite_text.insert("1.0", _saved_rewrite)

    if not ai_rewrite_var.get():
        rewrite_text.config(state="disabled")

    tk.Label(win, text="Negative prompt (чего избегать):",
             bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
             font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=20, pady=(6, 4))

    rewrite_negative_text = tk.Text(
        win, height=2, width=48,
        bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
        insertbackground=Colors.TEXT_MAIN,
        relief="flat", font=("Segoe UI", 9),
        highlightthickness=1, highlightbackground=Colors.BORDER,
        padx=8, pady=6, wrap="word"
    )
    rewrite_negative_text.pack(fill="x", padx=20, pady=(0, 4))

    _saved_rewrite_negative = s.get("ai_rewrite_negative", "")
    if _saved_rewrite_negative:
        rewrite_negative_text.insert("1.0", _saved_rewrite_negative)

    if not ai_rewrite_var.get():
        rewrite_negative_text.config(state="disabled")

    preset_options = ["Все пресеты"] + list(quality_params.keys())
    for opt in preset_options:
        tk.Radiobutton(
            preset_row, text=opt, variable=ai_preset_var, value=opt,
            bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
            selectcolor=Colors.BG_INPUT,
            activebackground=Colors.BG_CARD,
            font=("Segoe UI", 9), cursor="hand2"
        ).pack(side="left", padx=(0, 8))

    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x", padx=20, pady=(10, 10))

    # Инфо о провайдере
    try:
        from engine.gpt_client import get_provider, get_model, PROVIDERS
        prov = get_provider()
        model = get_model(prov)
        prov_label = PROVIDERS[prov]["label"]
        info_text = f"Провайдер: {prov_label}\nМодель: {model}"
    except Exception:
        info_text = "Провайдер: не настроен"

    tk.Label(win, text=info_text, bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
             font=("Consolas", 8), justify="left").pack(padx=20, pady=(0, 12), anchor="w")

    # Кнопки
    btn_row = tk.Frame(win, bg=Colors.BG_CARD)
    btn_row.pack(fill="x", padx=20, pady=(0, 18))

    def save_and_close():
        enabled = ai_enabled_var.get()
        preset_target = ai_preset_var.get()

        for preset_name, params in quality_params.items():
            if preset_target == "Все пресеты" or preset_target == preset_name:
                params["ai_conductor_enabled"].set(enabled)
                if "ai_rewrite_enabled" not in params:
                    params["ai_rewrite_enabled"] = tk.BooleanVar()
                params["ai_rewrite_enabled"].set(ai_rewrite_var.get())
                if "ai_rewrite_context" not in params:
                    params["ai_rewrite_context"] = tk.StringVar()
                params["ai_rewrite_context"].set(rewrite_text.get("1.0", "end-1c").strip())
                if "ai_rewrite_negative" not in params:
                    params["ai_rewrite_negative"] = tk.StringVar()
                params["ai_rewrite_negative"].set(rewrite_negative_text.get("1.0", "end-1c").strip())
                

        s2 = load_settings()
        s2["ai_conductor_enabled"] = enabled
        s2["ai_conductor_preset"] = preset_target
        s2["ai_rewrite_enabled"] = ai_rewrite_var.get()
        s2["ai_rewrite_context"] = rewrite_text.get("1.0", "end-1c").strip()
        s2["ai_rewrite_negative"] = rewrite_negative_text.get("1.0", "end-1c").strip()
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(s2, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        ai_btn.config(
            bg=Colors.BG_INPUT,
            fg=Colors.ACCENT if enabled else Colors.TEXT_DIM
        )
        win.destroy()

    create_button(btn_row, "✓ Сохранить", save_and_close, bg=Colors.BG_ACTIVE).pack(side="left", padx=(0, 10))
    create_button(btn_row, "Отмена", win.destroy, bg=Colors.BG_INPUT).pack(side="left")
# Восстанавливаем состояние кнопки из settings
_ai_s = load_settings()
_ai_active = _ai_s.get("ai_conductor_enabled", False)

ai_btn = create_button(right_opts, "🤖 AI",
                       open_ai_conductor_window,
                       bg=Colors.BG_INPUT,
                       fg=Colors.ACCENT if _ai_active else Colors.TEXT_DIM)
ai_btn.pack(side="left", padx=(0, 5))
ToolTip(ai_btn, "AI Conductor — управляет параметрами каждого чанка через AI.")
_ai_pulse_active = {"v": False, "state": False}

def _ai_pulse_tick():
    if not _ai_pulse_active["v"]:
        # Сбросит set_ai_pulse, не трогаем здесь
        return
    _ai_pulse_active["state"] = not _ai_pulse_active["state"]
    ai_btn.config(bg="#1f6feb" if _ai_pulse_active["state"] else Colors.BG_ACTIVE,
                  fg=Colors.TEXT_MAIN)
    root.after(600, _ai_pulse_tick)

def set_ai_pulse(active: bool):
    _ai_pulse_active["v"] = active
    if active:
        _ai_pulse_tick()
    else:
        # Конец работы — вернуть в "включён но простаивает" или "выключен"
        enabled = any(
            params.get("ai_conductor_enabled", tk.BooleanVar()).get()
            for params in quality_params.values()
        )
        ai_btn.config(
            bg=Colors.BG_INPUT,
            fg=Colors.ACCENT if enabled else Colors.TEXT_DIM
        )

# Кнопка "Высокое качество"
def studio_click():
    quality_var.set("Высокое качество")
    save_settings()

def studio_double(e):
    quality_var.set("Высокое качество")
    save_settings()
    open_quality_settings("Высокое качество")

studio_btn = tk.Button(
    right_opts,
    text="⭐ Высокое качество",
    command=studio_click,
    bg=Colors.BG_ACTIVE,
    fg=Colors.TEXT_MAIN,
    activebackground=Colors.BG_HOVER,
    activeforeground=Colors.TEXT_MAIN,
    relief="flat",
    borderwidth=0,
    font=("Segoe UI", 10, "bold"),
    cursor="hand2",
    padx=8, pady=5
)
studio_btn.pack(side="left")
studio_btn.bind("<Double-Button-1>", studio_double)
ToolTip(studio_btn, PRESET_HINT)

def update_quality_buttons(*args):
    q = quality_var.get()
    if q == "Высокое качество":
        studio_btn.config(bg=Colors.BG_ACTIVE)
        styles_btn.config(bg=Colors.BG_INPUT)
        styles_btn.config(text="🎨 Стили ▾")
    else:
        studio_btn.config(bg=Colors.BG_INPUT)
        emoji = {"Нарратив": "📖", "Динамика": "⚡", "Экспрессия": "🎭"}.get(q, "🎨")
        styles_btn.config(bg=Colors.BG_ACTIVE, text=f"{emoji} {q} ▾")

quality_var.trace_add("write", update_quality_buttons)
update_quality_buttons()


# Action buttons — ПОСЛЕ текстового блока
action_frame = tk.Frame(right_panel, bg=Colors.BG_DARK)
action_frame.pack(fill="x", pady=(0, 10))
create_button(action_frame, "🚀 ГЕНЕРИРОВАТЬ", generate,
              bg=Colors.BG_ACTIVE, fg=Colors.TEXT_MAIN, height=2
              ).pack(side="left", fill="x", expand=True, padx=(0, 5))
create_button(action_frame, "⛔ ОТМЕНА", cancel_task,
              bg=Colors.BG_DANGER, fg=Colors.TEXT_MAIN, height=2
              ).pack(side="left", fill="x", expand=True)

# =========================
# STATUS BAR — ВНИЗУ, ПОД КНОПКАМИ
# =========================
status_frame = tk.Frame(right_panel, bg=Colors.BG_CARD)
status_frame.pack(fill="x", side="bottom", pady=(0, 0))

style = ttk.Style()
style.theme_use("clam")
style.configure("Horizontal.TProgressbar",
                background=Colors.PROGRESS_FG, troughcolor=Colors.PROGRESS_BG,
                borderwidth=0, thickness=8)
ttk.Progressbar(
    status_frame, orient="horizontal", mode="determinate", maximum=100,
    variable=progress_value, style="Horizontal.TProgressbar"
).pack(fill="x", padx=10, pady=(10, 5))

tk.Label(status_frame, textvariable=status_var, anchor="w", bg=Colors.BG_CARD,
         fg=Colors.TEXT_MAIN, font=("Segoe UI", 10)).pack(fill="x", padx=10, pady=(0, 10))

# =========================
# LAUNCH
# =========================
apply_settings(load_settings())
refresh_voice_list()
queue_autorefresh()

root.update_idletasks()
sw = root.winfo_screenwidth()
sh = root.winfo_screenheight()
x = max(0, (sw - 1000) // 2)
y = max(0, (sh - 820) // 2)
root.geometry(f"1160x820+{x}+{y}")

root.after(150, start_preload_thread)
root.after(150, start_preload_thread)

def _auto_check_update():
    from engine.updater import check_update
    result = check_update()
    if result.get("error"):
        return
    if result.get("available"):
        def _notify():
            import tkinter.messagebox as mb
            if mb.askyesno(
                "🆕 Доступно обновление",
                f"Версия {result['remote']} доступна.\nСейчас у вас {result['local']}.\n\nОбновить?"
            ):
                check_and_update()
        root.after(0, _notify)

threading.Thread(target=_auto_check_update, daemon=True).start()
root.mainloop()