from __future__ import annotations

"""Страница локальных LLM и каталог моделей.

Отвечает за lifecycle установленных моделей, активацию/удаление, каталог
совместимости, resume/stop загрузки, очистку partial-файлов, импорт из папки
и подключение секции системного окружения.
"""

import os
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

from i18n import t
import engine.gui.chat_window.state as state
from engine.gui.progress_throttle import ProgressThrottle
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
from engine.gui.chat_window.services.settings_environment import build_environment_section


def build_local_page(ctx):
    win = ctx.win
    canvas_frame = ctx.canvas_frame
    gpt_client = ctx.gpt_client
    local_llm_client = ctx.local_llm_client
    _invalidate_page = ctx.invalidate_page
    show_page_with_style = ctx.show_page_with_style
    container = TkFrame(canvas_frame, bg=_c("BG_CARD"))
    container.pack(fill="both", expand=True, padx=20, pady=20)

    local_view = container
    catalog_view = container

    # ═══════════════════════════════════════════════════════════════════════
    #  Установленные модели
    # ═══════════════════════════════════════════════════════════════════════
    TkLabel(
        local_view,
        text=t("local_models_header"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 17, "bold"),
    ).pack(anchor="w", pady=(0, 10))

    TkLabel(
        local_view,
        text=t("local_models_desc"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 12),
        anchor="w",
        wraplength=500,
    ).pack(anchor="w", pady=(0, 20))

    # Installed models list
    list_frame = TkFrame(local_view, bg=_c("BG_CARD"))
    list_frame.pack(fill="x", pady=(0, 15))
    TkLabel(
        list_frame,
        text=t("local_model_active"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 12),
        anchor="w",
    ).pack(fill="x", pady=(0, 6))

    installed = local_llm_client.list_installed_models()
    active_id = local_llm_client.get_active_model_id()

    status_lbl = TkLabel(
        local_view,
        text="",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 12),
        anchor="w",
    )

    if not installed:
        TkLabel(
            list_frame,
            text=t("local_no_installed_models"),
            bg=_c("BG_CARD"),
            fg=_c("TEXT_DIM"),
            font=("Segoe UI", 12),
            anchor="w",
        ).pack(fill="x")
    else:
        for m in installed:
            row = TkFrame(list_frame, bg=_c("BG_CARD"))
            row.pack(fill="x", pady=2)
            is_active = m.get("id") == active_id
            dot = "🟢" if is_active else "⚪"
            # Reserve action width before the expandable model label.
            actions = TkFrame(row, bg=_c("BG_CARD"))
            actions.pack(side="right", padx=(6, 0))
            TkLabel(
                row,
                text=f"{dot} {m.get('label', m.get('filename', '?'))}",
                bg=_c("BG_CARD"),
                fg=_c("TEXT_MAIN"),
                font=("Segoe UI", 12),
                anchor="w",
            ).pack(side="left", fill="x", expand=True)

            def _activate(mid=m.get("id")):
                local_llm_client.set_active_model_id(mid)
                gpt_client.set_model(mid, "local")
                gpt_client.set_provider("local")
                _invalidate_page("local")
                show_page_with_style("local")

            def _remove(mid=m.get("id"), lbl=m.get("label", "")):
                if messagebox.askyesno(
                    t("local_model_delete_title"), t("local_model_delete_msg", lbl), parent=win
                ):
                    local_llm_client.remove_model(mid)
                    _invalidate_page("local")
                    show_page_with_style("local")

            if not is_active:
                _make_button(
                    actions,
                    t("local_model_activate_btn"),
                    _activate,
                    bg=_c("BG_ACTIVE"),
                    font_size=10,
                    height=1,
                    padx=6,
                    pady=2,
                ).pack(side="right", padx=(4, 0))
            _make_button(
                actions,
                "🗑",
                _remove,
                bg=_c("BG_INPUT"),
                font_size=10,
                height=1,
                width=3,
                padx=4,
                pady=2,
            ).pack(side="right")

    status_lbl.pack(fill="x", pady=(10, 0))

    # Системное окружение — карточка проверки/установки llama-cpp-python
    build_environment_section(ctx, local_view)

    tk.Frame(container, bg=_c("BORDER"), height=1).pack(fill="x", pady=(20, 20))

    # ═══════════════════════════════════════════════════════════════════════
    #  Каталог моделей
    # ═══════════════════════════════════════════════════════════════════════
    TkLabel(
        catalog_view,
        text=t("local_catalog_header"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", 17, "bold"),
    ).pack(anchor="w", pady=(0, 10))

    # Загружаем каталог с оценкой совместимости
    from engine import env_setup

    resolved = env_setup.resolve_backend()
    catalog_items = local_llm_client.get_compatible_models(vram_gb=resolved["gpu"].get("vram_gb"))

    list_outer = TkFrame(catalog_view, bg=_c("BORDER"), padx=1, pady=1)
    list_outer.pack(fill="both", expand=True, pady=(0, 15))
    sc = tk.Scrollbar(list_outer)
    sc.pack(side="right", fill="y")
    lb = tk.Listbox(
        list_outer,
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

    for m in catalog_items:
        prefix = "✅ " if m.get("installed") else ("✓ " if m.get("compatible") else "❌ ")
        lb.insert(tk.END, f"{prefix}{m['label']}")

    info_box = TkFrame(catalog_view, bg=_c("BG_CARD"), pady=10)
    info_box.pack(fill="x")
    desc_lbl = TkLabel(
        info_box,
        text="",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 12),
        anchor="w",
        wraplength=480,
    )
    desc_lbl.pack(anchor="w")
    mem_lbl = TkLabel(
        info_box,
        text="",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 11),
        anchor="w",
    )
    mem_lbl.pack(anchor="w")
    status_cat_lbl = TkLabel(
        info_box,
        text="",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 11, "bold"),
        anchor="w",
    )
    status_cat_lbl.pack(anchor="w")
    link_lbl = TkLabel(
        info_box,
        text="",
        bg=_c("BG_CARD"),
        fg=_c("ACCENT"),
        font=("Segoe UI", 12),
        cursor="hand2",
        anchor="w",
    )
    link_lbl.pack(anchor="w")
    action_status_lbl = TkLabel(
        info_box,
        text="",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", 11),
        anchor="w",
    )
    action_status_lbl.pack(anchor="w")

    selected_model = [None]
    download_thread = [None]
    download_cancelled = [False]
    download_in_progress = [False]
    # id модели, которую сейчас качаем (чтобы Стоп/UI не путались при смене selection)
    downloading_model_id = [None]

    def _has_incomplete_download(filename: str) -> bool:
        if not filename:
            return False
        try:
            chk = local_llm_client._load_download_checkpoint(filename)
            if chk and chk.get("offset", 0) > 0 and chk.get("url"):
                return True
        except Exception:
            pass
        # также считаем «незавершённым», если рядом лежит .part/.tmp/.download
        try:
            path = local_llm_client.get_model_file_path(filename)
            base = path if path else filename
            for suf in (".part", ".tmp", ".download", ".crdownload", ".partial"):
                if os.path.isfile(str(base) + suf) or os.path.isfile(
                    str(base).replace(".gguf", "") + suf
                ):
                    return True
            # файл существует, но меньше «ожидаемого» из checkpoint total
            if path and os.path.isfile(path):
                try:
                    chk = local_llm_client._load_download_checkpoint(filename) or {}
                    total = int(chk.get("total") or chk.get("size") or 0)
                    if total > 0 and os.path.getsize(path) < total:
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def _models_dir() -> str:
        """Папка /models/ проекта — туда кладутся gguf и partial-кэш."""
        try:
            # если client отдаёт путь к файлу каталога — берём dirname
            for m in catalog_items:
                fn = m.get("filename")
                if not fn:
                    continue
                p = local_llm_client.get_model_file_path(fn)
                if p:
                    d = os.path.dirname(str(p))
                    if d:
                        return d
        except Exception:
            pass
        try:
            d = local_llm_client.get_last_model_dir()
            if d and os.path.isdir(d):
                # если last_dir — файл, dirname
                return d if os.path.isdir(d) else os.path.dirname(d)
        except Exception:
            pass
        try:
            from engine.paths import BASE_DIR

            d = os.path.join(str(BASE_DIR), "models")
            os.makedirs(d, exist_ok=True)
            return d
        except Exception:
            return os.getcwd()

    def _set_download_ui(active: bool):
        """Показать/скрыть кнопку Стоп и залочить «Из папки» на время загрузки."""
        if active:
            try:
                stop_btn.pack(side="right", padx=(0, 4))
            except Exception:
                pass
            try:
                from_folder_btn.config(state="disabled")
            except Exception:
                pass
            try:
                discard_btn.pack_forget()
            except Exception:
                pass
        else:
            try:
                stop_btn.pack_forget()
            except Exception:
                pass
            try:
                from_folder_btn.config(state="normal")
            except Exception:
                pass
        # Reserve visible stop/discard buttons first, then let the main action
        # consume only the remaining width.
        try:
            action_btn.pack_forget()
            action_btn.pack(side="left", fill="x", expand=True)
        except Exception:
            pass

    def _update_catalog_info(e=None):
        sel = lb.curselection()
        if not sel:
            return
        m = catalog_items[sel[0]]
        selected_model[0] = m
        desc_lbl.config(text=t("local_model_meta_desc").format(m.get("description", "")))
        mem_lbl.config(text=t("local_catalog_memory").format(m.get("memory_gb", 0)))

        # во время загрузки — action_btn показывает статус/не стартует вторую загрузку
        if download_in_progress[0]:
            status_cat_lbl.config(text=t("local_catalog_downloading"), fg=_c("TEXT_DIM"))
            # если выбрана та же модель, что качается — action disabled; иначе можно смотреть инфо
            same = downloading_model_id[0] is not None and m.get("id") == downloading_model_id[0]
            action_btn.config(
                text=(t("local_catalog_downloading") if same else t("local_catalog_download_btn")),
                state="disabled" if same else "disabled",
                bg=_c("BG_INPUT"),
            )
            discard_btn.pack_forget()
            _set_download_ui(True)
        elif m.get("installed"):
            status_cat_lbl.config(text=t("local_catalog_installed"), fg=_c("TEXT_SUCCESS"))
            action_btn.config(
                text=t("local_catalog_activate_btn"), state="normal", bg=_c("BG_ACTIVE")
            )
            discard_btn.pack_forget()
            _set_download_ui(False)
        elif not m.get("compatible"):
            status_cat_lbl.config(text=t("local_catalog_too_large"), fg=_c("TEXT_ERROR"))
            action_btn.config(
                text=t("local_model_install_btn"), state="disabled", bg=_c("BG_INPUT")
            )
            discard_btn.pack_forget()
            _set_download_ui(False)
        elif _has_incomplete_download(m.get("filename", "")):
            status_cat_lbl.config(text=t("local_catalog_partial"), fg=_c("TEXT_DIM"))
            action_btn.config(
                text=t("local_catalog_resume_btn"), state="normal", bg=_c("BG_ACTIVE")
            )
            discard_btn.pack(side="right", padx=(0, 4))
            _set_download_ui(False)
        else:
            status_cat_lbl.config(text=t("local_catalog_compatible"), fg=_c("TEXT_SUCCESS"))
            action_btn.config(
                text=t("local_catalog_download_btn"), state="normal", bg=_c("BG_ACTIVE")
            )
            discard_btn.pack_forget()
            _set_download_ui(False)

        link_lbl.config(text=t("local_model_meta_link"))
        link_lbl.bind(
            "<Button-1>",
            lambda e, u=m.get("download_link", ""): webbrowser.open(u) if u else None,
        )
        if not download_in_progress[0]:
            # не затираем progress-строку во время загрузки
            pass

    lb.bind("<<ListboxSelect>>", _update_catalog_info)

    def _finish_download(entry, m):
        sel = lb.curselection()
        if sel:
            try:
                lb.delete(sel[0])
                lb.insert(sel[0], f"✅ {m['label']}")
            except Exception:
                pass
        action_status_lbl.config(
            text=t("local_model_added_msg", entry["label"]), fg=_c("TEXT_SUCCESS")
        )
        action_btn.config(text=t("local_catalog_activate_btn"), state="normal", bg=_c("BG_ACTIVE"))
        local_llm_client.set_active_model_id(entry["id"])
        gpt_client.set_model(entry["id"], "local")
        gpt_client.set_provider("local")
        download_in_progress[0] = False
        download_cancelled[0] = False
        downloading_model_id[0] = None
        _set_download_ui(False)
        _invalidate_page("local")
        _safe_after(900, lambda: show_page_with_style("local"))

    def _stop_download():
        """Явная кнопка «Остановить» во время загрузки."""
        if not download_in_progress[0]:
            return
        # без лишнего confirm, если уже жмут Стоп — но с лёгким подтверждением
        if not messagebox.askyesno(
            t("local_catalog_cancel_confirm_title"),
            t("local_catalog_cancel_confirm_msg"),
            parent=win,
        ):
            return
        download_cancelled[0] = True
        try:
            stop_btn.config(state="disabled", text=t("local_catalog_stopping_btn"))
        except Exception:
            pass
        try:
            action_btn.config(state="disabled")
        except Exception:
            pass
        action_status_lbl.config(text=t("local_catalog_stopping"), fg=_c("TEXT_DIM"))

    def _action_model():
        m = selected_model[0]
        if not m:
            return
        if download_in_progress[0]:
            # основная кнопка во время загрузки не стартует второе — Стоп отдельный
            return
        if m.get("installed"):
            path = local_llm_client.get_model_file_path(m["filename"])
            entry = next(
                (x for x in local_llm_client.list_installed_models() if x.get("path") == path),
                None,
            )
            if not entry:
                entry = local_llm_client.register_model(path, label=m.get("label"))
            local_llm_client.set_active_model_id(entry["id"])
            gpt_client.set_model(entry["id"], "local")
            gpt_client.set_provider("local")
            action_status_lbl.config(text=t("local_model_activated_status"), fg=_c("TEXT_SUCCESS"))
            _invalidate_page("local")
            _safe_after(900, lambda: show_page_with_style("local"))
            return

        if not m.get("compatible"):
            return

        resume = _has_incomplete_download(m.get("filename", ""))
        download_cancelled[0] = False
        download_in_progress[0] = True
        downloading_model_id[0] = m.get("id")
        action_btn.config(text=t("local_catalog_downloading"), state="disabled", bg=_c("BG_INPUT"))
        try:
            stop_btn.config(state="normal", text=t("local_catalog_stop_btn"))
        except Exception:
            pass
        _set_download_ui(True)
        action_status_lbl.config(
            text=t("local_catalog_downloading") if not resume else t("local_catalog_resuming"),
            fg=_c("TEXT_DIM"),
        )

        bridge = state._ui_bridge
        progress_throttle = ProgressThrottle(max_hz=8)
        progress_seq = [0]
        if bridge is not None:
            bridge.begin()

        def _deliver(callback):
            if bridge is not None:
                bridge.post(callback)
            else:
                _safe_after(0, callback)

        def _progress(line):
            progress_seq[0] += 1
            if progress_throttle.should_emit(progress_seq[0]):
                _deliver(lambda value=line: action_status_lbl.config(text=value, fg=_c("TEXT_DIM")))

        def worker():
            try:
                entry = local_llm_client.install_catalog_model(
                    m["id"],
                    progress_cb=_progress,
                    cancelled_flag=download_cancelled,
                    resume=resume,
                )
                _deliver(lambda: _finish_download(entry, m))
            except InterruptedError:

                def _on_pause():
                    download_in_progress[0] = False
                    downloading_model_id[0] = None
                    action_status_lbl.config(text=t("local_catalog_paused"), fg=_c("TEXT_DIM"))
                    action_btn.config(
                        text=t("local_catalog_resume_btn"), state="normal", bg=_c("BG_ACTIVE")
                    )
                    try:
                        stop_btn.config(state="normal", text=t("local_catalog_stop_btn"))
                    except Exception:
                        pass
                    _set_download_ui(False)
                    # показать discard для partial
                    try:
                        discard_btn.pack(side="right", padx=(0, 4))
                    except Exception:
                        pass

                _deliver(_on_pause)
            except Exception as e:
                err_msg = str(e)

                def _on_err(msg=err_msg):
                    download_in_progress[0] = False
                    downloading_model_id[0] = None
                    action_status_lbl.config(text=msg, fg=_c("TEXT_ERROR"))
                    has_part = _has_incomplete_download(m.get("filename", ""))
                    action_btn.config(
                        text=(
                            t("local_catalog_resume_btn")
                            if has_part
                            else t("local_catalog_download_btn")
                        ),
                        state="normal",
                        bg=_c("BG_ACTIVE"),
                    )
                    _set_download_ui(False)
                    if has_part:
                        try:
                            discard_btn.pack(side="right", padx=(0, 4))
                        except Exception:
                            pass

                _deliver(_on_err)

            finally:
                if bridge is not None:
                    bridge.producer_done()

        download_thread[0] = threading.Thread(target=worker, daemon=True)
        download_thread[0].start()

    def _is_partial_model_file(path: str) -> bool:
        name = os.path.basename(path).lower()
        if name.endswith((".part", ".tmp", ".download", ".crdownload", ".partial")):
            return True
        # checkpoint рядом
        base = os.path.basename(path)
        try:
            if _has_incomplete_download(base):
                return True
        except Exception:
            pass
        return False

    def _select_from_folder():
        """Диалог выбора модели: показывает и готовые .gguf, и partial/недокачанный мусор."""
        models_dir = _models_dir()
        last_dir = None
        try:
            last_dir = local_llm_client.get_last_model_dir()
        except Exception:
            pass
        initial = last_dir if (last_dir and os.path.isdir(last_dir)) else models_dir

        file_path = filedialog.askopenfilename(
            title=t("local_select_model_file_title"),
            filetypes=[
                (
                    "Models & partial",
                    "*.gguf *.bin *.pt *.safetensors *.part *.tmp *.download *.partial",
                ),
                ("GGUF models", "*.gguf"),
                ("Partial / incomplete", "*.part *.tmp *.download *.partial *.crdownload"),
                ("All files", "*.*"),
            ],
            initialdir=initial or None,
        )
        if not file_path:
            return
        try:
            local_llm_client.set_last_model_dir(file_path)
        except Exception:
            pass

        # Недокачанный/мусорный файл — предложить удалить, а не «установить»
        if _is_partial_model_file(file_path):
            size_mb = 0.0
            try:
                size_mb = os.path.getsize(file_path) / (1024 * 1024)
            except Exception:
                pass
            if messagebox.askyesno(
                t("local_partial_file_title"),
                t("local_partial_file_msg", os.path.basename(file_path), f"{size_mb:.1f}"),
                parent=win,
            ):
                try:
                    # сначала API discard по basename (checkpoint + part)
                    base = os.path.basename(file_path)
                    # срезаем суффиксы partial
                    for suf in (".part", ".tmp", ".download", ".crdownload", ".partial"):
                        if base.lower().endswith(suf):
                            base = base[: -len(suf)]
                            break
                    try:
                        local_llm_client.discard_incomplete_download(base)
                    except Exception:
                        pass
                    # сам файл
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                    # checkpoint json рядом, если есть
                    for side in (
                        file_path + ".checkpoint",
                        file_path + ".ckpt",
                        file_path + ".json",
                        os.path.join(os.path.dirname(file_path), base + ".download.json"),
                        os.path.join(os.path.dirname(file_path), "." + base + ".download"),
                    ):
                        try:
                            if os.path.isfile(side):
                                os.remove(side)
                        except Exception:
                            pass
                    messagebox.showinfo(
                        t("local_partial_deleted_title"),
                        t("local_partial_deleted_msg", os.path.basename(file_path)),
                        parent=win,
                    )
                    action_status_lbl.config(
                        text=t("local_catalog_discard_done"), fg=_c("TEXT_DIM")
                    )
                    _update_catalog_info()
                except Exception as e:
                    messagebox.showerror(t("chat_err_title"), str(e), parent=win)
            return

        # Обычный полный файл модели — как раньше: перенос в /models/
        if messagebox.askyesno(t("local_move_model_title"), t("local_move_model_msg"), parent=win):
            try:
                entry = local_llm_client.move_model_file(file_path)
                local_llm_client.set_active_model_id(entry["id"])
                gpt_client.set_model(entry["id"], "local")
                gpt_client.set_provider("local")
                messagebox.showinfo(
                    t("local_model_added_title"),
                    t("local_model_added_msg", entry["label"]),
                    parent=win,
                )
                _invalidate_page("local")
                show_page_with_style("local")
            except Exception as e:
                messagebox.showerror(t("chat_err_title"), str(e), parent=win)

    def _browse_models_folder_trash():
        """Окно: все файлы в /models/ включая partial — можно удалить мусор."""
        models_dir = _models_dir()
        dlg = tk.Toplevel(win)
        try:
            _set_dark_titlebar(dlg)
        except Exception:
            pass
        dlg.title(t("local_models_folder_title"))
        dlg.geometry("560x420")
        dlg.configure(bg=_c("BG_CARD"))
        dlg.transient(win)
        dlg.grab_set()

        TkLabel(
            dlg,
            text=t("local_models_folder_desc", models_dir),
            bg=_c("BG_CARD"),
            fg=_c("TEXT_DIM"),
            font=("Segoe UI", 11),
            anchor="w",
            wraplength=520,
            justify="left",
        ).pack(fill="x", padx=14, pady=(12, 6))

        list_outer = TkFrame(dlg, bg=_c("BORDER"), padx=1, pady=1)
        list_outer.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        sc2 = tk.Scrollbar(list_outer)
        sc2.pack(side="right", fill="y")
        lb2 = tk.Listbox(
            list_outer,
            bg=_c("BG_INPUT"),
            fg=_c("TEXT_MAIN"),
            selectbackground=_c("ACCENT"),
            selectforeground="#ffffff",
            activestyle="none",
            relief="flat",
            highlightthickness=0,
            font=("Consolas", 11),
            yscrollcommand=sc2.set,
        )
        lb2.pack(fill="both", expand=True)
        sc2.config(command=lb2.yview)

        # entries: list[(display, fullpath, kind)]
        entries = []

        def _refresh_folder_list():
            lb2.delete(0, tk.END)
            entries.clear()
            try:
                names = sorted(os.listdir(models_dir), key=lambda s: s.lower())
            except Exception as e:
                lb2.insert(tk.END, f"! {e}")
                return
            for name in names:
                full = os.path.join(models_dir, name)
                if not os.path.isfile(full):
                    continue
                low = name.lower()
                # показываем модели + partial + checkpoint-мусор
                interesting = (
                    low.endswith(
                        (
                            ".gguf",
                            ".bin",
                            ".pt",
                            ".safetensors",
                            ".part",
                            ".tmp",
                            ".download",
                            ".partial",
                            ".crdownload",
                            ".ckpt",
                            ".checkpoint",
                        )
                    )
                    or ".download" in low
                    or low.startswith(".")
                )
                if not interesting:
                    # json checkpoint рядом
                    if not (low.endswith(".json") and ("download" in low or "ckpt" in low)):
                        continue
                try:
                    sz = os.path.getsize(full)
                    size_s = f"{sz/1024/1024:.1f} MB" if sz >= 1024 * 1024 else f"{sz/1024:.1f} KB"
                except Exception:
                    size_s = "?"
                if _is_partial_model_file(full) or low.endswith(
                    (
                        ".part",
                        ".tmp",
                        ".download",
                        ".partial",
                        ".crdownload",
                        ".ckpt",
                        ".checkpoint",
                    )
                ):
                    kind = "partial"
                    mark = "⚠"
                else:
                    kind = "model"
                    mark = "✅"
                display = f"{mark}  {name}   ({size_s})"
                entries.append((display, full, kind, name))
                lb2.insert(tk.END, display)

        def _delete_selected():
            sel = lb2.curselection()
            if not sel:
                return
            idx = sel[0]
            if idx < 0 or idx >= len(entries):
                return
            _disp, full, kind, name = entries[idx]
            if not messagebox.askyesno(
                t("local_models_folder_delete_title"),
                t("local_models_folder_delete_msg", name),
                parent=dlg,
            ):
                return
            try:
                # discard checkpoint API if possible
                base = name
                for suf in (".part", ".tmp", ".download", ".crdownload", ".partial"):
                    if base.lower().endswith(suf):
                        base = base[: -len(suf)]
                        break
                try:
                    local_llm_client.discard_incomplete_download(base)
                except Exception:
                    pass
                if os.path.isfile(full):
                    os.remove(full)
                _refresh_folder_list()
                try:
                    _update_catalog_info()
                except Exception:
                    pass
            except Exception as e:
                messagebox.showerror(t("chat_err_title"), str(e), parent=dlg)

        def _open_dir():
            try:
                if hasattr(os, "startfile"):
                    os.startfile(models_dir)  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    import subprocess

                    subprocess.Popen(["open", models_dir])
                else:
                    import subprocess

                    subprocess.Popen(["xdg-open", models_dir])
            except Exception as e:
                messagebox.showerror(t("chat_err_title"), str(e), parent=dlg)

        btn_row = TkFrame(dlg, bg=_c("BG_CARD"))
        btn_row.pack(fill="x", padx=14, pady=(0, 12))
        _make_button(
            btn_row,
            t("local_models_folder_refresh"),
            _refresh_folder_list,
            bg=_c("BG_INPUT"),
            font_size=11,
            height=1,
            padx=6,
            pady=3,
        ).pack(side="left")
        _make_button(
            btn_row,
            t("local_models_folder_open"),
            _open_dir,
            bg=_c("BG_INPUT"),
            font_size=11,
            height=1,
            padx=6,
            pady=3,
        ).pack(side="left", padx=(6, 0))
        _make_button(
            btn_row,
            t("local_models_folder_delete"),
            _delete_selected,
            bg=_c("BG_INPUT"),
            font_size=11,
            height=1,
            padx=6,
            pady=3,
        ).pack(side="right")
        _make_button(
            btn_row,
            t("chat_btn_cancel_x"),
            lambda: dlg.destroy(),
            bg=_c("BG_INPUT"),
            font_size=11,
            height=1,
            padx=6,
            pady=3,
        ).pack(side="right", padx=(0, 6))

        _refresh_folder_list()

    def _discard_cached_download():
        m = selected_model[0]
        if not m:
            return
        filename = m.get("filename", "")
        if not filename:
            return
        # разрешаем discard даже если checkpoint «странный», но partial-файл есть
        if not _has_incomplete_download(filename):
            return
        if not messagebox.askyesno(
            t("local_catalog_discard_confirm_title"),
            t("local_catalog_discard_confirm_msg", m.get("label", filename)),
            parent=win,
        ):
            return
        try:
            local_llm_client.discard_incomplete_download(filename)
        except Exception as e:
            messagebox.showerror(t("chat_err_title"), str(e), parent=win)
            return
        # подчистить leftover .part рядом
        try:
            path = local_llm_client.get_model_file_path(filename)
            if path:
                for suf in (".part", ".tmp", ".download", ".partial", ".crdownload"):
                    p = str(path) + suf
                    if os.path.isfile(p):
                        os.remove(p)
        except Exception:
            pass
        _update_catalog_info()
        action_status_lbl.config(text=t("local_catalog_discard_done"), fg=_c("TEXT_DIM"))

    br = TkFrame(catalog_view, bg=_c("BG_CARD"))
    br.pack(fill="x", pady=(0, 15))
    primary_actions = TkFrame(br, bg=_c("BG_CARD"))
    primary_actions.pack(fill="x", pady=(0, 5))
    secondary_actions = TkFrame(br, bg=_c("BG_CARD"))
    secondary_actions.pack(fill="x")

    from_folder_btn = _make_button(
        secondary_actions,
        t("chat_btn_from_folder"),
        _select_from_folder,
        bg=_c("BG_INPUT"),
        font_size=11,
        height=1,
        padx=6,
        pady=3,
    )
    from_folder_btn.pack(side="left", fill="x", expand=True, padx=(3, 0))
    # Обзор /models/ — видны partial и мусор
    manage_btn = _make_button(
        secondary_actions,
        t("local_models_folder_btn"),
        _browse_models_folder_trash,
        bg=_c("BG_INPUT"),
        font_size=11,
        height=1,
        padx=6,
        pady=3,
    )
    manage_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
    action_btn = _make_button(
        primary_actions,
        t("local_model_install_btn"),
        _action_model,
        bg=_c("BG_ACTIVE"),
        font_size=11,
        height=1,
        padx=6,
        pady=3,
    )
    action_btn.pack(side="left", fill="x", expand=True)
    # Стоп — видна только во время загрузки
    stop_btn = _make_button(
        primary_actions,
        t("local_catalog_stop_btn"),
        _stop_download,
        bg="#c0392b",
        font_size=11,
        height=1,
        padx=6,
        pady=3,
    )
    # изначально скрыта
    discard_btn = _make_button(
        primary_actions,
        "🗑 " + t("local_catalog_discard_btn"),
        _discard_cached_download,
        bg=_c("BG_INPUT"),
        font_size=11,
        height=1,
        padx=6,
        pady=3,
    )
    # discard_btn / stop_btn изначально скрыты — pack через _update_catalog_info / _set_download_ui
    lb.bind("<Double-Button-1>", _action_model)

    return container
