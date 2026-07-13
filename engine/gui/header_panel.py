# -*- coding: utf-8 -*-
"""engine/gui/header_panel.py — шапка левой панели (заголовок, кнопки
Обновить / AI статус / RU-EN) (перенесено из gui.py: секция LEFT PANEL header,
_switch_ui_lang).

PATCH 2026-07-09: радужный анимированный заголовок XTTS Studio
PATCH 2026-07-09b: кастомизация (speed/sat/bri/hue/spread)
PATCH 2026-07-09c: custom colors + отдельный rainbow для «by EXIZ10TION»
PATCH 2026-07-09d: неоновый glow (neon) вместо плоской радуги
"""
import tkinter as tk
from tkinter import messagebox

from i18n import t, set_language

from engine.gui.colors import Colors, scaled_font_size
from engine.gui.tooltip import ToolTip
from engine.gui.widgets import CompatCTkFrame, create_button
from engine.gui.env_settings import check_and_update
from engine.gui.ai_status_window import open_ai_status_window

# Внедряются из main_window: root, ui_lang_var, save_settings
root = None
ui_lang_var = None
save_settings = None

# Виджеты (создаются в build_header)
header_frame = None
title_row = None
header_btn_row = None
upd_btn = None
ai_status_btn = None
ui_lang_btn = None

# --- Rainbow header state ---
_title_label = None
_title_canvas = None
_rainbow_frames = []  # list[PhotoImage] – держим ссылки, иначе GC съест
_rainbow_timer = None
_rainbow_index = 0
_rainbow_enabled = False
_rainbow_text = "XTTS Studio"
_rainbow_font_size = 16
_rainbow_last_scale = None
_rainbow_style = {
    "speed_ms": 40,
    "saturation": 1.0,
    "brightness": 1.0,
    "hue_offset": 0.0,
    "spread": 1.0,
    "mode": "hsv",
    "colors": [],
}
_rainbow_style_sig = None  # tuple — для детекта изменений в apply_layout

# --- Author rainbow («by EXIZ10TION») ---
_author_label = None
_author_canvas = None
_author_canvas_img = None
_author_frames = []
_author_timer = None
_author_index = 0
_author_enabled = False
_author_style = {
    "speed_ms": 50,
    "saturation": 0.75,
    "brightness": 0.95,
    "hue_offset": 0.15,
    "spread": 1.0,
    "mode": "hsv",
    "colors": [],
}
_author_style_sig = None
_author_row = None  # parent frame for author widget

# --- Underline animation (переливающееся подчёркивание) ---
_title_underline = None
_author_underline = None
_underline_timer = None
_underline_hue = 0.0


def init(**deps):
    """Внедрение зависимостей из engine.gui.main_window (имена совпадают с
    именами глобальных переменных исходного gui.py)."""
    globals().update(deps)


# ── UI Language Switcher ──
def switch_ui_lang():
    current = ui_lang_var.get()
    new_lang = "en" if current == "ru" else "ru"
    ui_lang_var.set(new_lang)
    set_language(new_lang)
    try:
        save_settings()
    except Exception:
        pass
    try:
        from engine import gpt_client as _gpt

        _gpt.refresh_i18n_labels()
    except Exception:
        pass
    try:
        from engine.gui import chat_window as _chat_window

        _chat_window.reapply_language()
    except Exception:
        pass
    messagebox.showinfo(t("lang_ui_label"), t("lang_changed_msg"))


_switch_ui_lang = switch_ui_lang


# ── Rainbow text engine ──
def _is_rainbow_enabled() -> bool:
    try:
        from engine.gui import theme_manager as tm

        return bool(tm.get_header_rainbow())
    except Exception:
        return False


def _is_author_rainbow_enabled() -> bool:
    try:
        from engine.gui import theme_manager as tm

        return bool(tm.get_header_author_rainbow())
    except Exception:
        return False


def _default_style(kind: str = "title") -> dict:
    if kind == "author":
        return {
            "speed_ms": 50,
            "saturation": 0.75,
            "brightness": 0.95,
            "hue_offset": 0.15,
            "spread": 1.0,
            "mode": "hsv",
            "colors": [],
        }
    return {
        "speed_ms": 40,
        "saturation": 0.85,
        "brightness": 1.0,
        "hue_offset": 0.0,
        "spread": 1.0,
        "mode": "hsv",
        "colors": [],
    }


