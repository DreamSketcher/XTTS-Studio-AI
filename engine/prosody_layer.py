# engine/prosody_layer.py

import re
from dataclasses import dataclass

from engine.text_utils import is_list_item as _is_list_item


@dataclass
class ProsodyConfig:
    mode: str = "balanced"
    intensity: float = 1.0
    breath_length: str = "medium"


class ProsodyLayer:
    PAUSE_SHORT = ","
    PAUSE_MEDIUM = "..."
    PAUSE_LONG = "... ."

    CONTRAST_WORDS = {
        "но",
        "однако",
        "хотя",
        "впрочем",
        "зато",
        "but",
        "however",
        "although",
        "though",
        "yet",
        "nevertheless",
    }
    CONCLUSION_WORDS = {
        "поэтому",
        "итак",
        "таким образом",
        "следовательно",
        "therefore",
        "thus",
        "so",
        "hence",
        "consequently",
    }
    EMPHASIS_WORDS = {
        "важно",
        "главное",
        "обратите внимание",
        "заметьте",
        "important",
        "note that",
        "key point",
        "remember",
        "crucial",
    }
    EXAMPLE_WORDS = {
        "например",
        "к примеру",
        "допустим",
        "скажем",
        "for example",
        "for instance",
        "such as",
        "like",
    }

    def __init__(self, config: ProsodyConfig = ProsodyConfig()):
        self.cfg = config

    def process(
        self, text: str, lang: str = "auto", in_list: bool = False, is_last_list_item: bool = False
    ) -> str:
        if self.cfg.intensity == 0.0:
            return text
        if lang not in ("ru", "en"):
            return text
        text = self._normalize(text)
        text = self._insert_contrast_pauses(text)
        text = self._insert_conclusion_pauses(text)
        text = self._insert_emphasis_pauses(text)
        text = self._insert_example_pauses(text)

        # #4: специальная обработка контекста перечисления
        if in_list:
            text = self._apply_list_prosody(text, is_last=is_last_list_item)

        text = self._cleanup(text)
        return text

    # =========================
    # #4 LIST PROSODY
    # =========================
    def _apply_list_prosody(self, text: str, is_last: bool = False) -> str:
        """
        Для последнего пункта перечисления — гарантируем финальную точку
        (сигнал модели завершить интонацию вниз, а не оборвать).
        Для промежуточных — запятая в конце (перечислительная интонация).
        """
        text = text.rstrip()

        if is_last:
            # финальная точка — завершающая интонация
            if text and text[-1] not in ".!?":
                text += "."
        else:
            # запятая в конце промежуточного пункта — интонация продолжения
            if text and text[-1] in ".":
                text = text[:-1] + ","
            elif text and text[-1] not in ",.!?":
                text += ","

        return text

    def process_chunks(self, chunks: list, lang: str = "auto") -> list:
        """
        Обрабатывает список чанков с учётом контекста перечисления.
        Определяет runs из list-item чанков и помечает последний.
        """
        result = []
        n = len(chunks)

        i = 0
        while i < n:
            chunk = chunks[i]
            if _is_list_item(chunk):
                # находим конец серии list items
                j = i
                while j < n and _is_list_item(chunks[j]):
                    j += 1
                # обрабатываем серию
                for k in range(i, j):
                    is_last = k == j - 1
                    result.append(
                        self.process(chunks[k], lang=lang, in_list=True, is_last_list_item=is_last)
                    )
                i = j
            else:
                result.append(self.process(chunk, lang=lang))
                i += 1

        return result

    def _insert_contrast_pauses(self, text: str) -> str:
        pause = self._get_pause("contrast")
        for word in self.CONTRAST_WORDS:
            text = re.sub(
                rf"([.!?])\s+({re.escape(word)}\b)", rf"\1 {pause} \2", text, flags=re.IGNORECASE
            )
        return text

    def _insert_conclusion_pauses(self, text: str) -> str:
        pause = self._get_pause("conclusion")
        for word in self.CONCLUSION_WORDS:
            text = re.sub(
                rf"([.!?])\s+({re.escape(word)}\b)", rf"\1 {pause} \2", text, flags=re.IGNORECASE
            )
        return text

    def _insert_emphasis_pauses(self, text: str) -> str:
        pause = self._get_pause("emphasis")
        for word in self.EMPHASIS_WORDS:
            text = re.sub(
                rf"([.!?])\s+({re.escape(word)}\b)", rf"\1 {pause} \2", text, flags=re.IGNORECASE
            )
        return text

    def _insert_example_pauses(self, text: str) -> str:
        pause = self._get_pause("example")
        for word in self.EXAMPLE_WORDS:
            text = re.sub(
                rf"([.!?])\s+({re.escape(word)}\b)", rf"\1 {pause} \2", text, flags=re.IGNORECASE
            )
        return text

    def _get_pause(self, pause_type: str) -> str:
        intensity = self.cfg.intensity
        base = {
            "contrast": self.PAUSE_MEDIUM,
            "conclusion": self.PAUSE_LONG,
            "emphasis": self.PAUSE_LONG,
            "example": self.PAUSE_SHORT,
        }.get(pause_type, self.PAUSE_SHORT)
        if intensity < 0.8:
            if base == self.PAUSE_LONG:
                return self.PAUSE_MEDIUM
            if base == self.PAUSE_MEDIUM:
                return self.PAUSE_SHORT
        if intensity > 1.2:
            if base == self.PAUSE_SHORT:
                return self.PAUSE_MEDIUM
            if base == self.PAUSE_MEDIUM:
                return self.PAUSE_LONG
        return base

    def _normalize(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        return text.strip()

    def _cleanup(self, text: str) -> str:
        # Убираем некрасивые конструкции вроде ". ... ." или ". ..." оставляя просто чистый стык "... "
        text = re.sub(r"\.\s*\.\.\.\s*\.?\s*", "... ", text)
        text = re.sub(r"\.\dots\s*\.\s*", "... ", text)
        text = re.sub(r"(\.\.\.\s*)+", "... ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


def create_prosody_layer(mode="balanced", intensity=1.0, breath_length="medium"):
    return ProsodyLayer(ProsodyConfig(mode=mode, intensity=intensity, breath_length=breath_length))
