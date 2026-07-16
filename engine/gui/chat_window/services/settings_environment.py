from __future__ import annotations

"""Карточка системного окружения в настройках AI.

Отвечает за проверку/установку/удаление окружения, постоянный лог установки,
окно полного лога, прокрутку, контекстное меню и UI отмены процесса.
"""

import os
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

from i18n import t
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
from engine.gui.chat_window.ui_utils import (
    _c,
    _safe_after,
    _set_dark_titlebar,
    _make_button,
)
from engine.gui.chat_window.hotkeys import _bind_text_hotkeys


def _log_env_error(ctx, stage: str, full_trace: str):
    """Пишет traceback в файл рядом с приложением — единственный способ его
    увидеть, если приложение запущено без консоли (pythonw/portable)."""
    try:
        from engine.paths import BASE_DIR

        log_path = os.path.join(BASE_DIR, "env_error_log.txt")
    except Exception:
        log_path = "env_error_log.txt"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"── {datetime.now().isoformat()} — {stage} ──\n{full_trace}\n\n")
    except Exception:
        pass


def _build_environment_section(ctx, container):
    """Карточка «Системное окружение»: проверка CPU/GPU, статус llama-cpp-python
    и (пере)установка библиотеки. Логика вынесена в auto_install_local_ai.

    ВАЖНО: контроллер — singleton (get_or_create_controller). При rebuild
    страницы (show_page / _invalidate_page) прогресс и лог НЕ сбрасываются:
    UI переподписывается и делает replay_to_ui()."""
    win = ctx.win
    _scroll_over_child = ctx.scroll_over_child
    from engine.gui.chat_window.auto_install_local_ai import (
        get_or_create_controller,
        get_shared_state,
        clear_shared_log,
    )

    # Очистить "залипший" чекпоинт, если библиотека уже установлена
    # (не создаём новый контроллер — только cleanup через shared)
    try:
        get_or_create_controller().cleanup_orphaned_checkpoint()
    except Exception:
        pass

    card_outer = tk.Frame(container, bg=_c("BORDER"))
    card_outer.pack(fill="x", pady=(0, 15))
    card = tk.Frame(card_outer, bg=_c("BG_CARD"))
    card.pack(fill="x", padx=1, pady=1)

    header = TkFrame(card, bg=_c("BG_CARD"))
    header.pack(fill="x", padx=14, pady=(12, 6))
    TkLabel(
        header,
        text=t("env_section_title"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 13, "bold"),
        anchor="w",
    ).pack(side="left")

    body = TkFrame(card, bg=_c("BG_CARD"))
    body.pack(fill="x", padx=14, pady=(0, 14))

    status_lbl = TkLabel(
        body,
        text=t("env_status_hint"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 12),
        anchor="w",
        wraplength=480,
        justify="left",
    )
    status_lbl.pack(fill="x", pady=(4, 10))

    btn_row = TkFrame(body, bg=_c("BG_CARD"))
    btn_row.pack(fill="x")

    # ── Лог-область (изначально скрыта, раскрывается при запуске процесса) ──
    log_frame = TkFrame(body, bg=_c("BORDER"), padx=1, pady=1)

    log_inner = TkFrame(log_frame, bg=_c("BG_INPUT"))
    log_inner.pack(fill="both", expand=True)
    log_sc = tk.Scrollbar(log_inner)
    log_sc.pack(side="right", fill="y")
    log_txt = tk.Text(
        log_inner,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        insertbackground=_c("TEXT_MAIN"),
        relief="flat",
        highlightthickness=0,
        font=("Consolas", 11),
        wrap="word",
        state="disabled",
        yscrollcommand=log_sc.set,
        height=8,
    )
    log_txt.pack(fill="both", expand=True, padx=6, pady=6)
    log_sc.config(command=log_txt.yview)
    _bind_text_hotkeys(log_txt)

    # ── Скролл: при наведении на консоль — крутим лог; вне — страницу ──
    def _log_wheel(event):
        try:
            if getattr(event, "num", None) == 4:
                log_txt.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                log_txt.yview_scroll(3, "units")
            else:
                delta = int(getattr(event, "delta", 0) or 0)
                if delta == 0:
                    return "break"
                log_txt.yview_scroll(-3 if delta > 0 else 3, "units")
            return "break"
        except Exception:
            return "break"

    def _log_enter(_e=None):
        _scroll_over_child["widget"] = log_txt

    def _log_leave(_e=None):
        if _scroll_over_child["widget"] is log_txt:
            _scroll_over_child["widget"] = None

    for _w in (log_txt, log_inner, log_frame, log_sc):
        try:
            _w.bind("<Enter>", _log_enter, add="+")
            _w.bind("<Leave>", _log_leave, add="+")
            _w.bind("<MouseWheel>", _log_wheel, add="+")
            _w.bind("<Button-4>", _log_wheel, add="+")
            _w.bind("<Button-5>", _log_wheel, add="+")
        except Exception:
            pass

    log_visible = [False]
    log_was_shown = [False]

    # ── Полный лог: отдельный, ничем не урезаемый буфер ────────────────────
    # Мини-консоль (log_txt) намеренно схлопывает \r-прогресс (pip/cmake),
    # чтобы не зависать на больших объёмах вывода. Полный лог должен хранить
    # ВООБЩЕ ВСЁ, что пришло через log_cb, независимо от этой оптимизации —
    # иначе окно "полного лога" просто дублирует урезанный снимок мини-консоли.
    _full_log_lines = []
    _full_log_ref = {"txt": None}

    def _safe_config(widget, **kwargs):
        """Безопасный config: не падает, если виджет уже уничтожен."""
        try:
            if widget.winfo_exists():
                widget.config(**kwargs)
        except tk.TclError:
            pass

    def _append_log(line):
        def _do():
            # ── Полный лог: пишем ВСЕГДА, без схлопывания \r-прогресса ──
            # Это единственное место, где строка попадает в приложение,
            # так что именно тут должен наполняться полный буфер —
            # до и независимо от любых оптимизаций мини-консоли ниже.
            full_line = line[1:] if line.startswith("\r") else line
            _full_log_lines.append(full_line)

            full_widget = _full_log_ref.get("txt")
            if full_widget is not None:
                try:
                    if full_widget.winfo_exists():
                        full_widget.insert("end", full_line + "\n")
                        full_widget.see("end")
                    else:
                        _full_log_ref["txt"] = None
                except Exception:
                    _full_log_ref["txt"] = None

            # ── Мини-консоль: схлопывает \r-прогресс pip/cmake в одну
            # строку, чтобы не зависать на больших объёмах вывода ──
            if not log_txt.winfo_exists():
                return
            log_txt.config(state="normal")
            if line.startswith("\r"):
                # Прогресс-бар pip: заменить последнюю строку
                last_line = int(log_txt.index("end-1c").split(".")[0])
                if last_line > 1:
                    log_txt.delete(f"{last_line-1}.0", "end-1c")
                log_txt.insert("end-1c", line[1:])
            else:
                log_txt.insert("end", line + "\n")
            log_txt.see("end")
            log_txt.config(state="disabled")

        _safe_after(0, _do)

    def _show_log(visible=True):
        log_visible[0] = visible
        if visible:
            log_was_shown[0] = True
            if log_frame.winfo_exists() and not log_frame.winfo_ismapped():
                log_frame.pack(fill="x", pady=(10, 0), expand=False)
                log_frame.pack_propagate(False)
                log_frame.config(height=140)
            if log_toggle_btn.winfo_exists():
                log_toggle_btn.config(text="▲")
                log_toggle_btn.pack(side="left", padx=(4, 0))
            if log_full_btn.winfo_exists():
                log_full_btn.pack(side="left", padx=(4, 0))
        else:
            if log_frame.winfo_exists() and log_frame.winfo_ismapped():
                log_frame.pack_forget()
            if log_was_shown[0]:
                if log_toggle_btn.winfo_exists():
                    log_toggle_btn.config(text="▼")
                    log_toggle_btn.pack(side="left", padx=(4, 0))
                if log_full_btn.winfo_exists():
                    log_full_btn.pack(side="left", padx=(4, 0))
            else:
                if log_toggle_btn.winfo_exists():
                    log_toggle_btn.pack_forget()
                if log_full_btn.winfo_exists():
                    log_full_btn.pack_forget()

    def _toggle_log():
        _show_log(not log_visible[0])

    def _show_full_log():
        """Открыть полный лог в отдельном окне.

        Источник — независимый несокращаемый буфер _full_log_lines,
        а не мини-консоль (та схлопывает \\r-прогресс ради производительности
        и поэтому не хранит всю историю). Пока окно открыто, новые строки
        дописываются сюда же живьём через _full_log_ref."""
        full_text = "\n".join(_full_log_lines)

        dlg = tk.Toplevel(win)
        _set_dark_titlebar(dlg)
        dlg.title(t("env_log_full_title"))
        dlg.geometry("720x520")
        dlg.configure(bg=_c("BG_CARD"))
        dlg.transient(win)

        outer = TkFrame(dlg, bg=_c("BORDER"), padx=1, pady=1)
        outer.pack(fill="both", expand=True, padx=16, pady=(16, 12))
        inner = TkFrame(outer, bg=_c("BG_INPUT"))
        inner.pack(fill="both", expand=True)
        sc = tk.Scrollbar(inner)
        sc.pack(side="right", fill="y")
        txt = tk.Text(
            inner,
            bg=_c("BG_INPUT"),
            fg=_c("TEXT_MAIN"),
            insertbackground=_c("TEXT_MAIN"),
            relief="flat",
            highlightthickness=0,
            font=("Consolas", 11),
            wrap="word",
            yscrollcommand=sc.set,
        )
        txt.pack(fill="both", expand=True, padx=6, pady=6)
        sc.config(command=txt.yview)
        _bind_text_hotkeys(txt)

        def _full_wheel(event):
            try:
                if getattr(event, "num", None) == 4:
                    txt.yview_scroll(-3, "units")
                elif getattr(event, "num", None) == 5:
                    txt.yview_scroll(3, "units")
                else:
                    delta = int(getattr(event, "delta", 0) or 0)
                    if delta == 0:
                        return "break"
                    txt.yview_scroll(-3 if delta > 0 else 3, "units")
                return "break"
            except Exception:
                return "break"

        txt.bind("<MouseWheel>", _full_wheel, add="+")
        txt.bind("<Button-4>", _full_wheel, add="+")
        txt.bind("<Button-5>", _full_wheel, add="+")

        txt.insert("1.0", full_text)
        txt.see("end")

        # Регистрируем виджет — пока окно открыто, _append_log будет
        # дописывать сюда новые строки в реальном времени.
        _full_log_ref["txt"] = txt

        def _on_full_log_close():
            _full_log_ref["txt"] = None
            dlg.destroy()

        dlg.protocol("WM_DELETE_WINDOW", _on_full_log_close)

        # Контекстное меню: копировать всё / выделенное
        ctx = tk.Menu(
            txt,
            tearoff=0,
            bg=_c("BG_INPUT"),
            fg=_c("TEXT_MAIN"),
            activebackground=_c("ACCENT"),
            activeforeground="#ffffff",
        )
        ctx.add_command(label=t("ctx_select_all"), command=lambda: txt.tag_add("sel", "1.0", "end"))
        ctx.add_command(
            label=t("env_log_copy_selection"),
            command=lambda: dlg.clipboard_append(txt.selection_get()),
        )
        ctx.add_command(
            label=t("env_log_copy_all"),
            command=lambda: (
                txt.tag_add("sel", "1.0", "end"),
                dlg.clipboard_append(txt.get("1.0", "end-1c")),
            ),
        )
        txt.bind("<Button-3>", lambda e: ctx.post(e.x_root, e.y_root))
        txt.bind("<Control-Button-1>", lambda e: ctx.post(e.x_root, e.y_root))

        def _copy_all():
            dlg.clipboard_clear()
            dlg.clipboard_append(txt.get("1.0", "end-1c"))

        def _copy_selection():
            try:
                selected = txt.selection_get()
                dlg.clipboard_clear()
                dlg.clipboard_append(selected)
            except tk.TclError:
                pass

        br = TkFrame(dlg, bg=_c("BG_CARD"))
        br.pack(fill="x", padx=16, pady=(0, 16))
        _make_button(
            br,
            t("env_log_copy_all"),
            _copy_all,
            bg=_c("BG_INPUT"),
            font_size=11,
            height=1,
            padx=8,
            pady=3,
        ).pack(side="left", padx=(0, 6))
        _make_button(
            br,
            t("env_log_copy_selection"),
            _copy_selection,
            bg=_c("BG_INPUT"),
            font_size=11,
            height=1,
            padx=8,
            pady=3,
        ).pack(side="left")
        _make_button(
            br,
            t("chat_btn_close_x"),
            _on_full_log_close,
            bg=_c("BG_ACTIVE"),
            font_size=11,
            height=1,
            padx=8,
            pady=3,
        ).pack(side="right")

    def _set_buttons(checking=False, installing=False):
        if checking:
            _safe_config(check_btn, state="disabled", text=t("env_btn_checking"))
            _safe_config(install_btn, state="disabled", text=t("env_btn_install_short"))
            _safe_config(remove_btn, state="disabled")
        elif installing:
            _safe_config(check_btn, state="disabled", text=t("env_btn_check_short"))
            _safe_config(install_btn, state="disabled", text=t("env_btn_installing"))
            _safe_config(remove_btn, state="disabled")
        else:
            _safe_config(check_btn, state="normal", text=t("env_btn_check_short"))
            _safe_config(install_btn, state="normal", text=t("env_btn_install_short"))
            _safe_config(remove_btn, state="normal")

    def _set_status(text, color_key):
        color_map = {
            "success": _c("TEXT_SUCCESS"),
            "error": _c("TEXT_ERROR"),
            "dim": _c("TEXT_DIM"),
            "main": _c("TEXT_MAIN"),
        }
        _safe_config(status_lbl, text=text, fg=color_map.get(color_key, _c("TEXT_DIM")))

    controller = get_or_create_controller(
        log_cb=_append_log,
        status_cb=_set_status,
        buttons_cb=lambda c, i: _set_buttons(checking=c, installing=i),
        error_cb=lambda title, tb: _log_env_error(ctx, title, tb),
    )

    # Восстановить лог/статус/кнопки после rebuild страницы (не сбрасывать прогресс)
    def _restore_from_shared():
        st = get_shared_state()
        if st["log_lines"] or st["running"] or st["status_text"]:
            # не дублируем в _full_log_lines через _append_log — наполним напрямую
            _full_log_lines.clear()
            _full_log_lines.extend(st["log_lines"])
            try:
                log_txt.config(state="normal")
                log_txt.delete("1.0", "end")
                for line in st["log_lines"]:
                    log_txt.insert("end", line + "\n")
                log_txt.see("end")
                log_txt.config(state="disabled")
            except Exception:
                pass
            if st["log_lines"] or st["running"]:
                _show_log(True)
            if st["status_text"]:
                _set_status(st["status_text"], st["status_color"] or "dim")
            _set_buttons(checking=st["checking"], installing=st["installing"])
        # live callbacks already bound via get_or_create_controller

    _restore_from_shared()

    def _run_check():
        _show_log(True)
        controller.check_environment()

    def _prompt_resume_and_install():
        stage = controller.get_resume_stage()
        if stage:
            resume = messagebox.askyesno(
                t("env_resume_title"),
                t("env_resume_msg", stage),
                parent=win,
            )
        else:
            resume = False
        _show_log(True)
        controller.install(resume=resume)

    def _run_uninstall():
        if not messagebox.askyesno(t("env_uninstall_title"), t("env_uninstall_msg"), parent=win):
            return
        _show_log(True)
        controller.uninstall()

    def _cancel_process():
        controller.request_cancel()

    def _clear_log():
        log_txt.config(state="normal")
        log_txt.delete("1.0", "end")
        log_txt.config(state="disabled")
        _full_log_lines.clear()
        try:
            clear_shared_log()
        except Exception:
            pass
        full_widget = _full_log_ref.get("txt")
        if full_widget is not None:
            try:
                if full_widget.winfo_exists():
                    full_widget.delete("1.0", "end")
                else:
                    _full_log_ref["txt"] = None
            except Exception:
                _full_log_ref["txt"] = None

    def _copy_log():
        log_txt.config(state="normal")
        content = log_txt.get("1.0", "end-1c")
        log_txt.config(state="disabled")
        try:
            body.clipboard_clear()
            body.clipboard_append(content)
        except Exception:
            pass

    # ── Контекстное меню ───────────────────────────────────────────────────
    menu = tk.Menu(
        body,
        tearoff=0,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        activebackground=_c("ACCENT"),
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
    )
    menu.add_command(label=t("env_ctx_copy_log"), command=_copy_log)
    menu.add_command(label=t("env_ctx_clear_log"), command=_clear_log)
    menu.add_separator()
    menu.add_command(label=t("env_ctx_cancel"), command=_cancel_process, state="disabled")
    menu.add_command(label=t("env_ctx_hide_log"), command=lambda: _show_log(False))
    menu.add_command(label=t("env_ctx_show_log"), command=lambda: _show_log(True))

    def _update_menu_state():
        if controller.is_running():
            menu.entryconfig(t("env_ctx_cancel"), state="normal")
        else:
            menu.entryconfig(t("env_ctx_cancel"), state="disabled")

    def _show_context_menu(event):
        _update_menu_state()
        menu.post(event.x_root, event.y_root)

    for widget in (body, status_lbl, btn_row, log_txt):
        widget.bind("<Button-3>", _show_context_menu)
        widget.bind("<Control-Button-1>", _show_context_menu)

    check_btn = _make_button(
        btn_row,
        t("env_btn_check_short"),
        _run_check,
        bg=_c("BG_INPUT"),
        font_size=10,
        height=1,
        padx=6,
        pady=3,
    )
    check_btn.pack(side="left", padx=(0, 4))
    install_btn = _make_button(
        btn_row,
        t("env_btn_install_short"),
        _prompt_resume_and_install,
        bg=_c("BG_ACTIVE"),
        font_size=10,
        height=1,
        padx=6,
        pady=3,
    )
    install_btn.pack(side="left")
    remove_btn = _make_button(
        btn_row,
        "🗑",
        _run_uninstall,
        bg=_c("BG_INPUT"),
        font_size=10,
        height=1,
        width=3,
        padx=4,
        pady=3,
    )
    remove_btn.pack(side="left", padx=(4, 0))

    # Стрелка сворачивания лога (изначально скрыта, появляется вместе с логом)
    log_toggle_btn = _make_button(
        btn_row,
        "▲",
        _toggle_log,
        bg=_c("BG_INPUT"),
        font_size=10,
        height=1,
        width=3,
        padx=4,
        pady=3,
    )
    # Кнопка открытия полного лога в отдельном окне
    log_full_btn = _make_button(
        btn_row,
        t("env_log_full_btn"),
        _show_full_log,
        bg=_c("BG_INPUT"),
        font_size=10,
        height=1,
        width=3,
        padx=4,
        pady=3,
    )

    # Проверка не запускается автоматически — только по кнопке "Проверить"
    pass


def build_environment_section(ctx, container):
    """Публичный builder карточки для страницы локальных моделей."""
    return _build_environment_section(ctx, container)
