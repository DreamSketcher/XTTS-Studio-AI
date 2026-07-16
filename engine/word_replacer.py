import json
from engine.atomic_write import atomic_write_json
import os
import re
import shutil
from datetime import datetime
from typing import Optional


# Приоритет категорий при сборке flat_rules: позже = выше приоритет.
# builtin — исторические записи из ранних версий словаря (низший приоритет)
# auto — слова, добавленные эвристическим автодетектором
# ai_corrected — исправления от AI Conductor
# custom — ручные правки пользователя через окно "📖 Словарь" (высший приоритет)
#
# ВАЖНО: единственный источник правды — word_rules.json в корне проекта.
# Никакого захардкоженного seed-словаря в коде больше нет: если слово
# удалено через окно "📖 Словарь" (или прямо в JSON) — оно остаётся
# удалённым навсегда и не пересоздаётся при следующем запуске.
_CATEGORY_PRIORITY = ["builtin", "auto", "ai_corrected", "custom"]

# Сколько последних бэкапов word_rules.json хранить локально
# (backups/word_rules_YYYYMMDD_HHMMSS.json рядом с самим файлом правил).
_MAX_BACKUPS = 30

_LATIN_LETTER_MAP = {
    "a": "эй",
    "b": "би",
    "c": "си",
    "d": "ди",
    "e": "и",
    "f": "эф",
    "g": "джи",
    "h": "эйч",
    "i": "ай",
    "j": "джей",
    "k": "кей",
    "l": "эл",
    "m": "эм",
    "n": "эн",
    "o": "оу",
    "p": "пи",
    "q": "кью",
    "r": "ар",
    "s": "эс",
    "t": "ти",
    "u": "ю",
    "v": "ви",
    "w": "дабл ю",
    "x": "икс",
    "y": "уай",
    "z": "зед",
}

_SERVICE_WORDS = {
    "a",
    "an",
    "the",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "and",
    "or",
    "but",
    "if",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "as",
    "by",
    "from",
    "this",
    "that",
    "it",
    "its",
    "his",
    "her",
    "their",
    "not",
    "no",
    "yes",
    "ok",
    "okay",
    "vs",
    "etc",
    "id",
    "fast",
    "slow",
    "speed",
    "high",
    "low",
    "new",
    "old",
    "good",
    "bad",
    "we",
    "you",
    "he",
    "she",
    "they",
    "them",
    "our",
    "your",
    "my",
    "end",
    "back",
    "up",
    "down",
    "out",
    "off",
    "on",
    "now",
    "then",
    "can",
    "will",
    "must",
    "may",
    "has",
    "had",
    "do",
    "did",
    "does",
}

_DIGRAPHS = [
    ("tion", "шн"),
    ("sion", "жн"),
    ("ough", "оу"),
    ("augh", "аф"),
    ("th", "т"),
    ("sh", "ш"),
    ("ch", "ч"),
    ("ph", "ф"),
    ("wh", "у"),
    ("ck", "к"),
    ("ng", "нг"),
    ("qu", "кв"),
    ("ee", "и"),
    ("oo", "у"),
    ("ou", "ау"),
    ("ow", "оу"),
    ("au", "ау"),
    ("ai", "эй"),
    ("ay", "эй"),
    ("ea", "и"),
    ("ie", "ай"),
    ("oa", "оу"),
    ("ue", "ю"),
    ("ui", "ю"),
]

_SINGLE_SOUND = {
    "a": "а",
    "b": "б",
    "c": "к",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "дж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "а",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "и",
    "z": "з",
}

_VOWELS = set("aeiou")

_NUM_WORDS = {
    "0": "ноль",
    "1": "один",
    "2": "два",
    "3": "три",
    "4": "четыре",
    "5": "пять",
    "6": "шесть",
    "7": "семь",
    "8": "восемь",
    "9": "девять",
}


def _looks_like_abbrev(word: str) -> bool:
    """Капс-аббревиатура (XTTS, CPU, GPU) -> читаем побуквенно."""
    if not word or len(word) < 2 or len(word) > 6:
        return False
    if not word.isalpha():
        return False
    if not word.isascii():
        return False
    if not word.isupper():
        return False
    return True


def _auto_transliterate_abbrev(word: str) -> str:
    parts = []
    for ch in word.lower():
        parts.append(_LATIN_LETTER_MAP.get(ch, ch))
    return " ".join(parts)


