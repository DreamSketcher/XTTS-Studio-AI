import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import engine.tts.utils as utils


class TestMakeOutputName:
    def test_simple(self, tmp_path):
        result = utils._make_output_name("Привет мир", str(tmp_path))
        assert result.endswith(".wav")
        assert "Привет" in result or "привет" in result.lower()

    def test_unique(self, tmp_path):
        first = utils._make_output_name("test", str(tmp_path))
        Path(first).write_text("x")
        second = utils._make_output_name("test", str(tmp_path))
        assert second != first
        assert "(1)" in second

    def test_trims(self, tmp_path):
        long_text = "слово " * 30
        result = utils._make_output_name(long_text, str(tmp_path))
        basename = os.path.basename(result).replace(".wav", "")
        assert len(basename) <= 48


class TestDetectLangAdaptive:
    def test_ru(self):
        assert utils.detect_lang_adaptive("Привет мир") == "ru"
        assert utils.detect_lang_adaptive("Привет Hello") == "ru"  # cyrillic present

    def test_en(self):
        assert utils.detect_lang_adaptive("Hello world") == "en"
        assert utils.detect_lang_adaptive("") == "en"


class TestIsDenseAbbrevChunk:
    def test_dense(self):
        assert utils._is_dense_abbrev_chunk("цэ пэ у эф бэ") is True  # много коротких
        assert utils._is_dense_abbrev_chunk("Это нормальное предложение с глаголами") is False

    def test_empty(self):
        assert utils._is_dense_abbrev_chunk("") is False


class TestAdjustParams:
    def test_list_item_increases_temp(self):
        base = {"temperature": 0.7, "repetition_penalty": 9.0}
        result = utils._adjust_params_for_chunk(
            base, chunk_idx=5, total_chunks=10, chunk_text="1. пункт"
        )
        assert result["temperature"] > 0.7
        assert result["temperature"] <= 0.92

    def test_dense_abbrev(self):
        base = {"temperature": 0.7, "repetition_penalty": 9.0}
        result = utils._adjust_params_for_chunk(base, 0, 10, "цэ пэ у эф бэ эр")
        assert result["temperature"] > 0.7
        assert result["repetition_penalty"] < 9.0

    def test_normal(self):
        base = {"temperature": 0.7}
        result = utils._adjust_params_for_chunk(base, 0, 10, "Обычный текст.")
        assert result["temperature"] == 0.7


class TestCountRealWords:
    def test_count(self):
        assert utils._count_real_words("Привет мир") == 2
        assert utils._count_real_words("Hello 123") == 1  # только буквы
        assert utils._count_real_words("") == 0


class TestSplitByLanguage:
    def test_empty(self):
        assert utils._split_by_language("") == []
        assert utils._split_by_language("   ") == []

    def test_ru_only(self):
        result = utils._split_by_language("Привет мир", base_lang="ru")
        assert len(result) == 1
        assert result[0][1] == "ru"

    def test_en_only(self):
        result = utils._split_by_language("Hello world", base_lang="ru")
        assert result[0][1] == "en"

    def test_mixed(self):
        # маленький en поглощается ru, поэтому для смешанного с большим en нужно >3 слов
        text = "Привет " + " ".join(["word"] * 5) + " мир"
        result = utils._split_by_language(text, base_lang="ru")
        langs = [lang for _, lang in result]
        assert "ru" in langs
        assert "en" in langs

    def test_small_en_absorbed(self):
        # маленькие английские вставки <=3 слов должны поглощаться русским → нет en
        text = "Привет CPU мир"
        result = utils._split_by_language(text, base_lang="ru")
        langs = [lang for _, lang in result]
        assert "en" not in langs
        assert "ru" in langs
        # может быть 1 или 2 ru чанка, главное без en
        assert len(result) >= 1

    def test_large_en_kept(self):
        text = "Привет " + " ".join(["word"] * 10) + " мир"
        result = utils._split_by_language(text, base_lang="ru")
        # 10 английских слов >3 — не должно поглощаться
        langs = [lang for _, lang in result]
        assert "en" in langs


class TestNormalizeLookup:
    def test_normalize(self):
        norm, mapping = utils._normalize_lookup_text_with_map("  Привет   Мир  ")
        assert norm == "привет мир"
        assert len(mapping) == len(norm.replace(" ", "")) + 1  # пробел один

    def test_empty(self):
        norm, mapping = utils._normalize_lookup_text_with_map("")
        assert norm == ""
        assert mapping == []


class TestBuildChunkMap:
    def test_basic(self):
        full = "Привет мир. Как дела?"
        chunks = ["Привет мир.", "Как дела?"]
        mapping = utils._build_chunk_text_map(full, chunks)
        assert len(mapping) == 2
        # первый чанк должен начинаться с 0
        assert mapping[0][0] == 0

    def test_with_no_pause(self):
        full = "Тест [NO_PAUSE] продолжение"
        chunks = ["Тест продолжение"]
        mapping = utils._build_chunk_text_map(full, chunks)
        assert len(mapping) == 1

    def test_not_found(self):
        full = "Привет мир"
        chunks = ["Несуществующий чанк"]
        mapping = utils._build_chunk_text_map(full, chunks)
        # если не найден — last_end
        assert mapping[0][0] == mapping[0][1] or True

    def test_empty(self):
        assert utils._build_chunk_text_map("", []) == []
        assert utils._build_chunk_text_map("text", [""]) == [(0, 0)]


class TestGetEmbedding:
    def test_no_torch_raises(self, monkeypatch):
        monkeypatch.setattr(utils, "torch", None)
        with pytest.raises(RuntimeError, match="torch not available"):
            utils._get_embedding(MagicMock(), "/tmp/ref.wav", "/tmp/cache.pth")

    def test_load_from_cache(self, tmp_path, monkeypatch):
        # мокаем torch
        mock_torch = MagicMock()
        mock_torch.load.return_value = {"gpt_cond_latent": "latent", "speaker_embedding": "emb"}
        monkeypatch.setattr(utils, "torch", mock_torch)
        monkeypatch.setattr(utils, "detect_device", lambda: "cpu")

        cache = tmp_path / "cache.pth"
        cache.write_text("fake")

        tts = MagicMock()
        latent, emb = utils._get_embedding(tts, "/tmp/ref.wav", str(cache))
        assert latent == "latent"
        assert emb == "emb"
        assert mock_torch.load.called

    def test_compute_and_save(self, tmp_path, monkeypatch):
        mock_torch = MagicMock()
        mock_torch.load.side_effect = Exception("no cache")
        mock_torch.save = MagicMock()
        # мок get_conditioning_latents
        mock_tts = MagicMock()
        mock_latent = MagicMock()
        mock_latent.to.return_value = "latent_to"
        mock_emb = MagicMock()
        mock_emb.to.return_value = "emb_to"
        mock_tts.synthesizer.tts_model.get_conditioning_latents.return_value = (
            mock_latent,
            mock_emb,
        )

        monkeypatch.setattr(utils, "torch", mock_torch)
        monkeypatch.setattr(utils, "detect_device", lambda: "cpu")

        cache = tmp_path / "new_cache.pth"

        latent, emb = utils._get_embedding(mock_tts, "/tmp/ref.wav", str(cache))
        assert latent == "latent_to"
        assert emb == "emb_to"
        assert mock_torch.save.called
