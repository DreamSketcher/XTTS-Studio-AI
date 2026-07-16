# -*- coding: utf-8 -*-
"""engine/gui/theme_manager.py — сохранение/загрузка кастомной темы в theme_settings.json

Добавлено в патче 2026-07-09:
- сохранение состояния кнопки повтора аудио-окна (audio_repeat_one)
- header_rainbow + header_rainbow_style (кастомизация радужного заголовка)
"""

import json
import os

from engine.atomic_write import atomic_write_json

# ВАЖНОЕ ПРАВИЛО ПРОЕКТА: любое обращение к путям — ТОЛЬКО через BASE_DIR из engine.paths
try:
    from engine.paths import BASE_DIR

    THEME_FILE = os.path.join(str(BASE_DIR), "theme_settings.json")
except Exception:
    # Fallback для обратной совместимости, если engine.paths ещё не подключен
    _BASE_DIR = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    THEME_FILE = os.path.join(_BASE_DIR, "theme_settings.json")

DEFAULT_LAYOUT_PRESETS = {
    "classic": {
        "left_panel_width": 260,
        "padding_main_x": 8,
        "padding_main_y": 14,
        "panel_spacing": 2,
        "toggle_strip_width": 22,
        "right_panel_left_pad": 8,
        "textbox_padx": 10,
        "textbox_pady": 7,
        "toolbar_rows": 2,
        "toolbar_button_size": 32,
        "console_height": 140,
        "statusbar_height": 24,
        "item_spacing": 8,
        "padding_inner": 5,
    },
    "compact": {
        "left_panel_width": 220,
        "padding_main_x": 4,
        "padding_main_y": 8,
        "panel_spacing": 2,
        "toggle_strip_width": 18,
        "right_panel_left_pad": 4,
        "textbox_padx": 6,
        "textbox_pady": 4,
        "toolbar_rows": 1,
        "toolbar_button_size": 26,
        "console_height": 100,
        "statusbar_height": 20,
        "item_spacing": 4,
        "padding_inner": 3,
    },
    "wide": {
        "left_panel_width": 380,
        "padding_main_x": 12,
        "padding_main_y": 18,
        "panel_spacing": 4,
        "toggle_strip_width": 24,
        "right_panel_left_pad": 10,
        "textbox_padx": 14,
        "textbox_pady": 10,
        "toolbar_rows": 2,
        "toolbar_button_size": 36,
        "console_height": 180,
        "statusbar_height": 28,
        "item_spacing": 10,
        "padding_inner": 8,
    },
}

DEFAULT_THEME = {
    "colors": {
        "BG_MAIN": "#1a1b26",
        "BG_SEC": "#24283b",
        "BG_DARK": "#16161e",
        "TEXT_MAIN": "#c0caf5",
        "TEXT_DIM": "#565f89",
        "ACCENT": "#7aa2f7",
        "ACCENT_HOVER": "#8caaee",
        "ACCENT_DARK": "#3d59a1",
        "BORDER": "#414868",
        "SUCCESS": "#9ece6a",
        "ERROR": "#f7768e",
    },
    "fonts": {
        "main": "Segoe UI",
        "mono": "Consolas",
        "size_main": 10,
        "size_header": 14,
        "size_small": 9,
    },
    "geometry": {
        "padding_main": 10,
        "padding_inner": 5,
        "item_spacing": 8,
    },
    "layout": "classic",
    "layout_preset": "classic",
    "presets": DEFAULT_LAYOUT_PRESETS,
    "custom_colors": {
        "dark": {},
        "light": {},
    },
    "font_base_size": 10,
    "saved_presets": {},
    # NEW: состояние кнопки повтора аудио-окна
    "audio_repeat_one": False,
    # ── Расположение интерфейса (patch 2026-07-09) ──
    "sidebar_side": "left",
    "toolbar_order": ["file", "output", "ai", "action"],
    "header_rainbow": False,
    "header_author_rainbow": False,
    # Параметры радужного заголовка (см. get/set_header_rainbow_style)
    # target: "title" (XTTS Studio) / "author" (by EXIZ10TION)
    "header_rainbow_style": {
        "speed_ms": 40,
        "saturation": 1.0,
        "brightness": 1.0,
        "hue_offset": 0.0,
        "spread": 1.0,
        "mode": "hsv",  # "hsv" | "custom"
        "colors": [],  # hex-цвета для mode=custom (цикл градиента)
    },
    "header_author_rainbow_style": {
        "speed_ms": 50,
        "saturation": 0.75,
        "brightness": 0.95,
        "hue_offset": 0.15,
        "spread": 1.0,
        "mode": "hsv",
        "colors": [],
    },
    # Неон тулбара: у каждой кнопки свой enabled + style
    "neon_buttons": {
        "chat": {"enabled": True, "style": {}},
        "ai": {"enabled": True, "style": {}},
        "styles": {"enabled": True, "style": {}},
        "quality": {"enabled": True, "style": {}},
        "generate": {"enabled": True, "style": {}},
    },
}


