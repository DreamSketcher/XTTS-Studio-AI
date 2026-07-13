# -*- coding: utf-8 -*-
"""engine/gui/ai_status_window.py — окно «AI статус» в стиле Аудио/История"""
import tkinter as tk
import os

from i18n import t
from engine.paths import BASE_DIR

try:
    from engine.paths import ICON_PATH
except ImportError:
    ICON_PATH = os.path.join(str(BASE_DIR), "icon.ico")

from engine.gui.colors import Colors, scaled_font_size, scaled_size
from engine.gui.widgets import CompatCTkFrame, CompatCTkButton, CompatCTkLabel
from engine.gui.tooltip import ToolTip
import customtkinter as ctk

root = None


def init(**deps):
    globals().update(deps)


def _apply_window_icon(win: tk.Toplevel):
    try:
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XTTSStudio.App")
        except Exception:
            pass
    except Exception:
        pass
    ico = ICON_PATH if os.path.isfile(ICON_PATH) else os.path.join(str(BASE_DIR), "icon.ico")
    if os.path.isfile(ico):
        try:
            win.iconbitmap(default=ico)
            win.after(200, lambda: win.iconbitmap(default=ico))
        except Exception:
            pass
    try:
        png = os.path.join(str(BASE_DIR), "icon.png")
        if os.path.isfile(png):
            photo = tk.PhotoImage(file=png)
            win.iconphoto(True, photo)
            win._icon_photo_ref = photo
    except Exception:
        pass


