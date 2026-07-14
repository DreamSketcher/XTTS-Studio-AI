# -*- coding: utf-8 -*-
"""engine/gui/layout.py — базовая раскладка главного окна
(перенесено из gui.py, секция LAYOUT: градиент, main_container, left/right panel).

Дополнено: левая панель — выдвижная. Между панелями расположена
вертикальная полоса-переключатель с заметной кнопкой-стрелкой («◀»/«▶»),
клик по которой скрывает или показывает левую панель. Положение панели
сохраняется в settings.json (ключ left_panel_visible) и восстанавливается
при следующем запуске.

PATCH 2026-07-15: плавный slide боковой панели через AnimationManager.
"""
import json
import os
import tkinter as tk

from engine.gui.colors import Colors, scaled_font_size
from engine.gui.gradient import GradientBackground
from engine.gui.widgets import CompatCTkFrame

# --- Layout Preset API ---
# Делегируем в theme_manager, единственный источник истины
try:
    from . import theme_manager

    def get_layout_preset(name: str | None = None) -> dict:
        return theme_manager.get_layout_preset(name)

except Exception:
    # Fallback, если theme_manager ещё не готов
    def get_layout_preset(name=None):
        return {
            "left_panel_width": 260,
            "padding_main_x": 8,
            "padding_main_y": 14,
            "panel_spacing": 2,
            "toggle_strip_width": 22,
            "right_panel_left_pad": 8,
        }


_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "settings.json",
)

main_gradient = None
main_container = None
left_panel = None
right_panel = None

# ── Состояние выдвижной левой панели ──
toggle_strip = None
_toggle_arrow = None
_toggle_btn = None
_left_visible = True
_current_layout_preset = {}
# ── NEW: сторона боковой панели ──
_sidebar_side = "left"  # "left" | "right"


def _load_saved_panel_state() -> bool:
    """Читает сохранённое положение левой панели (по умолчанию — видима)."""
    try:
        with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("left_panel_visible", True))
    except Exception:
        return True


def _save_panel_state() -> None:
    """Сохраняет положение левой панели в settings.json
    (не трогая остальные ключи)."""
    try:
        try:
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        data["left_panel_visible"] = _left_visible
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── PATCH 2026-07-15: анимированный toggle ──────────────────────


def _animate_left_panel_width(target_width: int, duration_ms: int = 250, on_complete=None):
    """Плавно меняет ширину left_panel через публичный AnimationManager.animate()."""
    try:
        from engine.gui.animation_manager import AnimationManager

        try:
            left_panel.update_idletasks()
            start_width = int(left_panel.winfo_width())
        except Exception:
            start_width = 1
        if start_width <= 0:
            try:
                start_width = int(left_panel.cget("width"))
            except Exception:
                start_width = 1

        def _set_width(value):
            left_panel.configure(width=max(0, int(round(value))))

        mgr = AnimationManager.get()
        mgr.animate(
            target=left_panel,
            property_setter=_set_width,
            start=start_width,
            end=max(0, int(target_width)),
            duration_ms=duration_ms,
            easing="ease_out",
            on_complete=on_complete,
            animation_id="_sidebar_slide",
        )
    except Exception:
        try:
            left_panel.configure(width=target_width)
        except Exception:
            pass
        if on_complete:
            try:
                on_complete()
            except Exception:
                pass


