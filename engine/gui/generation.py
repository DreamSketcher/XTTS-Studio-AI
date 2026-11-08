# -*- coding: utf-8 -*-
"""engine/gui/generation.py — GUI-обвязка генерации: запуск/отмена задач,
callback обновления интерфейса, предзагрузка модели
(перенесено из gui.py: on_task_update, _on_task_done, _on_task_error,
_preload_model, start_preload_thread, cancel_task, generate
+ состояние current_task / current_text_snapshot / model_ready)."""
import os
import re
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Optional

import pygame

import webbrowser

from i18n import t

from engine.task_models import Task
from engine.text_tools import normalize_text
from engine.logging_utils import write_log
from engine.history_store import _save_history
from engine.cpml_consent import (
    CPML_URL,
    cpml_consent_path,
    set_coqui_tos_agreed,
)
from engine.gui import textbox
from engine.gui.statusbar import set_status, set_stage, set_progress
from engine.gui.textbox import (
    lock_textbox,
    unlock_textbox,
    clear_chunk_highlight,
    hide_placeholder,
    _highlight_chunk,
    _highlight_chunk_by_text,
)

# Внедряются из main_window: root, PYGAME_OK, ref_var, lang_var, quality_var,
# word_replacer_enabled, lang_split_enabled, use_gpt, _textbox_updated,
# clean_path, task_manager, quality_params, text_box, update_gen_btn,
# set_ai_pulse, update_queue_view, save_settings, refresh_voice_list
root = None
_engine_offer_active = False  # True, пока открыто окно предложения/загрузки движка
PYGAME_OK = False
ref_var = None
lang_var = None
quality_var = None
word_replacer_enabled = None
lang_split_enabled = None
use_gpt = None
_textbox_updated = None
clean_path = None
task_manager = None
quality_params = {}
text_box = None
# Функции из других GUI-модулей (внедряются через init из main_window)
save_settings = None
set_ai_pulse = None
update_queue_view = None
refresh_voice_list = None
update_gen_btn = None

# Состояние (перенесено из секции STATE gui.py)
current_task: Optional[Task] = None
current_text_snapshot = ""
model_ready = False

# ── Парсинг прогресса pip для _ensure_torch_ready() ──
# "Collecting torch==2.11.0" / "Downloading torch-2.11.0+cpu-....whl (200.8 MB)"
_torch_collecting_re = re.compile(r"^Collecting\s+([A-Za-z0-9_.\-]+)")
_torch_downloading_re = re.compile(r"^Downloading\s+([A-Za-z0-9_.\-]+)")
_torch_installing_re = re.compile(r"^Installing collected packages")
# Обычный прогресс-бар pip внутри одной строки: "45%" либо "90.5/200.8 MB"
_torch_percent_re = re.compile(r"(\d{1,3})%")
_torch_ratio_re = re.compile(r"([\d.]+)\s*/\s*([\d.]+)\s*MB")


