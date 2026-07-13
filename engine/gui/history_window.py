# -*- coding: utf-8 -*-
"""engine/gui/history_window.py — окно «История»

Редизайн (в стиле output_window.py) + патч 2026-07-09:
- Увеличен размер текста и кнопок как в окне аудио (как просил пользователь)
- Фикс иконки в панели задач Windows (перо -> нормальная иконка)
- Добавлен fallback для pygame play(start=) чтобы сик работал на WAV
"""
import json
import os
import threading
import tkinter as tk
from tkinter import messagebox

import pygame
import customtkinter as ctk

try:
    import soundfile as sf
except ImportError:
    sf = None

from i18n import t

from engine.history_store import HISTORY_PATH
from engine.paths import BASE_DIR

try:
    from engine.paths import ICON_PATH
except ImportError:
    ICON_PATH = os.path.join(str(BASE_DIR), "icon.ico")

from engine.gui.colors import Colors, scaled_font_size, scaled_size
from engine.gui.textbox import set_textbox_content
from engine.gui.tooltip import ToolTip
from engine.gui.widgets import CompatCTkFrame, CompatCTkButton, CompatCTkLabel

# Внедряется из main_window: root, PYGAME_OK
root = None
PYGAME_OK = False

_WAVE_BARS = 200
_VOL_TRANSPARENT_KEY = "#ff00ff"


def _safe_t(key, fallback):
    try:
        val = t(key)
        return val if val and val != key else fallback
    except Exception:
        return fallback


def init(**deps):
    globals().update(deps)


