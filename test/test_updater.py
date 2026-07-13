# -*- coding: utf-8 -*-
"""
test_updater.py — тесты для engine/updater.py.

Ничего не ходит в реальную сеть: _urlopen_with_retry подменяется мок-объектом,
который отдаёт заранее заданное содержимое файлов. Все пути (BASE_DIR,
STAGING_DIR, BACKUP_DIR, ROLLBACK_MARKER, LOCAL_VERSION_PATH) подменяются на
временную папку pytest (tmp_path), так что тесты никогда не трогают реальный
проект.

Запуск:
    pip install pytest --break-system-packages
    pytest test_updater.py -v
"""
import hashlib
import io
import json
import os

import pytest

from engine import updater


class FakeResponse(io.BytesIO):
    """Имитирует объект, который возвращает urllib.request.urlopen()."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def isolated_project(tmp_path, monkeypatch):
    """Подменяет все пути updater.py на временную директорию."""
    base = tmp_path / "project"
    base.mkdir()
    monkeypatch.setattr(updater, "BASE_DIR", str(base))
    monkeypatch.setattr(updater, "LOCAL_VERSION_PATH", str(base / "version.json"))
    monkeypatch.setattr(updater, "STAGING_DIR", str(base / "_update_staging"))
    monkeypatch.setattr(updater, "BACKUP_DIR", str(base / "_update_backup"))
    monkeypatch.setattr(updater, "ROLLBACK_MARKER", str(base / "_update_pending.json"))

    # исходный version.json — старая версия
    (base / "version.json").write_text(
        json.dumps({"version": "1.0.0", "files": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    return base


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mock_urlopen(contents_by_relpath: dict, remote_version_info: dict, monkeypatch):
    """
    contents_by_relpath: {"a.txt": b"..."} — что отдавать для download-запросов.
    remote_version_info: dict — что отдавать на запрос VERSION_URL.
    """

    def fake(url, timeout=15, max_retries=updater.MAX_RETRIES):
        if url == updater.VERSION_URL:
            return FakeResponse(json.dumps(remote_version_info, ensure_ascii=False).encode("utf-8"))
        for relpath, content in contents_by_relpath.items():
            if url.endswith(relpath.replace(" ", "%20")) or url.endswith(relpath):
                return FakeResponse(content)
        raise RuntimeError(f"Неожиданный URL в тесте: {url}")

    monkeypatch.setattr(updater, "_urlopen_with_retry", fake)


# ───────────────────────── check_update / min_app_version ─────────────────────────


def test_check_update_detects_available_version(isolated_project, monkeypatch):
    remote_info = {"version": "1.0.1", "files": ["a.txt"], "sha256": {}, "changelog": "fix"}
    _mock_urlopen({}, remote_info, monkeypatch)

    result = updater.check_update()

    assert result["available"] is True
    assert result["local"] == "1.0.0"
    assert result["remote"] == "1.0.1"
    assert result["needs_manual_reinstall"] is False


def test_check_update_flags_manual_reinstall_when_too_old(isolated_project, monkeypatch):
    remote_info = {"version": "2.0.0", "min_app_version": "1.5.0", "files": []}
    _mock_urlopen({}, remote_info, monkeypatch)

    result = updater.check_update()

    assert result["needs_manual_reinstall"] is True


# ───────────────────────── apply_update: успешный сценарий ─────────────────────────


def test_apply_update_success_writes_files_and_marker(isolated_project, monkeypatch):
    content_a = b"hello world"
    files = ["a.txt"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {"version": "1.0.1", "files": files, "sha256": sha256_map}
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    ok = updater.apply_update(files, sha256_map=sha256_map)

    assert ok is True
    assert (isolated_project / "a.txt").read_bytes() == content_a
    assert not os.path.isdir(updater.STAGING_DIR), "staging должен быть очищен после применения"
    assert os.path.exists(
        updater.ROLLBACK_MARKER
    ), "маркер должен появиться сразу после apply_update"
    assert os.path.isdir(
        updater.BACKUP_DIR
    ), "backup должен существовать до confirm_update_success()"

    local_version = json.loads((isolated_project / "version.json").read_text(encoding="utf-8"))
    assert local_version["version"] == "1.0.1"


# ───────────────────────── apply_update: битый SHA256 ─────────────────────────


def test_apply_update_aborts_on_bad_checksum_and_touches_nothing(isolated_project, monkeypatch):
    # исходный рабочий файл — должен остаться нетронутым
    (isolated_project / "a.txt").write_bytes(b"OLD CONTENT")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    wrong_sha256_map = {"a.txt": "0" * 64}  # заведомо неверный хэш
    remote_info = {"version": "1.0.1", "files": files, "sha256": wrong_sha256_map}
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    ok = updater.apply_update(
        files,
        sha256_map=wrong_sha256_map,
        sha_mismatch_retries=0,  # без повторов — тест не должен ждать backoff
        sha_mismatch_delay=0,  # без реальных time.sleep между попытками
    )

    assert ok is False
    assert (
        isolated_project / "a.txt"
    ).read_bytes() == b"OLD CONTENT", "рабочий файл не должен был измениться"
    assert not os.path.isdir(updater.STAGING_DIR)
    assert not os.path.isdir(
        updater.BACKUP_DIR
    ), "backup не должен создаваться при провале проверки"
    assert not os.path.exists(updater.ROLLBACK_MARKER)

    local_version = json.loads((isolated_project / "version.json").read_text(encoding="utf-8"))
    assert local_version["version"] == "1.0.0", "version.json не должен обновляться при неудаче"


# ───────────────────────── rollback ─────────────────────────


def test_rollback_restores_previous_file_content(isolated_project, monkeypatch):
    (isolated_project / "a.txt").write_bytes(b"OLD CONTENT")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {"version": "1.0.1", "files": files, "sha256": sha256_map}
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    assert updater.apply_update(files, sha256_map=sha256_map) is True
    assert (isolated_project / "a.txt").read_bytes() == b"NEW CONTENT"

    ok = updater.rollback_update()

    assert ok is True
    assert (isolated_project / "a.txt").read_bytes() == b"OLD CONTENT"
    assert not os.path.exists(updater.ROLLBACK_MARKER)
    assert not os.path.isdir(updater.BACKUP_DIR)

    local_version = json.loads((isolated_project / "version.json").read_text(encoding="utf-8"))
    assert local_version["version"] == "1.0.0", "версия должна откатиться на старую"


def test_confirm_update_success_clears_marker_and_backup(isolated_project, monkeypatch):
    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {"version": "1.0.1", "files": files, "sha256": sha256_map}
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    assert updater.apply_update(files, sha256_map=sha256_map) is True
    assert os.path.exists(updater.ROLLBACK_MARKER)

    updater.confirm_update_success()

    assert not os.path.exists(updater.ROLLBACK_MARKER)
    assert not os.path.isdir(updater.BACKUP_DIR)
    # файл, конечно, остаётся обновлённым
    assert (isolated_project / "a.txt").read_bytes() == content_a


# ───────────────────────── check_startup_health: сценарий двойного сбоя ─────────────────────────


def test_startup_health_rolls_back_after_second_unconfirmed_launch(isolated_project, monkeypatch):
    (isolated_project / "a.txt").write_bytes(b"OLD CONTENT")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {"version": "1.0.1", "files": files, "sha256": sha256_map}
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    assert updater.apply_update(files, sha256_map=sha256_map) is True
    assert (isolated_project / "a.txt").read_bytes() == b"NEW CONTENT"

    # Запуск №1 после обновления — приложение "падает" до confirm_update_success()
    status_1 = updater.check_startup_health()
    assert status_1 == "first_attempt"
    assert (
        isolated_project / "a.txt"
    ).read_bytes() == b"NEW CONTENT", "файлы ещё не должны откатываться"

    # Запуск №2 — снова не подтверждён (симулируем повторный сбой) → должен произойти откат
    status_2 = updater.check_startup_health()
    assert status_2 == "rolled_back"
    assert (
        isolated_project / "a.txt"
    ).read_bytes() == b"OLD CONTENT", "после второго сбоя файлы должны откатиться"
    assert not os.path.exists(updater.ROLLBACK_MARKER)


def test_startup_health_ok_when_no_pending_update(isolated_project):
    assert updater.check_startup_health() == "ok"


# ───────────────────────── повторные неудачные загрузки ─────────────────────────


def test_apply_update_fails_cleanly_when_file_missing_from_server(isolated_project, monkeypatch):
    files = ["a.txt", "missing.txt"]
    content_a = b"NEW CONTENT"
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {"version": "1.0.1", "files": files, "sha256": sha256_map}
    # "missing.txt" намеренно отсутствует в contents_by_relpath → download упадёт с RuntimeError
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    ok = updater.apply_update(files, sha256_map=sha256_map)

    assert ok is False
    assert not os.path.isdir(updater.STAGING_DIR)
    assert not os.path.exists(updater.ROLLBACK_MARKER)
