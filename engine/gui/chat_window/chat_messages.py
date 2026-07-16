from __future__ import annotations
import tkinter as tk
import engine.gui.chat_window.state as state

_CHAT_INITIAL_CHARS = 8000
_CHAT_PAGE_CHARS = 8000
_CHAT_MEASURE_MAX_LINES = 40
_CHAT_MEASURE_MAX_CHARS_PER_LINE = 800
_session_render_token = 0
_session_render_after_id = None
_SESSION_RENDER_BATCH = 6
_SESSION_VISIBLE_WINDOW = 40
_session_visible_counts = {}
_session_scroll_top_once = set()
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

try:
    from engine.gui.colors import Colors, scaled_font_size
except Exception:

    def scaled_font_size(x):
        return x

    Colors = None


def _bubble_max_width_px() -> int:
    """Макс. ширина пузыря в px: ~62% canvas, clamp 220..640."""
    try:
        if _widget_exists(state.chat_canvas):
            w = int(state.chat_canvas.winfo_width() or 0)
            if w >= 80:
                return max(220, min(640, int(w * 0.62)))
    except Exception:
        pass
    return 420


def _tk_font(font_spec):
    """tkinter.font.Font из tuple/str."""
    import tkinter.font as tkfont

    try:
        if isinstance(font_spec, (tuple, list)):
            fam = font_spec[0] if len(font_spec) > 0 else "Segoe UI"
            sz = int(font_spec[1]) if len(font_spec) > 1 else 11
            weight = (
                "bold" if (len(font_spec) > 2 and "bold" in str(font_spec[2]).lower()) else "normal"
            )
            return tkfont.Font(family=fam, size=sz, weight=weight)
        return tkfont.Font(font=font_spec)
    except Exception:
        return tkfont.Font(family="Segoe UI", size=11)


def _measure_text_px(text: str, font_spec) -> int:
    """Ширина самой длинной строки текста в px (без wrap)."""
    f = _tk_font(font_spec)
    if not text:
        return 0
    widest = 0
    # Width saturates at max_w later; measuring megabyte-long lines or every
    # line is wasted Tcl work. A bounded sample is enough to select bubble width.
    lines = str(text).splitlines() or [""]
    for line in lines[:_CHAT_MEASURE_MAX_LINES]:
        sample = line[:_CHAT_MEASURE_MAX_CHARS_PER_LINE]
        try:
            widest = max(widest, int(f.measure(sample)))
        except Exception:
            widest = max(
                widest, len(sample) * max(6, int(getattr(f, "cget", lambda k: 11)("size") or 11))
            )
    return widest


def _chars_for_width(px: int, font_pt: int) -> int:
    """Оценка Text.width (в символах) по пикселям."""
    avg = max(5.5, float(font_pt) * 0.55)
    return max(8, min(100, int(px / avg)))


