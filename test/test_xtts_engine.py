"""Тесты engine/xtts_engine.py — каталог файлов движка, статус, скачивание."""

import hashlib
import json
import os
import urllib.error

import pytest

import engine.xtts_engine as xe


# ── Фейковый движок в tmp_path ─────────────────────────────────────────────────

CONTENTS = {
    "model.pth": b"FAKE-MODEL-BYTES",
    "speakers_xtts.pth": b"FAKE-SPEAKERS-BYTES",
    "vocab.json": json.dumps(["a", "b", "c"]).encode("utf-8"),
    "config.json": json.dumps({"model": "xtts", "model_args": {"gpt_layers": 30}}).encode("utf-8"),
    "hash.md5": xe.OFFICIAL_MODEL_MD5.encode("ascii"),
}


def _fake_files():
    files = []
    for name, data in CONTENTS.items():
        entry = {"name": name, "size": len(data)}
        if name in ("model.pth", "speakers_xtts.pth"):
            entry["sha256"] = hashlib.sha256(data).hexdigest()
        if name == "model.pth":
            entry["md5"] = hashlib.md5(data).hexdigest()  # фейк: не офиц. константа
        elif name == "vocab.json":
            entry["json"] = "vocab"
        elif name == "config.json":
            entry["json"] = "xtts_config"
        elif name == "hash.md5":
            entry["md5_file"] = xe.OFFICIAL_MODEL_MD5
        files.append(entry)
    return tuple(files)


@pytest.fixture
def fake_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(xe, "ENGINE_DIR", str(tmp_path))
    monkeypatch.setattr(xe, "ENGINE_FILES", _fake_files())
    monkeypatch.setattr(xe, "ENGINE_TOTAL_BYTES", sum(len(d) for d in CONTENTS.values()))
    return tmp_path


def _write_fake_engine(directory, names=None):
    for name, data in CONTENTS.items():
        if names and name not in names:
            continue
        with open(os.path.join(directory, name), "wb") as f:
            f.write(data)


# ── engine_status / engine_ready ──────────────────────────────────────────────


def test_engine_missing_when_empty(fake_engine):
    status = xe.engine_status()
    assert status["state"] == "missing"
    assert sorted(status["missing"]) == sorted(CONTENTS)
    assert xe.engine_ready() is False


def test_engine_partial_when_some_files(fake_engine):
    _write_fake_engine(fake_engine, names={"config.json", "vocab.json"})
    status = xe.engine_status()
    assert status["state"] == "partial"
    assert "model.pth" in status["missing"]
    assert "config.json" not in status["missing"]


def test_engine_ok_when_all_files(fake_engine):
    _write_fake_engine(fake_engine)
    assert xe.engine_ready() is True
    assert xe.engine_status()["state"] == "ok"
    assert xe.engine_status(deep=True)["state"] == "ok"


def test_engine_detects_size_mismatch(fake_engine):
    _write_fake_engine(fake_engine)
    with open(os.path.join(fake_engine, "model.pth"), "ab") as f:
        f.write(b"extra")
    status = xe.engine_status()
    assert "model.pth" in status["missing"]
    assert xe.engine_ready() is False


def test_engine_detects_sha256_corruption_in_deep_mode(fake_engine):
    _write_fake_engine(fake_engine)
    path = os.path.join(fake_engine, "model.pth")
    with open(path, "r+b") as f:
        f.write(b"X" * len(CONTENTS["model.pth"]))  # размер тот же, байты другие
    assert xe.engine_status()["state"] == "ok"  # быстрая проверка не хеширует
    deep = xe.engine_status(deep=True)
    assert deep["state"] == "partial"
    assert deep["missing"] == ["model.pth"]


def test_engine_rejects_config_that_is_not_xtts(fake_engine, tmp_path):
    _write_fake_engine(fake_engine)
    path = os.path.join(fake_engine, "config.json")
    with open(path, "wb") as f:
        f.write(json.dumps({"model": "tacotron"}).encode("utf-8"))  # чужой конфиг
    deep = xe.engine_status(deep=True)
    assert "config.json" in deep["missing"]


# ── Скачивание (фейковая сеть) ─────────────────────────────────────────────────


