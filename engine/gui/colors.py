# -*- coding: utf-8 -*-
"""engine/gui/colors.py — палитра приложения (перенесено из gui.py: class Colors).

Поддерживает две темы:
  • dark  — исходная тёмная (значения не изменены);
  • light — мягкая светлая («молочная», слегка книжная).

Все модули обращаются к атрибутам класса Colors, поэтому смена темы
выполняется мутацией этих атрибутов через apply_palette() ДО построения
окон (или перед открытием нового окна — динамические окна берут цвета
в момент создания и сразу получаются в актуальной теме).
"""

# ── Тёмная тема (исходные значения из gui.py) ──
DARK_PALETTE = {
    "BG_DARK": "#0d1117",
    "BG_CARD": "#161b22",
    "BG_INPUT": "#21262d",
    "BG_HOVER": "#30363d",
    "BG_ACTIVE": "#238636",
    "BG_DANGER": "#da3633",
    "TEXT_MAIN": "#f0f6fc",
    "TEXT_DIM": "#8b949e",
    "TEXT_SUCCESS": "#3fb950",
    "TEXT_WARNING": "#d29922",
    "TEXT_ERROR": "#f85149",
    "ACCENT": "#58a6ff",
    "BORDER": "#30363d",
    "PROGRESS_BG": "#21262d",
    "PROGRESS_FG": "#238636",
    "CHUNK_BG": "#2d5a8e",
    "CHUNK_FG": "#ffffff",
    "TOOLTIP_BG": "#30363d",
    "MENU_BG": "#1c2330",
    "MENU_HOVER": "#2a3142",
    "MENU_ACTIVE": "#1f6feb",
    # ── AI accent colour (muted purple-blue) ──
    "AI_ACCENT": "#7c3aed",
    "AI_ACCENT_HOVER": "#6d28d9",
    "AI_GROUP_BG": "#1a1730",
    # ── Toolbar group backgrounds ──
    "GROUP_BG": "#181d25",
    "GROUP_FILE_BG": "#161b22",
    "GROUP_OUTPUT_BG": "#161b22",
    "GROUP_ACTION_BG": "#161b22",
    # ── низ градиента главного окна ──
    "GRADIENT_BOTTOM": "#1a1f29",
}

# ── Светлая тема: мягкий молочно-книжный тон (не «вычурно белая») ──
LIGHT_PALETTE = {
    "BG_DARK": "#f4efe6",  # молочный фон
    "BG_CARD": "#faf6ee",  # карточки — чуть светлее, кремовые
    "BG_INPUT": "#fffdf7",  # поля ввода — тёплый почти-белый
    "BG_HOVER": "#e9e2d2",  # наведение — приглушённый бежевый
    "BG_ACTIVE": "#2da44e",
    "BG_DANGER": "#d1242f",
    "TEXT_MAIN": "#3a352d",  # тёмно-коричневатый «книжный» текст
    "TEXT_DIM": "#857d6e",
    "TEXT_SUCCESS": "#1a7f37",
    "TEXT_WARNING": "#9a6700",
    "TEXT_ERROR": "#cf222e",
    "ACCENT": "#0969da",
    "BORDER": "#d9d0bd",
    "PROGRESS_BG": "#e9e2d2",
    "PROGRESS_FG": "#2da44e",
    "CHUNK_BG": "#cfe3f7",  # мягкая подсветка чанка
    "CHUNK_FG": "#1f2328",
    "TOOLTIP_BG": "#efe8d8",
    "MENU_BG": "#f7f2e7",
    "MENU_HOVER": "#eae2cf",
    "MENU_ACTIVE": "#0969da",
    "AI_ACCENT": "#6639ba",
    "AI_ACCENT_HOVER": "#835bd6",
    "AI_GROUP_BG": "#f0ebf9",
    "GROUP_BG": "#f1ecdf",
    "GROUP_FILE_BG": "#faf6ee",
    "GROUP_OUTPUT_BG": "#faf6ee",
    "GROUP_ACTION_BG": "#faf6ee",
    "GRADIENT_BOTTOM": "#e9e1d0",
}

PALETTES = {"dark": DARK_PALETTE, "light": LIGHT_PALETTE}


class Colors:
    """Атрибуты заполняются apply_palette(); по умолчанию — тёмная тема."""

    pass


# ── Глобальный масштаб размера шрифта ──
# Пользователь выбирает БАЗОВЫЙ размер (в pt) через слайдер в Конструкторе
# темы. Все места в проекте, где сейчас захардкожен конкретный размер
# шрифта (font=("Segoe UI", N, ...)), должны при построении окна
# вызывать scaled_font_size(N) вместо голого N — тогда N масштабируется
# пропорционально относительно исходного "дизайнерского" размера
# BASE_FONT_SIZE_DEFAULT (10pt — это historically самый частый размер
# текста в проекте, см. fonts.size_main в theme_manager.DEFAULT_THEME).
#
# Пример: пользователь поставил базовый размер 14 (вместо 10) — тогда
# scale = 14/10 = 1.4, и любой хардкод font=(..., 9) отрисуется как
# round(9*1.4) = 13pt, font=(..., 16) — как round(16*1.4) = 22pt и т.д.
# Так сохраняется визуальная иерархия (заголовки крупнее подписей) при
# любом выбранном базовом размере.
#
# ИСКЛЮЧЕНИЕ (по требованию): основное текстовое поле ввода/редактор
# (engine/gui/textbox.py, виджет text_box) НЕ участвует в этом
# масштабировании — у него уже есть собственный независимый механизм
# размера шрифта (text_font_size, FONT_SIZE_MIN/MAX, слайдер "Aa").
BASE_FONT_SIZE_DEFAULT = 10
MIN_SCALED_FONT_SIZE = 6
MAX_SCALED_FONT_SIZE = 48