def init(**deps):
    """Внедрение зависимостей из engine.gui.main_window (имена совпадают с
    именами глобальных переменных исходного gui.py)."""
    globals().update(deps)


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

        def _do_chunk_highlight(s=chunk_start, e=chunk_end, t_text=chunk_raw):
            try:
                if s is not None and e is not None and int(e) > int(s):
                    _highlight_chunk(int(s), int(e))
                else:
                    _highlight_chunk_by_text(t_text)
            except Exception:
                _highlight_chunk_by_text(t_text)

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

            def _apply_normalized_text(nt=normalized):
                try:
                    text_box.config(state="normal")
                    text_box.delete("1.0", "end")
                    text_box.insert("1.0", nt)
                    lock_textbox()
                    # Text mutation is complete at this point; rendering can be
                    # deferred naturally. A synchronous geometry flush only
                    # stalls the UI and is not required by the worker handshake.
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
        set_status(t("status_queue_wait"))
        set_stage("QUEUED")
        root.after(0, lambda: update_gen_btn(True))
    elif task.status in ("running", "generate", "reference", "normalize", "chunking", "merge"):
        set_status(t("status_running", task.progress))
        set_stage("RUNNING")
        root.after(0, lambda: update_gen_btn(True))
    elif task.status == "done":
        root.after(0, lambda: set_ai_pulse(False))
        set_stage("DONE")
        unlock_textbox()
        if task.stats:
            t_sec = task.stats.get("time_sec", 0)
            mins, secs = divmod(t_sec, 60)
            time_str = t("time_format_m_s", mins, secs) if mins else t("time_format_s", secs)
            set_status(
                t(
                    "status_done_detail",
                    time_str,
                    task.stats.get("chunks", "?"),
                    task.stats.get("voice", "?"),
                )
            )
        else:
            set_status(t("status_done"))
        root.after(0, lambda: _on_task_done(task))
        root.after(0, lambda: update_gen_btn(False))
    elif task.status == "error":
        set_stage("ERROR")
        unlock_textbox()
        set_status(t("status_error"))
        root.after(0, lambda: set_ai_pulse(False))
        root.after(0, lambda: _on_task_error(task))
        root.after(0, lambda: update_gen_btn(False))
    elif task.status == "cancelled":
        if current_task and current_task.id == task.id:
            current_task = None
        clear_chunk_highlight()
        unlock_textbox()
        root.after(0, lambda: _restore_raw_text(task))
        set_stage("IDLE")
        set_status(t("status_cancelled"))
        set_progress(0)
        root.after(0, lambda: set_ai_pulse(False))
        root.after(0, lambda: update_gen_btn(False))
    else:
        set_stage(task.status.upper())
        set_status(f"{task.status}... {task.progress}%")


def _restore_raw_text(task: Task):
    """
    После генерации (done/error/cancelled) возвращаем в text_box оригинальный
    текст пользователя (task.raw_text), а не финальный normalize-текст,
    который использовался только для подсветки чанков во время генерации.
    """
    try:
        raw = getattr(task, "raw_text", None)
        if not raw:
            return
        text_box.config(state="normal")
        text_box.delete("1.0", "end")
        text_box.insert("1.0", raw)
    except Exception as e:
        print(f"[TextBox restore error]: {e}")


def _on_task_done(task: Task):
    global current_task
    if current_task and current_task.id == task.id:
        current_task = None
    clear_chunk_highlight()
    unlock_textbox()
    _restore_raw_text(task)
    _save_history(task)
    refresh_voice_list()
    messagebox.showinfo(t("dlg_done_title"), t("dlg_done_msg", task.output_path))


# ── CPML (Coqui Public Model License) ──────────────────────────────
# Генерация падает с CoquiTosNotAgreedError, если пользователь ещё не
# подтвердил лицензию. Раньше ошибка показывалась голым traceback'ом, и
# в основном окне не было никакого контроля принятия лицензии (issue #4).
# Теперь показываем тот же экран согласия, что и при старте.
_COQUI_TOS_MARKERS = (
    "CoquiTosNotAgreedError",
    "COQUI_TOS_AGREED",
    "set_coqui_tos_agreed",
    "cpml_consent",
    "Coqui Public Model License",
)


def _is_coqui_tos_error(error_text) -> bool:
    if not error_text:
        return False
    return any(marker in str(error_text) for marker in _COQUI_TOS_MARKERS)