def toggle_left_panel(event=None):
    """Скрывает/показывает левую панель (клик по полосе-переключателю).

    PATCH 2026-07-15: плавная анимация ширины вместо pack_forget/pack.
    """
    global _left_visible
    try:
        preset = _current_layout_preset
        panel_spacing = preset.get("panel_spacing", 2)
        right_pad = preset.get("right_panel_left_pad", 8)
        # симметричный зазор — кнопка визуально по центру
        gutter = 2

        if _left_visible:
            # PATCH 2026-07-15: плавный slide-out
            def _after_hide():
                global _left_visible
                try:
                    left_panel.pack_forget()
                except Exception:
                    pass
                _left_visible = False
                _save_panel_state()
                _update_toggle_arrow()
                try:
                    left_panel.pack_propagate(False)
                except Exception:
                    pass
                try:
                    main_container.update_idletasks()
                except Exception:
                    pass

            _animate_left_panel_width(0, duration_ms=250, on_complete=_after_hide)
        else:
            # PATCH 2026-07-15: плавный slide-in
            if _sidebar_side == "right":
                # Фиксированные элементы справа пакуются ПЕРВЫМИ от правого
                # края, а expand-контент — последним. Иначе right_panel,
                # упакованный первым с expand=True, забирает pack-cavity и
                # перекрывает/вытесняет toggle и раскрываемый sidebar.
                for widget in (left_panel, toggle_strip, right_panel):
                    try:
                        widget.pack_forget()
                    except Exception:
                        pass
                left_panel.pack(side="right", fill="y", padx=(gutter, 0))
                toggle_strip.pack(side="right", fill="y", padx=(gutter, gutter))
                try:
                    toggle_strip.pack_propagate(False)
                except Exception:
                    pass
                right_panel.pack(side="left", fill="both", expand=True)
            else:
                left_panel.pack(side="left", fill="y", padx=(0, gutter), before=toggle_strip)

            left_panel.configure(width=1)
            left_panel.pack_propagate(False)
            left_panel.update_idletasks()

            target_w = preset.get("left_panel_width", 260)

            def _after_show():
                global _left_visible
                _left_visible = True
                _save_panel_state()
                _update_toggle_arrow()
                try:
                    main_container.update_idletasks()
                except Exception:
                    pass

            _animate_left_panel_width(target_w, duration_ms=250, on_complete=_after_show)
    except Exception:
        pass


def _update_toggle_arrow():
    """Обновляет текст/вид кнопки-переключателя с учётом стороны и видимости"""
    global _toggle_arrow, _toggle_btn
    try:
        # Определяем направление стрелки
        # Когда панель видима — стрелка указывает наружу (скрыть)
        # Когда скрыта — указывает внутрь (показать)
        if _sidebar_side == "right":
            arrow = "▶" if _left_visible else "◀"
        else:
            arrow = "◀" if _left_visible else "▶"
        # пробуем оба варианта виджета: CTkButton и tk.Label
        if "_toggle_btn" in globals() and _toggle_btn is not None:
            try:
                _toggle_btn.configure(text=arrow)
                return
            except Exception:
                pass
        if _toggle_arrow is not None:
            _toggle_arrow.config(text=arrow)
    except Exception:
        pass


def _get_sidebar_side() -> str:
    """Читает сторону боковой панели из theme_manager, fallback = left"""
    try:
        if theme_manager and hasattr(theme_manager, "get_sidebar_side"):
            return theme_manager.get_sidebar_side()
    except Exception:
        pass
    return "left"


def apply_sidebar_side(side: str) -> bool:
    """Live-переключение стороны боковой панели. Возвращает True если применилось."""
    global _sidebar_side, _left_visible
    side = side if side in ("left", "right") else "left"
    if left_panel is None or right_panel is None or toggle_strip is None or main_container is None:
        # виджеты ещё не построены — просто запоминаем
        _sidebar_side = side
        return False
    try:
        preset = _current_layout_preset or {}
        panel_spacing = preset.get("panel_spacing", 2)
        right_pad = preset.get("right_panel_left_pad", 8)
        # симметричный зазор вокруг кнопки-переключателя
        # было: слева 2px, справа 8px — визуально кнопка прижата влево
        # стало: равномерно с обеих сторон
        gutter = 2

        # Снимаем все три панели с pack
        for w in (left_panel, toggle_strip, right_panel):
            try:
                w.pack_forget()
            except Exception:
                pass

        if side == "right":
            # С правой стороны сначала резервируем sidebar и toggle от
            # правого края. Expand-контент пакуется последним и занимает
            # только оставшееся пространство слева.
            if _left_visible:
                left_panel.pack(side="right", fill="y", padx=(gutter, 0))
            toggle_strip.pack(side="right", fill="y", padx=(gutter, gutter))
            toggle_strip.pack_propagate(False)
            right_panel.pack(side="left", fill="both", expand=True)
        else:
            # Сайдбар слева (классика)
            if _left_visible:
                left_panel.pack(side="left", fill="y", padx=(0, gutter))
            # симметричный отступ с обеих сторон кнопки
            toggle_strip.pack(side="left", fill="y", padx=(gutter, gutter))
            toggle_strip.pack_propagate(False)
            right_panel.pack(side="left", fill="both", expand=True)

        _sidebar_side = side
        _update_toggle_arrow()

        # PATCH 2026-07-15: плавная анимация ширины после repack
        if _left_visible:
            left_panel.configure(width=1)
            left_panel.pack_propagate(False)
            target_w = preset.get("left_panel_width", 260)
            _animate_left_panel_width(target_w, duration_ms=200)

        # обновляем геометрию
        try:
            main_container.update_idletasks()
        except Exception:
            pass
        return True
    except Exception as e:
        # print(f"[layout] apply_sidebar_side error: {e}")
        return False


