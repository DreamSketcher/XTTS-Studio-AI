"""Reusable, lightweight CPML confirmation dialog for startup and Settings."""

from __future__ import annotations

from contextlib import suppress

from i18n import t

from engine.coqui_consent import CPML_URL, is_coqui_tos_agreed, set_coqui_tos_agreed


def confirm_coqui_tos(parent=None, source: str = "user-confirmed", *, review: bool = False) -> bool:
    """Show the license and persist consent only when the user accepts.

    With ``review=False`` an existing explicit confirmation is reused. Settings
    passes ``review=True`` so the license can always be reopened. Declining does
    not revoke an earlier saved consent; it simply leaves the state unchanged.
    A save failure is visible in the dialog and returns False, never success.
    """
    if not review and is_coqui_tos_agreed():
        return True

    import tkinter as tk
    from tkinter import messagebox
    import webbrowser

    owns_root = parent is None
    root = tk.Tk() if owns_root else parent
    if owns_root:
        root.withdraw()

    result = {"agreed": False}
    win = None
    try:
        win = tk.Toplevel(root)
        win.title(t("cpml_dialog_title"))
        win.geometry("620x430")
        win.resizable(False, False)
        win.configure(bg="#1e1e1e")
        if not owns_root:
            win.transient(root)

        def _decline():
            result["agreed"] = False
            win.destroy()

        def _accept():
            try:
                set_coqui_tos_agreed(source)
            except (OSError, ValueError) as exc:
                messagebox.showerror(
                    t("cpml_save_error_title"),
                    t("cpml_save_error", str(exc)),
                    parent=win,
                )
                return
            result["agreed"] = True
            win.destroy()

        def _open_link(_event=None):
            webbrowser.open(CPML_URL)

        win.protocol("WM_DELETE_WINDOW", _decline)
        tk.Label(
            win,
            text=t("cpml_dialog_title"),
            font=("Segoe UI", 13, "bold"),
            bg="#1e1e1e",
            fg="#ffffff",
        ).pack(pady=(18, 6))
        tk.Label(
            win,
            text=t("cpml_body"),
            font=("Segoe UI", 10),
            bg="#1e1e1e",
            fg="#cfcfcf",
            justify="left",
            wraplength=560,
        ).pack(padx=24, pady=(0, 10))
        link = tk.Label(
            win,
            text=CPML_URL,
            font=("Segoe UI", 10, "underline"),
            bg="#1e1e1e",
            fg="#4da3ff",
            cursor="hand2",
        )
        link.pack(pady=(0, 20))
        link.bind("<Button-1>", _open_link)

        buttons = tk.Frame(win, bg="#1e1e1e")
        buttons.pack(pady=(0, 18))
        tk.Button(
            buttons,
            text=t("cpml_accept"),
            font=("Segoe UI", 10, "bold"),
            bg="#2e7d32",
            fg="#ffffff",
            activebackground="#388e3c",
            relief="flat",
            padx=16,
            pady=6,
            command=_accept,
        ).pack(side="left", padx=8)
        tk.Button(
            buttons,
            text=t("cpml_cancel"),
            font=("Segoe UI", 10),
            bg="#3a3a3a",
            fg="#ffffff",
            activebackground="#4a4a4a",
            relief="flat",
            padx=16,
            pady=6,
            command=_decline,
        ).pack(side="left", padx=8)

        win.update_idletasks()
        x = (win.winfo_screenwidth() - win.winfo_width()) // 2
        y = (win.winfo_screenheight() - win.winfo_height()) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        win.lift()
        win.focus_force()
        win.wait_visibility()
        win.grab_set()
        root.wait_window(win)
        return result["agreed"]
    finally:
        if win is not None:
            with suppress(tk.TclError):
                win.destroy()
        if owns_root:
            root.destroy()
