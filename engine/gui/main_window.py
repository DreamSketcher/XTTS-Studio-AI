# -*- coding: utf-8 -*-
"""engine/gui/main_window.py — сборка главного окна XTTS Studio.

Оркестратор: создаёт root-окно, глобальное состояние (tk-переменные),
внедряет зависимости в GUI-модули и строит интерфейс в том же порядке,
что и исходный монолитный gui.py. Поведение, внешний вид и названия
кнопок не изменены.
"""
import threading
import tkinter as tk
from typing import Optional

import pygame
from tkinterdnd2 import TkinterDnD

from i18n import t, set_language, LANGUAGES

try:
    # LIBRARY_DIR — папка library/ (normalized.wav + кеш эмбеддингов).
    # BACKUP_DIR — legacy-алиас; если paths.py ещё отдаёт reference/backup,
    # ниже принудительно предпочитаем LIBRARY_DIR.
    from engine.paths import BASE_DIR, OUTPUT_DIR, ICON_PATH

    try:
        from engine.paths import LIBRARY_DIR as _LIBRARY_DIR
    except ImportError:
        _LIBRARY_DIR = None
    try:
        from engine.paths import BACKUP_DIR as _BACKUP_DIR
    except ImportError:
        _BACKUP_DIR = None
except ImportError:
    # Fallback: paths.py в некоторых сборках экспортирует только BASE_DIR
    from engine.paths import BASE_DIR
    import os as _os_paths

    _LIBRARY_DIR = _os_paths.path.join(str(BASE_DIR), "library")
    _BACKUP_DIR = None
    OUTPUT_DIR = _os_paths.path.join(str(BASE_DIR), "outputs")
    ICON_PATH = _os_paths.path.join(str(BASE_DIR), "icon.ico")

import os as _os_paths_lib


def _resolve_voice_library_dir() -> str:
    """Каталог библиотеки голосов: C:\\XTTS Studio\\library\\<voice>\\normalized.wav

    Приоритет:
      1) LIBRARY_DIR из engine.paths (если существует / задан)
      2) BASE_DIR/library
      3) BACKUP_DIR — только если он уже указывает внутрь .../library
         (не reference/, не reference/backup)
    """
    candidates = []
    if _LIBRARY_DIR:
        candidates.append(str(_LIBRARY_DIR))
    candidates.append(_os_paths_lib.path.join(str(BASE_DIR), "library"))
    if _BACKUP_DIR:
        candidates.append(str(_BACKUP_DIR))

    def _looks_like_library(p: str) -> bool:
        if not p:
            return False
        norm = _os_paths_lib.path.normpath(p).replace("\\", "/").lower()
        # Явно отклоняем старые пути reference/backup
        if (
            "/reference/backup" in norm
            or norm.endswith("/reference")
            or "/reference/" in norm
            and "/library" not in norm
        ):
            return False
        return (
            norm.rstrip("/").endswith("/library")
            or "/library/" in norm
            or _os_paths_lib.path.basename(norm) == "library"
        )

    for c in candidates:
        if _looks_like_library(c):
            return c
    # Жёсткий дефолт — всегда library рядом с приложением
    return _os_paths_lib.path.join(str(BASE_DIR), "library")


LIBRARY_DIR = _resolve_voice_library_dir()
# BACKUP_DIR оставляем как алиас на library для старого кода (player.pick_backup_reference и т.п.)
BACKUP_DIR = LIBRARY_DIR
from engine.voice_manager import VoiceManager
from engine.task_manager import TaskManager
from engine.settings_store import load_settings
from engine import audio_backend
from engine import updater

from engine.gui.theme import apply_theme, set_dark_titlebar
from engine.gui.colors import Colors
from engine.gui.layout import build_layout
from engine.gui import (
    helpers,
    statusbar,
    console,
    textbox,
    player,
    voice_panel,
    queue_panel,
    history_window,
    output_window,
    dialogs,
    presets,
    settings_ui,
    ai_status_window,
    env_settings,
    header_panel,
    ai_conductor,
    styles_menu,
    generation,
    chat_panel,
    batch_panel,
    word_replacer_panel,
    toolbar,
)

# Layout preset support
from engine.gui import theme_manager
from engine.gui.layout import apply_layout_preset as layout_apply_preset

root = None
task_manager = None
voice_manager = None
quality_params = None
_current_layout_preset = {}


