import pytest

from engine.smart_pauses import SmartPauseEngine


@pytest.fixture
def engine():
    return SmartPauseEngine()


class TestGetPauseMs:
    def test_empty(self, engine):
        assert engine.get_pause_ms("") == engine.base_short
        assert engine.get_pause_ms("   ") == engine.base_short

    def test_list_item_current(self, engine):
        # текущий — list item
        assert engine.get_pause_ms("1. первый пункт") == engine.list_item_pause
        assert engine.get_pause_ms("- яблоко") == engine.list_item_pause

    def test_list_item_next(self, engine):
        # следующий — list item
        assert (
            engine.get_pause_ms("Обычный текст.", next_chunk="2. второй") == engine.list_item_pause
        )
        assert engine.get_pause_ms("Текст", next_chunk="- груша") == engine.list_item_pause

    def test_punctuation_base(self, engine):
        assert engine.get_pause_ms("Привет...") == engine.base_dramatic
        assert engine.get_pause_ms("Как дела?") == engine.base_long + 60
        assert engine.get_pause_ms("Отлично!") == engine.base_long - 20
        assert engine.get_pause_ms("Закончили.") == engine.base_medium
        assert engine.get_pause_ms("Пауза,") == engine.base_short
        assert engine.get_pause_ms("Без знака") == engine.base_short

    def test_length_modifier(self, engine):
        short = "Привет."
        long_text = "Это очень длинное предложение с большим количеством слов для проверки модификатора длины."
        short_pause = engine.get_pause_ms(short)
        long_pause = engine.get_pause_ms(long_text)
        # длинный должен дать большую паузу (word_count>6 adds)
        assert long_pause >= short_pause

    def test_clamp_min(self, engine):
        # даже очень короткий должен быть >=50
        result = engine.get_pause_ms("А.")
        assert result >= 50

    def test_clamp_max(self, engine):
        # очень длинный + ? → может превысить 450, но clamp до 450
        very_long = "Слово " * 100 + "?"
        result = engine.get_pause_ms(very_long)
        assert result <= 450

    def test_list_item_overrides_clamp(self, engine):
        # list_item_pause = 450, уже на границе clamp
        assert engine.get_pause_ms("1. пункт", next_chunk="") == 450

    def test_next_chunk_trim(self, engine):
        # next_chunk с пробелами должен trim и детектиться как list item
        assert engine.get_pause_ms("Текст", next_chunk="  1. пункт  ") == engine.list_item_pause


class TestDetectEmotion:
    def test_excited(self, engine):
        assert engine.detect_emotion("Wow, amazing!") == "excited"
        assert engine.detect_emotion("Это потрясающе и невероятно!") == "excited"
        assert engine.detect_emotion("Отлично, супер класс!") == "excited"

    def test_uncertain(self, engine):
        assert engine.detect_emotion("Maybe it works") == "uncertain"
        assert engine.detect_emotion("Может быть, наверное") == "uncertain"
        assert engine.detect_emotion("Не уверен, возможно") == "uncertain"

    def test_normal(self, engine):
        assert engine.detect_emotion("Обычный текст без эмоций.") == "normal"
        assert engine.detect_emotion("") == "normal"
        assert engine.detect_emotion("Привет мир") == "normal"

    def test_case_insensitive(self, engine):
        assert engine.detect_emotion("WOW") == "excited"
        assert engine.detect_emotion("MAYBE") == "uncertain"

    def test_excited_priority(self, engine):
        # если есть и excited и uncertain — excited первый в коде, должен вернуться excited
        assert engine.detect_emotion("Wow, maybe") == "excited"
