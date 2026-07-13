# -*- coding: utf-8 -*-
"""engine/gui/ai_conductor.py — окно AI Conductor, предупреждение и
пульс-анимация кнопки AI (перенесено из gui.py: open_ai_conductor_window,
_ai_pulse_tick, set_ai_pulse)."""
import json
import tkinter as tk

from i18n import t

from engine.settings_store import SETTINGS_PATH, load_settings
from engine.gui.colors import Colors, scaled_font_size
from engine.gui.widgets import create_button

# Внедряются из main_window: root, quality_params, save_settings
root = None
quality_params = {}
save_settings = None

# Кнопка 🤖 AI (создаётся в engine.gui.toolbar и внедряется сюда)
ai_btn = None


def init(**deps):
    """Внедрение зависимостей из engine.gui.main_window (имена совпадают с
    именами глобальных переменных исходного gui.py)."""
    globals().update(deps)


AI_CONDUCTOR_WARNING_INTERVAL = 3
_conductor_warning_session_resolved = False
_conductor_warning_pending = False


def _set_placeholder(text_widget, placeholder):
    """Показать серую подсказку-плейсхолдер в отключённом (disabled) поле."""
    text_widget.config(state="normal")
    text_widget.delete("1.0", "end")
    text_widget.insert("1.0", placeholder)
    text_widget.tag_add("placeholder", "1.0", "end")
    text_widget.tag_config("placeholder", foreground=Colors.TEXT_DIM)
    text_widget.config(state="disabled")


def _clear_placeholder(text_widget, placeholder):
    """Убрать плейсхолдер перед тем, как поле станет редактируемым."""
    text_widget.config(state="normal")
    if text_widget.get("1.0", "end-1c") == placeholder:
        text_widget.delete("1.0", "end")
    text_widget.tag_remove("placeholder", "1.0", "end")


def _get_real_value(text_widget, placeholder):
    """Вернуть содержимое поля, игнорируя плейсхолдер."""
    val = text_widget.get("1.0", "end-1c").strip()
    return "" if val == placeholder else val