def apply_layout_preset_to_all(preset: dict):
    """Live-применение пресета ко всем панелям.
    Вызывается из Конструктора темы.
    Возвращает True если что-то применилось.
    """
    global _current_layout_preset
    _current_layout_preset = preset.copy()
    applied = False

    # 0. Боковая панель: сторона
    try:
        from engine.gui.layout import apply_sidebar_side

        side = theme_manager.get_sidebar_side()
        if apply_sidebar_side(side):
            applied = True
    except Exception:
        pass

    # 0b. Порядок тулбара
    try:
        order = theme_manager.get_toolbar_order()
        if hasattr(toolbar, "apply_toolbar_order"):
            res = toolbar.apply_toolbar_order(order)
            # res True означает что live-apply сработал (или нужен перезапуск — тоже считаем applied)
            if res:
                applied = True
    except Exception:
        pass

    # 1. layout.py (toggle_strip и т.п.)
    try:
        if layout_apply_preset(preset):
            applied = True
    except Exception:
        pass

    # 2. Проходим по всем GUI-модулям, если у них есть apply_layout()
    for mod in (
        header_panel,
        voice_panel,
        player,
        queue_panel,
        console,
        textbox,
        toolbar,
        statusbar,
    ):
        func = getattr(mod, "apply_layout", None)
        if callable(func):
            try:
                if func(preset):
                    applied = True
            except Exception:
                pass

    try:
        if root:
            root.update_idletasks()
    except Exception:
        pass
    return applied


def open_theme_settings_dialog():
    """Открывает Конструктор темы с callback live-apply."""
    try:
        from engine.gui.chat_window.theme_settings import open_theme_customizer

        open_theme_customizer(root, on_layout_changed=apply_layout_preset_to_all)
    except Exception:
        # ИЗМЕНЕНО (по просьбе пользователя): трейсбек больше не печатается
        # в консоль приложения — раньше это было временно добавлено для
        # диагностики бага открытия окна конструктора темы (уже найден и
        # исправлен). Ошибка по-прежнему тихо пишется в лог-файл через
        # write_log(), чтобы при реальном сбое информация не терялась
        # полностью, но не засоряла консоль на каждый клик.
        import traceback

        try:
            from engine.logging_utils import write_log

            write_log(traceback.format_exc())
        except Exception:
            pass


