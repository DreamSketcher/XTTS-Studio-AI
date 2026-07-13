# -*- coding: utf-8 -*-
"""engine/gui/toolbar.py — тулбар главного окна: группы Файл / AI / Вывод /
Действия, кнопка ГЕНЕРИРОВАТЬ и её состояние
(перенесено из gui.py: секция TOOLBAR, _make_group, _tb_button,
on_gen_btn_click, update_gen_btn, update_quality_buttons, studio_click,
studio_double + создание кнопок chat_btn / ai_btn / styles_btn / studio_btn /
gen_btn).

PATCH 2026-07-09: добавлен порядок панелей тулбара (toolbar_order),
live-применение порядка.
"""
import tkinter as tk

import customtkinter as ctk

from i18n import t

from engine.settings_store import load_settings
from engine.gui.colors import Colors, scaled_font_size
from engine.gui.tooltip import ToolTip
from engine.gui.widgets import CompatCTkFrame, CompatCTkLabel, CompatCTkButton, create_button
from engine.gui.neon_widgets import create_neon_button
from engine.gui import (
    textbox,
    dialogs,
    presets,
    styles_menu,
    ai_conductor,
    chat_panel,
    word_replacer_panel,
    history_window,
    output_window,
    generation,
)

# Внедряются из main_window: root, quality_var, lang_var, save_settings
root = None
quality_var = None
lang_var = None
save_settings = None

# Виджеты (создаются в build_toolbar)
toolbar_frame = None
toolbar_frame2 = None
file_grp = file_inner = None
ai_grp = ai_inner = None
output_grp = output_inner = None
action_grp = action_inner = None
chat_btn = None
ai_btn = None
lang_btn = None
dict_btn = None
styles_btn = None
studio_btn = None
gen_btn = None

# Функции, определяемые при построении тулбара (используются извне)
update_quality_buttons = None
update_gen_btn = None

# текущее состояние порядка
_current_toolbar_order = []
_current_toolbar_rows = 2


def init(**deps):
    """Внедрение зависимостей из engine.gui.main_window."""
    globals().update(deps)


def _get_toolbar_order():
    try:
        from engine.gui import theme_manager as tm

        return tm.get_toolbar_order()
    except Exception:
        return ["file", "output", "ai", "action"]


def _get_toolbar_rows():
    try:
        from engine.gui import theme_manager as tm

        preset = tm.get_layout_preset()
        rows = int(preset.get("toolbar_rows", 2))
        return 1 if rows < 1 else 2 if rows > 2 else rows
    except Exception:
        return 2