class _FakeRawResponse:
    def __init__(self, data: bytes, offset: int = 0, on_read=None):
        self._data = data
        self._pos = offset
        self.status = 206 if offset else 200
        self._on_read = on_read

    def read(self, n: int = -1) -> bytes:
        if self._pos >= len(self._data):
            return b""
        if self._on_read:
            self._on_read()
        step = n if (n and n > 0) else len(self._data)
        chunk = self._data[self._pos : self._pos + step]
        self._pos += len(chunk)
        return chunk

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


def _url_mapping(base_urls):
    mapping = {}
    for base in base_urls:
        for name, data in CONTENTS.items():
            mapping[base + name] = data
    return mapping


@pytest.fixture
def fake_net(monkeypatch):
    """Подменяет _open_url фейковой сетью; возвращает (calls, state)."""
    calls = []
    state = {"mapping": None, "on_read": None, "offsets": []}

    def fake_open(url, offset=0, timeout=30):
        calls.append((url, offset))
        state["offsets"].append(offset)
        mapping = state["mapping"]
        if mapping is None or url not in mapping:
            raise urllib.error.URLError(f"unknown url: {url}")
        return _FakeRawResponse(mapping[url], offset, on_read=state["on_read"])

    monkeypatch.setattr(xe, "_open_url", fake_open)
    monkeypatch.setattr(xe, "_RETRY_BACKOFF_SEC", 0)
    return calls, state


def test_download_engine_installs_all_files(fake_engine, fake_net, monkeypatch):
    calls, state = fake_net
    monkeypatch.setattr(xe, "ENGINE_BASE_URLS", ("https://fake-primary/", "https://fake-fallback/"))
    state["mapping"] = _url_mapping(xe.ENGINE_BASE_URLS)

    events = []
    result = xe.download_engine(progress_cb=events.append)

    assert result["ok"] is True, result
    assert xe.engine_ready() is True
    assert sorted(os.listdir(fake_engine)) == sorted(CONTENTS)
    # нет .part остатков
    assert not any(n.endswith(".part") for n in os.listdir(fake_engine))
    # прогресс шёл по всем файлам и завершился stage=verify
    assert any(e.get("stage") == "verify" for e in events)


def test_download_engine_skips_valid_files(fake_engine, fake_net):
    calls, state = fake_net
    _write_fake_engine(fake_engine)
    state["mapping"] = {}  # сеть не должна дёргаться

    result = xe.download_engine()
    assert result["ok"] is True
    assert calls == []


def test_download_engine_falls_back_to_second_source(fake_engine, fake_net, monkeypatch):
    calls, state = fake_net
    bases = ("https://fake-primary/", "https://fake-fallback/")
    monkeypatch.setattr(xe, "ENGINE_BASE_URLS", bases)
    # первичный источник отдаёт искажённые байты model.pth, fallback — верные
    mapping = _url_mapping(bases)
    mapping[bases[0] + "model.pth"] = b"EVIL-BYTES-SAME-LEN!" + b"X" * (
        len(CONTENTS["model.pth"]) - len(b"EVIL-BYTES-SAME-LEN!")
    )
    state["mapping"] = mapping

    result = xe.download_engine()
    assert result["ok"] is True, result
    # fallback был задействован
    assert any(url.startswith(bases[1]) for url, _ in calls)


def test_download_engine_fails_when_both_sources_corrupt(fake_engine, fake_net, monkeypatch):
    calls, state = fake_net
    bases = ("https://fake-primary/", "https://fake-fallback/")
    monkeypatch.setattr(xe, "ENGINE_BASE_URLS", bases)
    mapping = _url_mapping(bases)
    evil = b"EVIL-BYTES-SAME-LEN!" + b"X" * (
        len(CONTENTS["model.pth"]) - len(b"EVIL-BYTES-SAME-LEN!")
    )
    mapping[bases[0] + "model.pth"] = evil
    mapping[bases[1] + "model.pth"] = evil
    state["mapping"] = mapping

    result = xe.download_engine()
    assert result["ok"] is False
    assert "model.pth" in result["error"]
    # битый файл не установлен в models/xtts_v2
    assert not os.path.exists(os.path.join(fake_engine, "model.pth"))


