import sys
import types
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine.gpt_client as gpt_client
from engine.gpt_client import (
    AIUnavailable,
    GroqNetworkError,
    GroqRateLimitError,
    _build_provider_chain,
    _call_with_chain,
    get_chain_diagnostics,
    _provider_available,
)


@pytest.fixture(autouse=True)
def clean_gpt_settings(tmp_path, monkeypatch):
    """Изолируем gpt_settings.json на tmp_path, чтобы реальные файлы не трогать."""
    settings_file = tmp_path / "gpt_settings.json"
    # Патчим константы модуля
    monkeypatch.setattr(gpt_client, "_SETTINGS_PATH", str(settings_file))
    monkeypatch.setattr(gpt_client, "_BASE_DIR", str(tmp_path))
    # Очищаем кэш импорта local_llm_client если был
    # Ничего не делаем
    yield settings_file


class TestBuildProviderChain:
    def test_active_first_if_available(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_provider", lambda: "groq")
        monkeypatch.setattr(gpt_client, "_provider_available", lambda pid: pid == "groq")
        monkeypatch.setattr(gpt_client, "get_hidden_providers", lambda: set())
        monkeypatch.setattr(gpt_client, "list_custom_providers", lambda: [])

        chain = _build_provider_chain()
        assert chain == ["groq"]

    def test_active_not_available_excluded(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_provider", lambda: "groq")

        # groq без ключа, openrouter с ключом
        def avail(pid):
            return pid == "openrouter"

        monkeypatch.setattr(gpt_client, "_provider_available", avail)
        monkeypatch.setattr(gpt_client, "get_hidden_providers", lambda: set())
        monkeypatch.setattr(gpt_client, "list_custom_providers", lambda: [])

        chain = _build_provider_chain()
        assert "groq" not in chain
        assert "openrouter" in chain

    def test_hidden_providers_skipped(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_provider", lambda: "groq")
        monkeypatch.setattr(gpt_client, "_provider_available", lambda pid: True)
        monkeypatch.setattr(gpt_client, "get_hidden_providers", lambda: {"proxy"})
        monkeypatch.setattr(gpt_client, "list_custom_providers", lambda: [])

        chain = _build_provider_chain()
        assert "proxy" not in chain
        assert "groq" in chain
        # groq активный должен быть первым
        assert chain[0] == "groq"

    def test_custom_providers_after_builtin(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_provider", lambda: "groq")
        monkeypatch.setattr(gpt_client, "_provider_available", lambda pid: True)
        monkeypatch.setattr(gpt_client, "get_hidden_providers", lambda: set())
        monkeypatch.setattr(gpt_client, "list_custom_providers", lambda: [{"id": "my_custom"}])

        chain = _build_provider_chain()
        # порядок: active, остальные встроенные, затем кастомные
        assert chain[0] == "groq"
        assert chain[-1] == "my_custom"
        # все PROVIDERS кроме groq должны быть между
        builtin_ids = set(gpt_client.PROVIDERS.keys()) - {"groq"}
        assert builtin_ids.issubset(set(chain))

    def test_active_custom_provider(self, monkeypatch):
        # активный — кастомный
        monkeypatch.setattr(gpt_client, "get_provider", lambda: "my_custom")

        def avail(pid):
            return pid in ("my_custom", "groq")

        monkeypatch.setattr(gpt_client, "_provider_available", avail)
        monkeypatch.setattr(gpt_client, "get_hidden_providers", lambda: set())
        monkeypatch.setattr(gpt_client, "list_custom_providers", lambda: [{"id": "my_custom"}])

        chain = _build_provider_chain()
        assert chain[0] == "my_custom"


class TestProviderAvailable:
    def test_builtin_with_key(self, monkeypatch):
        monkeypatch.setattr(
            gpt_client, "get_api_key", lambda pid=None: "sk-123" if pid == "groq" else ""
        )
        assert _provider_available("groq") is True
        assert _provider_available("proxy") is False

    def test_local_with_model(self, monkeypatch):
        # мок local_llm_client
        fake_local = types.ModuleType("engine.local_llm_client")
        fake_local.get_active_model = lambda: "model.gguf"
        monkeypatch.setitem(sys.modules, "engine.local_llm_client", fake_local)
        # также нужно для from engine import local_llm_client внутри функции
        fake_engine = types.ModuleType("engine")
        fake_engine.local_llm_client = fake_local
        monkeypatch.setitem(sys.modules, "engine", fake_engine)
        assert _provider_available("local") is True

    def test_local_without_model(self, monkeypatch):
        fake_local = types.ModuleType("engine.local_llm_client")
        fake_local.get_active_model = lambda: None
        monkeypatch.setitem(sys.modules, "engine.local_llm_client", fake_local)
        fake_engine = types.ModuleType("engine")
        fake_engine.local_llm_client = fake_local
        monkeypatch.setitem(sys.modules, "engine", fake_engine)
        assert _provider_available("local") is False


class TestCallWithChain:
    def test_empty_chain_raises_ai_unavailable(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: [])
        with pytest.raises(AIUnavailable, match="Нет ни одного"):
            _call_with_chain([{"role": "user", "content": "hi"}])

    def test_success_on_first_provider(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: ["groq"])
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "model1")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "model1")
        monkeypatch.setattr(gpt_client, "_call_api", lambda *a, **kw: "OK")

        result = _call_with_chain([{"role": "user", "content": "hi"}])
        assert result == "OK"

    def test_fallback_to_second_model_on_rate_limit(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: ["groq"])
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "primary")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "fallback")

        calls = []

        def fake_call_api(messages, model=None, max_tokens=0, provider=None):
            calls.append(model)
            if model == "primary":
                raise GroqRateLimitError("429")
            return "fallback_ok"

        monkeypatch.setattr(gpt_client, "_call_api", fake_call_api)

        result = _call_with_chain([{"role": "user", "content": "hi"}])
        assert result == "fallback_ok"
        assert calls == ["primary", "fallback"]

    def test_fallback_to_next_provider_on_network_error(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: ["groq", "proxy"])
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: f"{pid}_model")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: f"{pid}_model")

        def fake_api(messages, model=None, max_tokens=0, provider=None):
            if provider == "groq":
                raise GroqNetworkError("no internet")
            return f"ok from {provider}"

        monkeypatch.setattr(gpt_client, "_call_api", fake_api)

        result = _call_with_chain([{"role": "user", "content": "hi"}])
        assert result == "ok from proxy"

    def test_all_network_failures_raises_no_internet(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: ["groq", "proxy"])
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "m")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "m")
        monkeypatch.setattr(
            gpt_client, "_call_api", lambda *a, **kw: (_ for _ in ()).throw(GroqNetworkError("net"))
        )

        with pytest.raises(AIUnavailable, match="Нет подключения"):
            _call_with_chain([{"role": "user", "content": "hi"}])

    def test_all_providers_fail_raises_all_unavailable(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: ["groq", "proxy"])
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "m1")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "m2")

        def fake_api(*a, **kw):
            raise GroqRateLimitError("limit")

        monkeypatch.setattr(gpt_client, "_call_api", fake_api)

        with pytest.raises(AIUnavailable, match="Все провайдеры"):
            _call_with_chain([{"role": "user", "content": "hi"}])

    def test_generic_exception_continues_chain(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: ["groq", "openrouter"])
        monkeypatch.setattr(gpt_client, "get_model", lambda pid: "m")
        monkeypatch.setattr(gpt_client, "get_fallback_model", lambda pid: "m")

        def fake_api(messages, model=None, max_tokens=0, provider=None):
            if provider == "groq":
                raise RuntimeError("unexpected")
            return "ok openrouter"

        monkeypatch.setattr(gpt_client, "_call_api", fake_api)

        result = _call_with_chain([{"role": "user", "content": "hi"}])
        assert result == "ok openrouter"


