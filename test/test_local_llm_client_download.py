# -*- coding: utf-8 -*-
"""
test_local_llm_client_download.py — тесты для engine/local_llm_client.py,
конкретно для retry/resume-логики download_model() при обрыве соединения
(SSL EOF, URLError и т.п.) — то, что раньше приводило к полному провалу
скачивания модели с одной оборвавшейся попыткой.

Ничего не ходит в реальную сеть: urllib.request.urlopen подменяется мок-
объектом с управляемым поведением (может "оборвать" соединение посреди
чтения потока). time.sleep подменяется на no-op, чтобы тесты не ждали
реальные секунды backoff'а.

Запуск:
    pytest test_local_llm_client_download.py -v
"""
import os
import ssl
import urllib.error

import pytest

from engine import local_llm_client


class FakeResponse:
    """Полноценный ответ без обрывов."""

    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self._pos = 0
        self.status = status
        self.headers = {"Content-Length": str(len(data))}

    def read(self, n):
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class DroppingResponse(FakeResponse):
    """Отдаёт данные до cutoff байт, потом бросает SSLError — имитация
    обрыва соединения посреди скачивания (как реальный
    UNEXPECTED_EOF_WHILE_READING)."""

    def __init__(self, data: bytes, cutoff: int, status: int = 200):
        super().__init__(data, status)
        self._cutoff = cutoff

    def read(self, n):
        if self._pos >= self._cutoff:
            raise ssl.SSLError("UNEXPECTED_EOF_WHILE_READING")
        chunk = self._data[self._pos : min(self._pos + n, self._cutoff)]
        self._pos += len(chunk)
        return chunk


@pytest.fixture
def isolated_models_dir(tmp_path, monkeypatch):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(local_llm_client, "MODELS_DIR", str(models_dir))
    monkeypatch.setattr(local_llm_client.time, "sleep", lambda s: None)  # без реальных задержек
    return models_dir


def _last_range_offset(req) -> int:
    """Достаёт offset из заголовка Range: bytes=N- запроса."""
    range_header = req.headers.get("Range") or req.headers.get("range")
    if not range_header:
        return 0
    return int(range_header.split("=")[1].rstrip("-"))


# ───────────────────────── восстановление после обрыва ─────────────────────────


def test_download_recovers_after_transient_drop(isolated_models_dir, monkeypatch):
    """Первая попытка обрывается на середине, вторая — докачивает остаток.
    Итоговый файл должен побайтово совпадать с оригиналом."""
    content = b"A" * 200_000
    cutoff = 50_000
    call_log = []

    def fake_urlopen(req, timeout=30, context=None):
        offset = _last_range_offset(req)
        call_log.append(offset)
        if len(call_log) == 1:
            return DroppingResponse(content, cutoff=cutoff)
        # вторая попытка — отдаём остаток с нужного оффсета, как настоящий сервер с Range
        return FakeResponse(content[offset:], status=206 if offset > 0 else 200)

    monkeypatch.setattr(local_llm_client.urllib.request, "urlopen", fake_urlopen)

    path = local_llm_client.download_model("http://fake/model.gguf", "model.gguf")

    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == content
    assert len(call_log) == 2, "должно было потребоваться ровно 2 попытки"
    assert call_log[1] == cutoff, "вторая попытка должна была запросить Range именно с места обрыва"
    # чекпоинт должен быть очищен после успеха
    assert not os.path.exists(local_llm_client._download_checkpoint_path("model.gguf"))


def test_download_exhausts_retries_and_raises(isolated_models_dir, monkeypatch):
    """Если соединение рвётся КАЖДЫЙ раз — после _MAX_DOWNLOAD_RETRIES попыток
    должно быть RuntimeError с понятным сообщением, а не бесконечный цикл."""
    content = b"B" * 10_000
    attempts = {"n": 0}

    def always_dropping(req, timeout=30, context=None):
        attempts["n"] += 1
        return DroppingResponse(content, cutoff=100)

    monkeypatch.setattr(local_llm_client.urllib.request, "urlopen", always_dropping)

    with pytest.raises(RuntimeError, match="обрыв соединения"):
        local_llm_client.download_model("http://fake/model.gguf", "model.gguf")

    assert attempts["n"] == local_llm_client._MAX_DOWNLOAD_RETRIES


def test_http_error_is_not_retried(isolated_models_dir, monkeypatch):
    """HTTPError (404 и т.п.) — логическая ошибка, а не обрыв связи.
    Ретраить её бессмысленно, должна падать сразу с первой попытки."""
    attempts = {"n": 0}

    def raise_http_error(req, timeout=30, context=None):
        attempts["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, None)

    monkeypatch.setattr(local_llm_client.urllib.request, "urlopen", raise_http_error)

    with pytest.raises(RuntimeError, match="404"):
        local_llm_client.download_model("http://fake/model.gguf", "model.gguf")

    assert attempts["n"] == 1, "HTTPError не должен ретраиться"


def test_cancellation_during_retry_backoff_raises_interrupted(isolated_models_dir, monkeypatch):
    """Пользователь отменяет скачивание, пока идёт ожидание перед повторной
    попыткой — должно прерваться быстро, а не досиживать полный backoff."""
    content = b"C" * 10_000

    def always_dropping(req, timeout=30, context=None):
        return DroppingResponse(content, cutoff=100)

    monkeypatch.setattr(local_llm_client.urllib.request, "urlopen", always_dropping)

    cancelled_flag = {"cancelled": True}  # уже отменено — должно прерваться на первом же ожидании

    with pytest.raises(InterruptedError):
        local_llm_client.download_model(
            "http://fake/model.gguf",
            "model.gguf",
            cancelled_flag=cancelled_flag,
        )


def test_successful_download_without_any_drop(isolated_models_dir, monkeypatch):
    """Базовый happy-path — без единого обрыва, для контраста с остальными тестами."""
    content = b"D" * 5000

    def clean_urlopen(req, timeout=30, context=None):
        return FakeResponse(content)

    monkeypatch.setattr(local_llm_client.urllib.request, "urlopen", clean_urlopen)

    path = local_llm_client.download_model("http://fake/model.gguf", "model.gguf")

    with open(path, "rb") as f:
        assert f.read() == content


def test_checkpoint_saved_after_drop_matches_downloaded_bytes(isolated_models_dir, monkeypatch):
    """Пока идёт ретрай (до финального успеха/провала), чекпоинт на диске
    должен отражать реально скачанный на данный момент объём — на случай,
    если приложение закроется прямо посреди повторных попыток."""
    content = b"E" * 10_000
    cutoff = 3000
    seen_checkpoints = []
    original_save = local_llm_client._save_download_checkpoint

    def spying_save(filename, offset, total, url):
        seen_checkpoints.append(offset)
        return original_save(filename, offset, total, url)

    monkeypatch.setattr(local_llm_client, "_save_download_checkpoint", spying_save)

    call_count = {"n": 0}

    def fake_urlopen(req, timeout=30, context=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return DroppingResponse(content, cutoff=cutoff)
        offset = _last_range_offset(req)
        return FakeResponse(content[offset:], status=206)

    monkeypatch.setattr(local_llm_client.urllib.request, "urlopen", fake_urlopen)

    local_llm_client.download_model("http://fake/model.gguf", "model.gguf")

    assert (
        cutoff in seen_checkpoints
    ), "после обрыва должен был сохраниться чекпоинт ровно на том объёме, что успел скачаться"
