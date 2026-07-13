# -*- coding: utf-8 -*-
"""engine/gui/console.py — встроенная консоль единый размер 165, с сохранением позиции"""
import sys
import tkinter as tk
from i18n import t
from engine.gui.colors import Colors, scaled_font_size
from engine.gui.widgets import create_card

root = None
console_visible = None

console_card = None
console_header = None
toggle_btn = None
_clr_btn = None
console_inner = None
console_text = None
console_scroll = None


def init(**deps):
    globals().update(deps)


class ConsoleRedirect:
    def __init__(self):
        self.widget = None
        self._buffer = []

    def attach(self, widget):
        self.widget = widget
        for line in self._buffer:
            try:
                widget.after(0, self._write_to_widget, line)
            except Exception:
                pass
        self._buffer.clear()

    def _write_to_widget(self, text):
        if self.widget is None:
            return
        low = text.lower()
        if "error" in low or "ошибка" in low:
            tag = "error"
        elif "warn" in low or "warning" in low:
            tag = "warn"
        elif "done" in low or "готово" in low or "✔" in text:
            tag = "ok"
        else:
            tag = "info"
        try:
            self.widget.insert(tk.END, text, tag)
            self.widget.see(tk.END)
        except Exception:
            pass

    def write(self, text):
        if self.widget is None:
            self._buffer.append(text)
        else:
            try:
                self.widget.after(0, self._write_to_widget, text)
            except Exception:
                pass

    def flush(self):
        pass


console_redirect = ConsoleRedirect()


def install():
    sys.stdout = console_redirect
    sys.stderr = console_redirect


def _save_console_state():
    try:
        from engine.gui import theme_manager as tm

        data = tm._read_json()
        data["console_visible"] = bool(console_visible.get()) if console_visible else True
        try:
            if console_text and console_text.winfo_exists():
                data["console_scroll_pos"] = console_text.yview()[0]
        except Exception:
            pass
        with open(tm.THEME_FILE, "w", encoding="utf-8") as f:
            import json

            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_console_state():
    try:
        from engine.gui import theme_manager as tm

        data = tm._read_json()
        vis = data.get("console_visible", None)
        if vis is not None and console_visible is not None:
            console_visible.set(bool(vis))
        return data.get("console_scroll_pos", 0.0)
    except Exception:
        return 0.0


def _redistribute_left_panel():
    # Все 4 окна изначально одинаковые 165
    # При закрытой консоли — 3 остальных растут, и текст референса увеличивается
    # ТОЛЬКО карточка голос-референс меняет шрифт — как просил пользователь
    try:
        import engine.gui.voice_panel as vp
        import engine.gui.queue_panel as qp

        is_open = bool(console_visible.get()) if console_visible else True

        if is_open:
            h = 165
            for card in [vp.ref_card, vp.voice_card, qp.queue_card, console_card]:
                try:
                    if card and card.winfo_exists():
                        card.configure(height=h)
                        card.pack_propagate(False)
                except Exception:
                    pass
            try:
                if vp.voice_listbox:
                    vp.voice_listbox.configure(height=4)
            except Exception:
                pass
            try:
                if qp.queue_listbox:
                    qp.queue_listbox.configure(height=4)
            except Exception:
                pass
            try:
                if console_text:
                    console_text.configure(height=4)
            except Exception:
                pass
            # Текст референса — базовый увеличенный 9pt (было 7)
            try:
                if hasattr(vp, "set_ref_info_font_size"):
                    vp.set_ref_info_font_size(9)
            except Exception:
                pass
        else:
            try:
                if console_card and console_card.winfo_exists():
                    console_card.configure(height=32)
                    console_card.pack_propagate(False)
            except Exception:
                pass
            try:
                if vp.ref_card and vp.ref_card.winfo_exists():
                    vp.ref_card.configure(height=160)
                    vp.ref_card.pack_propagate(False)
            except Exception:
                pass
            for card in [vp.voice_card, qp.queue_card]:
                try:
                    if card and card.winfo_exists():
                        card.configure(height=220)
                        card.pack_propagate(False)
                except Exception:
                    pass
            try:
                if vp.voice_listbox:
                    vp.voice_listbox.configure(height=6)
            except Exception:
                pass
            try:
                if qp.queue_listbox:
                    qp.queue_listbox.configure(height=6)
            except Exception:
                pass
            # Текст "Конвертирован в WAV..." увеличивается когда консоль закрыта
            try:
                if hasattr(vp, "set_ref_info_font_size"):
                    vp.set_ref_info_font_size(10)
            except Exception:
                pass
        try:
            if console_card and console_card.master and console_card.master.winfo_exists():
                console_card.master.update_idletasks()
        except Exception:
            pass
    except Exception:
        pass


def toggle_console():
    if console_visible.get():
        console_inner.pack_forget()
        console_visible.set(False)
        try:
            toggle_btn.config(text=t("console_hide"))
        except Exception:
            pass
    else:
        console_inner.pack(fill="both", expand=True, padx=8, pady=(0, 7))
        console_visible.set(True)
        try:
            toggle_btn.config(text=t("console_show"))
        except Exception:
            pass
    _save_console_state()
    _redistribute_left_panel()


