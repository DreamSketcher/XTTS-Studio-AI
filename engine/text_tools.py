# -*- coding: utf-8 -*-
"""engine/text_tools.py — нормализация текста (перенесено из gui.py: normalize_text)."""
import re


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r",([A-ZА-ЯЁa-zа-яё])", r", \1", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"(\.)([A-ZА-ЯЁ])", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
