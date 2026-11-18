"""Тесты проверки доступности моделей одним ключом и авто-подбора модели.

Сеть подменена; файлы настроек/кэша изолированы в tmp_path.
"""

import io
import json
import time
import urllib.error

import pytest

import engine.gpt_client as gpt_client
from engine.gpt_client import (
    ModelGoneError,
    GroqRateLimitError,
    _call_with_chain,
)


@pytest.fixture(autouse=True)
def clean_settings(tmp_path, monkeypatch):
    settings_file = tmp_path / "gpt_settings.json"
    monkeypatch.setattr(gpt_client, "_SETTINGS_PATH", str(settings_file))
    monkeypatch.setattr(gpt_client, "_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("XTTS_TEST_SECRET_STORE", "1")
    # Ключ «по умолчанию» есть у всех провайдеров — иначе probe отклоняется до запросов.
    monkeypatch.setattr(gpt_client, "get_api_key", lambda pid=None: "test-key")
    return settings_file


def http_error(code: int, message: str) -> urllib.error.HTTPError:
    body = json.dumps({"error": {"message": message}}).encode("utf-8")
    return urllib.error.HTTPError(
        url="https://api.example.com", code=code, msg="err", hdrs=None, fp=io.BytesIO(body)
    )


# ── ModelGoneError mapping ─────────────────────────────────────────────────────


class TestModelGoneMapping:
    @pytest.mark.parametrize(
        "message",
        [
            "The model `x` does not exist or you do not have access to it.",
            "anthropic/claude-3.5-sonnet is no longer available on OpenRouter",
            "model_not_found",
            "no endpoints found for this model",
            "unknown model",
            "model has been decommissioned",
        ],
    )
    def test_404_always_model_gone(self, monkeypatch, message):
        monkeypatch.setattr(gpt_client, "get_api_key", lambda pid: "k")
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *a, **kw: (_ for _ in ()).throw(http_error(404, message)),
        )
        with pytest.raises(ModelGoneError):
            gpt_client._call_api(
                [{"role": "user", "content": "ping"}],
                model="m",
                max_tokens=1,
                provider="groq",
            )

    def test_400_with_model_missing_pattern(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_api_key", lambda pid: "k")
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *a, **kw: (_ for _ in ()).throw(http_error(400, "model_not_found: m")),
        )
        with pytest.raises(ModelGoneError):
            gpt_client._call_api(
                [{"role": "user", "content": "ping"}],
                model="m",
                max_tokens=1,
                provider="groq",
            )

    def test_400_unrelated_stays_runtime(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_api_key", lambda pid: "k")
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda *a, **kw: (_ for _ in ()).throw(http_error(400, "bad request parameter")),
        )
        with pytest.raises(RuntimeError):
            gpt_client._call_api(
                [{"role": "user", "content": "ping"}],
                model="m",
                max_tokens=1,
                provider="groq",
            )


# ── probe_models_availability ───────────────────────────────────────────────────


def _fake_call_api_factory(outcomes: dict, calls: list):
    def fake(messages, model=None, max_tokens=0, provider=None):
        calls.append((provider, model, max_tokens))
        outcome = outcomes.get(model, "ok")
        if outcome == "ok":
            return "pong"
        if outcome == "gone":
            raise ModelGoneError(f"{provider} error 404: {model} does not exist")
        if outcome == "rate_limited":
            raise GroqRateLimitError("429")
        if outcome == "network_error":
            raise gpt_client.GroqNetworkError("connection refused")
        if outcome == "invalid_key":
            raise RuntimeError("401 Unauthorized: invalid api key")
        raise RuntimeError("boom")

    return fake


