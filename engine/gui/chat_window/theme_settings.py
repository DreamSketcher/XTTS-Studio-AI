from __future__ import annotations
import tkinter as tk
from tkinter import colorchooser, ttk, messagebox
import engine.gui.chat_window.state as state
from engine.gui.chat_window.custom_widgets import TkFrame, TkLabel, TkButton
from engine.gui.chat_window.ui_utils import _make_button, _set_dark_titlebar
from engine.gui.theme_manager import (
    load_theme,
    save_theme,
    get_layout_preset,
    get_custom_colors,
    set_custom_colors,
    reset_custom_colors,
    get_font_base_size,
    set_font_base_size as tm_set_font_base_size,
    get_saved_presets,
    save_named_preset,
    delete_named_preset,
    apply_named_preset,
    get_sidebar_side,
    set_sidebar_side,
    get_toolbar_order,
    set_toolbar_order,
    TOOLBAR_PANELS,
    DEFAULT_TOOLBAR_ORDER,
    get_header_rainbow,
    set_header_rainbow,
    get_header_rainbow_style,
    set_header_rainbow_style,
    reset_header_rainbow_style,
    get_header_author_rainbow,
    set_header_author_rainbow,
    get_header_author_rainbow_style,
    set_header_author_rainbow_style,
    reset_header_author_rainbow_style,
    DEFAULT_HEADER_RAINBOW_STYLE,
    DEFAULT_HEADER_AUTHOR_RAINBOW_STYLE,
    get_neon_buttons,
    set_neon_buttons,
    NEON_BUTTON_IDS,
)
from engine.gui.colors import (
    Colors,
    DARK_PALETTE,
    LIGHT_PALETTE,
    apply_palette,
    set_font_base_size as rt_set_font_base_size,
    scaled_font_size,
    BASE_FONT_SIZE_DEFAULT,
)
from engine.gui.theme import get_theme, set_theme
from i18n import t


# ПРИМЕЧАНИЕ (фикс): custom_widgets.py не экспортирует функцию "_c" —
# её здесь никогда не было (ImportError на реальной машине пользователя
# подтвердил это). Palette-lookup по имени цвета уже реализован во всех
# остальных панелях проекта через engine.gui.colors.Colors (единственный
# источник палитр DARK/LIGHT), поэтому определяем "_c" локально как
# обёртку над Colors — без изменения общего custom_widgets.py.
def _c(name: str) -> str:
    """Возвращает значение цвета по имени атрибута Colors (например
    _c("BG_CARD") -> Colors.BG_CARD). Fallback на белый, если атрибута
    нет — чтобы окно конструктора темы не падало из-за опечатки в имени."""
    return getattr(Colors, name, "#ffffff")


# ── Человекочитаемые русские названия РЕАЛЬНЫХ атрибутов Colors ──
# ИСПРАВЛЕНО (важно): раньше здесь редактировались 11 ключей из легаси-
# секции theme_settings.json["colors"] (BG_MAIN, ACCENT_DARK, SUCCESS...),
# которые физически НЕ СУЩЕСТВОВАЛИ как атрибуты engine.gui.colors.Colors —
# редактирование в конструкторе темы сохранялось в JSON, но никогда не
# применялось к реальному виду приложения (см. подробный комментарий в
# engine/gui/theme_manager.py DEFAULT_THEME). Теперь список ниже — это
# ВСЕ 29 настоящих ключей DARK_PALETTE/LIGHT_PALETTE из colors.py,
# сгруппированные по смыслу для удобства. Правки реально применяются через
# theme_manager.set_custom_colors() -> colors.apply_palette() (см. ниже).
COLOR_LABELS_RU = {
    "BG_DARK": "Фон окна",
    "BG_CARD": "Фон карточек",
    "BG_INPUT": "Фон полей ввода",
    "BG_HOVER": "Фон при наведении",
    "BG_ACTIVE": "Кнопка «Генерировать»",
    "BG_DANGER": "Кнопка «Отмена/Стоп»",
    "TEXT_MAIN": "Текст основной",
    "TEXT_DIM": "Текст приглушённый",
    "TEXT_SUCCESS": "Текст успеха",
    "TEXT_WARNING": "Текст предупреждения",
    "TEXT_ERROR": "Текст ошибки",
    "ACCENT": "Акцентный цвет",
    "BORDER": "Цвет границ",
    "PROGRESS_BG": "Прогресс-бар (фон)",
    "PROGRESS_FG": "Прогресс-бар (шкала)",
    "CHUNK_BG": "Подсветка чанка (фон)",
    "CHUNK_FG": "Подсветка чанка (текст)",
    "TOOLTIP_BG": "Фон подсказки",
    "MENU_BG": "Фон меню",
    "MENU_HOVER": "Меню — наведение",
    "MENU_ACTIVE": "Меню — активный пункт",
    "AI_ACCENT": "AI — акцент",
    "AI_ACCENT_HOVER": "AI — акцент (hover)",
    "AI_GROUP_BG": "AI — фон в тулбаре",
    "GROUP_BG": "Тулбар — фон группы",
    "GROUP_FILE_BG": "Группа «Файл»",
    "GROUP_OUTPUT_BG": "Группа «Вывод»",
    "GROUP_ACTION_BG": "Группа «Действие»",
    "GRADIENT_BOTTOM": "Градиент фона (низ)",
}

# Группировка ключей цвета для отображения в конструкторе темы — просто
# порядок и заголовки секций, на данные никак не влияет.
COLOR_GROUPS_RU = [
    ("Фоны", ["BG_DARK", "BG_CARD", "BG_INPUT", "BG_HOVER", "BG_ACTIVE", "BG_DANGER"]),
    ("Текст", ["TEXT_MAIN", "TEXT_DIM", "TEXT_SUCCESS", "TEXT_WARNING", "TEXT_ERROR"]),
    ("Акцент и границы", ["ACCENT", "BORDER"]),
    ("Прогресс-бар", ["PROGRESS_BG", "PROGRESS_FG"]),
    ("Подсветка текста при генерации", ["CHUNK_BG", "CHUNK_FG"]),
    ("Подсказки и меню", ["TOOLTIP_BG", "MENU_BG", "MENU_HOVER", "MENU_ACTIVE"]),
    ("AI-функции", ["AI_ACCENT", "AI_ACCENT_HOVER", "AI_GROUP_BG"]),
    ("Тулбар — группы кнопок", ["GROUP_BG", "GROUP_FILE_BG", "GROUP_OUTPUT_BG", "GROUP_ACTION_BG"]),
    ("Градиент фона", ["GRADIENT_BOTTOM"]),
]


def _color_label(color_name: str) -> str:
    """Человекочитаемая подпись для технического имени цвета.
    Сначала i18n (через _tr), затем legacy COLOR_LABELS_RU, иначе ключ."""
    i18n_key = _COLOR_I18N_KEYS.get(color_name)
    if i18n_key:
        return _tr(i18n_key)
    return COLOR_LABELS_RU.get(color_name, color_name)


