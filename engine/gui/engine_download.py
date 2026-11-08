"""engine/gui/engine_download.py — диалог предложения и загрузки движка XTTS v2.

Фоновая предзагрузка модели (engine/gui/generation.py::_preload_model)
проверяет наличие движка; если его нет — открывается этот диалог:

  1. «Скачать (~1,9 ГБ)» → окно прогресса: файл N/M, общий прогресс в МБ/%/
     скорость, кнопка «Отмена» (докачка сохраняется в *.part);
  2. «Позже» → диалог закрывается, приложение остаётся в состоянии
     «Движок не установлен» (генерация не запустится до установки).

После успешной загрузки вызывается on_installed() — предзагрузка
перезапускается и модель подхватывается автоматически.
"""

import contextlib
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from i18n import t

from engine import xtts_engine


def _fmt_mb(n: float) -> str:
    return f"{n / (1024 ** 2):.1f} MB"


def _fmt_speed(bps: float) -> str:
    if bps <= 0:
        return "—"
    if bps >= 1024 * 1024:
        return f"{bps / (1024 ** 2):.1f} МБ/с"
    return f"{bps / 1024:.0f} КБ/с"


def offer_engine_download(parent=None, on_installed=None, on_closed=None):
    """Показать диалог «Скачать движок XTTS?».

    parent — корневое окно (Tk/Toplevel). on_installed() — колбэк после
    успешной установки. on_closed() — колбэк на любом выходе из диалога.
    """
    root = parent
    if root is None:
        try:
            root = tk._default_root
        except Exception:
            root = None

    if root is None:
        # Нет GUI (например, headless) — просто сообщаем в консоль/лог.
        print("[Engine] Движок XTTS отсутствует, а GUI недоступен для предложения загрузки.")
        if callable(on_closed):
            with contextlib.suppress(Exception):
                on_closed()
        return

    win = tk.Toplevel(root)
    win.title(t("engine_offer_title"))
    win.geometry("620x340")
    win.resizable(False, False)
    win.configure(bg="#2b2b2b")
    with contextlib.suppress(Exception):
        win.transient(root)
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x, y = (sw - 620) // 2, (sh - 340) // 2
        win.geometry(f"620x340+{x}+{y}")
        win.grab_set()

    tk.Label(
        win,
        text="⬇️ " + t("engine_offer_headline"),
        fg="#ffffff",
        bg="#2b2b2b",
        font=("Segoe UI", 15, "bold"),
    ).pack(padx=24, pady=(22, 8), anchor="w")

    tk.Label(
        win,
        text=t("engine_offer_msg"),
        fg="#dddddd",
        bg="#2b2b2b",
        font=("Segoe UI", 9),
        justify="left",
        wraplength=570,
    ).pack(padx=24, anchor="w")

    tk.Label(
        win,
        text=t("engine_offer_cpml"),
        fg="#8f8f8f",
        bg="#2b2b2b",
        font=("Segoe UI", 8),
        justify="left",
        wraplength=570,
    ).pack(padx=24, pady=(10, 0), anchor="w")

    buttons = tk.Frame(win, bg="#2b2b2b")
    buttons.pack(padx=24, pady=(18, 0), anchor="e")

    state = {"closed": False}

    def _close():
        if state["closed"]:
            return
        state["closed"] = True
        with contextlib.suppress(Exception):
            win.grab_release()
        with contextlib.suppress(Exception):
            win.destroy()
        if callable(on_closed):
            with contextlib.suppress(Exception):
                on_closed()

    def _download():
        with contextlib.suppress(Exception):
            win.grab_release()
        win.destroy()
        state["closed"] = True  # окно вопроса закрыто; дальше — прогресс
        _run_download(root, on_installed=on_installed, on_closed=on_closed)

    tk.Button(
        buttons,
        text=t("engine_offer_download"),
        command=_download,
        bg="#2e5b82",
        fg="#ffffff",
        activebackground="#3a719c",
        activeforeground="#ffffff",
        font=("Segoe UI", 10, "bold"),
        padx=18,
        pady=8,
        borderwidth=0,
        cursor="hand2",
    ).pack(side="left", padx=(0, 10))

    tk.Button(
        buttons,
        text=t("engine_offer_later"),
        command=_close,
        bg="#3d3d3d",
        fg="#dddddd",
        activebackground="#4a4a4a",
        activeforeground="#ffffff",
        font=("Segoe UI", 10),
        padx=18,
        pady=8,
        borderwidth=0,
        cursor="hand2",
    ).pack(side="left")

    win.protocol("WM_DELETE_WINDOW", _close)