class TestProbeModelsAvailability:
    def test_mixed_outcomes(self, monkeypatch):
        outcomes = {
            "good": "ok",
            "dead": "gone",
            "limited": "rate_limited",
            "noauth": "invalid_key",
        }
        calls = []
        monkeypatch.setattr(gpt_client, "_call_api", _fake_call_api_factory(outcomes, calls))
        result = gpt_client.probe_models_availability(
            "groq", models=["good", "dead", "limited", "noauth"], max_tokens=1
        )
        assert result["ok"] == 1
        assert result["total"] == 4
        assert result["results"] == outcomes
        # max_tokens=1 — дешёвый пинг
        assert all(c[2] == 1 for c in calls)
        health = gpt_client.get_model_health("groq")
        assert health["good"]["state"] == "ok"
        assert health["dead"]["state"] == "gone"
        assert health["limited"]["state"] == "rate_limited"
        assert health["noauth"]["state"] == "invalid_key"
        assert all(v["ts"] for v in health.values())
        # поставщик жив хоть на одной модели
        assert gpt_client.get_provider_health("groq")["state"] == "ok"

    def test_all_invalid_key_marks_provider(self, monkeypatch):
        monkeypatch.setattr(
            gpt_client,
            "_call_api",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("401 invalid api key")),
        )
        result = gpt_client.probe_models_availability("groq", models=["a", "b", "c"])
        assert result["ok"] == 0
        assert gpt_client.get_provider_health("groq")["state"] == "invalid_key"

    def test_all_network_error_marks_provider(self, monkeypatch):
        monkeypatch.setattr(
            gpt_client,
            "_call_api",
            lambda *a, **kw: (_ for _ in ()).throw(gpt_client.GroqNetworkError("net down")),
        )
        result = gpt_client.probe_models_availability("groq", models=["a", "b"])
        assert result["ok"] == 0
        assert gpt_client.get_provider_health("groq")["state"] == "network_error"

    def test_gone_model_recorded_once_and_skipped_in_chain(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_call_api", _fake_call_api_factory({"ghost": "gone"}, []))
        gpt_client.probe_models_availability("groq", models=["ghost"])
        assert "ghost" in gpt_client.get_gone_models("groq")

    def test_no_key_short_circuits_without_requests(self, monkeypatch):
        calls = []
        monkeypatch.setattr(gpt_client, "get_api_key", lambda pid=None: "")
        monkeypatch.setattr(gpt_client, "_call_api", _fake_call_api_factory({}, calls))
        result = gpt_client.probe_models_availability("groq", models=["a", "b", "c"])
        assert calls == []
        assert result["error"]
        assert result["total"] == 0

    def test_rich_counts_and_rate_limited_not_gone(self, monkeypatch):
        outcomes = {"a": "ok", "b": "gone", "c": "rate_limited"}
        monkeypatch.setattr(gpt_client, "_call_api", _fake_call_api_factory(outcomes, []))
        result = gpt_client.probe_models_availability("groq", models=["a", "b", "c"])
        assert result["ok"] == 1
        assert result["gone"] == 1
        assert result["rate_limited"] == 1
        assert result["total"] == 3
        assert result["error"] is None
        # rate_limited не делает модель «снятой» — она останется в цепочке
        assert gpt_client.get_gone_models("groq") == {"b"}

    def test_aborts_when_key_is_rejected(self, monkeypatch):
        calls = []

        def reject(messages, model=None, max_tokens=0, provider=None):
            # Немного «сети»: имитируем задержку запроса, чтобы отмена
            # ещё не запущенных проверок была наблюдаемой.
            time.sleep(0.02)
            calls.append(model)
            raise RuntimeError("401 Unauthorized: invalid api key")

        monkeypatch.setattr(gpt_client, "_call_api", reject)
        many = [f"m{i}" for i in range(60)]
        result = gpt_client.probe_models_availability("groq", models=many, workers=2)
        assert result["error"]
        assert len(calls) < len(many)
        assert gpt_client.get_provider_health("groq")["state"] == "invalid_key"

    def test_empty_list_is_noop(self, monkeypatch):
        calls = []
        monkeypatch.setattr(gpt_client, "_call_api", _fake_call_api_factory({}, calls))
        result = gpt_client.probe_models_availability("groq", models=[])
        assert result["ok"] == 0
        assert result["total"] == 0
        assert result["results"] == {}
        assert result["error"] is None
        assert calls == []

    def test_models_arg_deduped_and_sanitized(self, monkeypatch):
        calls = []
        monkeypatch.setattr(gpt_client, "_call_api", _fake_call_api_factory({}, calls))
        gpt_client.probe_models_availability("groq", models=["a", "a", "", "  ", "b"])
        assert [c[1] for c in calls] == ["a", "b"]

    def test_probe_uses_live_cache_by_default(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr(gpt_client, "_call_api", _fake_call_api_factory({}, calls))
        cache_dir = tmp_path / "json"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "provider_cache.json").write_text(
            json.dumps(
                {
                    "models": {
                        "groq": {
                            "models": ["cached-1", "cached-2"],
                            "ts": 1.0,
                            "url": "u",
                            "ok": True,
                            "error": None,
                        }
                    },
                    "health": {},
                }
            ),
            encoding="utf-8",
        )
        result = gpt_client.probe_models_availability("groq")
        assert result["total"] == 2


# ── _models_to_try / chain ─────────────────────────────────────────────────────


class TestModelsToTry:
    def test_live_models_appended_after_configured(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "primary")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "fallback")
        monkeypatch.setattr(
            gpt_client,
            "get_models_cache_meta",
            lambda pid: {
                "models": ["primary", "live-a", "live-b"],
                "ts": 1.0,
                "url": "u",
                "ok": True,
                "error": None,
            },
        )
        assert gpt_client._models_to_try("groq") == ["primary", "fallback", "live-a", "live-b"]

    def test_primary_fallback_deduped(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "same")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "same")
        monkeypatch.setattr(
            gpt_client,
            "get_models_cache_meta",
            lambda pid: {
                "models": [],
                "ts": None,
                "url": None,
                "ok": False,
                "error": None,
            },
        )
        assert gpt_client._models_to_try("groq") == ["same"]

    def test_live_list_capped_at_five(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "primary")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "primary")
        monkeypatch.setattr(
            gpt_client,
            "get_models_cache_meta",
            lambda pid: {
                "models": [f"live-{i}" for i in range(10)],
                "ts": 1.0,
                "url": "u",
                "ok": True,
                "error": None,
            },
        )
        models = gpt_client._models_to_try("groq")
        assert models == ["primary"] + [f"live-{i}" for i in range(5)]

    def test_gone_models_skipped(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "dead-primary")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "dead-primary")
        monkeypatch.setattr(
            gpt_client,
            "get_models_cache_meta",
            lambda pid: {
                "models": ["dead-primary", "alive"],
                "ts": 1.0,
                "url": "u",
                "ok": True,
                "error": None,
            },
        )
        gpt_client.record_model_state("groq", "dead-primary", "gone", "404")
        assert gpt_client._models_to_try("groq") == ["alive"]

    def test_all_gone_still_returns_primary(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "dead")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "dead")
        monkeypatch.setattr(
            gpt_client,
            "get_models_cache_meta",
            lambda pid: {"models": ["dead"], "ts": 1.0, "url": "u", "ok": True, "error": None},
        )
        gpt_client.record_model_state("groq", "dead", "gone", "404")
        assert gpt_client._models_to_try("groq") == ["dead"]

    def test_chain_auto_picks_live_model_after_gone(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: ["groq"])
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "dead-primary")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "dead-primary")
        monkeypatch.setattr(
            gpt_client,
            "get_models_cache_meta",
            lambda pid: {
                "models": ["dead-primary", "live-good"],
                "ts": 1.0,
                "url": "u",
                "ok": True,
                "error": None,
            },
        )
        calls = []

        def fake_api(messages, model=None, max_tokens=0, provider=None):
            calls.append(model)
            if model == "dead-primary":
                raise ModelGoneError("404 model removed")
            return "auto_ok"

        monkeypatch.setattr(gpt_client, "_call_api", fake_api)
        result = _call_with_chain([{"role": "user", "content": "hi"}])
        assert result == "auto_ok"
        assert calls == ["dead-primary", "live-good"]
        # модель записана как снятая — больше не будет вызываться
        assert "dead-primary" in gpt_client.get_gone_models("groq")

    def test_chain_skips_gone_on_next_run(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: ["groq"])
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "dead-primary")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "dead-primary")
        monkeypatch.setattr(
            gpt_client,
            "get_models_cache_meta",
            lambda pid: {
                "models": ["dead-primary", "live-good"],
                "ts": 1.0,
                "url": "u",
                "ok": True,
                "error": None,
            },
        )
        gpt_client.record_model_state("groq", "dead-primary", "gone", "404")
        calls = []
        monkeypatch.setattr(
            gpt_client,
            "_call_api",
            lambda messages, model=None, max_tokens=0, provider=None: calls.append(model) or "ok",
        )
        assert _call_with_chain([{"role": "user", "content": "hi"}]) == "ok"
        assert calls == ["live-good"]


