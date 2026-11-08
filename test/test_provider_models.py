"""Тесты живой загрузки моделей, кэша и health-трекинга провайдеров.

Сеть подменена фейковым urlopen; реальные файлы настроек изолированы в tmp_path.
"""

import json
import urllib.error
import io

import pytest

import engine.gpt_client as gpt_client


@pytest.fixture(autouse=True)
def clean_settings(tmp_path, monkeypatch):
    settings_file = tmp_path / "gpt_settings.json"
    monkeypatch.setattr(gpt_client, "_SETTINGS_PATH", str(settings_file))
    monkeypatch.setattr(gpt_client, "_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("XTTS_TEST_SECRET_STORE", "1")
    return settings_file


class FakeResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def make_urlopen(payload=None, error: Exception | None = None, calls: list | None = None):
    """Фейковый urlopen: возвращает payload либо бросает error. Копия адресов в calls."""

    def fake(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if calls is not None:
            calls.append(url)
        if error is not None:
            raise error
        return FakeResponse(payload or {})

    return fake


# ── catalogue seeds ─────────────────────────────────────────────────────────────


class TestCatalogue:
    def test_ids_unique_and_wellformed(self):
        ids = [e["id"] for e in gpt_client.PROVIDER_CATALOGUE]
        assert len(ids) == len(set(ids))
        for pid in ids:
            assert pid == pid.strip().lower()
            assert all(ch.isalnum() or ch in "_-" for ch in pid)

    def test_every_entry_usable(self):
        for e in gpt_client.PROVIDER_CATALOGUE:
            assert e.get("label"), e["id"]
            assert e.get("url"), e["id"]
            gpt_client._validate_api_url(e["url"])  # не должно бросать
            models_url = e.get("models_url")
            if models_url:
                gpt_client._validate_api_url(models_url)
            # всегда есть хотя бы встроенный seed или endpoint для live-загрузки
            assert e.get("models") or models_url, e["id"]
            assert e.get("notes"), e["id"]

    def test_flagship_providers_present(self):
        ids = {e["id"] for e in gpt_client.PROVIDER_CATALOGUE}
        expected = {
            "openrouter",
            "together",
            "mistral",
            "deepinfra",
            "openai",
            "anthropic",
            "gemini",
            "deepseek",
            "xai",
            "cerebras",
            "sambanova",
            "fireworks",
            "novita",
            "hyperbolic",
            "nvidia",
            "chutes",
            "ollama",
            "lmstudio",
            "vsegpt",
            "aitunnel",
            "proxyapi",
        }
        missing = expected - ids
        assert not missing, f"В каталоге нет: {sorted(missing)}"

    def test_notes_i18n_resolvable(self):
        """Заметки должны быть осмысленными строками, а не ключами i18n."""
        for e in gpt_client.PROVIDER_CATALOGUE:
            assert not str(e["notes"]).startswith("cat_"), e["id"]


# ── derive_models_url ───────────────────────────────────────────────────────────


class TestDeriveModelsUrl:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://api.openai.com/v1/chat/completions", "https://api.openai.com/v1/models"),
            ("https://api.x.ai/v1/responses", "https://api.x.ai/v1/models"),
            ("https://api.mistral.ai/v1/completions", "https://api.mistral.ai/v1/models"),
            ("https://api.openai.com/v1", "https://api.openai.com/v1/models"),
            ("https://api.openai.com/v1/", "https://api.openai.com/v1/models"),
            ("https://api.openai.com/v1/models", "https://api.openai.com/v1/models"),
            ("http://localhost:11434/v1", "http://localhost:11434/v1/models"),
        ],
    )
    def test_derive(self, url, expected):
        assert gpt_client.derive_models_url(url) == expected

    def test_derive_empty(self):
        assert gpt_client.derive_models_url("") is None
        assert gpt_client.derive_models_url(None) is None


# ── payload parsing ─────────────────────────────────────────────────────────────


class TestParseModelsPayload:
    def test_openai_format_filters_non_chat(self):
        data = {
            "data": [
                {"id": "gpt-4o-mini"},
                {"id": "text-embedding-3-small", "type": "embedding"},
                {"id": "dall-e-3", "type": "image"},
                {"id": "whisper-1"},
            ]
        }
        ids = gpt_client._parse_models_payload(data)
        assert "gpt-4o-mini" in ids
        assert "text-embedding-3-small" not in ids
        assert "dall-e-3" not in ids

    def test_openai_format_sorted_and_deduped(self):
        data = {"data": [{"id": "b"}, {"id": "a"}, {"id": "a"}]}
        assert gpt_client._parse_models_payload(data) == ["a", "b"]

    def test_gemini_format(self):
        data = {
            "models": [
                {
                    "name": "models/gemini-2.0-flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/text-embedding-004",
                    "supportedGenerationMethods": ["embedContent"],
                },
            ]
        }
        assert gpt_client._parse_models_payload(data) == ["gemini-2.0-flash"]

    def test_garbage(self):
        assert gpt_client._parse_models_payload([]) == []
        assert gpt_client._parse_models_payload({"data": "nope"}) == []
        assert gpt_client._parse_models_payload("junk") == []


