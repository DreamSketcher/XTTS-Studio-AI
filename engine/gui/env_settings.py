# -*- coding: utf-8 -*-
"""engine/gui/env_settings.py — управление окружением, CUDA-ускорением, диагностикой, библиотеками и обновлениями (GUI-обвязка)
(переименовано из updates.py для устранения путаницы, так как файл теперь охватывает полные системные настройки)."""
import os
import re
import json
import threading
import subprocess
import customtkinter as ctk

from engine.gui.ui_thread_bridge import UIThreadBridge
from engine.gui.progress_throttle import ProgressThrottle
import tkinter as tk
import tkinter.messagebox as mb

from i18n import t

from engine import env_setup
from engine.gui.colors import scaled_font_size, scaled_size
from engine.gui.statusbar import set_status, set_progress, show_cancel_button, hide_cancel_button
from engine.gui.widgets import CompatCTkButton

# Внедряется из main_window: root
root = None

# ── ГЛОБАЛЬНЫЙ ЛОК УСТАНОВКИ (предотвращает одновременные pip install) ──
# Используется всеми точками входа: startup recovery, settings buttons, rvc_setup, torch_setup
_INSTALL_LOCK = threading.RLock()
_INSTALL_STATE = {"running": False, "type": None, "cancelled": False}


def _acquire_install_lock(install_type: str) -> bool:
    """Пытается захватить лок установки.
    Возвращает True если лок получен, False если другая установка уже идёт.
    """
    global _INSTALL_STATE
    acquired = _INSTALL_LOCK.acquire(blocking=False)
    if acquired:
        _INSTALL_STATE = {"running": True, "type": install_type, "cancelled": False}
        return True
    return False


def _release_install_lock():
    """Освобождает лок установки."""
    global _INSTALL_STATE
    _INSTALL_STATE = {"running": False, "type": None, "cancelled": False}
    _INSTALL_LOCK.release()


def _is_install_running() -> bool:
    """Проверяет, идёт ли какая-то установка."""
    return _INSTALL_STATE.get("running", False)


def _get_current_install_type() -> str:
    """Возвращает тип текущей установки или пустую строку."""
    return _INSTALL_STATE.get("type", "")


def _set_install_cancelled():
    """Помечает текущую установку как отменённую."""
    _INSTALL_STATE["cancelled"] = True


# ── ЕДИНЫЙ СПИСОК ПАКЕТОВ ДЛЯ ВОССТАНОВЛЕНИЯ (PACKAGE_PIP_SPEC) ──
# Используется в gui.py (startup recovery) и env_settings.py (recovery flow)
# Единый источник истины — исключает расхождения при добавлении пакетов.
PACKAGE_PIP_SPEC = {
    "torch": "torch==2.11.0 torchaudio==2.11.0 torchvision==0.26.0",
    "torchaudio": "torchaudio==2.11.0",
    "torchvision": "torchvision==0.26.0",
    "tts": "coqui-tts",
    "numpy": "numpy==1.26.4",
    "pygame": "pygame",
    "customtkinter": "customtkinter",
    "num2words": "num2words",
    "cryptography": "cryptography==49.0.0",
    "llama_cpp": "llama-cpp-python",
    "soundfile": "soundfile",
    "rvc_python": "rvc-python",
    "av": "av==10.0.0",  # PyAV, совместимый с torchvision 0.26.0
}

# ── ПОТОКОБЕЗОПАСНЫЙ КЭШ ДИАГНОСТИКИ (thread-safe cache) ──
# Использует тот же лок установки для синхронизации доступа к файлу кэша.
_DIAG_CACHE_LOCK = threading.RLock()


# Флаг для защиты clear_diagnostics_cache — не очищать, если идёт восстановление/установка
def _can_clear_diagnostics_cache() -> bool:
    """Возвращает True если можно безопасно очистить кэш диагностики."""
    return not _is_install_running()


# Флаг отмены текущего обновления — тот же формат, что использует
# engine/local_llm_client.py и engine/updater.py (dict с ключом "cancelled").
_update_cancelled_flag = {"cancelled": False}

# Регэкспы парсинга прогресса pip для install_torch
_torch_collecting_re = re.compile(r"^Collecting\s+([A-Za-z0-9_.\-]+)")
_torch_downloading_re = re.compile(r"^Downloading\s+([A-Za-z0-9_.\-]+)")
_torch_installing_re = re.compile(r"^Installing collected packages")
_torch_percent_re = re.compile(r"(\d{1,3})%")
_torch_ratio_re = re.compile(r"([\d.]+)\s*/\s*([\d.]+)\s*MB")


def init(**deps):
    """Внедрение зависимостей из engine.gui.main_window (имена совпадают с
    именами глобальных переменных исходного gui.py)."""
    globals().update(deps)


def _cancel_current_update():
    """Вызывается по нажатию кнопки "Отмена" в статус-баре."""
    _update_cancelled_flag["cancelled"] = True


def _do_update(result):
    """Скачивает и устанавливает обновление."""
    from engine.updater import apply_update, restart
    import tkinter.messagebox as mb

    _update_cancelled_flag["cancelled"] = False
    set_status(t("status_update_download"))
    show_cancel_button(_cancel_current_update)

    def _apply():
        ok = apply_update(
            result["files"],
            sha256_map=result.get("sha256", {}),
            removed_files=result.get("removed_files", []),
            progress_callback=lambda i, t_val: set_progress(int(i / t_val * 100)),
            cancelled_flag=_update_cancelled_flag,
            commit_sha=result.get("commit_sha"),
        )
        hide_cancel_button()
        was_cancelled = _update_cancelled_flag["cancelled"]
        if ok:
            changelog = result.get("changelog", "").strip()
            msg = t("update_installed", result["remote"])
            if changelog:
                msg += t("update_changelog", changelog)
            msg += t("update_restart")

            def _notify_and_restart():
                mb.showinfo(t("update_done_title"), msg)
                restart()

            root.after(0, _notify_and_restart)
        elif was_cancelled:
            # Скачанные файлы уже удалены внутри apply_update (staging очищен),
            # рабочие файлы не тронуты — обновление отменено чисто.
            root.after(0, lambda: mb.showinfo(t("update_cancelled_title"), t("update_cancelled")))
            set_status(t("status_waiting"))
        else:
            # apply_update ничего не тронул на диске, если проверка SHA256
            # или скачивание не прошли — рабочие файлы остались как были.
            root.after(0, lambda: mb.showwarning(t("update_partial_title"), t("update_partial")))
            set_status(t("status_waiting"))

    threading.Thread(target=_apply, daemon=True).start()