def _looks_like_lowercase_term(word: str) -> bool:
    """
    Lowercase-слово, не входящее в список служебных слов -> кандидат на
    слоговую транслитерацию (pydub, tkinter, soundfile, ffmpeg,
    tkinterdnd2, num2words).
    """
    if not word or len(word) < 2:
        return False
    if not word.isascii():
        return False
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", word):
        return False
    if word.isupper():
        return False
    if word.lower() in _SERVICE_WORDS:
        return False
    return True


def _transliterate_term_word(word: str) -> str:
    """
    Транслитерация технического термина (эвристика, не словарь).
    Используется только как запасной вариант для слов, которых ЕЩЁ НЕТ
    в word_rules.json — после первого срабатывания слово автоматически
    сохраняется в категорию "auto" и больше не идёт через эвристику.
    Если результат неверный — поправьте слово в окне "📖 Словарь",
    оно перейдёт в "custom" и будет иметь приоритет навсегда.
    """
    segments = re.findall(r"[a-zA-Z]+|\d+", word)
    parts = []
    for seg in segments:
        if seg.isdigit():
            parts.append(" ".join(_NUM_WORDS.get(d, d) for d in seg))
        elif len(seg) <= 3:
            parts.append(" ".join(_LATIN_LETTER_MAP.get(c, c) for c in seg.lower()))
        else:
            parts.append(_letters_to_word_sound(seg))
    return " ".join(p for p in parts if p)


def _letters_to_word_sound(letters: str) -> str:
    w = letters.lower()
    out = []
    i = 0
    n = len(w)
    while i < n:
        if w[i] == "y" and (i == 0 or w[i - 1] not in _VOWELS):
            nxt = w[i + 1] if i + 1 < n else ""
            if nxt == "" or nxt not in _VOWELS:
                out.append("ай")
                i += 1
                continue
        if i + 1 < n and w[i] == w[i + 1] and w[i] not in _VOWELS:
            out.append(_SINGLE_SOUND.get(w[i], w[i]))
            i += 2
            continue
        matched = False
        for dg, sound in _DIGRAPHS:
            if w[i : i + len(dg)] == dg:
                out.append(sound)
                i += len(dg)
                matched = True
                break
        if matched:
            continue
        out.append(_SINGLE_SOUND.get(w[i], w[i]))
        i += 1
    return "".join(out)


