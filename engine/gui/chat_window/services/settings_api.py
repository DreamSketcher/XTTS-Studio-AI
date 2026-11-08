from __future__ import annotations

"""Страница облачных и пользовательских API-провайдеров.

Отвечает за accordion провайдеров, API-ключи, выбор моделей, проверку ключей,
активацию/скрытие, формы custom-провайдеров и каталог провайдеров.
"""

import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox

from i18n import t
import engine.gui.chat_window.state as state
from engine.gui.chat_window.custom_widgets import (
    TkFrame,
    TkLabel,
    TkButton,
)
from engine.gui.chat_window.ui_utils import (
    _c,
    _safe_after,
    _set_dark_titlebar,
    _make_button,
)
from engine.gui.chat_window.hotkeys import _bind_text_hotkeys


def _bind_api_key_entry_editing(entry):
    """Полное редактирование masked API-key Entry.

    Прямые widget-bindings имеют приоритет над window-level hotkeys и работают
    независимо от активной раскладки клавиатуры (для Windows учитывается
    стабильный ``event.keycode``). Контекстное меню копирует реальное значение
    Entry, а не символы маски ``•``.
    """
    history = [entry.get()]
    redo_stack = []
    applying_history = {"value": False}

    def _selection_range():
        try:
            return int(entry.index(tk.SEL_FIRST)), int(entry.index(tk.SEL_LAST))
        except Exception:
            return None

    def _record_state(event=None):
        if applying_history["value"]:
            return None
        try:
            value = entry.get()
            if not history or history[-1] != value:
                history.append(value)
                if len(history) > 100:
                    del history[:-100]
                redo_stack.clear()
        except Exception:
            pass
        return None

    def _replace_value(value):
        applying_history["value"] = True
        try:
            entry.delete(0, tk.END)
            entry.insert(0, value)
            entry.icursor(tk.END)
        finally:
            applying_history["value"] = False

    def _select_all(event=None):
        try:
            entry.selection_range(0, tk.END)
            entry.icursor(tk.END)
        except Exception:
            pass
        return "break"

    def _copy(event=None):
        selected = _selection_range()
        if selected:
            try:
                start, end = selected
                entry.clipboard_clear()
                entry.clipboard_append(entry.get()[start:end])
                entry.update_idletasks()
            except Exception:
                pass
        return "break"

    def _cut(event=None):
        selected = _selection_range()
        if selected:
            _copy()
            try:
                entry.delete(selected[0], selected[1])
                _record_state()
            except Exception:
                pass
        return "break"

    def _paste(event=None):
        try:
            text = entry.clipboard_get()
        except Exception:
            return "break"
        try:
            selected = _selection_range()
            if selected:
                entry.delete(selected[0], selected[1])
            insert_at = int(entry.index(tk.INSERT))
            entry.insert(insert_at, text)
            entry.icursor(insert_at + len(text))
            _record_state()
        except Exception:
            pass
        return "break"

    def _undo(event=None):
        if len(history) > 1:
            try:
                redo_stack.append(history.pop())
                _replace_value(history[-1])
            except Exception:
                pass
        return "break"

    def _redo(event=None):
        if redo_stack:
            try:
                value = redo_stack.pop()
                history.append(value)
                _replace_value(value)
            except Exception:
                pass
        return "break"

    actions = {
        "a": _select_all,
        "c": _copy,
        "v": _paste,
        "x": _cut,
        "z": _undo,
        "y": _redo,
    }
    keycodes = {
        65: _select_all,  # A
        67: _copy,  # C
        86: _paste,  # V
        88: _cut,  # X
        90: _undo,  # Z
        89: _redo,  # Y
    }

    def _on_ctrl_keypress(event):
        # Mod1/Alt (включая AltGr) не должен превращаться в edit-команду.
        if int(getattr(event, "state", 0) or 0) & 0x0008:
            return None
        handler = keycodes.get(int(getattr(event, "keycode", 0) or 0))
        if handler is None:
            handler = actions.get(str(getattr(event, "keysym", "")).lower())
        return handler(event) if handler is not None else None

    # Перезаписываем generic Ctrl-binding после общего _bind_text_hotkeys().
    entry.bind("<Control-KeyPress>", _on_ctrl_keypress)
    entry.bind("<Control-Insert>", _copy)
    entry.bind("<Shift-Insert>", _paste)
    entry.bind("<Shift-Delete>", _cut)
    entry.bind("<KeyRelease>", _record_state, add="+")

    menu = tk.Menu(
        entry,
        tearoff=0,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        activebackground=_c("ACCENT"),
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
    )
    menu.add_command(label=t("ctx_cut"), command=_cut)
    menu.add_command(label=t("ctx_copy"), command=_copy)
    menu.add_command(label=t("ctx_paste"), command=_paste)
    menu.add_separator()
    menu.add_command(label=t("ctx_select_all"), command=_select_all)

    def _show_context_menu(event):
        selected = _selection_range() is not None
        try:
            entry.clipboard_get()
            can_paste = True
        except Exception:
            can_paste = False
        try:
            menu.entryconfigure(0, state="normal" if selected else "disabled")
            menu.entryconfigure(1, state="normal" if selected else "disabled")
            menu.entryconfigure(2, state="normal" if can_paste else "disabled")
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
        return "break"

    entry.bind("<Button-3>", _show_context_menu)
    entry.bind("<Control-Button-1>", _show_context_menu)
    # Ссылка не даёт меню быть собранным раньше виджета на некоторых Tk-сборках.
    entry._api_key_context_menu = menu