def check_and_update(actual_check=False):
    """Ручная проверка обновлений (по кнопке).
    По умолчанию (при клике из внешнего UI без параметров) открывает окно системных настроек.
    При вызове с actual_check=True выполняет реальную проверку обновлений.
    """
    if not actual_check:
        open_env_settings_window()
        return

    from engine.updater import check_update, REPO
    import tkinter.messagebox as mb

    set_status(t("status_update_check"))

    def _run():
        result = check_update()
        if result.get("error"):
            root.after(0, lambda: mb.showerror(t("update_error_title"), result["error"]))
            set_status(t("status_waiting"))
            return
        if result.get("needs_manual_reinstall"):

            def notify_manual():
                mb.showwarning(
                    t("update_manual_required_title"),
                    t(
                        "update_manual_required",
                        result.get("min_app_version", "?"),
                        result["local"],
                        f"https://github.com/{REPO}/releases",
                    ),
                )
                set_status(t("status_waiting"))

            root.after(0, notify_manual)
            return
        if not result["available"]:
            root.after(
                0,
                lambda: mb.showinfo(t("update_no_title"), t("update_no_updates", result["local"])),
            )
            set_status(t("status_waiting"))
            return

        def ask():
            changelog = result.get("changelog", "").strip()
            text = t("update_available", result["remote"], result["local"])
            if changelog:
                text += t("update_whats_new", changelog)
            text += t("update_confirm")
            confirmed = mb.askyesno(t("update_title"), text)
            if confirmed:
                _do_update(result)
            else:
                set_status(t("status_waiting"))

        root.after(0, ask)

    threading.Thread(target=_run, daemon=True).start()


def _auto_check_update():
    from engine.settings_store import load_settings

    settings = load_settings()
    if not settings.get("auto_check_updates", True):
        return

    from engine.updater import check_update

    result = check_update()
    if result.get("error"):
        return
    if result.get("needs_manual_reinstall"):
        # Не дёргаем пользователя всплывающим окном при каждом автозапуске —
        # ручная переустановка не срочная, покажем только по кнопке "Проверить обновления".
        print(
            f"[Updater] Требуется ручная переустановка: локальная версия {result['local']} "
            f"старее минимально поддерживаемой {result.get('min_app_version')}"
        )
        return
    if result.get("available"):

        def _notify():
            import tkinter.messagebox as mb

            changelog = result.get("changelog", "").strip()
            text = t("update_available", result["remote"], result["local"])
            if changelog:
                text += t("update_whats_new", changelog)
            text += t("update_confirm")
            if mb.askyesno(t("update_title"), text):
                _do_update(result)

        root.after(0, _notify)