def show_context_menu(event):
    menu = tk.Menu(
        root,
        tearoff=0,
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        activebackground=Colors.BG_HOVER,
        activeforeground=Colors.TEXT_MAIN,
        relief="flat",
        borderwidth=1,
    )
    menu.add_command(
        label=t("ctx_copy"),
        command=lambda: (
            (
                root.clipboard_clear(),
                root.clipboard_append(console_text.get(tk.SEL_FIRST, tk.SEL_LAST)),
            )
            if console_text.tag_ranges(tk.SEL)
            else None
        ),
    )
    menu.add_separator()
    menu.add_command(label="🗑 " + t("ctx_clear"), command=clear_console)
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def clear_console():
    try:
        console_text.delete("1.0", tk.END)
    except Exception:
        pass


def build_console_card(left_panel, queue_card):
    global console_card, console_header, toggle_btn, _clr_btn
    global console_inner, console_text, console_scroll
    UNIFIED = 165
    console_card = create_card(left_panel, "")
    console_card.pack(fill="x", pady=(0, 6), after=queue_card)
    try:
        console_card.configure(height=UNIFIED)
        console_card.pack_propagate(False)
    except Exception:
        pass

    console_header = tk.Frame(console_card, bg=Colors.BG_CARD)
    console_header.pack(fill="x", padx=8, pady=(7, 3))

    toggle_btn = tk.Button(
        console_header,
        text=t("console_show"),
        command=toggle_console,
        bg=Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        activebackground=Colors.BG_HOVER,
        activeforeground=Colors.TEXT_MAIN,
        relief="flat",
        borderwidth=0,
        font=("Segoe UI", scaled_font_size(8)),
        cursor="hand2",
        padx=5,
        pady=1,
    )
    toggle_btn.bind("<Enter>", lambda e: toggle_btn.config(bg=Colors.BG_HOVER))
    toggle_btn.bind("<Leave>", lambda e: toggle_btn.config(bg=Colors.BG_INPUT))
    toggle_btn.pack(side="left")

    _clr_btn = tk.Button(
        console_header,
        text="🗑",
        command=clear_console,
        bg=Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        activebackground=Colors.BG_HOVER,
        activeforeground=Colors.TEXT_MAIN,
        relief="flat",
        borderwidth=0,
        font=("Segoe UI", scaled_font_size(8)),
        cursor="hand2",
        padx=5,
        pady=1,
    )
    _clr_btn.bind("<Enter>", lambda e: _clr_btn.config(bg=Colors.BG_HOVER))
    _clr_btn.bind("<Leave>", lambda e: _clr_btn.config(bg=Colors.BG_INPUT))
    _clr_btn.pack(side="right")

    console_inner = tk.Frame(console_card, bg=Colors.BG_CARD)
    console_inner.pack(fill="both", expand=True, padx=8, pady=(0, 7))

    text_wrap = tk.Frame(console_inner, bg=Colors.BORDER, padx=1, pady=1)
    text_wrap.pack(fill="both", expand=True)

    console_text = tk.Text(
        text_wrap,
        height=4,
        bg=Colors.BG_DARK,
        fg=Colors.TEXT_MAIN,
        font=("Consolas", scaled_font_size(9)),
        state="normal",
        wrap="word",
        cursor="arrow",
        relief="flat",
        highlightthickness=0,
        padx=8,
        pady=6,
    )
    console_scroll = tk.Scrollbar(
        text_wrap, command=console_text.yview, bg=Colors.BG_INPUT, troughcolor=Colors.BG_DARK
    )
    console_text.configure(yscrollcommand=console_scroll.set)
    console_scroll.pack(side="right", fill="y")
    console_text.pack(fill="both", expand=True)

    console_text.tag_configure("error", foreground=Colors.TEXT_ERROR)
    console_text.tag_configure("warn", foreground=Colors.TEXT_WARNING)
    console_text.tag_configure("ok", foreground=Colors.TEXT_SUCCESS)
    console_text.tag_configure("info", foreground=Colors.TEXT_MAIN)
    console_redirect.attach(console_text)
    console_text.bind("<Button-3>", show_context_menu)
    console_text.bind(
        "<Control-c>",
        lambda e: (
            (
                root.clipboard_clear(),
                root.clipboard_append(console_text.get(tk.SEL_FIRST, tk.SEL_LAST)),
                "break",
            )[-1]
            if console_text.tag_ranges(tk.SEL)
            else "break"
        ),
    )
    console_text.bind(
        "<Control-C>",
        lambda e: (
            (
                root.clipboard_clear(),
                root.clipboard_append(console_text.get(tk.SEL_FIRST, tk.SEL_LAST)),
                "break",
            )[-1]
            if console_text.tag_ranges(tk.SEL)
            else "break"
        ),
    )

    try:
        saved_pos = _load_console_state()
        if console_visible is not None and not console_visible.get():
            console_inner.pack_forget()
            try:
                toggle_btn.config(text=t("console_hide"))
            except Exception:
                pass
            try:
                root.after(100, _redistribute_left_panel)
            except Exception:
                pass
        else:
            if saved_pos:
                try:
                    root.after(200, lambda: console_text.yview_moveto(saved_pos))
                except Exception:
                    pass
            try:
                root.after(100, _redistribute_left_panel)
            except Exception:
                pass
    except Exception:
        pass
