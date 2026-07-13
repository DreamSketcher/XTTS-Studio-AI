# -*- coding: utf-8 -*-
"""engine/output_naming.py — генерация имени выходного файла (перенесено из gui.py: _make_output_name)."""

import os
import unicodedata

from engine.paths import OUTPUT_DIR


def _make_output_name(text: str) -> str:
    """Генерирует имя файла из первых слов текста с защитой от дублей."""
    snippet = text.strip()[:60]
    snippet = snippet.replace("\n", " ").replace("\r", "")
    allowed = []
    for ch in snippet:
        cat = unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("N") or ch == " ":
            allowed.append(ch)
    name = "".join(allowed).strip()
    if len(name) > 40:
        cut = name[:40].rsplit(" ", 1)
        name = cut[0] if len(cut) > 1 else name[:40]
    name = name.strip() or "output"
    base = os.path.join(OUTPUT_DIR, name)
    candidate = f"{base}.wav"
    counter = 1
    while os.path.exists(candidate):
        candidate = f"{base} ({counter}).wav"
        counter += 1
    return candidate
