# -*- coding: utf-8 -*-
"""
engine/gui/rvc_model_dropdown.py — выпадающий список выбора RVC-модели.

Заменяет обычный CTkOptionMenu целиком: в одном списке вперемешку
локальные скачанные модели (с кнопкой 🗑 удаления) и модели из каталога,
ещё не скачанные (с кнопкой ⬇ скачивания / ✕ отмены / 🔗 открыть страницу).
Клик по строке — это одновременно и выбор модели, и подсветка строки;
кнопка действия у строки активна ТОЛЬКО когда строка выделена.

Источники remote-списка:
  - без поиска: seed/кэш через rvc_catalog.get_catalog()
    (json/rvc_catalog_seed.json — подборка с voice-models.com / HF)
  - с поиском (≥2 символа): rvc_catalog.search_catalog() =
    локальный seed + live voice-models.com

ФИКС (dropdown не открывался в модальном окне настроек):
  попап — tk.Frame + place() на toplevel окна настроек (grab-safe).
"""
import os
import threading
import time
import tkinter as tk

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
    def __init__(self, parent, variable, t,
                 on_status=None, on_progress=None, on_show_cancel=None, on_hide_cancel=None):
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
        self._downloading_key = None
        self._cancel_flag = None
        self._enabled = True

        self._top_win = None
        self._escape_bind_id = None
        self._ignore_outside_until = 0.0

        # Поиск
        self._search_query = ""
        self._search_results = None   # None = режим seed/каталог; list = результаты поиска
        self._search_token = 0        # инвалидация устаревших async-ответов
        self._search_pending = False
        self._search_after_id = None  # debounce after() id
        self._search_debounce_ms = 450

        self.trigger_btn = CompatCTkButton(
            parent, text=self._trigger_text(), command=self._toggle_popup,
            width=scaled_size(210, min_size=180), height=scaled_size(30, min_size=28),
            corner_radius=8, fg_color=Colors.BG_INPUT, text_color=Colors.TEXT_MAIN,
            hover_color=Colors.BG_HOVER, font=("Segoe UI", scaled_font_size(10)),
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
            # placeholder через fg dim, если пусто — рисуем hint label
            self._search_status_lbl = tk.Label(
                search_wrap,
                text=placeholder,
                bg=Colors.BG_INPUT,
                fg=Colors.TEXT_DIM,
                anchor="w",
                font=("Segoe UI", scaled_font_size(8)),
            )
            self._search_status_lbl.pack(fill="x", padx=8, pady=(0, 4))

            self._search_entry.bind("<KeyRelease>", self._on_search_key)
            self._search_entry.bind("<Return>", self._on_search_key)
            # Не закрывать попап при клике в поле поиска
            self._search_entry.bind("<Button-1>", lambda e: "break" if False else None)

            # ── Скроллируемая область строк ──
            # Canvas+Frame+Scrollbar: длинные результаты поиска (voice-models)
            # не раздувают окно и реально крутятся колёсиком/полосой.
            list_host = tk.Frame(outer, bg=Colors.BG_INPUT)
            list_host.pack(fill="both", expand=True)

            # Скроллбар справа — пакуем первым, чтобы не схлопнулся
            vsb = tk.Scrollbar(list_host, orient="vertical")
            vsb.pack(side="right", fill="y")

            canvas = tk.Canvas(
                list_host, bg=Colors.BG_INPUT, highlightthickness=0, bd=0,
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
            self._render_rows()

            popup.update_idletasks()
            # Выше попап — удобнее листать сетевой поиск
            h = scaled_size(340, min_size=280)
            max_h = scaled_size(420, min_size=320)
            h = min(h, max_h)

            if x + width > win_w:
                x = max(0, win_w - width)
            if x < 0:
                x = 0
            if y + h > win_h:
                y_up = (btn_ry - win_ry) - h
                if y_up >= 0:
                    y = y_up
                else:
                    h = max(scaled_size(200, min_size=160), win_h - y)
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
            self._set_search_status(
                self._tr("rvc_search_placeholder", default="Поиск (voice-models.com)…")
            )
            self._render_rows()
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
            self._set_search_status(f"Локально: {n_local} · ищу online…")
        else:
            self._set_search_status(
                self._tr("rvc_search_searching", default="Ищу на voice-models.com…")
            )
        self._render_rows()

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
                self.trigger_btn.after(
                    0, lambda: self._on_search_done(token, query, results)
                )
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
        self._render_rows()

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

    def _on_list_wheel(self, event):
        """Скролл списка результатов (в т.ч. сетевого поиска)."""
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
                # Windows/macOS: delta обычно ±120; ускоряем чуть сильнее для длинных списков
                steps = int(-1 * (event.delta / 120))
                if steps == 0:
                    steps = -1 if event.delta > 0 else 1
                canvas.yview_scroll(steps * 3, "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(3, "units")
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
                canvas.itemconfigure(
                    self._list_inner_id, width=max(int(canvas.winfo_width()), 1)
                )
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

    def _render_rows(self):
        if self._rows_container is None:
            return
        for w in self._rows_container.winfo_children():
            w.destroy()

        rvc_dir = os.path.join(rvc_catalog.BASE_DIR, "models", "rvc")
        try:
            local_names = sorted(
                f[:-4] for f in os.listdir(rvc_dir) if f.endswith(".pth")
            )
        except Exception:
            local_names = []

        # Remote: либо результаты поиска, либо seed/каталог
        if self._search_results is not None:
            catalog_entries = [
                e for e in self._search_results
                if not rvc_catalog.is_downloaded(e)
            ]
            section_title = self._tr(
                "rvc_search_section",
                default="Результаты поиска (voice-models.com)",
            )
        else:
            try:
                catalog_entries = [
                    e for e in rvc_catalog.get_catalog()
                    if not rvc_catalog.is_downloaded(e)
                ]
            except Exception:
                catalog_entries = []
            section_title = self._tr(
                "rvc_catalog_section",
                default="Доступно для скачивания",
            )

        self._row_frame(
            NONE_LABEL, key=("none", None), select_cb=self._select_none
        ).pack(fill="x")

        # Локальные всегда показываем (фильтр по поиску — по имени)
        q = (self._search_query or "").lower()
        shown_local = 0
        for name in local_names:
            if q and q not in name.lower():
                continue
            self._render_local_row(name)
            shown_local += 1

        if catalog_entries:
            tk.Label(
                self._rows_container,
                text=section_title,
                bg=Colors.BG_INPUT,
                fg=Colors.TEXT_DIM,
                anchor="w",
                font=("Segoe UI", scaled_font_size(8)),
            ).pack(fill="x", padx=8, pady=(6, 2))
            for entry in catalog_entries:
                self._render_remote_row(entry)

        if shown_local == 0 and not catalog_entries and not self._search_pending:
            empty = (
                self._tr("rvc_search_empty", default="Ничего не найдено")
                if self._search_results is not None
                else self._tr("rvc_list_empty", default="Список моделей пуст")
            )
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
        try:
            # сброс позиции при новом поиске — список с начала
            if getattr(self, "_list_canvas", None):
                self._list_canvas.yview_moveto(0)
        except Exception:
            pass
        self._refresh_list_scroll()
        try:
            # повтор после layout idle — иначе bbox("all") бывает 0 на Windows
            if self.trigger_btn:
                self.trigger_btn.after(10, self._refresh_list_scroll)
                self.trigger_btn.after(50, self._refresh_list_scroll)
        except Exception:
            pass

    def _row_frame(self, text, key, select_cb, action_btn=None):
        active = (self._active_row_key == key)
        row_bg = Colors.BG_HOVER if active else Colors.BG_INPUT
        row = tk.Frame(self._rows_container, bg=row_bg)

        lbl = tk.Label(
            row, text=text, anchor="w", bg=row_bg, fg=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(9)),
        )
        lbl.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=4)
        lbl.bind("<Button-1>", lambda e: select_cb())
        row.bind("<Button-1>", lambda e: select_cb())

        if action_btn is not None:
            action_btn(row).pack(side="right", padx=(4, 8), pady=4)

        return row

    def _render_local_row(self, name):
        key = ("local", name)

        def _select():
            self._active_row_key = key
            self.variable.set(name)
            # Остаёмся открытыми: после выделения активируется 🗑
            self._render_rows()

        def _btn(row):
            active = (self._active_row_key == key)
            return CompatCTkButton(
                row, text="🗑", command=lambda: self._delete_local(name),
                width=scaled_size(26, min_size=24), height=scaled_size(20, min_size=18),
                corner_radius=6, fg_color=Colors.BG_CARD, hover_color="#a3342e",
                text_color=Colors.TEXT_MAIN, font=("Segoe UI", scaled_font_size(9)),
                state="normal" if active else "disabled",
            )

        self._row_frame(name, key, _select, action_btn=_btn).pack(fill="x")

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
            self._render_rows()

        if self._downloading_key == key:
            def _btn(row):
                return CompatCTkButton(
                    row, text="✕", command=self._cancel_download,
                    width=scaled_size(26, min_size=24), height=scaled_size(20, min_size=18),
                    corner_radius=6, fg_color=Colors.BG_CARD, hover_color="#a3342e",
                    text_color=Colors.TEXT_MAIN, font=("Segoe UI", scaled_font_size(9)),
                    state="normal",
                )
        elif downloadable:
            def _btn(row):
                active = (self._active_row_key == key)
                return CompatCTkButton(
                    row, text="⬇", command=lambda: self._start_download(entry),
                    width=scaled_size(26, min_size=24), height=scaled_size(20, min_size=18),
                    corner_radius=6, fg_color=Colors.BG_CARD, hover_color=Colors.BG_HOVER,
                    text_color=Colors.TEXT_MAIN, font=("Segoe UI", scaled_font_size(9)),
                    state="normal" if active else "disabled",
                )
        else:
            # Нет прямой ссылки (GDrive folder / только страница) — открыть в браузере
            def _btn(row):
                active = (self._active_row_key == key)
                return CompatCTkButton(
                    row, text="🔗", command=lambda: self._open_page(entry),
                    width=scaled_size(26, min_size=24), height=scaled_size(20, min_size=18),
                    corner_radius=6, fg_color=Colors.BG_CARD, hover_color=Colors.BG_HOVER,
                    text_color=Colors.TEXT_MAIN, font=("Segoe UI", scaled_font_size(9)),
                    state="normal" if active else "disabled",
                )

        label = entry.get("name", entry["id"])
        if entry.get("size"):
            # короткий размер в конце, если влезает
            short = label if len(label) < 48 else (label[:45] + "…")
            label = f"{short}"
        row = self._row_frame(label, key, _select, action_btn=_btn)
        tip_parts = [
            entry.get("name"),
            subtitle,
            entry.get("size"),
            entry.get("description"),
            None if downloadable else self._tr(
                "rvc_open_in_browser_tip",
                default="Нет прямой ссылки — откроется страница модели",
            ),
        ]
        ToolTip(row, "\n".join(p for p in tip_parts if p))
        row.pack(fill="x")

    def _select_none(self):
        self._active_row_key = ("none", None)
        self.variable.set(NONE_LABEL)
        self._render_rows()

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
        self._render_rows()
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
            local_name = os.path.splitext(
                os.path.basename(rvc_catalog.local_model_path(entry))
            )[0]
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
                self.on_status(
                    self.t("status_rvc_download_failed", entry.get("name", ""))
                )
        if self._popup is not None:
            self._render_rows()

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
            self._render_rows()