class EnvSettingsWindow(ctk.CTkToplevel):
    """Окно системных настроек: интеграция CUDA, RVC, диагностика окружения и обновление ПО."""

    def _post_ui(self, callback, *args, **kwargs):
        return self._ui_bridge.post(callback, *args, **kwargs)

    def _post_progress_text(self, text, *, force=False):
        self._log_sequence += 1
        if not force and not self._log_throttle.should_emit(self._log_sequence):
            return

        def apply(value=str(text)):
            try:
                if self.winfo_exists() and self.lbl_progress_status.winfo_exists():
                    self.lbl_progress_status.configure(text=value)
            except Exception:
                pass

        self._post_ui(apply)

    def _start_worker(self, target):
        """Start a producer whose UI results are delivered by the window bridge."""
        self._ui_bridge.begin()

        def wrapped():
            try:
                target()
            finally:
                self._ui_bridge.producer_done()

        thread = threading.Thread(target=wrapped, daemon=True)
        thread.start()
        return thread

    def destroy(self):
        try:
            self._ui_bridge.destroy()
        except Exception:
            pass
        super().destroy()

    def __init__(self, master=None):
        super().__init__(master)
        self._ui_bridge = UIThreadBridge(self, poll_ms=16, max_batch=64)
        self._log_throttle = ProgressThrottle(max_hz=8)
        self._log_sequence = 0
        self.title(t("win_update_settings_title"))
        self.geometry("600x820")  # Задали оптимальную высоту под раскрывающийся список зависимостей
        self.resizable(False, True)  # Разрешили ресайз по вертикали при раскрытии списка

        # Размещение окна по центру относительно главного окна
        if master:
            self.transient(master)
            try:
                master.update_idletasks()
                master_x = master.winfo_rootx()
                master_y = master.winfo_rooty()
                master_w = master.winfo_width()
                master_h = master.winfo_height()
                x = master_x + (master_w - 600) // 2
                y = master_y + (master_h - 820) // 2
                self.geometry(f"600x820+{x}+{y}")
            except Exception:
                pass

        self.grab_set()
        self.focus()

        # Применяем тему заголовка окна (Windows) для интеграции с Конструктором Тем
        try:
            from engine.gui import theme

            theme.set_dark_titlebar(self)
        except Exception:
            pass

        # Стилизация на основе темы приложения
        try:
            from engine.gui.colors import Colors

            bg_card = Colors.BG_CARD or "#2b2b2b"
            bg_input = Colors.BG_INPUT or "#333333"
            bg_hover = Colors.BG_HOVER or "#444444"
            text_main = Colors.TEXT_MAIN or "#ffffff"
            text_dim = Colors.TEXT_DIM or "#aaaaaa"
            border_color = Colors.BORDER or "#3f3f3f"
            ai_accent = Colors.AI_ACCENT or "#1f6aa5"
            bg_active = Colors.BG_ACTIVE or "#2e7d32"
            btn_color = Colors.ACCENT or "#1f6aa5"
        except Exception:
            bg_card = "#2b2b2b"
            bg_input = "#333333"
            bg_hover = "#444444"
            text_main = "#ffffff"
            text_dim = "#aaaaaa"
            border_color = "#3f3f3f"
            ai_accent = "#1f6aa5"
            bg_active = "#2e7d32"
            btn_color = "#1f6aa5"

        self.configure(fg_color=bg_card)

        # ── Functions needed by footer (must be defined before footer creation) ──
        def run_stop():
            self.install_was_stopped = True
            _set_install_cancelled()  # Помечаем установку как отменённую для проверки в потоках
            env_setup.cancel_install_torch()
            self.btn_stop.configure(state="disabled")

        def run_resume():
            checkpoint = env_setup.load_torch_checkpoint()
            variant = checkpoint.get("meta", {}).get("variant") or "cpu"
            start_install(variant, resume=True)

        # ── Фиксированный футер (всегда виден внизу) ──
        footer_wrap = tk.Frame(self, bg=bg_card)
        footer_wrap.pack(fill="x", side="bottom")
        footer_card = ctk.CTkFrame(
            footer_wrap,
            fg_color=bg_input,
            border_width=1,
            border_color=border_color,
            corner_radius=10,
        )
        footer_card.pack(fill="x", padx=8, pady=6)

        # Статус-строка футера
        self.lbl_progress_status = ctk.CTkLabel(
            footer_card,
            text="",
            text_color=text_dim,
            font=ctk.CTkFont(size=11),
            justify="left",
            anchor="w",
        )
        self.lbl_progress_status.pack(fill="x", padx=15, pady=(8, 2))

        # Прогресс-бар футера
        self.progress_bar = ctk.CTkProgressBar(footer_card, height=10)
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 4))
        self.progress_bar.set(0.0)

        # Кнопки Отмена / Продолжить (поочередный показ) во футере
        self.active_controls_frame = ctk.CTkFrame(footer_card, fg_color="transparent")

        self.btn_stop = ctk.CTkButton(
            self.active_controls_frame,
            text=t("btn_cancel_install"),
            command=run_stop,
            fg_color="#b22222",
            hover_color=bg_hover,
            text_color=text_main,
        )
        self.btn_stop.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.btn_resume = ctk.CTkButton(
            self.active_controls_frame,
            text=t("btn_resume_install"),
            command=run_resume,
            fg_color="#2e8b57",
            hover_color=bg_hover,
            text_color=text_main,
        )
        self.btn_resume.pack(side="left", expand=True, fill="x", padx=(5, 0))

        self.install_state = {"current_pkg": "torch"}

        # Scrollable — заполняет пространство НАД футером
        main_scroll = ctk.CTkScrollableFrame(self, fg_color=bg_card, corner_radius=0)
        main_scroll.pack(fill="both", expand=True)

        outer_frame = ctk.CTkFrame(main_scroll, fg_color=bg_card, corner_radius=0)
        outer_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # --- СЕКЦИЯ 1: Обновления ---
        sec_updates = ctk.CTkFrame(
            outer_frame, fg_color=bg_input, border_width=1, border_color=border_color
        )
        sec_updates.pack(fill="x", pady=(0, 15), padx=5)

        lbl_updates_title = ctk.CTkLabel(
            sec_updates,
            text=t("section_updates"),
            font=ctk.CTkFont(weight="bold", size=14),
            text_color=text_main,
        )
        lbl_updates_title.pack(anchor="w", padx=15, pady=(10, 5))

        from engine.settings_store import load_settings, save_settings

        self.settings = load_settings()
        self.chk_var = tk.BooleanVar(value=self.settings.get("auto_check_updates", True))

        def on_chk_toggle():
            self.settings["auto_check_updates"] = self.chk_var.get()
            save_settings(self.settings)

        self.chk_auto = ctk.CTkCheckBox(
            sec_updates,
            text=t("chk_auto_check"),
            variable=self.chk_var,
            command=on_chk_toggle,
            text_color=text_main,
        )
        self.chk_auto.pack(anchor="w", padx=15, pady=5)

        def run_manual_check():
            self.destroy()  # Закрываем настройки перед началом проверки, чтобы не мешать всплывающим окнам
            check_and_update(actual_check=True)

        self.btn_check = ctk.CTkButton(
            sec_updates,
            text=t("btn_check_now"),
            command=run_manual_check,
            fg_color=btn_color,
            hover_color=bg_hover,
            text_color=text_main,
        )
        self.btn_check.pack(anchor="w", padx=15, pady=(5, 15))

        # --- СЕКЦИЯ 2: Ускорение (CPU/GPU) ---
        sec_accel = ctk.CTkFrame(
            outer_frame, fg_color=bg_input, border_width=1, border_color=border_color
        )
        sec_accel.pack(fill="x", pady=(0, 15), padx=5)

        lbl_accel_title = ctk.CTkLabel(
            sec_accel,
            text=t("section_accel"),
            font=ctk.CTkFont(weight="bold", size=14),
            text_color=text_main,
        )
        lbl_accel_title.pack(anchor="w", padx=15, pady=(10, 5))

        # Обнаружение GPU
        gpu_info = env_setup.detect_gpu()
        gpu_vendor = gpu_info.get("vendor", "unknown").upper()
        gpu_name = gpu_info.get("name", "не определено")
        gpu_text = f"{gpu_vendor}: {gpu_name}"
        if gpu_info.get("cuda_version"):
            gpu_text += f" (CUDA: {gpu_info['cuda_version']})"

        lbl_gpu = ctk.CTkLabel(
            sec_accel,
            text=f"{t('lbl_detected_gpu')} {gpu_text}",
            text_color=text_dim,
            font=ctk.CTkFont(size=12),
        )
        lbl_gpu.pack(anchor="w", padx=15, pady=2)

        self.lbl_torch_var = ctk.CTkLabel(
            sec_accel, text="", text_color=text_dim, font=ctk.CTkFont(size=12)
        )
        self.lbl_torch_var.pack(anchor="w", padx=15, pady=(2, 10))

        def update_variant_label():
            try:
                if not self.winfo_exists():
                    return
                variant = env_setup.get_installed_torch_variant()
                if variant is None:
                    lbl_text = t("torch_variant_not_defined")
                else:
                    lbl_text = {"cu128": "NVIDIA CUDA 12.8 (GPU)", "cpu": "CPU"}.get(
                        variant, variant
                    )
                if self.lbl_torch_var.winfo_exists():
                    self.lbl_torch_var.configure(text=f"{t('lbl_current_torch')} {lbl_text}")
            except Exception:
                pass

        update_variant_label()

        # Выбор предпочитаемого режима (CPU/GPU) с сохранением в settings.json
        lbl_pref = ctk.CTkLabel(
            sec_accel,
            text=t("lbl_device_preference"),
            text_color=text_main,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        lbl_pref.pack(anchor="w", padx=15, pady=(5, 2))

        pref_val = self.settings.get("torch_device_preference", "gpu")

        # Защитная блокировка: если GPU-ускорение физически не доступно в установленной сборке,
        # предпочитаемый режим принудительно переключается на CPU.
        torch_stat = env_setup.torch_status()
        if pref_val == "gpu" and not torch_stat.get("cuda_available"):
            pref_val = "cpu"
            self.settings["torch_device_preference"] = "cpu"
            save_settings(self.settings)

        def on_pref_changed(value):
            if value == t("opt_pref_gpu"):
                status = env_setup.torch_status()
                # Разрешаем включать GPU только если библиотеки CUDA успешно импортированы и работают!
                if not status.get("cuda_available"):
                    gpu = env_setup.detect_gpu()
                    if gpu.get("vendor") != "nvidia":
                        mb.showerror(
                            t("update_error_title"), t("msg_cuda_requires_nvidia"), parent=self
                        )
                    else:
                        mb.showwarning(
                            t("update_title"),
                            "Для включения GPU-ускорения (CUDA) необходимо сначала установить совместимые библиотеки CUDA.\n\nПожалуйста, нажмите кнопку «Проверить и установить GPU-ускорение (CUDA)» ниже, чтобы запустить установку.",
                            parent=self,
                        )
                    # Возвращаем переключатель в положение CPU
                    self.seg_pref.set(t("opt_pref_cpu"))
                    return

            pref = "gpu" if value == t("opt_pref_gpu") else "cpu"
            self.settings["torch_device_preference"] = pref
            save_settings(self.settings)
            print(f"[Torch Setup UI] Сохранен предпочитаемый режим: {pref}")

        self.seg_pref = ctk.CTkSegmentedButton(
            sec_accel, values=[t("opt_pref_gpu"), t("opt_pref_cpu")], command=on_pref_changed
        )
        self.seg_pref.pack(anchor="w", padx=15, pady=(2, 10), fill="x")
        self.seg_pref.set(t("opt_pref_gpu") if pref_val == "gpu" else t("opt_pref_cpu"))

        # Кнопки установки stacked вертикально во избежание обрезки текста!
        self.btn_gpu = ctk.CTkButton(
            sec_accel,
            text=t("btn_install_gpu"),
            command=lambda: start_install("cu128"),
            fg_color=bg_active,
            hover_color=bg_hover,
            text_color=text_main,
        )
        self.btn_gpu.pack(anchor="w", fill="x", padx=15, pady=(0, 5))

        # Блокируем кнопку установки CUDA на аппаратном уровне, если в системе нет карты NVIDIA
        if gpu_info.get("vendor") == "nvidia":
            self.btn_gpu.configure(state="normal")
        else:
            self.btn_gpu.configure(state="disabled")

        self.btn_cpu = ctk.CTkButton(
            sec_accel,
            text=t("btn_install_cpu"),
            command=lambda: start_install("cpu"),
            fg_color=bg_hover,
            hover_color=bg_card,
            text_color=text_main,
        )
        self.btn_cpu.pack(anchor="w", fill="x", padx=15, pady=(0, 10))

        # --- СЕКЦИЯ 3: Установленные зависимости (РЕФАКТОРИНГ RVC КАРТОЧКИ) ---
        sec_deps = ctk.CTkFrame(
            outer_frame, fg_color=bg_input, border_width=1, border_color=border_color
        )
        sec_deps.pack(fill="x", pady=(0, 15), padx=5)

        lbl_deps_title = ctk.CTkLabel(
            sec_deps,
            text=t("section_dependencies"),
            font=ctk.CTkFont(weight="bold", size=14),
            text_color=text_main,
        )
        lbl_deps_title.pack(anchor="w", padx=15, pady=(10, 5))

        self.lbl_deps_status = ctk.CTkLabel(
            sec_deps,
            text="🔍 Статус загружается...",
            text_color=text_dim,
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="w",
            wraplength=540,
        )
        self.lbl_deps_status.pack(anchor="w", fill="x", padx=15, pady=2)

        # Списки соответствий для красивого вывода и targeted pip install
        self.dependency_names = {
            "numpy": "NumPy (вычисления)",
            "torch": "PyTorch (нейросети)",
            "torchaudio": "TorchAudio (аудиодвижок)",
            "torchvision": "TorchVision (модели зрения)",
            "tts": "Coqui TTS (синтез речи)",
            "soundfile": "SoundFile (запись аудио)",
            "pygame": "Pygame (воспроизведение)",
            "customtkinter": "CustomTkinter (виджеты)",
            "num2words": "num2words (нормализация)",
            "cryptography": "Cryptography (подпись обновлений)",
            "llama_cpp": "Llama-cpp (локальные чаты)",
            "rvc_python": "RVC-python (клон-фильтр)",
        }

        self.dependency_pip = {
            "numpy": "numpy==1.26.4",
            "torch": "torch==2.11.0 torchaudio==2.11.0 torchvision==0.26.0",
            "torchaudio": "torchaudio==2.11.0",
            "torchvision": "torchvision==0.26.0",
            "tts": "coqui-tts",
            "soundfile": "soundfile",
            "pygame": "pygame",
            "customtkinter": "customtkinter",
            "num2words": "num2words",
            "cryptography": "cryptography==49.0.0",
            "llama_cpp": "llama-cpp-python",
            "rvc_python": "rvc-python",
        }

        self.row_widgets = {}
        self.details_visible = False

        # Раскрывающийся контейнер
        self.details_frame = ctk.CTkFrame(sec_deps, fg_color="transparent")
        # По умолчанию скрыт (не упакован)

        def start_targeted_install(pkg_key, pip_spec):
            confirmed = mb.askyesno(
                t("update_title"),
                f"Вы действительно хотите исправить и переустановить пакет '{pkg_key}' ({pip_spec})?\n\nОперация займет около минуты.",
                parent=self,
            )
            if not confirmed:
                return

            # Пытаемся захватить лок установки
            if not _acquire_install_lock(f"targeted:{pkg_key}"):
                mb.showwarning(
                    t("update_title"),
                    f"Уже выполняется другая установка ({_get_current_install_type()}).\nДождитесь её завершения или отмените.",
                    parent=self,
                )
                return

            def _install_thread():
                self._post_ui(disable_buttons)
                self._post_ui(lambda: self.progress_bar.set(0.01))
                self._post_ui(
                    lambda: self.lbl_progress_status.configure(
                        text=f"🔧 Восстанавливаю {pkg_key}..."
                    ),
                )
                set_status(f"Восстановление {pkg_key}...")
                set_progress(10)
                try:

                    def progress_cb(line):
                        self._post_progress_text(line)
                        set_status(line)

                    if pkg_key == "torch":
                        env_setup.install_torch(
                            progress_cb=progress_cb, resume=False, variant="cpu"
                        )
                    elif pkg_key == "rvc_python":
                        env_setup.install_rvc(progress_cb=progress_cb)
                    else:
                        cmd = [
                            env_setup.PYTHON_EXE,
                            "-m",
                            "pip",
                            "install",
                            pip_spec,
                            "--target",
                            env_setup.SITE_PACKAGES,
                            "--upgrade",
                            "--no-deps",
                            "--force-reinstall",
                            "--no-cache-dir",
                        ]
                        env = os.environ.copy()
                        env["PYTHONUNBUFFERED"] = "1"
                        proc = subprocess.Popen(
                            cmd,
                            cwd=env_setup.PROJECT_ROOT,
                            env=env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            stdin=subprocess.PIPE,
                            bufsize=0,
                        )
                        env_setup._read_pip_output(proc, progress_cb)
                        proc.wait()
                        if proc.returncode != 0:
                            raise RuntimeError(f"pip завершился с кодом {proc.returncode}")

                    def success_done():
                        enable_buttons()
                        self.progress_bar.set(1.0)
                        set_progress(100)
                        self.lbl_progress_status.configure(
                            text=f"✅ Пакет '{pkg_key}' успешно восстановлен!"
                        )
                        set_status(t("status_ready"))
                        run_async_diagnostics(force_refresh=True)  # Перескан статусов
                        mb.showinfo(
                            t("update_done_title"),
                            f"Пакет '{pkg_key}' успешно восстановлен!",
                            parent=self,
                        )
                        _release_install_lock()

                    self._post_ui(success_done)
                except Exception as e:

                    def failed_done(err_msg=str(e)):
                        enable_buttons()
                        self.progress_bar.set(0.0)
                        set_progress(0)
                        set_status("Ожидание...")
                        self.lbl_progress_status.configure(
                            text=f"❌ Ошибка восстановления: {err_msg}"
                        )
                        mb.showerror(
                            t("update_error_title"),
                            f"Не удалось восстановить {pkg_key}:\n{err_msg}",
                            parent=self,
                        )
                        _release_install_lock()

                    self._post_ui(failed_done)

            self._start_worker(_install_thread)

        # Строим пустые строки с индикатором ожидания в раскрывающемся списке
        for key, friendly_name in self.dependency_names.items():
            row_frame = tk.Frame(self.details_frame, bg=bg_input)
            row_frame.pack(fill="x", pady=2, padx=5)

            lbl_name = tk.Label(
                row_frame,
                text=friendly_name,
                font=("Segoe UI", scaled_font_size(9)),
                bg=bg_input,
                fg=text_main,
                width=32,
                anchor="w",
            )
            lbl_name.pack(side="left", padx=5)

            lbl_stat = tk.Label(
                row_frame,
                text="⏳ Ожидание...",
                font=("Segoe UI", scaled_font_size(9), "bold"),
                bg=bg_input,
                fg=text_dim,
            )
            lbl_stat.pack(side="left", padx=10)

            # Кнопка ручного исправления конкретной зависимости (скрыта по умолчанию)
            pip_spec = self.dependency_pip.get(key, key)
            btn_fix = CompatCTkButton(
                row_frame,
                text="🔧 Исправить",
                command=lambda k=key, p=pip_spec: start_targeted_install(k, p),
                width=scaled_size(90, min_size=80),
                height=scaled_size(20, min_size=18),
                corner_radius=6,
                fg_color=btn_color,
                text_color=text_main,
                hover_color=bg_hover,
                font=("Segoe UI", scaled_font_size(8)),
            )

            self.row_widgets[key] = (lbl_name, lbl_stat, btn_fix)

        def toggle_details():
            if self.details_visible:
                self.details_frame.pack_forget()
                self.btn_toggle_details.configure(text=t("btn_show_details"))
                self.details_visible = False
            else:
                self.details_frame.pack(fill="x", padx=10, pady=(5, 10))
                self.btn_toggle_details.configure(text=t("btn_hide_details"))
                self.details_visible = True

        # Контейнер для двух кнопок в ряд: подробности и сканирование
        btn_row = tk.Frame(sec_deps, bg=bg_input)
        btn_row.pack(anchor="w", fill="x", padx=15, pady=(5, 15))

        self.btn_toggle_details = ctk.CTkButton(
            btn_row,
            text=t("btn_show_details"),
            command=toggle_details,
            fg_color=btn_color,
            hover_color=bg_hover,
            text_color=text_main,
            width=scaled_size(150, min_size=130),
            height=28,
        )
        self.btn_toggle_details.pack(side="left", padx=(0, 5))

        # ИСПРАВЛЕНО (Кэширование по выбору и кнопка пересканирования)
        self.btn_refresh_deps = ctk.CTkButton(
            btn_row,
            text="🔍 Проверить статус",
            command=lambda: run_async_diagnostics(force_refresh=True),
            fg_color=bg_active,
            hover_color=bg_hover,
            text_color=text_main,
            width=scaled_size(150, min_size=130),
            height=28,
        )
        self.btn_refresh_deps.pack(side="left", padx=(5, 0))

        def run_async_diagnostics(force_refresh=False):
            try:
                if not self.winfo_exists():
                    return
                self.lbl_deps_status.configure(
                    text="🔍 Сканирую состояние библиотек...", text_color=text_dim
                )
            except Exception:
                pass

            def _thread():
                results = env_setup.run_full_diagnostics(force_refresh=force_refresh)

                def _ui_update():
                    try:
                        if not self.winfo_exists():
                            return
                        if "error" in results:
                            if self.lbl_deps_status.winfo_exists():
                                self.lbl_deps_status.configure(
                                    text=f"❌ Сбой диагностики: {results['error']}",
                                    text_color="#b22222",
                                )
                            return

                        failed_count = 0
                        optional_status = env_setup.get_optional_status(results)
                        for key, val in results.items():
                            if key in env_setup.OPTIONAL_COMPONENTS:
                                opt_state = optional_status.get(key)
                                if opt_state == "ok":
                                    status_text, color = "✅ Исправен", "#2e7d32"
                                elif opt_state == "not_installed":
                                    # Нормальное состояние по умолчанию — модуль просто
                                    # не установлен (опциональная фича), а не поломка.
                                    status_text, color = "⚪ Не установлен (опционально)", text_dim
                                else:
                                    status_text, color = "❌ Сбой", "#b22222"
                                    failed_count += 1
                            else:
                                is_ok = val is True
                                status_text = "✅ Исправен" if is_ok else "❌ Сбой"
                                color = "#2e7d32" if is_ok else "#b22222"
                                if not is_ok:
                                    failed_count += 1

                            if key in self.row_widgets:
                                lbl_name, lbl_stat, btn_fix = self.row_widgets[key]
                                if lbl_stat.winfo_exists():
                                    # Исправлено TclError: fg=color вместо text_color
                                    lbl_stat.configure(text=status_text, fg=color)
                                if btn_fix.winfo_exists():
                                    if status_text != "✅ Исправен":
                                        btn_fix.pack(side="right", padx=5)
                                    else:
                                        btn_fix.pack_forget()

                        if self.lbl_deps_status.winfo_exists():
                            if failed_count == 0:
                                self.lbl_deps_status.configure(
                                    text=t("status_all_healthy"), text_color="#2e7d32"
                                )
                            else:
                                self.lbl_deps_status.configure(
                                    text=f"{t('status_some_failed')} ({failed_count})",
                                    text_color="#b22222",
                                )
                    except Exception:
                        pass

                self._post_ui(_ui_update)

            self._start_worker(_thread)

        # Быстрый старт: при открытии окна грузим кэш за 0мс (force_refresh=False)
        run_async_diagnostics(force_refresh=False)

        # --- СЕКЦИЯ 4: Диагностика ---
        sec_diag = ctk.CTkFrame(
            outer_frame, fg_color=bg_input, border_width=1, border_color=border_color
        )
        sec_diag.pack(fill="both", expand=True, pady=0, padx=5)

        lbl_diag_title = ctk.CTkLabel(
            sec_diag,
            text=t("section_diag"),
            font=ctk.CTkFont(weight="bold", size=14),
            text_color=text_main,
        )
        lbl_diag_title.pack(anchor="w", padx=15, pady=(10, 5))

        # Сетка сервисных кнопок внутри новой секции Диагностика
        util_frame = ctk.CTkFrame(sec_diag, fg_color="transparent")
        util_frame.pack(fill="x", padx=15, pady=(5, 5))
        util_frame.grid_columnconfigure(0, weight=1)
        util_frame.grid_columnconfigure(1, weight=1)

        def run_scan_flow():
            """Запускает полный цикл: Безопасное сканирование мусора -> Диагностика -> Подтверждение и удаление."""
            if _is_install_running():
                mb.showwarning(
                    t("update_title"),
                    f"Нельзя сканировать во время установки ({_get_current_install_type()}).\nДождитесь завершения или отмените установку.",
                    parent=self,
                )
                return

            def _scan_thread():
                self._post_ui(disable_buttons)
                self._post_ui(lambda: self.progress_bar.set(0.01))
                self._post_ui(
                    lambda: self.lbl_progress_status.configure(
                        text="🧹 Сканирование и перенос файлов в карантин..."
                    ),
                )
                set_status("Сканирование мусора...")
                set_progress(10)
                try:

                    def progress_cb(line):
                        self._post_progress_text(line)
                        set_status(line)

                    res = env_setup.scan_for_garbage(mode="deep", progress_cb=progress_cb)

                    def after_scan():
                        enable_buttons()
                        self.progress_bar.set(1.0)
                        set_progress(100)
                        set_status("Ожидание...")

                        q_count = res["quarantined_count"]
                        size_mb = res["size_mb"]
                        restored_count = res["restored_count"]

                        if restored_count > 0:
                            mb.showwarning(
                                t("msg_diagnostics_title"),
                                t("msg_scan_and_diag_restored"),
                                parent=self,
                            )
                        elif q_count > 0:
                            confirmed = mb.askyesno(
                                t("msg_diagnostics_title"),
                                t("msg_confirm_deletion_with_size", q_count, size_mb),
                                parent=self,
                            )
                            if confirmed:
                                self.lbl_progress_status.configure(
                                    text="🧹 Навсегда стираю файлы из карантина..."
                                )
                                set_status("Стирание файлов...")

                                def _delete_thread():
                                    deleted = env_setup.finalize_deletion(res["quarantined_list"])
                                    self._post_ui(
                                        lambda d=deleted: self.lbl_progress_status.configure(
                                            text=f"✅ Успешно очищено: {d} файлов."
                                        ),
                                    )
                                    self._post_ui(
                                        lambda d=deleted: mb.showinfo(
                                            t("update_done_title"),
                                            f"✅ Очистка успешно завершена!\nУдалено навсегда: {d} файлов.",
                                            parent=self,
                                        ),
                                    )
                                    set_status("Ожидание...")

                                self._start_worker(_delete_thread)
                            else:
                                self.lbl_progress_status.configure(
                                    text="📁 Файлы сохранены в карантине."
                                )
                        else:
                            mb.showinfo(
                                t("update_done_title"), "Мусорные файлы не обнаружены.", parent=self
                            )
                            self.lbl_progress_status.configure(text="")

                    self._post_ui(after_scan)
                except Exception as e:

                    def failed_done(err_msg=str(e)):
                        enable_buttons()
                        self.progress_bar.set(0.0)
                        set_progress(0)
                        set_status("Ожидание...")
                        self.lbl_progress_status.configure(text=f"❌ Ошибка: {err_msg}")
                        mb.showerror(
                            t("update_error_title"),
                            f"Не удалось выполнить сканирование:\n{err_msg}",
                            parent=self,
                        )

                    self._post_ui(failed_done)

            self._start_worker(_scan_thread)

        def run_diagnostics():
            self.lbl_progress_status.configure(text="🔍 Выполняю диагностику...")
            self.update_idletasks()
            status = env_setup.run_full_diagnostics(
                force_refresh=True
            )  # Форсируем принудительный перескан по кнопке

            if "error" in status:
                msg = f"Ошибка выполнения диагностики:\n{status['error']}\n\nХотите запустить процесс «Устранение ошибок», чтобы переустановить ключевые компоненты?"
                confirmed = mb.askyesno(t("msg_diagnostics_title"), msg, parent=self)
                if confirmed:
                    run_recovery_flow()
                self.lbl_progress_status.configure(text="")
                return

            failed = env_setup.get_broken_critical(status)
            optional_status = env_setup.get_optional_status(status)
            broken_optional = [k for k, v in optional_status.items() if v == "broken"]

            if not failed and not broken_optional:
                torch_stat = env_setup.torch_status()
                cuda_str = "Да" if torch_stat.get("cuda_available") else "Нет"
                msg = t("msg_diagnostics_success", torch_stat.get("version", "2.11.0"), cuda_str)
                mb.showinfo(t("msg_diagnostics_title"), msg, parent=self)
            elif not failed and broken_optional:
                # Критичные компоненты в порядке, но опциональный модуль
                # установлен и при этом не импортируется — стоит показать
                # отдельно, это не блокирует запуск, но требует внимания.
                msg = (
                    f"✅ Все критичные компоненты (нужные для аудио/GUI) исправны.\n\n"
                    f"⚠️ Опциональные модули с проблемой: {', '.join(broken_optional)}.\n\n"
                    f"Запустить автоматическое «Устранение ошибок» для этих модулей?"
                )
                confirmed = mb.askyesno(t("msg_diagnostics_title"), msg, parent=self)
                if confirmed:
                    run_recovery_flow()
            else:
                msg = f"❌ Неисправные компоненты: {', '.join(failed)}.\n\nЗапустить автоматическое «Устранение ошибок» для восстановления этих пакетов?"
                confirmed = mb.askyesno(t("msg_diagnostics_title"), msg, parent=self)
                if confirmed:
                    run_recovery_flow()

            update_variant_label()
            run_async_diagnostics(
                force_refresh=True
            )  # Обновляем раскрывающийся список зависимостей
            update_controls_visibility()
            self.lbl_progress_status.configure(text="")

        def run_recovery_flow():
            cache = env_setup.load_safe_files_cache()
            deleted = cache.get("deleted_files", [])
            if not deleted:
                mb.showinfo(t("btn_error_recovery"), t("msg_recovery_no_files"), parent=self)
                return

            # Используем общий PACKAGE_PIP_SPEC вместо локального package_mapping
            packages_to_restore = set()
            for f in deleted:
                pkg_folder = f.get("package", "unknown").lower()
                for key, pip_spec in PACKAGE_PIP_SPEC.items():
                    if key in pkg_folder:
                        packages_to_restore.add(pip_spec)

            if not packages_to_restore:
                mb.showinfo(
                    t("btn_error_recovery"),
                    "В истории удалений нет зарегистрированных ключевых пакетов.",
                    parent=self,
                )
                return

            confirmed = mb.askyesno(
                t("btn_error_recovery"),
                t("msg_recovery_confirm", ", ".join(packages_to_restore)),
                parent=self,
            )
            if not confirmed:
                return

            # Пытаемся захватить лок установки
            if not _acquire_install_lock("recovery"):
                mb.showwarning(
                    t("update_title"),
                    f"Уже выполняется другая установка ({_get_current_install_type()}).\nДождитесь её завершения или отмените.",
                    parent=self,
                )
                return

            def _recovery_thread():
                self._post_ui(disable_buttons)
                self._post_ui(lambda: self.progress_bar.set(0.01))
                self._post_ui(
                    lambda: self.lbl_progress_status.configure(text="🛠️ Восстановление пакетов..."),
                )
                set_status("Восстановление пакетов...")
                set_progress(10)
                try:

                    def progress_cb(line):
                        self._post_progress_text(line)
                        set_status(line)

                    restored = env_setup.run_error_recovery(progress_cb=progress_cb)

                    def success_done():
                        enable_buttons()
                        self.progress_bar.set(1.0)
                        set_progress(100)
                        set_status("Ожидание...")
                        if restored:
                            self.lbl_progress_status.configure(
                                text=t("msg_recovery_success", ", ".join(restored))
                            )
                            run_async_diagnostics(force_refresh=True)  # Перескан статусов
                            mb.showinfo(
                                t("update_done_title"),
                                t("msg_recovery_success", ", ".join(restored)),
                                parent=self,
                            )
                        else:
                            self.lbl_progress_status.configure(
                                text="Не удалось восстановить пакеты."
                            )
                            mb.showwarning(
                                t("update_error_title"),
                                "Не удалось восстановить пакеты. Проверьте соединение с интернетом.",
                                parent=self,
                            )
                        _release_install_lock()

                    self._post_ui(success_done)
                except Exception as e:

                    def failed_done(err_msg=str(e)):
                        enable_buttons()
                        self.progress_bar.set(0.0)
                        set_progress(0)
                        set_status("Ожидание...")
                        self.lbl_progress_status.configure(text=f"❌ Ошибка: {err_msg}")
                        mb.showerror(
                            t("update_error_title"),
                            f"Не удалось выполнить восстановление:\n{err_msg}",
                            parent=self,
                        )
                        _release_install_lock()

                    self._post_ui(failed_done)

            self._start_worker(_recovery_thread)

        # Кнопка очистки кэша и сканирования мусора объединена
        self.btn_clean = ctk.CTkButton(
            util_frame,
            text=t("btn_clean_cache"),
            command=run_scan_flow,
            fg_color=bg_active,
            hover_color=bg_hover,
            text_color=text_main,
        )
        self.btn_clean.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="ew")

        self.btn_diag = ctk.CTkButton(
            util_frame,
            text=t("btn_run_diagnostics"),
            command=run_diagnostics,
            fg_color=btn_color,
            hover_color=bg_hover,
            text_color=text_main,
        )
        self.btn_diag.grid(row=0, column=1, padx=(5, 0), pady=5, sticky="ew")

        self.btn_recovery = ctk.CTkButton(
            util_frame,
            text=t("btn_error_recovery"),
            command=run_recovery_flow,
            fg_color=btn_color,
            hover_color=bg_hover,
            text_color=text_main,
        )
        self.btn_recovery.grid(row=1, column=0, columnspan=2, padx=0, pady=5, sticky="ew")

        def progress_cb(line):
            line_str = line.replace("\r", "").strip()
            if not line_str:
                return
            print(f"[Torch Setup UI] {line_str}")

            self._post_progress_text(line_str)
            set_status(f"Setup: {line_str}")

            m_coll = _torch_collecting_re.search(line_str)
            m_dl = _torch_downloading_re.search(line_str)
            m_inst = _torch_installing_re.search(line_str)

            if m_coll:
                pkg = m_coll.group(1)
                self.install_state["current_pkg"] = pkg
            elif m_dl:
                pkg = m_dl.group(1)
                self.install_state["current_pkg"] = pkg
            elif m_inst:
                self._post_ui(lambda: self.progress_bar.set(0.95))
                set_progress(95)

            m_pct = _torch_percent_re.search(line_str)
            m_ratio = _torch_ratio_re.search(line_str)

            if m_pct:
                pct = int(m_pct.group(1))
                self._post_ui(lambda: self.progress_bar.set(pct / 100.0))
                set_progress(pct)
            elif m_ratio:
                cur, total = float(m_ratio.group(1)), float(m_ratio.group(2))
                if total > 0:
                    pct = int((cur / total) * 100)
                    self._post_ui(lambda: self.progress_bar.set(cur / total))
                    set_progress(pct)

        def start_install(variant, resume=False):
            if variant == "cu128":
                gpu = env_setup.detect_gpu()
                if gpu.get("vendor") != "nvidia":
                    mb.showerror(
                        t("update_error_title"), t("msg_cuda_requires_nvidia"), parent=self
                    )
                    return

            import sys

            if "torch" in sys.modules:
                confirmed = mb.askyesno(
                    t("update_title"), t("msg_torch_already_loaded_restart_confirm"), parent=self
                )
                if confirmed:
                    from engine.settings_store import load_settings, save_settings

                    settings = load_settings()
                    settings["open_updates_on_startup"] = True
                    settings["install_variant_on_startup"] = variant
                    save_settings(settings)

                    from engine.updater import restart

                    restart()
                return

            if not resume:
                warning_msg = t(
                    "torch_install_warning",
                    {"cu128": "GPU (CUDA)", "cpu": "CPU"}.get(variant, variant),
                )
                confirmed = mb.askyesno(t("update_title"), warning_msg, parent=self)
                if not confirmed:
                    return

            # Пытаемся захватить лок установки
            install_type = f"torch:{variant}"
            if not _acquire_install_lock(install_type):
                mb.showwarning(
                    t("update_title"),
                    f"Уже выполняется другая установка ({_get_current_install_type()}).\nДождитесь её завершения или отмените.",
                    parent=self,
                )
                return

            self.install_was_stopped = False

            def _install_thread():
                self._post_ui(disable_buttons)
                self._post_ui(lambda: self.progress_bar.set(0.01))
                set_progress(1)
                self._post_ui(
                    lambda: self.lbl_progress_status.configure(
                        text=t("status_torch_setup", variant)
                    ),
                )
                set_status(t("status_torch_setup", variant))
                try:
                    status = env_setup.install_torch(
                        progress_cb=progress_cb, resume=resume, variant=variant
                    )

                    def success_done():
                        enable_buttons()
                        self.progress_bar.set(1.0)
                        set_progress(100)
                        self.lbl_progress_status.configure(text=t("torch_install_success_label"))
                        set_status(t("status_ready"))
                        update_variant_label()
                        run_async_diagnostics(
                            force_refresh=True
                        )  # Обновляем раскрывающийся список зависимостей
                        mb.showinfo(
                            t("update_done_title"), t("torch_install_success", variant), parent=self
                        )
                        _release_install_lock()

                    self._post_ui(success_done)
                except Exception as e:

                    def failed_done(err_msg=str(e)):
                        enable_buttons()
                        self.progress_bar.set(0.0)
                        set_progress(0)
                        set_status(t("status_waiting"))
                        if getattr(self, "install_was_stopped", False):
                            self.lbl_progress_status.configure(text=t("msg_install_stopped"))
                            mb.showinfo(t("update_title"), t("msg_install_stopped"), parent=self)
                        else:
                            self.lbl_progress_status.configure(text=t("torch_install_failed_label"))
                            mb.showerror(
                                t("update_error_title"),
                                t("torch_install_failed", err_msg),
                                parent=self,
                            )
                        _release_install_lock()

                    self._post_ui(failed_done)

            self._start_worker(_install_thread)

        # Автоматический запуск/продолжение установки после перезапуска в безопасном режиме
        auto_install_variant = self.settings.get("install_variant_on_startup")
        if auto_install_variant:
            self.settings["install_variant_on_startup"] = None
            save_settings(self.settings)
            self.after(300, lambda: start_install(auto_install_variant, resume=True))

        # ── Управление видимостью кнопок Отмена/Продолжить во футере ──
        def disable_buttons():
            try:
                if not self.winfo_exists():
                    return
                if self.btn_gpu.winfo_exists():
                    self.btn_gpu.configure(state="disabled")
                if self.btn_cpu.winfo_exists():
                    self.btn_cpu.configure(state="disabled")
                if self.chk_auto.winfo_exists():
                    self.chk_auto.configure(state="disabled")
                if self.btn_check.winfo_exists():
                    self.btn_check.configure(state="disabled")
                if self.btn_clean.winfo_exists():
                    self.btn_clean.configure(state="disabled")
                if self.btn_diag.winfo_exists():
                    self.btn_diag.configure(state="disabled")
                if self.btn_recovery.winfo_exists():
                    self.btn_recovery.configure(state="disabled")
                if self.seg_pref.winfo_exists():
                    self.seg_pref.configure(state="disabled")
                if self.btn_toggle_details.winfo_exists():
                    self.btn_toggle_details.configure(state="disabled")
                if self.btn_refresh_deps.winfo_exists():
                    self.btn_refresh_deps.configure(state="disabled")
                self.install_running = True
                update_controls_visibility()
            except Exception:
                pass

        def enable_buttons():
            try:
                if not self.winfo_exists():
                    return
                if self.btn_gpu.winfo_exists():
                    if gpu_info.get("vendor") == "nvidia":
                        self.btn_gpu.configure(state="normal")
                    else:
                        self.btn_gpu.configure(state="disabled")

                if self.btn_cpu.winfo_exists():
                    self.btn_cpu.configure(state="normal")
                if self.chk_auto.winfo_exists():
                    self.chk_auto.configure(state="normal")
                if self.btn_check.winfo_exists():
                    self.btn_check.configure(state="normal")
                if self.btn_clean.winfo_exists():
                    self.btn_clean.configure(state="normal")
                if self.btn_diag.winfo_exists():
                    self.btn_diag.configure(state="normal")
                if self.btn_recovery.winfo_exists():
                    self.btn_recovery.configure(state="normal")
                if self.seg_pref.winfo_exists():
                    self.seg_pref.configure(state="normal")
                if self.btn_toggle_details.winfo_exists():
                    self.btn_toggle_details.configure(state="normal")
                if self.btn_refresh_deps.winfo_exists():
                    self.btn_refresh_deps.configure(state="normal")
                self.install_running = False
                update_controls_visibility()
            except Exception:
                pass

        def update_controls_visibility():
            try:
                if not self.winfo_exists():
                    return
                if getattr(self, "install_running", False):
                    if self.active_controls_frame.winfo_exists():
                        self.active_controls_frame.pack(fill="x", padx=15, pady=(5, 10))
                    if self.btn_stop.winfo_exists():
                        self.btn_stop.pack(side="left", expand=True, fill="x")
                    if self.btn_resume.winfo_exists():
                        self.btn_resume.pack_forget()
                else:
                    checkpoint = env_setup.load_torch_checkpoint()
                    has_checkpoint = checkpoint.get("stage") in (
                        "downloading",
                        "cleaned",
                        "verifying",
                    )
                    if has_checkpoint:
                        if self.active_controls_frame.winfo_exists():
                            self.active_controls_frame.pack(fill="x", padx=15, pady=(5, 10))
                        if self.btn_stop.winfo_exists():
                            self.btn_stop.pack_forget()
                        if self.btn_resume.winfo_exists():
                            self.btn_resume.pack(side="left", expand=True, fill="x")
                    else:
                        if self.active_controls_frame.winfo_exists():
                            self.active_controls_frame.pack_forget()
            except Exception:
                pass

        update_controls_visibility()


_env_settings_window = None


def open_env_settings_window():
    global _env_settings_window
    if _env_settings_window is not None and _env_settings_window.winfo_exists():
        _env_settings_window.focus()
        return
    _env_settings_window = EnvSettingsWindow(root)


from engine.env_core.diagnostics import _read_pip_output
