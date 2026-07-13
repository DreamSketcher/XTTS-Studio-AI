# -*- coding: utf-8 -*-
"""engine/gui/styles_menu.py — всплывающее меню «Стили» в стиле Аудио/История"""
import tkinter as tk
import os

from i18n import t
from engine.paths import BASE_DIR

try:
    from engine.paths import ICON_PATH
except ImportError:
    ICON_PATH = os.path.join(str(BASE_DIR), "icon.ico")

from engine.gui.colors import Colors, scaled_font_size, scaled_size
from engine.gui.widgets import CompatCTkFrame, CompatCTkLabel
from engine.gui.presets import open_quality_settings

root = None
quality_var = None
save_settings = None
PRESET_DESCRIPTIONS = {}
styles_btn = None

PRESET_HINT = t("tip_quality_default")
STYLES_HINT = t("tip_styles")


def init(**deps):
    globals().update(deps)


def open_styles_menu(event=None):
    # outer with rounded corners via CompatCTkFrame
    menu = tk.Toplevel(root)
    menu.wm_overrideredirect(True)
    menu.configure(bg=Colors.BG_DARK)
    menu.attributes("-topmost", True)

    # rounded card container
    card = CompatCTkFrame(
        menu, fg_color=Colors.BG_CARD, corner_radius=18, border_width=1, border_color=Colors.BORDER
    )
    card.pack(fill="both", expand=True, padx=2, pady=2)

    inner = tk.Frame(card, bg=Colors.BG_CARD)
    inner.pack(fill="both", expand=True, padx=8, pady=8)

    presets = [
        ("📖 " + t("preset_narrative"), "Нарратив"),
        ("⚡ " + t("preset_dynamic"), "Динамика"),
        ("🎭 " + t("preset_expressive"), "Экспрессия"),
    ]
    default_desc = "Наведите на пресет — здесь появится описание."

    def close_menu():
        try:
            menu.destroy()
        except Exception:
            pass
        try:
            root.unbind_all("<Button-1>")
        except Exception:
            pass

    def select_preset(name):
        quality_var.set(name)
        save_settings()

    def select_and_open(name):
        quality_var.set(name)
        save_settings()
        close_menu()
        open_quality_settings(name)

    for label, value in presets:
        is_active = quality_var.get() == value
        item = CompatCTkFrame(
            inner,
            fg_color=Colors.MENU_ACTIVE if is_active else Colors.BG_CARD,
            corner_radius=12,
            border_width=0,
        )
        item.pack(fill="x", pady=3)

        row = tk.Frame(item, bg=item.cget("fg_color") if hasattr(item, "cget") else Colors.BG_CARD)
        # fallback bg
        try:
            bg = item._fg_color if hasattr(item, "_fg_color") else Colors.BG_CARD
        except:
            bg = Colors.BG_CARD

        lbl = tk.Label(
            row,
            text=label,
            bg=bg,
            fg=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(13), "bold" if is_active else "normal"),
            padx=12,
            pady=10,
            anchor="w",
            cursor="hand2",
        )
        lbl.pack(fill="x")

        def on_enter(e, w=item, active=is_active, name=value, l=lbl):
            if not active:
                try:
                    w.configure(fg_color=Colors.MENU_HOVER)
                    l.configure(bg=Colors.MENU_HOVER)
                except Exception:
                    pass
            desc_label.configure(text=PRESET_DESCRIPTIONS.get(name, default_desc))

        def on_leave(e, w=item, active=is_active, l=lbl):
            if not active:
                try:
                    w.configure(fg_color=Colors.BG_CARD)
                    l.configure(bg=Colors.BG_CARD)
                except Exception:
                    pass

        for w in (item, row, lbl):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda e, n=value: select_preset(n))
            w.bind("<Double-Button-1>", lambda e, n=value: select_and_open(n))

        row.pack(fill="x")

    sep = tk.Frame(inner, bg=Colors.BORDER, height=1)
    sep.pack(fill="x", padx=8, pady=8)

    desc_card = CompatCTkFrame(inner, fg_color=Colors.BG_DARK, corner_radius=12, border_width=0)
    desc_card.pack(fill="x", pady=(0, 4))

    desc_label = tk.Label(
        desc_card,
        text=default_desc,
        bg=Colors.BG_DARK,
        fg=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(11)),
        justify="left",
        anchor="w",
        wraplength=240,
        padx=12,
        pady=8,
    )
    desc_label.pack(fill="x")

    menu.update_idletasks()
    menu_w = menu.winfo_reqwidth()
    menu_h = menu.winfo_reqheight()
    x = styles_btn.winfo_rootx()
    y = styles_btn.winfo_rooty() - menu_h - 10
    if y < 0:
        y = styles_btn.winfo_rooty() + styles_btn.winfo_height() + 10
    menu.wm_geometry(f"{menu_w+20}x{menu_h+20}+{x}+{y}")

    def click_outside(e):
        try:
            if not menu.winfo_exists():
                return
            wx, wy = menu.winfo_rootx(), menu.winfo_rooty()
            ww, wh = menu.winfo_width(), menu.winfo_height()
            if not (wx <= e.x_root <= wx + ww and wy <= e.y_root <= wy + wh):
                close_menu()
        except Exception:
            close_menu()

    root.after(100, lambda: root.bind_all("<Button-1>", click_outside, add="+"))
    menu.bind("<FocusOut>", lambda e: close_menu())

    # icon fix for popup? not needed but set transparent bg
    try:
        menu.attributes("-transparentcolor", Colors.BG_DARK)
    except Exception:
        pass