def _load_rainbow_style() -> dict:
    """Читает style заголовка из theme_manager."""
    global _rainbow_style
    defaults = _default_style("title")
    try:
        from engine.gui import theme_manager as tm

        style = tm.get_header_rainbow_style()
        if isinstance(style, dict):
            defaults.update(style)
    except Exception:
        pass
    _rainbow_style = defaults
    return defaults


def _load_author_style() -> dict:
    global _author_style
    defaults = _default_style("author")
    try:
        from engine.gui import theme_manager as tm

        style = tm.get_header_author_rainbow_style()
        if isinstance(style, dict):
            defaults.update(style)
    except Exception:
        pass
    _author_style = defaults
    return defaults


def _style_signature(style: dict | None = None) -> tuple:
    s = style if style is not None else _rainbow_style
    colors = tuple(s.get("colors") or [])
    return (
        int(s.get("speed_ms", 40)),
        round(float(s.get("saturation", 0.85)), 3),
        round(float(s.get("brightness", 1.0)), 3),
        round(float(s.get("hue_offset", 0.0)), 3),
        round(float(s.get("spread", 1.0)), 3),
        str(s.get("mode", "hsv")),
        colors,
    )


def _stop_rainbow():
    global _rainbow_timer
    if _rainbow_timer is not None:
        try:
            if root is not None:
                root.after_cancel(_rainbow_timer)
        except Exception:
            pass
    _rainbow_timer = None


def _stop_author_rainbow():
    global _author_timer
    if _author_timer is not None:
        try:
            if root is not None:
                root.after_cancel(_author_timer)
        except Exception:
            pass
    _author_timer = None


def _start_rainbow():
    global _rainbow_timer
    _stop_rainbow()
    if not _rainbow_enabled or not _rainbow_frames:
        return
    # пауза когда окно неактивно / свёрнуто
    try:
        if root is not None:
            # state normal?
            try:
                if root.state() == "iconic":
                    # окно свёрнуто — ждём
                    _rainbow_timer = root.after(500, _start_rainbow)
                    return
            except Exception:
                pass
            # focus check — мягко: если окно не в фокусе, всё равно тикаем реже
            # (оставляем 40ms, это дёшево — кадры предзагружены)
    except Exception:
        pass
    _rainbow_tick()


def _rainbow_tick():
    global _rainbow_timer, _rainbow_index
    try:
        if not _rainbow_enabled or not _rainbow_frames or _title_canvas is None:
            _rainbow_timer = None
            return
        frame = _rainbow_frames[_rainbow_index % len(_rainbow_frames)]
        # обновляем изображение на canvas
        try:
            _title_canvas.itemconfig(_title_canvas_img, image=frame)
        except Exception:
            pass
        _rainbow_index = (_rainbow_index + 1) % len(_rainbow_frames)
        # speed_ms из style (20..200) — компромисс плавность/CPU
        if root is not None:
            delay = int(_rainbow_style.get("speed_ms", 40))
            delay = max(16, min(200, delay))
            _rainbow_timer = root.after(delay, _rainbow_tick)
    except Exception:
        _rainbow_timer = None


def _start_author_rainbow():
    global _author_timer
    _stop_author_rainbow()
    if not _author_enabled or not _author_frames:
        return
    try:
        if root is not None:
            try:
                if root.state() == "iconic":
                    _author_timer = root.after(500, _start_author_rainbow)
                    return
            except Exception:
                pass
    except Exception:
        pass
    _author_tick()


def _author_tick():
    global _author_timer, _author_index
    try:
        if not _author_enabled or not _author_frames or _author_canvas is None:
            _author_timer = None
            return
        frame = _author_frames[_author_index % len(_author_frames)]
        try:
            _author_canvas.itemconfig(_author_canvas_img, image=frame)
        except Exception:
            pass
        _author_index = (_author_index + 1) % len(_author_frames)
        if root is not None:
            delay = int(_author_style.get("speed_ms", 50))
            delay = max(16, min(200, delay))
            _author_timer = root.after(delay, _author_tick)
    except Exception:
        _author_timer = None