def _read_json() -> dict:
    if not os.path.exists(THEME_FILE):
        return {}
    try:
        with open(THEME_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ThemeManager] Load error: {e}")
        return {}


def load_theme() -> dict:
    data = _read_json()
    if not data:
        return json.loads(json.dumps(DEFAULT_THEME))
    merged = json.loads(json.dumps(DEFAULT_THEME))
    for section in DEFAULT_THEME:
        if section in data:
            if isinstance(data[section], dict) and isinstance(merged.get(section), dict):
                merged[section].update(data[section])
            else:
                merged[section] = data[section]
    if "layout_preset" not in merged and "layout" in merged:
        merged["layout_preset"] = merged["layout"]
    return merged


def save_theme(theme_data: dict):
    try:
        current = _read_json()
        out = current.copy()
        out.update(theme_data)
        if "presets" not in out:
            out["presets"] = DEFAULT_LAYOUT_PRESETS
        if "layout_preset" in out:
            out["layout"] = out["layout_preset"]
        elif "layout" in out:
            out["layout_preset"] = out["layout"]
        atomic_write_json(THEME_FILE, out, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ThemeManager] Save error: {e}")


def get_layout_presets() -> dict:
    data = load_theme()
    presets = data.get("presets", {})
    merged = DEFAULT_LAYOUT_PRESETS.copy()
    merged.update(presets)
    return merged


def get_current_layout_preset_name() -> str:
    data = load_theme()
    name = data.get("layout_preset") or data.get("layout") or "classic"
    if name not in get_layout_presets():
        return "classic"
    return name


def get_layout_preset(name: str | None = None) -> dict:
    presets = get_layout_presets()
    if name is None:
        name = get_current_layout_preset_name()
    preset = presets.get(name)
    if preset is None:
        preset = presets.get("classic", DEFAULT_LAYOUT_PRESETS["classic"])
    return preset.copy()


def set_layout_preset(name: str) -> bool:
    presets = get_layout_presets()
    if name not in presets:
        return False
    data = _read_json()
    data["layout_preset"] = name
    data["layout"] = name
    if "presets" not in data:
        data["presets"] = DEFAULT_LAYOUT_PRESETS
    try:
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_layout_preset error: {e}")
        return False


def load_layout_preset(name: str | None = None) -> dict:
    return get_layout_preset(name)


def is_layout_hint_shown() -> bool:
    data = _read_json()
    return bool(data.get("layout_hint_shown", False))


def mark_layout_hint_shown() -> None:
    try:
        data = _read_json()
        data["layout_hint_shown"] = True
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ThemeManager] mark_layout_hint_shown error: {e}")


# ── NEW: сохранение состояния кнопки повтора аудио-окна ──
def get_audio_repeat() -> bool:
    """Возвращает сохраненное состояние повтора (True = повтор одного трека)."""
    data = _read_json()
    return bool(data.get("audio_repeat_one", False))


# Алиасы для совместимости
def get_audio_repeat_state() -> bool:
    return get_audio_repeat()


def is_audio_repeat() -> bool:
    return get_audio_repeat()


def set_audio_repeat(value: bool) -> bool:
    """Сохраняет состояние повтора в theme_settings.json, не затирая остальные ключи."""
    try:
        data = _read_json()
        data["audio_repeat_one"] = bool(value)
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_audio_repeat error: {e}")
        return False


def set_audio_repeat_state(value: bool) -> bool:
    return set_audio_repeat(value)


def get_custom_colors(theme_name: str) -> dict:
    data = load_theme()
    custom = data.get("custom_colors", {})
    if not isinstance(custom, dict):
        return {}
    theme_colors = custom.get(theme_name, {})
    return theme_colors.copy() if isinstance(theme_colors, dict) else {}


