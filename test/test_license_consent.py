"""GUI/startup regression tests for issue #4, without a display server."""

from __future__ import annotations

import ast
import json
import os
import sys
import traceback
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import i18n
from engine import coqui_consent as consent
from engine.gui import license_consent as dialog

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolated_consent(tmp_path, monkeypatch):
    monkeypatch.setattr(consent, "JSON_DIR", str(tmp_path / "json"))
    monkeypatch.delenv("COQUI_TOS_AGREED", raising=False)
    previous_language = i18n.get_language()
    i18n.set_language("ru")
    yield
    i18n.set_language(previous_language)


@pytest.fixture
def fake(monkeypatch):
    tk = types.ModuleType("tkinter")
    tk.TclError = type("TclError", (Exception,), {})
    root = MagicMock(name="root")
    win = MagicMock(name="license_window")
    win.winfo_screenwidth.return_value = 1920
    win.winfo_screenheight.return_value = 1080
    win.winfo_width.return_value = 620
    win.winfo_height.return_value = 430
    tk.Tk = MagicMock(return_value=root)
    tk.Toplevel = MagicMock(return_value=win)
    tk.Frame = MagicMock()
    buttons = []
    labels = []

    def make_button(_parent, **kwargs):
        button = MagicMock()
        button.options = kwargs
        buttons.append(button)
        return button

    def make_label(_parent, **kwargs):
        label = MagicMock()
        label.options = kwargs
        labels.append(label)
        return label

    tk.Button = MagicMock(side_effect=make_button)
    tk.Label = MagicMock(side_effect=make_label)
    messagebox = MagicMock()
    tk.messagebox = messagebox
    webbrowser = MagicMock()
    action = {"callback": None}
    root.wait_window.side_effect = lambda _window: (
        action["callback"]() if action["callback"] else None
    )
    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setitem(sys.modules, "tkinter.messagebox", messagebox)
    monkeypatch.setitem(sys.modules, "webbrowser", webbrowser)
    return types.SimpleNamespace(
        tk=tk,
        root=root,
        win=win,
        buttons=buttons,
        labels=labels,
        messagebox=messagebox,
        webbrowser=webbrowser,
        action=action,
    )


def _click(fake, key):
    text = i18n.t(key)
    button = next(button for button in fake.buttons if button.options["text"] == text)
    button.options["command"]()


def test_accept_saves_before_reporting_success(fake):
    fake.action["callback"] = lambda: _click(fake, "cpml_accept")
    assert dialog.confirm_coqui_tos(source="startup-dialog") is True
    record = json.loads(Path(consent._cpml_consent_path()).read_text(encoding="utf-8"))
    assert record["agreed"] is True
    assert record["source"] == "startup-dialog"
    assert os.environ["COQUI_TOS_AGREED"] == "1"
    fake.win.destroy.assert_called()
    fake.root.destroy.assert_called_once()


@pytest.mark.parametrize("key", ["cpml_cancel", "WM_DELETE_WINDOW"])
def test_cancel_and_window_close_do_not_accept(fake, key):
    if key == "WM_DELETE_WINDOW":
        fake.action["callback"] = lambda: fake.win.protocol.call_args[0][1]()
    else:
        fake.action["callback"] = lambda: _click(fake, key)
    assert dialog.confirm_coqui_tos() is False
    assert not Path(consent._cpml_consent_path()).exists()
    assert "COQUI_TOS_AGREED" not in os.environ


def test_existing_consent_skips_startup_dialog_but_can_be_reviewed(fake):
    consent.set_coqui_tos_agreed("first-run")
    assert dialog.confirm_coqui_tos() is True
    fake.tk.Tk.assert_not_called()

    fake.action["callback"] = lambda: _click(fake, "cpml_accept")
    assert dialog.confirm_coqui_tos(source="settings-dialog", review=True) is True
    fake.tk.Toplevel.assert_called_once()
    record = json.loads(Path(consent._cpml_consent_path()).read_text(encoding="utf-8"))
    assert record["source"] == "settings-dialog"


def test_settings_parent_is_reused_and_not_destroyed(fake):
    parent = MagicMock()
    parent.wait_window.side_effect = lambda _window: _click(fake, "cpml_accept")
    assert dialog.confirm_coqui_tos(parent=parent, review=True) is True
    fake.tk.Tk.assert_not_called()
    fake.tk.Toplevel.assert_called_once_with(parent)
    fake.win.transient.assert_called_once_with(parent)
    parent.destroy.assert_not_called()


