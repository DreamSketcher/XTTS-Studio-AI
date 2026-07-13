# -*- coding: utf-8 -*-
"""engine/gui/presets.py — пресеты качества (компактный редизайн, быстрый скролл) с интеграцией RVC"""
import tkinter as tk
import os

import customtkinter as ctk

from i18n import t
from engine.paths import BASE_DIR
try:
    from engine.paths import ICON_PATH
except ImportError:
    ICON_PATH = os.path.join(str(BASE_DIR), "icon.ico")

from engine.gui.colors import Colors, scaled_font_size, scaled_size
from engine.gui.tooltip import ToolTip
from engine.gui.widgets import CompatCTkFrame, CompatCTkButton, CompatCTkLabel
try:
    from engine.settings_store import load_settings as _load_app_settings
except Exception:
    def _load_app_settings():
        return {}
from engine.gui.rvc_model_dropdown import RVCModelDropdown
from engine import rvc_catalog

# set_progress ждёт int 0-100 (не долю 0..1) — см. engine/gui/statusbar.py.
# try/except на импорт — на случай если модуль ещё не инициализирован через
# init() на момент импорта presets.py (тот же паттерн, что и в остальном файле).
try:
    from engine.gui.statusbar import set_status, set_progress, show_cancel_button, hide_cancel_button
except ImportError:
    def set_status(*a, **k): pass
    def set_progress(*a, **k): pass
    def show_cancel_button(*a, **k): pass
    def hide_cancel_button(*a, **k): pass


def _safe_call(fn, *args):
    """Обёртка для колбэков statusbar — RVCModelDropdown не должен падать целиком
    из-за проблемы в статус-баре (тот же защитный стиль, что и в остальном файле)."""
    try:
        fn(*args)
    except Exception:
        pass

root = None
use_gpt = None
save_settings = None

quality_params = {}
PRESET_DESCRIPTIONS = {}

def init(**deps):
    globals().update(deps)