def create_main_window(startup_status: str = None):
    """Создаёт и полностью собирает главное окно. Возвращает root
    (mainloop() запускает вызывающая сторона — gui.py).

    startup_status — результат updater.check_startup_health(), переданный
    из gui.py ДО создания окна:
      "rolled_back"   — прошлый запуск после обновления не подтвердился,
                        файлы уже автоматически откачены на предыдущую
                        версию; пользователю нужно показать уведомление
      "first_attempt" — первый запуск после применения обновления
      "ok" / None     — обновления не применялись, ничего особенного
    """
    global root, task_manager, voice_manager, quality_params, _current_layout_preset

    # ── CUSTOMTKINTER THEME (как в gui.py: до создания root) ──
    apply_theme()

    # ── THEME MANAGER: загрузка темы + layout пресета ──
    try:
        theme_manager.load_theme()
        _current_layout_preset = theme_manager.load_layout_preset()
    except Exception:
        _current_layout_preset = {}

    # ── ROOT (перенесено из gui.py, секция ROOT) ──
    root = TkinterDnD.Tk()
    set_dark_titlebar(root)
    try:
        import os as _os

        if _os.path.isfile(ICON_PATH):
            root.iconbitmap(default=ICON_PATH)
    except Exception as e:
        print(f"[ICON ERROR] {e}")
    root.title("XTTS Studio")
    root.geometry("1160x820")
    root.minsize(920, 680)
    root.configure(bg=Colors.BG_DARK)

    # ── LAYOUT (градиент + панели) ──
    # Передаём пресет раскладки вместо хардкода
    try:
        sidebar_side = theme_manager.get_sidebar_side()
    except Exception:
        sidebar_side = "left"
    main_container, left_panel, right_panel = build_layout(
        root, preset=_current_layout_preset, sidebar_side=sidebar_side
    )

    # ── CONSOLE REDIRECT (как в gui.py: сразу после layout) ──
    console.install()

    # ── PYGAME ──
    audio_backend.init_audio()
    PYGAME_OK = audio_backend.PYGAME_OK

    # ── STATE (перенесено из gui.py, секция STATE) ──
    _textbox_updated = threading.Event()
    word_replacer_enabled = tk.BooleanVar(value=True)
    lang_split_enabled = tk.BooleanVar(value=True)
    ref_var = tk.StringVar()
    status_var = tk.StringVar(value=t("status_init"))
    stage_var = tk.StringVar(value="STARTUP")
    progress_value = tk.IntVar(value=0)
    console_visible = tk.BooleanVar(value=True)
    lang_var = tk.StringVar(value="auto")
    quality_var = tk.StringVar(value="Высокое качество")
    use_gpt = tk.BooleanVar(value=False)
    # UI language variable (stored in settings.json)
    ui_lang_var = tk.StringVar(value="ru")

    #  Библиотека голосов: library/<name>/normalized.wav (+ embedding cache рядом)
    # НЕ reference/backup — туда раньше ошибочно смотрел VoiceManager.
    voice_manager = VoiceManager(LIBRARY_DIR)
    try:
        # если VoiceManager умеет принимать явный library_dir / backup_dir
        if hasattr(voice_manager, "library_dir"):
            voice_manager.library_dir = LIBRARY_DIR
        if hasattr(voice_manager, "backup_dir"):
            # не даём legacy-полю утянуть скан в reference/
            voice_manager.backup_dir = LIBRARY_DIR
    except Exception:
        pass
    voice_manager.scan_voices()

    # ── ВНЕДРЕНИЕ ЗАВИСИМОСТЕЙ (порядок: сначала базовые модули) ──
    helpers.init(root=root)
    clean_path = helpers.clean_path

    statusbar.init(
        root=root, status_var=status_var, stage_var=stage_var, progress_value=progress_value
    )
    console.init(root=root, console_visible=console_visible)
    player.init(
        root=root,
        PYGAME_OK=PYGAME_OK,
        ref_var=ref_var,
        clean_path=clean_path,
        LIBRARY_DIR=LIBRARY_DIR,
        BACKUP_DIR=BACKUP_DIR,
    )
    voice_panel.init(
        root=root,
        PYGAME_OK=PYGAME_OK,
        ref_var=ref_var,
        voice_manager=voice_manager,
        LIBRARY_DIR=LIBRARY_DIR,
    )
    history_window.init(root=root, PYGAME_OK=PYGAME_OK)
    output_window.init(root=root, PYGAME_OK=PYGAME_OK)
    ai_status_window.init(root=root)
    env_settings.init(root=root)
    # Передаём в textbox callback открытия конструктора темы + текущий layout_preset
    textbox.init(
        root=root,
        use_gpt=use_gpt,
        textbox_updated=_textbox_updated,
        clean_path=clean_path,
        show_help=dialogs.show_help,
        on_open_theme_settings=open_theme_settings_dialog,
        layout_preset=_current_layout_preset,
    )

    # ── QUALITY PARAMS (перенесено из gui.py, секция QUALITY PARAMS) ──
    presets.init(root=root, use_gpt=use_gpt)
    quality_params = presets.build_quality_params()

    # ── SETTINGS (save/apply) ──
    settings_ui.init(
        lang_var=lang_var,
        quality_var=quality_var,
        ref_var=ref_var,
        use_gpt=use_gpt,
        word_replacer_enabled=word_replacer_enabled,
        lang_split_enabled=lang_split_enabled,
        ui_lang_var=ui_lang_var,
        quality_params=quality_params,
    )
    save_settings = settings_ui.save_settings

    presets.init(save_settings=save_settings)
    dialogs.init(
        root=root,
        lang_var=lang_var,
        lang_split_enabled=lang_split_enabled,
        save_settings=save_settings,
    )
    header_panel.init(root=root, ui_lang_var=ui_lang_var, save_settings=save_settings)
    ai_conductor.init(root=root, quality_params=quality_params, save_settings=save_settings)
    styles_menu.init(
        root=root,
        quality_var=quality_var,
        save_settings=save_settings,
        PRESET_DESCRIPTIONS=presets.PRESET_DESCRIPTIONS,
    )
    toolbar.init(root=root, quality_var=quality_var, lang_var=lang_var, save_settings=save_settings)

    # ── TASK MANAGER (перенесено из gui.py, секция TASK MANAGER) ──
    task_manager = TaskManager(ui_callback=generation.on_task_update)
    task_manager.start()

    queue_panel.init(root=root, task_manager=task_manager)
    generation.init(
        root=root,
        PYGAME_OK=PYGAME_OK,
        ref_var=ref_var,
        lang_var=lang_var,
        quality_var=quality_var,
        word_replacer_enabled=word_replacer_enabled,
        lang_split_enabled=lang_split_enabled,
        use_gpt=use_gpt,
        _textbox_updated=_textbox_updated,
        clean_path=clean_path,
        task_manager=task_manager,
        quality_params=quality_params,
        save_settings=save_settings,
        set_ai_pulse=ai_conductor.set_ai_pulse,
        update_queue_view=queue_panel.update_queue_view,
        refresh_voice_list=voice_panel.refresh_voice_list,
    )

    # ── CHAT / BATCH / WORD REPLACER — делегирование (как в gui.py) ──
    chat_panel.setup(root, use_gpt)
    batch_panel.setup(
        root,
        OUTPUT_DIR,
        task_manager,
        ref_var,
        quality_var,
        quality_params,
        word_replacer_enabled,
        lang_split_enabled,
        use_gpt,
        lang_var,
    )
    word_replacer_panel.setup(root, word_replacer_enabled, save_settings)

    # ── LEFT PANEL (порядок как в gui.py) ──
    # Если модули поддерживают apply_layout — применяем пресет до build
    for mod in (header_panel, voice_panel, queue_panel, console):
        func = getattr(mod, "apply_layout", None)
        if callable(func):
            try:
                func(_current_layout_preset)
            except Exception:
                pass

    header_panel.build_header(left_panel)
    voice_panel.build_voice_cards(left_panel)
    queue_panel.build_queue_card(left_panel)
    console.build_console_card(left_panel, queue_panel.queue_card)
    # Spacer
    tk.Frame(left_panel, bg=Colors.BG_DARK).pack(fill="both", expand=True)

    # ── RIGHT PANEL (порядок как в gui.py) ──
    # Статусбар строится ПЕРВЫМ (side="bottom"): при нехватке высоты pack
    # обрезает виджеты, упакованные последними, — так текст статуса
    # («Инициализация модели…» и т.п.) больше не «съедается» окном.
    # Применяем layout к правым панелям
    for mod in (statusbar, textbox, toolbar):
        func = getattr(mod, "apply_layout", None)
        if callable(func):
            try:
                func(_current_layout_preset)
            except Exception:
                pass

    statusbar.build_statusbar(right_panel)
    textbox.build_text_card(right_panel)
    toolbar.build_toolbar(textbox.text_card)

    # виджеты/функции, ставшие доступными после сборки интерфейса
    generation.init(text_box=textbox.text_box, update_gen_btn=toolbar.update_gen_btn)

    # ── LAUNCH (перенесено из gui.py, секция LAUNCH) ──
    def on_closing():
        try:
            if task_manager:
                try:
                    task_manager.stop()
                except Exception:
                    pass
            if PYGAME_OK:
                try:
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.music.stop()
                    pygame.mixer.quit()
                except Exception:
                    pass
            root.quit()
            root.destroy()
        except Exception:
            pass

    root.protocol("WM_DELETE_WINDOW", on_closing)
    # Apply saved settings (including UI language)
    _saved = load_settings()
    if "ui_language" in _saved and _saved["ui_language"] in LANGUAGES:
        set_language(_saved["ui_language"])
        ui_lang_var.set(_saved["ui_language"])
    settings_ui.apply_settings(_saved)
    for _var in (
        lang_var,
        quality_var,
        ref_var,
        use_gpt,
        word_replacer_enabled,
        lang_split_enabled,
    ):
        try:
            _var.trace_add("write", lambda *a: save_settings())
        except Exception:
            pass
    voice_panel.refresh_voice_list()
    queue_panel.queue_autorefresh()
    root.update_idletasks()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, (sw - 1000) // 2)
    y = max(0, (sh - 820) // 2)
    root.geometry(f"1160x820+{x}+{y}")
    root.after(150, generation.start_preload_thread)
    threading.Thread(target=env_settings._auto_check_update, daemon=True).start()

    # ── ПОДТВЕРЖДЕНИЕ ОБНОВЛЕНИЯ ──
    # Мы дошли до этой точки без исключений — интерфейс собран полностью.
    # Если до этого было применено обновление, помечаем его успешным,
    # иначе при следующем запуске сработает ложный откат.
    try:
        updater.confirm_update_success()
    except Exception:
        pass

    if startup_status == "rolled_back":
        # Не используем Toplevel/messagebox (см. известный конфликт
        # grab_set при вложенных модальных окнах) — показываем через
        # статус-бар и консоль, как более безопасный inline-вариант.
        try:
            status_var.set(t("status_update_rolled_back"))
        except Exception:
            pass
        try:
            print(
                "[Updater] Прошлый запуск после обновления не подтвердился. "
                "Файлы откачены на предыдущую версию."
            )
        except Exception:
            pass

    return root


# Совместимый псевдоним в духе «from engine.gui.main_window import MainWindow»
MainWindow = create_main_window
