"""Тесты engine/cpml_consent.py — явное согласие с Coqui Public Model License.

Модуль не тянет torch/TTS (только stdlib), поэтому эти тесты работают в
минимальной среде. Регрессия для issue #4: CoquiTosNotAgreedError при
генерации, несмотря на COQUI_TOS_AGREED=1 и перезапуски.
"""
import json
import os

import pytest

from engine.cpml_consent import (
    CoquiTosNotAgreedError,
    cpml_consent_path,
    ensure_coqui_tos_agreed,
    is_coqui_tos_agreed,
    set_coqui_tos_agreed,
)


@pytest.fixture
def consent_env(tmp_path, monkeypatch):
    """Изолированное файл согласия в tmp_path + чистая переменная окружения."""
    consent_file = tmp_path / "json" / "cpml_consent.json"
    monkeypatch.setenv("XTTS_CPML_CONSENT_PATH", str(consent_file))
    monkeypatch.delenv("COQUI_TOS_AGREED", raising=False)
    yield consent_file


def test_consent_path_respects_override(consent_env):
    assert cpml_consent_path() == str(consent_env)


def test_default_not_agreed_and_ensure_raises(consent_env):
    assert not is_coqui_tos_agreed()
    with pytest.raises(CoquiTosNotAgreedError) as excinfo:
        ensure_coqui_tos_agreed()
    msg = str(excinfo.value)
    assert "coqui.ai/cpml" in msg
    assert "COQUI_TOS_AGREED" in msg


def test_set_then_ensure_passes_and_persists(consent_env):
    set_coqui_tos_agreed("unit-test")
    assert is_coqui_tos_agreed()
    ensure_coqui_tos_agreed()  # не должно бросать
    record = json.loads(consent_env.read_text(encoding="utf-8"))
    assert record["agreed"] is True
    assert record["source"] == "unit-test"
    assert os.environ.get("COQUI_TOS_AGREED") == "1"


def test_env_var_counts_as_explicit_consent(consent_env, monkeypatch):
    # То, что пользователь пробовал в issue #4: env var + рестарт.
    monkeypatch.setenv("COQUI_TOS_AGREED", "1")
    assert is_coqui_tos_agreed()
    ensure_coqui_tos_agreed()
    # Согласие из env фиксируется в файле (best-effort) с прозрачным источником
    record = json.loads(consent_env.read_text(encoding="utf-8"))
    assert record["agreed"] is True
    assert record["source"] == "env:COQUI_TOS_AGREED"


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "2"])
def test_env_var_false_like_values_do_not_consent(consent_env, monkeypatch, value):
    monkeypatch.setenv("COQUI_TOS_AGREED", value)
    assert not is_coqui_tos_agreed()
    with pytest.raises(CoquiTosNotAgreedError):
        ensure_coqui_tos_agreed()


def test_corrupt_consent_file_is_treated_as_not_agreed(consent_env):
    consent_env.parent.mkdir(parents=True, exist_ok=True)
    consent_env.write_text("{ not json", encoding="utf-8")
    assert not is_coqui_tos_agreed()
    with pytest.raises(CoquiTosNotAgreedError):
        ensure_coqui_tos_agreed()
    # ...но повторное подтверждение чинит файл
    set_coqui_tos_agreed("unit-test-repair")
    assert is_coqui_tos_agreed()


def test_agreed_false_in_file_is_not_consent(consent_env):
    consent_env.parent.mkdir(parents=True, exist_ok=True)
    consent_env.write_text(json.dumps({"agreed": False}), encoding="utf-8")
    assert not is_coqui_tos_agreed()
    with pytest.raises(CoquiTosNotAgreedError):
        ensure_coqui_tos_agreed()


def test_set_is_atomic_via_tmp_file(consent_env):
    set_coqui_tos_agreed("unit-test-atomic")
    assert not os.path.exists(str(consent_env) + ".tmp")
    record = json.loads(consent_env.read_text(encoding="utf-8"))
    assert record["agreed"] is True