# ── Fallback-переводы для окна конструктора темы ──
# ВАЖНО: на реальной машине пользователя t() НЕ бросает исключение на
# отсутствующий ключ — она возвращает сам ключ "как есть" (это видно на
# скриншоте: заголовок окна показывал буквально "theme_custom_title" и
# т.п.). Значит, эти ключи просто не добавлены в файлы локализации проекта.
# _tr() ниже — временное решение: пробует t(key), и если результат совпал
# с самим ключом (перевод не найден), подставляет русский текст-заглушку.
# Как только в i18n добавят настоящие переводы для этих ключей — _tr()
# автоматически начнёт возвращать их вместо заглушки, ничего менять не
# придётся.
THEME_UI_FALLBACKS_RU = {
    "theme_custom_title": "Конструктор темы",
    "theme_custom_desc": "Настройте внешний вид и раскладку интерфейса",
    "theme_font_label": "Шрифт интерфейса:",
    "theme_font_size": "Размер шрифта:",
    "theme_padding_label": "Внутренние отступы:",
    "theme_layout_label": "Раскладка интерфейса",
    "theme_layout_classic": "Классическая",
    "theme_layout_compact": "Компактная",
    "theme_layout_wide": "Широкая",
    "theme_reset_btn": "Отмена",
    "theme_save_btn": "Сохранить",
    # ── Colors / typography / layout / presets (зеркало i18n) ──
    "theme_colors_section_title": "Цвета интерфейса — тема «{}»",
    "theme_name_dark": "тёмная",
    "theme_name_light": "светлая",
    "theme_colors_switch_hint": (
        "Переключите тему (☀/🌙 в главном окне) перед открытием этого\n"
        "окна, чтобы настроить цвета другой темы — они хранятся раздельно."
    ),
    "theme_colors_reset_btn": "↺ Сбросить цвета этой темы к стандартным",
    "theme_group_backgrounds": "Фоны",
    "theme_group_text": "Текст",
    "theme_group_accent_border": "Акцент и границы",
    "theme_group_progress": "Прогресс-бар",
    "theme_group_chunk_highlight": "Подсветка текста при генерации",
    "theme_group_tooltips_menus": "Подсказки и меню",
    "theme_group_ai": "AI-функции",
    "theme_group_toolbar": "Тулбар — группы кнопок",
    "theme_group_gradient": "Градиент фона",
    "theme_color_bg_dark": "Фон окна",
    "theme_color_bg_card": "Фон карточек",
    "theme_color_bg_input": "Фон полей ввода",
    "theme_color_bg_hover": "Фон при наведении",
    "theme_color_bg_active": "Кнопка «Генерировать»",
    "theme_color_bg_danger": "Кнопка «Отмена/Стоп»",
    "theme_color_text_main": "Текст основной",
    "theme_color_text_dim": "Текст приглушённый",
    "theme_color_text_success": "Текст успеха",
    "theme_color_text_warning": "Текст предупреждения",
    "theme_color_text_error": "Текст ошибки",
    "theme_color_accent": "Акцентный цвет",
    "theme_color_border": "Цвет границ",
    "theme_color_progress_bg": "Прогресс-бар (фон)",
    "theme_color_progress_fg": "Прогресс-бар (шкала)",
    "theme_color_chunk_bg": "Подсветка чанка (фон)",
    "theme_color_chunk_fg": "Подсветка чанка (текст)",
    "theme_color_tooltip_bg": "Фон подсказки",
    "theme_color_menu_bg": "Фон меню",
    "theme_color_menu_hover": "Меню — наведение",
    "theme_color_menu_active": "Меню — активный пункт",
    "theme_color_ai_accent": "AI — акцент",
    "theme_color_ai_accent_hover": "AI — акцент (hover)",
    "theme_color_ai_group_bg": "AI — фон в тулбаре",
    "theme_color_group_bg": "Тулбар — фон группы",
    "theme_color_group_file_bg": "Группа «Файл»",
    "theme_color_group_output_bg": "Группа «Вывод»",
    "theme_color_group_action_bg": "Группа «Действие»",
    "theme_color_gradient_bottom": "Градиент фона (низ)",
    "theme_font_section_title": "Размер шрифта интерфейса",
    "theme_font_section_desc": (
        "Меняет размер текста во всём приложении (кнопки, подписи,\n"
        "консоль, окна). НЕ влияет на текстовое поле ввода — там\n"
        "отдельный размер шрифта (кнопка «Aa» рядом с полем ввода)."
    ),
    "theme_layout_restart_note": (
        "Большинство параметров раскладки применяется сразу.\n"
        "Число рядов тулбара (Compact ⇄ Classic/Wide) вступит в силу\n"
        "только после перезапуска приложения."
    ),
    "theme_sidebar_label": "Боковая панель:",
    "theme_sidebar_left": "Слева",
    "theme_sidebar_right": "Справа",
    "theme_sidebar_apply_note": "Изменение применяется сразу после сохранения.",
    "theme_toolbar_order_label": "Порядок панелей под окном ввода:",
    "theme_toolbar_panel_file": "📁 Файл",
    "theme_toolbar_panel_ai": "🤖 AI",
    "theme_toolbar_panel_output": "🎛 Вывод",
    "theme_toolbar_panel_action": "⚡ Действие",
    "theme_toolbar_move_up": "▲ Вверх",
    "theme_toolbar_move_down": "▼ Вниз",
    "theme_toolbar_reset_order": "↺ Сброс",
    "theme_toolbar_order_hint": (
        "Перетащите порядок стрелками. Изменения применятся после сохранения.\n"
        "Если порядок требует смены ряда — может понадобиться перезапуск."
    ),
    "theme_header_effects_label": "Неоновые эффекты:",
    "theme_header_rainbow": "Неоновый заголовок «XTTS Studio»",
    "theme_header_rainbow_desc": (
        "Неоновое свечение и перелив цвета на тексте заголовка.\n"
        "Кадры предгенерированы — нагрузка на CPU минимальна."
    ),
    "theme_header_rainbow_speed": "Скорость анимации:",
    "theme_header_rainbow_speed_fast": "Быстро",
    "theme_header_rainbow_speed_normal": "Нормально",
    "theme_header_rainbow_speed_slow": "Медленно",
    "theme_header_rainbow_saturation": "Насыщенность:",
    "theme_header_rainbow_brightness": "Яркость:",
    "theme_header_rainbow_hue": "Сдвиг цвета (hue):",
    "theme_header_rainbow_spread": "Длина неона:",
    "theme_header_rainbow_reset_style": "↺ Сбросить неоновые параметры",
    "theme_header_rainbow_style_hint": (
        "Параметры применяются после «Сохранить»\n"
        "(неоновый заголовок пересоберётся с новыми настройками)."
    ),
    "theme_header_rainbow_cfg_btn": "⚙",
    "theme_header_rainbow_panel_title": "Настройки неона",
    "theme_header_rainbow_target_title": "Заголовок «XTTS Studio»",
    "theme_header_rainbow_target_author": "Подпись «by EXIZ10TION»",
    "theme_header_author_rainbow": "Неоновая подпись «by EXIZ10TION»",
    "theme_header_rainbow_mode": "Режим цвета:",
    "theme_header_rainbow_mode_hsv": "Неон (HSV)",
    "theme_header_rainbow_mode_custom": "Свои цвета",
    "theme_header_rainbow_colors": "Неоновая палитра",
    "theme_header_rainbow_add_color": "＋ Цвет",
    "theme_header_rainbow_clear_colors": "Очистить",
    "theme_header_rainbow_colors_hint": "Минимум 2 цвета. Неоновый градиент бежит по палитре.",
    "theme_header_rainbow_collapse": "Свернуть",
    "theme_neon_btn_chat": "AI Помощник",
    "theme_neon_btn_ai": "AI (кондуктор)",
    "theme_neon_btn_styles": "Стили",
    "theme_neon_btn_quality": "Высокое качество",
    "theme_neon_btn_generate": "Генерировать",
    "theme_neon_target_enabled": "Включить неон",
    "theme_neon_buttons_section": "Неоновые кнопки тулбара",
    "theme_presets_section_title": "Пресеты темы",
    "theme_presets_section_desc": (
        "Пресет сохраняет цвета текущей темы, размер шрифта и\n"
        "раскладку одним именем — чтобы быстро переключаться между\n"
        "готовыми настройками."
    ),
    "theme_presets_apply_btn": "Применить",
    "theme_presets_delete_btn": "Удалить",
    "theme_presets_new_name_label": "Имя нового пресета:",
    "theme_presets_save_btn": "Сохранить как пресет",
    "theme_presets_reset_all_btn": "↺ Сбросить ВСЁ (цвета + шрифт + раскладка) к заводским",
    "theme_presets_dlg_title": "Пресеты",
    "theme_presets_select_first": "Сначала выберите пресет из списка.",
    "theme_presets_not_found": "Пресет «{}» не найден.",
    "theme_presets_applied_other_theme": (
        "Пресет «{}» был сохранён для {} темы.\n"
        "Он применён, но чтобы увидеть цвета — переключите тему (☀/🌙)\n"
        "и откройте конструктор темы заново."
    ),
    "theme_presets_applied": (
        "Пресет «{}» применён. Откройте конструктор\n"
        "темы заново, чтобы увидеть все изменения в полях."
    ),
    "theme_presets_delete_confirm": "Удалить пресет «{}»?",
    "theme_presets_enter_name": "Введите имя пресета.",
    "theme_presets_overwrite_confirm": "Пресет «{}» уже существует.\nПерезаписать его?",
    "theme_presets_saved": "Пресет «{}» сохранён.",
    "theme_reset_all_dlg_title": "Сброс настроек",
    "theme_reset_all_confirm": (
        "Сбросить ВСЕ настройки темы (цвета, размер шрифта, раскладку)\n"
        "к заводским значениям? Сохранённые именованные пресеты не\n"
        "будут удалены."
    ),
    "theme_reset_all_done": (
        "Поля сброшены к заводским значениям.\n" "Нажмите «Сохранить», чтобы применить."
    ),
    "theme_saved_dlg_title": "Тема",
    "theme_saved_live_applied": (
        "Настройки сохранены. Цвета и размер шрифта применены сразу\n"
        "к этому окну и новым виджетам (остальные открытые окна и\n"
        "число рядов тулбара обновятся после их следующего открытия\n"
        "или перезапуска приложения)."
    ),
    "theme_saved_needs_restart": (
        "Настройки сохранены! Цвета и размер шрифта применятся ко\n"
        "всем окнам при следующем открытии, полностью — после\n"
        "перезапуска приложения."
    ),
}


def _tr(key: str, *args) -> str:
    """Перевод с fallback на русский текст, если t(key) вернула ключ
    без изменений (перевод отсутствует в i18n) — см. пояснение выше.
    *args: подстановки для строк с placeholders «{}» (как в i18n.t)."""
    try:
        value = t(key, *args) if args else t(key)
    except Exception:
        value = key
    # t() при отсутствии ключа возвращает сам key (без format) — см. i18n.t
    if value == key:
        fb = THEME_UI_FALLBACKS_RU.get(key, key)
        if args:
            try:
                return fb.format(*args)
            except Exception:
                return fb
        return fb
    return value


# Маппинг технического имени Colors -> i18n-ключ подписи
_COLOR_I18N_KEYS = {
    "BG_DARK": "theme_color_bg_dark",
    "BG_CARD": "theme_color_bg_card",
    "BG_INPUT": "theme_color_bg_input",
    "BG_HOVER": "theme_color_bg_hover",
    "BG_ACTIVE": "theme_color_bg_active",
    "BG_DANGER": "theme_color_bg_danger",
    "TEXT_MAIN": "theme_color_text_main",
    "TEXT_DIM": "theme_color_text_dim",
    "TEXT_SUCCESS": "theme_color_text_success",
    "TEXT_WARNING": "theme_color_text_warning",
    "TEXT_ERROR": "theme_color_text_error",
    "ACCENT": "theme_color_accent",
    "BORDER": "theme_color_border",
    "PROGRESS_BG": "theme_color_progress_bg",
    "PROGRESS_FG": "theme_color_progress_fg",
    "CHUNK_BG": "theme_color_chunk_bg",
    "CHUNK_FG": "theme_color_chunk_fg",
    "TOOLTIP_BG": "theme_color_tooltip_bg",
    "MENU_BG": "theme_color_menu_bg",
    "MENU_HOVER": "theme_color_menu_hover",
    "MENU_ACTIVE": "theme_color_menu_active",
    "AI_ACCENT": "theme_color_ai_accent",
    "AI_ACCENT_HOVER": "theme_color_ai_accent_hover",
    "AI_GROUP_BG": "theme_color_ai_group_bg",
    "GROUP_BG": "theme_color_group_bg",
    "GROUP_FILE_BG": "theme_color_group_file_bg",
    "GROUP_OUTPUT_BG": "theme_color_group_output_bg",
    "GROUP_ACTION_BG": "theme_color_group_action_bg",
    "GRADIENT_BOTTOM": "theme_color_gradient_bottom",
}

_COLOR_GROUP_I18N = [
    (
        "theme_group_backgrounds",
        ["BG_DARK", "BG_CARD", "BG_INPUT", "BG_HOVER", "BG_ACTIVE", "BG_DANGER"],
    ),
    ("theme_group_text", ["TEXT_MAIN", "TEXT_DIM", "TEXT_SUCCESS", "TEXT_WARNING", "TEXT_ERROR"]),
    ("theme_group_accent_border", ["ACCENT", "BORDER"]),
    ("theme_group_progress", ["PROGRESS_BG", "PROGRESS_FG"]),
    ("theme_group_chunk_highlight", ["CHUNK_BG", "CHUNK_FG"]),
    ("theme_group_tooltips_menus", ["TOOLTIP_BG", "MENU_BG", "MENU_HOVER", "MENU_ACTIVE"]),
    ("theme_group_ai", ["AI_ACCENT", "AI_ACCENT_HOVER", "AI_GROUP_BG"]),
    ("theme_group_toolbar", ["GROUP_BG", "GROUP_FILE_BG", "GROUP_OUTPUT_BG", "GROUP_ACTION_BG"]),
    ("theme_group_gradient", ["GRADIENT_BOTTOM"]),
]


# ── Singleton: не открывать несколько «Конструктор темы» подряд ──
_THEME_CUSTOMIZER_WIN = {"win": None}


def _theme_customizer_is_open() -> bool:
    w = _THEME_CUSTOMIZER_WIN.get("win")
    if w is None:
        return False
    try:
        return bool(w.winfo_exists())
    except Exception:
        return False