def build_layout(root, preset: dict | None = None, sidebar_side: str | None = None):
    global main_gradient, main_container, left_panel, right_panel
    global toggle_strip, _toggle_arrow, _toggle_btn, _left_visible, _current_layout_preset, _sidebar_side

    # Загружаем пресет раскладки
    if preset is None:
        preset = get_layout_preset()
    _current_layout_preset = preset.copy()

    # Извлекаем геометрию из пресета (Classic = значения по умолчанию, идентичные старому поведению)
    left_panel_width = preset.get("left_panel_width", 260)
    padding_main_x = preset.get("padding_main_x", 8)
    padding_main_y = preset.get("padding_main_y", 14)
    # panel_spacing и right_panel_left_pad используются в apply_sidebar_side
    toggle_strip_width = preset.get("toggle_strip_width", 22)

    main_gradient = GradientBackground(root, Colors.BG_DARK, Colors.GRADIENT_BOTTOM)
    main_container = CompatCTkFrame(root, fg_color="transparent", bg="transparent", corner_radius=0)
    main_container.pack(fill="both", expand=True, padx=padding_main_x, pady=padding_main_y)

    # ── Создаём виджеты БЕЗ pack — pack сделает apply_sidebar_side ──
    left_panel = CompatCTkFrame(
        main_container,
        fg_color="transparent",
        bg="transparent",
        width=left_panel_width,
        corner_radius=0,
    )
    left_panel.pack_propagate(False)

    # ── Полоса-переключатель (обновлённый UI: аккуратная округлая кнопка) ──
    # Делаем toggle_strip прозрачным контейнером, а внутри — закруглённую кнопку,
    # стилизованную под остальные кнопки приложения (CTkButton).
    # Это централизует визуально переключатель и делает отступы симметричными.
    # PATCH 2026-07-09 rev2: уменьшена ширина кнопки по просьбе пользователя
    toggle_strip_width = max(16, preset.get("toggle_strip_width", 16))
    toggle_strip = CompatCTkFrame(
        main_container,
        fg_color="transparent",
        bg="transparent",
        width=toggle_strip_width,
        corner_radius=0,
    )
    toggle_strip.pack_propagate(False)

    # Попробуем CTkButton (закруглённый), fallback → tk.Label
    _toggle_btn = None
    _toggle_arrow = None
    try:
        import customtkinter as ctk

        # Уменьшенная ширина: 18px вместо 26px, высота 44px вместо 56px
        _toggle_btn = ctk.CTkButton(
            toggle_strip,
            text="◀",
            width=14,
            height=36,
            corner_radius=8,
            fg_color=Colors.BG_CARD,
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_DIM,
            border_width=1,
            border_color=Colors.BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=scaled_font_size(10), weight="bold"),
            command=toggle_left_panel,
        )
        _toggle_btn.place(relx=0.5, rely=0.5, anchor="center")
        # тултип-подсказка
        try:
            from engine.gui.tooltip import ToolTip

            ToolTip(_toggle_btn, "Скрыть/показать боковую панель")
        except Exception:
            pass
    except Exception:
        # fallback: старый tk.Label
        _toggle_arrow = tk.Label(
            toggle_strip,
            text="◀",
            bg=Colors.BG_CARD,
            fg=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(13), "bold"),
            cursor="hand2",
        )
        _toggle_arrow.place(relx=0.5, rely=0.5, anchor="center")
        for w in (toggle_strip, _toggle_arrow):
            w.bind("<Button-1>", toggle_left_panel)
            w.bind(
                "<Enter>",
                lambda e: (
                    _toggle_arrow.config(fg=Colors.ACCENT),
                    (
                        toggle_strip.configure(fg_color=Colors.BG_HOVER)
                        if hasattr(toggle_strip, "configure")
                        else None
                    ),
                ),
            )
            w.bind("<Leave>", lambda e: (_toggle_arrow.config(fg=Colors.TEXT_MAIN)))

    right_panel = CompatCTkFrame(
        main_container, fg_color="transparent", bg="transparent", corner_radius=0
    )

    _left_visible = True

    # ── Определяем сторону боковой панели ──
    if sidebar_side is None:
        sidebar_side = _get_sidebar_side()
    _sidebar_side = sidebar_side if sidebar_side in ("left", "right") else "left"

    # Применяем раскладку (pack в правильном порядке)
    apply_sidebar_side(_sidebar_side)

    # ── Восстановление сохранённого положения панели ──
    if not _load_saved_panel_state():
        # Панель была скрыта в прошлой сессии — скрываем без записи в файл.
        # Сначала синхронизируем state, затем обновляем любой тип кнопки
        # через общий helper (CTkButton или fallback tk.Label).
        try:
            left_panel.pack_forget()
        except Exception:
            pass
        _left_visible = False
        _update_toggle_arrow()

    return main_container, left_panel, right_panel


