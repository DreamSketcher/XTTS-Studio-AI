# -*- coding: utf-8 -*-
"""engine/gui/voice_panel.py — карточки «Голос-референс» и «Библиотека» — единый размер

Библиотека голосов читается из VoiceManager → library/<voice>/normalized.wav
(НЕ reference/backup). Кеш эмбеддинга лежит рядом с normalized.wav.
"""
import os
import tkinter as tk
import pygame

from i18n import t
from engine.gui.colors import Colors, scaled_font_size
from engine.gui.tooltip import ToolTip
from engine.gui.widgets import create_card, create_button, create_entry
from engine.gui.statusbar import set_status
from engine.gui.player import (pick_reference, pick_backup_reference, play_reference, seek_back, seek_forward)
from engine.gui import player

root = None
PYGAME_OK = False
ref_var = None
voice_manager = None
LIBRARY_DIR = None  # внедряется из main_window → BASE_DIR/library

voice_map = {}

ref_card = None
ref_btn_row = None
ref_info_label = None
voice_card = None
voice_header = None
_voice_label_var = None
voice_list_frame = None
voice_listbox = None
voice_btn_row = None
lib_btn = None
play_btn = None

def init(**deps):
    globals().update(deps)

def set_ref_info_font_size(base_size: int):
    """Меняет размер текста 'Конвертирован в WAV...' только в карточке голос-референс"""
    global ref_info_label
    try:
        if ref_info_label and ref_info_label.winfo_exists():
            ref_info_label.configure(font=("Consolas", scaled_font_size(base_size)))
    except Exception:
        pass

def refresh_voice_list():
    # Перескан library/ (VoiceManager.library_dir / backup_dir / root)
    try:
        # если main_window поправил путь — подтянем
        for attr in ("library_dir", "backup_dir", "root", "voices_dir", "base_dir"):
            if voice_manager is not None and hasattr(voice_manager, attr):
                cur = getattr(voice_manager, attr, None)
                if cur and ("reference" in str(cur).replace("\\", "/").lower()) and ("library" not in str(cur).replace("\\", "/").lower()):
                    try:
                        fixed = LIBRARY_DIR
                        if not fixed:
                            from engine.paths import BASE_DIR
                            fixed = os.path.join(str(BASE_DIR), "library")
                        setattr(voice_manager, attr, fixed)
                    except Exception:
                        pass
    except Exception:
        pass
    voice_manager.scan_voices()
    voice_listbox.delete(0, tk.END)
    voice_map.clear()
    for voice in voice_manager.list_voices():
        voice_map[voice.name] = voice
        voice_listbox.insert(tk.END, f"🎤 {voice.name}")

def _voice_dir(voice) -> str | None:
    """Папка голоса: library/<name>/ (из Voice.path / .dir / .folder)."""
    for attr in ("path", "dir", "folder", "voice_dir", "directory"):
        p = getattr(voice, attr, None)
        if p and os.path.isdir(str(p)):
            return str(p)
    return None


def _resolve_normalized_path(voice) -> str | None:
    """Ищет library/<voice>/normalized.wav (и совместимые варианты).

    VoiceManager может отдавать:
      - voice.normalized = "normalized.wav"  + voice.path = ".../library/Name"
      - voice.normalized = полный путь
      - только voice.path — тогда сканируем папку
    """
    voice_path = _voice_dir(voice)
    normalized_file = getattr(voice, "normalized", None) or getattr(voice, "normalized_path", None)

    candidates = []
    if normalized_file:
        nf = str(normalized_file)
        if os.path.isabs(nf) or os.path.dirname(nf):
            candidates.append(nf)
        if voice_path:
            candidates.append(os.path.join(voice_path, os.path.basename(nf)))
            candidates.append(os.path.join(voice_path, nf))
    if voice_path:
        candidates.append(os.path.join(voice_path, "normalized.wav"))
        candidates.append(os.path.join(voice_path, "normalized.mp3"))

    seen = set()
    for c in candidates:
        c = os.path.normpath(c)
        if c in seen:
            continue
        seen.add(c)
        if os.path.isfile(c):
            return c

    # fallback: любой wav/mp3 в папке голоса (кроме явных кеш-файлов)
    if voice_path and os.path.isdir(voice_path):
        skip_ext = {".pt", ".pth", ".npy", ".json", ".txt", ".pkl"}
        # сначала normalized*, потом остальные
        files = sorted(os.listdir(voice_path), key=lambda f: (0 if f.lower().startswith("normalized") else 1, f.lower()))
        for f in files:
            fl = f.lower()
            if fl.endswith((".wav", ".mp3", ".flac", ".ogg")):
                return os.path.join(voice_path, f)
            # не цепляем кеш эмбеддинга как «аудио»
            if os.path.splitext(fl)[1] in skip_ext:
                continue
    return None