# ── Underline animation ──
def _stop_underline():
    global _underline_timer
    if _underline_timer is not None:
        try:
            if root is not None:
                root.after_cancel(_underline_timer)
        except Exception:
            pass
    _underline_timer = None


def _start_underline():
    global _underline_timer
    _stop_underline()
    if not _is_rainbow_enabled():
        return
    _underline_tick()


def _underline_tick():
    global _underline_timer, _underline_hue
    import colorsys

    try:
        if _title_underline is None and _author_underline is None:
            _underline_timer = None
            return
        _underline_hue = (_underline_hue + 0.006) % 1.0
        r, g, b = colorsys.hsv_to_rgb(_underline_hue, 0.75, 0.9)
        color = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
        if _title_underline is not None:
            try:
                _title_underline.configure(bg=color)
            except Exception:
                pass
        if _author_underline is not None:
            try:
                _author_underline.configure(bg=color)
            except Exception:
                pass
        if root is not None:
            _underline_timer = root.after(40, _underline_tick)
    except Exception:
        _underline_timer = None


def _build_rainbow_frames(
    text: str, font_size: int, style: dict | None = None, n_frames: int | None = None
):
    """Генерирует N кадров радужного текста заранее (Pillow).
    style: dict параметров (title или author). Возвращает list[PhotoImage].
    Не трогает глобальный кэш кадров — вызывающий сам сохраняет результат."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageTk
        import colorsys
    except Exception:
        return []

    # --- шрифт ---
    # Пытаемся найти Segoe UI Bold, fallback → DejaVu / Arial / default
    font = None
    font_names_try = [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for fp in font_names_try:
        try:
            import os

            if os.path.exists(fp):
                font = ImageFont.truetype(fp, font_size)
                break
        except Exception:
            continue
    if font is None:
        try:
            font = ImageFont.truetype("arialbd.ttf", font_size)
        except Exception:
            try:
                font = ImageFont.load_default()
            except Exception:
                return []

    # измеряем текст
    try:
        dummy = Image.new("RGB", (10, 10))
        ddraw = ImageDraw.Draw(dummy)
        bbox = ddraw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except Exception:
        text_w, text_h = 180, font_size + 8

    text_w = max(text_w, 10)
    text_h = max(text_h, 10)
    # паддинг + запас под неоновое свечение (blur)
    glow_r = max(5, min(14, font_size // 2))
    pad_x, pad_y = 4 + glow_r, 2 + glow_r
    W, H = text_w + pad_x * 2, text_h + pad_y * 2

    # маска текста (один раз)
    # ВАЖНО: textbbox((0,0), ...) возвращает bbox ОТНОСИТЕЛЬНО точки (0,0),
    # а НЕ "от нуля". bbox[0]/bbox[1] почти всегда != 0 (left bearing и
    # верхний overshoot у жирных/кириллических шрифтов) — поэтому рисовать
    # текст просто в (pad_x, pad_y) нельзя: часть глифов обрежется по
    # краям холста (это и есть причина "съедающегося" текста). Компенсируем
    # смещение bbox явно.
    try:
        text_mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(text_mask)
        md.text((pad_x - bbox[0], pad_y - bbox[1]), text, font=font, fill=255)
    except Exception:
        return []

    # Неоновая «ореола» — одна размытая маска на все кадры (не per-frame)
    try:
        from PIL import ImageFilter

        br = max(3.0, glow_r * 0.7)
        glow_mask = text_mask.filter(ImageFilter.GaussianBlur(radius=br))
        glow_mask = Image.eval(glow_mask, lambda p: min(255, int(p * 1.25)))
    except Exception:
        glow_mask = text_mask

    # параметры анимации + стиль пользователя
    if style is None:
        style = _rainbow_style if isinstance(_rainbow_style, dict) else {}
    sat = float(style.get("saturation", 0.85))
    val = float(style.get("brightness", 1.0))
    hue0 = float(style.get("hue_offset", 0.0))
    spread = float(style.get("spread", 1.0))
    mode = str(style.get("mode", "hsv")).lower()
    custom_colors = list(style.get("colors") or [])
    sat = max(0.0, min(1.0, sat))
    val = max(0.15, min(1.0, val))
    hue0 = hue0 % 1.0
    spread = max(0.2, min(2.0, spread))

    # custom palette → list of RGB tuples
    custom_rgb = []
    if mode == "custom" and custom_colors:
        for hx in custom_colors:
            try:
                s = hx.lstrip("#")
                custom_rgb.append((int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)))
            except Exception:
                continue
    use_custom = len(custom_rgb) >= 2

    # n_frames: 48 для заголовка; для кнопок тулбара — меньше (12–16), иначе UI зависает на старте
    if n_frames is None:
        n_frames = 24  # 24 достаточно плавно; 48 слишком тяжело на слабых CPU
    try:
        n_frames = max(8, min(32, int(n_frames)))
    except Exception:
        n_frames = 24
    # ширина радужной полосы: базово 1.8×, масштабируем spread
    grad_w = int(W * (1.2 + 0.8 * spread))
    if grad_w < W + 20:
        grad_w = W + 20

    frames_pil = []
    # предгенерируем градиент один раз
    base_grad = Image.new("RGB", (grad_w, H))
    bgd = base_grad.load()

    def _lerp_rgb(c1, c2, t):
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )

    def _color_at(t):
        """t in [0,1) — цвет вдоль градиента."""
        t = (t + 0.0) % 1.0
        if use_custom:
            n = len(custom_rgb)
            # цикл по пользовательским цветам
            pos = t * n
            i0 = int(pos) % n
            i1 = (i0 + 1) % n
            frac = pos - int(pos)
            return _lerp_rgb(custom_rgb[i0], custom_rgb[i1], frac)
        h = (hue0 + t * spread) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, sat, val)
        return (int(r * 255), int(g * 255), int(b * 255))

    try:
        gdraw = ImageDraw.Draw(base_grad)
        for x in range(grad_w):
            col = _color_at(x / float(grad_w))
            gdraw.line([(x, 0), (x, H - 1)], fill=col)
    except Exception:
        for x in range(grad_w):
            col = _color_at(x / float(grad_w))
            for y in range(H):
                bgd[x, y] = col

    # нарезаем кадры со сдвигом
    step = max(1, grad_w // n_frames)
    for i in range(n_frames):
        offset = (i * step) % grad_w
        # собираем кадровое полотно: берём окно grad_w сдвинутое, циклически
        frame_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        # левая часть
        remain = W
        cur_x = offset
        dst_x = 0
        while remain > 0:
            chunk_w = min(grad_w - cur_x, remain)
            if chunk_w <= 0:
                cur_x = 0
                continue
            crop = base_grad.crop((cur_x, 0, cur_x + chunk_w, H))
            frame_img.paste(crop, (dst_x, 0))
            dst_x += chunk_w
            remain -= chunk_w
            cur_x = (cur_x + chunk_w) % grad_w
            if cur_x == 0 and remain > 0:
                # зациклились — продолжаем с начала
                continue
        # Неон: цветной слой + glow (размытая альфа) + чёткое ядро текста
        if frame_img.mode != "RGBA":
            frame_img = frame_img.convert("RGBA")
        r, g, b, _a = frame_img.split()
        # glow layer (мягче, ярче)
        glow_layer = Image.merge("RGBA", (r, g, b, glow_mask))
        # core text (чёткие края)
        core_layer = Image.merge("RGBA", (r, g, b, text_mask))
        out_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        out_img = Image.alpha_composite(out_img, glow_layer)
        out_img = Image.alpha_composite(out_img, core_layer)
        frames_pil.append(out_img)

    # конвертируем в PhotoImage, сохраняем ссылки
    out = []
    try:
        for im in frames_pil:
            out.append(ImageTk.PhotoImage(im))
    except Exception:
        out = []
    return out


def _apply_rainbow_to_title(parent, text):
    """Заменяет обычный Label на Canvas с анимацией, если эффект включён"""
    global _title_label, _title_canvas, _title_canvas_img, _rainbow_frames, _rainbow_enabled, _rainbow_index, _rainbow_font_size, _rainbow_last_scale
    # останавливаем старую анимацию
    _stop_rainbow()
    _rainbow_frames = []
    _rainbow_index = 0

    # проверяем включение + подгружаем style
    enabled = _is_rainbow_enabled()
    _rainbow_enabled = enabled
    _load_rainbow_style()
    global _rainbow_style_sig
    _rainbow_style_sig = _style_signature()
    font_sz = scaled_font_size(16)
    _rainbow_font_size = font_sz

    if not enabled:
        # обычный лейбл
        if _title_canvas is not None:
            try:
                _title_canvas.destroy()
            except Exception:
                pass
            _title_canvas = None
        _title_label = tk.Label(
            parent,
            text=text,
            bg=Colors.BG_CARD,
            fg=Colors.TEXT_MAIN,
            font=("Segoe UI", font_sz, "bold"),
        )
        _title_label.pack(side="left", padx=(4, 0))
        return _title_label

    # радужный режим — Canvas + PhotoImage
    if _title_label is not None:
        try:
            _title_label.destroy()
        except Exception:
            pass
        _title_label = None

    # генерируем кадры (style уже в _rainbow_style)
    frames = _build_rainbow_frames(text, font_sz + 2, style=_rainbow_style, n_frames=16)
    if not frames:
        # fallback на обычный Label если генерация не удалась
        _rainbow_enabled = False
        lbl = tk.Label(
            parent,
            text=text,
            bg=Colors.BG_CARD,
            fg=Colors.TEXT_MAIN,
            font=("Segoe UI", font_sz, "bold"),
        )
        lbl.pack(side="left", padx=(4, 0))
        _title_label = lbl
        return lbl

    _rainbow_frames = frames
    # размер canvas по первому кадру
    try:
        w = frames[0].width()
        h = frames[0].height()
    except Exception:
        w, h = 200, 28
    # Canvas с фоном как у родителя
    try:
        bg = parent.cget("bg")
    except Exception:
        bg = Colors.BG_CARD
    _title_canvas = tk.Canvas(parent, width=w, height=h, bg=bg, highlightthickness=0, bd=0)
    _title_canvas.pack(side="left", padx=(4, 0))
    _title_canvas_img = _title_canvas.create_image(0, 0, anchor="nw", image=frames[0])
    # сохраняем id картинки в глобальной переменной для _rainbow_tick
    globals()["_title_canvas_img"] = _title_canvas_img
    _rainbow_last_scale = font_sz

    # старт анимации, с паузой если окно не в фокусе
    def _on_map(e):
        _start_rainbow()

    def _on_unmap(e):
        _stop_rainbow()

    try:
        _title_canvas.bind("<Map>", _on_map, add="+")
        _title_canvas.bind("<Unmap>", _on_unmap, add="+")
    except Exception:
        pass

    _start_rainbow()
    return _title_canvas


def _apply_rainbow_to_author(parent, text):
    """Подпись «by EXIZ10TION» — Label или радужный Canvas (свой style)."""
    global _author_label, _author_canvas, _author_canvas_img, _author_frames
    global _author_enabled, _author_index, _author_style_sig, _author_row
    _stop_author_rainbow()
    _author_frames = []
    _author_index = 0
    _author_row = parent

    enabled = _is_author_rainbow_enabled()
    _author_enabled = enabled
    _load_author_style()
    _author_style_sig = _style_signature(_author_style)
    font_sz = scaled_font_size(9)

    # destroy previous widgets
    for wname in ("_author_canvas", "_author_label"):
        w = globals().get(wname)
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass
            globals()[wname] = None

    if not enabled:
        _author_label = tk.Label(
            parent,
            text=text,
            bg=Colors.BG_CARD,
            fg=Colors.TEXT_DIM,
            font=("Segoe UI", font_sz),
        )
        _author_label.pack(side="left")
        return _author_label

    frames = _build_rainbow_frames(text, font_sz + 1, style=_author_style, n_frames=12)
    if not frames:
        _author_enabled = False
        _author_label = tk.Label(
            parent,
            text=text,
            bg=Colors.BG_CARD,
            fg=Colors.TEXT_DIM,
            font=("Segoe UI", font_sz),
        )
        _author_label.pack(side="left")
        return _author_label

    _author_frames = frames
    try:
        w, h = frames[0].width(), frames[0].height()
    except Exception:
        w, h = 160, 18
    try:
        bg = parent.cget("bg")
    except Exception:
        bg = Colors.BG_CARD
    _author_canvas = tk.Canvas(parent, width=w, height=h, bg=bg, highlightthickness=0, bd=0)
    _author_canvas.pack(side="left")
    _author_canvas_img = _author_canvas.create_image(0, 0, anchor="nw", image=frames[0])
    globals()["_author_canvas_img"] = _author_canvas_img

    def _on_map(e):
        _start_author_rainbow()

    def _on_unmap(e):
        _stop_author_rainbow()

    try:
        _author_canvas.bind("<Map>", _on_map, add="+")
        _author_canvas.bind("<Unmap>", _on_unmap, add="+")
    except Exception:
        pass
    _start_author_rainbow()
    return _author_canvas


def build_header(left_panel):
    global header_frame, title_row, header_btn_row, upd_btn, ai_status_btn, ui_lang_btn
    global _title_label, _title_canvas, _author_row, _author_label
    global _title_underline, _author_underline
    header_frame = CompatCTkFrame(left_panel, fg_color="transparent", bg="transparent")
    header_frame.pack(fill="x", pady=(0, 8))

    # ── КАРТОЧКА ЗАГОЛОВКА ──
    title_card = CompatCTkFrame(header_frame, fg_color=Colors.BG_CARD, corner_radius=10)
    title_card.pack(fill="x", padx=4, pady=(0, 4))

    # Цвет акцентной полоски (fallback — голубой, как в splash)
    _accent_color = getattr(Colors, "ACCENT", "#58a6ff")

    # ── Заголовок с акцентной полоской ──
    title_row = tk.Frame(title_card, bg=Colors.BG_CARD)
    title_row.pack(anchor="w", fill="x", padx=10, pady=(10, 0))
    _accent_bar_title = tk.Frame(title_row, bg="#ffffff", width=2)
    _accent_bar_title.pack(side="left", fill="y", padx=(0, 10))
    # Сначала обычные Label — окно рисуется сразу.
    # Неон (Pillow) — ПОСЛЕ idle, иначе «Не отвечает» на старте.
    title_text = t("app_title")
    _title_label = tk.Label(
        title_row,
        text=title_text,
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_MAIN,
        font=("Segoe UI", scaled_font_size(16), "bold"),
    )
    _title_label.pack(side="left", padx=(0, 0))

    # ── Подчёркивание заголовка (переливающееся) ──
    _title_underline = tk.Canvas(title_card, height=1, bg="#ffffff", highlightthickness=0, bd=0)
    _title_underline.pack(fill="x", padx=20, pady=(2, 6))

    # ── Подпись с акцентной полоской ──
    _author_row = tk.Frame(title_card, bg=Colors.BG_CARD)
    _author_row.pack(anchor="w", fill="x", padx=10, pady=(0, 0))
    _accent_bar_author = tk.Frame(_author_row, bg="#ffffff", width=2)
    _accent_bar_author.pack(side="left", fill="y", padx=(0, 10))
    _author_label = tk.Label(
        _author_row,
        text=t("app_author"),
        bg=Colors.BG_CARD,
        fg=Colors.TEXT_DIM,
        font=("Segoe UI", scaled_font_size(9)),
    )
    _author_label.pack(side="left")

    # ── Подчёркивание подписи (переливающееся) ──
    _author_underline = tk.Canvas(title_card, height=1, bg="#ffffff", highlightthickness=0, bd=0)
    _author_underline.pack(fill="x", padx=20, pady=(2, 10))

    def _deferred_neon_title():
        try:
            if root is not None and not root.winfo_exists():
                return
        except Exception:
            return
        try:
            if not _is_rainbow_enabled():
                return
            global _title_label
            if _title_label is not None:
                try:
                    _title_label.destroy()
                except Exception:
                    pass
                _title_label = None
            _apply_rainbow_to_title(title_row, t("app_title"))
        except Exception:
            pass

    def _deferred_neon_author():
        try:
            if root is not None and not root.winfo_exists():
                return
        except Exception:
            return
        try:
            if not _is_author_rainbow_enabled():
                return
            global _author_label
            if _author_label is not None:
                try:
                    _author_label.destroy()
                except Exception:
                    pass
                _author_label = None
            _apply_rainbow_to_author(_author_row, t("app_author"))
        except Exception:
            pass

    try:
        # разносим по времени: сначала title, потом author — меньше пик CPU
        r = root if root is not None else title_row
        r.after(500, _deferred_neon_title)
        r.after(900, _deferred_neon_author)
    except Exception:
        pass
    header_btn_row = tk.Frame(header_frame, bg=Colors.BG_DARK)
    header_btn_row.pack(anchor="w", pady=(4, 0))
    upd_btn = create_button(
        header_btn_row, t("btn_update"), check_and_update, bg=Colors.BG_INPUT, font_size=10
    )
    upd_btn.pack(side="left")
    ai_status_btn = create_button(
        header_btn_row, t("btn_ai_status"), open_ai_status_window, bg=Colors.BG_INPUT, font_size=10
    )
    ai_status_btn.pack(side="left", padx=(6, 0))
    # ── UI Language Switcher (функция switch_ui_lang — на уровне модуля) ──
    ui_lang_btn = create_button(
        header_btn_row, "RU/EN", switch_ui_lang, bg=Colors.BG_INPUT, font_size=10, width=50
    )
    ui_lang_btn.pack(side="left", padx=(6, 0))
    ToolTip(ui_lang_btn, t("lang_switch_tip"))
    left_panel.update_idletasks()


# Live-apply helper — вызывается из main_window.apply_layout_preset_to_all
def apply_layout(preset: dict) -> bool:
    """Live-apply: перегенерация радужных заголовков при смене шрифта/темы/флага/style"""
    changed = False
    try:
        from engine.gui.colors import scaled_font_size as _sc
        from i18n import t as _t

        new_sz = _sc(16)
        global _rainbow_last_scale, _rainbow_enabled, _author_enabled, _author_style_sig
        try:
            from engine.gui import theme_manager as _tm

            want_rainbow = bool(_tm.get_header_rainbow())
            want_author = bool(_tm.get_header_author_rainbow())
        except Exception:
            want_rainbow = False
            want_author = False
        try:
            new_style = _load_rainbow_style()
            new_sig = _style_signature(new_style)
        except Exception:
            new_sig = _rainbow_style_sig
        try:
            new_author_style = _load_author_style()
            new_author_sig = _style_signature(new_author_style)
        except Exception:
            new_author_sig = _author_style_sig

        need_title = False
        if want_rainbow != _rainbow_enabled:
            need_title = True
        elif _rainbow_enabled and _rainbow_last_scale is not None and new_sz != _rainbow_last_scale:
            need_title = True
        elif want_rainbow and new_sig != _rainbow_style_sig:
            need_title = True
        if want_rainbow and (_title_canvas is None and _title_label is None):
            need_title = True

        if need_title and title_row is not None:
            try:
                for key in ("_title_canvas", "_title_label"):
                    w = globals().get(key)
                    if w is not None:
                        try:
                            w.destroy()
                        except Exception:
                            pass
                        globals()[key] = None
                _stop_rainbow()
                globals()["_rainbow_frames"] = []
                _apply_rainbow_to_title(title_row, _t("app_title"))
                changed = True
            except Exception:
                pass

        need_author = False
        if want_author != _author_enabled:
            need_author = True
        elif want_author and new_author_sig != _author_style_sig:
            need_author = True
        if want_author and (_author_canvas is None and _author_label is None):
            need_author = True
        # always rebuild author when title rebuilt (font scale)
        if need_title:
            need_author = True

        if need_author and _author_row is not None:
            try:
                _apply_rainbow_to_author(_author_row, _t("app_author"))
                changed = True
            except Exception:
                pass
    except Exception:
        pass
    return changed


def stop_rainbow():
    _stop_rainbow()
    _stop_author_rainbow()
    _stop_underline()


def start_rainbow():
    if _is_rainbow_enabled():
        global _rainbow_enabled
        _rainbow_enabled = True
        _start_rainbow()
    if _is_author_rainbow_enabled():
        global _author_enabled
        _author_enabled = True
        _start_author_rainbow()