class TestKeyValidationUsesLiveModels:
    def test_gone_default_model_falls_through_to_live_one(self, monkeypatch):
        monkeypatch.setattr(
            gpt_client,
            "get_provider_info",
            lambda pid: {
                "label": "Groq",
                "default_model": "dead-model",
            },
        )
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "dead-model")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "dead-model")
        monkeypatch.setattr(
            gpt_client,
            "get_models_cache_meta",
            lambda pid: {
                "models": ["dead-model", "live-model"],
                "ts": 1.0,
                "url": "u",
                "ok": True,
                "error": None,
            },
        )
        monkeypatch.setattr(gpt_client, "set_api_key", lambda *a, **kw: None)
        monkeypatch.setattr(gpt_client, "get_api_key", lambda pid=None: "old")

        def fake(messages, model=None, max_tokens=0, provider=None):
            if model == "dead-model":
                raise ModelGoneError("404: The model `dead-model` does not exist")
            return "pong"

        monkeypatch.setattr(gpt_client, "_call_api", fake)
        ok, msg = gpt_client.validate_key("new-key", "groq")
        assert ok is True
        assert "live-model" in msg
        assert "dead-model" in gpt_client.get_gone_models("groq")

    def test_all_models_gone_suggests_refresh(self, monkeypatch):
        monkeypatch.setattr(
            gpt_client, "get_provider_info", lambda pid: {"label": "Groq", "default_model": "dead"}
        )
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "dead")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "dead")
        monkeypatch.setattr(
            gpt_client,
            "get_models_cache_meta",
            lambda pid: {"models": ["dead"], "ts": 1.0, "url": "u", "ok": True, "error": None},
        )
        monkeypatch.setattr(gpt_client, "set_api_key", lambda *a, **kw: None)
        monkeypatch.setattr(gpt_client, "get_api_key", lambda pid=None: "old")
        monkeypatch.setattr(
            gpt_client,
            "_call_api",
            lambda *a, **kw: (_ for _ in ()).throw(ModelGoneError("404 no longer available")),
        )
        ok, msg = gpt_client.validate_key("new-key", "groq")
        assert ok is False
        assert "Обновить модели" in msg
        assert gpt_client.get_provider_health("groq")["state"] == "ok"