def open_theme_customizer(parent, on_layout_changed=None):
    """Открывает окно расширенной настройки темы.

    on_layout_changed: необязательный callback(preset: dict) -> bool,
    вызывается при сохранении для live-применения пресета раскладки ко
    всем панелям (см. main_window.apply_layout_preset_to_all). Если не
    передан или бросает исключение — просто сохраняем в JSON, полное
    применение произойдёт при следующем запуске приложения.

    Защита от дублей: повторный вызов поднимает уже открытое окно
    вместо создания второго Toplevel.
    """
    # ── Не плодим окна ──
    if _theme_customizer_is_open():
        w = _THEME_CUSTOMIZER_WIN["win"]
        try:
            w.deiconify()
            w.lift()
            w.focus_force()
            try:
                w.attributes("-topmost", True)
                w.after(80, lambda: w.attributes("-topmost", False))
            except Exception:
                pass
        except Exception:
            _THEME_CUSTOMIZER_WIN["win"] = None
        else:
            return

    win = tk.Toplevel(parent)
    _THEME_CUSTOMIZER_WIN["win"] = win
    _set_dark_titlebar(win)
    win.title(_tr("theme_custom_title"))
    # Компактный размер конструктора. grab_set() убран — он блокировал
    # приложение при сбое destroy (окно «не закрывается, ничего нельзя»).
    # modal-поведение сохраняем через transient + lift/focus.
    win.geometry("620x680")
    win.minsize(480, 420)
    win.resizable(True, True)
    win.configure(bg=_c("BG_DARK"))
    try:
        win.transient(parent)
    except Exception:
        pass
    try:
        win.lift()
        win.focus_force()
    except Exception:
        pass

    current_theme = load_theme()

    # Главный контейнер — отступ уменьшен (20 -> 12), чтобы не создавать
    # лишнего "воздуха" по краям всего окна.
    main = TkFrame(win, bg=_c("BG_DARK"))
    main.pack(fill="both", expand=True, padx=12, pady=12)

    TkLabel(
        main,
        text=_tr("theme_custom_desc"),
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 17, "bold"),
    ).pack(anchor="w", pady=(0, 16))

    # Область прокрутки
    canvas = tk.Canvas(main, bg=_c("BG_DARK"), highlightthickness=0)
    scrollbar = ttk.Scrollbar(main, orient="vertical", command=canvas.yview)
    scroll_frame = TkFrame(canvas, bg=_c("BG_DARK"))

    _scroll_window_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

    def _on_scroll_frame_configure(event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event):
        # Растягиваем внутренний scroll_frame по ширине canvas, чтобы дочерние
        # виджеты (fill="x") корректно заполняли всю ширину окна при resize.
        canvas.itemconfig(_scroll_window_id, width=event.width)

    scroll_frame.bind("<Configure>", _on_scroll_frame_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    canvas.configure(yscrollcommand=scrollbar.set)

    # ИСПРАВЛЕНО: canvas/scrollbar здесь больше НЕ упаковываются — иначе они
    # (fill="both", expand=True) забирали всё свободное место в "main" ДО
    # того, как ниже упаковывалась нижняя панель с кнопками "Сохранить"/
    # "Отмена" — из-за этого кнопки сжимались в узкую полоску в углу окна
    # (см. скриншот пользователя). Правильный порядок: сначала закрепить
    # btn_row снизу (side="bottom"), и только потом отдать canvas/scrollbar
    # оставшееся пространство. Реальный .pack() для canvas/scrollbar теперь
    # вызывается в самом конце функции, после btn_row.pack(side="bottom").

    # ── Прокрутка колесом мыши (раньше отсутствовала полностью) ──
    # Windows/macOS шлют <MouseWheel> с event.delta (обычно ±120 за "щелчок"),
    # Linux (X11) вместо этого шлёт <Button-4>/<Button-5>. Обрабатываем оба
    # варианта. Биндим только пока курсор над окном конструктора темы
    # (bind при Enter/Leave), чтобы не перехватывать скролл всего приложения.
    _mw_bound = {"v": False}

    def _event_in_win(event) -> bool:
        """Событие относится к этому окну (или его потомкам)?"""
        try:
            w = event.widget
            if w is None:
                return False
            # строковый widget path / actual widget
            if isinstance(w, str):
                return str(w).startswith(str(win))
            return str(w).startswith(str(win)) or w == win or str(win) in str(w)
        except Exception:
            return False

    def _on_mousewheel_windows(event):
        if not _event_in_win(event):
            return
        try:
            if not win.winfo_exists():
                return
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _on_mousewheel_linux_up(event):
        if not _event_in_win(event):
            return
        try:
            canvas.yview_scroll(-1, "units")
        except Exception:
            pass

    def _on_mousewheel_linux_down(event):
        if not _event_in_win(event):
            return
        try:
            canvas.yview_scroll(1, "units")
        except Exception:
            pass

    def _bind_mousewheel(event=None):
        if _mw_bound["v"]:
            return
        try:
            # bind на win, НЕ bind_all — иначе ломается скролл всего приложения
            # и колёсико конфликтует с Scale/палитрой при раскрытой панели перелива.
            win.bind("<MouseWheel>", _on_mousewheel_windows, add="+")
            win.bind("<Button-4>", _on_mousewheel_linux_up, add="+")
            win.bind("<Button-5>", _on_mousewheel_linux_down, add="+")
            # также на canvas/scroll_frame
            canvas.bind("<MouseWheel>", _on_mousewheel_windows, add="+")
            canvas.bind("<Button-4>", _on_mousewheel_linux_up, add="+")
            canvas.bind("<Button-5>", _on_mousewheel_linux_down, add="+")
            scroll_frame.bind("<MouseWheel>", _on_mousewheel_windows, add="+")
            scroll_frame.bind("<Button-4>", _on_mousewheel_linux_up, add="+")
            scroll_frame.bind("<Button-5>", _on_mousewheel_linux_down, add="+")
            _mw_bound["v"] = True
        except Exception:
            pass

    def _unbind_mousewheel(event=None):
        if event is not None:
            try:
                # Destroy всплывает от детей — реагируем ТОЛЬКО на само окно
                if getattr(event, "widget", None) is not win:
                    return
            except Exception:
                pass
        if not _mw_bound["v"]:
            return
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            for w in (win, canvas, scroll_frame):
                try:
                    w.unbind(seq)
                except Exception:
                    pass
        # на всякий случай снять bind_all от старых версий
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            try:
                canvas.unbind_all(seq)
            except Exception:
                pass
        _mw_bound["v"] = False

    def _refresh_scrollregion(event=None):
        try:
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all") or (0, 0, 0, 0))
        except Exception:
            pass

    _bind_mousewheel()
    # Destroy ТОЛЬКО окна (не детей) — снимаем бинды
    win.bind("<Destroy>", _unbind_mousewheel, add="+")

    def _close_theme_window(event=None):
        """Безопасное закрытие: grab_release + unbind + destroy (не зависает UI)."""
        try:
            _unbind_mousewheel()
        except Exception:
            pass
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            if _THEME_CUSTOMIZER_WIN.get("win") is win:
                _THEME_CUSTOMIZER_WIN["win"] = None
        except Exception:
            _THEME_CUSTOMIZER_WIN["win"] = None
        try:
            if win.winfo_exists():
                win.destroy()
        except Exception:
            try:
                win.destroy()
            except Exception:
                pass
        return "break"

    win.protocol("WM_DELETE_WINDOW", _close_theme_window)
    win.bind("<Escape>", _close_theme_window, add="+")

    def _on_win_destroy_clear(event=None):
        try:
            if event is not None and getattr(event, "widget", None) is not win:
                return
        except Exception:
            pass
        if _THEME_CUSTOMIZER_WIN.get("win") is win:
            _THEME_CUSTOMIZER_WIN["win"] = None

    win.bind("<Destroy>", _on_win_destroy_clear, add="+")

    # ── Секция Цветов ─────────────────────────────────────────────────────────
    # ИСПРАВЛЕНО (важно): TkFrame(..., padx=10, pady=12, ...) НЕ работал, если
    # customtkinter установлен — CTkFrame.__init__() в custom_widgets.py
    # принимает padx/pady как параметры, но нигде их не применяет (тихо
    # "проглатывает"), в отличие от bg/highlightbackground (те конвертируются
    # в fg_color/border_color). Из-за этого весь контент секций (подписи
    # цветов, поле ввода имени пресета и т.д.) прижимался почти вплотную к
    # краям рамки — читать было тяжело, поле пресета выглядело "невидимым".
    # Решение: разделяем каждую секцию на ВНЕШНИЙ контейнер (только рамка +
    # фон, без padx/pady) и ВНУТРЕННИЙ (реальный контент), у которого отступ
    # задаётся через .pack(padx=..., pady=...) — pack ВСЕГДА применяет эти
    # параметры, независимо от того, CTkFrame это или обычный tk.Frame.
    # Переменная "colors_group" (и так же ниже для остальных секций)
    # намеренно указывает на ВНУТРЕННИЙ контейнер — все дочерние виджеты
    # ниже по коду не пришлось менять.
    colors_group_outer = TkFrame(
        scroll_frame, bg=_c("BG_CARD"), highlightthickness=1, highlightbackground=_c("BORDER")
    )
    colors_group_outer.pack(fill="x", pady=(0, 12))
    colors_group = TkFrame(colors_group_outer, bg=_c("BG_CARD"))
    colors_group.pack(fill="both", expand=True, padx=14, pady=12)

    # ИСПРАВЛЕНО: раньше здесь редактировались 11 "мёртвых" ключей (см.
    # комментарий у COLOR_LABELS_RU выше) — теперь редактируются РЕАЛЬНЫЕ
    # 29 атрибутов Colors для ТЕКУЩЕЙ активной темы (dark/light). Тема
    # берётся через engine.gui.theme.get_theme() — тот же переключатель
    # ☀/🌙, что и в textbox.py. Каждая тема (dark/light) хранит свои
    # переопределения отдельно (theme_manager.get/set_custom_colors),
    # поэтому настройка цветов в тёмной теме не портит светлую и наоборот.
    _active_theme_name = get_theme()
    _base_palette = DARK_PALETTE if _active_theme_name == "dark" else LIGHT_PALETTE
    _existing_custom = get_custom_colors(_active_theme_name)

    _theme_display_name = _tr(
        "theme_name_dark" if _active_theme_name == "dark" else "theme_name_light"
    )
    TkLabel(
        colors_group,
        text=_tr("theme_colors_section_title", _theme_display_name),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w", pady=(0, 4))
    TkLabel(
        colors_group,
        text=_tr("theme_colors_switch_hint"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        justify="left",
        anchor="w",
    ).pack(anchor="w", pady=(0, 10))

    color_vars = {}
    color_buttons = {}  # {color_name: button} — нужно для _reset_colors_to_default(),
    # чтобы сброс перекрашивал сами кнопки, а не только их StringVar

    def pick_color(name, var, btn):
        color = colorchooser.askcolor(initialcolor=var.get())[1]
        if color:
            var.set(color)
            btn.config(bg=color)

    for group_key, color_names in _COLOR_GROUP_I18N:
        TkLabel(
            colors_group,
            text=_tr(group_key),
            bg=_c("BG_CARD"),
            fg=_c("ACCENT"),
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(8, 4))
        for color_name in color_names:
            # Значение по умолчанию — из встроенной палитры, если
            # пользователь его не переопределял (_existing_custom).
            current_val = _existing_custom.get(color_name, _base_palette.get(color_name, "#ffffff"))
            row = TkFrame(colors_group, bg=_c("BG_CARD"))
            row.pack(fill="x", pady=2)

            var = tk.StringVar(value=current_val)
            color_vars[color_name] = var

            TkLabel(
                row,
                text=_color_label(color_name),
                bg=_c("BG_CARD"),
                fg=_c("TEXT_MAIN"),
                font=("Segoe UI", 11),
                width=24,
                anchor="w",
            ).pack(side="left")

            # Кнопка выбора цвета — сама показывает текущий выбранный цвет
            btn = TkButton(
                row, text=" 🎨 ", bg=current_val, fg="white", width=5, relief="flat", cursor="hand2"
            )
            # ИСПРАВЛЕН ПРЕДСУЩЕСТВОВАВШИЙ БАГ (был в коде ещё до этой
            # правки, просто не был заметен раньше): раньше здесь было
            # `b=btn: pick_color(n, v, btn)` — внутри тела лямбды
            # использовалась свободная переменная "btn" из внешней области
            # видимости (late binding), а не параметр "b" (early binding).
            # Так как переменная "btn" в цикле переопределяется на каждой
            # итерации, к моменту реального клика она уже указывала на
            # ПОСЛЕДНЮЮ созданную кнопку в цикле — клик по любой кнопке,
            # кроме самой последней, перекрашивал не тот цвет. Теперь
            # тело лямбды использует "b" (параметр по умолчанию),
            # который корректно захватывает кнопку именно этой итерации.
            btn.config(command=lambda n=color_name, v=var, b=btn: pick_color(n, v, b))
            btn.pack(side="left", padx=10)
            color_buttons[color_name] = btn

    def _reset_colors_to_default():
        """Сбрасывает ВСЕ цвета текущей темы обратно к встроенной палитре
        (в самих полях формы — реальный сброс в JSON происходит только
        по кнопке 'Сохранить', как и остальные секции этого окна).

        ИСПРАВЛЕНО: раньше здесь обновлялся только var.set(...) — сама
        кнопка-превью цвета (color_buttons[name]) визуально оставалась
        в старом цвете до следующего ручного клика по ней. Теперь
        обновляется и StringVar, и bg самой кнопки."""
        for color_name, var in color_vars.items():
            default_val = _base_palette.get(color_name, "#ffffff")
            var.set(default_val)
            btn_ref = color_buttons.get(color_name)
            if btn_ref is not None:
                try:
                    btn_ref.config(bg=default_val)
                except Exception:
                    pass

    TkButton(
        colors_group,
        text=_tr("theme_colors_reset_btn"),
        command=_reset_colors_to_default,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        relief="flat",
        font=("Segoe UI", 10),
        cursor="hand2",
        padx=10,
        pady=6,
    ).pack(anchor="w", pady=(10, 0))

    # ── Секция Типографики ──────────────────────────────────────────────
    # ИСПРАВЛЕНО: раньше здесь было поле "имя шрифта" (font_main_var) —
    # тоже "мёртвое": семейство шрифта нигде в проекте не читалось из
    # theme_settings.json, все виджеты хардкодят "Segoe UI"/"Consolas"
    # напрямую в коде. Убрано, чтобы не создавать иллюзию несуществующей
    # функциональности. Вместо него — РЕАЛЬНЫЙ рабочий слайдер базового
    # размера шрифта (colors.scaled_font_size() масштабирует им ВСЕ
    # хардкоженные font=(..., N) по всему проекту, КРОМЕ текстового поля
    # ввода/редактора — там свой отдельный независимый механизм, слайдер
    # "Aa" в textbox.py, который НЕ трогаем).
    # См. пояснение про padx/pady у TkFrame выше (секция "Цветов") — тот же
    # паттерн внешний/внутренний контейнер применяется здесь.
    fonts_group_outer = TkFrame(
        scroll_frame, bg=_c("BG_CARD"), highlightthickness=1, highlightbackground=_c("BORDER")
    )
    fonts_group_outer.pack(fill="x", pady=(0, 12))
    fonts_group = TkFrame(fonts_group_outer, bg=_c("BG_CARD"))
    fonts_group.pack(fill="both", expand=True, padx=14, pady=12)

    TkLabel(
        fonts_group,
        text=_tr("theme_font_section_title"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w", pady=(0, 4))
    TkLabel(
        fonts_group,
        text=_tr("theme_font_section_desc"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        justify="left",
        anchor="w",
    ).pack(anchor="w", pady=(0, 10))

    font_base_size_var = tk.IntVar(value=get_font_base_size())

    row_fs = TkFrame(fonts_group, bg=_c("BG_CARD"))
    row_fs.pack(fill="x")

    font_size_value_label = TkLabel(
        row_fs,
        text=str(font_base_size_var.get()),
        bg=_c("BG_CARD"),
        fg=_c("ACCENT"),
        font=("Segoe UI", 12, "bold"),
        width=3,
        anchor="e",
    )
    font_size_value_label.pack(side="right", padx=(6, 0))

    def _on_font_size_slider(value):
        try:
            size = int(round(float(value)))
        except Exception:
            return
        font_size_value_label.config(text=str(size))

    # ПРИМЕЧАНИЕ: используем и command=, и trace_add на самой переменной —
    # tk.Scale.command вызывается только при ручном взаимодействии
    # пользователя с ползунком мышью/клавиатурой, но НЕ при программном
    # var.set(...) (например, из кнопки "Сбросить ВСЁ" ниже). trace_add
    # гарантированно ловит оба случая, поэтому числовая подпись справа от
    # слайдера всегда синхронна со значением переменной.
    font_base_size_var.trace_add(
        "write", lambda *_: font_size_value_label.config(text=str(font_base_size_var.get()))
    )

    font_size_scale = tk.Scale(
        row_fs,
        from_=6,
        to=24,
        orient="horizontal",
        variable=font_base_size_var,
        command=_on_font_size_slider,
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        highlightthickness=0,
        troughcolor=_c("BG_INPUT"),
    )
    font_size_scale.pack(side="left", fill="x", expand=True)

    # ПРИМЕЧАНИЕ (удалено): здесь раньше была секция "Геометрия и Отступы"
    # со слайдером padding_main — она была так же "мертва", как раньше были
    # цвета: geometry.padding_main нигде в проекте не читался, кроме этого
    # самого файла. Настоящее управление отступами уже реализовано и
    # РЕАЛЬНО РАБОТАЕТ через пресеты раскладки ниже (Classic/Compact/Wide —
    # padding_main_x/y, panel_spacing и т.д., см. engine/gui/layout.py).
    # Секция убрана, чтобы не дублировать функциональность и не создавать
    # у пользователя ложное впечатление о ещё одном независимом регуляторе
    # отступов (заодно немного уменьшает высоту всего окна).

    # ── Секция Расположения ────────────────────────────────────────────────────────
    # См. пояснение про padx/pady у TkFrame выше (секция "Цветов").
    lay_group_outer = TkFrame(
        scroll_frame, bg=_c("BG_CARD"), highlightthickness=1, highlightbackground=_c("BORDER")
    )
    lay_group_outer.pack(fill="x", pady=(0, 12))
    lay_group = TkFrame(lay_group_outer, bg=_c("BG_CARD"))
    lay_group.pack(fill="both", expand=True, padx=14, pady=12)

    TkLabel(
        lay_group,
        text=_tr("theme_layout_label"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w", pady=(0, 10))

    # Читаем текущий пресет раскладки (поддержка старого ключа "layout"
    # реализована внутри theme_manager.load_theme() — merged содержит оба).
    _current_layout_name = (
        current_theme.get("layout_preset") or current_theme.get("layout") or "classic"
    )
    lay_var = tk.StringVar(value=_current_layout_name)
    for l_id, l_label in [
        ("classic", _tr("theme_layout_classic")),
        ("compact", _tr("theme_layout_compact")),
        ("wide", _tr("theme_layout_wide")),
    ]:
        tk.Radiobutton(
            lay_group,
            text=l_label,
            variable=lay_var,
            value=l_id,
            bg=_c("BG_CARD"),
            fg=_c("TEXT_MAIN"),
            selectcolor=_c("BG_INPUT"),
            activebackground=_c("BG_CARD"),
            font=("Segoe UI", 12),
            anchor="w",
        ).pack(fill="x")

    # Честное предупреждение: большинство параметров (ширина левой панели,
    # отступы окна, отступы панелей, размер консоли/статусбара, отступы
    # textbox) теперь применяется СРАЗУ (см. apply_layout_preset() в
    # engine/gui/layout.py и apply_layout() во всех панелях). Единственное
    # исключение — переключение числа рядов тулбара (Compact ⇄ Classic/Wide,
    # toolbar_rows: 1 ⇄ 2) — оно требует перезапуска, см. apply_layout() в
    # engine/gui/toolbar.py (там это явное и осознанное ограничение).
    # Ключ theme_layout_restart_note уже в i18n; _tr() даёт fallback.
    TkLabel(
        lay_group,
        text=_tr("theme_layout_restart_note"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 11),
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(8, 0))

    # ── NEW: Расположение интерфейса — боковая панель + порядок тулбара ──
    # Боковая панель: слева / справа
    TkLabel(
        lay_group,
        text=_tr("theme_sidebar_label"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 12, "bold"),
        anchor="w",
    ).pack(fill="x", pady=(16, 6))

    sidebar_side_var = tk.StringVar(value=get_sidebar_side())
    side_row = TkFrame(lay_group, bg=_c("BG_CARD"))
    side_row.pack(fill="x", pady=(0, 4))
    tk.Radiobutton(
        side_row,
        text=_tr("theme_sidebar_left"),
        variable=sidebar_side_var,
        value="left",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        selectcolor=_c("BG_INPUT"),
        activebackground=_c("BG_CARD"),
        font=("Segoe UI", 11),
        anchor="w",
    ).pack(side="left", padx=(0, 20))
    tk.Radiobutton(
        side_row,
        text=_tr("theme_sidebar_right"),
        variable=sidebar_side_var,
        value="right",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        selectcolor=_c("BG_INPUT"),
        activebackground=_c("BG_CARD"),
        font=("Segoe UI", 11),
        anchor="w",
    ).pack(side="left")

    TkLabel(
        lay_group,
        text=_tr("theme_sidebar_apply_note"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(0, 8))

    # Порядок панелей тулбара
    TkLabel(
        lay_group,
        text=_tr("theme_toolbar_order_label"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 12, "bold"),
        anchor="w",
    ).pack(fill="x", pady=(12, 6))

    _toolbar_labels = {
        "file": _tr("theme_toolbar_panel_file"),
        "ai": _tr("theme_toolbar_panel_ai"),
        "output": _tr("theme_toolbar_panel_output"),
        "action": _tr("theme_toolbar_panel_action"),
    }

    toolbar_order_list = get_toolbar_order()
    order_frame = TkFrame(lay_group, bg=_c("BG_CARD"))
    order_frame.pack(fill="x", pady=(0, 4))

    order_listbox = tk.Listbox(
        order_frame,
        height=4,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        selectbackground=Colors.ACCENT,
        selectforeground=_c("TEXT_MAIN"),
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
        relief="flat",
        font=("Segoe UI", 11),
    )
    order_listbox.pack(side="left", fill="both", expand=True)

    def _refresh_order_listbox(select_index=None):
        order_listbox.delete(0, tk.END)
        for pid in toolbar_order_list:
            order_listbox.insert(tk.END, _toolbar_labels.get(pid, pid))
        if select_index is not None and 0 <= select_index < order_listbox.size():
            order_listbox.selection_clear(0, tk.END)
            order_listbox.selection_set(select_index)
            order_listbox.activate(select_index)

    _refresh_order_listbox(0)

    btn_col = TkFrame(order_frame, bg=_c("BG_CARD"))
    btn_col.pack(side="right", padx=(8, 0), fill="y")

    def _move_up():
        nonlocal toolbar_order_list
        sel = order_listbox.curselection()
        if not sel:
            return
        i = sel[0]
        if i == 0:
            return
        toolbar_order_list[i - 1], toolbar_order_list[i] = (
            toolbar_order_list[i],
            toolbar_order_list[i - 1],
        )
        _refresh_order_listbox(i - 1)

    def _move_down():
        nonlocal toolbar_order_list
        sel = order_listbox.curselection()
        if not sel:
            return
        i = sel[0]
        if i >= len(toolbar_order_list) - 1:
            return
        toolbar_order_list[i + 1], toolbar_order_list[i] = (
            toolbar_order_list[i],
            toolbar_order_list[i + 1],
        )
        _refresh_order_listbox(i + 1)

    def _reset_order():
        nonlocal toolbar_order_list
        toolbar_order_list = DEFAULT_TOOLBAR_ORDER.copy()
        _refresh_order_listbox(0)

    TkButton(
        btn_col,
        text=_tr("theme_toolbar_move_up"),
        command=_move_up,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        relief="flat",
        font=("Segoe UI", 9),
        cursor="hand2",
        padx=8,
        pady=4,
    ).pack(fill="x", pady=(0, 4))
    TkButton(
        btn_col,
        text=_tr("theme_toolbar_move_down"),
        command=_move_down,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        relief="flat",
        font=("Segoe UI", 9),
        cursor="hand2",
        padx=8,
        pady=4,
    ).pack(fill="x", pady=(0, 8))
    TkButton(
        btn_col,
        text=_tr("theme_toolbar_reset_order"),
        command=_reset_order,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_DIM"),
        relief="flat",
        font=("Segoe UI", 8),
        cursor="hand2",
        padx=8,
        pady=2,
    ).pack(fill="x")

    TkLabel(
        lay_group,
        text=_tr("theme_toolbar_order_hint"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(4, 0))

    # --- Неоновые эффекты: одна кнопка ⚙, флажки вкл/выкл внутри панели у каждой цели ---
    TkLabel(
        lay_group,
        text=_tr("theme_header_effects_label"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 12, "bold"),
        anchor="w",
    ).pack(fill="x", pady=(16, 6))

    try:
        _rb_title_style = get_header_rainbow_style()
    except Exception:
        _rb_title_style = dict(DEFAULT_HEADER_RAINBOW_STYLE)
    try:
        _rb_author_style = get_header_author_rainbow_style()
    except Exception:
        _rb_author_style = dict(DEFAULT_HEADER_AUTHOR_RAINBOW_STYLE)
    try:
        _neon_btns_cfg = get_neon_buttons()
    except Exception:
        _neon_btns_cfg = {}

    # enabled flags (живут в UI; сохраняются в apply_and_save)
    header_rainbow_var = tk.BooleanVar(value=get_header_rainbow())
    header_author_rainbow_var = tk.BooleanVar(value=get_header_author_rainbow())
    neon_btn_vars = {}
    for _bid in NEON_BUTTON_IDS:
        neon_btn_vars[_bid] = tk.BooleanVar(
            value=bool((_neon_btns_cfg.get(_bid) or {}).get("enabled", True))
        )

    def _mk_check(parent, text, var):
        try:
            import customtkinter as ctk

            cb = ctk.CTkCheckBox(
                parent,
                text=text,
                variable=var,
                fg_color=Colors.ACCENT,
                text_color=Colors.TEXT_MAIN,
                font=("Segoe UI", 11),
            )
            cb.pack(side="left", pady=(0, 2))
            return cb
        except Exception:
            cb = tk.Checkbutton(
                parent,
                text=text,
                variable=var,
                bg=_c("BG_CARD"),
                fg=_c("TEXT_MAIN"),
                selectcolor=_c("BG_INPUT"),
                activebackground=_c("BG_CARD"),
                font=("Segoe UI", 11),
                anchor="w",
            )
            cb.pack(side="left", fill="x")
            return cb

    # ── Строка: [⚙ Настройки неона] ──
    neon_open_row = TkFrame(lay_group, bg=_c("BG_CARD"))
    neon_open_row.pack(fill="x", pady=(0, 4))
    _rb_panel_open = {"v": False}
    rb_cfg_btn = TkButton(
        neon_open_row,
        text=_tr("theme_header_rainbow_cfg_btn") + " " + _tr("theme_header_rainbow_panel_title"),
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        relief="flat",
        font=("Segoe UI", 11),
        cursor="hand2",
        padx=10,
        pady=4,
    )
    rb_cfg_btn.pack(side="left")

    TkLabel(
        lay_group,
        text=_tr("theme_header_rainbow_desc"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 11),
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(0, 4))

    # ══════════════════════════════════════════════════════
    # Раскрывающаяся панель (карточки в стиле audio/volume popup)
    # ══════════════════════════════════════════════════════
    rb_panel_outer = TkFrame(
        lay_group,
        bg=_c("BG_CARD"),
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
    )
    # по умолчанию скрыта — pack/forget
    rb_panel = TkFrame(rb_panel_outer, bg=_c("BG_INPUT"))
    rb_panel.pack(fill="both", expand=True, padx=1, pady=1)

    # Заголовок панели
    rb_panel_hdr = TkFrame(rb_panel, bg=_c("BG_INPUT"))
    rb_panel_hdr.pack(fill="x", padx=10, pady=(10, 6))
    TkLabel(
        rb_panel_hdr,
        text=_tr("theme_header_rainbow_panel_title"),
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 11, "bold"),
        anchor="w",
    ).pack(side="left")
    rb_collapse_btn = TkButton(
        rb_panel_hdr,
        text="▾ " + _tr("theme_header_rainbow_collapse"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        relief="flat",
        font=("Segoe UI", 11),
        cursor="hand2",
        padx=8,
        pady=2,
    )
    rb_collapse_btn.pack(side="right")

    # Переключатель target: title | author | chat | ai | styles | quality | generate
    target_row = TkFrame(rb_panel, bg=_c("BG_INPUT"))
    target_row.pack(fill="x", padx=10, pady=(0, 4))
    target_row2 = TkFrame(rb_panel, bg=_c("BG_INPUT"))
    target_row2.pack(fill="x", padx=10, pady=(0, 8))
    rainbow_target_var = tk.StringVar(value="title")

    _NEON_TARGETS = [
        ("title", "theme_header_rainbow_target_title"),
        ("author", "theme_header_rainbow_target_author"),
        ("chat", "theme_neon_btn_chat"),
        ("ai", "theme_neon_btn_ai"),
        ("styles", "theme_neon_btn_styles"),
        ("quality", "theme_neon_btn_quality"),
        ("generate", "theme_neon_btn_generate"),
    ]
    _chip_widgets = {}  # id -> (chip, lbl)

    def _target_chip(parent, value, label):
        chip = TkFrame(
            parent, bg=_c("BG_CARD"), highlightthickness=1, highlightbackground=_c("BORDER")
        )
        chip.pack(side="left", padx=(0, 6), pady=2)
        lbl = TkLabel(
            chip,
            text=label,
            bg=_c("BG_CARD"),
            fg=_c("TEXT_MAIN"),
            font=("Segoe UI", 11),
            padx=8,
            pady=5,
            cursor="hand2",
        )
        lbl.pack()

        def _sel(_e=None, v=value):
            if v != rainbow_target_var.get():
                _on_target_change(v)
            else:
                _refresh_target_chips()

        lbl.bind("<Button-1>", _sel)
        chip.bind("<Button-1>", _sel)
        _chip_widgets[value] = (chip, lbl)
        return chip, lbl

    for i, (tid, tkey) in enumerate(_NEON_TARGETS):
        parent = target_row if i < 4 else target_row2
        _target_chip(parent, tid, _tr(tkey))

    def _refresh_target_chips():
        cur = rainbow_target_var.get()
        for val, (chip, lbl) in _chip_widgets.items():
            active = val == cur
            bg = Colors.ACCENT if active else _c("BG_CARD")
            try:
                chip.configure(bg=bg, highlightbackground=Colors.ACCENT if active else _c("BORDER"))
                lbl.configure(bg=bg, fg=_c("TEXT_MAIN"))
            except Exception:
                pass

    # Флажок «Включить неон» — для текущей цели (заголовок / author / кнопка)
    enable_row = TkFrame(rb_panel, bg=_c("BG_INPUT"))
    enable_row.pack(fill="x", padx=10, pady=(0, 8))
    # proxy var synced with real flags when target changes
    neon_enable_proxy = tk.BooleanVar(value=True)

    def _enabled_var_for(target: str):
        if target == "title":
            return header_rainbow_var
        if target == "author":
            return header_author_rainbow_var
        return neon_btn_vars.get(target)

    def _sync_enable_proxy_from_target():
        v = _enabled_var_for(rainbow_target_var.get())
        if v is not None:
            try:
                neon_enable_proxy.set(bool(v.get()))
            except Exception:
                pass

    def _on_enable_proxy_write(*_a):
        v = _enabled_var_for(rainbow_target_var.get())
        if v is not None:
            try:
                v.set(bool(neon_enable_proxy.get()))
            except Exception:
                pass

    try:
        neon_enable_proxy.trace_add("write", _on_enable_proxy_write)
    except Exception:
        pass
    _mk_check(enable_row, _tr("theme_neon_target_enabled"), neon_enable_proxy)
    _sync_enable_proxy_from_target()

    # ── Внутренняя карточка настроек (audio-style card) ──
    def _audio_card(parent, title_text: str):
        outer = TkFrame(
            parent, bg=_c("BG_CARD"), highlightthickness=1, highlightbackground=_c("BORDER")
        )
        outer.pack(fill="x", padx=10, pady=(0, 8))
        inner = TkFrame(outer, bg=_c("BG_CARD"))
        inner.pack(fill="both", expand=True, padx=12, pady=10)
        if title_text:
            TkLabel(
                inner,
                text=title_text,
                bg=_c("BG_CARD"),
                fg=_c("ACCENT"),
                font=("Segoe UI", 11, "bold"),
                anchor="w",
            ).pack(fill="x", pady=(0, 6))
        return inner

    # State holders for both targets (fields bind to "active" vars; we swap on target change)
    _SPEED_MS = {"fast": 20, "normal": 40, "slow": 80}

    def _speed_choice_from_ms(ms: int) -> str:
        ms = int(ms)
        if ms <= 28:
            return "fast"
        if ms >= 60:
            return "slow"
        return "normal"

    # Working vars (UI-bound)
    rainbow_speed_var = tk.StringVar(
        value=_speed_choice_from_ms(_rb_title_style.get("speed_ms", 40))
    )
    rainbow_sat_var = tk.DoubleVar(value=float(_rb_title_style.get("saturation", 0.85)))
    rainbow_bri_var = tk.DoubleVar(value=float(_rb_title_style.get("brightness", 1.0)))
    rainbow_hue_var = tk.DoubleVar(value=float(_rb_title_style.get("hue_offset", 0.0)))
    rainbow_spread_var = tk.DoubleVar(value=float(_rb_title_style.get("spread", 1.0)))
    rainbow_mode_var = tk.StringVar(value=str(_rb_title_style.get("mode", "hsv")))
    # colors stored per-target
    _rb_colors = {
        "title": list(_rb_title_style.get("colors") or []),
        "author": list(_rb_author_style.get("colors") or []),
    }
    _rb_cache = {
        "title": dict(_rb_title_style),
        "author": dict(_rb_author_style),
    }
    for _bid in NEON_BUTTON_IDS:
        _st = dict((_neon_btns_cfg.get(_bid) or {}).get("style") or DEFAULT_HEADER_RAINBOW_STYLE)
        _rb_cache[_bid] = _st
        _rb_colors[_bid] = list(_st.get("colors") or [])

    # ── Card: speed ──
    speed_card = _audio_card(rb_panel, _tr("theme_header_rainbow_speed"))
    speed_chips = TkFrame(speed_card, bg=_c("BG_CARD"))
    speed_chips.pack(fill="x")
    _speed_chip_widgets = {}

    def _mk_speed_chip(value, label_key):
        chip = TkFrame(
            speed_chips, bg=_c("BG_INPUT"), highlightthickness=1, highlightbackground=_c("BORDER")
        )
        chip.pack(side="left", padx=(0, 6))
        lbl = TkLabel(
            chip,
            text=_tr(label_key),
            bg=_c("BG_INPUT"),
            fg=_c("TEXT_MAIN"),
            font=("Segoe UI", 11),
            padx=12,
            pady=6,
            cursor="hand2",
        )
        lbl.pack()

        def _sel(_e=None, v=value):
            rainbow_speed_var.set(v)
            _refresh_speed_chips()

        lbl.bind("<Button-1>", _sel)
        chip.bind("<Button-1>", _sel)
        _speed_chip_widgets[value] = (chip, lbl)
        return chip

    _mk_speed_chip("fast", "theme_header_rainbow_speed_fast")
    _mk_speed_chip("normal", "theme_header_rainbow_speed_normal")
    _mk_speed_chip("slow", "theme_header_rainbow_speed_slow")

    def _refresh_speed_chips():
        cur = rainbow_speed_var.get()
        for val, (chip, lbl) in _speed_chip_widgets.items():
            active = val == cur
            bg = Colors.ACCENT if active else _c("BG_INPUT")
            try:
                chip.configure(bg=bg, highlightbackground=Colors.ACCENT if active else _c("BORDER"))
                lbl.configure(bg=bg)
            except Exception:
                pass

    _refresh_speed_chips()

    # ── Card: sliders — тот же стиль, что слайдер «Размер шрифта» в пресетах/типографике ──
    UI_F = ("Segoe UI", 11)  # единый размер текста панели перелива
    UI_F_DIM = ("Segoe UI", 11)
    sliders_card = _audio_card(rb_panel, "")

    def _preset_style_slider(parent, label_key, var, from_, to_, resolution=0.05):
        """Ползунок как font_size_scale: label + Scale + число справа."""
        row = TkFrame(parent, bg=_c("BG_CARD"))
        row.pack(fill="x", pady=(0, 6))
        TkLabel(
            row,
            text=_tr(label_key),
            bg=_c("BG_CARD"),
            fg=_c("TEXT_MAIN"),
            font=UI_F,
            anchor="w",
            width=16,
        ).pack(side="left")
        val_lbl = TkLabel(
            row,
            text=f"{float(var.get()):.2f}",
            bg=_c("BG_CARD"),
            fg=_c("ACCENT"),
            font=("Segoe UI", 11, "bold"),
            width=5,
            anchor="e",
        )
        val_lbl.pack(side="right", padx=(6, 0))

        def _on_slide(v, lbl=val_lbl):
            try:
                lbl.config(text=f"{float(v):.2f}")
            except Exception:
                pass

        # trace — чтобы программный set тоже обновлял подпись
        try:
            var.trace_add(
                "write", lambda *_a, lbl=val_lbl, vv=var: lbl.config(text=f"{float(vv.get()):.2f}")
            )
        except Exception:
            pass

        scale = tk.Scale(
            row,
            from_=from_,
            to=to_,
            resolution=resolution,
            orient="horizontal",
            variable=var,
            showvalue=0,
            command=_on_slide,
            bg=_c("BG_CARD"),
            fg=_c("TEXT_MAIN"),
            highlightthickness=0,
            troughcolor=_c("BG_INPUT"),
        )
        scale.pack(side="left", fill="x", expand=True, padx=(4, 0))
        return scale, val_lbl

    _sat_scale, _sat_lbl = _preset_style_slider(
        sliders_card, "theme_header_rainbow_saturation", rainbow_sat_var, 0.0, 1.0, 0.05
    )
    _bri_scale, _bri_lbl = _preset_style_slider(
        sliders_card, "theme_header_rainbow_brightness", rainbow_bri_var, 0.15, 1.0, 0.05
    )
    _hue_scale, _hue_lbl = _preset_style_slider(
        sliders_card, "theme_header_rainbow_hue", rainbow_hue_var, 0.0, 1.0, 0.01
    )
    _spr_scale, _spr_lbl = _preset_style_slider(
        sliders_card, "theme_header_rainbow_spread", rainbow_spread_var, 0.2, 2.0, 0.05
    )
    _slider_val_labels = (_sat_lbl, _bri_lbl, _hue_lbl, _spr_lbl)

    # ── Card: color mode + custom palette ──
    mode_card = _audio_card(rb_panel, _tr("theme_header_rainbow_mode"))
    mode_row = TkFrame(mode_card, bg=_c("BG_CARD"))
    mode_row.pack(fill="x")
    _mode_chips = {}

    def _mk_mode_chip(value, label_key):
        chip = TkFrame(
            mode_row, bg=_c("BG_INPUT"), highlightthickness=1, highlightbackground=_c("BORDER")
        )
        chip.pack(side="left", padx=(0, 6))
        lbl = TkLabel(
            chip,
            text=_tr(label_key),
            bg=_c("BG_INPUT"),
            fg=_c("TEXT_MAIN"),
            font=("Segoe UI", 11),
            padx=12,
            pady=6,
            cursor="hand2",
        )
        lbl.pack()

        def _sel(_e=None, v=value):
            rainbow_mode_var.set(v)
            _refresh_mode_chips()
            _sync_palette_visibility()

        lbl.bind("<Button-1>", _sel)
        chip.bind("<Button-1>", _sel)
        _mode_chips[value] = (chip, lbl)

    _mk_mode_chip("hsv", "theme_header_rainbow_mode_hsv")
    _mk_mode_chip("custom", "theme_header_rainbow_mode_custom")

    def _refresh_mode_chips():
        cur = rainbow_mode_var.get()
        for val, (chip, lbl) in _mode_chips.items():
            active = val == cur
            bg = Colors.ACCENT if active else _c("BG_INPUT")
            try:
                chip.configure(bg=bg, highlightbackground=Colors.ACCENT if active else _c("BORDER"))
                lbl.configure(bg=bg)
            except Exception:
                pass

    # palette area
    palette_card = _audio_card(rb_panel, _tr("theme_header_rainbow_colors"))
    palette_swatches = TkFrame(palette_card, bg=_c("BG_CARD"))
    palette_swatches.pack(fill="x")
    palette_btns = TkFrame(palette_card, bg=_c("BG_CARD"))
    palette_btns.pack(fill="x", pady=(8, 0))

    def _current_target() -> str:
        v = rainbow_target_var.get()
        valid = ("title", "author") + tuple(NEON_BUTTON_IDS)
        return v if v in valid else "title"

    def _refresh_swatches():
        """Перерисовать swatches. Используем raw tk.Frame/Label — CTkButton
        часто не показывает bg/fg_color для «пустой» цветной клетки."""
        for w in list(palette_swatches.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        tgt = _current_target()
        colors = list(_rb_colors.get(tgt, []))
        # синхронизируем cache
        if tgt in _rb_cache:
            _rb_cache[tgt]["colors"] = list(colors)

        if not colors:
            tk.Label(
                palette_swatches,
                text="—",
                bg=_c("BG_CARD"),
                fg=_c("TEXT_DIM"),
                font=("Segoe UI", 11),
            ).pack(side="left")
            try:
                _refresh_scrollregion()
            except Exception:
                pass
            return

        for idx, hx in enumerate(colors):
            cell = tk.Frame(palette_swatches, bg=_c("BG_CARD"))
            cell.pack(side="left", padx=(0, 8), pady=4)

            # цветной квадрат 28x28
            sw = tk.Frame(
                cell,
                bg=hx,
                width=28,
                height=28,
                highlightthickness=1,
                highlightbackground=_c("BORDER"),
                cursor="hand2",
            )
            sw.pack(side="left")
            sw.pack_propagate(False)

            def _recolor(_e=None, i=idx):
                from tkinter import colorchooser

                cols = _rb_colors[_current_target()]
                init = cols[i] if i < len(cols) else "#ff006e"
                picked = colorchooser.askcolor(initialcolor=init, parent=win)
                if picked and picked[1]:
                    cols[i] = picked[1]
                    _rb_colors[_current_target()] = cols
                    if _current_target() in _rb_cache:
                        _rb_cache[_current_target()]["colors"] = list(cols)
                    _refresh_swatches()

            for w in (sw, cell):
                w.bind("<Button-1>", _recolor)

            rm = tk.Button(
                cell,
                text="×",
                command=lambda i=idx: _remove_color_at(i),
                bg=_c("BG_INPUT"),
                fg=_c("TEXT_DIM"),
                relief="flat",
                font=("Segoe UI", 11),
                cursor="hand2",
                bd=0,
                padx=4,
                pady=0,
            )
            rm.pack(side="left", padx=(3, 0))

        try:
            _refresh_scrollregion()
        except Exception:
            pass

    def _remove_color_at(i: int):
        cols = _rb_colors[_current_target()]
        if 0 <= i < len(cols):
            cols.pop(i)
            _rb_colors[_current_target()] = cols
            if _current_target() in _rb_cache:
                _rb_cache[_current_target()]["colors"] = list(cols)
            _refresh_swatches()

    def _add_color():
        from tkinter import colorchooser

        picked = colorchooser.askcolor(initialcolor="#ff006e", parent=win)
        if not picked or not picked[1]:
            return
        tgt = _current_target()
        cols = list(_rb_colors.get(tgt, []))
        if len(cols) >= 12:
            return
        cols.append(picked[1])
        _rb_colors[tgt] = cols
        if tgt in _rb_cache:
            _rb_cache[tgt]["colors"] = list(cols)
        # если mode ещё hsv — переключим на custom, иначе палитра «незаметна»
        try:
            if rainbow_mode_var.get() != "custom":
                rainbow_mode_var.set("custom")
                _refresh_mode_chips()
        except Exception:
            pass
        _refresh_swatches()

    def _clear_colors():
        tgt = _current_target()
        _rb_colors[tgt] = []
        if tgt in _rb_cache:
            _rb_cache[tgt]["colors"] = []
        _refresh_swatches()

    TkButton(
        palette_btns,
        text=_tr("theme_header_rainbow_add_color"),
        command=_add_color,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        relief="flat",
        font=("Segoe UI", 11),
        cursor="hand2",
        padx=10,
        pady=4,
    ).pack(side="left", padx=(0, 6))
    TkButton(
        palette_btns,
        text=_tr("theme_header_rainbow_clear_colors"),
        command=_clear_colors,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_DIM"),
        relief="flat",
        font=("Segoe UI", 11),
        cursor="hand2",
        padx=10,
        pady=4,
    ).pack(side="left")
    TkLabel(
        palette_card,
        text=_tr("theme_header_rainbow_colors_hint"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 11),
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(6, 0))

    def _sync_palette_visibility():
        # HSV-слайдеры полезны в hsv; в custom — палитра
        # оба блока оставляем, но подсвечиваем режим
        _refresh_mode_chips()

    # ── Footer: reset ──
    footer = TkFrame(rb_panel, bg=_c("BG_INPUT"))
    footer.pack(fill="x", padx=10, pady=(0, 10))

    def _flush_fields_to_cache():
        t = _current_target()
        _rb_cache[t] = {
            "speed_ms": _SPEED_MS.get(rainbow_speed_var.get(), 40),
            "saturation": float(rainbow_sat_var.get()),
            "brightness": float(rainbow_bri_var.get()),
            "hue_offset": float(rainbow_hue_var.get()),
            "spread": float(rainbow_spread_var.get()),
            "mode": (
                rainbow_mode_var.get() if rainbow_mode_var.get() in ("hsv", "custom") else "hsv"
            ),
            "colors": list(_rb_colors.get(t, [])),
        }

    def _load_target_into_fields():
        # save previous target first
        # (caller sets rainbow_target_var already)
        t = _current_target()
        # when switching, flush the OTHER? we flush on switch via chip handler before load
        st = dict(_rb_cache.get(t) or {})
        rainbow_speed_var.set(_speed_choice_from_ms(st.get("speed_ms", 40)))
        rainbow_sat_var.set(float(st.get("saturation", 0.85)))
        rainbow_bri_var.set(float(st.get("brightness", 1.0)))
        rainbow_hue_var.set(float(st.get("hue_offset", 0.0)))
        rainbow_spread_var.set(float(st.get("spread", 1.0)))
        rainbow_mode_var.set(str(st.get("mode", "hsv")))
        _rb_colors[t] = list(st.get("colors") or [])
        _refresh_speed_chips()
        _refresh_mode_chips()
        _refresh_swatches()
        # update pill labels
        for lbl, var in (
            (_sat_lbl, rainbow_sat_var),
            (_bri_lbl, rainbow_bri_var),
            (_hue_lbl, rainbow_hue_var),
            (_spr_lbl, rainbow_spread_var),
        ):
            try:
                lbl.config(text=f"{float(var.get()):.2f}")
            except Exception:
                pass

    # wrap chip select to flush before switch
    _prev_target = {"v": "title"}

    def _on_target_change(new_val: str):
        _flush_fields_to_cache()
        rainbow_target_var.set(new_val)
        try:
            _prev_target["v"] = new_val
        except Exception:
            pass
        _refresh_target_chips()
        _load_target_into_fields()
        _sync_enable_proxy_from_target()

    def _reset_rainbow_style_fields():
        t = _current_target()
        if t == "author":
            d = dict(DEFAULT_HEADER_AUTHOR_RAINBOW_STYLE)
        else:
            d = dict(DEFAULT_HEADER_RAINBOW_STYLE)
        _rb_cache[t] = dict(d)
        _rb_colors[t] = list(d.get("colors") or [])
        _load_target_into_fields()

    TkButton(
        footer,
        text=_tr("theme_header_rainbow_reset_style"),
        command=_reset_rainbow_style_fields,
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        relief="flat",
        font=("Segoe UI", 11),
        cursor="hand2",
        padx=10,
        pady=4,
    ).pack(side="left")
    TkLabel(
        footer,
        text=_tr("theme_header_rainbow_style_hint"),
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 11),
        justify="left",
        anchor="w",
    ).pack(side="left", padx=(12, 0))

    def _toggle_rb_panel():
        if _rb_panel_open["v"]:
            try:
                rb_panel_outer.pack_forget()
            except Exception:
                pass
            _rb_panel_open["v"] = False
            try:
                rb_cfg_btn.configure(bg=_c("BG_INPUT"))
            except Exception:
                pass
            try:
                _refresh_scrollregion()
            except Exception:
                pass
        else:
            # flush before show
            _flush_fields_to_cache()
            _refresh_target_chips()
            _load_target_into_fields()
            rb_panel_outer.pack(fill="x", pady=(4, 8))
            _rb_panel_open["v"] = True
            try:
                rb_cfg_btn.configure(bg=Colors.ACCENT)
            except Exception:
                pass
            # критично: после pack панели scrollregion устаревает → «баг скролла»
            try:
                _refresh_scrollregion()
                # прокрутить к панели, чтобы было видно
                canvas.yview_moveto(1.0)
            except Exception:
                pass

    rb_cfg_btn.configure(command=_toggle_rb_panel)
    rb_collapse_btn.configure(command=_toggle_rb_panel)

    # init chips visual
    _refresh_target_chips()
    _refresh_mode_chips()
    _refresh_swatches()

    def _collect_rainbow_style(target: str = "title") -> dict:
        """Собрать style для title/author.

        Всегда flush'им текущие поля UI в cache (чтобы ⚙-панель не теряла
        несохранённый target при сборе другого target), затем читаем cache.
        """
        try:
            _flush_fields_to_cache()
        except Exception:
            pass
        st = dict(_rb_cache.get(target) or {})
        # ensure required keys
        st.setdefault("speed_ms", 40)
        st.setdefault("saturation", 0.85)
        st.setdefault("brightness", 1.0)
        st.setdefault("hue_offset", 0.0)
        st.setdefault("spread", 1.0)
        st.setdefault("mode", "hsv")
        st["colors"] = list(_rb_colors.get(target, st.get("colors") or []))
        return st

    # ── Секция Пресетов (НОВОЕ) ──────────────────────────────────────────
    # Пресет — это именованный "снимок" ВСЕХ трёх настроек этого окна разом
    # (цвета текущей темы + базовый размер шрифта + раскладка). Хранится в
    # theme_settings.json -> "saved_presets" (см. theme_manager.py). Список
    # пресетов не ограничен — пользователь может создать сколько угодно.
    # См. пояснение про padx/pady у TkFrame выше (секция "Цветов") — именно
    # из-за этого бага поле ввода имени пресета выглядело "почти невидимым"
    # (было прижато вплотную к краю рамки без реального отступа).
    presets_group_outer = TkFrame(
        scroll_frame, bg=_c("BG_CARD"), highlightthickness=1, highlightbackground=_c("BORDER")
    )
    presets_group_outer.pack(fill="x", pady=(0, 12))
    presets_group = TkFrame(presets_group_outer, bg=_c("BG_CARD"))
    presets_group.pack(fill="both", expand=True, padx=14, pady=12)

    TkLabel(
        presets_group,
        text=_tr("theme_presets_section_title"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w", pady=(0, 4))
    TkLabel(
        presets_group,
        text=_tr("theme_presets_section_desc"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        justify="left",
        anchor="w",
    ).pack(anchor="w", pady=(0, 10))

    # -- Список существующих пресетов --
    preset_list_row = TkFrame(presets_group, bg=_c("BG_CARD"))
    preset_list_row.pack(fill="x", pady=(0, 8))

    preset_names_var = tk.StringVar()

    def _refresh_preset_list():
        names = sorted(get_saved_presets().keys())
        preset_combo["values"] = names
        if names:
            if preset_names_var.get() not in names:
                preset_names_var.set(names[0])
        else:
            preset_names_var.set("")

    preset_combo = ttk.Combobox(
        preset_list_row, textvariable=preset_names_var, state="readonly", font=("Segoe UI", 10)
    )
    preset_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))

    def _apply_selected_preset():
        name = preset_names_var.get()
        if not name:
            messagebox.showwarning(
                _tr("theme_presets_dlg_title"), _tr("theme_presets_select_first"), parent=win
            )
            return
        snapshot = apply_named_preset(name)
        if snapshot is None:
            messagebox.showerror(
                _tr("theme_presets_dlg_title"), _tr("theme_presets_not_found", name), parent=win
            )
            _refresh_preset_list()
            return
        # Живое применение цветов/шрифта прямо в открытом окне конструктора —
        # честно предупреждаем, что полный эффект по всему приложению
        # виден при следующем открытии/перезапуске (как и у обычного
        # сохранения — см. apply_and_save() ниже).
        preset_theme_name = snapshot.get("theme_name", _active_theme_name)
        if preset_theme_name != _active_theme_name:
            theme_label = _tr(
                "theme_name_dark" if preset_theme_name == "dark" else "theme_name_light"
            )
            messagebox.showinfo(
                _tr("theme_presets_dlg_title"),
                _tr("theme_presets_applied_other_theme", name, theme_label),
                parent=win,
            )
        else:
            try:
                apply_palette(preset_theme_name)
            except Exception:
                pass
        try:
            rt_set_font_base_size(snapshot.get("font_base_size", 10))
        except Exception:
            pass
        messagebox.showinfo(
            _tr("theme_presets_dlg_title"), _tr("theme_presets_applied", name), parent=win
        )
        _close_theme_window()

    def _delete_selected_preset():
        name = preset_names_var.get()
        if not name:
            return
        if messagebox.askyesno(
            _tr("theme_presets_dlg_title"), _tr("theme_presets_delete_confirm", name), parent=win
        ):
            delete_named_preset(name)
            _refresh_preset_list()

    TkButton(
        preset_list_row,
        text=_tr("theme_presets_apply_btn"),
        command=_apply_selected_preset,
        bg=_c("BG_ACTIVE"),
        fg=_c("TEXT_MAIN"),
        relief="flat",
        font=("Segoe UI", 10),
        cursor="hand2",
        padx=8,
        pady=4,
    ).pack(side="left", padx=(0, 4))
    TkButton(
        preset_list_row,
        text=_tr("theme_presets_delete_btn"),
        command=_delete_selected_preset,
        bg=_c("BG_DANGER"),
        fg=_c("TEXT_MAIN"),
        relief="flat",
        font=("Segoe UI", 10),
        cursor="hand2",
        padx=8,
        pady=4,
    ).pack(side="left")

    # -- Сохранение текущих настроек как нового пресета --
    TkLabel(
        presets_group,
        text=_tr("theme_presets_new_name_label"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 10),
        anchor="w",
    ).pack(fill="x", pady=(8, 4))

    save_preset_row = TkFrame(presets_group, bg=_c("BG_CARD"))
    save_preset_row.pack(fill="x")

    new_preset_name_var = tk.StringVar()
    # ИСПРАВЛЕНО: добавлена видимая рамка (highlightthickness=1,
    # highlightbackground=BORDER) — раньше поле было тем же bg, что и фон
    # секции, плюс padx/pady у родительского TkFrame не применялись
    # (см. комментарий у presets_group_outer выше), из-за чего поле
    # визуально сливалось с фоном и выглядело "почти невидимым".
    preset_name_entry = tk.Entry(
        save_preset_row,
        textvariable=new_preset_name_var,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        insertbackground=_c("TEXT_MAIN"),
        relief="flat",
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
        highlightcolor=_c("ACCENT"),
        font=("Segoe UI", 10),
    )
    preset_name_entry.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=6)

    def _save_current_as_preset():
        name = new_preset_name_var.get().strip()
        if not name:
            messagebox.showwarning(
                _tr("theme_presets_dlg_title"), _tr("theme_presets_enter_name"), parent=win
            )
            return
        existing = get_saved_presets()
        if name in existing:
            if not messagebox.askyesno(
                _tr("theme_presets_dlg_title"),
                _tr("theme_presets_overwrite_confirm", name),
                parent=win,
            ):
                return
        # Снимок ТЕКУЩЕГО состояния полей формы (ещё не сохранённого через
        # apply_and_save) — так пользователь может подготовить пресет и
        # сохранить его, не закрывая окно кнопкой "Сохранить".
        current_custom_colors = {}
        for color_name, var in color_vars.items():
            val = var.get()
            if val != _base_palette.get(color_name):
                current_custom_colors[color_name] = val
        try:
            _snap_rb = bool(header_rainbow_var.get())
            _snap_rb_style = _collect_rainbow_style("title")
            _snap_rb_author = bool(header_author_rainbow_var.get())
            _snap_rb_author_style = _collect_rainbow_style("author")
        except Exception:
            _snap_rb = False
            _snap_rb_style = {}
            _snap_rb_author = False
            _snap_rb_author_style = {}
        snapshot = {
            "custom_colors": current_custom_colors,
            "theme_name": _active_theme_name,
            "font_base_size": font_base_size_var.get(),
            "layout_preset": lay_var.get(),
            "sidebar_side": sidebar_side_var.get() if "sidebar_side_var" in locals() else "left",
            "toolbar_order": (
                toolbar_order_list if "toolbar_order_list" in locals() else DEFAULT_TOOLBAR_ORDER
            ),
            "header_rainbow": _snap_rb,
            "header_rainbow_style": _snap_rb_style,
            "header_author_rainbow": _snap_rb_author,
            "header_author_rainbow_style": _snap_rb_author_style,
            "neon_buttons": {
                bid: {
                    "enabled": bool(neon_btn_vars[bid].get()) if bid in neon_btn_vars else True,
                    "style": _collect_rainbow_style(bid),
                }
                for bid in NEON_BUTTON_IDS
            },
        }
        save_named_preset(name, snapshot)
        new_preset_name_var.set("")
        _refresh_preset_list()
        preset_names_var.set(name)
        messagebox.showinfo(
            _tr("theme_presets_dlg_title"), _tr("theme_presets_saved", name), parent=win
        )

    TkButton(
        save_preset_row,
        text=_tr("theme_presets_save_btn"),
        command=_save_current_as_preset,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        relief="flat",
        font=("Segoe UI", 10),
        cursor="hand2",
        padx=8,
        pady=4,
    ).pack(side="left")

    _refresh_preset_list()

    # -- Полный сброс всех настроек темы (цвета + шрифт + раскладка) --
    def _reset_everything_to_factory():
        if not messagebox.askyesno(
            _tr("theme_reset_all_dlg_title"), _tr("theme_reset_all_confirm"), parent=win
        ):
            return
        _reset_colors_to_default()
        font_base_size_var.set(BASE_FONT_SIZE_DEFAULT)
        font_size_value_label.config(text=str(BASE_FONT_SIZE_DEFAULT))
        lay_var.set("classic")
        try:
            sidebar_side_var.set("left")
        except Exception:
            pass
        try:
            nonlocal toolbar_order_list
            toolbar_order_list = DEFAULT_TOOLBAR_ORDER.copy()
            _refresh_order_listbox(0)
        except Exception:
            pass
        try:
            header_rainbow_var.set(False)
            header_author_rainbow_var.set(False)
            for _bid, _v in neon_btn_vars.items():
                _v.set(True)
            for _t in ("title", "author") + tuple(NEON_BUTTON_IDS):
                rainbow_target_var.set(_t)
                _reset_rainbow_style_fields()
            rainbow_target_var.set("title")
            _load_target_into_fields()
            _sync_enable_proxy_from_target()
        except Exception:
            pass
        messagebox.showinfo(
            _tr("theme_reset_all_dlg_title"), _tr("theme_reset_all_done"), parent=win
        )

    TkButton(
        presets_group,
        text=_tr("theme_presets_reset_all_btn"),
        command=_reset_everything_to_factory,
        bg=_c("BG_DANGER"),
        fg=_c("TEXT_MAIN"),
        relief="flat",
        font=("Segoe UI", 10),
        cursor="hand2",
        padx=10,
        pady=6,
    ).pack(anchor="w", pady=(10, 0))

    # ── Нижние кнопки ────────────────────────────────────────────────────────
    btn_row = TkFrame(main, bg=_c("BG_DARK"))
    # ИСПРАВЛЕНО: side="bottom" + упаковка ДО canvas/scrollbar (см. правку
    # выше) — гарантирует, что панель кнопок всегда закреплена внизу окна
    # на всю ширину, а прокручиваемый контент занимает оставшееся место
    # НАД ней, а не наоборот.
    btn_row.pack(side="bottom", fill="x", pady=(14, 0))

    # Разделительная линия над кнопками — чтобы визуально отделить их
    # от прокручиваемого контента (простая тонкая полоса через TkFrame).
    TkFrame(main, bg=_c("BORDER"), height=1).pack(side="bottom", fill="x", pady=(14, 0))

    # Теперь, когда нижняя панель кнопок уже закреплена (side="bottom"),
    # отдаём canvas/scrollbar всё оставшееся пространство.
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def apply_and_save():
        selected_layout = lay_var.get()

        # ИСПРАВЛЕНО: цвета теперь сохраняются через set_custom_colors()
        # (реально применяемая система — colors.apply_palette()), а НЕ
        # через легаси-ключ "colors" в new_theme (тот больше никто не
        # читает, см. комментарий в theme_manager.py DEFAULT_THEME).
        # Сохраняем только то, что отличается от встроенной палитры —
        # если пользователь оставил значение как есть, лишний ключ в JSON
        # не создаём (чище дифф в файле настроек, меньше "мусора").
        new_custom_colors = {}
        for color_name, var in color_vars.items():
            val = var.get()
            if val != _base_palette.get(color_name):
                new_custom_colors[color_name] = val
        set_custom_colors(_active_theme_name, new_custom_colors)
        # Применяем сразу — это безопасно и мгновенно видно в уже открытых
        # окнах, которые перечитывают Colors.* при следующей перерисовке
        # (кнопки/лейблы, создаваемые заново), полноценный эффект во ВСЕХ
        # существующих окнах — после их следующего открытия/перезапуска
        # приложения (см. пояснение в docstring apply_palette()).
        try:
            apply_palette(_active_theme_name)
        except Exception:
            pass

        # ИСПРАВЛЕНО: базовый размер шрифта теперь сохраняется через
        # РЕАЛЬНО работающий theme_manager.set_font_base_size() (легаси-
        # ключи "fonts"/"geometry" убраны — они физически ни на что не
        # влияли, см. комментарии выше). Применяем сразу в runtime
        # (colors.set_font_base_size) — часть окон подхватят новый размер
        # только при следующем открытии (см. пояснение в docstring
        # colors.scaled_font_size()), но само значение уже действует.
        new_font_base_size = font_base_size_var.get()
        tm_set_font_base_size(new_font_base_size)
        try:
            rt_set_font_base_size(new_font_base_size)
        except Exception:
            pass

        # Сохраняем расположение интерфейса
        try:
            set_sidebar_side(sidebar_side_var.get())
        except Exception:
            pass
        try:
            set_toolbar_order(toolbar_order_list)
        except Exception:
            pass
        # ── Неон: заголовки + кнопки тулбара ──
        try:
            _flush_fields_to_cache()
        except Exception:
            pass
        try:
            set_header_rainbow(bool(header_rainbow_var.get()))
        except Exception:
            pass
        try:
            set_header_author_rainbow(bool(header_author_rainbow_var.get()))
        except Exception:
            pass
        try:
            rb_style = _collect_rainbow_style("title")
            set_header_rainbow_style(rb_style)
        except Exception:
            try:
                rb_style = get_header_rainbow_style()
            except Exception:
                rb_style = dict(DEFAULT_HEADER_RAINBOW_STYLE)
        try:
            rb_author_style = _collect_rainbow_style("author")
            set_header_author_rainbow_style(rb_author_style)
        except Exception:
            try:
                rb_author_style = get_header_author_rainbow_style()
            except Exception:
                rb_author_style = dict(DEFAULT_HEADER_AUTHOR_RAINBOW_STYLE)

        neon_buttons_payload = {}
        for _bid in NEON_BUTTON_IDS:
            try:
                en = bool(neon_btn_vars[_bid].get())
            except Exception:
                en = True
            try:
                st = _collect_rainbow_style(_bid)
            except Exception:
                st = dict(DEFAULT_HEADER_RAINBOW_STYLE)
            neon_buttons_payload[_bid] = {"enabled": en, "style": st}
        try:
            set_neon_buttons(neon_buttons_payload)
        except Exception:
            pass

        new_theme = {
            # ВАЖНО: пишем именно "layout_preset" — это ключ, который читает
            # theme_manager.get_current_layout_preset_name(). save_theme()
            # сам синхронизирует старый ключ "layout" от этого значения
            # (см. engine.gui.theme_manager.py save_theme()), поэтому
            # обратная совместимость не ломается.
            "layout_preset": selected_layout,
            "sidebar_side": sidebar_side_var.get(),
            "toolbar_order": toolbar_order_list,
            "header_rainbow": bool(header_rainbow_var.get()),
            "header_rainbow_style": rb_style,
            "header_author_rainbow": bool(header_author_rainbow_var.get()),
            "header_author_rainbow_style": rb_author_style,
            "neon_buttons": neon_buttons_payload,
        }
        save_theme(new_theme)

        # Live: заголовки + neon-кнопки тулбара
        try:
            from engine.gui import header_panel as _hp

            if hasattr(_hp, "apply_layout"):
                _hp.apply_layout({})
        except Exception:
            pass
        try:
            from engine.gui import toolbar as _tb
            from engine.gui.neon_widgets import refresh_neon_button

            for _bname in ("chat_btn", "ai_btn", "styles_btn", "studio_btn", "gen_btn"):
                refresh_neon_button(getattr(_tb, _bname, None))
        except Exception:
            pass

        # ── Live-применение раскладки ко всем панелям (если возможно) ──
        live_applied = False
        if callable(on_layout_changed):
            try:
                preset_dict = get_layout_preset(selected_layout)
                live_applied = bool(on_layout_changed(preset_dict))
            except Exception:
                live_applied = False

        if live_applied:
            messagebox.showinfo(
                _tr("theme_saved_dlg_title"), _tr("theme_saved_live_applied"), parent=win
            )
        else:
            messagebox.showinfo(
                _tr("theme_saved_dlg_title"), _tr("theme_saved_needs_restart"), parent=win
            )
        _close_theme_window()

    _make_button(
        btn_row, _tr("theme_reset_btn"), _close_theme_window, bg=_c("BG_INPUT"), font_size=11
    ).pack(side="right", padx=(8, 0))
    _make_button(
        btn_row, _tr("theme_save_btn"), apply_and_save, bg=_c("BG_ACTIVE"), font_size=11
    ).pack(side="right")

    scrollbar.config(command=canvas.yview)