class WordReplacer:
    def __init__(self, rules_path: str):
        self.rules_path = rules_path
        self.data = {}
        self.flat_rules = {}
        self.load()

    def load(self):
        if os.path.exists(self.rules_path):
            try:
                with open(self.rules_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        self._build_flat_rules()

    def _build_flat_rules(self):
        self.flat_rules = {}
        categories = [c for c in self.data.keys() if c != "meta"]

        def _priority(cat):
            try:
                return _CATEGORY_PRIORITY.index(cat)
            except ValueError:
                return len(_CATEGORY_PRIORITY)  # неизвестные категории — выше custom

        categories.sort(key=_priority)

        for category_name in categories:
            category_data = self.data.get(category_name)
            if not isinstance(category_data, dict):
                continue
            for word, value in category_data.items():
                if isinstance(value, dict):
                    self.flat_rules[word] = value.get("text", "")
                else:
                    self.flat_rules[word] = value

    def _backup_dir(self):
        d = os.path.join(os.path.dirname(os.path.abspath(self.rules_path)), "word_rules_backups")
        os.makedirs(d, exist_ok=True)
        return d

    def _make_backup(self):
        """
        Перед КАЖДОЙ перезаписью word_rules.json сохраняем копию текущего
        (ещё не изменённого) состояния файла — так, если новая автозапись
        окажется ошибочной (как было с транслитерацией целых предложений),
        всегда можно откатиться вручную, просто скопировав нужный бэкап
        обратно поверх word_rules.json. Хранится последние _MAX_BACKUPS штук.
        """
        if not os.path.exists(self.rules_path):
            return
        try:
            backup_dir = self._backup_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            dst = os.path.join(backup_dir, f"word_rules_{ts}.json")
            shutil.copy2(self.rules_path, dst)

            backups = sorted(
                f
                for f in os.listdir(backup_dir)
                if f.startswith("word_rules_") and f.endswith(".json")
            )
            while len(backups) > _MAX_BACKUPS:
                oldest = backups.pop(0)
                try:
                    os.remove(os.path.join(backup_dir, oldest))
                except Exception:
                    pass
        except Exception as e:
            print(f"[WordReplacer] Backup failed (продолжаем без бэкапа): {e}")

    def save(self):
        self._make_backup()
        atomic_write_json(self.rules_path, self.data, ensure_ascii=False, indent=2)

    def get_words_list(self):
        words = []
        for category_name, category_data in self.data.items():
            if category_name == "meta":
                continue
            if isinstance(category_data, dict):
                words.extend(category_data.keys())
        return sorted(words)

    def get_category(self, word: str):
        for category_name, category_data in self.data.items():
            if category_name == "meta":
                continue
            if isinstance(category_data, dict) and word in category_data:
                return category_name
        return None

    def add_rule(
        self,
        word: str,
        replacement: str,
        category: str = "custom",
        weight: float = 1.0,
        context: str = "",
    ):
        word = word.strip()
        old_category = self.get_category(word)

        existing = None
        if old_category:
            existing = self.data.get(old_category, {}).get(word)

        if old_category and old_category != category:
            del self.data[old_category][word]

        if category not in self.data:
            self.data[category] = {}

        now = datetime.now().isoformat(timespec="seconds")

        if isinstance(existing, dict) and old_category == category:
            # Слово уже было в этой же категории — не теряем историю,
            # просто обновляем счётчик и текст правки.
            occurrences = int(existing.get("occurrences", 1)) + 1
            added_at = existing.get("added_at", now)
        else:
            occurrences = 1
            added_at = now

        entry = {
            "text": replacement.strip(),
            "weight": float(weight),
            "added_at": added_at,
            "updated_at": now,
            "occurrences": occurrences,
        }
        if context:
            entry["context"] = context[:120]

        self.data[category][word] = entry
        self._build_flat_rules()
        self.save()

    def remove_rule(self, word: str):
        for category in list(self.data.keys()):
            if category == "meta":
                continue
            if word in self.data.get(category, {}):
                del self.data[category][word]
        self._build_flat_rules()
        self.save()

    def apply(self, text: str, persist_new: bool = True) -> str:
        sorted_rules = sorted(self.flat_rules.items(), key=lambda kv: len(kv[0]), reverse=True)
        for word, replacement in sorted_rules:
            pattern = rf"(?<!\w){re.escape(word)}(?!\w)"
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        def _abbrev_sub(m):
            token = m.group(0)
            if token in self.flat_rules or token.lower() in self.flat_rules:
                return self.flat_rules.get(token, self.flat_rules.get(token.lower()))

            # Если слово — часть связной английской фразы (рядом ещё
            # латинские слова через пробел/дефис), это осмысленный
            # английский текст, а не одиночный вставленный термин —
            # транслитерацию не применяем, чтобы не ломать переключение
            # языка в _split_by_language.
            start, end = m.span()
            before = text[max(0, start - 25) : start]
            after = text[end : end + 25]

            # Смотрим ТОЛЬКО на непосредственного соседа в той же фразе —
            # если между токеном и соседним словом стоит точка (конец
            # предложения/клаузы), сосед не считается: список сокращений вида
            # "CPU, GPU. RAM, JSON." — это отдельные пары, а не одна фраза,
            # и точка не должна тянуть за собой контекст следующей пары.
            before_m = re.search(r"([A-Za-z]+)[ ,]*$", before)
            after_m = re.match(r"^[ ,]*([A-Za-z]+)", after)

            def _is_prose_word(w: Optional[str]) -> bool:
                # Признак связной английской речи — сосед НЕ выглядит как
                # отдельное сокращение (не весь в верхнем регистре) и/или
                # является служебным словом (the/is/of/...). Список
                # сокращений (CPU, GPU, JSON...) состоит из ЗАГЛАВНЫХ токенов
                # и не даёт такого сигнала, поэтому не блокирует соседей.
                if not w:
                    return False
                return (not w.isupper()) or (w.lower() in _SERVICE_WORDS)

            if _is_prose_word(before_m.group(1) if before_m else None) or _is_prose_word(
                after_m.group(1) if after_m else None
            ):
                return token

            if _looks_like_abbrev(token):
                replacement = _auto_transliterate_abbrev(token)
            elif _looks_like_lowercase_term(token):
                replacement = _transliterate_term_word(token)
            else:
                return token

            if persist_new:
                ctx_start = max(0, start - 40)
                ctx_end = min(len(text), end + 40)
                context = text[ctx_start:ctx_end].strip()
                self.add_rule(token, replacement, category="auto", context=context)
            return replacement

        text = re.sub(r"\b[A-Za-z][A-Za-z0-9]*\b", _abbrev_sub, text)
        return text