def set_custom_colors(theme_name: str, colors: dict) -> bool:
    if theme_name not in ("dark", "light"):
        return False
    try:
        data = _read_json()
        if "custom_colors" not in data or not isinstance(data["custom_colors"], dict):
            data["custom_colors"] = {"dark": {}, "light": {}}
        data["custom_colors"][theme_name] = dict(colors)
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_custom_colors error: {e}")
        return False


def reset_custom_colors(theme_name: str) -> bool:
    return set_custom_colors(theme_name, {})


def get_font_base_size() -> int:
    data = load_theme()
    try:
        return int(data.get("font_base_size", 10))
    except Exception:
        return 10


def set_font_base_size(base_size: int) -> bool:
    try:
        base_size = max(6, min(24, int(base_size)))
    except Exception:
        return False
    try:
        data = _read_json()
        data["font_base_size"] = base_size
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_font_base_size error: {e}")
        return False


# ── Расположение интерфейса: боковая панель + порядок тулбара ──
TOOLBAR_PANELS = ["file", "output", "ai", "action"]
DEFAULT_TOOLBAR_ORDER = ["file", "output", "ai", "action"]


def get_sidebar_side() -> str:
    """Возвращает 'left' или 'right'. По умолчанию 'left'."""
    data = load_theme()
    side = data.get("sidebar_side", "left")
    return side if side in ("left", "right") else "left"


def set_sidebar_side(side: str) -> bool:
    side = (side or "left").lower()
    if side not in ("left", "right"):
        return False
    try:
        data = _read_json()
        data["sidebar_side"] = side
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_sidebar_side error: {e}")
        return False


def get_toolbar_order() -> list:
    """Возвращает порядок панелей тулбара. Гарантирует валидность."""
    data = load_theme()
    order = data.get("toolbar_order")
    if not isinstance(order, list):
        return DEFAULT_TOOLBAR_ORDER.copy()
    # Фильтрация + дополнение недостающими
    clean = []
    seen = set()
    for x in order:
        if x in TOOLBAR_PANELS and x not in seen:
            clean.append(x)
            seen.add(x)
    # Добавляем недостающие в порядке по умолчанию
    for x in DEFAULT_TOOLBAR_ORDER:
        if x not in seen:
            clean.append(x)
            seen.add(x)
    # Обрезаем лишнее
    return clean[: len(TOOLBAR_PANELS)]


def set_toolbar_order(order: list) -> bool:
    """Сохраняет порядок панелей тулбара. Принимает list[str]."""
    if not isinstance(order, (list, tuple)):
        return False
    clean = []
    seen = set()
    for x in order:
        if x in TOOLBAR_PANELS and x not in seen:
            clean.append(x)
            seen.add(x)
    # Дополняем недостающими
    for x in DEFAULT_TOOLBAR_ORDER:
        if x not in seen:
            clean.append(x)
    try:
        data = _read_json()
        data["toolbar_order"] = clean
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_toolbar_order error: {e}")
        return False


DEFAULT_HEADER_RAINBOW_STYLE = {
    "speed_ms": 40,
    "saturation": 1.0,
    "brightness": 1.0,
    "hue_offset": 0.0,
    "spread": 1.0,
    "mode": "hsv",  # "hsv" (классическая радуга) | "custom" (палитра colors)
    "colors": [],  # ["#ff006e", "#8338ec", ...] — для mode=custom
}

DEFAULT_HEADER_AUTHOR_RAINBOW_STYLE = {
    "speed_ms": 50,
    "saturation": 0.75,
    "brightness": 0.95,
    "hue_offset": 0.15,
    "spread": 1.0,
    "mode": "hsv",
    "colors": [],
}

_HEX_RE = __import__("re").compile(r"^#?[0-9A-Fa-f]{6}$")


def _clamp(v, lo, hi, default):
    try:
        v = float(v)
    except Exception:
        return default
    return max(lo, min(hi, v))


def _norm_hex(c) -> str | None:
    if not isinstance(c, str):
        return None
    s = c.strip()
    if not s:
        return None
    if not s.startswith("#"):
        s = "#" + s
    if _HEX_RE.match(s):
        return s.lower()
    return None


