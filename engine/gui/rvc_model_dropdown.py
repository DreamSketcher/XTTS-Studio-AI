# -*- coding: utf-8 -*-
"""
engine/gui/rvc_model_dropdown.py — выпадающий список выбора RVC-модели.

Заменяет обычный CTkOptionMenu целиком: в одном списке вперемешку
локальные скачанные модели (с кнопкой 🗑 удаления) и модели из каталога,
ещё не скачанные (▶ пример / ⬇ скачать / ✕ отменить / 🔗 открыть страницу).
Клик по строке — это одновременно и выбор модели, и подсветка строки;
кнопка действия у строки активна ТОЛЬКО когда строка выделена.

Источники remote-списка:
  - без поиска: seed/кэш через rvc_catalog.get_catalog()
    (json/rvc_catalog_seed.json — подборка с voice-models.com / HF)
  - с поиском (≥2 символа): rvc_catalog.search_catalog() =
    локальный seed + live voice-models.com

ФИКС (dropdown не открывался в модальном окне настроек):
  попап — tk.Frame + place() на toplevel окна настроек (grab-safe).

PATCH 2026-07-14: плавный скролл списка через AnimationManager.
"""
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox

from engine.gui.colors import Colors, scaled_font_size, scaled_size
from engine.gui.widgets import CompatCTkButton
from engine.gui.tooltip import ToolTip
from engine import rvc_catalog

# Тот же sentinel, что уже используется в presets.py (quality_params, reset()) —
# намеренно НЕ пропускается через t(), чтобы не разъехаться со значением,
# которое хранится в settings.json и сравнивается в других местах кода.
NONE_LABEL = "Не выбрана"

# Открытые инстансы dropdown'а — один общий bind_all("<Button-1>") /
# колесо мыши рассылает им события. Так не копим add="+" и не зовём
# unbind_all (unbind_all снёс бы чужие глобальные бинды приложения).
_OPEN_DROPDOWNS = []
_GLOBAL_BINDS_READY = False


def _global_button1_dispatch(event):
    for dd in list(_OPEN_DROPDOWNS):
        try:
            dd._on_outside_click(event)
        except Exception:
            pass


def _global_scroll_dispatch(event):
    """
    Глобальное колесо при открытом dropdown:
      - курсор НАД попапом → скроллим список (и глотаем событие)
      - курсор СНАРУЖИ → закрываем попап, событие пропускаем дальше
        (чтобы скролл окна настроек продолжал работать)
    """
    ate = False
    for dd in list(_OPEN_DROPDOWNS):
        try:
            if dd._pointer_inside_popup(event):
                dd._on_list_wheel(event)
                ate = True
            else:
                # Скролл снаружи = пользователь ушёл листать окно → закрываем список
                dd._close_popup()
        except Exception:
            pass
    if ate:
        return "break"


def _ensure_global_binds(widget):
    """Вешает bind_all один раз на всё приложение (через любой живой widget)."""
    global _GLOBAL_BINDS_READY
    if _GLOBAL_BINDS_READY:
        return
    try:
        widget.bind_all("<Button-1>", _global_button1_dispatch, add="+")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind_all(seq, _global_scroll_dispatch, add="+")
        _GLOBAL_BINDS_READY = True
    except Exception:
        pass