def _estimate_display_lines(content: str, chars_per_line: int) -> int:
    width = max(8, int(chars_per_line))
    total = 0
    for line in str(content or "").splitlines() or [""]:
        total += max(1, (len(line) + width - 1) // width)
        if total >= 80:
            return 80
    return max(1, total)


def _bubble_needed_width_px(content: str, meta_text: str, font_body, font_meta, max_w: int) -> int:
    """Ширина пузыря = max(текст, meta+кнопки), clamp [min_w, max_w].

    Короткий «привет» → узкий пузырь; длинный абзац → до max_w с word-wrap.
    """
    pad = 40  # внутренние padx Text + frame
    body_w = _measure_text_px(content, font_body) + pad
    # meta + кнопки → / copy
    meta_w = _measure_text_px(meta_text, font_meta) + 72 + pad
    needed = max(body_w, meta_w, 96)
    return max(96, min(int(max_w), int(needed)))


def _add_message_bubble(message: dict, smooth_scroll: bool = True, force_scroll: bool = False):
    if not _widget_exists(state.chat_messages_frame):
        return

    role = message.get("role", "assistant")
    content = str(message.get("content", "") or "")
    displayed_content = content[:_CHAT_INITIAL_CHARS]
    is_truncated = len(displayed_content) < len(content)
    ts = message.get("ts", _now_ts())
    tokens = _approx_tokens(content)

    _destroy_empty_state_if_any()
    _was_near_bottom = _is_chat_near_bottom()

    if role == "system":
        _add_system_message(content, ts)
        if smooth_scroll and (_is_chat_near_bottom() or force_scroll):
            _scroll_chat_to_bottom(immediate=force_scroll)
        return

    is_user = role == "user"

    row = TkFrame(state.chat_messages_frame, bg=_c("BG_DARK"))
    row._is_message_row = True
    row.pack(fill="x", padx=14, pady=8)

    # Текст в пузырях: body 13 design pt (читаемо), meta чуть меньше
    _font_body = ("Segoe UI", scaled_font_size(13))
    _font_meta = ("Segoe UI", scaled_font_size(10))
    _font_btn = ("Segoe UI", scaled_font_size(11))
    _font_avatar = ("Segoe UI Emoji", scaled_font_size(18))

    avatar_text = "🧑" if is_user else "🤖"
    avatar = TkLabel(
        row,
        text=avatar_text,
        bg=_c("BG_DARK"),
        fg=_c("TEXT_MAIN"),
        font=_font_avatar,
        width=2,
    )

    bubble_bg = _c("ACCENT") if is_user else _c("BG_CARD")
    bubble_fg = "#ffffff" if is_user else _c("TEXT_MAIN")
    bubble_hover = _lighten_color(bubble_bg, 0.10)

    # Ширина по содержимому (не на весь max) — короткий «привет» узкий, длинный текст до max.
    max_bubble_w = _bubble_max_width_px()
    author = t("chat_author_you") if is_user else _ai_display_name()
    meta_text = t("chat_meta_format", author, ts, tokens)
    bubble_w = _bubble_needed_width_px(
        displayed_content, meta_text, _font_body, _font_meta, max_bubble_w
    )

    bubble = None
    inner_bg = bubble_bg
    try:
        bubble = CTkFrame(
            row,
            fg_color=bubble_bg,
            corner_radius=16,
            border_width=1,
            border_color=_c("BORDER") if not is_user else bubble_bg,
            width=bubble_w,
        )
        # propagate True: высота по children; width= — запрошенная ширина CTk
        bubble.pack_propagate(True)
    except Exception:
        bubble = tk.Frame(
            row,
            bg=bubble_bg,
            highlightthickness=1,
            highlightbackground=_c("BORDER") if not is_user else bubble_bg,
            width=bubble_w,
        )
        # для tk.Frame фиксируем ширину, высоту — по содержимому
        bubble.pack_propagate(True)
        inner_bg = bubble_bg

    meta = tk.Frame(bubble, bg=inner_bg)
    meta.pack(fill="x", padx=10, pady=(6, 2))

    meta_fg = "#dbeafe" if is_user else _c("TEXT_DIM")

    tk.Label(
        meta,
        text=meta_text,
        bg=inner_bg,
        fg=meta_fg,
        font=_font_meta,
        anchor="w",
    ).pack(side="left")

    btn_box = tk.Frame(meta, bg=inner_bg)
    btn_box.pack(side="right")

    def _send_selected_or_full(lbl=None):
        if lbl is not None and _widget_exists(lbl):
            try:
                sel = lbl.get("sel.first", "sel.last").strip()
                if sel:
                    _send_to_main_editor(sel)
                    return
            except Exception:
                pass
        _send_to_main_editor(content)

    to_editor_btn = tk.Button(
        btn_box,
        text="→",
        command=lambda: _send_selected_or_full(text_label),
        bg=inner_bg,
        fg=meta_fg,
        activebackground=bubble_hover,
        activeforeground=_c("TEXT_MAIN"),
        relief="flat",
        bd=0,
        cursor="hand2",
        font=(_font_btn[0], _font_btn[1], "bold"),
        width=3,
        padx=2,
        pady=0,
    )
    to_editor_btn.pack(side="right", padx=(4, 0))

    copy_btn = tk.Button(
        btn_box,
        text="",
        command=lambda t=content: _copy_to_clipboard(t),
        bg=inner_bg,
        fg=meta_fg,
        activebackground=bubble_hover,
        activeforeground=_c("TEXT_MAIN"),
        relief="flat",
        bd=0,
        cursor="hand2",
        font=_font_btn,
        width=5,
        padx=2,
        pady=0,
    )
    copy_btn.pack(side="right")

    # Text.width в символах — по фактической ширине пузыря (не max)
    _char_w = _chars_for_width(bubble_w - 32, _font_body[1])
    text_label = tk.Text(
        bubble,
        bg=inner_bg,
        fg=bubble_fg,
        font=_font_body,
        relief="flat",
        highlightthickness=0,
        bd=0,
        wrap="word",
        width=_char_w,
        height=1,
        padx=10,
        pady=3,
        cursor="arrow",
        takefocus=0,
    )
    text_label.insert("1.0", displayed_content)
    text_label.bind("<Key>", lambda e: "break")
    text_label.bind("<<Paste>>", lambda e: "break")
    text_label.bind("<<Cut>>", lambda e: "break")
    text_label.bind("<Button-2>", lambda e: "break")
    text_label.bind("<Button-1>", lambda e: _on_bubble_text_click(e))
    text_label.bind("<B1-Motion>", lambda e: "ignore_disabled_drag" or None)

    # Route wheel events from Text directly to the chat Canvas. Returning
    # "break" only after scrolling prevents Text from swallowing the wheel.
    text_label.bind("<MouseWheel>", _chat_mousewheel)
    text_label.bind("<Button-4>", _chat_mousewheel)
    text_label.bind("<Button-5>", _chat_mousewheel)

    # fill=x только внутри УЖЕ content-sized bubble — не раздувает row
    text_label.pack(fill="x", padx=4, pady=(0, 6))
    text_label._bubble_content = displayed_content
    text_label._bubble_full_content = content
    text_label._bubble_displayed_chars = len(displayed_content)
    text_label._bubble_bg = inner_bg
    text_label._bubble_max_w = max_bubble_w
    text_label._bubble_w = bubble_w
    text_label._bubble_frame = bubble
    text_label._font_body = _font_body
    text_label._font_meta = _font_meta
    text_label._meta_text = meta_text

    more_btn = None
    if is_truncated:
        more_btn = tk.Button(
            bubble,
            text="Показать ещё",
            bg=inner_bg,
            fg=meta_fg,
            activebackground=bubble_hover,
            activeforeground=_c("TEXT_MAIN"),
            relief="flat",
            bd=0,
            cursor="hand2",
            font=_font_meta,
            padx=8,
            pady=2,
        )
        more_btn.pack(anchor="w", padx=12, pady=(0, 6))

        def _show_next_page():
            start = int(getattr(text_label, "_bubble_displayed_chars", 0))
            end = min(len(content), start + _CHAT_PAGE_CHARS)
            if end <= start:
                return
            text_label.insert("end", content[start:end])
            text_label._bubble_displayed_chars = end
            text_label._bubble_content = content[:end]
            if end >= len(content):
                more_btn.pack_forget()
            else:
                remaining = len(content) - end
                more_btn.configure(text=f"Показать ещё · осталось {remaining:,} знаков")
            try:
                state._root.after_idle(lambda: _resize_bubble_text(text_label))
            except Exception:
                _resize_bubble_text(text_label)

        more_btn.configure(command=_show_next_page)

    state._message_labels.append(text_label)

    def _send_selected_or_full2():
        try:
            ranges = text_label.tag_ranges("sel")
            if ranges:
                sel = text_label.get(ranges[0], ranges[1]).strip()
                if sel:
                    _send_to_main_editor(sel)
                    return
        except Exception:
            pass
        _send_to_main_editor(content)

    to_editor_btn.config(command=_send_selected_or_full2)
    _resize_bubble_text(text_label)

    text_label.bind("<Button-3>", lambda e, c=content: _show_bubble_context_menu(e, c, text_label))
    bubble.bind("<Button-3>", lambda e, c=content: _show_bubble_context_menu(e, c, text_label))

    # spacer занимает свободное место; bubble БЕЗ expand — иначе Text тянет на всю ширину
    spacer_left = tk.Frame(row, bg=_c("BG_DARK"), width=1)
    spacer_right = tk.Frame(row, bg=_c("BG_DARK"), width=1)

    if is_user:
        spacer_left.pack(side="left", fill="x", expand=True)
        bubble.pack(side="left", padx=(40, 8), anchor="e", fill=None, expand=False)
        avatar.pack(side="left", anchor="n", pady=(2, 0), padx=(0, 4))
    else:
        avatar.pack(side="left", anchor="n", pady=(2, 0), padx=(4, 0))
        bubble.pack(side="left", padx=(8, 40), anchor="w", fill=None, expand=False)
        spacer_right.pack(side="left", fill="x", expand=True)

    def _select_this_bubble(_event=None):
        _select_bubble(bubble, content, inner_bg)

    for w in (row, bubble, meta):
        try:
            w.bind("<Button-1>", _select_this_bubble)
        except Exception:
            pass

    def on_enter(_event=None):
        if bubble is _selected_bubble_frame_get():
            return
        try:
            bubble.config(bg=bubble_hover)
            meta.config(bg=bubble_hover)
            text_label.config(bg=bubble_hover)
            copy_btn.config(text="Copy", bg=bubble_hover)
            for child in meta.winfo_children():
                try:
                    child.config(bg=bubble_hover)
                except Exception:
                    pass
        except Exception:
            pass

    def on_leave(_event=None):
        if bubble is _selected_bubble_frame_get():
            return
        try:
            bubble.config(bg=inner_bg)
            meta.config(bg=inner_bg)
            text_label.config(bg=inner_bg)
            copy_btn.config(text="", bg=inner_bg)
            to_editor_btn.config(bg=inner_bg)
            for child in meta.winfo_children():
                try:
                    child.config(bg=inner_bg)
                except Exception:
                    pass
        except Exception:
            pass

    bubble._on_select_colors = (inner_bg, bubble_hover, meta, text_label, copy_btn, to_editor_btn)

    for w in (row, bubble, meta, avatar):
        try:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<MouseWheel>", _chat_mousewheel, add="+")
            w.bind("<Button-4>", _chat_mousewheel, add="+")
            w.bind("<Button-5>", _chat_mousewheel, add="+")
        except Exception:
            pass

    _safe_after(50, lambda: _resize_bubble_text(text_label) if _widget_exists(text_label) else None)

    def _check_and_scroll():
        if not _widget_exists(state.chat_canvas):
            return
        if _was_near_bottom:
            _scroll_chat_to_bottom(immediate=False)
            _hide_new_message_indicator()
        elif role == "assistant" and smooth_scroll:
            _show_new_message_indicator()

    if smooth_scroll or force_scroll:
        _safe_after(150, _check_and_scroll)


def _add_system_message(content: str, ts: str):
    row = tk.Frame(state.chat_messages_frame, bg=_c("BG_DARK"))
    row._is_message_row = True
    row.pack(fill="x", padx=18, pady=10)

    card = CTkFrame(
        row, fg_color=_c("BG_CARD"), corner_radius=14, border_width=1, border_color=_c("BORDER")
    )
    card.pack(anchor="center", padx=12, pady=4)

    label = TkLabel(
        card,
        text=f"{ts} · {content}",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", scaled_font_size(11), "italic"),
        wraplength=480,
        justify="center",
        padx=16,
        pady=10,
    )
    label.pack()
    state._message_labels.append(label)


def _resize_bubble_text(text_widget):
    """Ширина по тексту (clamp max), высота по display-lines."""
    if not _widget_exists(text_widget):
        return
    try:
        max_w = int(getattr(text_widget, "_bubble_max_w", 0) or _bubble_max_width_px())
        content = ""
        try:
            content = text_widget.get("1.0", "end-1c")
        except Exception:
            content = getattr(text_widget, "_bubble_content", "") or ""

        font_body = getattr(text_widget, "_font_body", None)
        if font_body is None:
            try:
                font_body = text_widget.cget("font")
            except Exception:
                font_body = ("Segoe UI", 11)
        font_meta = getattr(text_widget, "_font_meta", ("Segoe UI", 9))
        meta_text = getattr(text_widget, "_meta_text", "")

        bubble_w = _bubble_needed_width_px(content, meta_text, font_body, font_meta, max_w)
        text_widget._bubble_w = bubble_w

        # pt for char estimate
        try:
            pt = (
                int(font_body[1])
                if isinstance(font_body, (tuple, list)) and len(font_body) > 1
                else 11
            )
        except Exception:
            pt = 11
        char_w = _chars_for_width(bubble_w - 32, pt)
        try:
            text_widget.config(width=char_w)
        except Exception:
            pass

        # подтянуть width CTk/Frame пузыря
        bubble = getattr(text_widget, "_bubble_frame", None)
        if bubble is not None and _widget_exists(bubble):
            try:
                bubble.configure(width=bubble_w)
            except Exception:
                try:
                    bubble.config(width=bubble_w)
                except Exception:
                    pass

        # Tcl `count -displaylines` forces a synchronous layout of the entire
        # Text widget and becomes pathological for long messages. The bounded
        # estimate is stable, O(displayed text), and the widget is capped at 80.
        n = _estimate_display_lines(content, char_w)
        text_widget.config(height=n)
    except Exception:
        try:
            content = text_widget.get("1.0", "end-1c")
            text_widget.config(height=max(1, min(80, content.count("\n") + 1)))
        except Exception:
            pass


def content_lines_estimate(text_widget) -> int:
    try:
        content = text_widget.get("1.0", "end-1c")
        return max(1, content.count("\n") + 1)
    except Exception:
        return 1


def _lighten_color(hex_color: str, factor: float = 0.1) -> str:
    try:
        h = hex_color.lstrip("#")
        if len(h) != 6:
            return hex_color
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return hex_color


def _selected_bubble_frame_get():
    return state._selected_bubble_frame


def _select_bubble(bubble_frame, content: str, base_bg: str):
    if (
        _widget_exists(state._selected_bubble_frame)
        and state._selected_bubble_frame is not bubble_frame
    ):
        try:
            prev_bg, _hover, prev_meta, prev_text, prev_copy, prev_to_editor = (
                state._selected_bubble_frame._on_select_colors
            )
            state._selected_bubble_frame.config(
                fg_color=prev_bg if hasattr(state._selected_bubble_frame, "configure") else prev_bg,
                bg=prev_bg,
            )
            prev_meta.config(bg=prev_bg)
            prev_text.config(bg=prev_bg)
            prev_copy.config(bg=prev_bg)
            prev_to_editor.config(bg=prev_bg)
            for child in prev_meta.winfo_children():
                try:
                    child.config(bg=prev_bg)
                except Exception:
                    pass
        except Exception:
            pass

    if state._selected_bubble_frame is bubble_frame:
        try:
            _, _hover, meta, text_w, copy_b, to_editor_b = bubble_frame._on_select_colors
            meta.config(bg=base_bg)
            text_w.config(bg=base_bg)
            copy_b.config(bg=base_bg)
            to_editor_b.config(bg=base_bg)
        except Exception:
            pass
        state._selected_bubble_frame = None
        state._selected_bubble_content = ""
        set_chat_status(t("chat_selection_cleared"))
        return

    try:
        bubble_frame.configure(border_color=_c("ACCENT"), border_width=2)
    except Exception:
        try:
            bubble_frame.config(highlightbackground=_c("ACCENT"), highlightthickness=2)
        except Exception:
            pass

    state._selected_bubble_frame = bubble_frame
    state._selected_bubble_content = content
    set_chat_status(t("chat_msg_selected"))


def _on_bubble_text_click(event):
    return None


def _show_bubble_context_menu(event, content: str, text_widget=None):
    if not _widget_exists(state._chat_window):
        return

    def _get_sel_or_full():
        if text_widget is not None and _widget_exists(text_widget):
            try:
                ranges = text_widget.tag_ranges("sel")
                if ranges:
                    sel = text_widget.get(ranges[0], ranges[1]).strip()
                    if sel:
                        return sel
            except Exception:
                pass
        return content

    menu = tk.Menu(
        state._chat_window,
        tearoff=0,
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        activebackground=_c("BG_HOVER") if hasattr(state._colors, "BG_HOVER") else _c("BORDER"),
        activeforeground=_c("TEXT_MAIN"),
        relief="flat",
        borderwidth=1,
        font=("Segoe UI", 11),
    )
    menu.add_command(
        label=t("chat_ctx_copy"), command=lambda: _copy_to_clipboard(_get_sel_or_full())
    )
    menu.add_separator()
    menu.add_command(
        label=t("chat_ctx_to_editor"), command=lambda: _send_to_main_editor(_get_sel_or_full())
    )
    menu.add_command(
        label=t("chat_ctx_to_input"),
        command=lambda: _insert_prompt_into_chat_input(_get_sel_or_full()),
    )
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def _update_wraplengths(event=None):
    """При ресайзе canvas — обновить max и пересчитать content-sized ширину."""
    if not _widget_exists(state.chat_canvas):
        return
    try:
        width = state.chat_canvas.winfo_width()
        if width < 50:
            return
        max_w = max(220, min(640, int(width * 0.62)))
        for widget in list(state._message_labels):
            if not _widget_exists(widget):
                continue
            try:
                if isinstance(widget, tk.Text):
                    widget._bubble_max_w = max_w
                    _resize_bubble_text(widget)
                else:
                    widget.config(wraplength=max_w)
            except Exception:
                pass
        try:
            state.chat_canvas.configure(scrollregion=state.chat_canvas.bbox("all"))
        except Exception:
            pass
    except Exception:
        pass


def _render_current_session():
    """Render message history in cancellable batches without changing data."""
    global _session_render_token, _session_render_after_id
    _hide_new_message_indicator()
    if _session_render_after_id is not None and state._root is not None:
        try:
            state._root.after_cancel(_session_render_after_id)
        except Exception:
            pass
        _session_render_after_id = None
    _session_render_token += 1
    token = _session_render_token
    _clear_messages_ui()
    session = _get_current_session()
    all_messages = list(session.get("messages", []))
    if not all_messages:
        _add_empty_state()
        _update_token_counter()
        return

    session_key = str(session.get("id") or id(session))
    visible_count = max(
        _SESSION_VISIBLE_WINDOW,
        int(_session_visible_counts.get(session_key, _SESSION_VISIBLE_WINDOW)),
    )
    visible_count = min(len(all_messages), visible_count)
    _session_visible_counts[session_key] = visible_count
    first_visible = len(all_messages) - visible_count
    messages = all_messages[first_visible:]

    if first_visible > 0:
        older_row = TkFrame(state.chat_messages_frame, bg=_c("BG_DARK"))
        older_row.pack(fill="x", padx=18, pady=(8, 4))

        def load_older():
            _session_visible_counts[session_key] = min(
                len(all_messages), visible_count + _SESSION_VISIBLE_WINDOW
            )
            _session_scroll_top_once.add(session_key)
            _render_current_session()

        older_btn = TkButton(
            older_row,
            text=f"Показать предыдущие сообщения · скрыто {first_visible}",
            command=load_older,
            bg=_c("BG_INPUT"),
            fg=_c("TEXT_MAIN"),
            activebackground=_c("BG_HOVER"),
            activeforeground=_c("TEXT_MAIN"),
            relief="flat",
            cursor="hand2",
            font=("Segoe UI", scaled_font_size(10), "bold"),
            padx=12,
            pady=6,
        )
        older_btn.pack(anchor="center")

    def render_batch(start=0):
        global _session_render_after_id
        _session_render_after_id = None
        if token != _session_render_token or not _widget_exists(state.chat_messages_frame):
            return
        end = min(len(messages), start + _SESSION_RENDER_BATCH)
        for message in messages[start:end]:
            _add_message_bubble(message, smooth_scroll=False)
        if end < len(messages):
            try:
                _session_render_after_id = state._root.after(
                    8, lambda next_start=end: render_batch(next_start)
                )
            except Exception:
                _session_render_after_id = None
            return
        _update_wraplengths()
        if session_key in _session_scroll_top_once:
            _session_scroll_top_once.discard(session_key)
            try:
                state.chat_canvas.yview_moveto(0.0)
            except Exception:
                pass
        else:
            _scroll_chat_to_bottom(immediate=True)
        _update_token_counter()

    render_batch(0)


def _add_empty_state():
    if not _widget_exists(state.chat_messages_frame):
        return
    box = TkFrame(state.chat_messages_frame, bg=_c("BG_DARK"))
    box._is_empty_state = True
    box.pack(fill="both", expand=True, padx=24, pady=60)

    card = CTkFrame(
        box, fg_color=_c("BG_CARD"), corner_radius=20, border_width=1, border_color=_c("BORDER")
    )
    card.pack(pady=10, padx=20)

    inner = TkFrame(card, bg=_c("BG_CARD"))
    inner.pack(padx=24, pady=24)

    TkLabel(
        inner,
        text="💬",
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI Emoji", scaled_font_size(36)),
    ).pack(pady=(0, 12))
    TkLabel(
        inner,
        text=t("chat_new_chat_title"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_MAIN"),
        font=("Segoe UI", scaled_font_size(15), "bold"),
    ).pack()
    TkLabel(
        inner,
        text=t("chat_welcome"),
        bg=_c("BG_CARD"),
        fg=_c("TEXT_DIM"),
        font=("Segoe UI", scaled_font_size(11)),
        wraplength=400,
        justify="center",
    ).pack(pady=(10, 0))


def _destroy_empty_state_if_any():
    if not _widget_exists(state.chat_messages_frame):
        return
    for child in state.chat_messages_frame.winfo_children():
        try:
            if getattr(child, "_is_empty_state", False):
                child.destroy()
        except Exception:
            pass


def _clear_messages_ui():
    state._message_labels = []
    state._typing_frame = None
    state._typing_label = None
    state._selected_bubble_frame = None
    state._selected_bubble_content = ""
    if not _widget_exists(state.chat_messages_frame):
        return
    for child in state.chat_messages_frame.winfo_children():
        try:
            child.destroy()
        except Exception:
            pass


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