def build_api_page(ctx):
    win = ctx.win
    canvas_frame = ctx.canvas_frame
    gpt_client = ctx.gpt_client
    container = TkFrame(canvas_frame, bg=_c("BG_CARD"))
    container.pack(fill="both", expand=True, padx=20, pady=20)

    TkLabel(
        container,
        text=t("chat_providers_header"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 17, "bold"),
    ).pack(anchor="w", pady=(0, 15))

    accordion_state = {"expanded": gpt_client.get_ui_state().get("expanded_provider")}
    auto_refresh_state = {"started": False}
    accordion_container = TkFrame(container, bg=_c("BG_CARD"))
    accordion_container.pack(fill="x")

    def _all_provider_entries():
        entries = []
        hidden = gpt_client.get_hidden_providers()
        for pid, info in gpt_client.PROVIDERS.items():
            if pid == "local" or pid in hidden:
                continue
            entries.append((pid, info, False))
        for p in gpt_client.list_custom_providers():
            entries.append((p.get("id"), p, True))
        return entries

    HEALTH_GLYPHS = {
        "ok": "🟢",
        "invalid_key": "🔴",
        "rate_limited": "🟠",
        "network_error": "🔴",
        "models_error": "🔴",
        "error": "🔴",
        "unchecked": "⬜",
    }

    def _health_caption(pid):
        health = gpt_client.get_provider_health(pid)
        state_name = health.get("state") or "unchecked"
        text = t(f"chat_health_{state_name}")
        ts = health.get("ts")
        if ts:
            try:
                text = f"{text} · {time.strftime('%H:%M', time.localtime(ts))}"
            except Exception:
                pass
        return text

    def _deliver(callback):
        bridge = state._ui_bridge
        if bridge is not None:
            bridge.post(callback)
        else:
            _safe_after(0, callback)

    def _start_models_refresh(pid, force=True):
        """Фоновое обновление списка моделей; карточки перестроятся по завершении."""
        bridge = state._ui_bridge
        if bridge is not None:
            bridge.begin()

        def worker():
            try:
                gpt_client.refresh_provider_models(pid, force=force)
            except Exception as error:
                print(f"[AI] Не удалось обновить модели провайдера {pid}: {error}")
            finally:
                if bridge is not None:
                    bridge.producer_done()

            def done():
                try:
                    _rebuild_accordion()
                except Exception:
                    pass

            _deliver(done)

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_all_in_background():
        """Проверить все видимые провайдеры с ключом и loopback (TTL-gated)."""
        targets = []
        for pid, _info, _is_custom in _all_provider_entries():
            try:
                has_key = bool(gpt_client.get_api_key(pid))
            except Exception:
                has_key = False
            url = ""
            try:
                url = (gpt_client.effective_models_url(pid) or "").lower()
            except Exception:
                url = ""
            is_loopback = ("localhost" in url) or ("127.0.0.1" in url)
            if not has_key and not is_loopback:
                continue
            try:
                meta = gpt_client.get_models_cache_meta(pid)
                ts = meta.get("ts")
                fresh = ts and (time.time() - ts < gpt_client.MODELS_CACHE_TTL)
                if fresh:
                    continue
            except Exception:
                pass
            targets.append(pid)
        if not targets:
            return
        bridge = state._ui_bridge
        if bridge is not None:
            bridge.begin()

        def worker():
            for pid in targets:
                try:
                    gpt_client.refresh_provider_models(pid)
                except Exception as error:
                    print(f"[AI] Фоновая проверка {pid} не удалась: {error}")
            if bridge is not None:
                bridge.producer_done()

            def done():
                try:
                    _rebuild_accordion()
                except Exception:
                    pass

            _deliver(done)

        threading.Thread(target=worker, daemon=True).start()

    def _toggle_card(pid):
        accordion_state["expanded"] = None if accordion_state["expanded"] == pid else pid
        gpt_client.set_ui_state(expanded_provider=accordion_state["expanded"])
        _rebuild_accordion()
        if accordion_state["expanded"] == pid:
            # Только что раскрыт — подтягиваем живые модели, если кэш протух
            try:
                meta = gpt_client.get_models_cache_meta(pid)
                ts = meta.get("ts")
                fresh = ts and (time.time() - ts < gpt_client.MODELS_CACHE_TTL)
                if not fresh:
                    _start_models_refresh(pid, force=True)
            except Exception:
                pass

    def _rebuild_accordion():
        for child in accordion_container.winfo_children():
            child.destroy()

        active_pid = gpt_client.get_provider()
        for pid, info, is_custom in _all_provider_entries():
            is_expanded = accordion_state["expanded"] == pid
            is_active = pid == active_pid

            card_outer = tk.Frame(accordion_container, bg=_c("BORDER"))
            card_outer.pack(fill="x", pady=(0, 6))

            card = tk.Frame(card_outer, bg=_c("BG_CARD"))
            card.pack(fill="x", padx=1, pady=1)

            header = tk.Frame(card, bg=_c("BG_CARD"), cursor="hand2")
            header.pack(fill="x", padx=12, pady=10)

            arrow = "▾" if is_expanded else "▸"
            dot = "🟢" if is_active else ("🔧" if is_custom else "⚪")

            tk.Label(
                header,
                text=arrow,
                bg=_c("BG_CARD"),
                fg=_c("TEXT_DIM"),
                font=("Segoe UI", 12),
                width=2,
            ).pack(side="left")
            tk.Label(header, text=dot, bg=_c("BG_CARD"), font=("Segoe UI", 13)).pack(
                side="left", padx=(0, 4)
            )

            title_box = tk.Frame(header, bg=_c("BG_CARD"))
            title_box.pack(side="left", fill="x", expand=True)

            tk.Label(
                title_box,
                text=info.get("label", pid),
                bg=_c("BG_CARD"),
                fg=_c("TEXT_MAIN"),
                font=("Segoe UI", 13),
                anchor="w",
            ).pack(anchor="w")

            cur_model = gpt_client.get_model(pid)
            has_key = bool(gpt_client.get_api_key(pid))
            try:
                health_state = gpt_client.get_provider_health(pid).get("state") or "unchecked"
            except Exception:
                health_state = "unchecked"
            health_glyph = HEALTH_GLYPHS.get(health_state, "⬜")
            sub = f"{health_glyph} · {t('chat_key_set') if has_key else t('chat_key_none')} · {cur_model or '—'}"
            tk.Label(
                title_box,
                text=sub,
                bg=_c("BG_CARD"),
                fg=_c("TEXT_DIM"),
                font=("Segoe UI", 11),
                anchor="w",
            ).pack(anchor="w")

            if is_active:
                # Put the status under the title: it stays prominent without
                # competing with the provider name for horizontal space.
                tk.Label(
                    title_box,
                    text=f"● {t('chat_active_label')}",
                    bg=_c("BG_CARD"),
                    fg=_c("TEXT_SUCCESS"),
                    font=("Segoe UI", 10, "bold"),
                    anchor="w",
                ).pack(anchor="w", pady=(2, 0))

            header.bind("<Button-1>", lambda e, p=pid: _toggle_card(p))
            for w in title_box.winfo_children():
                w.bind("<Button-1>", lambda e, p=pid: _toggle_card(p))

            if not is_expanded:
                continue

            body = tk.Frame(card, bg=_c("BG_CARD"))
            body.pack(fill="x", padx=12, pady=(0, 12))
            tk.Frame(body, bg=_c("BORDER"), height=1).pack(fill="x", pady=(0, 10))

            TkLabel(
                body,
                text=t("chat_field_api_key"),
                bg=_c("BG_CARD"),
                fg=_c("TEXT_MAIN"),
                font=("Segoe UI", 12),
                anchor="w",
            ).pack(fill="x", pady=(0, 4))
            card_key_var = tk.StringVar(value=gpt_client.get_api_key(pid))
            key_row = tk.Frame(body, bg=_c("BG_CARD"))
            key_row.pack(fill="x")
            ke = tk.Entry(
                key_row,
                textvariable=card_key_var,
                show="•",
                bg=_c("BG_INPUT"),
                fg=_c("TEXT_MAIN"),
                insertbackground=_c("TEXT_MAIN"),
                relief="flat",
                highlightthickness=1,
                highlightbackground=_c("BORDER"),
                highlightcolor=_c("ACCENT"),
                font=("Consolas", 12),
            )
            ke.pack(side="left", fill="x", expand=True, ipady=5)
            _bind_text_hotkeys(ke)
            _bind_api_key_entry_editing(ke)

            show_v = tk.BooleanVar(value=False)
            tk.Checkbutton(
                key_row,
                text="👁",
                variable=show_v,
                command=lambda e=ke, v=show_v: e.config(show="" if v.get() else "•"),
                bg=_c("BG_CARD"),
                fg=_c("TEXT_DIM"),
                selectcolor=_c("BG_INPUT"),
                activebackground=_c("BG_CARD"),
                relief="flat",
                font=("Segoe UI", 11),
            ).pack(side="left", padx=(4, 0))

            hint = info.get("key_hint", "")
            if hint:
                url = hint if hint.startswith("http") else f"https://{hint}"
                link_lbl = tk.Label(
                    body,
                    text=hint,
                    bg=_c("BG_CARD"),
                    fg=_c("ACCENT"),
                    font=("Segoe UI", 12),
                    cursor="hand2",
                    anchor="w",
                )
                link_lbl.pack(fill="x", pady=(3, 8))
                link_lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

            models_label_row = tk.Frame(body, bg=_c("BG_CARD"))
            models_label_row.pack(fill="x", pady=(4, 0))
            TkLabel(
                models_label_row,
                text=t("chat_model_label"),
                bg=_c("BG_CARD"),
                fg=_c("TEXT_MAIN"),
                font=("Segoe UI", 12),
                anchor="w",
            ).pack(side="left")
            _make_button(
                models_label_row,
                t("chat_btn_refresh_models"),
                lambda p=pid: _start_models_refresh(p, force=True),
                bg=_c("BG_INPUT"),
                font_size=9,
                height=1,
                padx=6,
                pady=1,
            ).pack(side="right")

            models_info = gpt_client.get_provider_models(pid)
            models = list(models_info["models"])
            if models_info["source"] == "live":
                try:
                    _age = time.strftime("%H:%M", time.localtime(models_info["ts"]))
                except Exception:
                    _age = "—"
                source_text = t("chat_models_live", _age)
            elif models_info["source"] == "builtin":
                source_text = t("chat_models_builtin")
            else:
                source_text = t("chat_models_source_none")
            if models_info.get("error"):
                source_text = f"⚠ {models_info['error']}"
            TkLabel(
                body,
                text=source_text,
                bg=_c("BG_CARD"),
                fg=_c("TEXT_DIM") if not models_info.get("error") else _c("TEXT_ERROR"),
                font=("Segoe UI", 10),
                anchor="w",
            ).pack(fill="x", pady=(0, 4))

            card_model_var = tk.StringVar(value=cur_model or (models[0] if models else ""))
            if models:
                for m in models:
                    tk.Radiobutton(
                        body,
                        text=m,
                        variable=card_model_var,
                        value=m,
                        bg=_c("BG_CARD"),
                        fg=_c("TEXT_MAIN"),
                        selectcolor=_c("BG_INPUT"),
                        activebackground=_c("BG_CARD"),
                        font=("Segoe UI", 12),
                        anchor="w",
                        cursor="hand2",
                    ).pack(fill="x", anchor="w")
            else:
                TkLabel(
                    body,
                    text=t("chat_models_empty"),
                    bg=_c("BG_CARD"),
                    fg=_c("TEXT_DIM"),
                    font=("Segoe UI", 12),
                ).pack(anchor="w")

            card_status = TkLabel(
                body,
                text=t("chat_health_caption", _health_caption(pid)),
                bg=_c("BG_CARD"),
                fg=_c("TEXT_DIM"),
                font=("Segoe UI", 11),
                anchor="w",
            )
            card_status.pack(fill="x", pady=(8, 4))

            def _save_card(p=pid, kv=card_key_var, mv=card_model_var, st=card_status):
                try:
                    gpt_client.set_api_key(kv.get().strip(), p)
                    if mv.get():
                        gpt_client.set_model(mv.get(), p)
                    st.config(text=t("chat_saved"), fg=_c("TEXT_SUCCESS"))
                    _rebuild_accordion()
                except Exception as e:
                    st.config(text=str(e), fg=_c("TEXT_ERROR"))

            test_request = {"token": None}

            def _test_card(p=pid, kv=card_key_var, st=card_status):
                st.config(text=t("chat_checking_key"), fg=_c("TEXT_DIM"))
                # Read Tk variables in the UI thread before starting work.
                key_value = kv.get().strip()
                request_token = object()
                test_request["token"] = request_token
                bridge = state._ui_bridge
                if bridge is not None:
                    bridge.begin()

                def deliver(callback):
                    if bridge is not None:
                        bridge.post(callback)
                    else:
                        _safe_after(0, callback)

                def worker():
                    try:
                        ok, msg = gpt_client.validate_key(key_value, p)

                        def apply_result():
                            if test_request["token"] is request_token and st.winfo_exists():
                                st.config(
                                    text=str(msg),
                                    fg=_c("TEXT_SUCCESS") if ok else _c("TEXT_ERROR"),
                                )

                        deliver(apply_result)
                    except Exception as error:

                        def apply_error(err=error):
                            if test_request["token"] is request_token and st.winfo_exists():
                                st.config(text=str(err), fg=_c("TEXT_ERROR"))

                        deliver(apply_error)
                    finally:
                        if bridge is not None:
                            bridge.producer_done()

                threading.Thread(target=worker, daemon=True).start()

            def _activate_card(p=pid):
                try:
                    gpt_client.set_provider(p)
                    _rebuild_accordion()
                except Exception as e:
                    print(e)

            btn_row = TkFrame(body, bg=_c("BG_CARD"))
            btn_row.pack(fill="x", pady=(2, 0))
            _make_button(
                btn_row,
                t("chat_btn_check"),
                _test_card,
                bg=_c("BG_INPUT"),
                font_size=10,
                height=1,
                padx=6,
                pady=2,
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))
            _make_button(
                btn_row,
                t("chat_btn_save"),
                _save_card,
                bg=_c("BG_INPUT"),
                font_size=10,
                height=1,
                padx=6,
                pady=2,
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))
            if not is_active:
                _make_button(
                    btn_row,
                    t("chat_btn_activate"),
                    _activate_card,
                    bg=_c("BG_ACTIVE"),
                    font_size=10,
                    height=1,
                    padx=6,
                    pady=2,
                ).pack(side="left", fill="x", expand=True, padx=(0, 4))

            # Secondary/destructive actions use their own row so the primary
            # Check/Save/Activate buttons always keep a usable width.
            secondary_row = TkFrame(body, bg=_c("BG_CARD"))
            secondary_row.pack(fill="x", pady=(5, 0))

            if is_custom:

                def _edit_this(p=pid):
                    _open_provider_form_internal(ctx, win, edit_pid=p)

                def _delete_this(p=pid, lbl=info.get("label", pid)):
                    if messagebox.askyesno(
                        t("chat_provider_delete_title"),
                        t("chat_provider_delete_msg", lbl),
                        parent=win,
                    ):
                        gpt_client.delete_custom_provider(p)
                        _rebuild_accordion()

                _make_button(
                    secondary_row,
                    "✎",
                    _edit_this,
                    bg=_c("BG_INPUT"),
                    font_size=10,
                    height=1,
                    width=3,
                    padx=4,
                    pady=2,
                ).pack(side="left", padx=(0, 4))
                _make_button(
                    secondary_row,
                    "🗑",
                    _delete_this,
                    bg=_c("BG_INPUT"),
                    font_size=10,
                    height=1,
                    width=3,
                    padx=4,
                    pady=2,
                ).pack(side="left")
            else:

                def _hide_this(p=pid, lbl=info.get("label", pid)):
                    if messagebox.askyesno(
                        t("chat_provider_hide_title"),
                        t("chat_provider_hide_msg", lbl),
                        parent=win,
                    ):
                        gpt_client.hide_provider(p)
                        _rebuild_accordion()

                _make_button(
                    secondary_row,
                    t("chat_btn_hide"),
                    _hide_this,
                    bg=_c("BG_INPUT"),
                    font_size=10,
                    height=1,
                    padx=6,
                    pady=2,
                ).pack(side="left", fill="x", expand=True)

    _rebuild_accordion()

    btn_row_f = TkFrame(container, bg=_c("BG_CARD"))
    btn_row_f.pack(fill="x", pady=(15, 0))

    def _check_all_providers():
        check_status.config(text=t("chat_checking_all"), fg=_c("TEXT_DIM"))
        bridge = state._ui_bridge
        if bridge is not None:
            bridge.begin()

        def worker():
            targets = []
            for pid, _info, _is_custom in _all_provider_entries():
                try:
                    has_key = bool(gpt_client.get_api_key(pid))
                except Exception:
                    has_key = False
                url = ""
                try:
                    url = (gpt_client.effective_models_url(pid) or "").lower()
                except Exception:
                    url = ""
                if has_key or ("localhost" in url) or ("127.0.0.1" in url):
                    targets.append(pid)
            ok_count = 0
            for pid in targets:
                try:
                    _, err = gpt_client.refresh_provider_models(pid, force=True)
                    if err is None:
                        ok_count += 1
                except Exception as error:
                    print(f"[AI] Проверка {pid} не удалась: {error}")
            if bridge is not None:
                bridge.producer_done()

            def done():
                try:
                    check_status.config(
                        text=t("chat_check_all_done", ok_count, len(targets)),
                        fg=_c("TEXT_SUCCESS"),
                    )
                    _rebuild_accordion()
                except Exception:
                    pass

            _deliver(done)

        threading.Thread(target=worker, daemon=True).start()

    check_row = TkFrame(btn_row_f, bg=_c("BG_CARD"))
    check_row.pack(fill="x")
    _make_button(
        check_row,
        t("chat_btn_add_provider"),
        lambda: _open_provider_form_internal(ctx, win),
        bg=_c("BG_INPUT"),
        font_size=11,
        height=1,
        padx=6,
        pady=3,
    ).pack(side="left", fill="x", expand=True, padx=(0, 4))
    _make_button(
        check_row,
        t("chat_btn_catalogue"),
        lambda: _open_catalogue_internal(ctx, win),
        bg=_c("BG_INPUT"),
        font_size=11,
        height=1,
        padx=6,
        pady=3,
    ).pack(side="left", fill="x", expand=True, padx=(0, 4))
    _make_button(
        check_row,
        t("chat_btn_check_all"),
        _check_all_providers,
        bg=_c("BG_INPUT"),
        font_size=11,
        height=1,
        padx=6,
        pady=3,
    ).pack(side="left", fill="x", expand=True)
    check_status = TkLabel(
        btn_row_f,
        text="",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 10),
        anchor="w",
    )
    check_status.pack(fill="x", pady=(4, 0))

    # Тихое фоновое автопродление живых списков моделей при открытии страницы
    # (TTL-gated, только для провайдеров с ключом или loopback).
    if not auto_refresh_state["started"]:
        auto_refresh_state["started"] = True
        _safe_after(150, _refresh_all_in_background)

    return container