def _normalize_rainbow_style(raw, defaults: dict | None = None) -> dict:
    """Валидирует/нормализует dict стиля радуги. Неизвестные ключи отбрасываются."""
    base = dict(defaults or DEFAULT_HEADER_RAINBOW_STYLE)
    if not isinstance(raw, dict):
        return base
    base["speed_ms"] = int(_clamp(raw.get("speed_ms", base["speed_ms"]), 16, 200, base["speed_ms"]))
    base["saturation"] = round(
        _clamp(raw.get("saturation", base["saturation"]), 0.0, 1.0, base["saturation"]), 3
    )
    base["brightness"] = round(
        _clamp(raw.get("brightness", base["brightness"]), 0.15, 1.0, base["brightness"]), 3
    )
    base["hue_offset"] = round(
        _clamp(raw.get("hue_offset", base["hue_offset"]), 0.0, 1.0, base["hue_offset"]), 3
    )
    base["spread"] = round(_clamp(raw.get("spread", base["spread"]), 0.2, 2.0, base["spread"]), 3)
    mode = str(raw.get("mode", base.get("mode", "hsv"))).lower().strip()
    base["mode"] = mode if mode in ("hsv", "custom") else "hsv"
    colors_in = raw.get("colors", base.get("colors", []))
    colors = []
    if isinstance(colors_in, (list, tuple)):
        for c in colors_in:
            hx = _norm_hex(c)
            if hx and hx not in colors:
                colors.append(hx)
            if len(colors) >= 12:
                break
    base["colors"] = colors
    # custom без цветов → откат на hsv при рендере, но mode сохраняем
    return base


def get_header_rainbow() -> bool:
    """Возвращает True если радужный заголовок (XTTS Studio) включён"""
    data = load_theme()
    return bool(data.get("header_rainbow", False))


def set_header_rainbow(enabled: bool) -> bool:
    try:
        data = _read_json()
        data["header_rainbow"] = bool(enabled)
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_header_rainbow error: {e}")
        return False


def get_header_author_rainbow() -> bool:
    """Радужный подзаголовок «by EXIZ10TION»."""
    data = load_theme()
    return bool(data.get("header_author_rainbow", False))


def set_header_author_rainbow(enabled: bool) -> bool:
    try:
        data = _read_json()
        data["header_author_rainbow"] = bool(enabled)
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_header_author_rainbow error: {e}")
        return False


def get_header_rainbow_style() -> dict:
    """Стиль радуги для заголовка XTTS Studio."""
    data = load_theme()
    return _normalize_rainbow_style(data.get("header_rainbow_style"), DEFAULT_HEADER_RAINBOW_STYLE)


def set_header_rainbow_style(style: dict) -> bool:
    """Сохраняет параметры радужного заголовка (частичное обновление допускается)."""
    try:
        current = get_header_rainbow_style()
        if isinstance(style, dict):
            current.update(style)
        normalized = _normalize_rainbow_style(current, DEFAULT_HEADER_RAINBOW_STYLE)
        data = _read_json()
        data["header_rainbow_style"] = normalized
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_header_rainbow_style error: {e}")
        return False


def reset_header_rainbow_style() -> bool:
    """Сброс параметров радуги заголовка к заводским (флаг on/off не трогаем)."""
    return set_header_rainbow_style(dict(DEFAULT_HEADER_RAINBOW_STYLE))


def get_header_author_rainbow_style() -> dict:
    """Стиль радуги для подписи by EXIZ10TION."""
    data = load_theme()
    return _normalize_rainbow_style(
        data.get("header_author_rainbow_style"),
        DEFAULT_HEADER_AUTHOR_RAINBOW_STYLE,
    )


def set_header_author_rainbow_style(style: dict) -> bool:
    try:
        current = get_header_author_rainbow_style()
        if isinstance(style, dict):
            current.update(style)
        normalized = _normalize_rainbow_style(current, DEFAULT_HEADER_AUTHOR_RAINBOW_STYLE)
        data = _read_json()
        data["header_author_rainbow_style"] = normalized
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_header_author_rainbow_style error: {e}")
        return False


def reset_header_author_rainbow_style() -> bool:
    return set_header_author_rainbow_style(dict(DEFAULT_HEADER_AUTHOR_RAINBOW_STYLE))


# ── Neon toolbar buttons ─────────────────────────────────────────────────────
NEON_BUTTON_IDS = ("chat", "ai", "styles", "quality", "generate")

DEFAULT_NEON_BUTTON_ENTRY = {
    "enabled": True,
    "style": {},  # partial override of DEFAULT_HEADER_RAINBOW_STYLE
}


