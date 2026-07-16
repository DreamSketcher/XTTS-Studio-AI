from __future__ import annotations

"""Оркестрация окна настроек AI и маршрутизация страниц.

Создаёт Toplevel, sidebar, scroll-canvas, кэш страниц и совместимые wrappers,
которые делегируют построение страниц специализированным engine-модулям.

PATCH 2026-07-14: плавный скролл колесом + анимация раскрытия страниц
через центральный AnimationManager.
"""
import json
import os
import sys
import threading
import uuid
from datetime import datetime
from tkinter import filedialog, messagebox
import tkinter as tk
import webbrowser

import engine.gui.chat_window.state as state
from engine.gui.chat_window.custom_widgets import (
    CTK_AVAILABLE,
    CTkFrame,
    CTkLabel,
    CTkButton,
    TkFrame,
    TkLabel,
    TkButton,
    TkRawFrame,
)
from i18n import t
from engine.gui.configure_coalescer import ConfigureCoalescer

# Убеждаемся, что папка site-packages bundled-окружения доступна для импортов
try:
    import sys
    from engine import env_setup

    if env_setup.SITE_PACKAGES not in sys.path:
        sys.path.insert(0, env_setup.SITE_PACKAGES)
except Exception:
    pass


from engine.gui.chat_window.ui_utils import (
    _c,
    _widget_exists,
    _set_dark_titlebar,
    _get_app_parent,
    _show_window,
)
from engine.gui.chat_window.services.settings_context import SettingsContext
from engine.gui.chat_window.services import settings_api
from engine.gui.chat_window.services import settings_local
from engine.gui.chat_window.services import settings_general
from engine.gui.chat_window.services import settings_environment


