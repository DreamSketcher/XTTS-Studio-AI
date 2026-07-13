# -*- coding: utf-8 -*-
"""gui.py — точка входа XTTS Studio.

Только запуск интерфейса: подготовка окружения, импорт GUI-модулей,
создание главного окна и mainloop(). Вся логика вынесена в engine/ (техника)
и engine/gui/ (интерфейс).
"""

import atexit
import os
import sys
import threading
import traceback

BASE_DIR = os.path.dirname(__file__)
SITE_PACKAGES = os.path.join(BASE_DIR, "python", "xtts_env", "Lib", "site-packages")
if os.path.exists(SITE_PACKAGES):
    sys.path.insert(0, SITE_PACKAGES)

# ── ЗАЩИТА ОТ ЗАПУСКА ВТОРОГО ЭКЗЕМПЛЯРА (Single Instance Lock) ──
# Используем файловый лок в %TEMP%/XTTS Studio.lock для кроссплатформенности.
# На Windows также пытаемся создать named mutex для надёжности.
_single_instance_lock = None
_single_instance_lock_file = None


def _acquire_single_instance_lock() -> bool:
    """Пытается захватить лок единственного экземпляра.

    Возвращает True если лок получен, False если другой экземпляр уже запущен.
    """
    global _single_instance_lock, _single_instance_lock_file

    # Пробуем named mutex на Windows (самый надёжный способ)
    if sys.platform == "win32":
        try:
            import ctypes

            # Создаем именованный мьютекс. Если он уже существует — другой процесс держит его.
            mutex_name = "Global\\XTTS_Studio_Single_Instance_Mutex"
            kernel32 = ctypes.windll.kernel32
            mutex = kernel32.CreateMutexW(None, False, mutex_name)
            last_error = kernel32.GetLastError()
            ERROR_ALREADY_EXISTS = 183
            if last_error == ERROR_ALREADY_EXISTS:
                # Мьютекс уже существует — другой экземпляр запущен
                if mutex:
                    kernel32.CloseHandle(mutex)
                return False
            # Мьютекс создан успешно, сохраняем хендл для закрытия при выходе
            _single_instance_lock = mutex
            atexit.register(
                lambda: (
                    kernel32.CloseHandle(_single_instance_lock) if _single_instance_lock else None
                )
            )
            return True
        except Exception as e:
            print(
                f"[Single Instance] Windows mutex failed, falling back to file lock: {e}",
                file=sys.stderr,
            )

    # Fallback: файловый лок (работает на всех платформах)
    try:
        import tempfile

        lock_path = os.path.join(tempfile.gettempdir(), "XTTS_Studio.lock")
        _single_instance_lock_file = open(lock_path, "w")
        # Пытаемся захватить эксклюзивный лок (non-blocking)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(_single_instance_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(_single_instance_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Лок захвачен, пишем PID для диагностики
        _single_instance_lock_file.write(str(os.getpid()))
        _single_instance_lock_file.flush()

        def _release_lock():
            try:
                if _single_instance_lock_file:
                    if sys.platform == "win32":
                        import msvcrt

                        msvcrt.locking(_single_instance_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(_single_instance_lock_file.fileno(), fcntl.LOCK_UN)
                    _single_instance_lock_file.close()
                    os.remove(lock_path)
            except Exception:
                pass

        atexit.register(_release_lock)
        return True
    except (IOError, OSError, BlockingIOError):
        # Не удалось захватить лок — другой экземпляр уже запущен
        try:
            if _single_instance_lock_file:
                _single_instance_lock_file.close()
        except Exception:
            pass
        _single_instance_lock_file = None
        return False
    except Exception as e:
        print(f"[Single Instance] Unexpected error acquiring lock: {e}", file=sys.stderr)
        return False


def _show_already_running_error():
    """Показывает ошибку, что приложение уже запущено."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "XTTS Studio — уже запущено",
            "Приложение уже запущено.\n\n"
            "Если окно не видно, проверьте область уведомлений (трей) или диспетчер задач.\n"
            "Можно также попробовать закрыть через диспетчер задач и запустить снова.",
        )
        root.destroy()
    except Exception:
        # Если GUI не доступен, печатаем в консоль
        print("ERROR: XTTS Studio is already running.", file=sys.stderr)


# Захватываем лок ПЕРВЫМ ДЕЛОМ, до любых других инициализаций
if not _acquire_single_instance_lock():
    _show_already_running_error()
    sys.exit(0)


def _global_exception_handler(exc_type, exc_value, exc_tb):
    traceback.print_exception(exc_type, exc_value, exc_tb)
    input("Press Enter to exit...")


sys.excepthook = _global_exception_handler

try:
    from engine.gui_cyrillic_checker import check_project_path

    check_project_path()
except Exception as e:
    print(f"[Cyrillic Checker] Skip path validation due to: {e}", file=sys.stderr)


# ── ХЕЛПЕР СОХРАНЕНИЯ ЛОГОВ СБОЕВ ВОССТАНОВЛЕНИЯ ──
def _log_startup_error(error_message):
    """
    Автоматически создает папку C:\\XTTS Studio\\logs\\ и записывает подробный
    traceback произошедшего сбоя восстановления/проверки при запуске.
    """
    try:
        logs_dir = os.path.join(BASE_DIR, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_file = os.path.join(logs_dir, "startup_recovery_error.log")
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] ERROR DURING STARTUP RECOVERY:\n{error_message}\n")
            f.write("-" * 80 + "\n")
        print(f"[Core Setup] Лог ошибки успешно записан в файл: {log_file}")
    except Exception as log_err:
        print(f"[Core Setup] Не удалось записать лог в файл: {log_err}", file=sys.stderr)


OPEN_UPDATES_ON_STARTUP = False


def _show_startup_install_window(variant):
    """
    Отображает легковесное Tkinter окно установки PyTorch до того,
    как будут импортированы модули GUI и загружен PyTorch. Это гарантирует
    отсутствие блокировок DLL-файлов (PermissionError) со стороны работающего приложения.
    """
    import re
    import threading
    import tkinter as tk
    from tkinter import messagebox, ttk

    import i18n

    from engine import env_setup

    # ── ЛОК УСТАНОВКИ для startup install ──
    try:
        from engine.gui.env_settings import (
            _acquire_install_lock,
            _get_current_install_type,
            _release_install_lock,
        )
    except ImportError:

        def _acquire_install_lock(install_type):
            return True

        def _release_install_lock():
            pass

        def _get_current_install_type():
            return "unknown"

    # Пытаемся захватить лок установки
    if not _acquire_install_lock(f"startup_install:{variant}"):
        # Если не удалось захватить лок — другая установка уже идёт
        root_temp = tk.Tk()
        root_temp.withdraw()
        messagebox.showwarning(
            i18n.t("update_title"),
            f"Уже выполняется другая установка ({_get_current_install_type()}).\nДождитесь её завершения.",
            parent=root_temp,
        )
        root_temp.destroy()
        return

    win = tk.Tk()
    win.title(i18n.t("win_update_settings_title"))
    win.geometry("500x200")
    win.resizable(False, False)

    # Центрирование окна по центру экрана
    try:
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = (sw - 500) // 2
        y = (sh - 200) // 2
        win.geometry(f"500x200+{x}+{y}")
    except Exception:
        pass

    win.configure(bg="#2b2b2b")

    # Заголовок
    lbl_title = tk.Label(
        win,
        text=i18n.t("status_torch_setup", variant),
        fg="#ffffff",
        bg="#2b2b2b",
        font=("Segoe UI", 12, "bold"),
        justify="left",
    )
    lbl_title.pack(padx=20, pady=(20, 5), anchor="w")

    # Текст статуса
    lbl_status = tk.Label(
        win, text="", fg="#aaaaaa", bg="#2b2b2b", font=("Segoe UI", 10), justify="left"
    )
    lbl_status.pack(padx=20, pady=(0, 15), anchor="w")

    # Стилизация прогресс-бара
    style = ttk.Style(win)
    style.theme_use("clam")
    style.configure("TProgressbar", thickness=12, troughcolor="#333333", background="#2e7d32")
    progress = ttk.Progressbar(
        win, orient="horizontal", length=460, mode="determinate", style="TProgressbar"
    )
    progress.pack(padx=20, pady=(0, 20))

    # Регэкспы для парсинга вывода pip в реальном времени
    _torch_percent_re = re.compile(r"(\d{1,3})%")
    _torch_ratio_re = re.compile(r"([\d.]+)\s*/\s*([\d.]+)\s*MB")

    def progress_cb(line):
        line_str = line.replace("\r", "").strip()
        if not line_str:
            return
        print(f"[Torch Setup Startup] {line_str}")
        win.after(0, lambda: lbl_status.config(text=line_str[:80]))
        m_pct = _torch_percent_re.search(line_str)
        m_ratio = _torch_ratio_re.search(line_str)
        if m_pct:
            pct = int(m_pct.group(1))
            win.after(0, lambda: progress.config(value=pct))
        elif m_ratio:
            cur, total = float(m_ratio.group(1)), float(m_ratio.group(2))
            if total > 0:
                pct = int((cur / total) * 100)
                win.after(0, lambda: progress.config(value=pct))

    def _install_thread():
        try:
            status = env_setup.install_torch(progress_cb=progress_cb, resume=True, variant=variant)
            win.after(
                0,
                lambda: messagebox.showinfo(
                    i18n.t("update_done_title"),
                    i18n.t("torch_install_success", variant),
                ),
            )
        except Exception as e:
            err = str(e)
            win.after(
                0,
                lambda: messagebox.showerror(
                    i18n.t("update_error_title"),
                    i18n.t("torch_install_failed", err),
                ),
            )
        finally:
            _release_install_lock()
            win.after(0, win.destroy)

    threading.Thread(target=_install_thread, daemon=True).start()
    win.mainloop()


def _show_startup_recovery_window(broken_packages):
    """
    Отображает легковесное Tkinter окно автоматического восстановления
    удаленных/поврежденных библиотек (self-healing) до старта главного GUI.
    """
    import threading
    import tkinter as tk
    from tkinter import messagebox, ttk

    import i18n

    from engine import env_setup

    win = tk.Tk()
    win.title(i18n.t("btn_error_recovery"))
    win.geometry("500x200")
    win.resizable(False, False)

    try:
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = (sw - 500) // 2
        y = (sh - 200) // 2
        win.geometry(f"500x200+{x}+{y}")
    except Exception:
        pass

    win.configure(bg="#2b2b2b")

    lbl_title = tk.Label(
        win,
        text="🛠️ Автоматическое восстановление библиотек...",
        fg="#ffffff",
        bg="#2b2b2b",
        font=("Segoe UI", 11, "bold"),
        justify="left",
    )
    lbl_title.pack(padx=20, pady=(20, 5), anchor="w")

    lbl_status = tk.Label(
        win,
        text="Восстановление: " + ", ".join(broken_packages)[:45] + "...",
        fg="#aaaaaa",
        bg="#2b2b2b",
        font=("Segoe UI", 9),
        justify="left",
    )
    lbl_status.pack(padx=20, pady=(0, 15), anchor="w")

    style = ttk.Style(win)
    style.theme_use("clam")
    style.configure("TProgressbar", thickness=12, troughcolor="#333333", background="#2e5b82")
    progress = ttk.Progressbar(
        win, orient="horizontal", length=460, mode="indeterminate", style="TProgressbar"
    )
    progress.pack(padx=20, pady=(0, 20))
    progress.start(10)

    def progress_cb(line):
        line_str = line.replace("\r", "").strip()
        if not line_str:
            return
        print(f"[Recovery Startup] {line_str}")
        try:
            win.after(0, lambda: lbl_status.config(text=line_str[:80]))
        except RuntimeError:
            # Окно уже не в mainloop (например, было закрыто раньше времени
            # или сработала гонка потоков) — обновление интерфейса просто
            # пропускаем, восстановление в фоновом потоке продолжается,
            # а реальный текст ошибки pip всё равно уже записан в
            # logs/recovery_pip_output.log функцией emit() в diagnostics.py.
            pass

    def _recovery_thread():
        try:
            # ── ЛОК УСТАНОВКИ: предотвращаем одновременный запуск восстановления ──
            # Импортируем функции лока из env_settings (они определены на уровне модуля)
            try:
                from engine.gui.env_settings import (
                    PACKAGE_PIP_SPEC,
                    _acquire_install_lock,
                    _get_current_install_type,
                    _release_install_lock,
                )
            except ImportError:
                # Fallback если env_settings недоступен (не должно случиться в нормальной работе)
                def _acquire_install_lock(install_type):
                    return True

                def _release_install_lock():
                    pass

                def _get_current_install_type():
                    return "unknown"

                PACKAGE_PIP_SPEC = {
                    "torch": "torch==2.2.2 torchaudio==2.2.2 torchvision==0.17.2",
                    "torchaudio": "torchaudio==2.2.2",
                    "torchvision": "torchvision==0.17.2",
                    "tts": "coqui-tts",
                    "numpy": "numpy==1.26.4",
                    "pygame": "pygame",
                    "customtkinter": "customtkinter",
                    "num2words": "num2words",
                    "llama_cpp": "llama-cpp-python",
                    "soundfile": "soundfile",
                    "rvc_python": "rvc-python",
                    "av": "av==10.0.0",
                }

            # Пытаемся захватить лок установки
            if not _acquire_install_lock("startup_recovery"):
                # Если не удалось захватить лок — другой процесс восстановления уже идёт
                win.after(
                    0,
                    lambda: messagebox.showwarning(
                        i18n.t("update_title"),
                        f"Уже выполняется другая установка ({_get_current_install_type()}).\nДождитесь её завершения.",
                        parent=win,
                    ),
                )
                win.after(0, win.destroy)
                return

            # Записываем сломанные пакеты в кэш удалений, чтобы run_error_recovery() знал, что чинить
            cache = env_setup.load_safe_files_cache()
            # Используем общий PACKAGE_PIP_SPEC (синхронизируется с env_settings.py)
            import time

            for pkg in broken_packages:
                pip_spec = PACKAGE_PIP_SPEC.get(pkg, pkg)
                if "deleted_files" not in cache or not isinstance(cache["deleted_files"], list):
                    cache["deleted_files"] = []
                cache["deleted_files"].append(
                    {
                        "path": f"site-packages/{pkg}",
                        "size": 0,
                        "package": pip_spec,
                        "timestamp": time.time(),
                    }
                )
            env_setup.save_safe_files_cache(cache)

            # Запускаем автовосстановление
            restored = env_setup.run_error_recovery(progress_cb=progress_cb)
            if restored:
                win.after(
                    0,
                    lambda: messagebox.showinfo(
                        i18n.t("update_done_title"),
                        "Библиотеки успешно восстановлены:\n" + ", ".join(restored),
                    ),
                )
            else:
                win.after(
                    0,
                    lambda: messagebox.showwarning(
                        i18n.t("update_error_title"),
                        "Не удалось переустановить библиотеки. Проверьте интернет-соединение.",
                    ),
                )
        except Exception as e:
            # Записываем подробный лог ошибки в logs/ при сбое в потоке
            err_trace = traceback.format_exc()
            _log_startup_error(err_trace)
            err_msg = str(e)
            win.after(
                0,
                lambda: messagebox.showerror(
                    i18n.t("update_error_title"),
                    f"Ошибка восстановления:\n{err_msg}\n\nПодробности записаны в logs/startup_recovery_error.log",
                ),
            )
        finally:
            _release_install_lock()
            win.after(0, win.destroy)

    threading.Thread(target=_recovery_thread, daemon=True).start()
    win.mainloop()


def _run_scan_with_splash(diagnostics_fn):
    """Показывает переливающийся сплэш-экран ("XTTS Studio"), пока в фоновом
    потоке выполняется diagnostics_fn() — САМА диагностика не меняется ни
    на йоту, это чистая визуальная обёртка поверх честного скана.

    Сознательно НЕ переиспользует движок радуги из header_panel.py (там PIL +
    неявный импорт customtkinter через env_settings/ai_status_window) — сплэш
    должен пережить даже ситуацию, когда именно customtkinter/PIL сломаны,
    ведь для обнаружения такой поломки diagnostics_fn и запускается. Поэтому
    здесь только «голый» tkinter + colorsys (тот же принцип HSV-цикла, что и
    в neon_widgets/header_panel, но без внешних зависимостей).
    """
    import colorsys
    import tkinter as tk
    import webbrowser

    GITHUB_URL = "https://github.com/DreamSketcher/XTTS-Studio"
    result = {}

    try:
        splash = tk.Tk()
        splash.overrideredirect(True)
        splash.configure(bg="#0d1117")
        w, h = 360, 140
        sw = splash.winfo_screenwidth()
        sh = splash.winfo_screenheight()
        splash.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        title_lbl = tk.Label(
            splash,
            text="XTTS Studio",
            font=("Segoe UI", 20, "bold"),
            bg="#0d1117",
            fg="#58a6ff",
        )
        title_lbl.pack(pady=(24, 0))

        author_lbl = tk.Label(
            splash,
            text="by EXIZ10TION",
            font=("Segoe UI", 9, "italic"),
            bg="#0d1117",
            fg="#7c6aa5",
            cursor="hand2",
        )
        author_lbl.pack(pady=(0, 2))
        # Клик по подписи автора открывает репозиторий в браузере по умолчанию
        author_lbl.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))

        # Жирное подчёркивание под подписью — обычный Label.underline слишком
        # тонкий и не поддаётся управлению толщиной, поэтому рисуем отдельной
        # полосой того же цвета, что и текст (ширина подгоняется под текст
        # после отрисовки).
        author_underline = tk.Frame(splash, bg="#7c6aa5", height=2, cursor="hand2")
        author_underline.pack(pady=(0, 8))
        author_underline.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))
        splash.update_idletasks()
        author_underline.configure(width=author_lbl.winfo_reqwidth())

        status_lbl = tk.Label(
            splash,
            text="Проверка окружения...",
            font=("Segoe UI", 10),
            bg="#0d1117",
            fg="#8b949e",
        )
        status_lbl.pack()

        hue_state = {"h": 0.0}
        # Смещение и приглушённые sat/val для подписи автора — тот же принцип,
        # что и в header_panel._author_style (title и author не должны
        # моргать абсолютно синхронно и одним и тем же цветом).
        AUTHOR_HUE_OFFSET = 0.15
        AUTHOR_SAT, AUTHOR_VAL = 0.55, 0.85

        def _pulse():
            if not splash.winfo_exists():
                return
            hue_state["h"] = (hue_state["h"] + 0.012) % 1.0
            r, g, b = colorsys.hsv_to_rgb(hue_state["h"], 0.65, 1.0)
            title_color = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
            ah = (hue_state["h"] + AUTHOR_HUE_OFFSET) % 1.0
            ar, ag, ab = colorsys.hsv_to_rgb(ah, AUTHOR_SAT, AUTHOR_VAL)
            author_color = f"#{int(ar * 255):02x}{int(ag * 255):02x}{int(ab * 255):02x}"
            try:
                title_lbl.configure(fg=title_color)
                author_lbl.configure(fg=author_color)
                author_underline.configure(bg=author_color)
                splash.after(40, _pulse)
            except Exception:
                pass

        _pulse()

        def _worker():
            try:
                result["value"] = diagnostics_fn()
            except Exception as e:
                result["error"] = e
            finally:
                try:
                    splash.after(0, splash.destroy)
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()
        splash.mainloop()
    except Exception as e:
        # Сплэш — чисто косметическая надстройка: если сам tkinter/дисплей
        # недоступны, диагностика ВСЁ РАВНО должна отработать честно.
        print(f"[Core Setup] Сплэш недоступен ({e}), скан без анимации.")
        return diagnostics_fn()

    if "error" in result:
        raise result["error"]
    return result.get("value")


def _ensure_dependencies_before_startup():
    """
    Единая система самолечения (Self-Healing) всех библиотек при старте.
    Проверяет работоспособность всех 11 пакетов. Если обнаружен критический сбой,
    предлагает запустить фоновую установку/исправление поврежденных пакетов.
    """
    global OPEN_UPDATES_ON_STARTUP
    try:
        from engine.settings_store import load_settings, save_settings

        st = load_settings()
        # Если затребована безопасная переустановка после рестарта
        auto_variant = st.get("install_variant_on_startup")
        if auto_variant:
            st["install_variant_on_startup"] = None
            st["open_updates_on_startup"] = False
            save_settings(st)
            _show_startup_install_window(auto_variant)
            OPEN_UPDATES_ON_STARTUP = True
            os.environ["OPEN_UPDATES_ON_STARTUP"] = "1"
            return
        if st.get("open_updates_on_startup"):
            OPEN_UPDATES_ON_STARTUP = True
            os.environ["OPEN_UPDATES_ON_STARTUP"] = "1"
            st["open_updates_on_startup"] = False
            save_settings(st)
    except Exception as e:
        print(f"[Core Setup] Ошибка загрузки настроек автозапуска: {e}")

    if OPEN_UPDATES_ON_STARTUP:
        os.environ["OPEN_UPDATES_ON_STARTUP"] = "1"
        return

    try:
        from engine import env_setup
    except Exception as e:
        print(f"[Core Setup] env_setup недоступен ({e}) — пропускаю проверку окружения.")
        return

    # get_broken_critical импортируем НАПРЯМУЮ из diagnostics.py, в обход
    # прокси-модуля env_setup (engine/env_core/__init__.py может явно
    # перечислять экспортируемые имена, и туда эту функцию можно забыть
    # добавить — прямой импорт работает независимо от этого списка).
    try:
        from engine.env_core.diagnostics import get_broken_critical
    except Exception as e:
        print(f"[Core Setup] get_broken_critical недоступен ({e}) — пропускаю проверку окружения.")
        return

    print("[Core Setup] Полная диагностика системных библиотек...")
    diag_status = _run_scan_with_splash(env_setup.run_full_diagnostics)

    if "error" in diag_status:
        # Записываем подробный лог ошибки при сбое диагностики
        _log_startup_error(f"Сбой диагностики при запуске: {diag_status['error']}")
        print(f"[Core Setup] Ошибка запуска диагностики: {diag_status['error']}")
        return

    # Находим ДЕЙСТВИТЕЛЬНО неисправные критичные библиотеки (те, без
    # которых невозможен вывод аудио TTS или запуск GUI). llama_cpp и
    # rvc_python — опциональные модули, их отсутствие не считается
    # поломкой (см. diagnostics.get_broken_critical / OPTIONAL_COMPONENTS).
    broken_critical = get_broken_critical(diag_status)

    if not broken_critical:
        # Если все критические импортируются — продолжаем запуск
        print("[Core Setup] Все критические библиотеки исправны. Продолжаю запуск.")
        return

    # Если критические сломаны — показываем диалог восстановления!
    print(f"[Core Setup] Обнаружены поврежденные критические библиотеки: {broken_critical}")
    try:
        import tkinter as tk
        from tkinter import messagebox

        root_temp = tk.Tk()
        root_temp.withdraw()
        title = "🛠️ Восстановление библиотек"
        msg = (
            f"Внимание: обнаружены поврежденные или отсутствующие критические библиотеки:\n"
            f"👉 {', '.join(broken_critical)}\n\n"
            f"Без них запуск приложения невозможен.\n\n"
            f"Запустить автоматическое восстановление и исправление через интернет?"
        )
        res = messagebox.askyesno(title, msg, parent=root_temp)
        if res is True:
            # Запускаем startup-окно восстановления для всех сломанных пакетов!
            root_temp.destroy()
            _show_startup_recovery_window(broken_critical)
        else:
            print("[Core Setup] Пользователь отказался от исправления. Завершение работы.")
            root_temp.destroy()
            sys.exit(0)
    except SystemExit:
        sys.exit(0)
    except Exception as e:
        # Записываем подробный лог ошибки при показе диалога восстановления
        err_trace = traceback.format_exc()
        _log_startup_error(err_trace)
        print(f"[Core Setup] Ошибка при показе диалога восстановления: {e}")


_ensure_dependencies_before_startup()

from engine import updater
from engine.gui.main_window import create_main_window


def main():
    # ВАЖНО: проверка обновления — самое первое, что делает приложение.
    # Если прошлый запуск (после apply_update) не дошёл до
    # updater.confirm_update_success() внутри create_main_window(), значит
    # обновление сломало старт — файлы уже автоматически откачены здесь.
    startup_status = updater.check_startup_health()
    root = create_main_window(startup_status=startup_status)

    # Если был выбран переход в настройки обновлений, открываем панель
    if OPEN_UPDATES_ON_STARTUP:
        try:
            from engine.gui import env_settings

            # ...
            root.after(500, lambda: env_settings.open_env_settings_window())
        except Exception as e:
            print(f"[Torch] Ошибка автооткрытия настроек: {e}")

    root.mainloop()


if __name__ == "__main__":
    main()
