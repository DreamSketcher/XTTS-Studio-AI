from __future__ import annotations
import tkinter as tk
from tkinter import colorchooser, ttk
import engine.gui.chat_window.state as state
from engine.gui.chat_window.custom_widgets import TkFrame, TkLabel, TkButton, _c
from engine.gui.chat_window.ui_utils import _make_button, _set_dark_titlebar
from engine.gui.chat_window.theme_manager import load_theme, save_theme
from i18n import t

def open_theme_customizer(parent):
    win = tk.Toplevel(parent)
    _set_dark_titlebar(win)
    win.title(t("theme_custom_title"))
    win.geometry("700x800")
    win.configure(bg=_c("BG_DARK"))
    win.transient(parent)
    win.grab_set()

    current_theme = load_theme()
    
    # Layout
    main = TkFrame(win, bg=_c("BG_DARK"))
    main.pack(fill="both", expand=True, padx=20, pady=20)

    TkLabel(
        main, text=t("theme_custom_desc"),
        bg=_c("BG_DARK"), fg=_c("TEXT_MAIN"), font=("Segoe UI", 14, "bold"),
    ).pack(anchor="w", pady=(0, 20))

    canvas = tk.Canvas(main, bg=_c("BG_DARK"), highlightthickness=0)
    scrollbar = ttk.Scrollbar(main, orient="vertical", command=canvas.yview)
    scroll_frame = TkFrame(canvas, bg=_c("BG_DARK"))

    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # ── Color Section ─────────────────────────────────────────────────────────
    colors_group = TkFrame(scroll_frame, bg=_c("BG_CARD"), padx=15, pady=15)
    colors_group.pack(fill="x", pady=(0, 20))
    
    TkLabel(colors_group, text="Цвета интерфейса", bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), 
            font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

    color_vars = {}

    def pick_color(name, var):
        color = colorchooser.askcolor(initialcolor=var.get())[1]
        if color:
            var.set(color)
            # Apply live preview to the button
            btn.config(bg=color)

    for color_name, color_val in current_theme["colors"].items():
        row = TkFrame(colors_group, bg=_c("BG_CARD"))
        row.pack(fill="x", pady=2)
        
        var = tk.StringVar(value=color_val)
        color_vars[color_name] = var
        
        TkLabel(row, text=color_name, bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), 
                font=("Segoe UI", 10), width=15, anchor="w").pack(side="left")
        
        btn = TkButton(row, text=" 🎨 ", command=lambda n=color_name, v=var: pick_color(n, v),
                       bg=color_val, fg="white" if color_val == "#16161e" else "black",
                       width=5, relief="flat", cursor="hand2")
        btn.pack(side="left", padx=10)

    # ── Font Section ──────────────────────────────────────────────────────────
    fonts_group = TkFrame(scroll_frame, bg=_c("BG_CARD"), padx=15, pady=15)
    fonts_group.pack(fill="x", pady=(0, 20))
    
    TkLabel(fonts_group, text="Типографика", bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), 
            font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

    font_main_var = tk.StringVar(value=current_theme["fonts"]["main"])
    font_size_var = tk.IntVar(value=current_theme["fonts"]["size_main"])
    
    row_f = TkFrame(fonts_group, bg=_c("BG_CARD"))
    row_f.pack(fill="x")
    
    TkLabel(row_f, text=t("theme_font_label"), bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), font=("Segoe UI", 10)).pack(side="left")
    tk.Entry(row_f, textvariable=font_main_var, bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"), 
             insertbackground=_c("TEXT_MAIN"), relief="flat", font=("Segoe UI", 10)).pack(side="left", padx=10, ipady=3)

    row_s = TkFrame(fonts_group, bg=_c("BG_CARD"))
    row_s.pack(fill="x", pady=10)
    
    TkLabel(row_s, text=t("theme_font_size"), bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), font=("Segoe UI", 10)).pack(side="left")
    tk.Spinbox(row_s, from_=8, to=24, textvariable=font_size_var, bg=_c("BG_INPUT"), 
               fg=_c("TEXT_MAIN"), insertbackground=_c("TEXT_MAIN"), relief="flat", font=("Segoe UI", 10)).pack(side="left", padx=10)

    # ── Geometry Section ──────────────────────────────────────────────────────
    geo_group = TkFrame(scroll_frame, bg=_c("BG_CARD"), padx=15, pady=15)
    geo_group.pack(fill="x", pady=(0, 20))
    
    TkLabel(geo_group, text="Геометрия и Отступы", bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), 
            font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))

    pad_var = tk.IntVar(value=current_theme["geometry"]["padding_main"])
    row_p = TkFrame(geo_group, bg=_c("BG_CARD"))
    row_p.pack(fill="x")
    
    TkLabel(row_p, text=t("theme_padding_label"), bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), font=("Segoe UI", 10)).pack(side="left")
    tk.Scale(row_p, from_=0, to=40, orient="horizontal", variable=pad_var, 
             bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), highlightthickness=0, troughcolor=_c("BG_INPUT")).pack(side="left", fill="x", expand=True, padx=10)

    # ── Layout Section ────────────────────────────────────────────────────────
    lay_group = TkFrame(scroll_frame, bg=_c("BG_CARD"), padx=15, pady=15)
    lay_group.pack(fill="x", pady=(0, 20))
    
    TkLabel(lay_group, text=t("theme_layout_label"), bg=_c("BG_CARD"), fg=_c, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))
    
    lay_var = tk.StringVar(value=current_theme["layout"])
    for l_id, l_label in [("classic", t("theme_layout_classic")), ("compact", t("theme_layout_compact")), ("wide", t("theme_layout_wide"))]:
        tk.Radiobutton(lay_group, text=l_label, variable=lay_var, value=l_id, 
                       bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), selectcolor=_c("BG_INPUT"), 
                       activebackground=_c("BG_CARD"), font=("Segoe UI", 10), anchor="w").pack(fill="x")

    # ── Bottom Buttons ────────────────────────────────────────────────────────
    btn_row = TkFrame(main, bg=_c("BG_DARK"))
    btn_row.pack(fill="x", pady=(20, 0))

    def apply_and_save():
        new_theme = {
            "colors": {k: v.get() for k, v in color_vars.items()},
            "fonts": {
                "main": font_main_var.get(),
                "size_main": font_size_var.get(),
                "mono": "Consolas", # Keeping defaults for rest
                "size_header": 14,
                "size_small": 9,
            },
            "geometry": {
                "padding_main": pad_var.get(),
                "padding_inner": 5,
                "item_spacing": 8,
            },
            "layout": lay_var.get()
        }
        save_theme(new_theme)
        messagebox.showinfo("Тема", "Настройки темы сохранены! Перезапустите приложение для полного применения.", parent=win)
        win.destroy()

    _make_button(btn_row, t("theme_reset_btn"), lambda: win.destroy(), bg=_c("BG_INPUT"), font_size=10).pack(side="right", padx=(6, 0))
    _make_button(btn_row, t("theme_save_btn"), apply_and_save, bg=_c("BG_ACTIVE"), font_size=10).pack(side="right")

    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.config(command=canvas.yview)