def open_ai_conductor_window():
    global _conductor_warning_session_resolved, _conductor_warning_pending
    if not _conductor_warning_session_resolved:
        s_check = load_settings()
        dismissed_forever = s_check.get("ai_conductor_warning_dismissed", False)
        open_count = s_check.get("ai_conductor_open_count", 0) + 1
        s_check["ai_conductor_open_count"] = open_count
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(s_check, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        _conductor_warning_pending = (not dismissed_forever) and (
            open_count % AI_CONDUCTOR_WARNING_INTERVAL == 1
        )
        _conductor_warning_session_resolved = True

    should_warn = _conductor_warning_pending
    if should_warn:
        _conductor_warning_pending = False

        def _show_conductor_warning():
            dlg = tk.Toplevel(root)
            dlg.title("AI Conductor")
            dlg.resizable(False, False)
            dlg.configure(bg=Colors.BG_CARD)
            dlg.grab_set()
            tk.Label(
                dlg,
                text=t("conductor_experimental"),
                bg=Colors.BG_CARD,
                fg="#d29922",
                font=("Segoe UI", scaled_font_size(12), "bold"),
            ).pack(padx=24, pady=(20, 8))
            tk.Label(
                dlg,
                text=t("conductor_warning_text"),
                bg=Colors.BG_CARD,
                fg=Colors.TEXT_MAIN,
                font=("Segoe UI", scaled_font_size(9)),
                justify="center",
            ).pack(padx=24, pady=(0, 16))
            dont_show_var = tk.BooleanVar(value=False)
            tk.Checkbutton(
                dlg,
                text=t("conductor_dont_show"),
                variable=dont_show_var,
                bg=Colors.BG_CARD,
                fg=Colors.TEXT_DIM,
                selectcolor=Colors.BG_INPUT,
                activebackground=Colors.BG_CARD,
                font=("Segoe UI", scaled_font_size(9)),
                cursor="hand2",
            ).pack(pady=(0, 12))

            def _close_warning():
                if dont_show_var.get():
                    s2 = load_settings()
                    s2["ai_conductor_warning_dismissed"] = True
                    try:
                        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                            json.dump(s2, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        print(f"[Warning] ошибка сохранения: {e}")
                dlg.grab_release()
                dlg.destroy()
                root.after(50, open_ai_conductor_window)

            create_button(dlg, t("conductor_understood"), _close_warning, bg=Colors.BG_ACTIVE).pack(
                pady=(0, 20)
            )
            dlg.protocol("WM_DELETE_WINDOW", _close_warning)

        _show_conductor_warning()
        return

    win = tk.Toplevel(root)
    win.title(t("win_conductor_title"))
    win.resizable(False, False)
    win.configure(bg=Colors.BG_CARD)
    win.grab_set()

    # Состояние
    ai_enabled_var = tk.BooleanVar(value=False)
    ai_preset_var = tk.StringVar(value="Все пресеты")
    ai_rewrite_var = tk.BooleanVar(value=False)
    s = load_settings()
    ai_enabled_var.set(s.get("ai_conductor_enabled", False))
    ai_preset_var.set(s.get("ai_conductor_preset", "Все пресеты"))
    ai_rewrite_var.set(s.get("ai_rewrite_enabled", False))

    # Плейсхолдеры-подсказки для полей стиля (показываются, когда поля отключены)
    STYLE_PLACEHOLDER = t("conductor_style_placeholder")
    NEGATIVE_PLACEHOLDER = t("conductor_negative_placeholder")

    # Заголовок
    tk.Label(
        win,
        text=t("conductor_header"),
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(13), "bold"),
    ).pack(padx=20, pady=(18, 4))
    tk.Label(
        win,
        text=t("conductor_desc"),
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(9)),
        justify="left",
    ).pack(padx=20, pady=(0, 6))
    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x", padx=20, pady=(0, 12))

    # Включить/выключить
    enable_row = tk.Frame(win, bg=Colors.BG_CARD)
    enable_row.pack(fill="x", padx=20, pady=(0, 10))

    def toggle_enabled():
        ai_enabled_var.set(not ai_enabled_var.get())
        toggle_btn_cond.config(
            text=t("conductor_enabled") if ai_enabled_var.get() else t("conductor_disabled"),
            bg=Colors.BG_ACTIVE if ai_enabled_var.get() else Colors.BG_INPUT,
        )

    toggle_btn_cond = tk.Button(
        enable_row,
        text=t("conductor_enabled") if ai_enabled_var.get() else t("conductor_disabled"),
        command=toggle_enabled,
        bg=Colors.BG_ACTIVE if ai_enabled_var.get() else Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        activebackground=Colors.BG_HOVER,
        activeforeground=Colors.TEXT_MAIN,
        relief="flat",
        bd=0,
        font=("Segoe UI", scaled_font_size(10), "bold"),
        cursor="hand2",
        padx=12,
        pady=5,
    )
    toggle_btn_cond.pack(side="left")

    # Применять к пресету
    preset_row = tk.Frame(win, bg=Colors.BG_CARD)
    preset_row.pack(fill="x", padx=20, pady=(0, 6))
    tk.Label(
        preset_row,
        text=t("conductor_apply_to"),
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(9)),
    ).pack(side="left", padx=(0, 10))

    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x", padx=20, pady=(10, 10))
    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x", padx=20, pady=(10, 10))

    # --- Уровень 2: Стиль текста ---
    rewrite_row = tk.Frame(win, bg=Colors.BG_CARD)
    rewrite_row.pack(fill="x", padx=20, pady=(0, 6))

    def toggle_rewrite():
        ai_rewrite_var.set(not ai_rewrite_var.get())
        rewrite_btn.config(
            text=t("conductor_rewrite_on") if ai_rewrite_var.get() else t("conductor_rewrite_off"),
            bg=Colors.BG_ACTIVE if ai_rewrite_var.get() else Colors.BG_INPUT,
        )
        is_on = ai_rewrite_var.get()
        if is_on:
            _clear_placeholder(rewrite_text, STYLE_PLACEHOLDER)
            _clear_placeholder(rewrite_negative_text, NEGATIVE_PLACEHOLDER)
            rewrite_text.config(state="normal")
            rewrite_negative_text.config(state="normal")
            rewrite_text.focus_set()
        else:
            if not _get_real_value(rewrite_text, STYLE_PLACEHOLDER):
                _set_placeholder(rewrite_text, STYLE_PLACEHOLDER)
            else:
                rewrite_text.config(state="disabled")
            if not _get_real_value(rewrite_negative_text, NEGATIVE_PLACEHOLDER):
                _set_placeholder(rewrite_negative_text, NEGATIVE_PLACEHOLDER)
            else:
                rewrite_negative_text.config(state="disabled")

    rewrite_btn = tk.Button(
        rewrite_row,
        text=t("conductor_rewrite_on") if ai_rewrite_var.get() else t("conductor_rewrite_off"),
        command=toggle_rewrite,
        bg=Colors.BG_ACTIVE if ai_rewrite_var.get() else Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        activebackground=Colors.BG_HOVER,
        activeforeground=Colors.TEXT_MAIN,
        relief="flat",
        bd=0,
        font=("Segoe UI", scaled_font_size(10), "bold"),
        cursor="hand2",
        padx=12,
        pady=5,
    )
    rewrite_btn.pack(side="left")
    tk.Label(
        win,
        text=t("conductor_rewrite_desc"),
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(8)),
        justify="left",
    ).pack(fill="x", padx=20, pady=(4, 6))
    tk.Label(
        win,
        text=t("conductor_style_prompt"),
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(9)),
        anchor="w",
    ).pack(fill="x", padx=20, pady=(0, 4))
    rewrite_text = tk.Text(
        win,
        height=4,
        width=48,
        bg=Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        insertbackground=Colors.TEXT_MAIN,
        relief="flat",
        font=("Segoe UI", scaled_font_size(9)),
        highlightthickness=1,
        highlightbackground=Colors.BORDER,
        padx=8,
        pady=6,
        wrap="word",
    )
    rewrite_text.pack(fill="x", padx=20, pady=(0, 4))
    _saved_rewrite = s.get("ai_rewrite_context", "")
    if _saved_rewrite:
        rewrite_text.insert("1.0", _saved_rewrite)
    if not ai_rewrite_var.get():
        if _saved_rewrite:
            rewrite_text.config(state="disabled")
        else:
            _set_placeholder(rewrite_text, STYLE_PLACEHOLDER)

    tk.Label(
        win,
        text=t("conductor_negative_prompt"),
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(9)),
        anchor="w",
    ).pack(fill="x", padx=20, pady=(6, 4))
    rewrite_negative_text = tk.Text(
        win,
        height=2,
        width=48,
        bg=Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        insertbackground=Colors.TEXT_MAIN,
        relief="flat",
        font=("Segoe UI", scaled_font_size(9)),
        highlightthickness=1,
        highlightbackground=Colors.BORDER,
        padx=8,
        pady=6,
        wrap="word",
    )
    rewrite_negative_text.pack(fill="x", padx=20, pady=(0, 4))
    _saved_rewrite_negative = s.get("ai_rewrite_negative", "")
    if _saved_rewrite_negative:
        rewrite_negative_text.insert("1.0", _saved_rewrite_negative)
    if not ai_rewrite_var.get():
        if _saved_rewrite_negative:
            rewrite_negative_text.config(state="disabled")
        else:
            _set_placeholder(rewrite_negative_text, NEGATIVE_PLACEHOLDER)

    preset_options = [t("conductor_all_presets")] + list(quality_params.keys())
    for opt in preset_options:
        tk.Radiobutton(
            preset_row,
            text=opt,
            variable=ai_preset_var,
            value=opt,
            bg=Colors.BG_CARD,
            fg=Colors.TEXT_MAIN,
            selectcolor=Colors.BG_INPUT,
            activebackground=Colors.BG_CARD,
            font=("Segoe UI", scaled_font_size(9)),
            cursor="hand2",
        ).pack(side="left", padx=(0, 8))

    tk.Frame(win, bg=Colors.BORDER, height=1).pack(fill="x", padx=20, pady=(10, 10))

    # Инфо о провайдере
    try:
        from engine.gpt_client import get_provider, get_model, PROVIDERS

        prov = get_provider()
        model = get_model(prov)
        prov_label = PROVIDERS[prov]["label"]
        info_text = t("conductor_provider_label", f"{prov_label}\nМодель: {model}")
    except Exception:
        info_text = t("conductor_provider_none")
    tk.Label(
        win,
        text=info_text,
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_DIM,
        font=("Consolas", scaled_font_size(8)),
        justify="left",
    ).pack(padx=20, pady=(0, 12), anchor="w")

    # Кнопки
    btn_row = tk.Frame(win, bg=Colors.BG_CARD)
    btn_row.pack(fill="x", padx=20, pady=(0, 18))

    def save_and_close():
        enabled = ai_enabled_var.get()
        preset_target = ai_preset_var.get()
        rewrite_value = _get_real_value(rewrite_text, STYLE_PLACEHOLDER)
        rewrite_negative_value = _get_real_value(rewrite_negative_text, NEGATIVE_PLACEHOLDER)
        # Map translated "Все пресеты" back to logic
        all_presets_label = t("conductor_all_presets")
        for preset_name, params in quality_params.items():
            if preset_target == all_presets_label or preset_target == preset_name:
                params["ai_conductor_enabled"].set(enabled)
                if "ai_rewrite_enabled" not in params:
                    params["ai_rewrite_enabled"] = tk.BooleanVar()
                params["ai_rewrite_enabled"].set(ai_rewrite_var.get())
                if "ai_rewrite_context" not in params:
                    params["ai_rewrite_context"] = tk.StringVar()
                params["ai_rewrite_context"].set(rewrite_value)
                if "ai_rewrite_negative" not in params:
                    params["ai_rewrite_negative"] = tk.StringVar()
                params["ai_rewrite_negative"].set(rewrite_negative_value)
        save_settings(extra={"ai_conductor_preset": preset_target})
        ai_btn.config(bg=Colors.BG_INPUT, fg=Colors.AI_ACCENT if enabled else Colors.TEXT_DIM)
        win.destroy()

    create_button(btn_row, t("btn_save"), save_and_close, bg=Colors.BG_ACTIVE).pack(
        side="left", padx=(0, 10)
    )
    create_button(btn_row, t("btn_cancel_dialog"), win.destroy, bg=Colors.BG_INPUT).pack(
        side="left"
    )


_ai_pulse_active = {"v": False, "state": False}


def _ai_pulse_tick():
    if not _ai_pulse_active["v"]:
        return
    _ai_pulse_active["state"] = not _ai_pulse_active["state"]
    ai_btn.config(
        bg=Colors.AI_ACCENT if _ai_pulse_active["state"] else Colors.AI_ACCENT_HOVER,
        fg=Colors.TEXT_MAIN,
    )
    _ai_pulse_active["after_id"] = root.after(600, _ai_pulse_tick)


def set_ai_pulse(active: bool):
    global _ai_pulse_active
    if not active:
        _ai_pulse_active["v"] = False
        try:
            root.after_cancel(_ai_pulse_active.get("after_id", None))
        except Exception:
            pass
        enabled = any(
            params.get("ai_conductor_enabled", tk.BooleanVar()).get()
            for params in quality_params.values()
        )
        ai_btn.config(bg=Colors.AI_GROUP_BG, fg=Colors.AI_ACCENT if enabled else Colors.TEXT_DIM)
        return
    _ai_pulse_active["v"] = True
    _ai_pulse_active["state"] = False
    _ai_pulse_tick()