def _show_cpml_consent_on_error():
    """Экран согласия с CPML поверх главного окна (при ошибке генерации)."""
    try:
        win = tk.Toplevel(root)
        win.title("📜 Лицензионное соглашение XTTS v2")
        win.geometry("560x380")
        win.resizable(False, False)
        win.configure(bg="#1e1e1e")
        win.transient(root)
        win.grab_set()

        def _accept():
            try:
                set_coqui_tos_agreed("generation-error-dialog")
                win.destroy()
                messagebox.showinfo(
                    "📜 Coqui Public Model License (CPML)",
                    "Согласие с CPML сохранено. Нажмите «Generate» ещё раз — "
                    "генерация должна запуститься.",
                    parent=root,
                )
            except Exception as save_err:
                # Пользователь согласился — даём согласие хотя бы на сеанс
                # и делаем сбой записи видимым.
                os.environ["COQUI_TOS_AGREED"] = "1"
                win.destroy()
                messagebox.showwarning(
                    "📜 Coqui Public Model License (CPML)",
                    "Вы согласились с CPML, но сохранить отметку не удалось:\n\n"
                    f"{save_err}\n\n"
                    f"Файл согласия: {cpml_consent_path()}\n\n"
                    "Проверьте, что папка приложения доступна на запись. "
                    "Пока что согласие действует только в этом сеансе.",
                    parent=root,
                )

        def _open_link(_event=None):
            webbrowser.open(CPML_URL)

        tk.Label(
            win,
            text="📜 Coqui Public Model License (CPML)",
            font=("Segoe UI", 13, "bold"),
            bg="#1e1e1e",
            fg="#ffffff",
        ).pack(pady=(18, 6))

        body = (
            "Генерация остановлена: вы ещё не подтвердили согласие с лицензией "
            "Coqui Public Model License (CPML), по которой распространяется "
            "голосовой движок XTTS v2.\n\n"
            "Это отдельное требование лицензии, а не ошибка приложения. "
            "Полный текст лицензии доступен по ссылке ниже. Нажимая "
            "«Согласен, продолжить», вы подтверждаете, что ознакомились "
            "с условиями CPML и принимаете их."
        )
        tk.Label(
            win,
            text=body,
            font=("Segoe UI", 10),
            bg="#1e1e1e",
            fg="#cfcfcf",
            justify="left",
            wraplength=500,
        ).pack(padx=24, pady=(0, 10))

        link = tk.Label(
            win,
            text=CPML_URL,
            font=("Segoe UI", 10, "underline"),
            bg="#1e1e1e",
            fg="#4da3ff",
            cursor="hand2",
        )
        link.pack(pady=(0, 20))
        link.bind("<Button-1>", _open_link)

        btn_frame = tk.Frame(win, bg="#1e1e1e")
        btn_frame.pack(pady=(0, 18))

        tk.Button(
            btn_frame,
            text="Согласен, продолжить",
            font=("Segoe UI", 10, "bold"),
            bg="#2e7d32",
            fg="#ffffff",
            activebackground="#388e3c",
            relief="flat",
            padx=16,
            pady=6,
            command=_accept,
        ).pack(side="left", padx=8)

        tk.Button(
            btn_frame,
            text="Закрыть",
            font=("Segoe UI", 10),
            bg="#3a3a3a",
            fg="#ffffff",
            activebackground="#4a4a4a",
            relief="flat",
            padx=16,
            pady=6,
            command=win.destroy,
        ).pack(side="left", padx=8)
    except Exception as e:
        # Даже сам экран согласия не смог открыться — показываем хотя бы
        # текстовое сообщение со ссылкой на лицензию.
        print(f"[CPML] Не удалось показать экран согласия: {e}")
        messagebox.showerror(
            "📜 Coqui Public Model License (CPML)",
            "Генерация остановлена: не подтверждено согласие с CPML.\n\n"
            f"Откройте {CPML_URL}, ознакомьтесь с лицензией и запустите "
            "генерацию снова — приложение покажет экран согласия.",
            parent=root,
        )


def _on_task_error(task: Task):
    global current_task
    if current_task and current_task.id == task.id:
        current_task = None
    clear_chunk_highlight()
    unlock_textbox()
    _restore_raw_text(task)
    write_log(task.error or "Unknown error")
    if _is_coqui_tos_error(task.error):
        _show_cpml_consent_on_error()
        return
    if _engine_missing():
        # Понятная подсказка + повторное предложение вместо сырой ошибки TTS
        try:
            messagebox.showinfo(t("engine_dlg_title"), t("engine_missing_hint"), parent=root)
        except Exception:
            pass
        _request_engine_offer()
        return
    messagebox.showerror(t("dlg_error_title"), task.error or "Неизвестная ошибка")


def _request_engine_offer():
    """Открывает диалог «Скачать движок XTTS?» (один раз за раз)."""
    global _engine_offer_active
    if _engine_offer_active:
        return
    _engine_offer_active = True

    def _open():
        try:
            from engine.gui import engine_download

            engine_download.offer_engine_download(
                parent=root,
                on_installed=_on_engine_installed,
                on_closed=_on_engine_offer_closed,
            )
        except Exception as e:
            globals()["_engine_offer_active"] = False
            print(f"[Preload] Диалог загрузки движка недоступен: {e}")

    try:
        if root is not None:
            root.after(0, _open)
        else:
            _open()
    except Exception:
        _open()