def _start_background_refresh_for(ctx, pid):
    """Фоново подтянуть live-список моделей (после добавления провайдера)."""
    if not pid:
        return
    gpt_client = ctx.gpt_client
    bridge = state._ui_bridge

    def deliver(callback):
        if bridge is not None:
            bridge.post(callback)
        else:
            _safe_after(0, callback)

    if bridge is not None:
        bridge.begin()

    def worker():
        try:
            gpt_client.refresh_provider_models(pid, force=True)
        except Exception as error:
            print(f"[AI] Не удалось подтянуть модели {pid}: {error}")
        finally:
            if bridge is not None:
                bridge.producer_done()

        def done():
            _safe_show_page(ctx, "api")

        deliver(done)

    threading.Thread(target=worker, daemon=True).start()


def _safe_show_page(ctx, page_id):
    """Инвалидировать и перерисовать страницу AI-настроек (после сохранения)."""
    try:
        invalidate = getattr(ctx, "invalidate_page", None)
        show = getattr(ctx, "show_page", None)
        if callable(invalidate):
            invalidate(page_id)
        if callable(show):
            show(page_id)
    except Exception as e:
        print(f"[AI] Не удалось обновить страницу настроек: {e}")


def _open_provider_form_internal(ctx, parent, edit_pid=None):
    gpt_client = ctx.gpt_client
    is_edit = edit_pid is not None
    existing = {}
    if is_edit:
        for p in gpt_client.list_custom_providers():
            if p.get("id") == edit_pid:
                existing = p
                break

    form = tk.Toplevel(parent)
    _set_dark_titlebar(form)
    form.title(t("chat_provider_edit") if is_edit else t("chat_provider_add"))
    form.geometry("480x640")
    form.configure(bg=_c("BG_CARD"))
    form.transient(parent)
    form.grab_set()

    def _f(p, l, i="", h=1):
        TkLabel(
            p, text=l, bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), font=("Segoe UI", 12), anchor="w"
        ).pack(fill="x", padx=16, pady=(10, 3))
        if h == 1:
            v = tk.StringVar(value=i)
            e = tk.Entry(
                p,
                textvariable=v,
                bg=_c("BG_INPUT"),
                fg=_c("TEXT_MAIN"),
                insertbackground=_c("TEXT_MAIN"),
                relief="flat",
                highlightthickness=1,
                highlightbackground=_c("BORDER"),
                highlightcolor=_c("ACCENT"),
                font=("Segoe UI", 12),
            )
            e.pack(fill="x", padx=16, ipady=5)
            _bind_text_hotkeys(e)
            return v, e
        else:
            fr = TkFrame(p, bg=_c("BORDER"), padx=1, pady=1)
            fr.pack(fill="x", padx=16)
            in_ = TkFrame(fr, bg=_c("BG_INPUT"))
            in_.pack(fill="x")
            t_ = tk.Text(
                in_,
                height=h,
                wrap="word",
                bg=_c("BG_INPUT"),
                fg=_c("TEXT_MAIN"),
                insertbackground=_c("TEXT_MAIN"),
                relief="flat",
                highlightthickness=0,
                font=("Segoe UI", 12),
                padx=6,
                pady=6,
            )
            t_.insert("1.0", i)
            t_.pack(fill="x")
            _bind_text_hotkeys(t_)
            return t_, t_

    l_v, _ = _f(form, t("chat_field_label"), existing.get("label", ""))
    u_v, _ = _f(form, t("chat_field_url"), existing.get("url", ""))
    mu_v, _ = _f(form, t("chat_field_models_url"), existing.get("models_url", "") or "")

    load_row = TkFrame(form, bg=_c("BG_CARD"))
    load_row.pack(fill="x", padx=16, pady=(4, 0))
    _make_button(
        load_row,
        t("chat_btn_load_models"),
        lambda: _load_models(),
        bg=_c("BG_INPUT"),
        font_size=10,
        height=1,
        padx=6,
        pady=2,
    ).pack(side="left")

    m_i = "\n".join(existing.get("models", []))
    m_t, _ = _f(form, t("chat_field_models"), m_i, h=4)
    f_v, _ = _f(form, t("chat_field_fallback"), existing.get("fallback_model", ""))
    h_i = "\n".join(f"{k}: {v}" for k, v in (existing.get("extra_headers") or {}).items())
    h_t, _ = _f(form, t("chat_field_headers"), h_i, h=3)

    st = TkLabel(
        form, text="", bg=_c("BG_CARD"), fg=_c("TEXT_DIM"), font=("Segoe UI", 11), anchor="w"
    )
    st.pack(fill="x", padx=16, pady=(8, 0))

    def _load_models():
        mu = mu_v.get().strip() or gpt_client.derive_models_url(u_v.get().strip()) or ""
        if not mu:
            st.config(text=t("chat_url_empty"), fg=_c("TEXT_ERROR"))
            return
        api_key = ""
        if edit_pid:
            try:
                api_key = gpt_client.get_api_key(edit_pid) or ""
            except Exception:
                api_key = ""
        st.config(text=t("chat_loading_models"), fg=_c("TEXT_DIM"))
        bridge = state._ui_bridge
        if bridge is not None:
            bridge.begin()

        def worker():
            try:
                ok, msg, models = gpt_client.validate_provider_models_url(mu, api_key)
            except Exception as error:
                ok, msg, models = False, str(error), []
            if bridge is not None:
                bridge.producer_done()

            def done():
                if not form.winfo_exists():
                    return
                if ok:
                    m_t.delete("1.0", "end")
                    m_t.insert("1.0", "\n".join(models))
                    st.config(text=t("chat_models_url_ok", len(models)), fg=_c("TEXT_SUCCESS"))
                else:
                    st.config(text=t("chat_models_url_err", msg), fg=_c("TEXT_ERROR"))

            if bridge is not None:
                bridge.post(done)
            else:
                _safe_after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def save():
        lbl = (l_v.get() if isinstance(l_v, tk.StringVar) else l_v).strip()
        url = (u_v.get() if isinstance(u_v, tk.StringVar) else u_v).strip()
        raw_m = m_t.get("1.0", "end-1c") if isinstance(m_t, tk.Text) else ""
        mods = [m.strip() for m in raw_m.splitlines() if m.strip()]
        fb = (f_v.get() if isinstance(f_v, tk.StringVar) else f_v).strip()
        raw_h = h_t.get("1.0", "end-1c") if isinstance(h_t, tk.Text) else ""
        ext_h = {
            k.strip(): v.strip()
            for line in raw_h.splitlines()
            if ":" in line
            for k, _, v in [line.partition(":")]
        }

        if not url:
            st.config(text=t("chat_url_empty"), fg=_c("TEXT_ERROR"))
            return
        if not mods:
            st.config(text=t("chat_need_model"), fg=_c("TEXT_ERROR"))
            return

        models_url = mu_v.get().strip()
        try:
            if is_edit:
                gpt_client.update_custom_provider(
                    edit_pid,
                    label=lbl,
                    url=url,
                    models=mods,
                    fallback_model=fb,
                    extra_headers=ext_h,
                    models_url=models_url,
                )
            else:
                pid = lbl.lower().replace(" ", "_")
                import re

                pid = re.sub(r"[^a-z0-9_]", "", pid) or "custom"
                entry = gpt_client.add_custom_provider(
                    pid, lbl, url, mods, fb or mods[0], ext_h, models_url=models_url
                )
                _start_background_refresh_for(ctx, entry.get("id"))
            form.destroy()
            _safe_show_page(ctx, "api")
        except Exception as e:
            st.config(text=str(e), fg=_c("TEXT_ERROR"))

    br = TkFrame(form, bg=_c("BG_CARD"))
    br.pack(fill="x", padx=16, pady=(6, 16))
    _make_button(
        br,
        t("chat_btn_cancel_x"),
        lambda: form.destroy(),
        bg=_c("BG_INPUT"),
        font_size=11,
        height=1,
        padx=6,
        pady=3,
    ).pack(side="right", padx=(4, 0))
    _make_button(
        br, t("chat_btn_save"), save, bg=_c("BG_ACTIVE"), font_size=11, height=1, padx=6, pady=3
    ).pack(side="right")