def open_gpt_settings(event=None):
    try:
        from engine import gpt_client
        from engine import local_llm_client
    except Exception as e:
        messagebox.showerror(
            t("chat_settings_title"),
            t("chat_err_load_gpt", e),
            parent=_get_app_parent() or state._root,
        )
        return "break"

    if _widget_exists(state._env_settings_window):
        _show_window(state._env_settings_window)
        return "break"

    win = tk.Toplevel(_get_app_parent() or state._root)
    _set_dark_titlebar(win)

    # Remove default feather icon
    try:
        win.iconbitmap("blank_icon.ico")
    except Exception:
        pass

    state._env_settings_window = win

    def _win_report_callback_exception(exc, val, tb):
        """Без этого переопределения Tkinter молча печатает traceback в stderr,
        который в portable-сборке без консоли (pythonw) никуда не попадает —
        кнопка визуально просто "не работает". Пишем в файл + показываем."""
        import traceback as _tb

        full_trace = "".join(_tb.format_exception(exc, val, tb))
        try:
            from engine.paths import BASE_DIR

            log_path = os.path.join(BASE_DIR, "env_error_log.txt")
        except Exception:
            log_path = "env_error_log.txt"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"── {datetime.now().isoformat()} — {t('chat_settings_title')} (необработанное) ──\n{full_trace}\n\n"
                )
        except Exception:
            pass
        try:
            messagebox.showerror(t("settings_win_error_title"), str(val), parent=win)
        except Exception:
            pass

    win.report_callback_exception = _win_report_callback_exception

    win.title(t("chat_settings_win_title"))
    # Compact AI settings window; content remains scrollable.
    # ~568×665 including standard Windows title bar/borders.
    win.geometry("566x630")
    win.minsize(500, 500)
    win.resizable(True, True)
    win.configure(bg=_c("BG_DARK"))
    win.transient(_get_app_parent() or state._root)

    # ── Layout: Sidebar + Content ──────────────────────────────────────────────
    main_container = TkFrame(win, bg=_c("BG_DARK"))
    main_container.pack(fill="both", expand=True)

    # Sidebar (Menu)
    sidebar = TkFrame(main_container, bg=_c("BG_CARD"), width=175)
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)

    TkLabel(
        sidebar,
        text=t("chat_settings_title"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 15, "bold"),
    ).pack(fill="x", padx=16, pady=(20, 20))

    # Content Area (with scroll)
    content_outer = TkFrame(main_container, bg=_c("BG_DARK"))
    content_outer.pack(side="left", fill="both", expand=True)

    canvas = tk.Canvas(content_outer, bg=_c("BG_CARD"), highlightthickness=0, bd=0)
    scrollbar = tk.Scrollbar(content_outer, orient="vertical", command=canvas.yview)

    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    canvas_frame = TkFrame(canvas, bg=_c("BG_CARD"))
    canvas_window = canvas.create_window((0, 0), window=canvas_frame, anchor="nw")

    def update_scroll_region(_width=0, _height=0):
        bbox = canvas.bbox("all")
        if bbox:
            # Не даём скроллить ниже реального контента
            h = max(bbox[3], canvas.winfo_height())
            canvas.configure(scrollregion=(bbox[0], bbox[1], bbox[2], h))

    def apply_canvas_size(width, _height):
        canvas.itemconfig(canvas_window, width=width)
        update_scroll_region()

    frame_configure = ConfigureCoalescer(canvas, update_scroll_region, threshold_px=3)
    canvas_configure = ConfigureCoalescer(canvas, apply_canvas_size, threshold_px=3)
    canvas_frame.bind("<Configure>", frame_configure)
    canvas.bind("<Configure>", canvas_configure)

    # Виджеты, которые хотят свой скролл (лог env, listbox и т.п.)
    # при Enter/Leave помечаются; page-wheel их не перехватывает.
    _scroll_over_child = {"widget": None}

    # ── PATCH 2026-07-14: helper for smooth scroll delta ────────────────────────
    def _estimate_scroll_delta(units: int) -> float:
        """Преобразует 'units' строк в дробь [0,1] для yview_moveto."""
        try:
            bbox = canvas.bbox("all")
            if not bbox:
                return units * 0.02
            total_h = float(max(1, bbox[3] - bbox[1]))
            LINE_HEIGHT = 24.0  # приблизительная высота строки настроек
            return units * LINE_HEIGHT / total_h
        except Exception:
            return units * 0.02

    _SCROLL_ANIM_ID = "_settings_smooth_scroll"
    _scroll_target = [None]

    def _on_mousewheel(event):
        try:
            # если курсор над дочерним scrollable (лог-консоль) — не скроллим страницу
            if _scroll_over_child["widget"] is not None:
                return None
            if getattr(event, "num", None) == 4:
                units = -8
            elif getattr(event, "num", None) == 5:
                units = 8
            else:
                delta = int(getattr(event, "delta", 0) or 0)
                if delta == 0:
                    return None
                steps = max(1, min(3, abs(delta) // 120 or 1))
                units = (-8 if delta > 0 else 8) * steps

            # PATCH 2026-07-14: плавный скролл через AnimationManager
            try:
                from engine.gui.animation_manager import AnimationManager

                mgr = AnimationManager.get()
                if mgr._no_op:
                    canvas.yview_scroll(units, "units")
                else:
                    current_top = canvas.yview()[0]
                    delta_frac = _estimate_scroll_delta(units)
                    # Accumulate rapid wheel events toward one destination.
                    # Starting every event from current_top alone makes fast
                    # scrolling feel sticky because each animation is cancelled.
                    base_target = (
                        _scroll_target[0]
                        if mgr.is_running(_SCROLL_ANIM_ID) and _scroll_target[0] is not None
                        else current_top
                    )
                    target = max(0.0, min(1.0, base_target + delta_frac))
                    _scroll_target[0] = target

                    if mgr.is_running(_SCROLL_ANIM_ID):
                        mgr.cancel(_SCROLL_ANIM_ID)

                    def _scroll_done():
                        _scroll_target[0] = None

                    mgr.animate(
                        target=canvas,
                        property_setter=lambda v: canvas.yview_moveto(v),
                        start=current_top,
                        end=target,
                        duration_ms=85,
                        easing="ease_out_cubic",
                        on_complete=_scroll_done,
                        animation_id=_SCROLL_ANIM_ID,
                    )
            except Exception:
                canvas.yview_scroll(units, "units")

            return "break"
        except Exception:
            return None

    for target in (win, canvas, canvas_frame):
        try:
            target.bind("<MouseWheel>", _on_mousewheel, add="+")
            target.bind("<Button-4>", _on_mousewheel, add="+")
            target.bind("<Button-5>", _on_mousewheel, add="+")
        except Exception:
            pass

    # ── Page Management ───────────────────────────────────────────────────────
    current_page = [None]
    _page_cache = {}

    def _invalidate_page(page_id):
        """Уничтожает закэшированный фрейм страницы, чтобы при следующем show_page()
        она была построена заново со свежими данными (например, после установки/
        удаления локальной модели список должен обновиться, а не остаться старым)."""
        frame = _page_cache.pop(page_id, None)
        if frame is not None:
            try:
                frame.destroy()
            except Exception:
                pass

    # ── PATCH 2026-07-14: плавное раскрытие страницы ──────────────────────────
    def _animate_page_expand(frame):
        """Анимирует высоту фрейма от 0 до естественной высоты (expand-эффект)."""
        try:
            from engine.gui.animation_manager import AnimationManager

            mgr = AnimationManager.get()
            if mgr._no_op:
                return
            frame.update_idletasks()
            target_h = frame.winfo_reqheight()
            if target_h <= 0:
                return
            frame.pack_propagate(False)
            frame.configure(height=0)
            mgr.animate(
                target=frame,
                property_setter=lambda v: frame.configure(height=max(1, int(v))),
                start=0,
                end=target_h,
                duration_ms=200,
                easing="ease_out",
                on_complete=lambda: frame.pack_propagate(True),
                animation_id=f"_page_expand_{id(frame)}",
            )
        except Exception:
            pass

    def show_page(page_id):
        # Скрываем все закэшированные страницы
        for pid, frame in list(_page_cache.items()):
            if frame is None or not frame.winfo_exists():
                del _page_cache[pid]
            else:
                frame.pack_forget()

        if page_id not in _page_cache or _page_cache[page_id] is None:
            if page_id == "api":
                frame = build_api_page()
            elif page_id == "local":
                frame = build_local_page()
            elif page_id == "general":
                frame = build_general_page()
            else:
                return
            if frame is None:
                return
            _page_cache[page_id] = frame
        else:
            frame = _page_cache[page_id]
            if frame is None:
                return

        frame.pack(fill="both", expand=True)
        # PATCH 2026-07-14: плавное раскрытие высоты
        _animate_page_expand(frame)
        update_scroll_region()
        current_page[0] = page_id

    # ── API Page implementation ───────────────────────────────────────────────

    # ── Модульные builders страниц ──────────────────────────────────────────
    # Прежние nested-имена намеренно сохранены как compatibility wrappers.
    ctx = SettingsContext(
        win=win,
        canvas=canvas,
        canvas_frame=canvas_frame,
        gpt_client=gpt_client,
        local_llm_client=local_llm_client,
        scroll_over_child=_scroll_over_child,
    )
    ctx.invalidate_page = _invalidate_page
    ctx.show_page = show_page

    def build_api_page():
        return settings_api.build_api_page(ctx)

    def build_local_page():
        return settings_local.build_local_page(ctx)

    def build_general_page():
        return settings_general.build_general_page(ctx)

    def _open_provider_form_internal(parent, edit_pid=None):
        return settings_api._open_provider_form_internal(ctx, parent, edit_pid)

    def _open_catalogue_internal(parent):
        return settings_api._open_catalogue_internal(ctx, parent)

    def _log_env_error(stage: str, full_trace: str):
        return settings_environment._log_env_error(ctx, stage, full_trace)

    def _build_environment_section(container):
        return settings_environment.build_environment_section(ctx, container)

    def create_menu_btn(text, page_id):
        btn = TkButton(
            sidebar,
            text=text,
            bg=_c("BG_CARD"),
            fg=_c("TEXT_DIM"),
            activebackground=_c("BG_INPUT"),
            activeforeground=_c("TEXT_MAIN"),
            relief="flat",
            bd=0,
            font=("Segoe UI", 11),
            anchor="w",
            cursor="hand2",
            command=lambda: show_page(page_id),
        )
        btn.pack(fill="x", padx=10, pady=2)
        return btn

    btn_gen = create_menu_btn(t("settings_menu_general"), "general")
    btn_api = create_menu_btn(t("settings_menu_api"), "api")
    btn_loc = create_menu_btn(t("settings_menu_local"), "local")

    def refresh_menu_style():
        for b, pid in [(btn_gen, "general"), (btn_api, "api"), (btn_loc, "local")]:
            if current_page[0] == pid:
                b.config(fg=_c("TEXT_MAIN"), bg=_c("BG_INPUT"))
            else:
                b.config(fg=_c("TEXT_DIM"), bg=_c("BG_CARD"))

    old_show_page = show_page

    def show_page_with_style(pid):
        old_show_page(pid)
        refresh_menu_style()

    ctx.show_page_with_style = show_page_with_style

    btn_gen.config(command=lambda: show_page_with_style("general"))
    btn_api.config(command=lambda: show_page_with_style("api"))
    btn_loc.config(command=lambda: show_page_with_style("local"))

    show_page_with_style("api")

    def close_settings(event=None):
        state._env_settings_window = None
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            return "break"
        return "break"

    win.bind("<Escape>", close_settings)
    win.protocol("WM_DELETE_WINDOW", close_settings)
    win.focus_set()
    return "break"