def test_startup_dialog_is_not_hidden_behind_a_withdrawn_transient_root(fake):
    fake.action["callback"] = lambda: _click(fake, "cpml_cancel")
    assert dialog.confirm_coqui_tos() is False
    fake.root.withdraw.assert_called_once()
    fake.win.transient.assert_not_called()
    fake.win.wait_visibility.assert_called_once()
    fake.root.destroy.assert_called_once()


def test_toplevel_construction_failure_still_cleans_up_owned_root(fake):
    fake.tk.Toplevel.side_effect = RuntimeError("cannot create window")
    with pytest.raises(RuntimeError, match="cannot create window"):
        dialog.confirm_coqui_tos()
    fake.root.destroy.assert_called_once()
    assert "COQUI_TOS_AGREED" not in os.environ


def test_save_failure_is_visible_and_never_returns_success(fake, monkeypatch):
    monkeypatch.setattr(
        dialog, "set_coqui_tos_agreed", MagicMock(side_effect=OSError("access denied"))
    )
    fake.action["callback"] = lambda: _click(fake, "cpml_accept")
    assert dialog.confirm_coqui_tos() is False
    fake.messagebox.showerror.assert_called_once()
    assert "access denied" in fake.messagebox.showerror.call_args[0][1]
    assert "COQUI_TOS_AGREED" not in os.environ
    assert not Path(consent._cpml_consent_path()).exists()


def test_license_link_opens_the_full_cpml(fake):
    def open_link_then_cancel():
        link = next(label for label in fake.labels if label.options["text"] == consent.CPML_URL)
        link.bind.assert_called_once()
        assert link.bind.call_args[0][0] == "<Button-1>"
        link.bind.call_args[0][1]()
        _click(fake, "cpml_cancel")

    fake.action["callback"] = open_link_then_cancel
    assert dialog.confirm_coqui_tos() is False
    fake.webbrowser.open.assert_called_once_with(consent.CPML_URL)


def test_dialog_uses_selected_interface_language(fake):
    i18n.set_language("en")
    fake.action["callback"] = lambda: _click(fake, "cpml_accept")
    assert dialog.confirm_coqui_tos() is True
    assert any(
        label.options.get("text") == i18n.LANGUAGES["en"]["cpml_body"] for label in fake.labels
    )
    fake.win.title.assert_called_once_with(i18n.LANGUAGES["en"]["cpml_dialog_title"])


def _load_startup_guard(confirm, monkeypatch):
    """Execute only the startup guard, not gui.py's lock/splash/mainloop imports."""
    tree = ast.parse((ROOT / "gui.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_ensure_coqui_tos_agreed_before_startup"
    )
    module = types.ModuleType("engine.gui.license_consent")
    module.confirm_coqui_tos = confirm
    log = MagicMock()
    namespace = {"sys": sys, "traceback": traceback, "_log_startup_error": log}
    import engine.gui as gui_package

    monkeypatch.setitem(sys.modules, "engine.gui.license_consent", module)
    monkeypatch.setattr(gui_package, "license_consent", module, raising=False)
    exec(compile(ast.Module(body=[function], type_ignores=[]), "gui.py", "exec"), namespace)
    return namespace[function.name], log


def test_startup_guard_does_not_skip_when_tts_imports_are_broken(monkeypatch):
    confirm = MagicMock(return_value=True)
    guard, _log = _load_startup_guard(confirm, monkeypatch)
    guard()
    confirm.assert_called_once_with(source="startup-dialog")


def test_startup_guard_stops_on_decline(monkeypatch):
    guard, _log = _load_startup_guard(MagicMock(return_value=False), monkeypatch)
    with pytest.raises(SystemExit) as exit_info:
        guard()
    assert exit_info.value.code == 0


def test_startup_guard_stops_and_logs_when_dialog_cannot_be_shown(monkeypatch):
    guard, log = _load_startup_guard(MagicMock(side_effect=RuntimeError("no display")), monkeypatch)
    with pytest.raises(SystemExit) as exit_info:
        guard()
    assert exit_info.value.code == 1
    log.assert_called_once()
    assert "no display" in log.call_args[0][0]


def test_license_preflight_runs_before_dependency_recovery():
    tree = ast.parse((ROOT / "gui.py").read_text(encoding="utf-8"))
    calls = [
        node.value.func.id
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    ]
    assert calls.index("_ensure_coqui_tos_agreed_before_startup") < calls.index(
        "_ensure_dependencies_before_startup"
    )
