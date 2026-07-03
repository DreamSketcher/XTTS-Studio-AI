from __future__ import annotations
import tkinter as tk

try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except Exception:
    CTK_AVAILABLE = False
    ctk = None

if CTK_AVAILABLE:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    class CTkFrame(ctk.CTkFrame):
        def __init__(self, *args, bg=None, highlightthickness=None, highlightbackground=None, bd=None, cursor=None, padx=None, pady=None, **kwargs):
            if bg is not None: kwargs.setdefault("fg_color", bg)
            if highlightbackground is not None: kwargs.setdefault("border_color", highlightbackground)
            if highlightthickness is not None: kwargs.setdefault("border_width", highlightthickness)
            kwargs.setdefault("corner_radius", 0)
            super().__init__(*args, **kwargs)
        def configure(self, cnf=None, **kwargs):
            if cnf: kwargs.update(cnf)
            if "bg" in kwargs: kwargs["fg_color"] = kwargs.pop("bg")
            if "highlightbackground" in kwargs: kwargs["border_color"] = kwargs.pop("highlightbackground")
            kwargs.pop("bd", None); kwargs.pop("cursor", None); kwargs.pop("padx", None); kwargs.pop("pady", None)
            return super().configure(**kwargs)
        config = configure

    class CTkLabel(ctk.CTkLabel):
        def __init__(self, *args, bg=None, fg=None, **kwargs):
            if bg is not None: kwargs.setdefault("fg_color", bg)
            if fg is not None: kwargs.setdefault("text_color", fg)
            kwargs.setdefault("corner_radius", 0)
            super().__init__(*args, **kwargs)
        def configure(self, cnf=None, **kwargs):
            if cnf: kwargs.update(cnf)
            if "bg" in kwargs: kwargs["fg_color"] = kwargs.pop("bg")
            if "fg" in kwargs: kwargs["text_color"] = kwargs.pop("fg")
            return super().configure(**kwargs)
        config = configure

    class CTkButton(ctk.CTkButton):
        def __init__(self, *args, bg=None, fg=None, activebackground=None, activeforeground=None, borderwidth=None, relief=None, padx=None, pady=None, bd=None, cursor=None, **kwargs):
            if bg is not None: kwargs.setdefault("fg_color", bg)
            if fg is not None: kwargs.setdefault("text_color", fg)
            if activebackground is not None: kwargs.setdefault("hover_color", activebackground)
            kwargs.setdefault("corner_radius", 10)
            if "height" in kwargs:
                try: h=int(kwargs["height"]); kwargs["height"]=max(28,h*28)
                except: pass
            super().__init__(*args, **kwargs)
        def configure(self, cnf=None, **kwargs):
            if cnf: kwargs.update(cnf)
            if "bg" in kwargs: kwargs["fg_color"] = kwargs.pop("bg")
            if "fg" in kwargs: kwargs["text_color"] = kwargs.pop("fg")
            if "activebackground" in kwargs: kwargs["hover_color"] = kwargs.pop("activebackground")
            kwargs.pop("activeforeground", None); kwargs.pop("borderwidth", None); kwargs.pop("relief", None); kwargs.pop("bd", None); kwargs.pop("cursor", None)
            return super().configure(**kwargs)
        config = configure

    TkFrame = CTkFrame
    TkLabel = CTkLabel
    TkButton = CTkButton
else:
    TkFrame = tk.Frame
    TkLabel = tk.Label
    TkButton = tk.Button

def TkRawFrame(*args, bg=None, highlightthickness=None, highlightbackground=None, bd=None, **kwargs):
    parent = args[0] if args else kwargs.get("master")
    if not parent and "master" not in kwargs:
        raise ValueError("TkRawFrame requires a master widget")
    
    kwargs.pop("padx", None)
    kwargs.pop("pady", None)
    
    # fix args if master is there
    if "master" in kwargs and not args:
        f = tk.Frame(**kwargs)
    else:
        f = tk.Frame(parent, **{k:v for k,v in kwargs.items() if k != "master"})
        
    if bg is not None: f.configure(bg=bg)
    if highlightthickness is not None: f.configure(highlightthickness=highlightthickness)
    if highlightbackground is not None: f.configure(highlightbackground=highlightbackground)
    if bd is not None: f.configure(bd=bd)
    return f
