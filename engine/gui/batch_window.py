# -*- coding: utf-8 -*-
"""
engine/gui/batch_window.py — окно «Пакетная обработка» в стиле Аудио/История

Редизайн 2026-07-09 (единый стиль):
- скруглённые карточки файлов, таблетка с кнопками сверху, счетчик
- крупные шрифты как в audio/history (scaled_font_size +3)
- круглые кнопки _round_btn (CompatCTkButton)
- фикс иконки в таскбаре Windows (перо -> норм)
- CTkScrollableFrame вместо Canvas
- статус трекер сохранен
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox
import json

from engine.task_models import Task
from engine.paths import BASE_DIR

try:
    from engine.paths import ICON_PATH
except ImportError:
    ICON_PATH = os.path.join(str(BASE_DIR), "icon.ico")

from engine.gui.colors import Colors, scaled_font_size, scaled_size
from engine.gui.tooltip import ToolTip
from engine.gui.widgets import CompatCTkFrame, CompatCTkButton, CompatCTkLabel
import customtkinter as ctk

# DI
_root = None
_colors = None
_output_dir = None
_task_manager = None
_ref_var = None
_quality_var = None
_quality_params = None
_word_replacer_enabled_var = None
_lang_split_enabled_var = None
_use_gpt_var = None
_lang_var = None
_normalize_text = None
_clean_path = None


def init(
    root,
    colors,
    output_dir,
    task_manager,
    ref_var,
    quality_var,
    quality_params,
    word_replacer_enabled_var,
    lang_split_enabled_var,
    use_gpt_var,
    lang_var,
    normalize_text_fn,
    clean_path_fn,
):
    global _root, _colors, _output_dir, _task_manager, _ref_var, _quality_var
    global _quality_params, _word_replacer_enabled_var, _lang_split_enabled_var
    global _use_gpt_var, _lang_var, _normalize_text, _clean_path
    _root = root
    _colors = colors
    _output_dir = output_dir
    _task_manager = task_manager
    _ref_var = ref_var
    _quality_var = quality_var
    _quality_params = quality_params
    _word_replacer_enabled_var = word_replacer_enabled_var
    _lang_split_enabled_var = lang_split_enabled_var
    _use_gpt_var = use_gpt_var
    _lang_var = lang_var
    _normalize_text = normalize_text_fn
    _clean_path = clean_path_fn


def _apply_window_icon(win: tk.Toplevel):
    try:
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XTTSStudio.App")
        except Exception:
            pass
    except Exception:
        pass
    candidates = []
    if ICON_PATH:
        candidates.append(ICON_PATH)
    candidates.extend(
        [
            os.path.join(str(BASE_DIR), "icon.ico"),
            os.path.join(str(BASE_DIR), "icon.png"),
            os.path.join(str(BASE_DIR), "images", "icon.ico"),
        ]
    )
    ico_file = None
    png_file = None
    for p in candidates:
        if p and os.path.isfile(p):
            if p.lower().endswith(".ico") and not ico_file:
                ico_file = p
            elif p.lower().endswith(".png") and not png_file:
                png_file = p
    if ico_file:
        try:
            win.iconbitmap(default=ico_file)
        except Exception:
            try:
                win.iconbitmap(ico_file)
            except Exception:
                pass
        try:
            win.after(100, lambda: win.iconbitmap(default=ico_file))
            win.after(400, lambda: win.iconbitmap(default=ico_file))
        except Exception:
            pass
    try:
        photo = None
        if png_file:
            try:
                photo = tk.PhotoImage(file=png_file)
            except Exception:
                photo = None
        if photo is None and ico_file:
            try:
                from PIL import Image, ImageTk

                im = Image.open(ico_file).resize((32, 32), Image.LANCZOS)
                photo = ImageTk.PhotoImage(im)
            except Exception:
                photo = None
        if photo:
            win.iconphoto(True, photo)
            win._icon_photo_ref = photo
    except Exception:
        pass


def open_batch_window():
    colors = _colors
    win = tk.Toplevel(_root)
    win.title("📦 Пакетная обработка")
    win.geometry("860x620")
    win.minsize(700, 480)
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    _apply_window_icon(win)
    win.grab_set()

    _files = []
    _status_vars = []
    _card_widgets = {}
    _empty_state = {"w": None}

    def _round_btn(parent, text, cmd, diameter=36, primary=False, danger=False):
        bg = Colors.BG_ACTIVE if primary else Colors.BG_INPUT
        hover = "#2ea043" if primary else (Colors.BG_DANGER if danger else Colors.BG_HOVER)
        sd = scaled_size(diameter, min_size=diameter)
        return CompatCTkButton(
            parent,
            text=text,
            command=cmd,
            width=sd,
            height=sd,
            corner_radius=sd // 2,
            fg_color=bg,
            text_color=Colors.TEXT_MAIN,
            hover_color=hover,
            border_width=0,
            font=("Segoe UI", scaled_font_size(17 if primary else 15)),
        )

    def _unique_wav(base: str) -> str:
        candidate = os.path.join(_output_dir, f"{base}.wav")
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(_output_dir, f"{base} ({counter}).wav")
            counter += 1
        return candidate

    def _maybe_show_empty():
        if list_frame.winfo_children():
            if _empty_state["w"]:
                try:
                    _empty_state["w"].destroy()
                except Exception:
                    pass
                _empty_state["w"] = None
            return
        if _empty_state["w"] is None:
            lbl = CompatCTkLabel(
                list_frame,
                text="Выберите папку или файлы с текстами",
                fg_color=Colors.BG_DARK,
                text_color=Colors.TEXT_DIM,
                font=("Segoe UI", scaled_font_size(13)),
            )
            lbl.pack(pady=60)
            _empty_state["w"] = lbl

    def _make_row(idx, src, dst, status_var):
        card = CompatCTkFrame(
            list_frame,
            fg_color=Colors.BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=Colors.BORDER,
        )
        card.pack(fill="x", padx=4, pady=5)
        _card_widgets[src] = card

        # badge
        badge = CompatCTkFrame(
            card, fg_color=Colors.BG_INPUT, corner_radius=20, width=44, height=44
        )
        badge.pack(side="left", padx=(14, 10), pady=12)
        badge.pack_propagate(False)
        CompatCTkLabel(
            badge,
            text="📄",
            fg_color=Colors.BG_INPUT,
            text_color=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(18)),
        ).pack(expand=True)

        info = tk.Frame(card, bg=Colors.BG_CARD)
        info.pack(side="left", fill="both", expand=True, pady=10)
        CompatCTkLabel(
            info,
            text=os.path.basename(src),
            fg_color=Colors.BG_CARD,
            text_color=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(13), "bold"),
            anchor="w",
        ).pack(fill="x")
        CompatCTkLabel(
            info,
            text=os.path.dirname(src)[-48:],
            fg_color=Colors.BG_CARD,
            text_color=Colors.TEXT_DIM,
            font=("Segoe UI", scaled_font_size(10)),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        status_lbl = CompatCTkLabel(
            card,
            textvariable=status_var,
            fg_color=Colors.BG_CARD,
            text_color=Colors.TEXT_DIM,
            font=("Consolas", scaled_font_size(11)),
        )
        status_lbl.pack(side="right", padx=12)

    def _refresh_rows():
        for w in list_frame.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        _status_vars.clear()
        _card_widgets.clear()
        if not _files:
            count_lbl.configure(text="0 файлов")
            btn_run.configure(state="disabled")
            _maybe_show_empty()
            return
        for i, (src, dst) in enumerate(_files):
            sv = tk.StringVar(value="⏳ Ожидает")
            _status_vars.append(sv)
            _make_row(i, src, dst, sv)
        count_lbl.configure(text=f"{len(_files)} файлов")
        btn_run.configure(state="normal")
        _maybe_show_empty()

    def _pick_folder():
        folder = filedialog.askdirectory(title="Выбрать папку с TXT-файлами")
        if not folder:
            return
        txts = sorted(f for f in os.listdir(folder) if f.lower().endswith(".txt"))
        if not txts:
            messagebox.showinfo("📂 Пусто", "В папке нет .txt файлов", parent=win)
            return
        _files.clear()
        os.makedirs(_output_dir, exist_ok=True)
        for fname in txts:
            src = os.path.join(folder, fname)
            base = os.path.splitext(fname)[0]
            _files.append((src, _unique_wav(base)))
        _refresh_rows()

    def _pick_files():
        paths = filedialog.askopenfilenames(title="Выбрать TXT-файлы", filetypes=[("TXT", "*.txt")])
        if not paths:
            return
        _files.clear()
        os.makedirs(_output_dir, exist_ok=True)
        for p in sorted(paths):
            base = os.path.splitext(os.path.basename(p))[0]
            _files.append((p, _unique_wav(base)))
        _refresh_rows()

    def _start_status_tracker():
        def _tick():
            if not win.winfo_exists():
                return
            queue = _task_manager.get_queue()
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
                        elif t.status in (
                            "running",
                            "generate",
                            "merge",
                            "chunking",
                            "normalize",
                            "reference",
                        ):
                            win.after(0, lambda s=sv, p=t.progress: s.set(f"▶ {p}%"))
                        elif t.status == "queued":
                            win.after(0, lambda s=sv: s.set("🕒 В очереди"))
                        break
            try:
                win.after(400, _tick)
            except Exception:
                pass

        _tick()

    def _run_batch():
        ref = _clean_path(_ref_var.get().strip())
        if not ref or not os.path.isfile(ref):
            messagebox.showerror("❌ Ошибка", "Сначала выберите голос-референс", parent=win)
            return
        if not _files:
            return
        quality_name = _quality_var.get()
        if quality_name not in _quality_params:
            quality_name = "Высокое качество"
        params = _quality_params[quality_name]
        btn_run.configure(state="disabled")
        btn_folder.configure(state="disabled")
        btn_files.configure(state="disabled")
        for i, (src, dst) in enumerate(_files):
            try:
                with open(src, "r", encoding="utf-8") as f:
                    raw = f.read()
            except Exception as e:
                if i < len(_status_vars):
                    _status_vars[i].set("❌ Ошибка")
                print(f"[Batch] Cannot read {src}: {e}")
                continue
            text = _normalize_text(raw)
            if not text.strip():
                if i < len(_status_vars):
                    _status_vars[i].set("⚠ Пустой")
                continue
            if i < len(_status_vars):
                _status_vars[i].set("🕒 В очереди")
            task = Task(
                text=text,
                raw_text=raw.strip(),
                voice=ref,
                speed=params["speed"].get(),
                language=_lang_var.get(),
                quality=quality_name,
                quality_params={
                    **{k: v.get() for k, v in params.items()},
                    "word_replacer_enabled": _word_replacer_enabled_var.get(),
                    "lang_split_enabled": _lang_split_enabled_var.get(),
                    "use_gpt": _use_gpt_var.get(),
                    "ai_conductor_enabled": params.get(
                        "ai_conductor_enabled", tk.BooleanVar()
                    ).get(),
                    "output_path_override": dst,
                },
            )
            _task_manager.add_task(task)
        win.after(
            500, lambda: (btn_folder.configure(state="normal"), btn_files.configure(state="normal"))
        )
        _start_status_tracker()

    # HEADER - pill
    header = tk.Frame(win, bg=Colors.BG_DARK, pady=12)
    header.pack(fill="x", padx=16)

    pill = CompatCTkFrame(
        header,
        fg_color=Colors.BG_CARD,
        corner_radius=18,
        border_width=1,
        border_color=Colors.BORDER,
    )
    pill.pack(side="left")
    row = tk.Frame(pill, bg=Colors.BG_CARD)
    row.pack(padx=6, pady=6)

    btn_folder = _round_btn(row, "📂", _pick_folder, diameter=36)
    btn_folder.pack(side="left", padx=3)
    ToolTip(btn_folder, "Выбрать папку с TXT")

    btn_files = _round_btn(row, "📄", _pick_files, diameter=36)
    btn_files.pack(side="left", padx=3)
    ToolTip(btn_files, "Выбрать отдельные TXT файлы")

    count_pill = CompatCTkFrame(
        header,
        fg_color=Colors.BG_CARD,
        corner_radius=14,
        border_width=1,
        border_color=Colors.BORDER,
    )
    count_pill.pack(side="right")
    count_lbl = CompatCTkLabel(
        count_pill,
        text="0 файлов",
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(12)),
    )
    count_lbl.pack(padx=16, pady=9)

    voice_pill = CompatCTkFrame(
        header,
        fg_color=Colors.BG_CARD,
        corner_radius=14,
        border_width=1,
        border_color=Colors.BORDER,
    )
    voice_pill.pack(side="right", padx=(0, 10))
    _batch_voice_var = tk.StringVar()

    def _update_batch_voice(*_):
        p = _ref_var.get().strip()
        if not p:
            _batch_voice_var.set("голос не выбран")
            return
        folder = os.path.basename(os.path.dirname(p))
        name = os.path.splitext(os.path.basename(p))[0]
        _batch_voice_var.set(folder if name.lower() == "normalized" else name)

    _ref_var.trace_add("write", _update_batch_voice)
    _update_batch_voice()
    tk.Frame(voice_pill, bg=Colors.BG_CARD, width=6).pack(side="left")
    CompatCTkLabel(
        voice_pill,
        text="Голос:",
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(11)),
    ).pack(side="left")
    CompatCTkLabel(
        voice_pill,
        textvariable=_batch_voice_var,
        fg_color=Colors.BG_CARD,
        text_color=Colors.ACCENT,
        font=("Segoe UI", scaled_font_size(11), "bold"),
        width=120,
    ).pack(side="left", padx=(4, 12), pady=9)

    # LIST
    list_frame = ctk.CTkScrollableFrame(win, fg_color=Colors.BG_DARK, corner_radius=12)
    list_frame.pack(fill="both", expand=True, padx=12, pady=(4, 6))

    # BOTTOM
    outer_wrap = tk.Frame(win, bg=Colors.BG_DARK)
    outer_wrap.pack(fill="x", side="bottom")
    bottom_card = CompatCTkFrame(
        outer_wrap,
        fg_color=Colors.BG_CARD,
        corner_radius=20,
        border_width=1,
        border_color=Colors.BORDER,
    )
    bottom_card.pack(fill="x", padx=14, pady=(6, 14))
    bottom_row = tk.Frame(bottom_card, bg=Colors.BG_CARD)
    bottom_row.pack(fill="x", padx=18, pady=14)

    CompatCTkLabel(
        bottom_row,
        text="Пресет:",
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(11)),
    ).pack(side="left")
    CompatCTkLabel(
        bottom_row,
        textvariable=_quality_var,
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(12), "bold"),
    ).pack(side="left", padx=(6, 12))

    btn_run = _round_btn(bottom_row, "🚀 Запустить пакет", _run_batch, diameter=44, primary=True)
    # делаем шире для текста
    try:
        btn_run.configure(width=scaled_size(220, min_size=200), corner_radius=22)
    except Exception:
        pass
    btn_run.pack(side="right")

    def _on_close():
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_close)
    _refresh_rows()
    try:
        win.after(150, lambda: _apply_window_icon(win))
    except Exception:
        pass