def build_quality_params():
    global quality_params, PRESET_DESCRIPTIONS
    quality_params = {
        "Высокое качество": {
            "qc_enabled": tk.BooleanVar(value=True),
            "temperature": tk.DoubleVar(value=0.70),
            "top_p": tk.DoubleVar(value=0.30),
            "top_k": tk.IntVar(value=80),
            "repetition_penalty": tk.DoubleVar(value=13.0),
            "prosody_intensity": tk.DoubleVar(value=0.0),
            "de_esser_intensity": tk.DoubleVar(value=0.8),
            "trim_ms": tk.IntVar(value=100),
            "speed": tk.DoubleVar(value=1.0),
            "trim_mode": tk.StringVar(value="auto"),
            "export_format": tk.StringVar(value="wav"),
            "use_gpt": tk.BooleanVar(value=use_gpt.get() if use_gpt else False),
            "ai_conductor_enabled": tk.BooleanVar(value=False),
            # RVC параметры для пресета "Высокое качество"
            "rvc_enable": tk.BooleanVar(value=False),
            "rvc_model": tk.StringVar(value="Не выбрана"),
            "rvc_index_rate": tk.DoubleVar(value=0.75),
            "rvc_pitch_shift": tk.IntVar(value=0),
            "rvc_f0_method": tk.StringVar(value="rmvpe"),
        },
        "Нарратив": {
            "qc_enabled": tk.BooleanVar(value=True),
            "temperature": tk.DoubleVar(value=0.75),
            "top_p": tk.DoubleVar(value=0.25),
            "top_k": tk.IntVar(value=85),
            "repetition_penalty": tk.DoubleVar(value=18.0),
            "prosody_intensity": tk.DoubleVar(value=0.5),
            "de_esser_intensity": tk.DoubleVar(value=0.7),
            "trim_ms": tk.IntVar(value=80),
            "speed": tk.DoubleVar(value=0.9),
            "trim_mode": tk.StringVar(value="auto"),
            "export_format": tk.StringVar(value="wav"),
            "use_gpt": tk.BooleanVar(value=use_gpt.get() if use_gpt else False),
            "ai_conductor_enabled": tk.BooleanVar(value=False),
            # RVC параметры для пресета "Нарратив"
            "rvc_enable": tk.BooleanVar(value=False),
            "rvc_model": tk.StringVar(value="Не выбрана"),
            "rvc_index_rate": tk.DoubleVar(value=0.85),
            "rvc_pitch_shift": tk.IntVar(value=0),
            "rvc_f0_method": tk.StringVar(value="rmvpe"),
        },
        "Динамика": {
            "qc_enabled": tk.BooleanVar(value=True),
            "temperature": tk.DoubleVar(value=0.82),
            "top_p": tk.DoubleVar(value=0.20),
            "top_k": tk.IntVar(value=100),
            "repetition_penalty": tk.DoubleVar(value=16.0),
            "prosody_intensity": tk.DoubleVar(value=1.1),
            "de_esser_intensity": tk.DoubleVar(value=1.0),
            "trim_ms": tk.IntVar(value=60),
            "speed": tk.DoubleVar(value=1.1),
            "trim_mode": tk.StringVar(value="auto"),
            "export_format": tk.StringVar(value="wav"),
            "use_gpt": tk.BooleanVar(value=use_gpt.get() if use_gpt else False),
            "ai_conductor_enabled": tk.BooleanVar(value=False),
            # RVC параметры для пресета "Динамика"
            "rvc_enable": tk.BooleanVar(value=False),
            "rvc_model": tk.StringVar(value="Не выбрана"),
            "rvc_index_rate": tk.DoubleVar(value=0.65),
            "rvc_pitch_shift": tk.IntVar(value=0),
            "rvc_f0_method": tk.StringVar(value="pm"),
        },
        "Экспрессия": {
            "qc_enabled": tk.BooleanVar(value=True),
            "temperature": tk.DoubleVar(value=0.88),
            "top_p": tk.DoubleVar(value=0.30),
            "top_k": tk.IntVar(value=90),
            "repetition_penalty": tk.DoubleVar(value=14.0),
            "prosody_intensity": tk.DoubleVar(value=1.3),
            "de_esser_intensity": tk.DoubleVar(value=1.3),
            "trim_ms": tk.IntVar(value=100),
            "speed": tk.DoubleVar(value=1.0),
            "trim_mode": tk.StringVar(value="auto"),
            "export_format": tk.StringVar(value="wav"),
            "use_gpt": tk.BooleanVar(value=use_gpt.get() if use_gpt else False),
            "ai_conductor_enabled": tk.BooleanVar(value=False),
            # RVC параметры для пресета "Экспрессия"
            "rvc_enable": tk.BooleanVar(value=False),
            "rvc_model": tk.StringVar(value="Не выбрана"),
            "rvc_index_rate": tk.DoubleVar(value=0.75),
            "rvc_pitch_shift": tk.IntVar(value=0),
            "rvc_f0_method": tk.StringVar(value="harvest"),
        },
    }
    PRESET_DESCRIPTIONS = {
        "Нарратив": t("preset_narrative_desc"),
        "Динамика": t("preset_dynamic_desc"),
        "Экспрессия": t("preset_expressive_desc"),
    }
    return quality_params

def _apply_window_icon(win):
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