# ── cache lifecycle ─────────────────────────────────────────────────────────────


class TestModelHealthLifecycle:
    def test_clear_provider_cache_clears_model_health(self):
        gpt_client.record_model_state("groq", "m1", "gone", "404")
        assert gpt_client.get_model_health("groq")["m1"]["state"] == "gone"
        gpt_client.clear_provider_cache("groq")
        assert gpt_client.get_model_health("groq") == {}

    def test_record_sanitizes_unknown_state(self):
        gpt_client.record_model_state("groq", "m1", "weird-state", "x")
        assert gpt_client.get_model_health("groq")["m1"]["state"] == "error"


# ── примечания каталога/меток не содержат гео-отметок ──────────────────────────


class TestNoGeoNotes:
    BANNED = ("РФ", "VPN", "рубл", "Russia", "rubles", "российск", "Russian")

    @pytest.mark.parametrize("lang", ["ru", "en"])
    def test_provider_labels_and_notes_geo_free(self, lang):
        from i18n import LANGUAGES

        data = LANGUAGES[lang]
        keys = [
            k for k in data if k.startswith(("prov_", "cat_")) and ("notes" in k or "label" in k)
        ]
        assert keys, "expected provider label/notes keys in i18n"
        offenders = {k: data[k] for k in keys if any(b in str(data[k]) for b in self.BANNED)}
        assert not offenders, f"гео-примечания остались в {lang}: {offenders}"
