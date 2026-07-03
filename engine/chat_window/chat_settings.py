from __future__ import annotations
import json
import os
import threading
import uuid
from datetime import datetime
from tkinter import filedialog, messagebox
import tkinter as tk

import engine.gui.chat_window.state as state
from engine.gui.chat_window.custom_widgets import CTK_AVAILABLE, CTkFrame, CTkLabel, CTkButton, TkFrame, TkLabel, TkButton, TkRawFrame

def open_gpt_settings(event=None):


    try:
        from engine import gpt_client
    except Exception as e:
        messagebox.showerror("Настройки AI", f"Не удалось загрузить engine.gpt_client: {e}", parent=_get_app_parent() or state._root)
        return "break"

    if _widget_exists(state._settings_window):
        _show_window(state._settings_window)
        return "break"

    import webbrowser
    _prov_list_ref = [None]

    win = tk.Toplevel(_get_app_parent() or state._root)
    _set_dark_titlebar(win)
    state._settings_window = win
    win.title("⚙ Настройки AI")
    win.geometry("600x680")
    win.minsize(520, 420)
    win.resizable(True, True)
    win.configure(bg=_c("BG_CARD"))
    win.transient(_get_app_parent() or state._root)
    

# ── Скроллируемый каркас ────────────────────────────────────────────────
    settings_canvas = tk.Canvas(
        win, bg=_c("BG_CARD"), highlightthickness=0, bd=0,
    )
    settings_scrollbar = tk.Scrollbar(win, orient="vertical", command=settings_canvas.yview)

    _scroll_save_id = [None]

    def _save_scroll_pos():
        try:
            gpt_client.set_ui_state(scroll_y=settings_canvas.yview()[0])
        except Exception:
            pass

    def _debounced_save_scroll():
        if _scroll_save_id[0] is not None:
            try:
                win.after_cancel(_scroll_save_id[0])
            except Exception:
                pass
        _scroll_save_id[0] = win.after(400, _save_scroll_pos)

    def _on_settings_yscroll(*args):
        settings_scrollbar.set(*args)
        _debounced_save_scroll()

    settings_canvas.configure(yscrollcommand=_on_settings_yscroll)

    settings_scrollbar.pack(side="right", fill="y")
    settings_canvas.pack(side="left", fill="both", expand=True)

    settings_scroll_frame = TkFrame(settings_canvas, bg=_c("BG_CARD"))

    # Принудительно обновляем геометрию ДО создания canvas-window, чтобы
    # winfo_width() вернул реальную ширину, а не 1px по умолчанию —
    # иначе при первом открытии содержимое "залипает" в узкой колонке слева
    # или съезжает, т.к. canvas_window получает неверную стартовую ширину.
    win.update_idletasks()
    initial_width = settings_canvas.winfo_width() or 580

    settings_canvas_window = settings_canvas.create_window(
        (0, 0), window=settings_scroll_frame, anchor="nw", width=initial_width,
    )

    def _on_settings_frame_configure(event=None):
        try:
            settings_canvas.configure(scrollregion=settings_canvas.bbox("all"))
        except Exception:
            pass

    def _on_settings_canvas_configure(event):
        try:
            settings_canvas.itemconfig(settings_canvas_window, width=event.width)
        except Exception:
            pass

    settings_scroll_frame.bind("<Configure>", _on_settings_frame_configure)
    settings_canvas.bind("<Configure>", _on_settings_canvas_configure)

    def _settings_mousewheel(event):
        try:
            if getattr(event, "num", None) == 4:
                units = -3
            elif getattr(event, "num", None) == 5:
                units = 3
            else:
                delta = int(getattr(event, "delta", 0) or 0)
                if delta == 0:
                    return None
                units = -3 if delta > 0 else 3
            settings_canvas.yview_scroll(units, "units")
            return "break"
        except Exception:
            return None

    for _target in (win, settings_canvas, settings_scroll_frame):
        try:
            _target.bind("<MouseWheel>", _settings_mousewheel, add="+")
            _target.bind("<Button-4>", _settings_mousewheel, add="+")
            _target.bind("<Button-5>", _settings_mousewheel, add="+")
        except Exception:
            pass

    # Финальная синхронизация ширины после того, как весь контент окна
    # будет создан и упакован (вызывается в самом конце функции, см. ниже).
    def _finalize_settings_layout():
        try:
            win.update_idletasks()
            settings_canvas.itemconfig(settings_canvas_window, width=settings_canvas.winfo_width())
            settings_canvas.configure(scrollregion=settings_canvas.bbox("all"))
        except Exception:
            pass
    

    get_provider = getattr(gpt_client, "get_provider", None)
    set_provider = getattr(gpt_client, "set_provider", None)
    get_provider_info = getattr(gpt_client, "get_provider_info", None)
    providers_map = getattr(gpt_client, "PROVIDERS", None)

    get_api_key = getattr(gpt_client, "get_api_key", None)
    set_api_key = getattr(gpt_client, "set_api_key", None)
    validate_key = getattr(gpt_client, "validate_key", None)
    get_model = getattr(gpt_client, "get_model", None)
    set_model = getattr(gpt_client, "set_model", None)

    multi_provider = callable(get_provider) and callable(get_provider_info) and isinstance(providers_map, dict)

    try:
        current_provider = get_provider() if multi_provider else "groq"
    except Exception:
        current_provider = "groq"

    def _models_for(provider: str) -> list:
        if multi_provider:
            try:
                return list(get_provider_info(provider).get("models", []) or [])
            except Exception:
                return []
        return list(getattr(gpt_client, "AVAILABLE_MODELS", []) or [])

    def _default_model_for(provider: str) -> str:
        if multi_provider:
            try:
                return get_provider_info(provider).get("default_model", "")
            except Exception:
                return ""
        return getattr(gpt_client, "DEFAULT_MODEL", "")

    try:
        current_key = (get_api_key(current_provider) if multi_provider else get_api_key()) if callable(get_api_key) else ""
    except Exception:
        current_key = ""

    try:
        current_model = (get_model(current_provider) if multi_provider else get_model()) if callable(get_model) else _default_model_for(current_provider)
    except Exception:
        current_model = _default_model_for(current_provider)

    # ── Провайдер ────────────────────────────────────────────────────────────
    provider_var = tk.StringVar(value=current_provider)

    list_custom_providers = getattr(gpt_client, "list_custom_providers", None)
    add_custom_provider = getattr(gpt_client, "add_custom_provider", None)
    update_custom_provider = getattr(gpt_client, "update_custom_provider", None)
    delete_custom_provider = getattr(gpt_client, "delete_custom_provider", None)
    has_custom_providers = callable(list_custom_providers) and callable(add_custom_provider)

    def _open_provider_form(edit_pid: str = None):
        """Форма добавления/редактирования кастомного провайдера."""
        is_edit = edit_pid is not None
        existing = {}
        if is_edit and callable(list_custom_providers):
            for p in list_custom_providers():
                if p.get("id") == edit_pid:
                    existing = p
                    break

        form = tk.Toplevel(win)
        _set_dark_titlebar(form)
        form.title("Редактировать провайдер" if is_edit else "Добавить провайдер")
        form.geometry("480x540")
        form.minsize(400, 460)
        form.resizable(True, True)
        form.configure(bg=_c("BG_CARD"))
        form.transient(win)
        form.grab_set()

        def _field(parent, label_text, initial="", height=1):
            TkLabel(
                parent, text=label_text,
                bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
                font=("Segoe UI", 9), anchor="w",
            ).pack(fill="x", padx=16, pady=(10, 3))
            if height == 1:
                var = tk.StringVar(value=initial)
                e = tk.Entry(
                    parent, textvariable=var,
                    bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"),
                    insertbackground=_c("TEXT_MAIN"),
                    relief="flat", highlightthickness=1,
                    highlightbackground=_c("BORDER"),
                    highlightcolor=_c("ACCENT"),
                    font=("Segoe UI", 9),
                )
                e.pack(fill="x", padx=16, ipady=5)
                _bind_text_hotkeys(e)
                return var, e
            else:
                frame = TkFrame(parent, bg=_c("BORDER"), padx=1, pady=1)
                frame.pack(fill="x", padx=16)
                inner = TkFrame(frame, bg=_c("BG_INPUT"))
                inner.pack(fill="x")
                t = tk.Text(
                    inner, height=height, wrap="word",
                    bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"),
                    insertbackground=_c("TEXT_MAIN"),
                    relief="flat", highlightthickness=0,
                    font=("Segoe UI", 9), padx=6, pady=6,
                )
                t.insert("1.0", initial)
                t.pack(fill="x")
                _bind_text_hotkeys(t)
                return t, t

        label_var, _ = _field(form, "Название", existing.get("label", ""))
        url_var, _ = _field(form, "URL эндпоинта (/v1/chat/completions)", existing.get("url", ""))

        models_initial = "\n".join(existing.get("models", []))
        models_text, _ = _field(form, "Модели (каждая с новой строки)", models_initial, height=4)

        fallback_var, _ = _field(form, "Fallback модель (при лимите)", existing.get("fallback_model", ""))

        headers_initial = "\n".join(
            f"{k}: {v}" for k, v in (existing.get("extra_headers") or {}).items()
        )
        headers_text, _ = _field(form, "Доп. заголовки (необязательно, формат «Key: Value», каждый с новой строки)", headers_initial, height=3)

        if is_edit:
            try:
                id_entry.config(state="disabled")
            except Exception:
                pass

        form_status = TkLabel(
            form, text="",
            bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
            font=("Segoe UI", 9), anchor="w",
        )
        form_status.pack(fill="x", padx=16, pady=(8, 0))

        btn_row_f = TkFrame(form, bg=_c("BG_CARD"))
        btn_row_f.pack(fill="x", padx=16, pady=(6, 16))

        def _save_form():
            if is_edit:
                pid_val = edit_pid
            else:
                lbl_raw = (label_var.get() if isinstance(label_var, tk.StringVar) else label_var).strip()
                pid_val = lbl_raw.lower().replace(" ", "_")
                # убираем всё кроме латиницы, цифр и _
                import re as _re
                pid_val = _re.sub(r"[^a-z0-9_]", "", pid_val) or "custom"
            lbl_val = (label_var.get() if isinstance(label_var, tk.StringVar) else label_var).strip()
            url_val = (url_var.get() if isinstance(url_var, tk.StringVar) else url_var).strip()

            raw_models = models_text.get("1.0", "end-1c") if isinstance(models_text, tk.Text) else ""
            models_list = [m.strip() for m in raw_models.splitlines() if m.strip()]

            fb_val = (fallback_var.get() if isinstance(fallback_var, tk.StringVar) else fallback_var).strip()
            if not fb_val and models_list:
                fb_val = models_list[0]

            raw_headers = headers_text.get("1.0", "end-1c") if isinstance(headers_text, tk.Text) else ""
            extra_h = {}
            for line in raw_headers.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    k, v = k.strip(), v.strip()
                    if k:
                        extra_h[k] = v

            if not url_val:
                form_status.config(text="URL не может быть пустым", fg=_c("TEXT_ERROR"))
                return
            if not models_list:
                form_status.config(text="Укажите хотя бы одну модель", fg=_c("TEXT_ERROR"))
                return

            try:
                if is_edit:
                    update_custom_provider(edit_pid, label=lbl_val, url=url_val,
                                           models=models_list, default_model=models_list[0],
                                           fallback_model=fb_val, extra_headers=extra_h)
                else:
                    add_custom_provider(pid_val, lbl_val, url_val, models_list, fb_val, extra_h)
                _rebuild_accordion()
                form.destroy()
            except Exception as e:
                form_status.config(text=str(e), fg=_c("TEXT_ERROR"))

        def _close_form(event=None):
            try:
                form.grab_release()
                form.destroy()
            except Exception:
                pass

        _make_button(
            btn_row_f, "✕ Отмена", _close_form,
            bg=_c("BG_INPUT"), font_size=9, height=1, padx=8, pady=3,
        ).pack(side="right", padx=(6, 0))
        _make_button(
            btn_row_f, "💾 Сохранить", _save_form,
            bg=_c("BG_ACTIVE"), font_size=9, height=1, padx=8, pady=3,
        ).pack(side="right")

        form.bind("<Escape>", _close_form)
        form.protocol("WM_DELETE_WINDOW", _close_form)

    def _open_catalogue():
        cat = getattr(gpt_client, "PROVIDER_CATALOGUE", [])
        fetch_models = getattr(gpt_client, "fetch_models_from_url", None)
        if not cat:
            messagebox.showinfo("Каталог", "Каталог провайдеров недоступен.", parent=win)
            return

        dlg = tk.Toplevel(win)
        _set_dark_titlebar(dlg)
        dlg.title("Каталог провайдеров")
        dlg.geometry("560x520")
        dlg.minsize(460, 400)
        dlg.resizable(True, True)
        dlg.configure(bg=_c("BG_CARD"))
        dlg.transient(win)
        dlg.grab_set()

        TkLabel(
            dlg, text="Выберите провайдера из каталога",
            bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 6))

        TkLabel(
            dlg, text="Двойной клик или «Добавить» — подключить провайдера",
            bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=16, pady=(0, 8))

        list_outer = TkFrame(dlg, bg=_c("BORDER"), padx=1, pady=1)
        list_outer.pack(fill="both", expand=True, padx=16)

        cat_scroll = tk.Scrollbar(list_outer)
        cat_scroll.pack(side="right", fill="y")

        cat_listbox = tk.Listbox(
            list_outer,
            bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"),
            selectbackground=_c("ACCENT"), selectforeground="#ffffff",
            activestyle="none", relief="flat", highlightthickness=0,
            font=("Segoe UI", 9),
            yscrollcommand=cat_scroll.set,
        )
        cat_listbox.pack(fill="both", expand=True)
        cat_scroll.config(command=cat_listbox.yview)

        already = set(pid for pid, _, _ in _all_provider_entries())
        for entry in cat:
            pid = entry.get("id", "")
            lbl = entry.get("label", pid)
            notes = entry.get("notes", "")
            suffix = "  ✓ уже добавлен" if pid in already else ""
            cat_listbox.insert(tk.END, f"{lbl}{suffix}  —  {notes}")

        info_lbl = TkLabel(
            dlg, text="Выберите провайдера из списка",
            bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
            font=("Segoe UI", 8), anchor="w", wraplength=500,
        )
        info_lbl.pack(fill="x", padx=16, pady=(8, 0))

        status_lbl_cat = TkLabel(
            dlg, text="",
            bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
            font=("Segoe UI", 8), anchor="w",
        )
        status_lbl_cat.pack(fill="x", padx=16, pady=(2, 0))

        def _on_cat_select(event=None):
            sel = cat_listbox.curselection()
            if not sel:
                return
            entry = cat[sel[0]]
            hint = entry.get("key_hint", "")
            notes = entry.get("notes", "")
            info_lbl.config(text=f"{notes}  |  Ключ: {hint}")

        cat_listbox.bind("<<ListboxSelect>>", _on_cat_select)

        def _add_from_catalogue(event=None):
            sel = cat_listbox.curselection()
            if not sel:
                messagebox.showinfo("Каталог", "Выберите провайдера.", parent=dlg)
                return

            entry = cat[sel[0]]
            pid = entry.get("id", "")

            existing_ids = set(pid for pid, _, _ in _all_provider_entries())
            if pid in existing_ids:
                messagebox.showinfo("Каталог", f"Провайдер «{entry.get('label')}» уже добавлен.", parent=dlg)
                return

            models_url = entry.get("models_url")
            api_key = key_var.get().strip()

            status_lbl_cat.config(text="Загружаю список моделей...", fg=_c("ACCENT"))
            dlg.update_idletasks()

            def _worker():
                models = []
                if callable(fetch_models) and models_url:
                    models = fetch_models(models_url, api_key)
                if not models:
                    models = entry.get("models", [])

                def _apply():
                    if not models:
                        status_lbl_cat.config(
                            text="Модели не загрузились — добавлю провайдера без списка моделей. Введите вручную.",
                            fg=_c("WARNING"),
                        )
                    else:
                        status_lbl_cat.config(
                            text=f"Загружено моделей: {len(models)}",
                            fg=_c("TEXT_SUCCESS"),
                        )

                    try:
                        add_custom_provider(
                            pid,
                            entry.get("label", pid),
                            entry.get("url", ""),
                            models,
                            models[0] if models else "",
                            entry.get("extra_headers", {}),
                            key_hint=entry.get("key_hint", ""),
                        )
                        _rebuild_accordion()
                        # Открываем форму редактирования чтобы пользователь
                        # мог выбрать primary/fallback модель и ввести ключ
                        dlg.destroy()
                        _open_provider_form(edit_pid=pid)
                    except Exception as e:
                        status_lbl_cat.config(text=str(e), fg=_c("TEXT_ERROR"))

                _safe_after(0, _apply)

            import threading as _threading
            _threading.Thread(target=_worker, daemon=True).start()

        btn_row_cat = TkFrame(dlg, bg=_c("BG_CARD"))
        btn_row_cat.pack(fill="x", padx=16, pady=(8, 16))

        _make_button(
            btn_row_cat, "✕ Закрыть",
            lambda: (dlg.grab_release(), dlg.destroy()),
            bg=_c("BG_INPUT"), font_size=9, height=1, padx=8, pady=3,
        ).pack(side="right", padx=(6, 0))

        _make_button(
            btn_row_cat, "＋ Добавить", _add_from_catalogue,
            bg=_c("BG_ACTIVE"), font_size=9, height=1, padx=8, pady=3,
        ).pack(side="right")

        cat_listbox.bind("<Double-Button-1>", _add_from_catalogue)
        dlg.bind("<Escape>", lambda e: (dlg.grab_release(), dlg.destroy()))
        dlg.protocol("WM_DELETE_WINDOW", lambda: (dlg.grab_release(), dlg.destroy()))

    # ── Провайдеры (аккордеон) ──────────────────────────────────────────────
    _ui_state = gpt_client.get_ui_state() if multi_provider else {}
    accordion_state = {"expanded": _ui_state.get("expanded_provider")}
    if multi_provider:
        prov_header_row = TkFrame(settings_scroll_frame, bg=_c("BG_CARD"))
        prov_header_row.pack(fill="x", padx=20, pady=(18, 6))
        TkLabel(
            prov_header_row, text="Провайдеры AI",
            bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), font=("Segoe UI", 10),
        ).pack(side="left")
        accordion_container = TkFrame(settings_scroll_frame, bg=_c("BG_CARD"))
        accordion_container.pack(fill="x", padx=20)
        def _all_provider_entries():
            entries = []
            hidden = gpt_client.get_hidden_providers()
            for pid, info in providers_map.items():
                if pid in hidden:
                    continue
                entries.append((pid, info, False))
            if callable(list_custom_providers):
                for p in list_custom_providers():
                    entries.append((p.get("id"), p, True))
            return entries
        def _toggle_card(pid):
            accordion_state["expanded"] = None if accordion_state["expanded"] == pid else pid
            try:
                gpt_client.set_ui_state(expanded_provider=accordion_state["expanded"])
            except Exception:
                pass
            _rebuild_accordion()
        def _rebuild_accordion():
            for child in accordion_container.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass
            active_pid = get_provider()
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
                tk.Label(header, text=arrow, bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
                         font=("Segoe UI", 9), width=2).pack(side="left")
                tk.Label(header, text=dot, bg=_c("BG_CARD"),
                         font=("Segoe UI", 10)).pack(side="left", padx=(0, 6))
                title_box = tk.Frame(header, bg=_c("BG_CARD"))
                title_box.pack(side="left", fill="x", expand=True)
                tk.Label(title_box, text=info.get("label", pid), bg=_c("BG_CARD"),
                         fg=_c("TEXT_MAIN"), font=("Segoe UI", 10),
                         anchor="w").pack(anchor="w")
                try:
                    cur_model = get_model(pid) if callable(get_model) else ""
                except Exception:
                    cur_model = ""
                has_key = bool(get_api_key(pid)) if callable(get_api_key) else False
                sub = f"{'✅ ключ задан' if has_key else '❌ нет ключа'} · {cur_model or '—'}"
                tk.Label(title_box, text=sub, bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
                         font=("Segoe UI", 8), anchor="w").pack(anchor="w")
                if is_active:
                    tk.Label(header, text="АКТИВНЫЙ", bg=_c("BG_CARD"),
                             fg=_c("TEXT_SUCCESS"), font=("Segoe UI", 8, "bold")
                             ).pack(side="right")
                for w in [header, title_box] + list(header.winfo_children()) + list(title_box.winfo_children()):
                    try:
                        w.bind("<Button-1>", lambda e, p=pid: _toggle_card(p))
                    except Exception:
                        pass
                if not is_expanded:
                    continue
                body = tk.Frame(card, bg=_c("BG_CARD"))
                body.pack(fill="x", padx=12, pady=(0, 12))
                tk.Frame(body, bg=_c("BORDER"), height=1).pack(fill="x", pady=(0, 10))
                TkLabel(body, text="API Key", bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
                        font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(0, 4))
                card_key_var = tk.StringVar(value=get_api_key(pid) if callable(get_api_key) else "")
                key_row = tk.Frame(body, bg=_c("BG_CARD"))
                key_row.pack(fill="x")
                ke = tk.Entry(
                    key_row, textvariable=card_key_var, show="•",
                    bg=_c("BG_INPUT"), fg=_c("TEXT_MAIN"), insertbackground=_c("TEXT_MAIN"),
                    relief="flat", highlightthickness=1, highlightbackground=_c("BORDER"),
                    highlightcolor=_c("ACCENT"), font=("Consolas", 9),
                )
                ke.pack(side="left", fill="x", expand=True, ipady=5)
                _bind_text_hotkeys(ke)
                show_v = tk.BooleanVar(value=False)
                tk.Checkbutton(
                    key_row, text="👁", variable=show_v,
                    command=lambda e=ke, v=show_v: e.config(show="" if v.get() else "•"),
                    bg=_c("BG_CARD"), fg=_c("TEXT_DIM"), selectcolor=_c("BG_INPUT"),
                    activebackground=_c("BG_CARD"), relief="flat", font=("Segoe UI", 8),
                ).pack(side="left", padx=(6, 0))
                hint = info.get("key_hint", "")
                if hint:
                    url = hint if hint.startswith("http") else f"https://{hint}"
                    link_lbl = tk.Label(
                        body, text=hint, bg=_c("BG_CARD"), fg=_c("ACCENT"),
                        font=("Segoe UI", 10), cursor="hand2", anchor="w",
                    )
                    link_lbl.pack(fill="x", pady=(3, 8))
                    link_lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                TkLabel(body, text="Модель", bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"),
                        font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(4, 4))
                models = list(info.get("models", []) or [])
                card_model_var = tk.StringVar(value=cur_model or (models[0] if models else ""))
                if models:
                    for m in models:
                        tk.Radiobutton(
                            body, text=m, variable=card_model_var, value=m,
                            bg=_c("BG_CARD"), fg=_c("TEXT_MAIN"), selectcolor=_c("BG_INPUT"),
                            activebackground=_c("BG_CARD"), font=("Segoe UI", 9),
                            anchor="w", cursor="hand2",
                        ).pack(fill="x", anchor="w")
                else:
                    TkLabel(body, text="Список моделей пуст.", bg=_c("BG_CARD"),
                            fg=_c("TEXT_DIM"), font=("Segoe UI", 9)).pack(anchor="w")
                card_status = TkLabel(body, text="", bg=_c("BG_CARD"), fg=_c("TEXT_DIM"),
                                      font=("Segoe UI", 8), anchor="w")
                card_status.pack(fill="x", pady=(8, 4))
                def _save_card(p=pid, kv=card_key_var, mv=card_model_var, st=card_status):
                    try:
                        if callable(set_api_key):
                            set_api_key(kv.get().strip(), p)
                        if callable(set_model) and mv.get():
                            set_model(mv.get(), p)
                        st.config(text="💾 Сохранено", fg=_c("TEXT_SUCCESS"))
                        _rebuild_accordion()
                    except Exception as e:
                        st.config(text=str(e), fg=_c("TEXT_ERROR"))
                def _test_card(p=pid, kv=card_key_var, st=card_status):
                    if not callable(validate_key):
                        st.config(text="Проверка недоступна", fg=_c("WARNING"))
                        return
                    st.config(text="Проверка ключа...", fg=_c("TEXT_DIM"))
                    def worker():
                        try:
                            ok, msg = validate_key(kv.get().strip(), p)
                            _safe_after(0, lambda: st.config(
                                text=str(msg),
                                fg=_c("TEXT_SUCCESS") if ok else _c("TEXT_ERROR"),
                            ))
                        except Exception as e:
                            _safe_after(0, lambda err=e: st.config(text=str(err), fg=_c("TEXT_ERROR")))
                    threading.Thread(target=worker, daemon=True).start()
                def _activate_card(p=pid, st=card_status):
                    try:
                        if callable(set_provider):
                            set_provider(p)
                        _rebuild_accordion()
                    except Exception as e:
                        st.config(text=str(e), fg=_c("TEXT_ERROR"))
                btn_row = TkFrame(body, bg=_c("BG_CARD"))
                btn_row.pack(fill="x", pady=(2, 0))
                _make_button(btn_row, "🔑 Проверить", _test_card, bg=_c("BG_INPUT"),
                            font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True, padx=(0, 4))
                _make_button(btn_row, "💾 Сохранить", _save_card, bg=_c("BG_INPUT"),
                            font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True, padx=(0, 4))
                if not is_active:
                    _make_button(btn_row, "✓ Активным", _activate_card, bg=_c("BG_ACTIVE"),
                                font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True, padx=(0, 4))
                if is_custom:
                    def _edit_this(p=pid):
                        _open_provider_form(edit_pid=p)
                    def _delete_this(p=pid, lbl=info.get("label", pid)):
                        if not messagebox.askyesno(
                            "Удалить провайдер",
                            f"Удалить «{lbl}» без возможности восстановления?",
                            parent=win,
                        ):
                            return
                        try:
                            delete_custom_provider(p)
                            if accordion_state["expanded"] == p:
                                accordion_state["expanded"] = None
                                gpt_client.set_ui_state(expanded_provider=None)
                            _rebuild_accordion()
                        except Exception as e:
                            messagebox.showerror("Ошибка", str(e), parent=win)
                    _make_button(btn_row, "✎", _edit_this, bg=_c("BG_INPUT"),
                                font_size=8, height=1, width=3, padx=4, pady=2).pack(side="left", padx=(0, 4))
                    _make_button(btn_row, "🗑", _delete_this, bg=_c("BG_INPUT"),
                                font_size=8, height=1, width=3, padx=4, pady=2).pack(side="left")
                else:
                    def _hide_this(p=pid, lbl=info.get("label", pid)):
                        if not messagebox.askyesno(
                            "Скрыть провайдер",
                            f"Скрыть «{lbl}»? Ключ и модель будут забыты.",
                            parent=win,
                        ):
                            return
                        try:
                            gpt_client.hide_provider(p)
                            if accordion_state["expanded"] == p:
                                accordion_state["expanded"] = None
                                gpt_client.set_ui_state(expanded_provider=None)
                            _rebuild_accordion()
                        except Exception as e:
                            messagebox.showerror("Ошибка", str(e), parent=win)
                    _make_button(btn_row, "🚫 Скрыть", _hide_this, bg=_c("BG_INPUT"),
                                font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True)
            _finalize_settings_layout()
        prov_btn_row = TkFrame(settings_scroll_frame, bg=_c("BG_CARD"))
        prov_btn_row.pack(fill="x", padx=20, pady=(6, 0))
        def _add_provider():
            if has_custom_providers:
                _open_provider_form()
        _make_button(prov_btn_row, "＋ Добавить", _add_provider, bg=_c("BG_ACTIVE"),
                    font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True, padx=(0, 4))
        _make_button(prov_btn_row, "🌐 Каталог", lambda: _open_catalogue(), bg=_c("BG_INPUT"),
                    font_size=8, height=1, padx=6, pady=2).pack(side="left", fill="x", expand=True)
        _rebuild_accordion()

    status_lbl = TkLabel(
        settings_scroll_frame,
        text="",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 9),
        anchor="w",
    )
    status_lbl.pack(fill="x", padx=20, pady=(8, 18))

    def close_settings(event=None):

        state._settings_window = None
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            win.after(0, win.destroy)
        except Exception:
            pass
        return "break"

    def _open_search_shortcut(event=None):
        return open_search(event)

    win.bind("<Escape>", close_settings)
    _bind_window_hotkeys(win, {
        "f": _open_search_shortcut,
    })

    win.protocol("WM_DELETE_WINDOW", close_settings)
    win.focus_set()

    # Контент создан полностью — синхронизируем геометрию канваса в самом конце,
    # это убирает гонку, когда <Configure> срабатывает раньше, чем все виджеты
    # внутри settings_scroll_frame созданы.
    _safe_after(0, _finalize_settings_layout)
    _safe_after(50, _finalize_settings_layout)

    _saved_scroll_y = gpt_client.get_ui_state().get("scroll_y", 0.0)
    _safe_after(120, lambda: settings_canvas.yview_moveto(_saved_scroll_y))

    return "break"