def build_toolbar(text_card):
    global toolbar_frame, toolbar_frame2
    global file_grp, file_inner, ai_grp, ai_inner
    global output_grp, output_inner, action_grp, action_inner
    global chat_btn, ai_btn, lang_btn, dict_btn, styles_btn, studio_btn, gen_btn
    global update_quality_buttons, update_gen_btn
    global _current_toolbar_order, _current_toolbar_rows

    # Определяем порядок панелей и число рядов
    order = _get_toolbar_order()
    toolbar_rows = _get_toolbar_rows()
    _current_toolbar_order = order.copy()
    _current_toolbar_rows = toolbar_rows

    # Ряды тулбара пакуются side="bottom" (нижний ряд первым),
    # text_box перепаковывается ПОСЛЕДНИМ
    row_frames = []
    toolbar_frame2 = None
    toolbar_frame = None
    if toolbar_rows >= 2:
        toolbar_frame2 = CompatCTkFrame(text_card, fg_color=Colors.BG_CARD, corner_radius=0)
        toolbar_frame2.pack(side="bottom", fill="x", padx=10, pady=(0, 7))
        row_frames.append(toolbar_frame2)  # будет нижний, но пока временно
    # верхний (или единственный) ряд
    toolbar_frame = CompatCTkFrame(text_card, fg_color=Colors.BG_CARD, corner_radius=0)
    bottom_pad = 4 if toolbar_rows >= 2 else 7
    toolbar_frame.pack(side="bottom", fill="x", padx=10, pady=(0, bottom_pad))

    # упорядочим row_frames сверху вниз
    if toolbar_rows >= 2:
        row_frames = [toolbar_frame, toolbar_frame2]
    else:
        row_frames = [toolbar_frame]
        toolbar_frame2 = toolbar_frame  # для совместимости

    try:
        textbox.text_box.pack_forget()
        textbox.text_box.pack(fill="both", expand=True, padx=10, pady=7)
    except Exception:
        pass

    # Uniform icon size / padding constants
    _TB_FONT_SIZE = 11
    _TB_PAD_X = 4
    _TB_GROUP_PAD = 8

    # ── Helper: group container ──
    def _make_group(parent, label_text, bg_color=Colors.GROUP_BG):
        grp = CompatCTkFrame(
            parent, fg_color=bg_color, corner_radius=8, border_width=1, border_color=Colors.BORDER
        )
        CompatCTkLabel(
            grp,
            text=label_text,
            fg=Colors.TEXT_DIM,
            bg=bg_color,
            font=ctk.CTkFont(family="Segoe UI", size=scaled_font_size(10)),
            anchor="w",
        ).pack(fill="x", padx=6, pady=(3, 0))
        inner = CompatCTkFrame(grp, fg_color=bg_color, corner_radius=0)
        inner.pack(fill="x", padx=4, pady=(0, 4))
        return grp, inner

    def _tb_button(
        parent,
        text,
        command,
        bg=Colors.BG_INPUT,
        fg=Colors.TEXT_MAIN,
        hover=Colors.BG_HOVER,
        font_size=_TB_FONT_SIZE,
    ):
        btn = create_button(
            parent, text, command, bg=bg, fg=fg, active_bg=hover, font_size=font_size
        )
        btn.configure(width=0)
        return btn

    # ── Строители групп ──
    def build_file_group(parent):
        global file_grp, file_inner
        file_grp, file_inner = _make_group(parent, t("group_file"), Colors.GROUP_FILE_BG)
        for _c in range(3):
            file_inner.grid_columnconfigure(_c, weight=1)
        _tb_button(file_inner, t("btn_load"), textbox.load_txt).grid(
            row=0, column=0, sticky="ew", padx=(_TB_PAD_X, _TB_PAD_X)
        )
        _tb_button(file_inner, t("btn_paste"), textbox.paste_clipboard).grid(
            row=0, column=1, sticky="ew", padx=(0, _TB_PAD_X)
        )
        _tb_button(file_inner, t("btn_clear"), lambda: [textbox.set_textbox_content("")]).grid(
            row=0, column=2, sticky="ew", padx=(0, _TB_PAD_X)
        )
        return file_grp

    def build_ai_group(parent):
        global ai_grp, ai_inner, chat_btn, ai_btn
        ai_grp, ai_inner = _make_group(parent, t("group_ai"), Colors.AI_GROUP_BG)
        for _c in range(2):
            ai_inner.grid_columnconfigure(_c, weight=1)
        chat_btn = create_neon_button(
            ai_inner,
            t("btn_ai_assistant"),
            chat_panel.toggle_chat_panel,
            font_size=_TB_FONT_SIZE,
            height=28,
            bg=Colors.AI_GROUP_BG,
            fg=Colors.AI_ACCENT,
            button_id="chat",
        )
        chat_btn.grid(row=0, column=0, sticky="ew", padx=(_TB_PAD_X, _TB_PAD_X))
        ToolTip(chat_btn, t("tip_ai_assistant"))
        _ai_s = load_settings()
        _ai_active = _ai_s.get("ai_conductor_enabled", False)
        ai_btn = create_neon_button(
            ai_inner,
            t("btn_ai_conductor"),
            ai_conductor.open_ai_conductor_window,
            font_size=_TB_FONT_SIZE,
            height=28,
            bg=Colors.AI_GROUP_BG,
            fg=Colors.AI_ACCENT if _ai_active else Colors.TEXT_DIM,
            button_id="ai",
        )
        ai_btn.grid(row=0, column=1, sticky="ew", padx=(0, _TB_PAD_X))
        ToolTip(ai_btn, t("tip_ai_conductor"))
        return ai_grp

    def build_output_group(parent):
        global output_grp, output_inner, lang_btn, dict_btn, styles_btn, studio_btn, update_quality_buttons
        output_grp, output_inner = _make_group(parent, t("group_output"), Colors.GROUP_OUTPUT_BG)
        # Крайние кнопки шире: «Язык генерации» слева, «Высокое качество» справа до края панели
        output_inner.grid_columnconfigure(0, weight=3, minsize=150)  # Язык генерации
        output_inner.grid_columnconfigure(1, weight=2, minsize=100)  # Словарь
        output_inner.grid_columnconfigure(2, weight=2, minsize=100)  # Стили
        output_inner.grid_columnconfigure(3, weight=8, minsize=160)  # Высокое качество
        lang_btn = _tb_button(output_inner, t("btn_language"), dialogs.pick_language)
        # padx слева 0 — кнопка до левого края inner-панели
        lang_btn.grid(row=0, column=0, sticky="nsew", padx=(0, _TB_PAD_X))
        try:
            lang_btn.configure(anchor="center")
        except Exception:
            pass
        ToolTip(lang_btn, lambda: t("tip_language", lang_var.get()))
        dict_btn = _tb_button(
            output_inner, t("btn_dictionary"), word_replacer_panel.open_word_replacer
        )
        dict_btn.grid(row=0, column=1, sticky="nsew", padx=(0, _TB_PAD_X))
        try:
            dict_btn.configure(anchor="center")
        except Exception:
            pass
        ToolTip(dict_btn, t("tip_dictionary"))
        styles_btn = create_neon_button(
            output_inner,
            t("btn_styles"),
            styles_menu.open_styles_menu,
            font_size=_TB_FONT_SIZE,
            height=28,
            bg=Colors.BG_INPUT,
            fg=Colors.AI_ACCENT,
            button_id="styles",
        )
        styles_btn.grid(row=0, column=2, sticky="nsew", padx=(0, _TB_PAD_X))
        try:
            styles_btn.configure(anchor="center")
        except Exception:
            pass
        ToolTip(styles_btn, styles_menu.STYLES_HINT)

        def studio_click():
            quality_var.set("Высокое качество")
            save_settings()

        def studio_double(e):
            quality_var.set("Высокое качество")
            save_settings()
            presets.open_quality_settings("Высокое качество")

        studio_btn = create_neon_button(
            output_inner,
            t("btn_quality_default"),
            studio_click,
            font_size=_TB_FONT_SIZE,
            height=32,
            bg=Colors.BG_INPUT,
            fg=Colors.AI_ACCENT,
            button_id="quality",
        )
        # padx справа 0 — кнопка до правого края панели «Вывод»
        studio_btn.grid(row=0, column=3, sticky="nsew", padx=(_TB_PAD_X, 0))
        try:
            studio_btn.configure(anchor="center")
        except Exception:
            pass
        try:
            studio_btn.bind("<Double-Button-1>", studio_double)
        except Exception:
            pass
        ToolTip(studio_btn, styles_menu.PRESET_HINT)

        def update_quality_buttons(*args):
            q = quality_var.get()
            if q == "Высокое качество":
                try:
                    studio_btn.configure(fg_color=Colors.BG_HOVER, text_color=Colors.AI_ACCENT)
                except Exception:
                    pass
                try:
                    if getattr(studio_btn, "_neon_pulse", None):
                        studio_btn._neon_pulse.base = Colors.AI_ACCENT
                except Exception:
                    pass
                try:
                    styles_btn.configure(text=t("btn_styles"))
                except Exception:
                    try:
                        styles_btn.config(text=t("btn_styles"))
                    except Exception:
                        pass
            else:
                try:
                    studio_btn.configure(fg_color=Colors.BG_INPUT, text_color=Colors.TEXT_DIM)
                except Exception:
                    pass
                try:
                    if getattr(studio_btn, "_neon_pulse", None):
                        studio_btn._neon_pulse.base = Colors.TEXT_DIM
                except Exception:
                    pass
                emoji = {"Нарратив": "📖", "Динамика": "⚡", "Экспрессия": "🎭"}.get(q, "🎨")
                try:
                    styles_btn.configure(text=f"{emoji} {q} ▾")
                except Exception:
                    try:
                        styles_btn.config(text=f"{emoji} {q} ▾")
                    except Exception:
                        pass

        quality_var.trace_add("write", update_quality_buttons)
        update_quality_buttons()
        globals()["update_quality_buttons"] = update_quality_buttons
        return output_grp

    def build_action_group(parent):
        global action_grp, action_inner, gen_btn, update_gen_btn
        action_grp, action_inner = _make_group(parent, t("group_action"), Colors.GROUP_ACTION_BG)

        def on_gen_btn_click():
            if generation.current_task is not None:
                generation.cancel_task()
            else:
                generation.generate()

        action_inner.grid_columnconfigure(0, weight=1)
        action_inner.grid_columnconfigure(1, weight=1)
        action_inner.grid_columnconfigure(2, weight=3)
        _tb_button(action_inner, t("btn_history"), history_window.open_history).grid(
            row=0, column=0, sticky="ew", padx=(_TB_PAD_X, _TB_PAD_X)
        )
        _tb_button(action_inner, t("btn_audio"), output_window.open_outputs_folder).grid(
            row=0, column=1, sticky="ew", padx=(0, _TB_PAD_X)
        )
        gen_btn = create_neon_button(
            action_inner,
            t("btn_generate"),
            on_gen_btn_click,
            font_size=13,
            height=42,
            bg=Colors.BG_ACTIVE,
            fg="#b8f2c0",
            button_id="generate",
        )
        gen_btn.grid(row=0, column=2, sticky="nsew", padx=(_TB_PAD_X, 0))

        def update_gen_btn(is_running: bool):
            try:
                if is_running:
                    gen_btn.configure(
                        text=t("btn_cancel"),
                        fg_color=Colors.BG_DANGER,
                        hover_color="#c0312e",
                        text_color="#ffffff",
                    )
                else:
                    gen_btn.configure(
                        text=t("btn_generate"),
                        fg_color=Colors.BG_ACTIVE,
                        hover_color=Colors.BG_HOVER,
                        text_color="#b8f2c0",
                    )
            except Exception:
                pass

        globals()["update_gen_btn"] = update_gen_btn
        return action_grp

    builders = {
        "file": build_file_group,
        "ai": build_ai_group,
        "output": build_output_group,
        "action": build_action_group,
    }

    # Распределяем панели по рядам согласно порядку
    # groups_per_row = ceil(len(order)/rows)
    n = len(order)
    per_row = (n + toolbar_rows - 1) // toolbar_rows if toolbar_rows > 0 else n
    idx = 0
    # сбрасываем глобальные ссылки
    file_grp = ai_grp = output_grp = action_grp = None

    for row_i, row_frame in enumerate(row_frames):
        # сколько групп в этом ряду
        remaining = n - idx
        rows_left = toolbar_rows - row_i
        take = (remaining + rows_left - 1) // rows_left if rows_left > 0 else remaining
        for j in range(take):
            if idx >= n:
                break
            panel_id = order[idx]
            builder = builders.get(panel_id)
            if builder:
                grp = builder(row_frame)
                # pack: первые слева, последний справа растягивается?
                # Упрощённо: все pack left, кроме action — right expand
                # Все слева→направо. Минимальный зазор между панелями (2px),
                # чтобы «Вывод»/«Действие» почти вплотную к «Файл»/«AI».
                gap = 3 if j > 0 else 0
                if panel_id in ("output", "action"):
                    grp.pack(side="left", fill="both", expand=True, padx=(gap, 0))
                else:
                    # file / ai — ширина по кнопкам (см. _sync_left_column)
                    grp.pack(side="left", fill="y", expand=False, padx=(gap, 0))
            idx += 1

    # ── связываем созданные кнопки ──
    try:
        ai_conductor.ai_btn = ai_btn
        styles_menu.styles_btn = styles_btn
        from engine.gui import settings_ui as _settings_ui

        _settings_ui.ai_btn = ai_btn
    except Exception:
        pass

    # ── выравнивание левой колонки ──
    _left_base = {"l_req": None, "ratio": None, "h_file": None, "h_ai": None}

    def _sync_left_column(_e=None):
        try:
            # найти левые группы (file/ai) — они могут быть в разных рядах
            left_widgets = []
            if file_grp is not None:
                left_widgets.append(file_grp)
            if ai_grp is not None:
                left_widgets.append(ai_grp)
            if not left_widgets:
                return
            # правые группы
            right_widgets = []
            if output_grp is not None:
                right_widgets.append(output_grp)
            if action_grp is not None:
                right_widgets.append(action_grp)
            if _left_base["l_req"] is None:
                for w in left_widgets + right_widgets:
                    w.update_idletasks()
                l_req = max((w.winfo_reqwidth() for w in left_widgets), default=100)
                r_req = max((w.winfo_reqwidth() for w in right_widgets), default=200)
                if l_req <= 1 or r_req <= 1:
                    return
                _left_base["l_req"] = l_req
                _left_base["ratio"] = l_req / float(l_req + r_req)
                # сохраняем высоты
                if file_grp:
                    _left_base["h_file"] = file_grp.winfo_reqheight()
                if ai_grp:
                    _left_base["h_ai"] = ai_grp.winfo_reqheight()
            l_req = _left_base["l_req"]
            # Файл/AI — только ширина по кнопкам (не раздувать с окном).
            # Иначе слева появляется «пустой хвост», а «Вывод»/«Действие»
            # визуально отъезжают вправо (дыра по центру на скрине).
            # Правый край «Вывод»/«Действие» (side=right expand) не трогаем —
            # они сами забирают освободившееся место СЛЕВА, зазор = _TB_GROUP_PAD.
            # Файл и AI — одинаковая ширина (max req), чтобы колонки совпали
            # по вертикали. Не раздуваем от ширины окна — только контент.
            if file_grp is not None:
                try:
                    file_grp.pack_propagate(True)
                    file_grp.update_idletasks()
                except Exception:
                    pass
            if ai_grp is not None:
                try:
                    ai_grp.pack_propagate(True)
                    ai_grp.update_idletasks()
                except Exception:
                    pass
            fw = fh = aw = ah = 0
            if file_grp is not None:
                try:
                    fw = max(1, int(file_grp.winfo_reqwidth()))
                    fh = max(1, int(file_grp.winfo_reqheight() or _left_base.get("h_file") or 1))
                except Exception:
                    fw, fh = int(_left_base.get("l_req") or 120), int(
                        _left_base.get("h_file") or 40
                    )
            if ai_grp is not None:
                try:
                    aw = max(1, int(ai_grp.winfo_reqwidth()))
                    ah = max(1, int(ai_grp.winfo_reqheight() or _left_base.get("h_ai") or 1))
                except Exception:
                    aw, ah = int(_left_base.get("l_req") or 120), int(_left_base.get("h_ai") or 40)
            left_w = max(fw, aw, int(_left_base.get("l_req") or 1), 1)
            if file_grp is not None:
                try:
                    file_grp.configure(width=left_w, height=fh or ah or 40)
                    file_grp.pack_propagate(False)
                except Exception:
                    pass
            if ai_grp is not None:
                try:
                    ai_grp.configure(width=left_w, height=ah or fh or 40)
                    ai_grp.pack_propagate(False)
                except Exception:
                    pass
            # Правая колонка: Вывод и Действие — одинаковая ширина (остаток ряда)
            try:
                if row_frames:
                    rf = row_frames[0]
                    rf.update_idletasks()
                    avail = int(rf.winfo_width() or 0)
                    if avail <= 1:
                        avail = int(rf.winfo_reqwidth() or 0)
                    gap = 3
                    right_w = max(200, avail - int(left_w) - gap)
                    for g in (output_grp, action_grp):
                        if g is None:
                            continue
                        try:
                            g.update_idletasks()
                            gh = max(1, int(g.winfo_reqheight()))
                            g.configure(width=right_w, height=gh)
                            g.pack_propagate(False)
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            pass

    _sync_left_column()
    try:
        text_card.after(150, _sync_left_column)
        if row_frames:
            row_frames[0].bind("<Configure>", _sync_left_column, add="+")
    except Exception:
        pass