def _normalize_neon_buttons(raw) -> dict:
    out = {}
    src = raw if isinstance(raw, dict) else {}
    for bid in NEON_BUTTON_IDS:
        entry = src.get(bid, {})
        if not isinstance(entry, dict):
            # legacy: bool
            if isinstance(entry, bool):
                entry = {"enabled": entry, "style": {}}
            else:
                entry = {}
        enabled = bool(entry.get("enabled", True))
        style_raw = entry.get("style") if isinstance(entry.get("style"), dict) else {}
        # merge with defaults then normalize
        base = dict(DEFAULT_HEADER_RAINBOW_STYLE)
        base.update(style_raw)
        style = _normalize_rainbow_style(base, DEFAULT_HEADER_RAINBOW_STYLE)
        out[bid] = {"enabled": enabled, "style": style}
    return out


def get_neon_buttons() -> dict:
    data = load_theme()
    return _normalize_neon_buttons(data.get("neon_buttons"))


def set_neon_buttons(buttons: dict) -> bool:
    try:
        normalized = _normalize_neon_buttons(buttons)
        data = _read_json()
        data["neon_buttons"] = normalized
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] set_neon_buttons error: {e}")
        return False


def get_neon_button_enabled(button_id: str) -> bool:
    return bool(get_neon_buttons().get(button_id, {}).get("enabled", True))


def set_neon_button_enabled(button_id: str, enabled: bool) -> bool:
    if button_id not in NEON_BUTTON_IDS:
        return False
    buttons = get_neon_buttons()
    buttons[button_id]["enabled"] = bool(enabled)
    return set_neon_buttons(buttons)


def get_neon_button_style(button_id: str) -> dict:
    return dict(get_neon_buttons().get(button_id, {}).get("style") or DEFAULT_HEADER_RAINBOW_STYLE)


def set_neon_button_style(button_id: str, style: dict) -> bool:
    if button_id not in NEON_BUTTON_IDS:
        return False
    buttons = get_neon_buttons()
    cur = dict(buttons[button_id].get("style") or {})
    if isinstance(style, dict):
        cur.update(style)
    buttons[button_id]["style"] = _normalize_rainbow_style(cur, DEFAULT_HEADER_RAINBOW_STYLE)
    return set_neon_buttons(buttons)


def get_saved_presets() -> dict:
    data = load_theme()
    presets = data.get("saved_presets", {})
    return presets if isinstance(presets, dict) else {}


def save_named_preset(preset_name: str, snapshot: dict) -> bool:
    preset_name = (preset_name or "").strip()
    if not preset_name:
        return False
    try:
        data = _read_json()
        if "saved_presets" not in data or not isinstance(data["saved_presets"], dict):
            data["saved_presets"] = {}
        data["saved_presets"][preset_name] = dict(snapshot)
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] save_named_preset error: {e}")
        return False


def delete_named_preset(preset_name: str) -> bool:
    try:
        data = _read_json()
        presets = data.get("saved_presets", {})
        if not isinstance(presets, dict) or preset_name not in presets:
            return False
        del presets[preset_name]
        data["saved_presets"] = presets
        atomic_write_json(THEME_FILE, data, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ThemeManager] delete_named_preset error: {e}")
        return False


def apply_named_preset(preset_name: str) -> dict | None:
    presets = get_saved_presets()
    snapshot = presets.get(preset_name)
    if not isinstance(snapshot, dict):
        return None
    theme_name = snapshot.get("theme_name", "dark")
    custom_colors = snapshot.get("custom_colors", {})
    font_base_size = snapshot.get("font_base_size", 10)
    layout_preset_name = snapshot.get("layout_preset", "classic")

    set_custom_colors(theme_name, custom_colors)
    set_font_base_size(font_base_size)
    set_layout_preset(layout_preset_name)

    # ── Расположение интерфейса ──
    sidebar_side = snapshot.get("sidebar_side")
    if sidebar_side in ("left", "right"):
        set_sidebar_side(sidebar_side)
    toolbar_order = snapshot.get("toolbar_order")
    if isinstance(toolbar_order, list):
        set_toolbar_order(toolbar_order)

    # header rainbow (title + author)
    if "header_rainbow" in snapshot:
        set_header_rainbow(bool(snapshot.get("header_rainbow", False)))
    if "header_rainbow_style" in snapshot:
        set_header_rainbow_style(snapshot.get("header_rainbow_style") or {})
    if "header_author_rainbow" in snapshot:
        set_header_author_rainbow(bool(snapshot.get("header_author_rainbow", False)))
    if "header_author_rainbow_style" in snapshot:
        set_header_author_rainbow_style(snapshot.get("header_author_rainbow_style") or {})
    if "neon_buttons" in snapshot:
        set_neon_buttons(snapshot.get("neon_buttons") or {})

    return snapshot.copy()