class RVCModelDropdown:
    def __init__(
        self,
        parent,
        variable,
        t,
        on_status=None,
        on_progress=None,
        on_show_cancel=None,
        on_hide_cancel=None,
    ):
        """
        parent   — родитель для кнопки-триггера (сам список place()'ится на toplevel)
        variable — tk.StringVar (params["rvc_model"])
        t        — функция i18n.t
        on_status/on_progress/on_show_cancel/on_hide_cancel — колбэки statusbar
        """
        self.parent = parent
        self.variable = variable
        self.t = t
        self.on_status = on_status or (lambda *a: None)
        self.on_progress = on_progress or (lambda *a: None)
        self.on_show_cancel = on_show_cancel or (lambda *a: None)
        self.on_hide_cancel = on_hide_cancel or (lambda: None)

        self._popup = None
        self._rows_container = None
        self._search_var = None
        self._search_entry = None
        self._search_status_lbl = None
        self._active_row_key = None
        self._active_row_widget = None
        self._render_token = 0
        self._downloading_key = None
        self._preview_loading_key = None
        self._preview_playing_key = None
        self._preview_token = 0
        self._cancel_flag = None
        self._enabled = True

        self._top_win = None
        self._escape_bind_id = None
        self._ignore_outside_until = 0.0

        # Поиск
        self._search_query = ""
        self._search_results = None  # None = режим seed/каталог; list = результаты поиска
        self._search_token = 0  # инвалидация устаревших async-ответов
        self._search_pending = False
        self._search_after_id = None  # debounce after() id
        self._search_debounce_ms = 450

        # Каталоги: локальная подборка + публичные New/Top voice-models.com.
        self._catalog_mode = "curated"
        self._catalog_results = None
        self._catalog_loading = False
        self._catalog_token = 0
        self._catalog_buttons = {}

        self.trigger_btn = CompatCTkButton(
            parent,
            text=self._trigger_text(),
            command=self._toggle_popup,
            width=scaled_size(210, min_size=180),
            height=scaled_size(30, min_size=28),
            corner_radius=8,
            fg_color=Colors.BG_INPUT,
            text_color=Colors.TEXT_MAIN,
            hover_color=Colors.BG_HOVER,
            font=("Segoe UI", scaled_font_size(10)),
            anchor="w",
        )
        ToolTip(self.trigger_btn, t("tip_rvc_model"))
        self.variable.trace_add("write", lambda *a: self._sync_trigger_text())

    # ------------------------------------------------------------
    #  Публичный интерфейс — вызывается из presets.py
    # ------------------------------------------------------------

    def pack(self, **kw):
        self.trigger_btn.pack(**kw)
        return self

    def set_enabled(self, enabled: bool):
        """Вызывается из update_rvc_state() в presets.py вместе с остальными RVC-виджетами."""
        self._enabled = enabled
        try:
            self.trigger_btn.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass
        if not enabled:
            self._close_popup()

    # ------------------------------------------------------------
    #  Кнопка-триггер
    # ------------------------------------------------------------

    def _trigger_text(self):
        name = self.variable.get() or NONE_LABEL
        return f"{name}  ▾"

    def _sync_trigger_text(self):
        try:
            self.trigger_btn.configure(text=self._trigger_text())
        except Exception:
            pass

    def _tr(self, key, *args, default=None):
        """i18n с фоллбэком, если ключ ещё не добавлен в i18n.py."""
        try:
            text = self.t(key, *args) if args else self.t(key)
            if text and text != key:
                return text
        except Exception:
            pass
        return default if default is not None else key

    # ------------------------------------------------------------
    #  Попап со списком
    # ------------------------------------------------------------

    def _toggle_popup(self):
        if not self._enabled:
            return
        if self._popup is not None:
            self._close_popup()
        else:
            self._open_popup()

    def _close_popup(self):
        if self._popup is None and self not in _OPEN_DROPDOWNS:
            return

        try:
            while self in _OPEN_DROPDOWNS:
                _OPEN_DROPDOWNS.remove(self)
        except ValueError:
            pass

        top = self._top_win
        if top is not None:
            try:
                if top.winfo_exists() and self._escape_bind_id is not None:
                    try:
                        top.unbind("<Escape>", self._escape_bind_id)
                    except Exception:
                        pass
            except Exception:
                pass

        self._escape_bind_id = None
        self._top_win = None

        popup = self._popup
        self._popup = None
        self._rows_container = None
        self._search_entry = None
        self._search_status_lbl = None
        # search_var оставляем — можно переиспользовать; query сбрасываем
        self._search_query = ""
        self._search_results = None
        self._search_pending = False
        self._search_token += 1
        self._catalog_loading = False
        self._catalog_token += 1
        self._catalog_buttons = {}

        if popup is not None:
            try:
                popup.place_forget()
            except Exception:
                pass
            try:
                popup.destroy()
            except Exception:
                pass

    def _open_popup(self):
        """Рисует список как Frame.place() на toplevel окна настроек (grab-safe)."""
        if self._popup is not None:
            self._close_popup()

        try:
            self.trigger_btn.update_idletasks()
            top_win = self.trigger_btn.winfo_toplevel()
            if not top_win or not top_win.winfo_exists():
                return

            top_win.update_idletasks()

            btn_rx = self.trigger_btn.winfo_rootx()
            btn_ry = self.trigger_btn.winfo_rooty()
            btn_h = self.trigger_btn.winfo_height()
            btn_w = self.trigger_btn.winfo_width()
            win_rx = top_win.winfo_rootx()
            win_ry = top_win.winfo_rooty()
            win_w = max(top_win.winfo_width(), 1)
            win_h = max(top_win.winfo_height(), 1)

            x = btn_rx - win_rx
            y = btn_ry - win_ry + btn_h
            width = max(btn_w, scaled_size(320, min_size=280))
        except Exception:
            return

        try:
            popup = tk.Frame(
                top_win,
                bg=Colors.BORDER,
                bd=0,
                highlightthickness=0,
            )
            self._popup = popup
            self._top_win = top_win

            outer = tk.Frame(popup, bg=Colors.BORDER, bd=0, highlightthickness=0)
            outer.pack(fill="both", expand=True, padx=1, pady=1)

            # ── Поиск ──
            search_wrap = tk.Frame(outer, bg=Colors.BG_INPUT)
            search_wrap.pack(fill="x", padx=0, pady=0)

            self._search_var = tk.StringVar(value="")
            self._search_entry = tk.Entry(
                search_wrap,
                textvariable=self._search_var,
                bg=Colors.BG_CARD,
                fg=Colors.TEXT_MAIN,
                insertbackground=Colors.TEXT_MAIN,
                relief="flat",
                font=("Segoe UI", scaled_font_size(9)),
                highlightthickness=1,
                highlightbackground=Colors.BORDER,
                highlightcolor=Colors.ACCENT,
            )
            self._search_entry.pack(fill="x", padx=6, pady=(6, 2))
            placeholder = self._tr(
                "rvc_search_placeholder",
                default="Поиск (voice-models.com)…",
            )
            self._search_entry.insert(0, "")
            # Статус + очистка orphan-preview/недокачанных моделей.
            status_row = tk.Frame(search_wrap, bg=Colors.BG_INPUT)
            status_row.pack(fill="x", padx=(8, 6), pady=(0, 4))
            self._search_status_lbl = tk.Label(
                status_row,
                text=placeholder,
                bg=Colors.BG_INPUT,
                fg=Colors.TEXT_DIM,
                anchor="w",
                font=("Segoe UI", scaled_font_size(8)),
            )
            self._search_status_lbl.pack(side="left", fill="x", expand=True)
            cache_button = CompatCTkButton(
                status_row,
                text=self._tr("rvc_cache_clear_btn", default="🧹"),
                command=self._clear_rvc_cache,
                width=scaled_size(25, min_size=23),
                height=scaled_size(20, min_size=18),
                corner_radius=6,
                fg_color=Colors.BG_CARD,
                hover_color=Colors.BG_HOVER,
                text_color=Colors.TEXT_MAIN,
                font=("Segoe UI", scaled_font_size(8)),
            )
            cache_button.pack(side="right", padx=(4, 0))
            ToolTip(
                cache_button,
                self._tr(
                    "tip_rvc_cache_clear",
                    default=(
                        "Очистить временные preview и недокачанные модели. "
                        "Примеры установленных моделей сохраняются."
                    ),
                ),
            )

            self._search_entry.bind("<KeyRelease>", self._on_search_key)
            self._search_entry.bind("<Return>", self._on_search_key)
            # Не закрывать попап при клике в поле поиска
            self._search_entry.bind("<Button-1>", lambda e: "break" if False else None)

            # ── Каталоги вместо прокручиваемого заголовка секции ──
            catalog_bar = tk.Frame(outer, bg=Colors.BG_INPUT)
            catalog_bar.pack(fill="x", padx=6, pady=(0, 4))
            self._catalog_buttons = {}
            catalog_specs = ("curated", "new", "top")
            for mode in catalog_specs:
                caption = self._catalog_title(mode)
                button = CompatCTkButton(
                    catalog_bar,
                    text=caption,
                    command=lambda selected=mode: self._set_catalog_mode(selected),
                    width=scaled_size(90, min_size=78),
                    height=scaled_size(24, min_size=22),
                    corner_radius=7,
                    fg_color=Colors.BG_INPUT,
                    hover_color=Colors.BG_HOVER,
                    text_color=Colors.TEXT_MAIN,
                    font=("Segoe UI", scaled_font_size(8), "bold"),
                )
                button.pack(side="left", fill="x", expand=True, padx=2)
                self._catalog_buttons[mode] = button
                tip_keys = {
                    "curated": (
                        "tip_rvc_catalog_curated",
                        "Стабильная офлайн-подборка XTTS Studio",
                    ),
                    "new": (
                        "tip_rvc_catalog_new",
                        "Последние добавленные модели voice-models.com",
                    ),
                    "top": (
                        "tip_rvc_catalog_top",
                        "Популярные модели voice-models.com",
                    ),
                }
                tip_key, tip_fallback = tip_keys[mode]
                ToolTip(button, self._tr(tip_key, default=tip_fallback))
            self._style_catalog_buttons()

            # ── Скроллируемая область строк ──
            # Canvas+Frame+Scrollbar: длинные результаты поиска (voice-models)
            # не раздувают окно и реально крутятся колёсиком/полосой.
            list_host = tk.Frame(outer, bg=Colors.BG_INPUT)
            list_host.pack(fill="both", expand=True)

            # Скроллбар справа — пакуем первым, чтобы не схлопнулся
            vsb = tk.Scrollbar(list_host, orient="vertical")
            vsb.pack(side="right", fill="y")

            canvas = tk.Canvas(
                list_host,
                bg=Colors.BG_INPUT,
                highlightthickness=0,
                bd=0,
                height=scaled_size(240, min_size=200),
            )
            canvas.pack(side="left", fill="both", expand=True)

            inner = tk.Frame(canvas, bg=Colors.BG_INPUT, bd=0, highlightthickness=0)
            self._rows_container = inner
            self._list_canvas = canvas
            self._list_vsb = vsb
            self._list_inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

            def _on_inner_configure(_e=None):
                self._refresh_list_scroll()

            def _on_canvas_configure(e):
                try:
                    canvas.itemconfigure(self._list_inner_id, width=max(int(e.width), 1))
                    self._refresh_list_scroll()
                except Exception:
                    pass

            inner.bind("<Configure>", _on_inner_configure)
            canvas.bind("<Configure>", _on_canvas_configure)
            canvas.configure(yscrollcommand=vsb.set)
            vsb.configure(command=canvas.yview)

            # Колесо на canvas/host (+ позже рекурсивно на строки в _render_rows)
            for w in (canvas, inner, list_host, vsb):
                w.bind("<MouseWheel>", self._on_list_wheel)
                w.bind("<Button-4>", self._on_list_wheel)
                w.bind("<Button-5>", self._on_list_wheel)

            self._search_results = None
            self._search_query = ""
            if self._catalog_mode == "curated":
                self._set_search_status(
                    self._tr(
                        "status_rvc_catalog_curated",
                        default="Офлайн-подборка XTTS Studio",
                    )
                )
            elif self._catalog_results:
                label = self._catalog_title(self._catalog_mode)
                self._set_search_status(
                    self._tr(
                        "status_rvc_catalog_count",
                        label,
                        len(self._catalog_results),
                        default=f"Каталог «{label}»: {len(self._catalog_results)} моделей",
                    )
                )
            self._render_rows(reset_scroll=True)
            if self._catalog_mode in ("new", "top") and not self._catalog_results:
                self._start_catalog_load(self._catalog_mode)

            popup.update_idletasks()
            # Увеличиваем только нижнюю границу примерно на треть. Верх остаётся
            # привязан к кнопке, а снизу резервируется место под footer/«Закрыть».
            target_h = scaled_size(450, min_size=360)
            max_h = scaled_size(520, min_size=400)
            bottom_reserve = scaled_size(72, min_size=58)
            available_down = max(100, win_h - y - bottom_reserve)
            h = min(target_h, max_h, available_down)

            if x + width > win_w:
                x = max(0, win_w - width)
            if x < 0:
                x = 0
            if y < 0:
                y = 0

            popup.place(x=int(x), y=int(y), width=int(width), height=int(h))
            try:
                popup.lift()
                popup.tkraise()
            except Exception:
                pass

            self._ignore_outside_until = time.monotonic() + 0.20

            try:
                self._escape_bind_id = top_win.bind(
                    "<Escape>", lambda e: self._close_popup(), add="+"
                )
            except Exception:
                self._escape_bind_id = None

            _ensure_global_binds(top_win)
            if self not in _OPEN_DROPDOWNS:
                _OPEN_DROPDOWNS.append(self)

            # Фокус в поиск — удобно сразу печатать
            try:
                self._search_entry.focus_set()
            except Exception:
                pass

        except Exception as e:
            print(f"[RVC] Ошибка dropdown: {e}")
            self._close_popup()

    def _clear_rvc_cache(self):
        parent = self._top_win
        try:
            confirmed = messagebox.askyesno(
                self._tr("rvc_cache_clear_title", default="Очистка кэша RVC"),
                self._tr(
                    "rvc_cache_clear_confirm",
                    default=(
                        "Удалить временные аудиопримеры и недокачанные модели?\n\n"
                        "Примеры уже установленных RVC-моделей будут сохранены "
                        "и удалятся только вместе с моделью."
                    ),
                ),
                parent=parent,
            )
        except Exception:
            confirmed = True
        if not confirmed:
            return

        try:
            result = rvc_catalog.clear_rvc_cache()
        except Exception as error:
            self.on_status(
                self._tr(
                    "status_rvc_cache_failed",
                    error,
                    default=f"❌ Не удалось очистить кэш RVC: {error}",
                )
            )
            return

        removed = int(result.get("removed_files", 0))
        if not removed:
            self.on_status(
                self._tr(
                    "status_rvc_cache_empty",
                    default="Кэш RVC уже пуст",
                )
            )
            return

        size_bytes = int(result.get("removed_bytes", 0))
        if size_bytes >= 1024 * 1024:
            size_text = f"{size_bytes / (1024 * 1024):.1f} MB"
        elif size_bytes >= 1024:
            size_text = f"{size_bytes / 1024:.1f} KB"
        else:
            size_text = f"{size_bytes} B"
        self.on_status(
            self._tr(
                "status_rvc_cache_cleared",
                removed,
                result.get("removed_previews", 0),
                result.get("removed_partials", 0),
                size_text,
                default=(
                    f"🧹 Кэш RVC очищен: {removed} файлов · "
                    f"preview: {result.get('removed_previews', 0)} · "
                    f"недокачанные: {result.get('removed_partials', 0)} · "
                    f"{size_text}"
                ),
            )
        )

    # ------------------------------------------------------------
    #  Каталоги: подборка / новые / топ
    # ------------------------------------------------------------

    def _catalog_title(self, mode):
        keys = {
            "curated": ("rvc_catalog_curated", "★ Подборка"),
            "new": ("rvc_catalog_new", "🆕 Новые"),
            "top": ("rvc_catalog_top", "🔥 Топ"),
        }
        key, fallback = keys.get(mode, keys["curated"])
        return self._tr(key, default=fallback)

    def _style_catalog_buttons(self):
        for mode, button in self._catalog_buttons.items():
            try:
                active = mode == self._catalog_mode
                button.configure(
                    fg_color=Colors.BG_ACTIVE if active else Colors.BG_INPUT,
                    hover_color=Colors.BG_ACTIVE if active else Colors.BG_HOVER,
                    text_color=Colors.TEXT_MAIN,
                )
            except Exception:
                pass

    def _set_catalog_mode(self, mode):
        selected = str(mode or "curated").lower()
        if selected not in ("curated", "new", "top"):
            return

        if self._search_after_id is not None:
            try:
                self.trigger_btn.after_cancel(self._search_after_id)
            except Exception:
                pass
            self._search_after_id = None
        self._search_token += 1
        self._search_pending = False
        self._search_query = ""
        self._search_results = None
        try:
            if self._search_var is not None:
                self._search_var.set("")
        except Exception:
            pass

        self._catalog_token += 1
        self._catalog_loading = False
        self._catalog_mode = selected
        self._catalog_results = None
        self._style_catalog_buttons()

        if selected == "curated":
            self._set_search_status(
                self._tr(
                    "status_rvc_catalog_curated",
                    default="Офлайн-подборка XTTS Studio",
                )
            )
            self._render_rows(reset_scroll=True)
        else:
            self._start_catalog_load(selected)

    def _start_catalog_load(self, mode):
        selected = str(mode or "").lower()
        if selected not in ("new", "top") or self._catalog_loading:
            return
        self._catalog_mode = selected
        self._catalog_loading = True
        self._catalog_results = []
        self._catalog_token += 1
        token = self._catalog_token
        label = self._catalog_title(selected)
        self._set_search_status(
            self._tr(
                "status_rvc_catalog_loading",
                label,
                default=f"Загружаю каталог «{label}»…",
            )
        )
        self._style_catalog_buttons()
        self._render_rows(reset_scroll=True)

        def _worker():
            try:
                results = rvc_catalog.browse_voice_models(selected, max_results=50)
            except Exception:
                results = []
            try:
                self.trigger_btn.after(
                    0,
                    lambda: self._on_catalog_done(token, selected, results),
                )
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_catalog_done(self, token, mode, results):
        if token != self._catalog_token or mode != self._catalog_mode:
            return
        if self._popup is None:
            return
        self._catalog_loading = False
        self._catalog_results = results or []
        label = self._catalog_title(mode)
        if self._catalog_results:
            self._set_search_status(
                self._tr(
                    "status_rvc_catalog_count",
                    label,
                    len(self._catalog_results),
                    default=f"Каталог «{label}»: {len(self._catalog_results)} моделей",
                )
            )
        else:
            self._set_search_status(
                self._tr(
                    "status_rvc_catalog_unavailable",
                    label,
                    default=f"Каталог «{label}» временно недоступен",
                )
            )
        self._render_rows(reset_scroll=True)

    # ------------------------------------------------------------
    #  Поиск
    # ------------------------------------------------------------

    def _on_search_key(self, event=None):
        """Debounce: не дёргать сеть на каждую букву (иначе timeout spam)."""
        if not self._search_var:
            return
        q = (self._search_var.get() or "").strip()
        self._search_query = q

        # Отменяем предыдущий отложенный запуск
        if self._search_after_id is not None:
            try:
                self.trigger_btn.after_cancel(self._search_after_id)
            except Exception:
                pass
            self._search_after_id = None

        if len(q) < 2:
            self._search_results = None
            self._search_pending = False
            self._search_token += 1
            if self._catalog_mode == "curated":
                status = self._tr(
                    "status_rvc_catalog_curated",
                    default="Офлайн-подборка XTTS Studio",
                )
            elif self._catalog_loading:
                label = self._catalog_title(self._catalog_mode)
                status = self._tr(
                    "status_rvc_catalog_loading",
                    label,
                    default=f"Загружаю каталог «{label}»…",
                )
            else:
                label = self._catalog_title(self._catalog_mode)
                count = len(self._catalog_results or [])
                status = self._tr(
                    "status_rvc_catalog_count",
                    label,
                    count,
                    default=f"Каталог «{label}»: {count} моделей",
                )
            self._set_search_status(status)
            self._render_rows(reset_scroll=True)
            return

        # Мгновенно — только локальный seed (без сети), чтобы UI не «молчал»
        try:
            local_only = rvc_catalog.search_catalog(q, max_results=30, live=False)
        except Exception:
            local_only = []
        self._search_results = local_only
        self._search_pending = True
        n_local = len(local_only)
        if n_local:
            self._set_search_status(
                self._tr(
                    "rvc_search_local_online",
                    n_local,
                    default=f"Локально: {n_local} · ищу online…",
                )
            )
        else:
            self._set_search_status(
                self._tr("rvc_search_searching", default="Ищу на voice-models.com…")
            )
        self._render_rows(reset_scroll=True)

        # Live — с debounce
        delay = self._search_debounce_ms
        # Enter — сразу
        if event is not None and getattr(event, "keysym", "") == "Return":
            delay = 0

        def _fire():
            self._search_after_id = None
            self._start_live_search(q)

        try:
            self._search_after_id = self.trigger_btn.after(delay, _fire)
        except Exception:
            _fire()

    def _start_live_search(self, q: str):
        self._search_token += 1
        token = self._search_token
        query = (q or "").strip()
        if len(query) < 2:
            return

        def _worker():
            try:
                results = rvc_catalog.search_catalog(query, max_results=30, live=True)
            except Exception:
                results = []
            try:
                self.trigger_btn.after(0, lambda: self._on_search_done(token, query, results))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_search_done(self, token, query, results):
        if token != self._search_token:
            return  # устаревший ответ
        if self._popup is None:
            return
        self._search_pending = False
        self._search_results = results or []
        n = len(self._search_results)
        if n:
            try:
                self._set_search_status(self.t("rvc_search_found", n))
            except Exception:
                self._set_search_status(f"Найдено: {n}")
        else:
            self._set_search_status(
                self._tr(
                    "rvc_search_empty_or_offline",
                    default="Ничего не найдено (online недоступен — смотри seed)",
                )
            )
        self._render_rows(reset_scroll=True)

    def _set_search_status(self, text):
        try:
            if self._search_status_lbl and self._search_status_lbl.winfo_exists():
                self._search_status_lbl.configure(text=text)
        except Exception:
            pass

    # ------------------------------------------------------------
    #  Outside-click helpers
    # ------------------------------------------------------------

    def _widget_is_descendant(self, widget, ancestor):
        if widget is None or ancestor is None:
            return False
        try:
            w = widget
            for _ in range(64):
                if w == ancestor:
                    return True
                try:
                    w = w.master
                except Exception:
                    break
                if w is None:
                    break
        except Exception:
            pass
        return False

    def _point_in_widget(self, x_root, y_root, widget):
        try:
            if not widget or not widget.winfo_exists():
                return False
            wx = widget.winfo_rootx()
            wy = widget.winfo_rooty()
            ww = widget.winfo_width()
            wh = widget.winfo_height()
            return wx <= x_root <= wx + ww and wy <= y_root <= wy + wh
        except Exception:
            return False

    def _is_click_on_trigger(self, event):
        try:
            if self._widget_is_descendant(event.widget, self.trigger_btn):
                return True
        except Exception:
            pass
        return self._point_in_widget(event.x_root, event.y_root, self.trigger_btn)

    def _is_click_inside_popup(self, event):
        if not self._popup:
            return False
        try:
            if self._widget_is_descendant(event.widget, self._popup):
                return True
        except Exception:
            pass
        return self._point_in_widget(event.x_root, event.y_root, self._popup)

    def _pointer_inside_popup(self, event=None):
        """По координатам указателя (надёжнее для MouseWheel, чем event.widget)."""
        if not self._popup:
            return False
        try:
            if not self._popup.winfo_exists():
                return False
            if event is not None and hasattr(event, "x_root") and hasattr(event, "y_root"):
                return self._point_in_widget(event.x_root, event.y_root, self._popup)
            # fallback: текущая позиция курсора
            x = self._popup.winfo_pointerx()
            y = self._popup.winfo_pointery()
            return self._point_in_widget(x, y, self._popup)
        except Exception:
            return False

    # ── PATCH 2026-07-14: helper for smooth scroll ─────────────────────────────
    def _estimate_scroll_delta(self, units: int) -> float:
        """Преобразует 'units' в дробь [0,1] для yview_moveto."""
        canvas = getattr(self, "_list_canvas", None)
        if not canvas:
            return units * 0.02
        try:
            bbox = canvas.bbox("all")
            if not bbox:
                return units * 0.02
            total_h = float(max(1, bbox[3] - bbox[1]))
            LINE_HEIGHT = 28.0  # высота строки в списке RVC
            return units * LINE_HEIGHT / total_h
        except Exception:
            return units * 0.02

    def _on_list_wheel(self, event):
        """Скролл списка результатов (в т.ч. сетевого поиска).

        PATCH 2026-07-14: плавный скролл через AnimationManager.
        """
        canvas = getattr(self, "_list_canvas", None)
        if not canvas:
            return "break"
        try:
            if not canvas.winfo_exists():
                return "break"
            # Если контент целиком влезает — нечего крутить
            try:
                first, last = canvas.yview()
                if first <= 0.0 and last >= 1.0:
                    return "break"
            except Exception:
                pass
            if hasattr(event, "delta") and event.delta:
                steps = int(-1 * (event.delta / 120))
                if steps == 0:
                    steps = -1 if event.delta > 0 else 1
            elif getattr(event, "num", None) == 4:
                steps = -1
            elif getattr(event, "num", None) == 5:
                steps = 1
            else:
                return "break"

            # Smooth scroll через AnimationManager
            try:
                from engine.gui.animation_manager import AnimationManager

                mgr = AnimationManager.get()
                if mgr._no_op:
                    canvas.yview_scroll(steps * 3, "units")
                else:
                    current_top = canvas.yview()[0]
                    delta_frac = self._estimate_scroll_delta(steps * 3)
                    target = max(0.0, min(1.0, current_top + delta_frac))

                    anim_id = f"_rvc_scroll_{id(self)}"
                    if mgr.is_running(anim_id):
                        mgr.cancel(anim_id)
                        canvas.yview_moveto(current_top)

                    mgr.animate(
                        target=canvas,
                        property_setter=lambda v: canvas.yview_moveto(v),
                        start=current_top,
                        end=target,
                        duration_ms=200,
                        easing="ease_out",
                        animation_id=anim_id,
                    )
            except Exception:
                canvas.yview_scroll(steps * 3, "units")

        except Exception:
            pass
        return "break"

    def _refresh_list_scroll(self):
        """Пересчёт scrollregion + показ/скрытие полосы при переполнении."""
        canvas = getattr(self, "_list_canvas", None)
        inner = self._rows_container
        if not canvas or inner is None:
            return
        try:
            if not canvas.winfo_exists():
                return
            inner.update_idletasks()
            bbox = canvas.bbox("all")
            if bbox:
                canvas.configure(scrollregion=bbox)
            # ширина inner = ширина canvas
            try:
                canvas.itemconfigure(self._list_inner_id, width=max(int(canvas.winfo_width()), 1))
            except Exception:
                pass
            # Авто-скрытие скроллбара, если всё влезает
            vsb = getattr(self, "_list_vsb", None)
            if vsb is not None and vsb.winfo_exists():
                try:
                    first, last = canvas.yview()
                    if first <= 0.001 and last >= 0.999:
                        # всё видно — полоса не обязательна, но оставляем (Windows UX)
                        pass
                except Exception:
                    pass
        except Exception:
            pass

    def _bind_wheel_tree(self, widget):
        """Вешает колесо на виджет и всех детей (строки после _render_rows)."""
        if widget is None:
            return
        try:
            widget.bind("<MouseWheel>", self._on_list_wheel, add="+")
            widget.bind("<Button-4>", self._on_list_wheel, add="+")
            widget.bind("<Button-5>", self._on_list_wheel, add="+")
        except Exception:
            return
        try:
            for child in widget.winfo_children():
                self._bind_wheel_tree(child)
        except Exception:
            pass

    def _on_outside_click(self, event):
        if self._popup is None:
            return
        try:
            if not self._popup.winfo_exists():
                return
        except Exception:
            return

        if time.monotonic() < self._ignore_outside_until:
            return
        if self._is_click_on_trigger(event):
            return
        if self._is_click_inside_popup(event):
            return
        self._close_popup()

    # ------------------------------------------------------------
    #  Построение строк списка
    # ------------------------------------------------------------

    def _ensure_active_row_visible(self):
        """Прокручивает только список так, чтобы выделенная строка не исчезала из вида."""
        canvas = getattr(self, "_list_canvas", None)
        inner = self._rows_container
        row = self._active_row_widget
        if not canvas or inner is None or row is None:
            return
        try:
            if not canvas.winfo_exists() or not row.winfo_exists():
                return
            inner.update_idletasks()
            self._refresh_list_scroll()

            visible_top = float(canvas.canvasy(0))
            visible_bottom = visible_top + max(float(canvas.winfo_height()), 1.0)
            row_top = float(row.winfo_y())
            row_bottom = row_top + max(float(row.winfo_height()), 1.0)
            margin = float(scaled_size(3, min_size=2))

            target_top = None
            if row_top < visible_top + margin:
                target_top = max(0.0, row_top - margin)
            elif row_bottom > visible_bottom - margin:
                target_top = max(0.0, row_bottom - float(canvas.winfo_height()) + margin)

            if target_top is None:
                return
            bbox = canvas.bbox("all")
            if not bbox:
                return
            content_top = float(bbox[1])
            content_height = max(float(bbox[3] - bbox[1]), 1.0)
            canvas.yview_moveto(max(0.0, min(1.0, (target_top - content_top) / content_height)))
        except Exception:
            pass

    def _render_rows(self, reset_scroll=False, ensure_active=False):
        """
        Перестраивает строки, не теряя текущую позицию списка.

        reset_scroll=True нужен только при открытии/новом поиске. При выборе
        строки позиция сохраняется, а активная кнопка остаётся в поле зрения.
        """
        if self._rows_container is None:
            return

        canvas = getattr(self, "_list_canvas", None)
        old_view = None
        if not reset_scroll and canvas is not None:
            try:
                old_view = float(canvas.yview()[0])
            except Exception:
                old_view = None

        self._render_token += 1
        render_token = self._render_token
        self._active_row_widget = None
        for w in self._rows_container.winfo_children():
            w.destroy()

        rvc_dir = os.path.join(rvc_catalog.BASE_DIR, "models", "rvc")
        try:
            local_names = sorted(f[:-4] for f in os.listdir(rvc_dir) if f.endswith(".pth"))
        except Exception:
            local_names = []

        # При повторном открытии сразу считаем сохранённую локальную модель
        # активной: кнопка удаления появляется без дополнительного клика.
        if self._active_row_key is None:
            selected_name = self.variable.get() or NONE_LABEL
            if selected_name == NONE_LABEL:
                self._active_row_key = ("none", None)
            elif selected_name in local_names:
                self._active_row_key = ("local", selected_name)

        # Remote: поиск имеет приоритет; иначе выбранный каталог.
        if self._search_results is not None:
            catalog_entries = [e for e in self._search_results if not rvc_catalog.is_downloaded(e)]
        elif self._catalog_mode == "curated":
            try:
                catalog_entries = [
                    e for e in rvc_catalog.get_catalog() if not rvc_catalog.is_downloaded(e)
                ]
            except Exception:
                catalog_entries = []
        else:
            catalog_entries = [
                e for e in (self._catalog_results or []) if not rvc_catalog.is_downloaded(e)
            ]

        self._row_frame(NONE_LABEL, key=("none", None), select_cb=self._select_none).pack(fill="x")

        # Локальные всегда показываем (фильтр по поиску — по имени)
        q = (self._search_query or "").lower()
        shown_local = 0
        for name in local_names:
            if q and q not in name.lower():
                continue
            self._render_local_row(name)
            shown_local += 1

        if catalog_entries:
            if shown_local:
                tk.Frame(
                    self._rows_container,
                    bg=Colors.BORDER,
                    height=1,
                ).pack(fill="x", padx=8, pady=(5, 3))
            for entry in catalog_entries:
                self._render_remote_row(entry)

        if shown_local == 0 and not catalog_entries and not self._search_pending:
            if self._catalog_loading:
                empty = self._tr(
                    "rvc_catalog_loading",
                    default="Загрузка каталога…",
                )
            elif self._search_results is not None:
                empty = self._tr("rvc_search_empty", default="Ничего не найдено")
            else:
                empty = self._tr("rvc_list_empty", default="Список моделей пуст")
            tk.Label(
                self._rows_container,
                text=empty,
                bg=Colors.BG_INPUT,
                fg=Colors.TEXT_DIM,
                font=("Segoe UI", scaled_font_size(9)),
            ).pack(fill="x", padx=8, pady=8)

        # Колесо на всех строках/кнопках + scrollregion
        # (без этого MouseWheel на Label/CTkButton не доходит до canvas)
        self._bind_wheel_tree(self._rows_container)

        def _finish_layout():
            # Отложенный callback от старого render не должен менять новый список.
            if render_token != self._render_token:
                return
            current_canvas = getattr(self, "_list_canvas", None)
            if current_canvas is None:
                return
            try:
                if not current_canvas.winfo_exists():
                    return
                self._refresh_list_scroll()
                if reset_scroll:
                    current_canvas.yview_moveto(0)
                elif old_view is not None:
                    current_canvas.yview_moveto(old_view)
                if ensure_active:
                    self._ensure_active_row_visible()
            except Exception:
                pass

        _finish_layout()
        try:
            # На Windows bbox("all") окончательно готов только после layout idle.
            if self.trigger_btn:
                self.trigger_btn.after(10, _finish_layout)
                self.trigger_btn.after(50, _finish_layout)
        except Exception:
            pass

    def _row_frame(self, text, key, select_cb, action_btn=None, preview_btn=None):
        """Строка с зарезервированной правой колонкой для активных действий."""
        active = self._active_row_key == key
        row_bg = Colors.BG_HOVER if active else Colors.BG_INPUT
        row = tk.Frame(self._rows_container, bg=row_bg)
        if active:
            self._active_row_widget = row

        # Важно: action-slot пакуется ПЕРВЫМ. Поэтому длинное имя сжимается,
        # а кнопки справа никогда не выталкиваются за границу canvas.
        if action_btn is not None or preview_btn is not None:
            has_two_actions = action_btn is not None and preview_btn is not None
            slot_width = 68 if has_two_actions else 38
            action_slot = tk.Frame(
                row,
                bg=row_bg,
                width=scaled_size(slot_width, min_size=slot_width - 4),
                height=scaled_size(28, min_size=26),
            )
            action_slot.pack(side="right", fill="y", padx=(2, 4))
            action_slot.pack_propagate(False)
            action_slot.bind("<Button-1>", lambda e: select_cb())

            # Не рисуем бесполезные disabled-кнопки на каждой строке.
            # Действия появляются только у выделенной строки (или у загрузки)
            # и сразу находятся в видимой зарезервированной колонке.
            if active or self._downloading_key == key:
                if preview_btn is not None:
                    preview = preview_btn(action_slot)
                    preview.pack(side="left", expand=True, padx=(1, 0))
                if action_btn is not None:
                    btn = action_btn(action_slot)
                    btn.pack(side="right", expand=True, padx=(0, 1))

        lbl = tk.Label(
            row,
            text=text,
            width=1,  # разрешает геометрии обрезать длинный текст до доступной ширины
            anchor="w",
            bg=row_bg,
            fg=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(9)),
        )
        lbl.pack(side="left", fill="both", expand=True, padx=(8, 2), pady=4)
        lbl.bind("<Button-1>", lambda e: select_cb())
        row.bind("<Button-1>", lambda e: select_cb())
        return row

    def _build_preview_button(self, parent, entry, key, local=False):
        loading = self._preview_loading_key == key
        playing = self._preview_playing_key == key
        button = CompatCTkButton(
            parent,
            text="…" if loading else ("■" if playing else "▶"),
            command=lambda: self._toggle_preview(entry, key),
            width=scaled_size(26, min_size=24),
            height=scaled_size(20, min_size=18),
            corner_radius=6,
            fg_color=Colors.BG_CARD,
            hover_color="#a3342e" if playing else Colors.BG_HOVER,
            text_color=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(9)),
            state="disabled" if loading else "normal",
        )
        if loading:
            tip = self._tr(
                "tip_rvc_preview_loading",
                default="Загружаю короткий пример…",
            )
        elif playing:
            tip = self._tr(
                "tip_rvc_preview_stop",
                default="Остановить пример",
            )
        elif local:
            tip = self._tr(
                "tip_rvc_preview_local",
                default="Прослушать пример скачанной RVC-модели",
            )
        else:
            tip = self._tr(
                "tip_rvc_preview_remote",
                default="Прослушать пример до скачивания",
            )
        ToolTip(button, tip)
        return button

    def _render_local_row(self, name):
        key = ("local", name)

        def _select():
            self._active_row_key = key
            self.variable.set(name)
            # Остаёмся открытыми: после выделения активируется 🗑
            self._render_rows(ensure_active=True)

        def _btn(row):
            return CompatCTkButton(
                row,
                text="🗑",
                command=lambda: self._delete_local(name),
                width=scaled_size(26, min_size=24),
                height=scaled_size(20, min_size=18),
                corner_radius=6,
                fg_color=Colors.BG_CARD,
                hover_color="#a3342e",
                text_color=Colors.TEXT_MAIN,
                font=("Segoe UI", scaled_font_size(9)),
                state="normal",
            )

        local_entry = None
        try:
            local_entry = rvc_catalog.get_local_model_entry(name)
        except Exception:
            pass
        preview_available = False
        if local_entry:
            try:
                preview_available = rvc_catalog.can_preview(local_entry)
            except Exception:
                pass

        preview_factory = None
        if preview_available:
            preview_factory = lambda row: self._build_preview_button(
                row,
                local_entry,
                key,
                local=True,
            )
        self._row_frame(
            name,
            key,
            _select,
            action_btn=_btn,
            preview_btn=preview_factory,
        ).pack(fill="x")

    def _render_remote_row(self, entry):
        key = ("remote", entry["id"])
        subtitle_parts = [p for p in (entry.get("author"), entry.get("license")) if p]
        subtitle = " · ".join(subtitle_parts)
        downloadable = entry.get("downloadable")
        if downloadable is None:
            try:
                downloadable = rvc_catalog._is_direct_downloadable(entry.get("url") or "")
            except Exception:
                downloadable = True

        def _select():
            self._active_row_key = key
            self._render_rows(ensure_active=True)

        preview_available = False
        try:
            preview_available = rvc_catalog.can_preview(entry)
        except Exception:
            pass

        if self._downloading_key == key:

            def _btn(row):
                return CompatCTkButton(
                    row,
                    text="✕",
                    command=self._cancel_download,
                    width=scaled_size(26, min_size=24),
                    height=scaled_size(20, min_size=18),
                    corner_radius=6,
                    fg_color=Colors.BG_CARD,
                    hover_color="#a3342e",
                    text_color=Colors.TEXT_MAIN,
                    font=("Segoe UI", scaled_font_size(9)),
                    state="normal",
                )

        elif downloadable:

            def _btn(row):
                return CompatCTkButton(
                    row,
                    text="⬇",
                    command=lambda: self._start_download(entry),
                    width=scaled_size(26, min_size=24),
                    height=scaled_size(20, min_size=18),
                    corner_radius=6,
                    fg_color=Colors.BG_CARD,
                    hover_color=Colors.BG_HOVER,
                    text_color=Colors.TEXT_MAIN,
                    font=("Segoe UI", scaled_font_size(9)),
                    state="normal",
                )

        else:
            # Нет прямой ссылки (GDrive folder / только страница) — открыть в браузере
            def _btn(row):
                return CompatCTkButton(
                    row,
                    text="🔗",
                    command=lambda: self._open_page(entry),
                    width=scaled_size(26, min_size=24),
                    height=scaled_size(20, min_size=18),
                    corner_radius=6,
                    fg_color=Colors.BG_CARD,
                    hover_color=Colors.BG_HOVER,
                    text_color=Colors.TEXT_MAIN,
                    font=("Segoe UI", scaled_font_size(9)),
                    state="normal",
                )

        label = entry.get("name", entry["id"])
        if entry.get("size"):
            # короткий размер в конце, если влезает
            short = label if len(label) < 48 else (label[:45] + "…")
            label = f"{short}"
        preview_factory = None
        if preview_available:
            preview_factory = lambda parent: self._build_preview_button(
                parent,
                entry,
                key,
                local=False,
            )
        row = self._row_frame(
            label,
            key,
            _select,
            action_btn=_btn,
            preview_btn=preview_factory,
        )
        tip_parts = [
            entry.get("name"),
            subtitle,
            entry.get("size"),
            entry.get("description"),
            (
                None
                if downloadable
                else self._tr(
                    "rvc_open_in_browser_tip",
                    default="Нет прямой ссылки — откроется страница модели",
                )
            ),
        ]
        ToolTip(row, "\n".join(p for p in tip_parts if p))
        row.pack(fill="x")

    def _select_none(self):
        self._active_row_key = ("none", None)
        self.variable.set(NONE_LABEL)
        self._render_rows(ensure_active=True)

    def _toggle_preview(self, entry, key=None):
        preview_key = key or ("remote", entry["id"])
        if self._preview_playing_key == preview_key:
            try:
                from engine.gui import player as audio_player

                audio_player.stop_rvc_preview()
            except Exception:
                self._preview_playing_key = None
                if self._popup is not None:
                    self._render_rows(ensure_active=True)
            return
        self._start_preview(entry, preview_key)

    def _start_preview(self, entry, key=None):
        """Кэширует только короткий sample и передаёт его общему pygame-плееру."""
        preview_key = key or ("remote", entry["id"])
        if self._preview_loading_key is not None:
            return
        self._preview_loading_key = preview_key
        self._preview_token += 1
        token = self._preview_token
        self._render_rows(ensure_active=True)
        self.on_status(
            self._tr(
                "status_rvc_preview_searching",
                entry.get("name", ""),
                default=f"🔎 Загружаю пример голоса: {entry.get('name', '')}",
            )
        )

        def _worker():
            try:
                audio_path = rvc_catalog.get_preview_audio_path(entry)
            except Exception:
                audio_path = ""
            try:
                self.trigger_btn.after(
                    0,
                    lambda: self._on_preview_ready(
                        token,
                        preview_key,
                        entry,
                        audio_path,
                    ),
                )
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_preview_ready(self, token, key, entry, audio_path):
        if token != self._preview_token:
            return
        self._preview_loading_key = None
        if self._popup is not None:
            self._render_rows(ensure_active=True)

        if not audio_path:
            self.on_status(
                self._tr(
                    "status_rvc_preview_unavailable",
                    entry.get("name", ""),
                    default=f"⚠ Для модели нет доступного примера: {entry.get('name', '')}",
                )
            )
            return

        def _state_callback(playing):
            try:
                self.trigger_btn.after(
                    0,
                    lambda: self._on_preview_state(key, entry, bool(playing)),
                )
            except Exception:
                pass

        try:
            from engine.gui import player as audio_player

            audio_player.play_rvc_preview(
                audio_path,
                on_state_change=_state_callback,
            )
        except Exception as error:
            # Если pygame недоступен, sample всё ещё можно открыть напрямую.
            try:
                opened = rvc_catalog.open_preview(entry)
            except Exception:
                opened = False
            if opened:
                self.on_status(
                    self._tr(
                        "status_rvc_preview_browser",
                        entry.get("name", ""),
                        default=f"▶ Пример открыт в браузере: {entry.get('name', '')}",
                    )
                )
            else:
                self.on_status(
                    self._tr(
                        "status_rvc_preview_failed",
                        entry.get("name", ""),
                        error,
                        default=(
                            f"❌ Не удалось воспроизвести пример "
                            f"{entry.get('name', '')}: {error}"
                        ),
                    )
                )

    def _on_preview_state(self, key, entry, playing):
        if playing:
            self._preview_playing_key = key
            self.on_status(
                self._tr(
                    "status_rvc_preview_playing",
                    entry.get("name", ""),
                    default=f"▶ Воспроизводится: {entry.get('name', '')}",
                )
            )
        elif self._preview_playing_key == key:
            self._preview_playing_key = None
        if self._popup is not None:
            self._render_rows(ensure_active=True)

    def _open_page(self, entry):
        ok = False
        try:
            ok = rvc_catalog.open_model_page(entry)
        except Exception:
            pass
        if ok:
            self.on_status(
                self._tr(
                    "status_rvc_open_page",
                    entry.get("name", ""),
                    default=f"🌐 Открыто в браузере: {entry.get('name', '')}",
                )
            )
        else:
            self.on_status(
                self._tr(
                    "status_rvc_open_page_failed",
                    entry.get("name", ""),
                    default=f"❌ Не удалось открыть: {entry.get('name', '')}",
                )
            )

    # ------------------------------------------------------------
    #  Скачивание / отмена / удаление
    # ------------------------------------------------------------

    def _start_download(self, entry):
        self._downloading_key = ("remote", entry["id"])
        self._cancel_flag = {"cancelled": False}
        self._render_rows(ensure_active=True)
        self.on_status(self.t("status_rvc_downloading", entry.get("name", "")))
        self.on_show_cancel(self._cancel_download)

        def _progress_cb(downloaded, total):
            if total:
                pct = int(downloaded * 100 / total)
                try:
                    self.trigger_btn.after(0, lambda: self.on_progress(pct))
                except Exception:
                    pass

        def _worker():
            ok = rvc_catalog.download_model(
                entry,
                progress_callback=_progress_cb,
                cancelled_flag=self._cancel_flag,
            )
            try:
                self.trigger_btn.after(0, lambda: self._on_download_done(ok, entry))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _cancel_download(self):
        if self._cancel_flag is not None:
            self._cancel_flag["cancelled"] = True

    def _on_download_done(self, ok, entry):
        self._downloading_key = None
        self._cancel_flag = None
        self.on_hide_cancel()
        self.on_progress(0)
        if ok:
            local_name = os.path.splitext(os.path.basename(rvc_catalog.local_model_path(entry)))[0]
            self.on_status(self.t("status_rvc_downloaded", entry.get("name", "")))
            self._active_row_key = ("local", local_name)
            self.variable.set(local_name)
        else:
            # Если не downloadable — подсказка открыть страницу
            if entry.get("downloadable") is False:
                self.on_status(
                    self._tr(
                        "status_rvc_need_manual",
                        entry.get("name", ""),
                        default=(
                            f"⚠ Нет прямой ссылки для «{entry.get('name', '')}» "
                            f"— откройте 🔗 и положите .pth в models/rvc/"
                        ),
                    )
                )
            else:
                self.on_status(self.t("status_rvc_download_failed", entry.get("name", "")))
        if self._popup is not None:
            self._render_rows(ensure_active=True)

    def _delete_local(self, name):
        ok = rvc_catalog.delete_local_model(name)
        if ok:
            self.on_status(self.t("status_rvc_deleted", name))
            if self.variable.get() == name:
                self.variable.set(NONE_LABEL)
        else:
            self.on_status(self.t("status_rvc_delete_failed", name))
        self._active_row_key = None
        if self._popup is not None:
            self._render_rows(ensure_active=True)
