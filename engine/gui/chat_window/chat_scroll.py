from __future__ import annotations
import json
import os
import threading
import uuid
from datetime import datetime
from tkinter import filedialog, messagebox
import tkinter as tk

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


def _is_chat_near_bottom(threshold: float = 0.01) -> bool:
    if not _widget_exists(state.chat_canvas):
        return True
    try:
        _top, bottom = state.chat_canvas.yview()
        return bottom >= (1.0 - threshold)
    except Exception:
        return True


def _scroll_chat_to_bottom(immediate: bool = False):

    if not _widget_exists(state.chat_canvas):
        return

    if immediate:
        try:
            state.chat_canvas.update_idletasks()
            state.chat_canvas.configure(scrollregion=state.chat_canvas.bbox("all"))
            state.chat_canvas.yview_moveto(1.0)
        except Exception:
            pass
        return

    # Отменяем предыдущий запланированный скролл
    if state._scroll_debounce_id is not None:
        try:
            state._root.after_cancel(state._scroll_debounce_id)
        except Exception:
            pass
        state._scroll_debounce_id = None

    def _do_scroll():

        state._scroll_debounce_id = None
        if not _widget_exists(state.chat_canvas):
            return
        try:
            # This callback already runs after an 80 ms debounce, so Tk has
            # completed geometry processing. Avoid another synchronous flush.
            state.chat_canvas.configure(scrollregion=state.chat_canvas.bbox("all"))

            # PATCH 2026-07-14: плавный скролл вниз через AnimationManager
            try:
                from engine.gui.animation_manager import AnimationManager

                mgr = AnimationManager.get()
                current_top = state.chat_canvas.yview()[0]
                # Анимируем только если не на самом низу
                if current_top < 0.99:
                    mgr.animate(
                        target=state.chat_canvas,
                        property_setter=lambda v: state.chat_canvas.yview_moveto(v),
                        start=current_top,
                        end=1.0,
                        duration_ms=250,
                        easing="ease_out",
                        animation_id=f"scroll_bottom_{id(state.chat_canvas)}",
                    )
                else:
                    state.chat_canvas.yview_moveto(1.0)
            except Exception:
                # Fallback: мгновенный скролл если AnimationManager недоступен
                state.chat_canvas.yview_moveto(1.0)

        except Exception:
            pass

    state._scroll_debounce_id = _safe_after(80, _do_scroll)


def _show_new_message_indicator():

    if not _widget_exists(state.composer_outer_ref[0]):
        return

    if _widget_exists(state._new_message_btn):
        return  # уже показана

    state._new_message_btn = _make_button(
        state.composer_outer_ref[0],
        "\u2193 Новый ответ \u2014 нажмите, чтобы прокрутить",
        _scroll_to_new_message,
        bg=_c("ACCENT"),
        fg="#ffffff",
        font_size=9,
        height=1,
        padx=10,
        pady=5,
    )
    state._new_message_btn.pack(fill="x", pady=(0, 4), before=state.composer_card_ref[0])


def _hide_new_message_indicator():

    if _widget_exists(state._new_message_btn):
        try:
            state._new_message_btn.destroy()
        except Exception:
            pass
    state._new_message_btn = None


def _scroll_to_new_message():
    _hide_new_message_indicator()
    _scroll_chat_to_bottom(immediate=True)


def _get_scroll_animation_id(canvas) -> str:
    """Единый ID для smooth-scroll анимации указанного canvas."""
    return f"smooth_scroll_{id(canvas)}"


def _estimate_scroll_delta(canvas, units: int) -> float:
    """Преобразовать 'units' (строки) в дробь [0,1] для yview_moveto.

    Вычисляет реальную высоту контента и видимую область,
    чтобы пересчитать 'units' строк в корректную дельту прокрутки.
    """
    try:
        bbox = canvas.bbox("all")
        if not bbox:
            return units * 0.02
        total_h = float(max(1, bbox[3] - bbox[1]))
        view_h = float(max(1, canvas.winfo_height()))
        # Каждая "unit" ≈ одна строка текста (~пикселей)
        # Зная общую высоту в пикселях, считаем долю одной строки
        # Приблизительно: высота строки ≈ total_h / число элементов
        # Но проще: 1 строка ≈ 20px (типичная высота строки в чате)
        LINE_HEIGHT = 20.0
        fraction_per_unit = LINE_HEIGHT / total_h
        return units * fraction_per_unit
    except Exception:
        return units * 0.02