# ── fetch / refresh / cache ─────────────────────────────────────────────────────


class TestRefreshProviderModels:
    def test_refresh_writes_cache_and_health(self, monkeypatch):
        payload = {"data": [{"id": "m1"}, {"id": "m2"}, {"id": "embed-x", "type": "embedding"}]}
        monkeypatch.setattr("urllib.request.urlopen", make_urlopen(payload=payload))
        models, err = gpt_client.refresh_provider_models("groq", force=True)
        assert err is None
        assert models == ["m1", "m2"]
        meta = gpt_client.get_models_cache_meta("groq")
        assert meta["ok"] is True
        assert meta["models"] == ["m1", "m2"]
        assert meta["ts"] is not None
        health = gpt_client.get_provider_health("groq")
        assert health["state"] == "ok"

    def test_ttl_skips_network(self, monkeypatch):
        payload = {"data": [{"id": "m1"}]}
        calls = []
        monkeypatch.setattr("urllib.request.urlopen", make_urlopen(payload=payload, calls=calls))
        gpt_client.refresh_provider_models("groq", force=True)
        assert len(calls) == 1
        # Повторный вызов без force не должен ходить в сеть
        models, err = gpt_client.refresh_provider_models("groq")
        assert models == ["m1"]
        assert err is None
        assert len(calls) == 1

    def test_error_keeps_stale_cache_and_marks_health(self, monkeypatch):
        payload = {"data": [{"id": "stable-model"}]}
        monkeypatch.setattr("urllib.request.urlopen", make_urlopen(payload=payload))
        gpt_client.refresh_provider_models("groq", force=True)
        # Теперь сеть падает
        err_http = urllib.error.HTTPError(
            url="https://x", code=401, msg="unauthorized", hdrs=None, fp=io.BytesIO(b"")
        )
        monkeypatch.setattr("urllib.request.urlopen", make_urlopen(error=err_http))
        models, err = gpt_client.refresh_provider_models("groq", force=True)
        assert err is not None
        assert models == ["stable-model"]  # устаревший кэш сохранён
        meta = gpt_client.get_models_cache_meta("groq")
        assert meta["ok"] is False
        assert gpt_client.get_provider_health("groq")["state"] == "invalid_key"

    def test_network_failure_marks_health(self, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            make_urlopen(error=urllib.error.URLError("connection refused")),
        )
        models, err = gpt_client.refresh_provider_models("groq", force=True)
        assert err is not None
        # Кэша нет → возвращается встроенный seed (builtin), не падаем
        assert isinstance(models, list)
        assert gpt_client.get_provider_health("groq")["state"] == "network_error"

    def test_local_provider_without_url_returns_seed_without_network(self, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "urllib.request.urlopen",
            make_urlopen(error=RuntimeError("network must not be called"), calls=calls),
        )
        models, err = gpt_client.refresh_provider_models("local", force=True)
        assert calls == []
        assert err is None
        assert isinstance(models, list)

    def test_custom_provider_models_url_used(self, clean_settings, monkeypatch):
        payload = {"data": [{"id": "custom-live-model"}]}
        calls = []
        monkeypatch.setattr("urllib.request.urlopen", make_urlopen(payload=payload, calls=calls))
        gpt_client.add_custom_provider(
            "myop",
            "My OP",
            "https://api.example.com/v1/chat/completions",
            ["seed-model"],
            "seed-model",
            models_url="https://api.example.com/v1/models",
        )
        models, err = gpt_client.refresh_provider_models("myop", force=True)
        assert err is None
        assert models == ["custom-live-model"]
        assert calls == ["https://api.example.com/v1/models"]
        info = gpt_client.get_provider_info("myop")
        assert info["models_url"] == "https://api.example.com/v1/models"

    def test_custom_provider_models_url_derived(self, clean_settings, monkeypatch):
        payload = {"data": [{"id": "derived-model"}]}
        calls = []
        monkeypatch.setattr("urllib.request.urlopen", make_urlopen(payload=payload, calls=calls))
        gpt_client.add_custom_provider(
            "derived",
            "Derived",
            "https://api.example.com/v1/chat/completions",
            ["seed-model"],
            "seed-model",
        )
        models, err = gpt_client.refresh_provider_models("derived", force=True)
        assert err is None
        assert models == ["derived-model"]
        assert calls == ["https://api.example.com/v1/models"]

    def test_custom_provider_models_url_validated(self, clean_settings):
        with pytest.raises(ValueError):
            gpt_client.add_custom_provider(
                "badmu",
                "Bad MU",
                "https://api.example.com/v1/chat/completions",
                ["m"],
                "m",
                models_url="http://example.com/v1/models",  # не loopback http
            )

    def test_update_custom_provider_models_url_and_cache_clear(self, clean_settings, monkeypatch):
        payload = {"data": [{"id": "live-x"}]}
        monkeypatch.setattr("urllib.request.urlopen", make_urlopen(payload=payload))
        gpt_client.add_custom_provider(
            "editmu", "Edit MU", "https://api.a.com/v1/chat/completions", ["m"], "m"
        )
        gpt_client.refresh_provider_models("editmu", force=True)
        assert gpt_client.get_cached_models("editmu") == ["live-x"]
        gpt_client.update_custom_provider("editmu", url="https://api.b.com/v1/chat/completions")
        assert gpt_client.get_cached_models("editmu") == []
        assert gpt_client.get_provider_health("editmu")["state"] == "unchecked"

    def test_delete_custom_provider_clears_cache(self, clean_settings, monkeypatch):
        payload = {"data": [{"id": "gone"}]}
        monkeypatch.setattr("urllib.request.urlopen", make_urlopen(payload=payload))
        gpt_client.add_custom_provider(
            "gonebye", "Gone", "https://api.a.com/v1/chat/completions", ["m"], "m"
        )
        gpt_client.refresh_provider_models("gonebye", force=True)
        assert gpt_client.get_cached_models("gonebye") == ["gone"]
        gpt_client.delete_custom_provider("gonebye")
        assert gpt_client.get_cached_models("gonebye") == []