def apply_layout_preset(preset: dict) -> bool:
    """
    Live-применение пресета раскладки.
    Возвращает True если хоть что-то применилось.

    ИСПРАВЛЕНО: раньше ширина left_panel и отступы main_container намеренно
    НЕ применялись live («чтобы не сломать pack-геометрию») — но это как раз
    ГЛАВНЫЕ визуальные параметры, отличающие Classic/Compact/Wide, поэтому
    переключение пресетов выглядело так, будто ничего не происходит.
    На практике left_panel создаётся с pack_propagate(False) (см. build_layout
    выше), поэтому left_panel.configure(width=...) и pack_configure(padx=...)
    у main_container/left_panel/toggle_strip применяются мгновенно и безопасно.

    PATCH 2026-07-15: анимированная смена ширины через AnimationManager.
    """
    global _current_layout_preset
    _current_layout_preset = preset.copy()
    changed = False

    # 1. Ширина полосы-переключателя (toggle_strip)
    try:
        if toggle_strip is not None:
            w = preset.get("toggle_strip_width", 22)
            toggle_strip.config(width=w)
            changed = True
    except Exception:
        pass

    # 2. Ширина левой панели — PATCH 2026-07-15: плавная анимация
    try:
        if left_panel is not None:
            new_width = preset.get("left_panel_width", 260)
            if _left_visible:
                _animate_left_panel_width(new_width, duration_ms=200)
            else:
                left_panel.configure(width=new_width)
            changed = True
    except Exception:
        pass

    # 3. Отступы главного контейнера (main_container padx/pady) — live
    try:
        if main_container is not None:
            padx = preset.get("padding_main_x", 8)
            pady = preset.get("padding_main_y", 14)
            main_container.pack_configure(padx=padx, pady=pady)
            changed = True
    except Exception:
        pass

    # 4-5. Симметричный зазор вокруг кнопки-переключателя
    try:
        spacing = preset.get("panel_spacing", 2)
        right_pad = preset.get("right_panel_left_pad", 8)
        gutter = 2
        if left_panel is not None and _left_visible:
            if _sidebar_side == "right":
                left_panel.pack_configure(padx=(gutter, 0))
            else:
                left_panel.pack_configure(padx=(0, gutter))
            changed = True
        if toggle_strip is not None:
            toggle_strip.pack_configure(padx=(gutter, gutter))
            changed = True
    except Exception:
        pass

    return changed
