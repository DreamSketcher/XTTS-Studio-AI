# -*- coding: utf-8 -*-
"""engine/gui/statusbar.py — статусбар и прогресс-бар
(перенесено из gui.py: set_status, set_stage, set_progress, секция STATUS BAR).

PATCH 2026-07-14: плавное появление/исчезновение кнопки отмены
через AnimationManager (slide-in/slide-out по ширине).
"""
import tkinter as tk

import customtkinter as ctk

from i18n import t
from engine.gui.colors import Colors, scaled_font_size

# Внедряются из main_window: root, status_var, stage_var, progress_value
root = None
status_var = None
stage_var = None
progress_value = None

status_frame = None
progress_bar = None
cancel_button = None
_on_cancel_callback = None

_CANCEL_BTN_WIDTH = 90


def init(**deps):
    """Внедрение зависимостей из engine.gui.main_window.
    Имена совпадают с именами глобальных переменных исходного gui.py."""
    globals().update(deps)


def set_status(text):
    root.after(0, lambda: status_var.set(text))


def set_stage(text):
    root.after(0, lambda: stage_var.set(text))


def set_progress(value):
    try:
        value = max(0, min(100, int(value)))
    except Exception:
        return
    root.after(
        0,
        lambda: (
            progress_value.set(value),
            globals().get("progress_bar") and progress_bar.set(value / 100),
        ),
    )


def show_cancel_button(on_cancel):
    """
    Показывает кнопку "Отмена" в правом нижнем углу статус-бара.
    on_cancel — функция без аргументов, вызывается по нажатию (из UI-потока).

    PATCH 2026-07-14: плавный slide-in (ширина 1 → _CANCEL_BTN_WIDTH).
    """
    global _on_cancel_callback
    _on_cancel_callback = on_cancel

    def _show():
        if cancel_button is None:
            return
        cancel_button.configure(state="normal", text=t("update_cancel_btn"))
        # Slide-in: стартуем с минимальной ширины
        cancel_button.configure(width=1)
        cancel_button.pack(side="right", padx=(8, 0))
        cancel_button.update_idletasks()

        try:
            from engine.gui.animation_manager import AnimationManager

            mgr = AnimationManager.get()
            if not mgr._no_op:
                mgr.animate(
                    target=cancel_button,
                    property_setter=lambda v: cancel_button.configure(width=max(1, int(v))),
                    start=1,
                    end=_CANCEL_BTN_WIDTH,
                    duration_ms=200,
                    easing="ease_out",
                    animation_id="_cancel_slide_in",
                )
            else:
                cancel_button.configure(width=_CANCEL_BTN_WIDTH)
        except Exception:
            cancel_button.configure(width=_CANCEL_BTN_WIDTH)

    root.after(0, _show)


def hide_cancel_button():
    """Прячет кнопку "Отмена" — обновление завершилось (успешно, с ошибкой или было отменено).

    PATCH 2026-07-14: плавный slide-out (ширина → 1, затем pack_forget).
    """
    global _on_cancel_callback
    _on_cancel_callback = None

    def _hide():
        if cancel_button is None:
            return

        try:
            from engine.gui.animation_manager import AnimationManager

            mgr = AnimationManager.get()
            if not mgr._no_op:
                current_w = max(1, cancel_button.winfo_width() or _CANCEL_BTN_WIDTH)
                mgr.animate(
                    target=cancel_button,
                    property_setter=lambda v: cancel_button.configure(width=max(1, int(v))),
                    start=current_w,
                    end=1,
                    duration_ms=150,
                    easing="ease_in",
                    on_complete=lambda: cancel_button.pack_forget(),
                    animation_id="_cancel_slide_out",
                )
                return
        except Exception:
            pass
        cancel_button.pack_forget()

    root.after(0, _hide)


def set_cancel_button_cancelling():
    """
    Мгновенная обратная связь по нажатию — сама отмена может занять
    короткое время (флаг проверяется между блоками скачивания файла),
    поэтому кнопка сразу блокируется и меняет подпись, чтобы не было
    впечатления, что нажатие не сработало.
    """

    def _set():
        if cancel_button is None:
            return
        cancel_button.configure(state="disabled", text=t("update_cancelling_btn"))

    root.after(0, _set)


def _handle_cancel_click():
    if _on_cancel_callback:
        set_cancel_button_cancelling()
        _on_cancel_callback()


def build_statusbar(right_panel):
    global status_frame, progress_bar, cancel_button
    status_frame = tk.Frame(right_panel, bg=Colors.BG_CARD)
    status_frame.pack(fill="x", side="bottom", pady=(0, 0))
    progress_bar = ctk.CTkProgressBar(
        status_frame,
        orientation="horizontal",
        height=14,  # чуть выше — полоса больше не выглядит плоской
        fg_color=Colors.PROGRESS_BG,
        progress_color=Colors.PROGRESS_FG,
        corner_radius=7,
    )
    progress_bar.pack(fill="x", padx=10, pady=(10, 5))
    progress_bar.set(0)

    bottom_row = tk.Frame(status_frame, bg=Colors.BG_CARD)
    bottom_row.pack(fill="x", padx=10, pady=(0, 10))

    tk.Label(
        bottom_row,
        textvariable=status_var,
        anchor="w",
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(11)),
    ).pack(side="left", fill="x", expand=True)

    # Кнопка "Отмена" — правый нижний угол статус-бара. Скрыта по умолчанию,
    # показывается только на время активного обновления (show_cancel_button /
    # hide_cancel_button вызываются из engine/gui/env_settings.py).
    cancel_button = ctk.CTkButton(
        bottom_row,
        text=t("update_cancel_btn"),
        width=_CANCEL_BTN_WIDTH,
        height=24,
        corner_radius=6,
        fg_color=getattr(Colors, "BG_INPUT", Colors.BG_CARD),
        hover_color=getattr(Colors, "TEXT_ERROR", Colors.PROGRESS_FG),
        text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(10)),
        command=_handle_cancel_click,
    )
    # Не паковим сразу — pack() вызывается в show_cancel_button()