# ── validate_provider_models_url ────────────────────────────────────────────────


class TestValidateProviderModelsUrl:
    def test_ok(self, monkeypatch):
        payload = {"data": [{"id": "a"}, {"id": "b"}]}
        monkeypatch.setattr("urllib.request.urlopen", make_urlopen(payload=payload))
        ok, msg, models = gpt_client.validate_provider_models_url(
            "https://api.example.com/v1/models", "k"
        )
        assert ok is True
        assert models == ["a", "b"]

    def test_rejects_bad_url(self):
        ok, _msg, models = gpt_client.validate_provider_models_url(
            "http://example.com/v1/models", "k"
        )
        assert ok is False
        assert models == []

    def test_empty_url(self):
        ok, _msg, models = gpt_client.validate_provider_models_url("", "k")
        assert ok is False
        assert models == []


# ── health tracking ─────────────────────────────────────────────────────────────


class TestProviderHealth:
    def test_default_unchecked(self):
        assert gpt_client.get_provider_health("groq")["state"] == "unchecked"

    def test_record_and_validate_key_ok(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_call_api", lambda *a, **k: "pong")
        ok, _msg = gpt_client.validate_key("any-key", "groq")
        assert ok is True
        assert gpt_client.get_provider_health("groq")["state"] == "ok"

    def test_validate_key_rate_limited(self, monkeypatch):
        def boom(*a, **k):
            raise gpt_client.GroqRateLimitError("429")

        monkeypatch.setattr(gpt_client, "_call_api", boom)
        ok, _msg = gpt_client.validate_key("any-key", "groq")
        assert ok is False
        assert gpt_client.get_provider_health("groq")["state"] == "rate_limited"

    def test_validate_key_network(self, monkeypatch):
        def boom(*a, **k):
            raise gpt_client.GroqNetworkError("host unreachable")

        monkeypatch.setattr(gpt_client, "_call_api", boom)
        ok, _msg = gpt_client.validate_key("any-key", "groq")
        assert ok is False
        assert gpt_client.get_provider_health("groq")["state"] == "network_error"

    def test_validate_key_invalid_key(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("401 Unauthorized: invalid api key")

        monkeypatch.setattr(gpt_client, "_call_api", boom)
        ok, _msg = gpt_client.validate_key("any-key", "groq")
        assert ok is False
        assert gpt_client.get_provider_health("groq")["state"] == "invalid_key"

    def test_record_provider_state_sanitizes_unknown(self):
        gpt_client.record_provider_state("groq", "nonsense-state", "x")
        assert gpt_client.get_provider_health("groq")["state"] == "error"