def _chat_mousewheel(event):
    if not _widget_exists(state.chat_canvas):
        return None

    try:
        pointer = (
            state._root.winfo_containing(event.x_root, event.y_root)
            if state._root is not None
            else None
        )
        if pointer is None:
            return None

        if not _is_descendant(pointer, state.chat_canvas):
            return None

        if getattr(event, "num", None) == 4:
            units = -9
        elif getattr(event, "num", None) == 5:
            units = 9
        else:
            delta = int(getattr(event, "delta", 0) or 0)
            if delta == 0:
                return None
            # Faster wheel response for long conversations.
            units = -9 if delta > 0 else 9

        # PATCH 2026-07-14: плавный скролл через AnimationManager
        try:
            from engine.gui.animation_manager import AnimationManager

            mgr = AnimationManager.get()

            # Если менеджер в no-op режиме (нет root) — fallback на прыжковый скролл
            if mgr._no_op:
                state.chat_canvas.yview_scroll(units, "units")
            else:
                current_top = state.chat_canvas.yview()[0]
                delta_frac = _estimate_scroll_delta(state.chat_canvas, units)
                target = max(0.0, min(1.0, current_top + delta_frac))

                anim_id = _get_scroll_animation_id(state.chat_canvas)
                # Отменяем предыдущую scroll-анимацию для этого canvas
                if mgr.is_running(anim_id):
                    mgr.cancel(anim_id)
                    # После отмены применяем конечное значение, чтобы
                    # не было "залипания" промежуточного состояния
                    state.chat_canvas.yview_moveto(current_top)

                mgr.animate(
                    target=state.chat_canvas,
                    property_setter=lambda v: state.chat_canvas.yview_moveto(v),
                    start=current_top,
                    end=target,
                    duration_ms=95,
                    easing="ease_out_cubic",
                    animation_id=anim_id,
                )

        except Exception:
            # Fallback: прыжковый скролл при любой ошибке
            state.chat_canvas.yview_scroll(units, "units")

        # Если пользователь докрутил до низа сам — убираем индикатор
        _safe_after(50, lambda: _hide_new_message_indicator() if _is_chat_near_bottom() else None)

        return "break"
    except Exception:
        return None


# Inter-module imports
from engine.gui.chat_window.services.utils import (
    _now_ts,
    _now_full,
    _approx_tokens,
    _ai_display_name,
    _build_editor_compose_prompt,
)
from engine.gui.chat_window.services.sessions import (
    _load_sessions,
    _save_sessions,
    _enforce_limits,
    _create_session_dict,
    _get_current_session,
    _update_session_title_if_needed,
    _messages_for_api,
)
from engine.gui.chat_window.services.generation import _run_generation
from engine.gui.chat_window.ui_utils import (
    _c,
    _safe_after,
    _widget_exists,
    _set_dark_titlebar,
    _get_app_parent,
    _show_window,
    _call_and_break,
    _ask_simple_text,
    _make_button,
    _set_button_text,
    _set_button_state,
    _is_descendant,
    _get_widget_text,
    _select_all_widget,
    _paste_clipboard_into_widget,
    _copy_to_clipboard,
)
from engine.gui.chat_window.hotkeys import (
    _event_has_ctrl,
    _event_has_shift,
    _match_hotkey,
    _on_ctrl_keypress,
    _handle_text_ctrl,
    _handle_window_ctrl,
    _bind_window_hotkeys,
    _bind_text_hotkeys,
)
from engine.gui.chat_window.placeholders import (
    _create_placeholder_overlay,
    _sync_text_placeholder,
    _refresh_placeholder_state,
    _update_input_placeholder_text,
)
from engine.gui.chat_window.chat_scroll import (
    _is_chat_near_bottom,
    _scroll_chat_to_bottom,
    _show_new_message_indicator,
    _hide_new_message_indicator,
    _scroll_to_new_message,
    _chat_mousewheel,
)
from engine.gui.chat_window.chat_history import (
    _refresh_session_list,
    _on_session_select,
    new_chat,
    delete_current_chat,
    clear_chat_history,
)
from engine.gui.chat_window.chat_messages import (
    _add_message_bubble,
    _add_system_message,
    _resize_bubble_text,
    content_lines_estimate,
    _lighten_color,
    _selected_bubble_frame_get,
    _select_bubble,
    _on_bubble_text_click,
    _show_bubble_context_menu,
    _update_wraplengths,
    _render_current_session,
    _add_empty_state,
    _destroy_empty_state_if_any,
    _clear_messages_ui,
)
from engine.gui.chat_window.chat_input import (
    _focus_chat_input,
    _reset_editor_mode,
    _input_has_placeholder,
    _set_input_placeholder,
    _clear_input_placeholder,
    _get_input_text,
    _clear_input_text,
    _resize_input,
    _update_token_counter,
    _paste_into_input,
    _on_input_focus_in,
    _on_input_focus_out,
    _on_input_key_release,
    _on_enter,
    _submit_prompt,
    send_chat_message,
    _insert_prompt_into_chat_input,
)
from engine.gui.chat_window.chat_typing import _show_typing, _animate_typing, _hide_typing
from engine.gui.chat_window.chat_actions import (
    _send_to_main_editor,
    _stop_generation,
    _set_generation_ui,
    improve_text_with_gpt,
    paste_from_editor,
    set_chat_status,
    append_chat_message,
)
from engine.gui.chat_window.chat_export import export_current_chat
from engine.gui.chat_window.chat_search import open_search
from engine.gui.chat_window.chat_settings import open_gpt_settings
from engine.gui.chat_window.chat_editor import (
    _show_editor_preview,
    _hide_editor_preview,
    open_editor_text_window,
    _get_selected_or_all_text,
    _show_editor_window,
)
from engine.gui.chat_window import init, open_chat_window
