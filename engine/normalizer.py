import re

from num2words import num2words


class TextNormalizer:
    ORDINALS = {
        1: "первое",
        2: "второе",
        3: "третье",
        4: "четвёртое",
        5: "пятое",
        6: "шестое",
        7: "седьмое",
        8: "восьмое",
        9: "девятое",
        10: "десятое",
        11: "одиннадцатое",
        12: "двенадцатое",
        13: "тринадцатое",
        14: "четырнадцатое",
        15: "пятнадцатое",
        16: "шестнадцатое",
        17: "семнадцатое",
        18: "восемнадцатое",
        19: "девятнадцатое",
        20: "двадцатое",
    }

    # =========================
    # КИРИЛЛИЧЕСКИЕ АББРЕВИАТУРЫ
    # Словарь: аббревиатура → произношение
    # Если нет в словаре — применяем ритм как для латиницы
    # =========================
    CYR_ABBREV_DICT = {
        "РФ": "эр эф",
        "РБ": "эр бэ",
        "СНГ": "эс эн гэ",
        "СССР": "эс эс эс эр",
        "ВВП": "вэ вэ пэ",
        "МВД": "эм вэ дэ",
        "ФСБ": "эф эс бэ",
        "ФБР": "эф бэ эр",
        "ЦРУ": "цэ эр у",
        "ООН": "о о эн",
        "США": "эс ша а",
        "МЧС": "эм чэ эс",
        "МИД": "мид",
        "ГДР": "гэ дэ эр",
        "НДС": "эн дэ эс",
        "ВНП": "вэ эн пэ",
        "КГБ": "кэ гэ бэ",
        "ФНС": "эф эн эс",
        "РЖД": "эр жэ дэ",
        "МГУ": "эм гэ у",
        "ЕГЭ": "е гэ э",
        "ОГЭ": "о гэ э",
        "ЧП": "чэ пэ",
        "ИП": "и пэ",
        "ООО": "о о о",
        "АО": "а о",
        "ПАО": "пэ а о",
    }

    def _ordinal_neuter(self, n: int) -> str:
        cached = self.ORDINALS.get(n)
        if cached is not None:
            return cached
        word = num2words(n, lang="ru", to="ordinal")
        if word.endswith("ый"):
            word = word[:-2] + "ое"
        elif word.endswith("ий"):
            word = word[:-2] + "ье"
        elif word.endswith("ой"):
            word = word[:-2] + "ое"
        return word

    @staticmethod
    def _render_abbrev_series(words: list) -> str:
        """Чередует запятую и точку каждые 2 элемента серии аббревиатур."""
        parts = []
        for i, word in enumerate(words):
            if i == len(words) - 1:
                parts.append(word + ".")
            elif (i + 1) % 2 == 0:
                parts.append(word + ".")
            else:
                parts.append(word + ",")
        return " ".join(parts)

    def _fix_abbrev_rhythm(self, text: str) -> str:
        """
        Латинские аббревиатуры: серии получают ритм , и .
        Одиночные — точку в конце.
        """

        def replace_series(m: re.Match) -> str:
            raw = m.group(0)
            words = re.findall(r"[A-Z]{2,8}", raw)
            if len(words) == 1:
                return words[0]
            return self._render_abbrev_series(words)

        # серия из 2+ латинских аббревиатур
        text = re.sub(
            r"\b[A-Z]{2,8}\b(?:[\s,\.]+\b[A-Z]{2,8}\b)+",
            replace_series,
            text,
        )

        return text

    def _fix_mixed_case_rhythm(self, text: str) -> str:
        """
        Смешанный регистр / бренды (CamelCase, 2+ заглавных блока внутри слова):
        OpenAI, ChatGPT, PyTorch, JavaScript, GitHub.
        Не трогает обычные слова с одной заглавной буквой в начале (Привет, Hello)
        и не трогает чистые аббревиатуры (CPU, GPU) — те уже обработаны в
        _fix_abbrev_rhythm. Логика ритма (, и .) идентична _render_abbrev_series.
        """
        # слово должно содержать минимум 2 заглавных блока:
        # заглавная буква в начале ИЛИ внутри слова, плюс строчные между ними
        mixed_word = r"(?:[A-Z][a-z]*){2,}"

        def replace_series(m: re.Match) -> str:
            raw = m.group(0)
            words = re.findall(mixed_word, raw)
            if len(words) == 1:
                return words[0]
            return self._render_abbrev_series(words)

        # серия из 2+ смешанных слов
        text = re.sub(
            rf"\b{mixed_word}\b(?:[\s,\.]+\b{mixed_word}\b)+",
            replace_series,
            text,
        )
        return text

    def _fix_cyrillic_abbrev(self, text: str) -> str:
        """
        Кириллические аббревиатуры:
        - если есть в словаре → заменяем на произношение
        - если нет → применяем ритм , и . как для латиницы
        """
        # сначала заменяем известные из словаря
        for abbr, pronunciation in self.CYR_ABBREV_DICT.items():
            text = re.sub(
                rf"\b{re.escape(abbr)}\b",
                pronunciation,
                text,
            )

        # серии неизвестных кириллических аббревиатур (2-6 заглавных букв)
        def replace_cyr_series(m: re.Match) -> str:
            raw = m.group(0)
            words = re.findall(r"[А-ЯЁ]{2,6}", raw)
            if len(words) == 1:
                return words[0]
            return self._render_abbrev_series(words)

        text = re.sub(
            r"\b[А-ЯЁ]{2,6}\b(?:[\s,\.]+\b[А-ЯЁ]{2,6}\b)+",
            replace_cyr_series,
            text,
        )
        return text

    def _yoficator(self, text: str) -> str:
        """
        Автоматическая Ёфикация наиболее частотных и однозначных слов.
        XTTS v2 значительно лучше интонирует и ставит ударения при явном наличии буквы Ё.
        """
        yo_words = {
            "еще": "ещё",
            "Еще": "Ещё",
            "ее": "её",
            "Ее": "Её",
            "мое": "моё",
            "Мое": "Моё",
            "твое": "твоё",
            "Твое": "Твоё",
            "свое": "своё",
            "Свое": "Своё",
            "нее": "неё",
            "Нее": "Неё",
            "черт": "чёрт",
            "Черт": "Чёрт",
            "идет": "идёт",
            "Идет": "Идёт",
            "ждет": "ждёт",
            "Ждет": "Ждёт",
            "бьет": "бьёт",
            "Бьет": "Бьёт",
            "пьет": "пьёт",
            "Пьет": "Пьёт",
            "поет": "поёт",
            "Поет": "Поёт",
            "придет": "придёт",
            "Придет": "Придёт",
            "уйдет": "уйдёт",
            "Уйдет": "Уйдёт",
            "назовет": "назовёт",
            "Назовет": "Назовёт",
            "смеется": "смеётся",
            "Смеется": "Смеётся",
        }
        for word, yo_word in yo_words.items():
            text = re.sub(rf"\b{word}\b", yo_word, text)
        return text

    # Известные НЕ-временные X:Y (соотношения сторон и т.п.) — проверяются
    # первыми, до того как число попадёт в общее правило "читать как время".
    # Пополняйте вручную по мере обнаружения новых кейсов.
    KNOWN_COLON_RATIOS = {
        "16:9": "шестнадцать на девять",
        "4:3": "четыре на три",
        "21:9": "двадцать один на девять",
        "1:1": "один к одному",
    }

    def _replace_time_and_ratio(self, text: str) -> str:
        """
        Числа вида X:Y, которые не были превращены в паузу (защищены в
        BASIC CLEANUP как цифра-двоеточие-цифра).
        По умолчанию ВСЁ читается как время: "14:30" → "четырнадцать тридцать",
        "9:05" → "девять ноль пять" (с ведущим нулём — по цифрам).
        Отличить время от соотношения (16:9 vs "16 минут девятого") надёжной
        эвристикой нельзя, поэтому известные исключения (соотношения сторон
        и т.п.) заданы явным словарём KNOWN_COLON_RATIOS и обрабатываются
        first.
        """

        def repl(m: re.Match) -> str:
            raw = m.group(0)
            if raw in self.KNOWN_COLON_RATIOS:
                return self.KNOWN_COLON_RATIOS[raw]
            h_str, mm_str = m.group(1), m.group(2)
            h, mm = int(h_str), int(mm_str)
            h_words = num2words(h, lang="ru")
            if mm == 0:
                mm_words = "ноль"
            elif mm < 10 and len(mm_str) == 2:
                mm_words = "ноль " + num2words(mm, lang="ru")
            else:
                mm_words = num2words(mm, lang="ru")
            return f"{h_words} {mm_words}"

        return re.sub(r"\b(\d{1,2}):(\d{1,2})\b", repl, text)

    def normalize(self, text: str) -> str:
        if not text:
            return ""

        # =========================
        # BASIC CLEANUP
        # =========================
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = text.replace("—", "...")
        text = re.sub(r"\s-\s", ", ", text)
        # двоеточие -> пауза, но не трогаем время (14:30) и соотношения (16:9)
        text = re.sub(r"(?<!\d):(?!\d)", "...", text)

        # Разворачивание частых сокращений с точками (до очистки пунктуации)
        text = re.sub(r"\bи\s+т\.\s*д\.\b", "и так далее", text, flags=re.IGNORECASE)
        text = re.sub(r"\bи\s+т\s*п\.\b", "и тому подобное", text, flags=re.IGNORECASE)
        text = re.sub(r"\bт\.\s*д\.\b", "так далее", text, flags=re.IGNORECASE)
        text = re.sub(r"\bт\.\s*п\.\b", "тому подобное", text, flags=re.IGNORECASE)
        text = re.sub(r"\bи\s+др\.\b", "и другие", text, flags=re.IGNORECASE)
        text = re.sub(r"\bсм\.\b", "смотри", text, flags=re.IGNORECASE)
        text = re.sub(r"\bстр\.\b", "страница", text, flags=re.IGNORECASE)
        text = re.sub(r"\bруб\.\b", "рублей", text, flags=re.IGNORECASE)
        text = re.sub(r"\bкоп\.\b", "копеек", text, flags=re.IGNORECASE)
        text = re.sub(r"\bтыс\.\b", "тысяч", text, flags=re.IGNORECASE)
        text = re.sub(r"\bмлн\b", "миллионов", text, flags=re.IGNORECASE)
        text = re.sub(r"\bмлрд\b", "миллиардов", text, flags=re.IGNORECASE)
        text = re.sub(r"\bкм/ч\b", "километров в час", text, flags=re.IGNORECASE)
        text = re.sub(r"\bм/с\b", "метров в секунду", text, flags=re.IGNORECASE)

        # проценты: 87% → 87 процентов
        text = re.sub(r"(\d+)\s*%", r"\1 процентов", text)

        text = re.sub(r"!{2,}", "!", text)
        text = re.sub(r"\?{2,}", "?", text)
        text = re.sub(r",{2,}", ",", text)
        text = re.sub(r",([A-ZА-ЯЁa-zа-яё])", r", \1", text)
        text = "\n".join(line.strip() for line in text.split("\n"))
        text = re.sub(r"\n{2,}", "\n", text)
        text = re.sub(r"(\.)([A-ZА-ЯЁ])", r"\1 \2", text)
        text = re.sub(r"\s+", " ", text).strip()

        # =========================
        # AUTOMATIC YO-FICATION
        # =========================
        text = self._yoficator(text)

        # =========================
        # ABBREV RHYTHM (латиница)
        # CPU GPU RAM → CPU, GPU. RAM.
        # =========================
        text = self._fix_abbrev_rhythm(text)

        # =========================
        # MIXED CASE RHYTHM (CamelCase / бренды)
        # OpenAI ChatGPT PyTorch → OpenAI, ChatGPT. PyTorch.
        # =========================
        text = self._fix_mixed_case_rhythm(text)

        # =========================
        # ABBREV RHYTHM (кириллица)
        # ВВП РФ → вэ вэ пэ, эр эф.
        # =========================
        text = self._fix_cyrillic_abbrev(text)

        # убираем двойную пунктуацию
        text = re.sub(r"([.,])\s*([.,])", r"\1", text)
        text = re.sub(r"\s+", " ", text).strip()

        # =========================
        # NUMBERS TO WORDS
        # =========================
        # 0. Время (14:30) и соотношения/счёт (16:9) — до общей конвертации чисел
        text = self._replace_time_and_ratio(text)

        # 1. Нумерованные списки: "1)" → "первое,"
        text = re.sub(
            r"\b(\d+)\)",
            lambda m: self._ordinal_neuter(int(m.group(1))) + ",",
            text,
        )

        # 2. Функция для замены обычных чисел
        def replace_number(match):
            num_str = match.group(0).replace(" ", "")
            try:
                num = int(num_str)
                return num2words(num, lang="ru")
            except ValueError:
                try:
                    num = float(num_str.replace(",", "."))
                    return num2words(num, lang="ru")
                except Exception:
                    return num_str
            except Exception:
                return num_str

        # проценты: 87% → 87 процентов
        text = re.sub(r"(\d+)\s*%", r"\1 процентов", text)

        # дробные через точку → через запятую
        text = re.sub(r"\b(\d+)\.(\d+)\b", r"\1,\2", text)

        # 3. Дробные числа через запятую: 3,14
        text = re.sub(r"\b\d+,\d+\b", replace_number, text)

        # 4. Целые числа
        text = re.sub(r"\b\d[\d ]{0,30}\d\b|\b\d\b", replace_number, text)

        # =========================
        # LINE CLEANUP
        # =========================
        text = "\n".join(line.strip() for line in text.split("\n"))
        text = re.sub(r"\n{2,}", "\n", text)

        # =========================
        # FINAL NORMALIZATION
        # =========================
        text = text.strip()
        text = re.sub(r"[.,]+$", "", text)

        # пауза перед противительными союзами
        text = re.sub(
            r"(?<![,;!?\.])(\s+)(но|однако|хотя|зато|впрочем|тем\s+не\s+менее)\b",
            r",\1\2",
            text,
            flags=re.IGNORECASE,
        )

        # «а» отдельно — только если перед ней строчная буква/цифра
        text = re.sub(
            r"(?<=[а-яёa-z0-9])(\s+)(а)\s+(?!то\b|значит\b|также\b|ещё\b|еще\b|о\b)",
            r",\1\2 ",
            text,
            flags=re.IGNORECASE,
        )

        if text and text[-1] not in ".!?":
            text += "."
        return text

    def safe_character_filter(self, text: str) -> str:
        """
        Вынесено из normalize(), чтобы вызываться ПОСЛЕ word_replacer.apply() —
        иначе словарь не находит C++/C#/км/ч, т.к. +, #, / уже выброшены.
        """
        text = re.sub(
            r"[^\w\s.,!?:;\"'\-()\nа-яА-ЯёЁa-zA-Z0-9]",
            "",
            text,
        )
        text = text.strip()
        text = re.sub(r"[.,]+$", "", text)
        if text and text[-1] not in ".!?":
            text += "."
        return text
