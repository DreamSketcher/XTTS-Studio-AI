# -*- coding: utf-8 -*-
"""engine/gui/queue_panel.py — карточка «Очередь задач» единый размер 165"""
import tkinter as tk
from i18n import t
from engine.gui.colors import Colors, scaled_font_size
from engine.gui.widgets import create_card, create_button
from engine.gui.batch_panel import open_batch_window

root = None
task_manager = None

queue_card = None
queue_listbox = None
batch_btn_row = None


def init(**deps):
    globals().update(deps)


def update_queue_view():
    try:
        queue_listbox.delete(0, tk.END)
        status_icons = {
            "queued": "⏳",
            "running": "▶ ",
            "done": "✔",
            "error": "❌",
            "cancelled": "⛔",
        }
        queue = task_manager.get_queue()
        active_set = False
        for i, task in enumerate(queue):
            name = task.text[:30].replace("\n", " ")
            if not active_set and task.status in ("queued", "running"):
                icon = "▶ "
                active_set = True
            else:
                icon = status_icons.get(task.status, "•")
            queue_listbox.insert(tk.END, f"{icon} {name} | {task.progress}%")
            if icon == "▶ ":
                queue_listbox.itemconfig(i, fg=Colors.TEXT_SUCCESS)
            elif task.status == "done":
                queue_listbox.itemconfig(i, fg=Colors.TEXT_DIM)
            elif task.status == "error":
                queue_listbox.itemconfig(i, fg=Colors.TEXT_ERROR)
    except Exception:
        pass


def queue_autorefresh():
    update_queue_view()
    try:
        root.after(500, queue_autorefresh)
    except Exception:
        pass


def build_queue_card(left_panel):
    global queue_card, queue_listbox, batch_btn_row
    UNIFIED = 165
    queue_card = create_card(left_panel, "")
    queue_card.pack(fill="x", pady=(0, 6))
    try:
        queue_card.configure(height=UNIFIED)
        queue_card.pack_propagate(False)
    except Exception:
        pass

    tk.Label(
        queue_card,
        text=t("card_queue"),
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(9), "bold"),
        anchor="w",
    ).pack(fill="x", padx=10, pady=(7, 3))

    list_wrap = tk.Frame(queue_card, bg=Colors.BORDER, padx=1, pady=1)
    list_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 4))

    queue_listbox = tk.Listbox(
        list_wrap,
        height=4,
        bg=Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        selectbackground=Colors.ACCENT,
        selectforeground=Colors.TEXT_MAIN,
        relief="flat",
        highlightthickness=0,
        font=("Consolas", scaled_font_size(8)),
        activestyle="none",
        exportselection=False,
    )
    queue_listbox.pack(fill="both", expand=True)

    batch_btn_row = tk.Frame(queue_card, bg=Colors.BG_CARD)
    batch_btn_row.pack(fill="x", padx=10, pady=(0, 7))
    create_button(batch_btn_row, t("btn_batch"), open_batch_window, bg=Colors.BG_INPUT).pack(
        fill="x"
    )