def on_voice_select(event):
    selection = voice_listbox.curselection()
    if not selection:
        return
    raw_name = voice_listbox.get(selection[0])
    voice_name = raw_name.replace("🎤 ", "").strip()
    voice = voice_map.get(voice_name) or voice_manager.get_voice(voice_name)
    if not voice:
        return
    try:
        voice_manager.set_active(voice_name)
    except Exception:
        pass
    ref_loaded = False
    normalized_path = _resolve_normalized_path(voice)
    if normalized_path:
        ref_var.set(normalized_path)
        ref_loaded = True
    if ref_loaded:
        if PYGAME_OK and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        if PYGAME_OK:
            root.after(100, play_reference)
    set_status(t("active_voice", voice_name))

def build_voice_cards(left_panel):
    global ref_card, ref_btn_row, ref_info_label, voice_card, voice_header, _voice_label_var
    global voice_list_frame, voice_listbox, voice_btn_row, lib_btn, play_btn

    UNIFIED = 165  # все 4 окна левой панели одинакового размера

    # Reference
    ref_card = create_card(left_panel, t("card_voice_ref"))
    ref_card.pack(fill="x", pady=(0, 6))
    try:
        ref_card.configure(height=UNIFIED)
        ref_card.pack_propagate(False)
    except Exception:
        pass
    create_entry(ref_card, ref_var).pack(fill="x", padx=10, pady=(3, 5))
    ref_btn_row = tk.Frame(ref_card, bg=Colors.BG_CARD)
    ref_btn_row.pack(fill="x", padx=10, pady=(0, 4))
    create_button(ref_btn_row, t("btn_pick_ref"), pick_reference, bg=Colors.BG_INPUT, font_size=10, height=0.75).pack(side="left", ipady=0)
    # Только эта карточка меняет шрифт — сохраняем ссылку
    ref_info_label = tk.Label(ref_card, text=t("ref_info"), bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
             font=("Consolas", scaled_font_size(9)), justify="left", anchor="w")
    ref_info_label.pack(fill="x", padx=10, pady=(1, 3))

    # Voice library — тот же размер 165
    voice_card = create_card(left_panel, "")
    voice_card.pack(fill="x", pady=(0, 6))
    try:
        voice_card.configure(height=UNIFIED)
        voice_card.pack_propagate(False)
    except Exception:
        pass

    voice_header = tk.Frame(voice_card, bg=Colors.BG_CARD)
    voice_header.pack(fill="x", padx=10, pady=(6, 4))
    tk.Label(voice_header, text=t("card_voice_lib"), bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
             font=("Segoe UI", scaled_font_size(9), "bold"), anchor="w").pack(side="left")

    def _voice_display_name() -> str:
        p = ref_var.get().strip()
        if not p:
            return ""
        folder = os.path.basename(os.path.dirname(p))
        name = os.path.splitext(os.path.basename(p))[0]
        return folder if name.lower() == "normalized" else name

    _voice_label_var = tk.StringVar()
    def _update_voice_label(*_):
        _voice_label_var.set(_voice_display_name())
    ref_var.trace_add("write", _update_voice_label)
    _update_voice_label()

    tk.Label(voice_header, textvariable=_voice_label_var, bg=Colors.BG_CARD, fg=Colors.TEXT_DIM,
             font=("Segoe UI", scaled_font_size(7)), anchor="e", width=16).pack(side="right")

    tk.Frame(voice_card, bg=Colors.BORDER, height=1).pack(fill="x", padx=10, pady=(0, 3))
    voice_list_frame = tk.Frame(voice_card, bg=Colors.BORDER, highlightthickness=0, padx=1, pady=1)
    voice_list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 4))
    voice_listbox = tk.Listbox(
        voice_list_frame, height=4,
        bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
        selectbackground=Colors.ACCENT, selectforeground=Colors.TEXT_MAIN,
        relief="flat", highlightthickness=0,
        font=("Segoe UI", scaled_font_size(9)), activestyle="none", exportselection=False
    )
    voice_listbox.pack(fill="both", expand=True)
    voice_listbox.bind("<<ListboxSelect>>", on_voice_select)

    tk.Frame(voice_card, bg=Colors.BORDER, height=1).pack(fill="x", padx=10, pady=(0, 4))
    voice_btn_row = tk.Frame(voice_card, bg=Colors.BG_CARD)
    voice_btn_row.pack(fill="x", padx=10, pady=(0, 6))

    lib_btn = create_button(voice_btn_row, "📂", pick_backup_reference, bg=Colors.BG_INPUT, width=3)
    lib_btn.pack(side="left", padx=(0, 2))
    ToolTip(lib_btn, t("tip_pick_from_lib"))
    create_button(voice_btn_row, "⏪", seek_back, bg=Colors.BG_INPUT, width=3).pack(side="left", padx=(0, 2))
    play_btn = create_button(voice_btn_row, "▶ ", play_reference, bg=Colors.BG_ACTIVE, width=3)
    play_btn.pack(side="left", padx=(0, 2))
    create_button(voice_btn_row, "⏩", seek_forward, bg=Colors.BG_INPUT, width=3).pack(side="left", padx=(0, 2))
    player.play_btn = play_btn

    def _volume_icon(vol):
        return "🔇" if vol <= 0.001 else ("🔉" if vol < 0.5 else "🔊")
    vol_btn = create_button(voice_btn_row, _volume_icon(player.get_volume()), None, bg=Colors.BG_INPUT, width=3)
    vol_btn.pack(side="left")
    _vol_popup = {"win": None, "click_bind": None}
    def _close_volume_popup(event=None):
        if _vol_popup["click_bind"] is not None:
            try:
                root.unbind_all("<Button-1>")
            except Exception:
                pass
            _vol_popup["click_bind"] = None
        w = _vol_popup["win"]
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass
            _vol_popup["win"] = None
    def _toggle_volume_popup():
        if _vol_popup["win"] is not None:
            _close_volume_popup()
            return
        from tkinter import ttk
        popup = tk.Toplevel(vol_btn)
        popup.overrideredirect(True)
        popup.configure(bg=Colors.BG_CARD, highlightthickness=1, highlightbackground=Colors.BORDER)
        popup.attributes("-topmost", True)
        popup_w, popup_h = 44, 150
        x = vol_btn.winfo_rootx() - (popup_w - vol_btn.winfo_width()) // 2
        y = vol_btn.winfo_rooty() - popup_h - 4
        popup.geometry(f"{popup_w}x{popup_h}+{x}+{y}")
        inner = tk.Frame(popup, bg=Colors.BG_CARD)
        inner.pack(fill="both", expand=True, padx=6, pady=6)
        icon_lbl = tk.Label(inner, text=_volume_icon(player.get_volume()), bg=Colors.BG_CARD, fg=Colors.TEXT_DIM, font=("Segoe UI", scaled_font_size(9)))
        icon_lbl.pack(side="bottom", pady=(6, 0))
        vol_var = tk.DoubleVar(value=player.get_volume() * 100)
        def _on_change(val):
            vol = max(0.0, min(1.0, float(val) / 100.0))
            player.set_volume(vol)
            icon = _volume_icon(vol)
            icon_lbl.config(text=icon)
            vol_btn.config(text=icon)
        scale = ttk.Scale(inner, from_=100, to=0, orient="vertical", variable=vol_var, command=_on_change)
        scale.pack(side="top", fill="y", expand=True)
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
        _vol_popup["click_bind"] = root.bind_all("<Button-1>", _on_global_click, add="+")
        _vol_popup["win"] = popup
    vol_btn.config(command=_toggle_volume_popup)
    ToolTip(vol_btn, "Громкость")