def _run_download(root, on_installed=None, on_closed=None):
    """Окно прогресса загрузки движка."""
    win = tk.Toplevel(root)
    win.title(t("engine_dl_title"))
    win.geometry("620x240")
    win.resizable(False, False)
    win.configure(bg="#2b2b2b")
    with contextlib.suppress(Exception):
        win.transient(root)
        win.grab_set()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x, y = (sw - 620) // 2, (sh - 240) // 2
        win.geometry(f"620x240+{x}+{y}")

    tk.Label(
        win,
        text=t("engine_dl_title"),
        fg="#ffffff",
        bg="#2b2b2b",
        font=("Segoe UI", 13, "bold"),
    ).pack(padx=24, pady=(18, 4), anchor="w")

    file_var = tk.StringVar(value=t("engine_dl_prepare"))
    tk.Label(
        win,
        textvariable=file_var,
        fg="#aaaaaa",
        bg="#2b2b2b",
        font=("Consolas", 8),
        anchor="w",
        justify="left",
    ).pack(padx=24, anchor="w", fill="x")

    style = ttk.Style(win)
    with contextlib.suppress(Exception):
        style.theme_use("clam")
    style.configure("TProgressbar", thickness=14, troughcolor="#333333", background="#2e5b82")

    bar = ttk.Progressbar(
        win,
        orient="horizontal",
        length=570,
        mode="determinate",
        maximum=100.0,
        style="TProgressbar",
    )
    bar.pack(padx=24, pady=(12, 4))

    overall_var = tk.StringVar(
        value=t("engine_dl_overall", _fmt_mb(0), _fmt_mb(xtts_engine.ENGINE_TOTAL_BYTES), 0.0, "—")
    )
    tk.Label(
        win,
        textvariable=overall_var,
        fg="#dddddd",
        bg="#2b2b2b",
        font=("Segoe UI", 9),
    ).pack(padx=24, anchor="w")

    cancel_flag = {"cancelled": False}

    cancel_btn = tk.Button(
        win,
        text=t("engine_dl_cancel"),
        bg="#3d3d3d",
        fg="#ffffff",
        font=("Segoe UI", 10),
        padx=18,
        pady=6,
        borderwidth=0,
        cursor="hand2",
    )
    cancel_btn.pack(padx=24, pady=(14, 0), anchor="e")

    def _request_cancel():
        cancel_flag["cancelled"] = True
        cancel_btn.config(state="disabled", text=t("engine_dl_cancel_requested"))

    cancel_btn.config(command=_request_cancel)

    # Скользящая оценка скорости: (timestamp, overall_done)
    samples = [(time.monotonic(), 0)]

    def _progress(evt: dict):
        overall_done = evt.get("overall_done", 0)
        overall_total = evt.get("overall_total") or xtts_engine.ENGINE_TOTAL_BYTES
        now = time.monotonic()
        samples.append((now, overall_done))
        while len(samples) > 1 and now - samples[0][0] > 2.0:
            samples.pop(0)
        if len(samples) >= 2:
            dt = samples[-1][0] - samples[0][0]
            speed = (samples[-1][1] - samples[0][1]) / dt if dt > 0 else 0.0
        else:
            speed = 0.0
        pct = (overall_done / overall_total * 100.0) if overall_total else 0.0
        stage = evt.get("stage")
        if stage == "verify":
            file_text = t("engine_dl_verify", evt.get("file", ""))
        else:
            file_text = t(
                "engine_dl_file",
                evt.get("file_index", 0),
                evt.get("file_count", 0),
                evt.get("file", ""),
            )
        overall_text = t(
            "engine_dl_overall",
            _fmt_mb(overall_done),
            _fmt_mb(overall_total),
            pct,
            _fmt_speed(speed),
        )

        def _apply():
            with contextlib.suppress(Exception):
                file_var.set(file_text)
                overall_var.set(overall_text)
                bar["value"] = pct

        with contextlib.suppress(Exception):
            win.after(0, _apply)

    def _close_quietly():
        with contextlib.suppress(Exception):
            win.grab_release()
        with contextlib.suppress(Exception):
            win.destroy()

    def _finish(result: dict):
        _close_quietly()
        if result.get("ok"):
            messagebox.showinfo(t("engine_dl_done_title"), t("engine_dl_done_msg"), parent=root)
            if callable(on_installed):
                with contextlib.suppress(Exception):
                    on_installed()
        elif result.get("cancelled"):
            messagebox.showinfo(t("engine_dl_cancel_title"), t("engine_dl_cancel_msg"), parent=root)
        else:
            messagebox.showerror(
                t("engine_dl_fail_title"),
                f"{result.get('error', t('dlg_error_title'))}",
                parent=root,
            )
        if callable(on_closed):
            with contextlib.suppress(Exception):
                on_closed()

    def _work():
        try:
            result = xtts_engine.download_engine(progress_cb=_progress, cancelled_cb=cancel_flag)
        except Exception as e:  # страховка: download_engine не должен кидать наружу
            result = {"ok": False, "error": str(e), "cancelled": False}
        win.after(0, lambda: _finish(result))

    threading.Thread(target=_work, daemon=True).start()
