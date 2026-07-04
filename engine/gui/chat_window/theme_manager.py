import json
import os

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
THEME_FILE = os.path.join(_BASE_DIR, "theme_settings.json")

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
    "layout": "classic"
}

def load_theme() -> dict:
    if not os.path.exists(THEME_FILE):
        return DEFAULT_THEME
    try:
        with open(THEME_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with default to ensure all keys exist
            merged = DEFAULT_THEME.copy()
            for section in DEFAULT_THEME:
                if section in data and isinstance(data[section], dict):
                    merged[section].update(data[section])
                elif section in data:
                    merged[section] = data[section]
            return merged
    except Exception:
        return DEFAULT_THEME

def save_theme(theme_data: dict):
    try:
        with open(THEME_FILE, "w", encoding="utf-8") as f:
            json.dump(theme_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ThemeManager] Save error: {e}")
