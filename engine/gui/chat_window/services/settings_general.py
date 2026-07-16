from __future__ import annotations

"""Общая страница настроек AI.

Содержит заголовок и placeholder общей страницы, сохраняя её границы
независимыми от API-настроек и страницы локальных моделей.
"""

from i18n import t
from engine.gui.chat_window.custom_widgets import (
    CTK_AVAILABLE,
    CTkFrame,
    CTkLabel,
    CTkButton,
    TkFrame,
    TkLabel,
    TkButton,
    TkRawFrame,
)
from engine.gui.chat_window.ui_utils import _c


def build_general_page(ctx):
    canvas_frame = ctx.canvas_frame
    container = TkFrame(canvas_frame, bg=_c("BG_CARD"))
    container.pack(fill="both", expand=True, padx=20, pady=20)
    TkLabel(
        container,
        text=t("settings_general_title"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 17, "bold"),
    ).pack(anchor="w", pady=(0, 15))
    TkLabel(
        container,
        text=t("settings_general_placeholder"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 12),
        anchor="w",
    ).pack(anchor="w")

    return container
