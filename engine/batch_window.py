"""
engine/batch_window.py — окно "Пакетная обработка" для XTTS Studio

Массовая генерация из папки или списка TXT-файлов: выбор источника,
список файлов со статусами, запуск через общую очередь task_manager.

Архитектура:
    init(root, colors, output_dir, task_manager, ref_var, quality_var,
         quality_params, word_replacer_enabled_var, lang_split_enabled_var,
         use_gpt_var, lang_var, normalize_text_fn, clean_path_fn)

Окно не импортирует ничего из gui.py напрямую — все зависимости
приходят через init().
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox

from engine.task_models import Task


# ─────────────────────────────────────────────────────────────────────────────
# Dependency injection
# ─────────────────────────────────────────────────────────────────────────────

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


def init(root, colors, output_dir, task_manager, ref_var, quality_var,
          quality_params, word_replacer_enabled_var, lang_split_enabled_var,
          use_gpt_var, lang_var, normalize_text_fn, clean_path_fn):
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


# ─────────────────────────────────────────────────────────────────────────────
# Window
# ─────────────────────────────────────────────────────────────────────────────

def open_batch_window():
    """Открывает окно пакетной обработки TXT-файлов."""
    colors = _colors
    win = tk.Toplevel(_root)
    win.title("📦 Пакетная обработка")
    win.geometry("660x520")
    win.minsize(560, 400)
    win.resizable(True, True)
    win.configure(bg=colors.BG_DARK)
    win.grab_set()

    _files = []        # list of (src_txt, dst_wav)
    _status_vars = []  # list of tk.StringVar

    def _unique_wav(base: str) -> str:
        candidate = os.path.join(_output_dir, f"{base}.wav")
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(_output_dir, f"{base} ({counter}).wav")
            counter += 1
        return candidate

    def _refresh_rows():
        for w in scroll_inner.winfo_children():
            w.destroy()
        _status_vars.clear()
        if not _files:
            tk.Label(scroll_inner, text="Выберите папку или файлы ",
                     bg=colors.BG_DARK, fg=colors.TEXT_DIM,
                     font=("Segoe UI", 11)).pack(pady=60)
            count_lbl.config(text="0 файлов")
            btn_run.config(state="disabled")
            return
        for i, (src, dst) in enumerate(_files):
            sv = tk.StringVar(value="⏳ Ожидает")
            _status_vars.append(sv)
            row = tk.Frame(scroll_inner, bg=colors.BG_CARD,
                           highlightthickness=1,
                           highlightbackground=colors.BORDER)
            row.pack(fill="x", padx=8, pady=2)
            tk.Label(row, text=f"{i+1}.", width=3,
                     bg=colors.BG_CARD, fg=colors.TEXT_DIM,
                     font=("Consolas", 9)).pack(side="left", padx=(6, 2), pady=6)
            tk.Label(row, text=os.path.basename(src), anchor="w",
                     bg=colors.BG_CARD, fg=colors.TEXT_MAIN,
                     font=("Segoe UI", 9)).pack(side="left", fill="x",
                                                 expand=True, pady=6)
            tk.Label(row, textvariable=sv, width=14, anchor="e",
                     bg=colors.BG_CARD, fg=colors.TEXT_DIM,
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
        os.makedirs(_output_dir, exist_ok=True)
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
                        elif t.status in ("running", "generate", "merge",
                                          "chunking", "normalize", "reference"):
                            win.after(0, lambda s=sv, p=t.progress: s.set(f" ▶{p}%"))
                        elif t.status == "queued":
                            win.after(0, lambda s=sv: s.set("▶  В очереди"))
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
            text = _normalize_text(raw)
            if not text.strip():
                if i < len(_status_vars):
                    _status_vars[i].set("⚠ Пустой")
                continue
            if i < len(_status_vars):
                _status_vars[i].set("▶  В очереди")
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
                        "ai_conductor_enabled", tk.BooleanVar()).get(),
                }
            )
            _task_manager.add_task(task)
        win.after(500, lambda: (
            btn_folder.config(state="normal"),
            btn_files.config(state="normal"),
        ))
        _start_status_tracker()

    # ── LAYOUT ───────────────────────────────────────────────────────────────
    toolbar = tk.Frame(win, bg=colors.BG_CARD, pady=6)
    toolbar.pack(fill="x")

    def _tb_btn(text, cmd):
        b = tk.Button(toolbar, text=text, command=cmd,
                      bg=colors.BG_INPUT, fg=colors.TEXT_MAIN,
                      activebackground=colors.BG_HOVER,
                      activeforeground=colors.TEXT_MAIN,
                      relief="flat", bd=0, font=("Segoe UI", 9),
                      padx=10, pady=4, cursor="hand2")
        b.bind("<Enter>", lambda e: b.config(bg=colors.BG_HOVER))
        b.bind("<Leave>", lambda e: b.config(bg=colors.BG_INPUT))
        return b

    btn_folder = _tb_btn("📂 Выбрать папку", _pick_folder)
    btn_folder.pack(side="left", padx=(10, 4))
    btn_files = _tb_btn("📄 Выбрать файлы", _pick_files)
    btn_files.pack(side="left", padx=(0, 4))
    count_lbl = tk.Label(toolbar, text="0 файлов",
                         bg=colors.BG_CARD, fg=colors.TEXT_DIM,
                         font=("Segoe UI", 9))
    count_lbl.pack(side="left", padx=8)

    # текущий голос — справа в тулбаре
    _batch_voice_var = tk.StringVar()

    def _update_batch_voice(*_):
        p = _ref_var.get().strip()
        if not p:
            _batch_voice_var.set("")
            return
        folder = os.path.basename(os.path.dirname(p))
        name = os.path.splitext(os.path.basename(p))[0]
        _batch_voice_var.set(folder if name.lower() == "normalized" else name)

    _ref_var.trace_add("write", _update_batch_voice)
    _update_batch_voice()

    tk.Label(toolbar, text="Голос:", bg=colors.BG_CARD, fg=colors.TEXT_DIM,
             font=("Segoe UI", 8)).pack(side="right", padx=(0, 2))
    tk.Label(toolbar, textvariable=_batch_voice_var, bg=colors.BG_CARD,
             fg=colors.ACCENT, font=("Segoe UI", 8),
             width=18, anchor="e").pack(side="right", padx=(0, 10))

    tk.Frame(win, bg=colors.BORDER, height=1).pack(fill="x")

    # список файлов (прокручиваемый)
    list_outer = tk.Frame(win, bg=colors.BG_DARK)
    list_outer.pack(fill="both", expand=True)
    canvas = tk.Canvas(list_outer, bg=colors.BG_DARK, bd=0, highlightthickness=0)
    scrollbar = tk.Scrollbar(list_outer, orient="vertical",
                             command=canvas.yview,
                             bg=colors.BG_INPUT, troughcolor=colors.BG_DARK)
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    scroll_inner = tk.Frame(canvas, bg=colors.BG_DARK)
    cw = canvas.create_window((0, 0), window=scroll_inner, anchor="nw")
    scroll_inner.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))

    def _on_mousewheel(e):
        try:
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        except Exception:
            pass

    win.bind("<MouseWheel>", _on_mousewheel)
    tk.Frame(win, bg=colors.BORDER, height=1).pack(fill="x")

    # нижняя панель
    bottom = tk.Frame(win, bg=colors.BG_CARD, pady=8)
    bottom.pack(fill="x", side="bottom")
    tk.Label(bottom, text="Пресет:", bg=colors.BG_CARD, fg=colors.TEXT_DIM,
             font=("Segoe UI", 9)).pack(side="left", padx=(12, 4))
    tk.Label(bottom, textvariable=_quality_var, bg=colors.BG_CARD,
             fg=colors.TEXT_MAIN,
             font=("Segoe UI", 9, "bold")).pack(side="left")
    btn_run = tk.Button(
        bottom, text="🚀 Запустить пакет",
        command=_run_batch,
        bg=colors.BG_ACTIVE, fg=colors.TEXT_MAIN,
        activebackground="#2ea043", activeforeground=colors.TEXT_MAIN,
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