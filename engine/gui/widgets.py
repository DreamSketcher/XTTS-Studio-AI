# -*- coding: utf-8 -*-
"""engine/gui/widgets.py — совместимые CTk-виджеты и фабрики виджетов
(перенесено из gui.py: CompatCTkButton/Label/Frame, create_card, create_button, create_entry)."""
import tkinter as tk

import customtkinter as ctk

from engine.gui.colors import Colors, scaled_font_size, scaled_size


class CompatCTkButton(ctk.CTkButton):
    def __init__(
        self,
        *args,
        bg=None,
        fg=None,
        activebackground=None,
        activeforeground=None,
        borderwidth=None,
        relief=None,
        padx=None,
        pady=None,
        bd=None,
        cursor=None,
        **kwargs,
    ):
        if bg is not None:
            kwargs.setdefault("fg_color", bg)
        if fg is not None:
            kwargs.setdefault("text_color", fg)
        if activebackground is not None:
            kwargs.setdefault("hover_color", activebackground)
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("border_width", 0)
        super().__init__(*args, **kwargs)

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        if "bg" in kwargs:
            kwargs["fg_color"] = kwargs.pop("bg")
        if "fg" in kwargs:
            kwargs["text_color"] = kwargs.pop("fg")
        if "activebackground" in kwargs:
            kwargs["hover_color"] = kwargs.pop("activebackground")
        kwargs.pop("activeforeground", None)
        kwargs.pop("borderwidth", None)
        kwargs.pop("relief", None)
        kwargs.pop("bd", None)
        kwargs.pop("cursor", None)
        kwargs.pop("padx", None)
        kwargs.pop("pady", None)
        return super().configure(**kwargs)

    config = configure


class CompatCTkLabel(ctk.CTkLabel):
    """CTkLabel с совместимостью под старые tk.Label .config(bg/fg)."""

    def __init__(self, *args, bg=None, fg=None, **kwargs):
        if bg is not None:
            kwargs.setdefault("fg_color", bg)
        if fg is not None:
            kwargs.setdefault("text_color", fg)
        super().__init__(*args, **kwargs)

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        if "bg" in kwargs:
            kwargs["fg_color"] = kwargs.pop("bg")
        if "fg" in kwargs:
            kwargs["text_color"] = kwargs.pop("fg")
        return super().configure(**kwargs)

    config = configure


class CompatCTkFrame(ctk.CTkFrame):
    def __init__(
        self,
        *args,
        bg=None,
        highlightthickness=None,
        highlightbackground=None,
        bd=None,
        cursor=None,
        padx=None,
        pady=None,
        **kwargs,
    ):
        if bg is not None:
            kwargs.setdefault("fg_color", bg)
        if highlightbackground is not None:
            kwargs.setdefault("border_color", highlightbackground)
        if highlightthickness is not None:
            kwargs.setdefault("border_width", highlightthickness)
        super().__init__(*args, **kwargs)

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        if "bg" in kwargs:
            kwargs["fg_color"] = kwargs.pop("bg")
        if "highlightbackground" in kwargs:
            kwargs["border_color"] = kwargs.pop("highlightbackground")
        kwargs.pop("bd", None)
        kwargs.pop("cursor", None)
        kwargs.pop("padx", None)
        kwargs.pop("pady", None)
        return super().configure(**kwargs)

    config = configure


def create_card(parent, title="", bg=None, padx=10, pady=10):
    # ЛЕНИВЫЕ дефолты: цвета берутся в момент вызова, а не при импорте —
    # иначе смена темы (light/dark) не влияла бы на новые виджеты.
    if bg is None:
        bg = Colors.BG_CARD
    card = CompatCTkFrame(
        parent, bg=bg, fg_color=bg, corner_radius=14, border_width=1, border_color=Colors.BORDER
    )
    if title:
        CompatCTkLabel(
            card,
            text=title,
            bg=bg,
            fg=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(11), "bold"),
            anchor="w",
        ).pack(fill="x", padx=padx, pady=(pady, 5))
    return card


def create_button(
    parent, text, command, bg=None, fg=None, active_bg=None, width=None, height=1, font_size=12
):
    # ЛЕНИВЫЕ дефолты (см. create_card)
    if bg is None:
        bg = Colors.BG_INPUT
    if fg is None:
        fg = Colors.TEXT_MAIN
    if active_bg is None:
        active_bg = Colors.BG_HOVER
    is_bold = "ГЕНЕРИРОВАТЬ" in text or "ОТМЕНА" in text or "GENERATE" in text or "CANCEL" in text
    # ИСПРАВЛЕНО: высота и ширина кнопки раньше не учитывали пользовательский
    # масштаб шрифта из Конструктора темы — рос только сам шрифт (через
    # scaled_font_size), а геометрия кнопки оставалась фиксированной в
    # пикселях. На крупных базовых размерах шрифта текст физически
    # переставал помещаться и обрезался/съезжал за границы кнопки. Теперь
    # высота и ширина масштабируются той же единой функцией scaled_size(),
    # что использует и весь остальной проект — кнопка растёт синхронно с
    # текстом внутри неё. min_size=design-значение — кнопка не должна
    # становиться мельче исходного дизайнерского размера.
    design_height = int(height * 28) if height else 28
    kwargs = dict(
        text=text,
        command=command,
        fg_color=bg,
        text_color=fg,
        hover_color=active_bg,
        border_width=0,
        corner_radius=10,
        # единый центр текста на всех кнопках (Язык генерации / Высокое качество и др.)
        anchor="center",
        font=ctk.CTkFont(
            family="Segoe UI",
            size=scaled_font_size(font_size + 2),
            weight="bold" if is_bold else "normal",
        ),
        height=scaled_size(design_height, min_size=design_height),
    )
    # width в конструкторе — CTk иначе может игнорировать поздний configure(width=…)
    if width:
        kwargs["width"] = scaled_size(int(width), min_size=int(width))
    btn = CompatCTkButton(parent, **kwargs)
    return btn


def create_entry(parent, textvariable, bg=None, fg=None):
    # ЛЕНИВЫЕ дефолты (см. create_card)
    if bg is None:
        bg = Colors.BG_INPUT
    if fg is None:
        fg = Colors.TEXT_MAIN
    return tk.Entry(
        parent,
        textvariable=textvariable,
        bg=bg,
        fg=fg,
        insertbackground=Colors.TEXT_MAIN,
        relief="flat",
        borderwidth=0,
        font=("Segoe UI", scaled_font_size(10)),
        highlightthickness=1,
        highlightbackground=Colors.BORDER,
        highlightcolor=Colors.ACCENT,
    )