# Inter-module imports
from engine.gui.chat_window.chat_window_engine.utils import _now_ts, _now_full, _approx_tokens, _ai_display_name, _build_editor_compose_prompt
from engine.gui.chat_window.chat_window_engine.sessions import _load_sessions, _save_sessions, _enforce_limits, _create_session_dict, _get_current_session, _update_session_title_if_needed, _messages_for_api
from engine.gui.chat_window.chat_window_engine.generation import _run_generation
from engine.gui.chat_window.ui_utils import _c, _safe_after, _widget_exists, _set_dark_titlebar, _get_app_parent, _show_window, _call_and_break, _ask_simple_text, _make_button, _set_button_text, _set_button_state, _is_descendant, _get_widget_text, _select_all_widget, _paste_clipboard_into_widget, _copy_to_clipboard
from engine.gui.chat_window.hotkeys import _event_has_ctrl, _event_has_shift, _match_hotkey, _on_ctrl_keypress, _handle_text_ctrl, _handle_window_ctrl, _bind_window_hotkeys, _bind_text_hotkeys
from engine.gui.chat_window.placeholders import _create_placeholder_overlay, _sync_text_placeholder, _refresh_placeholder_state, _update_input_placeholder_text
from engine.gui.chat_window.chat_scroll import _is_chat_near_bottom, _scroll_chat_to_bottom, _show_new_message_indicator, _hide_new_message_indicator, _scroll_to_new_message, _chat_mousewheel
from engine.gui.chat_window.chat_history import _refresh_session_list, _on_session_select, new_chat, delete_current_chat, clear_chat_history
from engine.gui.chat_window.chat_messages import _add_message_bubble, _add_system_message, _resize_bubble_text, content_lines_estimate, _lighten_color, _selected_bubble_frame_get, _select_bubble, _on_bubble_text_click, _show_bubble_context_menu, _update_wraplengths, _render_current_session, _add_empty_state, _destroy_empty_state_if_any, _clear_messages_ui
from engine.gui.chat_window.chat_input import _focus_chat_input, _reset_editor_mode, _input_has_placeholder, _set_input_placeholder, _clear_input_placeholder, _get_input_text, _clear_input_text, _resize_input, _update_token_counter, _paste_into_input, _on_input_focus_in, _on_input_focus_out, _on_input_key_release, _on_enter, _submit_prompt, send_chat_message, _insert_prompt_into_chat_input
from engine.gui.chat_window.chat_typing import _show_typing, _animate_typing, _hide_typing
from engine.gui.chat_window.chat_actions import _send_to_main_editor, _stop_generation, _set_generation_ui, improve_text_with_gpt, paste_from_editor, set_chat_status, append_chat_message
from engine.gui.chat_window.chat_export import export_current_chat
from engine.gui.chat_window.chat_search import open_search
from engine.gui.chat_window.chat_editor import _show_editor_preview, _hide_editor_preview, open_editor_text_window, _get_selected_or_all_text, _show_editor_window
from engine.gui.chat_window import init, open_chat_window