def _on_engine_installed():
    global _engine_offer_active
    _engine_offer_active = False
    print("[Preload] Движок XTTS установлен — перезапускаю предзагрузку модели.")
    try:
        threading.Thread(target=_preload_model, daemon=True).start()
    except Exception as e:
        print(f"[Preload] Не удалось перезапустить предзагрузку: {e}")


def _on_engine_offer_closed():
    global _engine_offer_active
    _engine_offer_active = False


def _engine_missing() -> bool:
    """True, если файлы движка XTTS отсутствуют/неполные (дёшево: только stat)."""
    try:
        from engine import xtts_engine

        return not xtts_engine.engine_ready()
    except Exception:
        return False  # проверка недоступна — не блокируем привычный путь


def _preload_model():
    global model_ready
    try:
        import os
        import sys

        is_updates_mode = False

        # 1. Проверяем переменную окружения (процесс-глобальный и самый надежный способ!)
        if os.environ.get("OPEN_UPDATES_ON_STARTUP") == "1":
            is_updates_mode = True

        # 2. Проверяем __main__ (так как gui.py запускается напрямую и попадает в __main__)
        if "__main__" in sys.modules:
            main_mod = sys.modules["__main__"]
            if getattr(main_mod, "OPEN_UPDATES_ON_STARTUP", False):
                is_updates_mode = True

        # 3. Проверяем gui
        if "gui" in sys.modules:
            gui_mod = sys.modules["gui"]
            if getattr(gui_mod, "OPEN_UPDATES_ON_STARTUP", False):
                is_updates_mode = True

        if is_updates_mode:
            print(
                "[Preload] Отключение предзагрузки модели (запущен режим обновления/восстановления PyTorch)."
            )
            model_ready = False
            set_stage("IDLE")
            set_status(t("status_waiting"))
            return
    except Exception as e:
        print(f"[Preload] Ошибка проверки режима обновления: {e}")

    if _engine_missing():
        # Движок — обязательный компонент: предлагаем скачать (официальный
        # источник, проверка SHA-256 после загрузки). Окно — немодальное по
        # отношению к главному GUI-потоку (открывается через root.after).
        model_ready = False
        set_stage("IDLE")
        set_status(t("status_engine_missing"))
        write_log(
            "[Preload] Файлы движка XTTS (models/xtts_v2) отсутствуют/неполные — "
            "показываю предложение скачать."
        )
        _request_engine_offer()
        return

    try:
        from engine.tts_runner import get_tts

        set_stage("STARTUP")
        set_status(t("status_init"))
        get_tts()
        model_ready = True
        set_stage("READY")
        set_status(t("status_ready"))
    except Exception as e:
        print(f"[Preload] Модель будет загружена при генерации. ({e})")
        model_ready = False
        set_stage("IDLE")
        if _is_coqui_tos_error(e) or _is_coqui_tos_error(repr(e)):
            # Пользователь увидит экран согласия при первой генерации
            # (см. _on_task_error); здесь — явная подсказка в строке статуса
            # вместо молчаливого «Waiting».
            set_status("⚠️ Требуется согласие с CPML — откроется при первой генерации")
        else:
            set_status(t("status_waiting"))


def start_preload_thread():
    threading.Thread(target=_preload_model, daemon=True).start()


def cancel_task():
    global current_task
    if current_task is None:
        return
    task_manager.cancel_task(current_task.id)
    clear_chunk_highlight()
    unlock_textbox()
    set_status(t("status_cancelling"))
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
        messagebox.showerror("❌", t("dlg_error_empty"))
        return
    if not ref or not os.path.isfile(ref):
        messagebox.showerror("❌", t("dlg_error_no_ref"))
        return
    current_text_snapshot = text
    # _highlight_pos живёт в engine.gui.textbox (та же переменная, что и раньше)
    textbox._highlight_pos = 0
    try:
        _textbox_updated.clear()
    except Exception:
        pass
    clear_chunk_highlight()
    lock_textbox()
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
        },
    )
    set_status(t("status_queued"))
    set_stage("QUEUED")
    set_progress(0)
    task_manager.add_task(current_task)
    root.after(0, update_queue_view)
    save_settings()