def open_ai_status_window():
    from engine.gpt_client import get_chain_diagnostics

    diag = get_chain_diagnostics()
    win = tk.Toplevel(root)
    win.title(t("win_ai_status_title"))
    win.geometry("720x640")
    win.minsize(640, 500)
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    _apply_window_icon(win)
    win.grab_set()

    def _round_btn(parent, text, cmd, diameter=36, primary=False):
        bg = Colors.BG_ACTIVE if primary else Colors.BG_INPUT
        hover = "#2ea043" if primary else Colors.BG_HOVER
        sd = scaled_size(diameter, min_size=diameter)
        return CompatCTkButton(
            parent,
            text=text,
            command=cmd,
            width=sd,
            height=sd,
            corner_radius=sd // 2,
            fg_color=bg,
            text_color=Colors.TEXT_MAIN,
            hover_color=hover,
            border_width=0,
            font=("Segoe UI", scaled_font_size(15)),
        )

    try:
        from engine.tts_runner import detect_device

        device_str = detect_device().upper()
    except Exception:
        device_str = "?"

    # HEADER pill
    header = CompatCTkFrame(
        win, fg_color=Colors.BG_CARD, corner_radius=20, border_width=1, border_color=Colors.BORDER
    )
    header.pack(fill="x", padx=14, pady=(12, 8))

    inner = tk.Frame(header, bg=Colors.BG_CARD)
    inner.pack(fill="x", padx=18, pady=14)

    CompatCTkLabel(
        inner,
        text=t("ai_xtts_device", device_str),
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(11)),
    ).pack(anchor="w")

    active_info = next((p for p in diag["providers"] if p["id"] == diag["active"]), None)
    active_label = active_info["label"] if active_info else diag["active"]
    active_key_ok = active_info["has_key"] if active_info else False

    CompatCTkLabel(
        inner,
        text=t("ai_active_provider", active_label),
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(14), "bold"),
    ).pack(anchor="w", pady=(6, 0))
    CompatCTkLabel(
        inner,
        text=(t("ai_key_set") if active_key_ok else t("ai_key_missing")),
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_SUCCESS if active_key_ok else Colors.TEXT_ERROR,
        font=("Segoe UI", scaled_font_size(11)),
    ).pack(anchor="w", pady=(4, 0))

    if diag["chain_order"]:
        chain_labels = []
        for pid in diag["chain_order"]:
            entry = next((p for p in diag["providers"] if p["id"] == pid), None)
            chain_labels.append(entry["label"] if entry else pid)
        chain_text = " → ".join(chain_labels)
    else:
        chain_text = t("ai_fallback_empty")
    CompatCTkLabel(
        inner,
        text=t("ai_fallback_order", chain_text),
        fg_color=Colors.BG_CARD,
        text_color=Colors.ACCENT,
        font=("Segoe UI", scaled_font_size(11)),
        anchor="w",
        wraplength=620,
        justify="left",
    ).pack(anchor="w", pady=(10, 0), fill="x")

    # LIST
    list_frame = ctk.CTkScrollableFrame(win, fg_color=Colors.BG_DARK, corner_radius=12)
    list_frame.pack(fill="both", expand=True, padx=12, pady=6)

    status_meta = {
        "active": ("🟢", Colors.TEXT_SUCCESS),
        "in_chain": ("🔵", Colors.ACCENT),
        "skipped": ("⚪", Colors.TEXT_DIM),
        "hidden": ("🚫", Colors.TEXT_DIM),
    }

    for entry in diag["providers"]:
        icon, color = status_meta.get(entry["status"], ("•", Colors.TEXT_DIM))
        card = CompatCTkFrame(
            list_frame,
            fg_color=Colors.BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=Colors.BORDER,
        )
        card.pack(fill="x", padx=4, pady=5)

        badge = CompatCTkFrame(
            card, fg_color=Colors.BG_INPUT, corner_radius=20, width=44, height=44
        )
        badge.pack(side="left", padx=(14, 10), pady=12)
        badge.pack_propagate(False)
        CompatCTkLabel(
            badge,
            text=icon,
            fg_color=Colors.BG_INPUT,
            text_color=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(18)),
        ).pack(expand=True)

        info = tk.Frame(card, bg=Colors.BG_CARD)
        info.pack(side="left", fill="both", expand=True, pady=10)

        top = tk.Frame(info, bg=Colors.BG_CARD)
        top.pack(fill="x")
        CompatCTkLabel(
            top,
            text=entry["label"],
            fg_color=Colors.BG_CARD,
            text_color=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(13), "bold"),
            anchor="w",
        ).pack(side="left")
        CompatCTkLabel(
            top,
            text=t("ai_builtin") if entry["builtin"] else t("ai_custom"),
            fg_color=Colors.BG_CARD,
            text_color=Colors.TEXT_DIM,
            font=("Segoe UI", scaled_font_size(10)),
            anchor="e",
        ).pack(side="right")

        CompatCTkLabel(
            info,
            text=entry["reason"],
            fg_color=Colors.BG_CARD,
            text_color=color,
            font=("Segoe UI", scaled_font_size(11)),
            anchor="w",
            justify="left",
            wraplength=460,
        ).pack(fill="x", pady=(2, 2))

        if entry["model"]:
            CompatCTkLabel(
                info,
                text=t("ai_model_label", entry["model"]),
                fg_color=Colors.BG_CARD,
                text_color=Colors.TEXT_DIM,
                font=("Consolas", scaled_font_size(11)),
                anchor="w",
            ).pack(fill="x")

    # BOTTOM
    outer_wrap = tk.Frame(win, bg=Colors.BG_DARK)
    outer_wrap.pack(fill="x", side="bottom")
    bottom_card = CompatCTkFrame(
        outer_wrap,
        fg_color=Colors.BG_CARD,
        corner_radius=20,
        border_width=1,
        border_color=Colors.BORDER,
    )
    bottom_card.pack(fill="x", padx=14, pady=(6, 14))
    bottom_row = tk.Frame(bottom_card, bg=Colors.BG_CARD)
    bottom_row.pack(fill="x", padx=18, pady=12)

    def refresh():
        win.destroy()
        open_ai_status_window()

    b_refresh = _round_btn(bottom_row, "🔄", refresh, diameter=40)
    b_refresh.pack(side="left", padx=4)
    ToolTip(b_refresh, "Обновить")

    b_close = _round_btn(bottom_row, "✕", win.destroy, diameter=40, primary=True)
    b_close.pack(side="right", padx=4)
    ToolTip(b_close, t("btn_close"))

    def on_close():
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)
    try:
        win.after(150, lambda: _apply_window_icon(win))
    except Exception:
        pass
