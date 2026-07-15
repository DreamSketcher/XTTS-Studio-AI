import re


class TextChunker:
    def __init__(self):
        # =========================
        # LIMITS
        # =========================
        self.max_size = 175
        self.target_size = 150
        self.min_size = 50

        # =========================
        # PROSODY SAFETY RULES
        # =========================

        # ❌ НЕЛЬЗЯ НАЧИНАТЬ ЧАНК С ЭТОГО (самая частая причина “задыхания”)
        self.bad_start_tokens = (
            "и",
            "а",
            "но",
            "или",
            "который",
            "которая",
            "которое",
            "которые",
            "что",
            "где",
            "когда",
            "это",
            "такие",
            "таким",
            "такая",
            "включая",
            "например",
        )

        # ❌ НЕЛЬЗЯ ЗАКАНЧИВАТЬ ЧАНК НА ЭТО
        self.bad_end_tokens = ("и", "а", "но", "или", "который", "которая", "которое", "которые")

        # 🔥 СИЛЬНЫЕ РАЗРЫВЫ (идеальные точки реза)
        self.hard_break = r"[.!?]"

        # 🟡 СРЕДНИЕ РАЗРЫВЫ
        self.soft_break = r"[;—]"

        # 🟠 СЛАБЫЕ РАЗРЫВЫ
        self.weak_break = r","

    # =========================
    # SENTENCE SPLIT (SAFE)
    # =========================
    def _split_sentences(self, text):
        text = text.replace("...", "<ELL>")
        # 🔥 FIX: схлопываем случайно задвоенные знаки препинания ("он..", "!!", "?!"),
        # оставшиеся после копипаста/OCR — иначе такой артефакт создаёт ложную границу
        # предложения и отрывает перечисление от вводной фразы (см. "он.. ходьбу, лодку...")
        text = re.sub(r"([.!?])\1+", r"\1", text)
        # Регулярное выражение с негативным просмотром назад (negative lookbehind),
        # чтобы предотвратить ложную разбивку предложений на инициалах вроде "А. С. Пушкин"
        parts = re.split(r"(?<!\b[A-ZА-ЯЁ])(?<=[.!?])\s+", text)
        return [p.replace("<ELL>", "...") for p in parts if p.strip()]

    # =========================
    # BAD START CHECK
    # =========================
    def _is_bad_start(self, chunk: str) -> bool:
        c = chunk.strip().lower()
        return any(c.startswith(tok + " ") or c == tok for tok in self.bad_start_tokens)

    # =========================
    # BAD END CHECK
    # =========================
    def _is_bad_end(self, chunk: str) -> bool:
        c = chunk.strip().lower()
        return any(c.endswith(" " + tok) or c == tok for tok in self.bad_end_tokens)

    # =========================
    # ENUMERATION DETECTION
    # =========================
    def _is_enumeration(self, text: str) -> bool:
        """
        Плотное перечисление (много однородных элементов через запятую,
        почти без других знаков разрыва) — статистически проблемная для XTTS
        структура: авторегрессивный декодер склонен "рваться"/повторяться на
        длинной монотонной последовательности "слово, слово, слово...".
        """
        commas = text.count(",")
        strong = len(re.findall(r"[.!?;:—]", text))
        return commas >= 5 and commas > strong * 2

    # =========================
    # SCORE CUT POSITION
    # =========================
    def _score(self, text, pos, is_enum=False):
        char = text[pos] if pos < len(text) else ""
        # 🔥 FIX: для плотных перечислений режем чаще и короче — даём XTTS больше
        # "точек передышки" вместо одного длинного монотонного чанка
        target = self.target_size * 0.6 if is_enum else self.target_size
        dist = abs(pos - target)

        score = 0

        if char in ".!?":
            score += 100
        elif char in ";":
            score += 70
        elif char in "—":
            score += 60
        elif char == ":":
            score += 65
        elif char == ",":
            score += 75 if is_enum else 20

        score -= dist * 0.25
        return score

    # =========================
    # SMART SPLIT
    # =========================
    def _split_long(self, text):
        if len(text) <= self.max_size:
            return [text]

        is_enum = self._is_enumeration(text)

        out = []
        remaining = text

        while len(remaining) > self.max_size:

            window_end = min(len(remaining), self.max_size)
            candidates = []

            for m in re.finditer(r"[.!?;,—:]", remaining[:window_end]):
                pos = m.start()

                if pos < self.min_size:
                    continue

                candidates.append((pos, self._score(remaining, pos, is_enum)))

            if candidates:
                best = max(candidates, key=lambda x: x[1])
                cut = best[0] + 1
            else:
                cut = remaining.rfind(" ", self.min_size, window_end)
                if cut == -1:
                    cut = remaining.rfind(" ", 0, window_end)
                if cut == -1:
                    cut = window_end

            chunk = remaining[:cut].strip()
            remaining = remaining[cut:].strip()

            # 🔥 FIX: remove bad start continuity
            if out and self._is_bad_start(chunk):
                out[-1] = out[-1] + " " + chunk
            else:
                out.append(chunk)

        if remaining:
            remaining = remaining.strip()
            # ТА ЖЕ проверка, что и внутри while-цикла: если хвостовой остаток
            # начинается с запрещённого токена ("и", "что", "а" и т.д.),
            # он должен приклеиться к предыдущему чанку, а не звучать как
            # оборванная мысль в отдельном TTS-чанке.
            if out and self._is_bad_start(remaining):
                out[-1] = out[-1] + " " + remaining
            else:
                out.append(remaining)

        return out

    # =========================
    # MERGE SAFETY
    # =========================
    def _merge(self, chunks):
        out = []
        buf = ""

        for c in chunks:
            c = c.strip()
            if not c:
                continue

            if len(buf) < self.min_size:
                buf = (buf + " " + c).strip()
                continue

            if len(buf) + len(c) <= self.max_size:
                buf = (buf + " " + c).strip()
            else:
                if not self._is_bad_end(buf):
                    out.append(buf)
                    buf = c
                else:
                    buf = buf + " " + c

        if buf:
            out.append(buf)

        return out

    # =========================
    # PUBLIC
    # =========================
    def chunk_text(self, text: str):
        sentences = self._split_sentences(text)

        chunks = []
        for s in sentences:
            chunks.extend(self._split_long(s))

        chunks = self._merge(chunks)

        return [c.strip() for c in chunks if c.strip()]