_font_scale_state = {"base_size": BASE_FONT_SIZE_DEFAULT}


def get_font_base_size() -> int:
    """Текущий выбранный пользователем базовый размер шрифта (pt)."""
    return _font_scale_state["base_size"]


def get_font_scale() -> float:
    """Коэффициент масштаба = текущий_базовый / дефолтный_базовый (10pt)."""
    return _font_scale_state["base_size"] / BASE_FONT_SIZE_DEFAULT


def set_font_base_size(base_size: int) -> None:
    """Устанавливает новый базовый размер шрифта (без сохранения в JSON —
    сохранение делает theme_manager.set_font_base_size(), эта функция
    только держит значение в памяти для scaled_font_size())."""
    try:
        base_size = int(base_size)
    except Exception:
        return
    base_size = max(6, min(24, base_size))
    _font_scale_state["base_size"] = base_size


def scaled_font_size(design_size: int) -> int:
    """Возвращает design_size, промасштабированный текущим коэффициентом
    (см. get_font_scale()), округлённый и ограниченный разумными
    пределами (MIN/MAX_SCALED_FONT_SIZE), чтобы экстремальные пользовательские
    значения не ломали раскладку окон (слишком мелкий/огромный шрифт)."""
    try:
        scale = get_font_scale()
        result = round(design_size * scale)
        return max(MIN_SCALED_FONT_SIZE, min(MAX_SCALED_FONT_SIZE, result))
    except Exception:
        return design_size


# ── Масштабирование произвольной геометрии (высота/ширина кнопок, диаметр
# круглых кнопок, отступы и т.д.) — единая точка правды, использующая тот
# же коэффициент get_font_scale(), что и шрифт. Раньше в разных местах
# (widgets.create_button, output_window._round_btn, history_window.
# _round_btn) один и тот же расчёт "diameter * get_font_scale()" был
# продублирован вручную с разной обвязкой (где-то min_size был, где-то
# нет) — это гарантированный источник рассинхронизации при следующей
# правке. scaled_size() — единственное место, где стоит поменять формулу
# масштабирования геометрии, если она когда-нибудь понадобится.
MIN_SCALED_SIZE = 20
MAX_SCALED_SIZE = 200


def scaled_size(design_size, min_size=None, max_size=None):
    """Масштабирует пиксельный размер (высоту/ширину/диаметр виджета)
    тем же коэффициентом, что и scaled_font_size() — гарантирует, что
    кнопки и другие геометрически заданные виджеты растут/уменьшаются
    синхронно с текстом внутри них при смене базового размера шрифта.

    min_size/max_size — необязательные локальные пределы конкретного
    вызова (например, круглая кнопка не должна становиться меньше своего
    исходного диаметра — используй min_size=design_size); если не
    указаны, применяются глобальные MIN/MAX_SCALED_SIZE.
    """
    try:
        scale = get_font_scale()
        result = round(design_size * scale)
    except Exception:
        result = design_size
    lo = MIN_SCALED_SIZE if min_size is None else min_size
    hi = MAX_SCALED_SIZE if max_size is None else max_size
    return max(lo, min(hi, result))


def load_font_scale_from_settings() -> None:
    """Читает сохранённый базовый размер шрифта из theme_settings.json
    (через theme_manager) и применяет его к текущему состоянию масштаба.
    Вызывается при старте приложения (apply_theme() в theme.py) — аналогично
    apply_palette(). try/except — сбой чтения не должен ронять приложение,
    в худшем случае останется дефолтный размер (без масштабирования)."""
    try:
        from engine.gui import theme_manager

        base_size = theme_manager.get_font_base_size()
        set_font_base_size(base_size)
    except Exception:
        pass


def apply_palette(theme: str = "dark") -> None:
    """Мутирует атрибуты Colors под выбранную тему ('dark' | 'light').

    ДОПОЛНЕНО: после применения встроенной палитры (DARK_PALETTE/
    LIGHT_PALETTE) поверх неё накладываются пользовательские
    переопределения из theme_settings.json (theme_manager.get_custom_colors),
    если они есть. Это делает окно "Конструктор темы" реально влияющим на
    внешний вид приложения — до этой правки секция цветов в конструкторе
    темы сохраняла значения в JSON, которые никто и никогда не читал
    обратно в Colors (см. историю комментариев в theme_manager.py).

    Импорт theme_manager делается ЛОКАЛЬНО внутри функции (а не в начале
    файла), чтобы избежать циклического импорта: theme_manager.py в этом
    проекте ни на что из engine.gui не ссылается, но colors.py — базовый
    модуль, который должен оставаться независимым от остального GUI на
    уровне импортов верхнего файла (стиль проекта: engine/ = 0 импортов
    tkinter, colors.py — один из первых модулей, что импортируется).
    """
    palette = PALETTES.get(theme, DARK_PALETTE)
    for key, value in palette.items():
        setattr(Colors, key, value)

    # Наложение пользовательских переопределений (см. docstring выше).
    # try/except — чтобы сбой чтения JSON никогда не мешал запуску
    # приложения: в худшем случае просто останется встроенная палитра.
    try:
        from engine.gui import theme_manager

        custom = theme_manager.get_custom_colors(theme)
        for key, value in custom.items():
            # Применяем только к уже существующим атрибутам палитры —
            # опечатка в имени ключа (или устаревший ключ из старой
            # версии конструктора темы) не создаст "мусорный" атрибут
            # Colors, который нигде не используется.
            if hasattr(Colors, key):
                setattr(Colors, key, value)
    except Exception:
        pass


# Инициализация по умолчанию — тёмная (как в исходном gui.py)
apply_palette("dark")
