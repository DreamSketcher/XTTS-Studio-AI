"""Regression tests for issue #4: explicit, durable CPML consent."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from engine import coqui_consent as consent

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_consent(tmp_path, monkeypatch):
    monkeypatch.setattr(consent, "JSON_DIR", str(tmp_path / "json"))
    monkeypatch.delenv("COQUI_TOS_AGREED", raising=False)


def test_missing_consent_is_actionable_and_does_not_auto_accept():
    assert consent.is_coqui_tos_agreed() is False
    with pytest.raises(consent.CoquiTosNotAgreedError) as error:
        consent.ensure_coqui_tos_agreed()
    assert "Settings" in str(error.value)
    assert consent.CPML_URL in str(error.value)
    assert "COQUI_TOS_AGREED=1" in str(error.value)
    assert "COQUI_TOS_AGREED" not in os.environ
    assert not Path(consent._cpml_consent_path()).exists()


@pytest.mark.parametrize(
    "record",
    [None, [], {}, {"agreed": False}, {"agreed": "false"}, {"agreed": "true"}, {"agreed": 1}],
)
def test_invalid_or_unconfirmed_records_do_not_count_as_consent(record):
    destination = Path(consent._cpml_consent_path())
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(record), encoding="utf-8")
    assert consent.is_coqui_tos_agreed() is False
    with pytest.raises(consent.CoquiTosNotAgreedError):
        consent.ensure_coqui_tos_agreed()


def test_corrupt_json_requires_confirmation():
    destination = Path(consent._cpml_consent_path())
    destination.parent.mkdir(parents=True)
    destination.write_text("{broken", encoding="utf-8")
    assert consent.is_coqui_tos_agreed() is False


def test_explicit_confirmation_survives_a_new_process_environment():
    consent.set_coqui_tos_agreed("settings-dialog")
    record = json.loads(Path(consent._cpml_consent_path()).read_text(encoding="utf-8"))
    assert record["agreed"] is True
    assert record["source"] == "settings-dialog"
    assert isinstance(record["confirmed_at"], int)
    assert os.environ["COQUI_TOS_AGREED"] == "1"

    # A restart does not inherit the previous process environment, but the
    # saved user decision must still authorize the next model load.
    del os.environ["COQUI_TOS_AGREED"]
    assert consent.is_coqui_tos_agreed() is True
    consent.ensure_coqui_tos_agreed()
    assert os.environ["COQUI_TOS_AGREED"] == "1"
    assert sorted(p.name for p in Path(consent._cpml_consent_path()).parent.iterdir()) == [
        "cpml_consent.json"
    ]


def test_user_provided_environment_opt_in_is_honoured_without_persisting():
    os.environ["COQUI_TOS_AGREED"] = "1"
    assert consent.is_coqui_tos_agreed() is True
    consent.ensure_coqui_tos_agreed()
    assert os.environ["COQUI_TOS_AGREED"] == "1"
    assert not Path(consent._cpml_consent_path()).exists()


@pytest.mark.parametrize("value", ["", "0", "false", "true", "yes", "2"])
def test_other_environment_values_are_not_acceptance(value):
    os.environ["COQUI_TOS_AGREED"] = value
    assert consent.is_coqui_tos_agreed() is False
    with pytest.raises(consent.CoquiTosNotAgreedError):
        consent.ensure_coqui_tos_agreed()
    assert os.environ["COQUI_TOS_AGREED"] == value


def test_failed_write_does_not_claim_success_or_change_environment(monkeypatch):
    def denied(*_args, **_kwargs):
        raise OSError("read-only directory")

    monkeypatch.setattr(consent, "atomic_write_json", denied)
    with pytest.raises(OSError, match="read-only directory"):
        consent.set_coqui_tos_agreed()
    assert "COQUI_TOS_AGREED" not in os.environ
    assert consent.is_coqui_tos_agreed() is False


def test_failed_replacement_preserves_previous_record_and_reports_failure(monkeypatch):
    consent.set_coqui_tos_agreed("first-confirmation")
    original = Path(consent._cpml_consent_path()).read_bytes()
    monkeypatch.delenv("COQUI_TOS_AGREED")

    def denied(*_args, **_kwargs):
        raise OSError("file locked")

    monkeypatch.setattr(consent, "atomic_write_json", denied)
    with pytest.raises(OSError, match="file locked"):
        consent.set_coqui_tos_agreed("second-confirmation")
    assert Path(consent._cpml_consent_path()).read_bytes() == original
    assert "COQUI_TOS_AGREED" not in os.environ


def test_consent_works_in_a_fresh_process_with_broken_tts_dependencies(tmp_path):
    script = """
import importlib.abc
import json
import os
import sys

class BlockHeavyImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {
            'num2words', 'pydub', 'torch', 'TTS', 'pygame', 'customtkinter', 'tkinter'
        }:
            raise ImportError(fullname + ' is intentionally unavailable')
        return None

sys.meta_path.insert(0, BlockHeavyImports())
os.environ.pop('COQUI_TOS_AGREED', None)
from engine import coqui_consent
coqui_consent.JSON_DIR = sys.argv[1]
assert 'COQUI_TOS_AGREED' not in os.environ
assert not coqui_consent.is_coqui_tos_agreed()
coqui_consent.set_coqui_tos_agreed('startup-dialog')
coqui_consent.ensure_coqui_tos_agreed()
with open(coqui_consent._cpml_consent_path(), encoding='utf-8') as handle:
    assert json.load(handle)['agreed'] is True
assert os.environ['COQUI_TOS_AGREED'] == '1'
"""
    env = os.environ.copy()
    env.pop("COQUI_TOS_AGREED", None)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "json")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_tts_facade_keeps_the_same_consent_api():
    # Avoid importing the optional ML stack here; the facade must re-export the
    # lightweight implementation rather than maintaining a second consent store.
    import ast

    tree = ast.parse((ROOT / "engine" / "tts" / "__init__.py").read_text(encoding="utf-8"))
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "engine.coqui_consent"
    ]
    assert len(imports) == 1
    assert {alias.name for alias in imports[0].names} == {
        "CoquiTosNotAgreedError",
        "ensure_coqui_tos_agreed",
        "is_coqui_tos_agreed",
        "set_coqui_tos_agreed",
    }


def test_user_consent_is_not_release_payload():
    from tools.rebuild_release_files import included

    assert included("json/cpml_consent.json") is False
    assert "json/cpml_consent.json" in (ROOT / ".gitignore").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "json" / "version.json").read_text(encoding="utf-8"))
    assert "json/cpml_consent.json" not in manifest["files"]
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "json/cpml_consent.json"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert tracked.returncode != 0, "Do not distribute a developer's pre-accepted license"