class TestChainDiagnostics:
    def test_diagnostics_structure(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_provider", lambda: "groq")
        monkeypatch.setattr(gpt_client, "get_hidden_providers", lambda: set())
        monkeypatch.setattr(
            gpt_client, "get_api_key", lambda pid=None: "key" if pid == "groq" else ""
        )
        monkeypatch.setattr(gpt_client, "get_model", lambda pid=None: f"{pid}_model")
        monkeypatch.setattr(
            gpt_client, "list_custom_providers", lambda: [{"id": "custom1", "label": "Custom"}]
        )
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: ["groq"])

        diag = get_chain_diagnostics()
        assert "active" in diag
        assert "chain_order" in diag
        assert "providers" in diag
        assert diag["active"] == "groq"
        # должен содержать все встроенные + кастомный
        ids = {p["id"] for p in diag["providers"]}
        assert "groq" in ids
        assert "custom1" in ids

    def test_hidden_marked(self, monkeypatch):
        monkeypatch.setattr(gpt_client, "get_provider", lambda: "groq")
        monkeypatch.setattr(gpt_client, "get_hidden_providers", lambda: {"openrouter"})
        monkeypatch.setattr(gpt_client, "get_api_key", lambda pid=None: "k")
        monkeypatch.setattr(gpt_client, "get_model", lambda pid=None: "m")
        monkeypatch.setattr(gpt_client, "list_custom_providers", lambda: [])
        monkeypatch.setattr(gpt_client, "_build_provider_chain", lambda: ["groq"])

        diag = get_chain_diagnostics()
        openrouter_entry = next(p for p in diag["providers"] if p["id"] == "openrouter")
        assert openrouter_entry["status"] == "hidden"