def test_download_engine_cancel_keeps_partial_for_resume(fake_engine, fake_net, monkeypatch):
    calls, state = fake_net
    bases = ("https://fake-only/",)
    monkeypatch.setattr(xe, "ENGINE_BASE_URLS", bases)
    state["mapping"] = _url_mapping(bases)

    cancel_flag = {"cancelled": False}
    reads = {"n": 0}
    monkeypatch.setattr(xe, "_CHUNK_SIZE", 4)  # файл 17 байт — качается несколькими чанками

    def on_read():
        reads["n"] += 1
        if reads["n"] == 2:  # отменяем после второй порции model.pth
            cancel_flag["cancelled"] = True

    state["on_read"] = on_read
    result = xe.download_engine(cancelled_cb=cancel_flag)
    assert result["cancelled"] is True
    parts = [n for n in os.listdir(fake_engine) if n.endswith(".part")]
    assert "model.pth.part" in parts, "частичная закачка должна сохраниться для докачки"
    partial_size = os.path.getsize(os.path.join(fake_engine, "model.pth.part"))
    assert 0 < partial_size < len(CONTENTS["model.pth"])

    # Второй запуск: докачка продолжается с сохранённого оффсета (Range)
    state["on_read"] = None
    cancel_flag["cancelled"] = False
    result2 = xe.download_engine(cancelled_cb=cancel_flag)
    assert result2["ok"] is True, result2
    assert any(offset > 0 for offset in state["offsets"]), "ожидалась докачка с Range"


# ── Diagnostics: движок не участвует в блокирующем восстановлении ───────────────


def test_get_broken_critical_ignores_engine():
    from engine.env_core.diagnostics import get_broken_critical

    results = {"xtts_engine": "engine missing: model.pth", "torch": "boom"}
    assert get_broken_critical(results) == ["torch"]

    # и движок сам по себе не считается поломкой для pre-GUI восстановления
    assert get_broken_critical({"xtts_engine": "engine missing: model.pth"}) == []


# ── i18n: ключи движка есть в обоих языках ─────────────────────────────────────


def test_engine_i18n_keys_present():
    from i18n import LANGUAGES

    keys = [
        "status_engine_missing",
        "engine_offer_title",
        "engine_offer_headline",
        "engine_offer_msg",
        "engine_offer_download",
        "engine_offer_later",
        "engine_dl_title",
        "engine_dl_overall",
        "engine_dl_done_msg",
        "engine_missing_hint",
    ]
    for lang in ("ru", "en"):
        for key in keys:
            assert key in LANGUAGES[lang], f"{lang}: {key}"


# ── Фоновая предзагрузка: при отсутствии движка — предложение, не падение ─────

try:
    import tkinter  # noqa: F401

    _TK_OK = True
except Exception:
    _TK_OK = False

try:
    import pygame  # noqa: F401

    _PYGAME_OK = True
except Exception:
    _PYGAME_OK = False


@pytest.mark.skipif(not (_TK_OK and _PYGAME_OK), reason="нужны tkinter и pygame")
def test_preload_offers_engine_download_when_missing(monkeypatch):
    import engine.gui.generation as gen

    monkeypatch.setattr("engine.xtts_engine.engine_ready", lambda: False)
    gen._engine_offer_active = False

    seen = {}
    monkeypatch.setattr(gen, "set_status", lambda s: seen.setdefault("status", s))
    monkeypatch.setattr(gen, "set_stage", lambda s: None)
    monkeypatch.setattr(gen, "_request_engine_offer", lambda: seen.setdefault("offer", True))

    def _boom():
        raise AssertionError("get_tts не должен вызываться без движка")

    import sys
    import types

    fake_tts_runner = types.ModuleType("engine.tts_runner")
    fake_tts_runner.get_tts = _boom
    monkeypatch.setitem(sys.modules, "engine.tts_runner", fake_tts_runner)

    gen._preload_model()
    assert seen.get("offer") is True
    assert seen.get("status")  # статус «движок отсутствует» показан
    assert gen.model_ready is False


@pytest.mark.skipif(not (_TK_OK and _PYGAME_OK), reason="нужны tkinter и pygame")
def test_preload_loads_model_when_engine_ready(monkeypatch):
    import sys
    import types

    import engine.gui.generation as gen

    monkeypatch.setattr("engine.xtts_engine.engine_ready", lambda: True)
    monkeypatch.setattr(gen, "set_status", lambda s: None)
    monkeypatch.setattr(gen, "set_stage", lambda s: None)

    fake_tts_runner = types.ModuleType("engine.tts_runner")
    fake_tts_runner.get_tts = lambda: object()
    monkeypatch.setitem(sys.modules, "engine.tts_runner", fake_tts_runner)

    gen._preload_model()
    assert gen.model_ready is True