# ── Live-apply порядка ──
def apply_toolbar_order(order: list | None = None) -> bool:
    """Перестраивает тулбар согласно новому порядку.
    Возвращает True если требуется пересборка (нужен перезапуск)."""
    global _current_toolbar_order
    if order is None:
        order = _get_toolbar_order()
    # Проверяем валидность
    try:
        from engine.gui import theme_manager as tm

        valid = tm.get_toolbar_order()
        # если переданный order отличается от сохранённого — используем переданный
        if isinstance(order, (list, tuple)):
            # нормализуем
            clean = []
            seen = set()
            for x in order:
                if x in tm.TOOLBAR_PANELS and x not in seen:
                    clean.append(x)
                    seen.add(x)
            for x in tm.DEFAULT_TOOLBAR_ORDER:
                if x not in seen:
                    clean.append(x)
            order = clean
        else:
            order = valid
    except Exception:
        pass
    _current_toolbar_order = order.copy() if isinstance(order, list) else []
    # Полная пересборка требует destroy/create — делаем упрощённо:
    # сообщаем вызывающему, что нужен перезапуск / пересборка
    # Но попробуем live: просто перепаковать существующие группы
    try:
        # Определяем ряды
        rows = _get_toolbar_rows()
        row_frames = []
        if toolbar_frame is not None:
            row_frames.append(toolbar_frame)
        if toolbar_frame2 is not None and toolbar_frame2 is not toolbar_frame:
            row_frames.append(toolbar_frame2)
        if not row_frames:
            return False
        # Снимаем все группы
        grp_map = {
            "file": file_grp,
            "ai": ai_grp,
            "output": output_grp,
            "action": action_grp,
        }
        for g in grp_map.values():
            if g is not None:
                try:
                    g.pack_forget()
                except Exception:
                    pass
        # Распределяем заново
        n = len(order)
        per_row = (n + rows - 1) // rows if rows > 0 else n
        idx = 0
        _TB_GROUP_PAD = 8
        for row_i, row_frame in enumerate(row_frames):
            if idx >= n:
                break
            remaining = n - idx
            rows_left = rows - row_i
            take = (remaining + rows_left - 1) // rows_left if rows_left > 0 else remaining
            for j in range(take):
                if idx >= n:
                    break
                pid = order[idx]
                grp = grp_map.get(pid)
                if grp is None:
                    idx += 1
                    continue
                # сменить master нельзя — если группа была создана в другом row_frame,
                # pack в новый parent не сработает корректно.
                # Поэтому: если master не совпадает — пропускаем live, требуем перезапуск
                try:
                    if str(grp.master) != str(row_frame):
                        return True  # нужен перезапуск
                except Exception:
                    pass
                gap = 3 if j > 0 else 0
                if pid in ("output", "action"):
                    grp.pack(side="left", fill="both", expand=True, padx=(gap, 0))
                else:
                    grp.pack(side="left", fill="y", expand=False, padx=(gap, 0))
                idx += 1
        return True
    except Exception:
        return False


def apply_layout(preset: dict) -> bool:
    """Совместимость с main_window.apply_layout_preset_to_all"""
    # toolbar_rows может измениться — сообщаем что нужен перезапуск
    try:
        new_rows = int(preset.get("toolbar_rows", 2))
        if new_rows != _current_toolbar_rows:
            return False
    except Exception:
        pass
    return True
