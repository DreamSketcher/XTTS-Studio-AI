# -*- coding: utf-8 -*-
"""engine/gui/output_window.py — окно «Аудио» / Outputs со встроенным плеером

ФИКС v2 от 2026-07-09:
1. Починена кнопка повтора (замыкание) + увеличен текст (из v1)
2. NEW: сохранение состояния повтора между перезапусками окна/приложения
   -> сохраняется в theme_settings.json как audio_repeat_one через theme_manager
3. NEW: фикс иконки в панели задач Windows (перо tkinter -> нормальная иконка)
   -> ставится iconbitmap + iconphoto + AppUserModelID + re-apply через after
"""
import os
import datetime as _dt
import threading
import tkinter as tk
from tkinter import messagebox
import json

import pygame
import customtkinter as ctk

try:
    import soundfile as sf
except ImportError:
    sf = None

from i18n import t

from engine.paths import BASE_DIR, OUTPUT_DIR

# ICON_PATH может быть, а может нет — обрабатываем fallback
try:
    from engine.paths import ICON_PATH
except ImportError:
    ICON_PATH = os.path.join(str(BASE_DIR), "icon.ico")

from engine.gui.colors import Colors, scaled_font_size, scaled_size
from engine.gui.tooltip import ToolTip
from engine.gui.widgets import CompatCTkFrame, CompatCTkButton, CompatCTkLabel

# Внедряются из main_window: root, PYGAME_OK
root = None
PYGAME_OK = False

_WAVE_BARS = 200
_VOL_TRANSPARENT_KEY = "#ff00ff"


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


