import re

from engine.text_utils import is_list_item as _is_list_item


class SmartPauseEngine:
    def __init__(self):
        self.base_short = 70
        self.base_medium = 140
        self.base_long = 220
        self.base_dramatic = 420

        # #3: пауза между пунктами перечисления — длиннее стандартной,
        # даёт модели "reset point" и сохраняет тон между чанками
        self.list_item_pause = 450

    def get_pause_ms(self, chunk: str, next_chunk: str = "") -> int:
        chunk = chunk.strip()
        if not chunk:
            return self.base_short

        # #3: если текущий чанк — пункт списка ИЛИ следующий является им
        if _is_list_item(chunk) or (next_chunk and _is_list_item(next_chunk.strip())):
            return self.list_item_pause

        words = re.findall(r"\w+", chunk)
        word_count = len(words)

        last_char = chunk[-1] if chunk else ""

        # =========================
        # BASE PAUSE BY PUNCTUATION
        # =========================
        if chunk.endswith("..."):
            pause = self.base_dramatic

        elif last_char == "?":
            pause = self.base_long + 60

        elif last_char == "!":
            pause = self.base_long - 20

        elif last_char == ".":
            pause = self.base_medium

        elif last_char == ",":
            pause = self.base_short

        else:
            pause = self.base_short

        # =========================
        # LENGTH MODIFIER (SOFT CURVE)
        # =========================
        if word_count > 6:
            pause += int((word_count - 6) * 3.5)

        # =========================
        # CLAMP
        # =========================
        pause = max(50, min(pause, 450))

        return pause

    def detect_emotion(self, chunk: str) -> str:
        chunk_lower = chunk.lower()

        excited_words = [
            "wow",
            "amazing",
            "incredible",
            "потрясающе",
            "невероятно",
            "отлично",
            "класс",
            "супер",
            "блестяще",
        ]

        uncertain_words = [
            "maybe",
            "perhaps",
            "not sure",
            "может",
            "наверное",
            "возможно",
            "не уверен",
            "пожалуй",
            "вроде",
        ]

        if any(w in chunk_lower for w in excited_words):
            return "excited"
        if any(w in chunk_lower for w in uncertain_words):
            return "uncertain"
        return "normal"
