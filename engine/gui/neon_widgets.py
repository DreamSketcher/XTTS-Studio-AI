# -*- coding: utf-8 -*-
"""engine/gui/neon_widgets.py — неоновые кнопки БЕЗ обводки.

База: обычные скруглённые CompatCTkButton / create_button.
Неон: яркий цвет текста + мягкий hue-pulse (только text_color).
Вкл/выкл и стиль — из theme_manager.neon_buttons[button_id].
"""
from __future__ import annotations

import colorsys
from typing import Callable, Optional

from engine.gui.colors import Colors
from engine.gui.widgets import create_button


def _hex_to_rgb(h: str):
    h = (h or "#7aa2f7").lstrip("#")
    if len(h) != 6:
        return (122, 162, 247)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r, g, b):
    return f"#{max(0, min(255, int(r))):02x}{max(0, min(255, int(g))):02x}{max(0, min(255, int(b))):02x}"


def _shift_hue(hex_color: str, dh: float, sat_boost: float = 1.2, val_boost: float = 1.08) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    h = (h + dh) % 1.0
    s = max(0.65, min(1.0, s * sat_boost))
    v = max(0.8, min(1.0, v * val_boost))
    rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)
    return _rgb_to_hex(rr * 255, gg * 255, bb * 255)


def _style_to_base_color(style: dict, fallback: str) -> str:
    """Базовый цвет неона из style (custom colors[0] или hue_offset HSV)."""
    try:
        mode = str(style.get("mode", "hsv")).lower()
        colors = style.get("colors") or []
        if mode == "custom" and colors:
            c0 = colors[0]
            if isinstance(c0, str) and len(c0.lstrip("#")) == 6:
                return c0 if c0.startswith("#") else ("#" + c0)
        hue = float(style.get("hue_offset", 0.0)) % 1.0
        sat = max(0.55, min(1.0, float(style.get("saturation", 1.0))))
        val = max(0.75, min(1.0, float(style.get("brightness", 1.0))))
        r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
        return _rgb_to_hex(r * 255, g * 255, b * 255)
    except Exception:
        return fallback


def _load_button_cfg(button_id: str | None) -> tuple[bool, dict]:
    if not button_id:
        return True, {}
    try:
        from engine.gui import theme_manager as tm

        buttons = tm.get_neon_buttons()
        entry = buttons.get(button_id) or {}
        return bool(entry.get("enabled", True)), dict(entry.get("style") or {})
    except Exception:
        return True, {}


class _NeonPulse:
    def __init__(self, btn, base_color: str, speed_ms: int = 90):
        self.btn = btn
        self.base = base_color
        self.speed_ms = max(40, min(200, int(speed_ms)))
        self.hue = 0.0
        self.timer = None
        self.alive = True
        try:
            btn.bind("<Destroy>", self._on_destroy, add="+")
        except Exception:
            pass
        try:
            btn.after(350, self._tick)
        except Exception:
            pass

    def _on_destroy(self, _e=None):
        self.alive = False
        self._stop()

    def _stop(self):
        if self.timer is not None:
            try:
                self.btn.after_cancel(self.timer)
            except Exception:
                pass
        self.timer = None

    def _tick(self):
        if not self.alive:
            return
        try:
            if not self.btn.winfo_exists():
                return
            self.hue = (self.hue + 0.018) % 1.0
            col = _shift_hue(self.base, self.hue)
            try:
                self.btn.configure(text_color=col)
            except Exception:
                try:
                    self.btn.configure(fg=col)
                except Exception:
                    pass
            self.timer = self.btn.after(self.speed_ms, self._tick)
        except Exception:
            self.timer = None

    def set_base(self, color: str):
        self.base = color


def create_neon_button(
    parent,
    text,
    command,
    font_size=12,
    height=34,
    padx=10,
    bg=None,
    fg=None,
    button_id: str | None = None,
    width=None,
    **kwargs,
):
    """Скруглённая кнопка; neon pulse если neon_buttons[button_id].enabled."""
    enabled, style = _load_button_cfg(button_id)

    if bg is None:
        bg = getattr(Colors, "BG_INPUT", None)

    default_fg = fg or getattr(Colors, "AI_ACCENT", None) or getattr(Colors, "ACCENT", "#7aa2f7")
    if enabled and style:
        neon_fg = _style_to_base_color(style, default_fg)
    else:
        neon_fg = default_fg if enabled else (getattr(Colors, "TEXT_MAIN", "#c0caf5"))

    h_units = max(1.0, float(height) / 28.0) if height else 1.0

    btn = create_button(
        parent,
        text,
        command,
        bg=bg,
        fg=neon_fg if enabled else getattr(Colors, "TEXT_MAIN", "#c0caf5"),
        active_bg=getattr(Colors, "BG_HOVER", None),
        height=h_units,
        font_size=font_size,
        width=width,
    )
    try:
        btn.configure(
            border_width=0,
            corner_radius=10,
            anchor="center",
            text_color=neon_fg if enabled else getattr(Colors, "TEXT_MAIN", "#c0caf5"),
        )
    except Exception:
        try:
            btn.configure(border_width=0, corner_radius=10, anchor="center")
        except Exception:
            pass

    btn._neon_button_id = button_id  # type: ignore[attr-defined]
    btn._neon_enabled = enabled  # type: ignore[attr-defined]

    if enabled:
        speed = 90
        try:
            # speed_ms style ~ frame delay; map to pulse delay
            speed = max(50, min(160, int(style.get("speed_ms", 40)) + 50))
        except Exception:
            pass
        try:
            btn._neon_pulse = _NeonPulse(btn, neon_fg, speed_ms=speed)  # type: ignore[attr-defined]
        except Exception:
            pass
    else:
        btn._neon_pulse = None  # type: ignore[attr-defined]

    return btn


def refresh_neon_button(btn) -> None:
    """Перечитать настройки и обновить pulse (после Сохранить в конструкторе)."""
    if btn is None:
        return
    bid = getattr(btn, "_neon_button_id", None)
    enabled, style = _load_button_cfg(bid)
    default_fg = getattr(Colors, "AI_ACCENT", None) or getattr(Colors, "ACCENT", "#7aa2f7")
    neon_fg = (
        _style_to_base_color(style, default_fg)
        if enabled
        else getattr(Colors, "TEXT_MAIN", "#c0caf5")
    )
    btn._neon_enabled = enabled
    try:
        btn.configure(text_color=neon_fg)
    except Exception:
        pass
    pulse = getattr(btn, "_neon_pulse", None)
    if enabled:
        if pulse is None:
            try:
                speed = max(50, min(160, int(style.get("speed_ms", 40)) + 50))
                btn._neon_pulse = _NeonPulse(btn, neon_fg, speed_ms=speed)
            except Exception:
                pass
        else:
            try:
                pulse.set_base(neon_fg)
                if pulse.timer is None and pulse.alive:
                    pulse._tick()
            except Exception:
                pass
    else:
        if pulse is not None:
            try:
                pulse._stop()
                pulse.alive = False
            except Exception:
                pass
            btn._neon_pulse = None
