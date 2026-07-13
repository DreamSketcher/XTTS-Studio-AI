from __future__ import annotations
import tkinter as tk

try:
    import customtkinter as ctk

    CTK_AVAILABLE = True
except Exception:
    CTK_AVAILABLE = False
    ctk = None

# Unified design: use scaled_font_size / scaled_size from main colors
try:
    from engine.gui.colors import scaled_font_size, scaled_size, Colors
except Exception:

    def scaled_font_size(x):
        return x

    def scaled_size(x, min_size=None, max_size=None):
        return x

    Colors = None

if CTK_AVAILABLE:

    class CTkFrame(ctk.CTkFrame):
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
            # unified rounded corners 14 like audio/history
            kwargs.setdefault("corner_radius", 14)
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

    class CTkLabel(ctk.CTkLabel):
        def __init__(self, *args, bg=None, fg=None, **kwargs):
            if bg is not None:
                kwargs.setdefault("fg_color", bg)
            if fg is not None:
                kwargs.setdefault("text_color", fg)
            kwargs.setdefault("corner_radius", 0)
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

    class CTkButton(ctk.CTkButton):
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
            # unified pill style: 18 radius, larger font
            kwargs.setdefault("corner_radius", 18)
            if "height" in kwargs:
                try:
                    h = int(kwargs["height"])
                    # scale height with font scale
                    kwargs["height"] = scaled_size(max(32, h * 28), min_size=32)
                except:
                    pass
            # font scaling: if font passed as tuple, scale size part
            if "font" in kwargs and isinstance(kwargs["font"], tuple):
                try:
                    fam, sz = kwargs["font"][0], kwargs["font"][1]
                    kwargs["font"] = (fam, scaled_font_size(sz))
                except:
                    pass
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
            return super().configure(**kwargs)

        config = configure

    TkFrame = CTkFrame
    TkLabel = CTkLabel
    TkButton = CTkButton
else:
    CTkFrame = CTkLabel = CTkButton = None
    TkFrame = tk.Frame
    TkLabel = tk.Label
    TkButton = tk.Button


def TkRawFrame(
    *args, bg=None, highlightthickness=None, highlightbackground=None, bd=None, **kwargs
):
    parent = args[0] if args else kwargs.get("master")
    if not parent and "master" not in kwargs:
        raise ValueError("TkRawFrame requires a master widget")
    kwargs.pop("padx", None)
    kwargs.pop("pady", None)
    if "master" in kwargs and not args:
        f = tk.Frame(**kwargs)
    else:
        f = tk.Frame(parent, **{k: v for k, v in kwargs.items() if k != "master"})
    if bg is not None:
        f.configure(bg=bg)
    if highlightthickness is not None:
        f.configure(highlightthickness=highlightthickness)
    if highlightbackground is not None:
        f.configure(highlightbackground=highlightbackground)
    if bd is not None:
        f.configure(bd=bd)
    return f