def open_quality_settings(preset_name):
    if preset_name not in quality_params:
        preset_name = "Высокое качество"
    win = tk.Toplevel(root)
    win.title(t("win_settings_title", preset_name))
    win.geometry("640x660")
    win.minsize(560, 500)
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    _apply_window_icon(win)
    win.grab_set()

    params = quality_params[preset_name]

    # Последняя открытая вкладка (sticky tabbar) — живёт весь lifetime окна
    _active_tab = tk.StringVar(value="rvc")

    def _round_btn(parent, text, cmd, primary=False, width=None):
        bg = Colors.BG_ACTIVE if primary else Colors.BG_INPUT
        hover = "#2ea043" if primary else Colors.BG_HOVER
        return CompatCTkButton(
            parent, text=text, command=cmd,
            width=width if width else scaled_size(120, min_size=110),
            height=scaled_size(34, min_size=32),
            corner_radius=12,
            fg_color=bg, text_color=Colors.TEXT_MAIN, hover_color=hover,
            font=("Segoe UI", scaled_font_size(12)),
        )

    def _strip_check_mark(s, fallback=""):
        text = (s or "").replace("☑", "").replace("✓", "").strip()
        return text or fallback

    def _section_card(parent, title, subtitle=None, accent=None):
        """Крупная секция: заголовок + опциональный подзаголовок + body."""
        card = CompatCTkFrame(
            parent, fg_color=Colors.BG_CARD, corner_radius=10,
            border_width=1, border_color=Colors.BORDER,
        )
        card.pack(fill="x", padx=1, pady=(0, 8))
        head = tk.Frame(card, bg=Colors.BG_CARD)
        head.pack(fill="x", padx=10, pady=(8, 2))
        if accent:
            strip = tk.Frame(head, bg=accent, width=scaled_size(4, min_size=3))
            strip.pack(side="left", fill="y", padx=(0, 8))
            strip.pack_propagate(False)
        title_col = tk.Frame(head, bg=Colors.BG_CARD)
        title_col.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_col, text=title, anchor="w",
            bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(12), "bold"),
        ).pack(anchor="w")
        if subtitle:
            tk.Label(
                title_col, text=subtitle, anchor="w",
                bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
                font=("Segoe UI", scaled_font_size(9)),
                wraplength=scaled_size(520, min_size=420), justify="left",
            ).pack(anchor="w", pady=(1, 0))
        body = tk.Frame(card, bg=Colors.BG_CARD)
        body.pack(fill="x", padx=10, pady=(4, 10))
        return card, body

    def _slider_row(parent, label, var, from_, to, res, tip, font_label=10, font_val=10):
        wrap = tk.Frame(parent, bg=Colors.BG_CARD)
        wrap.pack(fill="x", pady=3)
        top = tk.Frame(wrap, bg=Colors.BG_CARD)
        top.pack(fill="x")
        lbl = tk.Label(
            top, text=label, anchor="w",
            bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(font_label)),
        )
        lbl.pack(side="left")
        if tip:
            ToolTip(lbl, tip)
        val = tk.Label(
            top, textvariable=var, width=5,
            bg=Colors.BG_CARD, fg=Colors.ACCENT,
            font=("Consolas", scaled_font_size(font_val), "bold"),
        )
        val.pack(side="right")
        scale = tk.Scale(
            wrap, variable=var, from_=from_, to=to, resolution=res,
            orient="horizontal",
            bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, troughcolor=Colors.BG_INPUT,
            highlightthickness=0, sliderrelief="flat", sliderlength=16,
            font=("Segoe UI", scaled_font_size(9)),
        )
        scale.pack(fill="x", pady=(1, 0))
        return scale, lbl, val

    # ── Header ──
    header = CompatCTkFrame(win, fg_color=Colors.BG_CARD, corner_radius=10,
                            border_width=1, border_color=Colors.BORDER)
    header.pack(fill="x", padx=8, pady=(8, 4))
    h_inner = tk.Frame(header, bg=Colors.BG_CARD)
    h_inner.pack(fill="x", padx=10, pady=8)
    CompatCTkLabel(
        h_inner, text=f"⚙ {preset_name}", fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_MAIN, font=("Segoe UI", scaled_font_size(12), "bold"),
        anchor="w",
    ).pack(side="left")
    CompatCTkLabel(
        h_inner, text=PRESET_DESCRIPTIONS.get(preset_name, ""),
        fg_color=Colors.BG_CARD, text_color=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(9)),
        anchor="w", wraplength=280, justify="left",
    ).pack(side="left", padx=(8, 0))

    # ── Footer (фиксирован снизу) ──
    bottom_wrap = tk.Frame(win, bg=Colors.BG_DARK)
    bottom_wrap.pack(fill="x", side="bottom")
    bottom_card = CompatCTkFrame(
        bottom_wrap, fg_color=Colors.BG_CARD, corner_radius=10,
        border_width=1, border_color=Colors.BORDER,
    )
    bottom_card.pack(fill="x", padx=8, pady=6)
    bottom_row = tk.Frame(bottom_card, bg=Colors.BG_CARD)
    bottom_row.pack(fill="x", padx=10, pady=6)

    tk.Label(
        bottom_row, text=f"Пресет: {preset_name}",
        bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(9)),
    ).pack(side="left")

    def _close_and_save():
        # quality_params (включая RVC: enable/model/index/pitch/f0) сериализуются
        # целиком в settings.json → quality_params[preset] через settings_ui.save_settings.
        # Дополнительно пишем последнюю вкладку окна.
        extra = {}
        try:
            extra["quality_settings_last_tab"] = _active_tab.get()
        except Exception:
            pass
        try:
            save_settings(extra if extra else None)
        except Exception:
            try:
                save_settings()
            except Exception:
                pass
        try:
            win.destroy()
        except Exception:
            pass

    _round_btn(
        bottom_row, t("btn_reset"), lambda: reset(),
        width=scaled_size(120, min_size=110),
    ).pack(side="left", padx=(12, 0))
    _round_btn(
        bottom_row, t("btn_close"),
        _close_and_save,
        primary=True, width=scaled_size(140, min_size=120),
    ).pack(side="right")

    # Закрытие крестиком — тоже сохраняем (в т.ч. RVC и последнюю вкладку)
    try:
        win.protocol("WM_DELETE_WINDOW", _close_and_save)
    except Exception:
        pass

    # ── Tabbar (фиксирован, НЕ внутри scroll) ──
    tabbar = CompatCTkFrame(
        win, fg_color=Colors.BG_CARD, corner_radius=10,
        border_width=1, border_color=Colors.BORDER,
    )
    tabbar.pack(fill="x", padx=10, pady=(0, 4))
    tabbar_inner = tk.Frame(tabbar, bg=Colors.BG_CARD)
    tabbar_inner.pack(fill="x", padx=6, pady=6)

    # ── Scroll — только контент вкладок ──
    scroll = ctk.CTkScrollableFrame(win, fg_color=Colors.BG_DARK, corner_radius=10)
    scroll.pack(fill="both", expand=True, padx=10, pady=(0, 6))

    _SCROLL_STEP = 28

    def _fast_scroll_up(e=None):
        try:
            scroll._parent_canvas.yview_scroll(-_SCROLL_STEP, "units")
            return "break"
        except Exception:
            pass

    def _fast_scroll_down(e=None):
        try:
            scroll._parent_canvas.yview_scroll(_SCROLL_STEP, "units")
            return "break"
        except Exception:
            pass

    def _fast_wheel(e):
        try:
            canvas = scroll._parent_canvas
            if hasattr(e, "delta") and e.delta:
                steps = int(e.delta / 120)
                if steps == 0:
                    steps = 1 if e.delta > 0 else -1
                canvas.yview_scroll(-steps * _SCROLL_STEP, "units")
                return "break"
            num = getattr(e, "num", None)
            if num == 4:
                canvas.yview_scroll(-_SCROLL_STEP, "units")
                return "break"
            if num == 5:
                canvas.yview_scroll(_SCROLL_STEP, "units")
                return "break"
        except Exception:
            pass

    try:
        scroll._parent_canvas.bind("<MouseWheel>", _fast_wheel, add=True)
        scroll._parent_canvas.bind("<Button-4>", lambda e: _fast_scroll_up() or "break", add=True)
        scroll._parent_canvas.bind("<Button-5>", lambda e: _fast_scroll_down() or "break", add=True)
        win.bind("<MouseWheel>", _fast_wheel, add=True)
        scroll.bind("<MouseWheel>", _fast_wheel, add=True)
        win.bind("<Button-4>", lambda e: _fast_scroll_up() or "break", add=True)
        win.bind("<Button-5>", lambda e: _fast_scroll_down() or "break", add=True)

        def _bind_recursive_fast(w):
            try:
                w.bind("<MouseWheel>", _fast_wheel, add=True)
                w.bind("<Button-4>", lambda e: _fast_scroll_up() or "break", add=True)
                w.bind("<Button-5>", lambda e: _fast_scroll_down() or "break", add=True)
                for child in w.winfo_children():
                    _bind_recursive_fast(child)
            except Exception:
                pass

        win.after(100, lambda: _bind_recursive_fast(scroll))
        win.after(300, lambda: _bind_recursive_fast(scroll))
        win.after(600, lambda: _bind_recursive_fast(scroll))
    except Exception:
        pass

    # ══════════════════════════════════════════
    #  Вкладки: кнопки сверху (sticky) заменяют содержимое
    # ══════════════════════════════════════════
    _tabs = {}          # key -> frame (panel)
    _tab_buttons = {}   # key -> button
    # _active_tab создан выше (нужен _close_and_save)

    # Контейнер панелей внутри scroll: одна видима, остальные pack_forget
    panels_host = tk.Frame(scroll, bg=Colors.BG_DARK)
    panels_host.pack(fill="both", expand=True)

    def _style_tab_btn(key, active):
        btn = _tab_buttons.get(key)
        if not btn:
            return
        try:
            if active:
                btn.configure(
                    fg_color=Colors.BG_ACTIVE,
                    hover_color=Colors.BG_ACTIVE,
                    text_color=Colors.TEXT_MAIN,
                )
            else:
                btn.configure(
                    fg_color=Colors.BG_INPUT,
                    hover_color=Colors.BG_HOVER,
                    text_color=Colors.TEXT_MAIN,
                )
        except Exception:
            pass

    def _show_tab(key):
        if key not in _tabs:
            return
        _active_tab.set(key)
        for k, frame in _tabs.items():
            try:
                if k == key:
                    frame.pack(fill="both", expand=True)
                else:
                    frame.pack_forget()
            except Exception:
                pass
        for k in _tab_buttons:
            _style_tab_btn(k, k == key)
        # при смене вкладки — в начало + пересчёт scrollregion
        try:
            scroll._parent_canvas.yview_moveto(0)
        except Exception:
            pass
        _force_scroll_update()
        # Запоминаем вкладку (не блокируем UI; полный save — на закрытии)
        try:
            win.after(300, lambda k=key: save_settings({"quality_settings_last_tab": k}))
        except Exception:
            pass

    def _make_tab_btn(text, key, tip):
        b = CompatCTkButton(
            tabbar_inner, text=text,
            command=lambda k=key: _show_tab(k),
            width=scaled_size(110, min_size=90),
            height=scaled_size(30, min_size=28),
            corner_radius=8,
            fg_color=Colors.BG_INPUT, hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(10), "bold"),
        )
        b.pack(side="left", padx=3)
        ToolTip(b, tip)
        _tab_buttons[key] = b
        return b

    _make_tab_btn("🎙️ RVC", "rvc", "Пост-обработка голоса RVC")
    _make_tab_btn("✂️ Обрезка", "trim", "Ползунок и режим trim")
    _make_tab_btn("💾 Вывод", "out", "Формат, де-эссер и контроль качества")
    _make_tab_btn("🎛 XTTS", "xtts", "Параметры генерации модели")

    def _panel(key):
        f = tk.Frame(panels_host, bg=Colors.BG_DARK)
        _tabs[key] = f
        return f

    # ══════════════════════════════════════════
    #  A. RVC
    # ══════════════════════════════════════════
    panel_rvc = _panel("rvc")
    rvc_card, rvc_body = _section_card(
        panel_rvc,
        title="🎙️ RVC · улучшение голоса",
        subtitle="Накладывает тембр RVC-модели на XTTS. Включите и выберите модель.",
        accent=Colors.ACCENT if hasattr(Colors, "ACCENT") else None,
    )

    _rvc_enable_text = _strip_check_mark(
        t("chk_rvc_enable"), "Использовать RVC пост-обработку"
    )
    chk_rvc = ctk.CTkCheckBox(
        rvc_body, text=_rvc_enable_text, variable=params["rvc_enable"],
        fg_color=Colors.BG_ACTIVE, hover_color=Colors.BG_HOVER,
        border_color=Colors.BORDER, text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(12), "bold"),
    )
    chk_rvc.pack(anchor="w", pady=(0, 6))
    ToolTip(chk_rvc, t("tip_rvc_enable"))

    rvc_controls = tk.Frame(rvc_body, bg=Colors.BG_CARD)
    rvc_controls.pack(fill="x")

    model_row = tk.Frame(rvc_controls, bg=Colors.BG_CARD)
    model_row.pack(fill="x", pady=4)
    lbl_model_title = tk.Label(
        model_row, text=t("lbl_rvc_model"), anchor="w",
        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(10)),
    )
    lbl_model_title.pack(side="left")
    ToolTip(lbl_model_title, t("tip_rvc_model"))
    model_dropdown = RVCModelDropdown(
        model_row, params["rvc_model"], t,
        on_status=lambda text: _safe_call(set_status, text),
        on_progress=lambda pct: _safe_call(set_progress, pct),
        on_show_cancel=lambda cb: _safe_call(show_cancel_button, cb),
        on_hide_cancel=lambda: _safe_call(hide_cancel_button),
    )
    model_dropdown.pack(side="right")

    index_scale, lbl_index_title, lbl_index_val = _slider_row(
        rvc_controls, t("lbl_rvc_index"), params["rvc_index_rate"],
        0.0, 1.0, 0.05,
        "Насколько сильно подмешивается index-файл модели.\n"
        "Выше — ближе к тембру RVC, но возможны артефакты.",
    )
    pitch_scale, lbl_pitch_title, lbl_pitch_val = _slider_row(
        rvc_controls, t("lbl_rvc_pitch"), params["rvc_pitch_shift"],
        -12, 12, 1,
        "Сдвиг тона в полутонах (+ выше, − ниже).\n"
        "0 — без изменения высоты.",
    )

    f0_row = tk.Frame(rvc_controls, bg=Colors.BG_CARD)
    f0_row.pack(fill="x", pady=4)
    lbl_f0_title = tk.Label(
        f0_row, text=t("lbl_rvc_f0_method"), anchor="w",
        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(10)),
    )
    lbl_f0_title.pack(side="left")
    ToolTip(
        lbl_f0_title,
        "Алгоритм извлечения высоты тона.\n"
        "rmvpe — обычно лучший баланс; harvest/pm — альтернативы;\n"
        "crepe — точнее, но медленнее (особенно на CPU).",
    )
    f0_menu = ctk.CTkOptionMenu(
        f0_row,
        variable=params["rvc_f0_method"],
        values=["rmvpe", "harvest", "pm", "crepe"],
        fg_color=Colors.BG_INPUT,
        button_color=Colors.BG_INPUT,
        button_hover_color=Colors.BG_HOVER,
        dropdown_fg_color=Colors.BG_INPUT,
        dropdown_hover_color=Colors.BG_HOVER,
        text_color=Colors.TEXT_MAIN,
        dropdown_text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(10)),
        height=scaled_size(30, min_size=28),
        width=scaled_size(140, min_size=120),
    )
    f0_menu.pack(side="right")
    ToolTip(f0_menu, "Метод Pitch (f0) для RVC")

    def update_rvc_state(*args):
        try:
            enabled = params["rvc_enable"].get()
            state = "normal" if enabled else "disabled"
            model_dropdown.set_enabled(enabled)
            f0_menu.configure(state=state)
            index_scale.config(
                state=state,
                fg=Colors.TEXT_MAIN if enabled else Colors.TEXT_DIM,
                troughcolor=Colors.BG_INPUT if enabled else Colors.BG_DARK,
            )
            pitch_scale.config(
                state=state,
                fg=Colors.TEXT_MAIN if enabled else Colors.TEXT_DIM,
                troughcolor=Colors.BG_INPUT if enabled else Colors.BG_DARK,
            )
            dim = Colors.TEXT_MAIN if enabled else Colors.TEXT_DIM
            for w in (lbl_model_title, lbl_index_title, lbl_pitch_title, lbl_f0_title):
                w.config(fg=dim)
            accent_or_dim = Colors.ACCENT if enabled else Colors.TEXT_DIM
            lbl_index_val.config(fg=accent_or_dim)
            lbl_pitch_val.config(fg=accent_or_dim)
            if enabled:
                rvc_controls.pack(fill="x")
            else:
                rvc_controls.pack_forget()
            _force_scroll_update()
        except Exception:
            pass

    params["rvc_enable"].trace_add("write", update_rvc_state)
    update_rvc_state()

    # ══════════════════════════════════════════
    #  B. Trim
    # ══════════════════════════════════════════
    panel_trim = _panel("trim")
    trim_card, trim_body = _section_card(
        panel_trim,
        title="✂️ Обрезка хвоста",
        subtitle="Убирает тишину/хвост в конце. Ползунок активен только в режиме Manual.",
    )

    trim_scale, lbl_trim, _lbl_trim_val = _slider_row(
        trim_body, t("lbl_trim"), params["trim_ms"],
        0, 300, 10,
        "Длина обрезки конца в миллисекундах.\n"
        "Работает при режиме Trim = Manual.",
    )

    lbl_trim_mode = tk.Label(
        trim_body, text=t("lbl_trim_mode"), anchor="w",
        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(11)),
    )
    lbl_trim_mode.pack(anchor="w", pady=(8, 2))
    ToolTip(
        lbl_trim_mode,
        "Auto — умная обрезка; Manual — ваш ползунок; Off — без обрезки.",
    )

    mode_row = tk.Frame(trim_body, bg=Colors.BG_CARD)
    mode_row.pack(fill="x")
    for txt_key, val, tip in [
        (t("trim_auto"), "auto", "Автоматическая обрезка хвоста"),
        (t("trim_manual"), "manual", "Ручная обрезка — задайте длину ползунком выше"),
        (t("trim_off"), "off", "Не обрезать конец"),
    ]:
        rb = tk.Radiobutton(
            mode_row, text=txt_key, variable=params["trim_mode"], value=val,
            bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, selectcolor=Colors.BG_INPUT,
            activebackground=Colors.BG_CARD,
            font=("Segoe UI", scaled_font_size(9)),
        )
        rb.pack(side="left", padx=(0, 10))
        ToolTip(rb, tip)

    def update_trim_state(*args):
        if not trim_scale:
            return
        try:
            if params["trim_mode"].get() == "manual":
                trim_scale.config(
                    state="normal", fg=Colors.TEXT_MAIN, troughcolor=Colors.BG_INPUT
                )
                lbl_trim.config(fg=Colors.TEXT_MAIN)
            else:
                trim_scale.config(
                    state="disabled", fg=Colors.TEXT_DIM, troughcolor=Colors.BG_DARK
                )
                lbl_trim.config(fg=Colors.TEXT_DIM)
        except Exception:
            pass

    params["trim_mode"].trace_add("write", update_trim_state)
    update_trim_state()

    # ══════════════════════════════════════════
    #  C. Output
    # ══════════════════════════════════════════
    panel_out = _panel("out")
    out_card, out_body = _section_card(
        panel_out,
        title="💾 Вывод",
        subtitle="Формат файла, де-эссер и авто-проверка качества чанков.",
    )

    lbl_fmt = tk.Label(
        out_body, text=t("lbl_export_format"), anchor="w",
        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(11)),
    )
    lbl_fmt.pack(anchor="w", pady=(0, 2))
    ToolTip(lbl_fmt, "Итоговый формат файла после генерации.")

    fmt_row = tk.Frame(out_body, bg=Colors.BG_CARD)
    fmt_row.pack(fill="x", pady=(0, 8))
    rb_wav = tk.Radiobutton(
        fmt_row, text="WAV", variable=params["export_format"], value="wav",
        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, selectcolor=Colors.BG_INPUT,
        activebackground=Colors.BG_CARD, font=("Segoe UI", scaled_font_size(9)),
    )
    rb_wav.pack(side="left", padx=(0, 10))
    ToolTip(rb_wav, "Без потерь, больше размер — лучше для монтажа.")
    rb_mp3 = tk.Radiobutton(
        fmt_row, text="MP3 192k", variable=params["export_format"], value="mp3",
        bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN, selectcolor=Colors.BG_INPUT,
        activebackground=Colors.BG_CARD, font=("Segoe UI", scaled_font_size(9)),
    )
    rb_mp3.pack(side="left")
    ToolTip(rb_mp3, "Меньший размер, сжатие с потерями.")

    # Де-эссер — постобработка вывода (рядом с форматом/QC), не параметр модели
    _slider_row(
        out_body, t("lbl_deesser"), params["de_esser_intensity"],
        0.0, 2.0, 0.1,
        "Подавление шипящих (s/sh) в итоговом аудио.\n0 — выкл, выше — сильнее фильтрация.",
    )

    _qc_text = _strip_check_mark(
        t("chk_qc"), "Контроль качества (перегенерация брака)"
    )
    qc_cb = ctk.CTkCheckBox(
        out_body, text=_qc_text, variable=params["qc_enabled"],
        fg_color=Colors.BG_ACTIVE, hover_color=Colors.BG_HOVER,
        border_color=Colors.BORDER, text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(12), "bold"),
    )
    qc_cb.pack(anchor="w", pady=(8, 0))
    ToolTip(qc_cb, t("tip_qc"))

    # ══════════════════════════════════════════
    #  D. XTTS (параметры генерации модели)
    # ══════════════════════════════════════════
    panel_xtts = _panel("xtts")
    xtts_card, xtts_body = _section_card(
        panel_xtts,
        title="🎛 Параметры XTTS",
        subtitle="Тонкая настройка генерации. Обычно достаточно значений пресета.",
    )

    fields = [
        ("temperature", t("lbl_temperature"), 0.1, 1.0, 0.05,
         "Случайность голоса.\nВыше — разнообразнее, ниже — стабильнее."),
        ("top_p", t("lbl_top_p"), 0.1, 1.0, 0.05,
         "Ограничивает набор вероятных вариантов (nucleus sampling)."),
        ("top_k", t("lbl_top_k"), 10, 100, 5,
         "Сколько лучших вариантов рассматривает модель."),
        ("repetition_penalty", t("lbl_rep_penalty"), 1.0, 20.0, 0.5,
         "Штраф за повторы. Выше — меньше зацикливаний."),
        ("speed", t("lbl_speed"), 0.75, 2.25, 0.05,
         "Скорость речи. 1.0 — нормальная."),
        ("prosody_intensity", t("lbl_prosody"), 0.0, 2.0, 0.1,
         "Выразительность / интонация (просодия)."),
    ]
    for key, label, from_, to, res, hint in fields:
        _slider_row(xtts_body, label, params[key], from_, to, res, hint)

    def reset():
        defaults = {
            "Высокое качество": (0.70, 0.30, 80, 13.0, 1.0, 100, "auto", 0.0, 0.8),
            "Нарратив": (0.75, 0.25, 85, 18.0, 0.9, 80, "auto", 0.5, 0.7),
            "Динамика": (0.82, 0.20, 100, 16.0, 1.1, 60, "auto", 1.1, 1.0),
            "Экспрессия": (0.88, 0.30, 90, 14.0, 1.0, 100, "auto", 1.3, 1.3),
        }
        d = defaults.get(preset_name, (0.70, 0.30, 80, 13.0, 1.0, 80, "auto", 0.8, 1.0))
        params["temperature"].set(d[0]); params["top_p"].set(d[1]); params["top_k"].set(d[2])
        params["repetition_penalty"].set(d[3]); params["speed"].set(d[4]); params["trim_ms"].set(d[5])
        params["trim_mode"].set(d[6]); params["prosody_intensity"].set(d[7]); params["de_esser_intensity"].set(d[8])
        params["export_format"].set("wav")

        rvc_defaults = {
            "Высокое качество": (False, "Не выбрана", 0.75, 0, "rmvpe"),
            "Нарратив": (False, "Не выбрана", 0.85, 0, "rmvpe"),
            "Динамика": (False, "Не выбрана", 0.65, 0, "pm"),
            "Экспрессия": (False, "Не выбрана", 0.75, 0, "harvest"),
        }
        rd = rvc_defaults.get(preset_name, (False, "Не выбрана", 0.75, 0, "rmvpe"))
        params["rvc_enable"].set(rd[0])
        params["rvc_model"].set(rd[1])
        params["rvc_index_rate"].set(rd[2])
        params["rvc_pitch_shift"].set(rd[3])
        params["rvc_f0_method"].set(rd[4])

    def _force_scroll_update():
        try:
            win.update_idletasks()
            canvas = scroll._parent_canvas
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass

    # Стартовая вкладка: последняя из settings.json, иначе RVC
    _start_tab = "rvc"
    try:
        _st = _load_app_settings() if callable(_load_app_settings) else {}
        cand = (_st or {}).get("quality_settings_last_tab")
        if cand in ("rvc", "trim", "out", "xtts"):
            _start_tab = cand
    except Exception:
        pass
    _show_tab(_start_tab)

    win.after(200, _force_scroll_update)
    win.after(500, _force_scroll_update)
    win.after(150, lambda: _apply_window_icon(win))
