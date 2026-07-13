# -*- coding: utf-8 -*-
"""engine/gui/tooltip.py — всплывающие подсказки (перенесено из gui.py: class ToolTip)."""
import tkinter as tk

from engine.gui.colors import Colors, scaled_font_size


class ToolTip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def show(self, event=None):
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 15
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.tip,
            text=self.text() if callable(self.text) else self.text,
            bg=Colors.TOOLTIP_BG,
            fg=Colors.TEXT_MAIN,
            justify="left",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=7,
            font=("Segoe UI", scaled_font_size(9)),
            wraplength=280,
        ).pack()

    def hide(self, event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None