# ── Helpers для сохранения повтора ──
def _load_repeat_saved() -> bool:
    # 1. через theme_manager если есть новый API
    try:
        from engine.gui import theme_manager as tm

        if hasattr(tm, "get_audio_repeat"):
            return bool(tm.get_audio_repeat())
        if hasattr(tm, "get_audio_repeat_state"):
            return bool(tm.get_audio_repeat_state())
        # fallback чтение json напрямую
        if hasattr(tm, "_read_json"):
            data = tm._read_json()
            return bool(data.get("audio_repeat_one", False))
    except Exception:
        pass
    # 2. через settings.json (устаревший fallback)
    try:
        from engine.settings_store import SETTINGS_PATH

        if os.path.isfile(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
                if "audio_repeat_one" in d:
                    return bool(d["audio_repeat_one"])
    except Exception:
        pass
    # 3. прямой чтение theme_settings.json
    try:
        tf = os.path.join(str(BASE_DIR), "theme_settings.json")
        if os.path.isfile(tf):
            with open(tf, "r", encoding="utf-8") as f:
                d = json.load(f)
                return bool(d.get("audio_repeat_one", False))
    except Exception:
        pass
    return False


def _save_repeat_state(val: bool):
    try:
        from engine.gui import theme_manager as tm

        if hasattr(tm, "set_audio_repeat"):
            tm.set_audio_repeat(bool(val))
            return
        if hasattr(tm, "set_audio_repeat_state"):
            tm.set_audio_repeat_state(bool(val))
            return
        # прямой write если API нет
        if hasattr(tm, "_read_json") and hasattr(tm, "THEME_FILE"):
            data = tm._read_json()
            data["audio_repeat_one"] = bool(val)
            with open(tm.THEME_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return
    except Exception:
        pass
    # fallback в theme_settings.json напрямую
    try:
        tf = os.path.join(str(BASE_DIR), "theme_settings.json")
        data = {}
        if os.path.isfile(tf):
            try:
                with open(tf, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["audio_repeat_one"] = bool(val)
        with open(tf, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ── Helper для иконки окна аудио (фикс пера) ──
def _apply_window_icon(win: tk.Toplevel):
    """Ставит нормальную иконку окну аудио чтобы в таскбаре не было пера tkinter.
    Тянет ICON_PATH если есть, иначе ищет icon.ico / icon.png в BASE_DIR / images.
    Делает iconbitmap + iconphoto + AppUserModelID + повтор через after.
    """
    # 1. AppUserModelID чтобы Windows группировала иконку с основным приложением
    try:
        import ctypes

        # тот же ID что и у основного окна — тогда иконка не слетает
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
            os.path.join(str(BASE_DIR), "..", "icon.ico"),
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

    # iconbitmap — для заголовка окна и частично для таскбара на Win
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

    # iconphoto — более надежно для таскбара в Windows с Tk 8.6
    try:
        photo = None
        if png_file:
            try:
                photo = tk.PhotoImage(file=png_file)
            except Exception:
                photo = None
        if photo is None and ico_file:
            # попробуем через PIL если есть
            try:
                from PIL import Image, ImageTk

                im = Image.open(ico_file)
                im = im.resize((32, 32), Image.LANCZOS)
                photo = ImageTk.PhotoImage(im)
            except Exception:
                # пробуем напрямую PhotoImage с ico (иногда работает)
                try:
                    photo = tk.PhotoImage(file=ico_file)
                except Exception:
                    photo = None
        if photo is not None:
            try:
                win.iconphoto(True, photo)
                win._icon_photo_ref = photo  # keep ref
            except Exception:
                pass
    except Exception:
        pass


def open_outputs_folder():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    win = tk.Toplevel(root)
    win.title(t("win_audio_title"))
    win.geometry("820x680")
    win.minsize(640, 500)
    win.resizable(True, True)
    win.configure(bg=Colors.BG_DARK)
    # ФИКС ИКОНКИ — сразу
    _apply_window_icon(win)
    win.grab_set()

    # ── состояние плеера ──
    saved_repeat = _load_repeat_saved()
    _p = {
        "playing": False,
        "path": None,
        "pos": 0.0,
        "duration": 0.0,
        "after_id": None,
        "volume": 0.8,
        "repeat_one": bool(saved_repeat),
        "error": None,
    }
    _wave_state = {"peaks": [], "path": None}
    _card_widgets = {}
    _card_buttons = {}
    _active_path = {"v": None}
    _vol_popup = {"win": None}
    _empty_state = {"widget": None}
    _ui_refs = {"repeat_btn": None, "vol_btn": None, "play_btn": None}

    def _round_btn(parent, text, cmd, diameter=36, primary=False, danger=False):
        bg = Colors.BG_ACTIVE if primary else Colors.BG_INPUT
        if primary:
            hover = "#2ea043"
        elif danger:
            hover = Colors.BG_DANGER
        else:
            hover = Colors.BG_HOVER
        scaled_diameter = scaled_size(diameter, min_size=diameter)
        return CompatCTkButton(
            parent,
            text=text,
            command=cmd,
            width=scaled_diameter,
            height=scaled_diameter,
            corner_radius=scaled_diameter // 2,
            fg_color=bg,
            text_color=Colors.TEXT_MAIN,
            hover_color=hover,
            border_width=0,
            font=("Segoe UI", scaled_font_size(17 if primary else 15)),
        )

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

    def _file_date(path):
        try:
            ts = os.path.getmtime(path)
            d = _dt.datetime.fromtimestamp(ts)
            today = _dt.date.today()
            if d.date() == today:
                return t("time_today", d.strftime("%H:%M"))
            elif (today - d.date()).days == 1:
                return t("time_yesterday", d.strftime("%H:%M"))
            return d.strftime("%d.%m.%Y %H:%M")
        except Exception:
            return ""

    def _collect_files():
        try:
            files = [f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".wav")]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR, f)), reverse=True)
            return files
        except Exception:
            return []

    def _sorted_paths():
        return [os.path.join(OUTPUT_DIR, f) for f in _collect_files()]

    def _volume_icon(vol):
        return "🔇" if vol <= 0.001 else ("🔉" if vol < 0.5 else "🔊")

    def _redraw_waveform():
        try:
            wave_canvas.delete("all")
            w = wave_canvas.winfo_width()
            h = wave_canvas.winfo_height()
            if w <= 1 or h <= 1:
                return
            text_zone_h = 28
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

    def _refresh_card_icons():
        for p, btn in list(_card_buttons.items()):
            try:
                btn.configure(text="⏸" if (p == _p["path"] and _p["playing"]) else "▶")
            except Exception:
                pass

    def _reset_player_ui():
        _stop_ticker()
        _p.update(playing=False, path=None, pos=0.0, duration=0.0, error=None)
        _wave_state.update(peaks=[], path=None)
        try:
            _ui_refs.get("play_btn").configure(text="▶")
        except Exception:
            try:
                play_btn.configure(text="▶")
            except Exception:
                pass
        _redraw_waveform()
        _refresh_card_icons()

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
                _on_natural_end()
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
            return
        _stop_ticker()
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(_p["volume"])
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
            _refresh_card_icons()
            try:
                _ui_refs.get("play_btn").configure(text="⏸")
            except Exception:
                play_btn.configure(text="⏸")
            _tick()
        except Exception as e:
            _p["error"] = str(e)
            _redraw_waveform()

    def _card_click_play(path):
        if _p["path"] == path and _p["playing"]:
            toggle_play()
        else:
            _load_play(path, 0.0)

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
                try:
                    play_btn.configure(text="▶")
                except Exception:
                    pass
            _refresh_card_icons()
        else:
            if _p["path"] and os.path.isfile(_p["path"]):
                pygame.mixer.music.unpause()
                _p["playing"] = True
                try:
                    _ui_refs.get("play_btn").configure(text="⏸")
                except Exception:
                    try:
                        play_btn.configure(text="⏸")
                    except Exception:
                        pass
                _refresh_card_icons()
                _tick()

    def _neighbor_path(delta):
        paths = _sorted_paths()
        if not paths:
            return None
        idx = paths.index(_p["path"]) if _p["path"] in paths else (-1 if delta > 0 else 0)
        return paths[(idx + delta) % len(paths)]

    def _skip_track(delta):
        nxt = _neighbor_path(delta)
        if nxt:
            _load_play(nxt, 0.0)

    def _on_natural_end():
        if _p["repeat_one"] and _p["path"]:
            _load_play(_p["path"], 0.0)
            return
        nxt = _neighbor_path(1)
        if nxt:
            _load_play(nxt, 0.0)
        else:
            _reset_player_ui()

    def _update_repeat_btn_visual():
        btn = _ui_refs.get("repeat_btn")
        if btn is None:
            try:
                btn = repeat_btn
            except Exception:
                return
        try:
            if _p["repeat_one"]:
                btn.configure(
                    fg_color=Colors.AI_ACCENT,
                    hover_color=getattr(
                        Colors, "AI_ACCENT_HOVER", getattr(Colors, "ACCENT_HOVER", Colors.BG_HOVER)
                    ),
                    text="🔂",
                )
            else:
                btn.configure(fg_color=Colors.BG_INPUT, hover_color=Colors.BG_HOVER, text="🔁")
        except Exception:
            pass

    def _toggle_repeat():
        _p["repeat_one"] = not _p["repeat_one"]
        _save_repeat_state(_p["repeat_one"])
        _update_repeat_btn_visual()

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

    def _make_card(parent, fname):
        path = os.path.join(OUTPUT_DIR, fname)
        dur = _get_duration(path)
        try:
            size_kb = os.path.getsize(path) // 1024
        except Exception:
            size_kb = 0
        date_str = _file_date(path)
        dur_str = _fmt(dur) if dur > 0 else "--:--"
        meta = f"{dur_str}   ·   {size_kb} KB   ·   {date_str}"

        card = CompatCTkFrame(
            parent,
            fg_color=Colors.BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=Colors.BORDER,
        )
        card.pack(fill="x", padx=4, pady=5)
        _card_widgets[path] = card

        badge = CompatCTkFrame(
            card, fg_color=Colors.BG_INPUT, corner_radius=20, width=44, height=44
        )
        badge.pack(side="left", padx=(14, 10), pady=12)
        badge.pack_propagate(False)
        CompatCTkLabel(
            badge,
            text="🎵",
            fg_color=Colors.BG_INPUT,
            text_color=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(18)),
        ).pack(expand=True)

        info = tk.Frame(card, bg=Colors.BG_CARD)
        info.pack(side="left", fill="both", expand=True, pady=10)
        CompatCTkLabel(
            info,
            text=fname,
            fg_color=Colors.BG_CARD,
            text_color=Colors.TEXT_MAIN,
            font=("Segoe UI", scaled_font_size(13), "bold"),
            anchor="w",
        ).pack(fill="x")
        CompatCTkLabel(
            info,
            text=meta,
            fg_color=Colors.BG_CARD,
            text_color=Colors.TEXT_DIM,
            font=("Segoe UI", scaled_font_size(11)),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        actions = tk.Frame(card, bg=Colors.BG_CARD)
        actions.pack(side="right", padx=12)
        play_btn_card = _round_btn(actions, "▶", lambda p=path: _card_click_play(p), diameter=34)
        play_btn_card.pack(side="left", padx=(0, 6))
        _card_buttons[path] = play_btn_card
        del_btn_card = _round_btn(
            actions, "🗑", lambda p=path, c=card: _delete_file(p, c), diameter=34, danger=True
        )
        del_btn_card.pack(side="left")

        for w in (card, badge, info):
            w.bind("<Double-Button-1>", lambda e, p=path: _card_click_play(p))

    def _delete_file(path, card_widget):
        fname = os.path.basename(path)
        if not messagebox.askyesno(t("dlg_delete_title"), t("dlg_delete_msg", fname), parent=win):
            return
        if _p.get("path") == path:
            try:
                pygame.mixer.music.stop()
                if hasattr(pygame.mixer.music, "unload"):
                    pygame.mixer.music.unload()
            except Exception:
                pass
            _reset_player_ui()
        try:
            os.remove(path)
        except Exception as e:
            messagebox.showerror("❌", str(e), parent=win)
            return
        _card_widgets.pop(path, None)
        _card_buttons.pop(path, None)
        try:
            card_widget.destroy()
        except Exception:
            pass
        _update_count()
        _maybe_show_empty_state()

    def _delete_all():
        files = [f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".wav")]
        if not files:
            messagebox.showinfo(t("dlg_empty"), t("dlg_empty_msg"), parent=win)
            return
        if not messagebox.askyesno(
            t("dlg_delete_all_title"), t("dlg_delete_all_msg", len(files)), parent=win
        ):
            return
        try:
            pygame.mixer.music.stop()
            if hasattr(pygame.mixer.music, "unload"):
                pygame.mixer.music.unload()
        except Exception:
            pass
        _reset_player_ui()
        for f in files:
            try:
                os.remove(os.path.join(OUTPUT_DIR, f))
            except Exception:
                pass
        _card_widgets.clear()
        _card_buttons.clear()
        _active_path["v"] = None
        for w in list(list_frame.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        _update_count()
        _maybe_show_empty_state()

    def _clear_cache():
        cache_dirs = [
            os.path.join(BASE_DIR, "reference"),
            os.path.join(BASE_DIR, "cache"),
            os.path.join(OUTPUT_DIR, "_cache"),
        ]
        removed = 0
        for d in cache_dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.endswith((".pth", ".cache", ".wav")):
                    try:
                        os.remove(os.path.join(d, f))
                        removed += 1
                    except Exception:
                        pass
        messagebox.showinfo(
            t("cache_cleared"),
            t("cache_cleared_msg", removed) if removed else t("cache_already_empty"),
            parent=win,
        )

    def _open_folder():
        try:
            os.startfile(OUTPUT_DIR)
        except Exception:
            messagebox.showinfo("Folder", OUTPUT_DIR, parent=win)

    def _update_count():
        try:
            n = len([f for f in os.listdir(OUTPUT_DIR) if f.lower().endswith(".wav")])
        except Exception:
            n = 0
        try:
            count_lbl.configure(text=t("files_count", n))
        except Exception:
            pass

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
            lbl = CompatCTkLabel(
                list_frame,
                text="Здесь появятся ваши аудиозаписи",
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

    # LAYOUT
    header = tk.Frame(win, bg=Colors.BG_DARK, pady=12)
    header.pack(fill="x", padx=16)

    actions_pill = CompatCTkFrame(
        header,
        fg_color=Colors.BG_CARD,
        corner_radius=18,
        border_width=1,
        border_color=Colors.BORDER,
    )
    actions_pill.pack(side="left")
    actions_row = tk.Frame(actions_pill, bg=Colors.BG_CARD)
    actions_row.pack(padx=6, pady=6)
    btn_open = _round_btn(actions_row, "📂", _open_folder, diameter=34)
    btn_open.pack(side="left", padx=3)
    ToolTip(btn_open, t("btn_open_folder"))
    btn_cache = _round_btn(actions_row, "🧹", _clear_cache, diameter=34)
    btn_cache.pack(side="left", padx=3)
    ToolTip(btn_cache, t("btn_clear_cache"))
    btn_delete_all = _round_btn(actions_row, "🗑", _delete_all, diameter=34, danger=True)
    btn_delete_all.pack(side="left", padx=3)
    ToolTip(btn_delete_all, t("btn_delete_all"))

    count_pill = CompatCTkFrame(
        header,
        fg_color=Colors.BG_CARD,
        corner_radius=14,
        border_width=1,
        border_color=Colors.BORDER,
    )
    count_pill.pack(side="right")
    count_lbl = CompatCTkLabel(
        count_pill,
        text="",
        fg_color=Colors.BG_CARD,
        text_color=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(12)),
    )
    count_lbl.pack(padx=16, pady=9)

    list_frame = ctk.CTkScrollableFrame(win, fg_color=Colors.BG_DARK, corner_radius=12)
    list_frame.pack(fill="both", expand=True, padx=12, pady=(4, 6))

    for fname in _collect_files():
        _make_card(list_frame, fname)
    _update_count()
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

    btn_prev = _round_btn(ctrl_row, "⏮", lambda: _skip_track(-1), diameter=38)
    btn_prev.pack(side="left", padx=4)
    ToolTip(btn_prev, "Предыдущий трек")

    play_btn = _round_btn(ctrl_row, "▶", toggle_play, diameter=56, primary=True)
    play_btn.pack(side="left", padx=10)
    _ui_refs["play_btn"] = play_btn

    btn_next = _round_btn(ctrl_row, "⏭", lambda: _skip_track(1), diameter=38)
    btn_next.pack(side="left", padx=4)
    ToolTip(btn_next, "Следующий трек")

    repeat_btn = _round_btn(ctrl_row, "🔁", _toggle_repeat, diameter=38)
    repeat_btn.pack(side="left", padx=(16, 4))
    ToolTip(repeat_btn, "Повтор трека")
    _ui_refs["repeat_btn"] = repeat_btn
    try:
        repeat_btn.configure(command=_toggle_repeat)
    except Exception:
        pass
    # применить сохраненное состояние визуально
    _update_repeat_btn_visual()

    vol_btn = _round_btn(ctrl_row, _volume_icon(_p["volume"]), _toggle_volume_popup, diameter=38)
    vol_btn.pack(side="left", padx=4)
    ToolTip(vol_btn, "Громкость")
    _ui_refs["vol_btn"] = vol_btn

    if PYGAME_OK:
        try:
            pygame.mixer.music.set_volume(_p["volume"])
        except Exception:
            pass

    _redraw_waveform()
    # финальная попытка иконки после отрисовки
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