def _compute_waveform_peaks(path, num_bars=_WAVE_BARS):
    if sf is None:
        return []
    try:
        with sf.SoundFile(path) as f:
            frames = f.frames
            if frames <= 0:
                return []
            block = max(1, frames // num_bars)
            peaks = []
            for start in range(0, frames, block):
                f.seek(start)
                data = f.read(min(block, frames - start), dtype="float32", always_2d=True)
                if data.size == 0:
                    continue
                mono = data.mean(axis=1)
                peaks.append((float(mono.min()), float(mono.max())))
                if len(peaks) >= num_bars:
                    break
            return peaks
    except Exception:
        return []


def _round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [
        x1 + r,
        y1,
        x2 - r,
        y1,
        x2,
        y1,
        x2,
        y1 + r,
        x2,
        y2 - r,
        x2,
        y2,
        x2 - r,
        y2,
        x1 + r,
        y2,
        x1,
        y2,
        x1,
        y2 - r,
        x1,
        y1 + r,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def _apply_window_icon(win: tk.Toplevel):
    """Фикс иконки в панели задач Windows (как в output_window)."""
    try:
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("XTTSStudio.App")
        except Exception:
            pass
    except Exception:
        pass

    candidates = []
    if ICON_PATH:
        candidates.append(ICON_PATH)
    candidates.extend(
        [
            os.path.join(str(BASE_DIR), "icon.ico"),
            os.path.join(str(BASE_DIR), "icon.png"),
            os.path.join(str(BASE_DIR), "images", "icon.ico"),
            os.path.join(str(BASE_DIR), "images", "icon.png"),
        ]
    )
    ico_file = None
    png_file = None
    for p in candidates:
        try:
            if p and os.path.isfile(p):
                if p.lower().endswith(".ico") and ico_file is None:
                    ico_file = p
                elif p.lower().endswith(".png") and png_file is None:
                    png_file = p
        except Exception:
            continue

    if ico_file:
        try:
            win.iconbitmap(default=ico_file)
        except Exception:
            try:
                win.iconbitmap(ico_file)
            except Exception:
                pass

        def _reapply_icon():
            try:
                win.iconbitmap(default=ico_file)
            except Exception:
                try:
                    win.iconbitmap(ico_file)
                except Exception:
                    pass

        try:
            win.after(100, _reapply_icon)
            win.after(400, _reapply_icon)
            win.after(1000, _reapply_icon)
        except Exception:
            pass

    try:
        photo = None
        if png_file:
            try:
                photo = tk.PhotoImage(file=png_file)
            except Exception:
                photo = None
        if photo is None and ico_file:
            try:
                from PIL import Image, ImageTk

                im = Image.open(ico_file)
                im = im.resize((32, 32), Image.LANCZOS)
                photo = ImageTk.PhotoImage(im)
            except Exception:
                try:
                    photo = tk.PhotoImage(file=ico_file)
                except Exception:
                    photo = None
        if photo is not None:
            try:
                win.iconphoto(True, photo)
                win._icon_photo_ref = photo
            except Exception:
                pass
    except Exception:
        pass


def open_history():
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        history = []
    win = tk.Toplevel(root)
    win.title(t("win_history_title"))
    win.geometry("860x700")
    win.minsize(700, 540)
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    _apply_window_icon(win)
    win.grab_set()

    _p = {
        "playing": False,
        "path": None,
        "pos": 0.0,
        "duration": 0.0,
        "after_id": None,
        "volume": 0.8,
        "error": None,
    }
    _wave_state = {"peaks": [], "path": None}
    _card_widgets = {}
    _active_path = {"v": None}
    _vol_popup = {"win": None}
    _empty_state = {"widget": None}
    _ui_refs = {"vol_btn": None, "play_btn": None}

    def _round_btn(parent, text, cmd, diameter=36, primary=False, danger=False, disabled=False):
        bg = Colors.BG_ACTIVE if primary else Colors.BG_INPUT
        if disabled:
            bg = Colors.BG_DARK
        if primary:
            hover = "#2ea043"
        elif danger:
            hover = Colors.BG_DANGER
        else:
            hover = Colors.BG_HOVER if not disabled else Colors.BG_DARK
        scaled_diameter = scaled_size(diameter, min_size=diameter)
        # УВЕЛИЧЕНО: было 14/12 -> 17/15 как в аудио окне
        btn = CompatCTkButton(
            parent,
            text=text,
            command=cmd if not disabled else None,
            width=scaled_diameter,
            height=scaled_diameter,
            corner_radius=scaled_diameter // 2,
            fg_color=bg,
            text_color=Colors.TEXT_MAIN if not disabled else Colors.TEXT_DIM,
            hover_color=hover,
            border_width=0,
            font=("Segoe UI", scaled_font_size(17 if primary else 15)),
        )
        if disabled:
            btn.configure(state="disabled")
        return btn

    def _fmt(sec):
        sec = max(0, int(sec))
        return f"{sec // 60}:{sec % 60:02d}"

    def _truncate(s, max_chars=44):
        return s if len(s) <= max_chars else s[: max_chars - 1] + "…"

    def _get_duration(path):
        try:
            if sf is None:
                return 0.0
            return sf.info(path).duration
        except Exception:
            return 0.0

    def _volume_icon(vol):
        return "🔇" if vol <= 0.001 else ("🔉" if vol < 0.5 else "🔊")

    def _redraw_waveform():
        try:
            wave_canvas.delete("all")
            w = wave_canvas.winfo_width()
            h = wave_canvas.winfo_height()
            if w <= 1 or h <= 1:
                return
            text_zone_h = 28  # было 22 -> 28
            body_top = text_zone_h + 6
            body_h = max(10, h - body_top - 4)
            mid = body_top + body_h / 2
            peaks = _wave_state["peaks"]
            played_frac = 0.0
            if _p["duration"] > 0:
                played_frac = min(1.0, max(0.0, _p["pos"] / _p["duration"]))
            played_x = played_frac * w
            if not peaks:
                wave_canvas.create_line(0, mid, w, mid, fill=Colors.BORDER)
            else:
                n = len(peaks)
                bar_w = w / n
                for i, (mn, mx) in enumerate(peaks):
                    x0 = i * bar_w
                    x1 = x0 + max(1.0, bar_w - 1)
                    y0 = mid - mx * (body_h / 2 - 2)
                    y1 = mid - mn * (body_h / 2 - 2)
                    if y1 - y0 < 1.5:
                        y0 -= 0.75
                        y1 += 0.75
                    color = Colors.ACCENT if x0 <= played_x else Colors.BG_INPUT
                    wave_canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
            if _p["path"]:
                wave_canvas.create_line(
                    played_x, body_top - 2, played_x, h, fill=Colors.TEXT_MAIN, width=1
                )
            wave_canvas.create_rectangle(0, 0, w, text_zone_h, fill=Colors.BG_CARD, outline="")
            if _p.get("error"):
                title, title_color = _p["error"], Colors.TEXT_ERROR
            elif _p["path"]:
                title, title_color = os.path.basename(_p["path"]), Colors.TEXT_MAIN
            else:
                title, title_color = t("no_file"), Colors.TEXT_DIM
            # УВЕЛИЧЕНО: 9->12 и 8->11 как в аудио окне
            wave_canvas.create_text(
                10,
                text_zone_h / 2,
                text=_truncate(title),
                anchor="w",
                fill=title_color,
                font=("Segoe UI", scaled_font_size(12), "bold"),
            )
            time_text = f"{_fmt(_p['pos'])} / {_fmt(_p['duration'])}" if _p["path"] else "0:00"
            wave_canvas.create_text(
                w - 10,
                text_zone_h / 2,
                text=time_text,
                anchor="e",
                fill=Colors.TEXT_DIM,
                font=("Consolas", scaled_font_size(11)),
            )
        except Exception:
            pass

    def _load_waveform_async(path):
        if _wave_state.get("path") == path and _wave_state.get("peaks"):
            _redraw_waveform()
            return
        _wave_state["peaks"] = []
        _wave_state["path"] = path
        _redraw_waveform()

        def worker():
            peaks = _compute_waveform_peaks(path)

            def apply():
                if _wave_state["path"] == path:
                    _wave_state["peaks"] = peaks
                    _redraw_waveform()

            try:
                win.after(0, apply)
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _wave_seek(event):
        w = wave_canvas.winfo_width()
        if w <= 1 or not _p["path"] or not _p["duration"]:
            return
        frac = min(1.0, max(0.0, event.x / w))
        _load_play(_p["path"], frac * _p["duration"])

    def _reset_player_ui():
        _stop_ticker()
        _p.update(playing=False, path=None, pos=0.0, duration=0.0, error=None)
        _wave_state.update(peaks=[], path=None)
        try:
            _ui_refs.get("play_btn", {}).configure(text="▶")
        except Exception:
            try:
                play_btn.configure(text="▶")
            except Exception:
                pass
        _redraw_waveform()

    def _tick():
        if not PYGAME_OK:
            return
        try:
            if pygame.mixer.music.get_busy():
                _p["pos"] += 0.2
                _redraw_waveform()
                _p["after_id"] = win.after(200, _tick)
            else:
                _p["after_id"] = None
                _reset_player_ui()
        except Exception:
            pass

    def _stop_ticker():
        if _p["after_id"]:
            try:
                win.after_cancel(_p["after_id"])
            except Exception:
                pass
            _p["after_id"] = None

    def _load_play(path, from_pos=0.0):
        if not PYGAME_OK or not path or not os.path.isfile(path):
            messagebox.showwarning("⚠", t("dlg_audio_unavailable"), parent=win)
            return
        _stop_ticker()
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(_p["volume"])
            # ФИКС: fallback для WAV
            try:
                pygame.mixer.music.play(start=from_pos)
            except TypeError:
                pygame.mixer.music.play()
            except Exception:
                try:
                    pygame.mixer.music.play()
                except Exception:
                    raise
            dur = _get_duration(path)
            _p.update(playing=True, path=path, pos=from_pos, duration=dur, error=None)
            _load_waveform_async(path)
            _redraw_waveform()
            _highlight_active(path)
            try:
                _ui_refs.get("play_btn").configure(text="⏸")
            except Exception:
                try:
                    play_btn.configure(text="⏸")
                except Exception:
                    pass
            _tick()
        except Exception as e:
            _p["error"] = str(e)
            _redraw_waveform()

    def toggle_play():
        if not PYGAME_OK:
            return
        if _p["playing"]:
            pygame.mixer.music.pause()
            _p["playing"] = False
            _stop_ticker()
            try:
                _ui_refs.get("play_btn").configure(text="▶")
            except Exception:
                play_btn.configure(text="▶")
        else:
            if _p["path"] and os.path.isfile(_p["path"]):
                pygame.mixer.music.unpause()
                _p["playing"] = True
                try:
                    _ui_refs.get("play_btn").configure(text="⏸")
                except Exception:
                    play_btn.configure(text="⏸")
                _tick()

    def seek_rel(delta):
        if not _p["path"]:
            return
        _load_play(_p["path"], max(0.0, _p["pos"] + delta))

    def on_volume_change(vol):
        vol = max(0.0, min(1.0, vol))
        _p["volume"] = vol
        if PYGAME_OK:
            try:
                pygame.mixer.music.set_volume(vol)
            except Exception:
                pass
        try:
            vb = _ui_refs.get("vol_btn")
            if vb:
                vb.configure(text=_volume_icon(vol))
            else:
                vol_btn.configure(text=_volume_icon(vol))
        except Exception:
            pass

    def _highlight_active(path):
        prev = _active_path["v"]
        if prev and prev in _card_widgets:
            try:
                _card_widgets[prev].configure(border_color=Colors.BORDER, border_width=1)
            except Exception:
                pass
        _active_path["v"] = path
        if path in _card_widgets:
            try:
                _card_widgets[path].configure(border_color=Colors.ACCENT, border_width=2)
            except Exception:
                pass

    def clear_history():
        if not messagebox.askyesno(t("ctx_clear"), t("dlg_clear_history"), parent=win):
            return
        try:
            os.remove(HISTORY_PATH)
        except Exception:
            pass
        for w in list(list_frame.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        _card_widgets.clear()
        _active_path["v"] = None
        count_lbl.configure(text=t("entries_count", 0))
        _maybe_show_empty_state()

    def _maybe_show_empty_state():
        if list_frame.winfo_children():
            if _empty_state["widget"] is not None:
                try:
                    _empty_state["widget"].destroy()
                except Exception:
                    pass
                _empty_state["widget"] = None
            return
        if _empty_state["widget"] is None:
            # УВЕЛИЧЕНО: 10->13
            lbl = CompatCTkLabel(
                list_frame,
                text=t("history_empty"),
                fg_color=Colors.BG_DARK,
                text_color=Colors.TEXT_DIM,
                font=("Segoe UI", scaled_font_size(13)),
            )
            lbl.pack(pady=50)
            _empty_state["widget"] = lbl

    def _close_volume_popup(event=None):
        w = _vol_popup["win"]
        if w is not None:
            try:
                win.unbind("<Button-1>")
            except Exception:
                try:
                    win.unbind_all("<Button-1>")
                except Exception:
                    pass
            try:
                w.destroy()
            except Exception:
                pass
            _vol_popup["win"] = None

    def _toggle_volume_popup():
        if _vol_popup["win"] is not None:
            _close_volume_popup()
            return
        popup_w, popup_h = 56, 168
        popup = tk.Toplevel(vol_btn)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        try:
            popup.configure(bg=_VOL_TRANSPARENT_KEY)
            popup.attributes("-transparentcolor", _VOL_TRANSPARENT_KEY)
            canvas_bg = _VOL_TRANSPARENT_KEY
        except Exception:
            popup.configure(bg=Colors.BG_DARK)
            canvas_bg = Colors.BG_DARK
        x = vol_btn.winfo_rootx() - (popup_w - vol_btn.winfo_width()) // 2
        y = vol_btn.winfo_rooty() - popup_h - 10
        popup.geometry(f"{popup_w}x{popup_h}+{x}+{y}")
        pcanvas = tk.Canvas(
            popup, width=popup_w, height=popup_h, bg=canvas_bg, highlightthickness=0, bd=0
        )
        pcanvas.pack(fill="both", expand=True)

        track_top, track_bottom = 16, popup_h - 40
        track_h = track_bottom - track_top
        cx = popup_w / 2

        def _redraw_slider():
            pcanvas.delete("all")
            _round_rect(
                pcanvas,
                2,
                2,
                popup_w - 2,
                popup_h - 2,
                18,
                fill=Colors.BG_CARD,
                outline=Colors.BORDER,
            )
            _round_rect(
                pcanvas,
                cx - 3,
                track_top,
                cx + 3,
                track_bottom,
                3,
                fill=Colors.BG_INPUT,
                outline="",
            )
            fill_top = track_top + track_h * (1 - _p["volume"])
            if track_bottom - fill_top > 1:
                _round_rect(
                    pcanvas,
                    cx - 3,
                    fill_top,
                    cx + 3,
                    track_bottom,
                    3,
                    fill=Colors.ACCENT,
                    outline="",
                )
            thumb_y = track_top + track_h * (1 - _p["volume"])
            pcanvas.create_oval(
                cx - 7, thumb_y - 7, cx + 7, thumb_y + 7, fill=Colors.TEXT_MAIN, outline=""
            )
            # УВЕЛИЧЕНО 11->14
            pcanvas.create_text(
                cx,
                popup_h - 18,
                text=_volume_icon(_p["volume"]),
                font=("Segoe UI", scaled_font_size(14)),
                fill=Colors.TEXT_DIM,
            )

        def _on_slider_drag(event):
            frac = 1 - min(1.0, max(0.0, (event.y - track_top) / track_h))
            on_volume_change(frac)
            _redraw_slider()

        pcanvas.bind("<Button-1>", _on_slider_drag)
        pcanvas.bind("<B1-Motion>", _on_slider_drag)
        _redraw_slider()

        popup.bind("<Escape>", _close_volume_popup)
        popup.focus_force()

        def _on_global_click(event):
            try:
                wx, wy = popup.winfo_rootx(), popup.winfo_rooty()
                ww, wh = popup.winfo_width(), popup.winfo_height()
                inside_popup = wx <= event.x_root <= wx + ww and wy <= event.y_root <= wy + wh
                bx, by = vol_btn.winfo_rootx(), vol_btn.winfo_rooty()
                bw, bh = vol_btn.winfo_width(), vol_btn.winfo_height()
                inside_btn = bx <= event.x_root <= bx + bw and by <= event.y_root <= by + bh
                if not inside_popup and not inside_btn:
                    _close_volume_popup()
            except Exception:
                _close_volume_popup()

        win.bind_all("<Button-1>", _on_global_click, add="+")
        _vol_popup["win"] = popup

    def _make_card(parent, entry):
        output_path = entry.get("output", "")
        audio_exists = bool(output_path) and os.path.isfile(output_path)

        card = CompatCTkFrame(
            parent,
            fg_color=Colors.BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=Colors.BORDER,
        )
        card.pack(fill="x", padx=4, pady=5)
        if output_path:
            _card_widgets[output_path] = card

        # ФИКС: actions пакуем ПЕРВЫМ справа, чтобы его не съедало left с expand=True
        # при крупном шрифте кнопка ↩ раньше уезжала за край карточки
        actions = tk.Frame(card, bg=Colors.BG_CARD)
        actions.pack(side="right", padx=12, pady=10, anchor="e")

        def _play_entry(p=output_path):
            _load_play(p, 0.0)

        btn_listen = _round_btn(actions, "▶", _play_entry, diameter=34, disabled=not audio_exists)
        btn_listen.pack(side="left", padx=(0, 6))
        ToolTip(
            btn_listen,
            (
                _safe_t("tip_listen", "Прослушать")
                if audio_exists
                else _safe_t("tip_audio_missing", "Аудио удалено")
            ),
        )

        def _reuse(t_text=entry.get("text", "")):
            set_textbox_content(t_text)
            on_close()

        btn_reuse = _round_btn(actions, "↩", _reuse, diameter=34)
        btn_reuse.pack(side="left")
        ToolTip(btn_reuse, _safe_t("tip_reuse", "Вставить текст обратно"))

        left = tk.Frame(card, bg=Colors.BG_CARD)
        left.pack(side="left", fill="both", expand=True, padx=14, pady=10)

        # УВЕЛИЧЕНО: дата 8->11, мета 8->11, превью 11->14
        CompatCTkLabel(
            left,
            text=entry.get("date", ""),
            fg_color=Colors.BG_CARD,
            text_color=Colors.ACCENT,
            font=("Segoe UI", scaled_font_size(11), "bold"),
            anchor="w",
        ).pack(fill="x")
        meta = f"🎤 {entry.get('voice', '?')}   ·   ⭐ {entry.get('quality', '?')}   ·   {entry.get('chunks', 0)} {t('chunks_word')}"
        CompatCTkLabel(
            left,
            text=meta,
            fg_color=Colors.BG_CARD,
            text_color=Colors.TEXT_DIM,
            font=("Segoe UI", scaled_font_size(11)),
            anchor="w",
        ).pack(fill="x", pady=(2, 4))
        text_preview = entry.get("text", "").replace("\n", " ")
        # ФИКС: уменьшили обрезку с 90 до 65 символов,
        # чтобы при крупном шрифте текст не выдавливал кнопки за пределы карточки
        CompatCTkLabel(
            left,
            text=_truncate(text_preview, 65),
            fg_color=Colors.BG_CARD,
            text_color=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(14)),
            anchor="w",
            justify="left",
        ).pack(fill="x")

    # LAYOUT
    header = tk.Frame(win, bg=Colors.BG_DARK, pady=12)
    header.pack(fill="x", padx=16)

    clear_pill = CompatCTkFrame(
        header,
        fg_color=Colors.BG_CARD,
        corner_radius=18,
        border_width=1,
        border_color=Colors.BORDER,
    )
    clear_pill.pack(side="left")
    clear_row = tk.Frame(clear_pill, bg=Colors.BG_CARD)
    clear_row.pack(padx=6, pady=6)
    btn_clear = _round_btn(clear_row, "🗑", clear_history, diameter=36, danger=True)
    btn_clear.pack(side="left")
    ToolTip(btn_clear, t("btn_clear_history"))

    count_pill = CompatCTkFrame(
        header,
        fg_color=Colors.BG_CARD,
        corner_radius=14,
        border_width=1,
        border_color=Colors.BORDER,
    )
    count_pill.pack(side="right")
    # УВЕЛИЧЕНО 9->12
    count_lbl = CompatCTkLabel(
        count_pill,
        text=t("entries_count", len(history)),
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(12)),
    )
    count_lbl.pack(padx=16, pady=9)

    list_frame = ctk.CTkScrollableFrame(win, fg_color=Colors.BG_DARK, corner_radius=12)
    list_frame.pack(fill="both", expand=True, padx=12, pady=(4, 6))

    for entry in history:
        _make_card(list_frame, entry)
    _maybe_show_empty_state()

    outer_wrap = tk.Frame(win, bg=Colors.BG_DARK)
    outer_wrap.pack(fill="x", side="bottom")

    player_card = CompatCTkFrame(
        outer_wrap,
        fg_color=Colors.BG_CARD,
        corner_radius=20,
        border_width=1,
        border_color=Colors.BORDER,
    )
    player_card.pack(fill="x", padx=14, pady=(6, 14))

    wave_canvas = tk.Canvas(
        player_card, bg=Colors.BG_CARD, height=90, bd=0, highlightthickness=0, cursor="hand2"
    )
    wave_canvas.pack(fill="x", padx=18, pady=(16, 6))
    wave_canvas.bind("<Button-1>", _wave_seek)
    wave_canvas.bind("<B1-Motion>", _wave_seek)
    wave_canvas.bind("<Configure>", lambda e: _redraw_waveform())

    ctrl_pill = CompatCTkFrame(player_card, fg_color=Colors.BG_INPUT, corner_radius=26)
    ctrl_pill.pack(pady=(2, 18))
    ctrl_row = tk.Frame(ctrl_pill, bg=Colors.BG_INPUT)
    ctrl_row.pack(padx=12, pady=8)

    btn_back10 = _round_btn(ctrl_row, "⏪", lambda: seek_rel(-10), diameter=38)
    btn_back10.pack(side="left", padx=4)
    btn_back5 = _round_btn(ctrl_row, "⏮", lambda: seek_rel(-5), diameter=38)
    btn_back5.pack(side="left", padx=4)

    play_btn = _round_btn(ctrl_row, "▶", toggle_play, diameter=56, primary=True)
    play_btn.pack(side="left", padx=10)
    _ui_refs["play_btn"] = play_btn

    btn_fwd5 = _round_btn(ctrl_row, "⏭", lambda: seek_rel(5), diameter=38)
    btn_fwd5.pack(side="left", padx=4)
    btn_fwd10 = _round_btn(ctrl_row, "⏩", lambda: seek_rel(10), diameter=38)
    btn_fwd10.pack(side="left", padx=4)

    vol_btn = _round_btn(ctrl_row, _volume_icon(_p["volume"]), _toggle_volume_popup, diameter=38)
    vol_btn.pack(side="left", padx=(16, 0))
    ToolTip(vol_btn, "Громкость")
    _ui_refs["vol_btn"] = vol_btn

    if PYGAME_OK:
        try:
            pygame.mixer.music.set_volume(_p["volume"])
        except Exception:
            pass

    _redraw_waveform()
    try:
        win.after(150, lambda: _apply_window_icon(win))
    except Exception:
        pass

    def on_close():
        _close_volume_popup()
        _stop_ticker()
        try:
            pygame.mixer.music.stop()
            if hasattr(pygame.mixer.music, "unload"):
                pygame.mixer.music.unload()
        except Exception:
            pass
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)