def _open_catalogue_internal(ctx, parent):
    gpt_client = ctx.gpt_client
    cat = list(gpt_client.PROVIDER_CATALOGUE)
    dlg = tk.Toplevel(parent)
    _set_dark_titlebar(dlg)
    dlg.title(t("chat_catalogue_win"))
    dlg.geometry("580x560")
    dlg.configure(bg=_c("BG_CARD"))
    dlg.transient(parent)
    dlg.grab_set()
    TkLabel(
        dlg,
        text=t("chat_catalogue_header"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 13, "bold"),
    ).pack(anchor="w", padx=16, pady=(14, 6))

    search_var = tk.StringVar()
    search_entry = tk.Entry(
        dlg,
        textvariable=search_var,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        insertbackground=_c("TEXT_MAIN"),
        relief="flat",
        highlightthickness=1,
        highlightbackground=_c("BORDER"),
        highlightcolor=_c("ACCENT"),
        font=("Segoe UI", 12),
    )
    search_entry.pack(fill="x", padx=16, ipady=5)
    search_entry.insert(0, t("chat_catalogue_search"))
    search_entry.config(fg=_c("TEXT_DIM"))

    def _search_focus_in(_e):
        if search_entry.get() == t("chat_catalogue_search"):
            search_entry.delete(0, tk.END)
            search_entry.config(fg=_c("TEXT_MAIN"))
            return "break"
        return None

    def _search_focus_out(_e):
        if not search_entry.get().strip():
            search_entry.insert(0, t("chat_catalogue_search"))
            search_entry.config(fg=_c("TEXT_DIM"))

    search_entry.bind("<FocusIn>", _search_focus_in)
    search_entry.bind("<FocusOut>", _search_focus_out)
    _bind_text_hotkeys(search_entry)

    lo = TkFrame(dlg, bg=_c("BORDER"), padx=1, pady=1)
    lo.pack(fill="both", expand=True, padx=16, pady=(8, 0))
    sc = tk.Scrollbar(lo)
    sc.pack(side="right", fill="y")
    lb = tk.Listbox(
        lo,
        bg=_c("BG_INPUT"),
        fg=_c("TEXT_MAIN"),
        selectbackground=_c("ACCENT"),
        selectforeground="#ffffff",
        activestyle="none",
        relief="flat",
        highlightthickness=0,
        font=("Segoe UI", 12),
        yscrollcommand=sc.set,
    )
    lb.pack(fill="both", expand=True)
    sc.config(command=lb.yview)

    detail = TkLabel(
        dlg, text="", bg=_c("BG_CARD"), fg=_c("TEXT_DIM"), font=("Segoe UI", 10), anchor="w"
    )
    detail.pack(fill="x", padx=16, pady=(6, 0))

    def _already_ids():
        hidden = gpt_client.get_hidden_providers()
        ids = {pid for pid in gpt_client.PROVIDERS if pid != "local" and pid not in hidden}
        ids.update(p.get("id") for p in gpt_client.list_custom_providers())
        return ids

    visible: list[int] = []

    def refresh_list(*_):
        query = search_var.get().strip().lower()
        if query == t("chat_catalogue_search").lower():
            query = ""
        already = _already_ids()
        visible.clear()
        lb.delete(0, tk.END)
        for i, e in enumerate(cat):
            hay = f"{e['label']} {e['id']} {e.get('notes', '')}".lower()
            if query and query not in hay:
                continue
            suffix = ""
            if e["id"] in already:
                suffix = (
                    f"  ✓ {t('chat_builtin_badge')}" if e["id"] in gpt_client.PROVIDERS else "  ✓"
                )
            cached = gpt_client.get_cached_models(e["id"])
            cached_txt = f" · {t('chat_catalogue_cached', len(cached))}" if cached else ""
            lb.insert(tk.END, f"{e['label']}{suffix}{cached_txt}")
            visible.append(i)
        detail.config(text=f"{len(visible)} / {len(cat)}")
        return None

    search_var.trace_add("write", refresh_list)

    def _on_select(_event=None):
        sel = lb.curselection()
        if not sel or sel[0] >= len(visible):
            detail.config(text="")
            return None
        e = cat[visible[sel[0]]]
        note = e.get("notes", "")
        hint = e.get("key_hint") or "—"
        detail.config(text=f"{note}  |  {t('chat_key_hint', e['id'], hint)}")
        return None

    lb.bind("<<ListboxSelect>>", _on_select)

    status = TkLabel(
        dlg, text="", bg=_c("BG_CARD"), fg=_c("TEXT_DIM"), font=("Segoe UI", 11), anchor="w"
    )
    status.pack(fill="x", padx=16, pady=(4, 0))

    def add():
        sel = lb.curselection()
        if not sel or sel[0] >= len(visible):
            status.config(text=t("chat_select_provider"), fg=_c("TEXT_DIM"))
            return
        e = cat[visible[sel[0]]]
        if e["id"] in _already_ids():
            status.config(text=t("chat_provider_exists", e["label"]), fg=_c("TEXT_ERROR"))
            return
        try:
            entry = gpt_client.add_custom_provider(
                e["id"],
                e["label"],
                e["url"],
                list(e["models"]),
                e["models"][0] if e["models"] else "",
                dict(e.get("extra_headers") or {}),
                models_url=str(e.get("models_url") or ""),
            )
        except Exception as exc:
            status.config(text=str(exc), fg=_c("TEXT_ERROR"))
            return
        status.config(text=t("chat_loading_models"), fg=_c("TEXT_DIM"))
        # Живая загрузка /v1/models в фоне; страница настроек перерисуется сама
        _start_background_refresh_for(ctx, entry["id"])
        dlg.after(150, dlg.destroy)

    br = TkFrame(dlg, bg=_c("BG_CARD"))
    br.pack(fill="x", padx=16, pady=(8, 16))
    _make_button(
        br,
        t("chat_btn_close_x"),
        lambda: dlg.destroy(),
        bg=_c("BG_INPUT"),
        font_size=11,
        height=1,
        padx=6,
        pady=3,
    ).pack(side="right", padx=(4, 0))
    _make_button(
        br, t("chat_btn_add"), add, bg=_c("BG_ACTIVE"), font_size=11, height=1, padx=6, pady=3
    ).pack(side="right")
    lb.bind("<Double-Button-1>", lambda _e: add())
    refresh_list()
