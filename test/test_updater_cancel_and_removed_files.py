# -*- coding: utf-8 -*-
"""
test_updater_cancel_and_removed_files.py — тесты для двух новых механизмов
в engine/updater.py:

  1. cancelled_flag — отмена обновления пользователем (кнопка "Отмена").
     Проверяем: отмена во время скачивания чистит staging и НЕ трогает
     рабочие файлы; отмена ПОСЛЕ прохождения проверки (когда уже начался
     backup+подмена) больше не действует — "точка невозврата".

  2. removed_files — устаревшие файлы, которых больше нет в новом
     манифесте (переименованные/перенесённые при рефакторинге).
     Проверяем: они бэкапятся, удаляются с диска после успешного
     обновления, и восстанавливаются при откате (rollback_update).

Ничего не ходит в реальную сеть — тот же подход, что и в test_updater.py:
_urlopen_with_retry подменяется мок-объектом, все пути указывают на
временную папку pytest (tmp_path).

Запуск:
    pytest test_updater_cancel_and_removed_files.py -v
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
    """Подменяет все пути updater.py на временную директорию (как в test_updater.py)."""
    base = tmp_path / "project"
    base.mkdir()
    monkeypatch.setattr(updater, "BASE_DIR", str(base))
    monkeypatch.setattr(updater, "LOCAL_VERSION_PATH", str(base / "version.json"))
    monkeypatch.setattr(updater, "STAGING_DIR", str(base / "_update_staging"))
    monkeypatch.setattr(updater, "BACKUP_DIR", str(base / "_update_backup"))
    monkeypatch.setattr(updater, "ROLLBACK_MARKER", str(base / "_update_pending.json"))

    (base / "version.json").write_text(
        json.dumps({"version": "1.0.0", "files": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    return base


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _mock_urlopen(contents_by_relpath: dict, remote_version_info: dict, monkeypatch):
    def fake(url, timeout=15, max_retries=updater.MAX_RETRIES):
        if url == updater.VERSION_URL:
            return FakeResponse(json.dumps(remote_version_info, ensure_ascii=False).encode("utf-8"))
        for relpath, content in contents_by_relpath.items():
            if url.endswith(relpath.replace(" ", "%20")) or url.endswith(relpath):
                return FakeResponse(content)
        raise RuntimeError(f"Неожиданный URL в тесте: {url}")

    monkeypatch.setattr(updater, "_urlopen_with_retry", fake)


# ───────────────────────── cancelled_flag: базовый формат ─────────────────────────


@pytest.mark.parametrize(
    "flag_before, flag_after, expected",
    [
        ({"cancelled": False}, None, False),
        ({"cancelled": True}, None, True),
        ([False], None, False),
        ([True], None, True),
        (None, None, False),
    ],
)
def test_is_cancelled_supports_dict_and_list_formats(flag_before, flag_after, expected):
    assert updater._is_cancelled(flag_before) is expected


# ───────────────────────── отмена во время скачивания ─────────────────────────


def test_apply_update_cancelled_before_any_file_touches_nothing(isolated_project, monkeypatch):
    (isolated_project / "a.txt").write_bytes(b"OLD CONTENT")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {"version": "1.0.1", "files": files, "sha256": sha256_map}
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    cancelled_flag = {"cancelled": True}  # уже отменено до старта
    ok = updater.apply_update(files, sha256_map=sha256_map, cancelled_flag=cancelled_flag)

    assert ok is False
    assert (isolated_project / "a.txt").read_bytes() == b"OLD CONTENT"
    assert not os.path.isdir(updater.STAGING_DIR), "staging должен быть удалён после отмены"
    assert not os.path.isdir(updater.BACKUP_DIR), "backup не должен создаваться при отмене"
    assert not os.path.exists(updater.ROLLBACK_MARKER)


def test_apply_update_cancelled_mid_download_between_files(isolated_project, monkeypatch):
    """Отмена срабатывает МЕЖДУ файлами: первый файл успевает скачаться
    в staging, но флаг отменяет обработку до второго — весь staging
    должен быть вычищен, а не оставлен наполовину."""
    (isolated_project / "a.txt").write_bytes(b"OLD A")
    (isolated_project / "b.txt").write_bytes(b"OLD B")

    content_a, content_b = b"NEW A", b"NEW B"
    files = ["a.txt", "b.txt"]
    sha256_map = {"a.txt": _sha256(content_a), "b.txt": _sha256(content_b)}
    remote_info = {"version": "1.0.1", "files": files, "sha256": sha256_map}
    _mock_urlopen({"a.txt": content_a, "b.txt": content_b}, remote_info, monkeypatch)

    cancelled_flag = {"cancelled": False}

    def progress_cb(i, total):
        if i == 1:
            cancelled_flag["cancelled"] = True  # отменяем сразу после первого файла

    ok = updater.apply_update(
        files,
        sha256_map=sha256_map,
        cancelled_flag=cancelled_flag,
        progress_callback=progress_cb,
    )

    assert ok is False
    assert (isolated_project / "a.txt").read_bytes() == b"OLD A"
    assert (isolated_project / "b.txt").read_bytes() == b"OLD B"
    assert not os.path.isdir(
        updater.STAGING_DIR
    ), "весь staging должен быть вычищен, включая уже скачанный a.txt"
    assert not os.path.isdir(updater.BACKUP_DIR)
    assert not os.path.exists(updater.ROLLBACK_MARKER)


def test_apply_update_cancelled_mid_chunk_download(isolated_project, monkeypatch):
    """Отмена должна прерывать чтение блоками ВНУТРИ одного файла, а не
    только между файлами — важно для крупных файлов."""
    files = ["big.bin"]
    big_content = b"X" * (65536 * 5)  # несколько блоков по 65536 байт
    sha256_map = {"big.bin": _sha256(big_content)}
    remote_info = {"version": "1.0.1", "files": files, "sha256": sha256_map}
    _mock_urlopen({"big.bin": big_content}, remote_info, monkeypatch)

    cancelled_flag = {"cancelled": False}
    call_count = {"n": 0}

    os.makedirs(updater.STAGING_DIR, exist_ok=True)

    original_read = FakeResponse.read

    def counting_read(self, n):
        call_count["n"] += 1
        if call_count["n"] == 2:
            cancelled_flag["cancelled"] = True  # отменяем после первого блока
        return original_read(self, n)

    monkeypatch.setattr(FakeResponse, "read", counting_read)

    with pytest.raises(InterruptedError):
        updater._download_to_staging(
            "big.bin", sha256_map["big.bin"], cancelled_flag=cancelled_flag
        )

    staged_path = os.path.join(updater.STAGING_DIR, "big.bin")
    assert not os.path.exists(staged_path)
    assert not os.path.exists(
        staged_path + ".part"
    ), "частично скачанный .part должен удаляться при отмене"


def test_cancellation_via_progress_callback_on_last_file_is_still_honored(
    isolated_project, monkeypatch
):
    """apply_update делает финальную проверку cancelled_flag ПОСЛЕ того как
    все файлы скачаны/проверены, но ДО начала backup+подмены — то есть
    отмена, выставленная даже в progress_callback последнего файла, всё
    ещё успевает остановить обновление. Рабочие файлы не должны меняться."""
    (isolated_project / "a.txt").write_bytes(b"OLD CONTENT")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {"version": "1.0.1", "files": files, "sha256": sha256_map}
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    cancelled_flag = {"cancelled": False}

    def progress_cb(i, total):
        cancelled_flag["cancelled"] = True

    ok = updater.apply_update(
        files,
        sha256_map=sha256_map,
        cancelled_flag=cancelled_flag,
        progress_callback=progress_cb,
    )

    assert ok is False, "финальная проверка перед backup должна была поймать отмену"
    assert (isolated_project / "a.txt").read_bytes() == b"OLD CONTENT"
    assert not os.path.isdir(updater.STAGING_DIR)
    assert not os.path.isdir(updater.BACKUP_DIR), "backup не должен был начаться"


def test_cancellation_ignored_once_backup_and_swap_have_actually_started(
    isolated_project, monkeypatch
):
    """Настоящая точка невозврата — это момент, когда _backup_current_files
    уже начал выполняться. Если флаг отмены выставляется КАК ПОБОЧНЫЙ ЭФФЕКТ
    самого шага подмены (т.е. уже после финальной проверки), апдейт должен
    доиграться до конца, а не оставить рабочие файлы в промежуточном
    состоянии."""
    (isolated_project / "a.txt").write_bytes(b"OLD CONTENT")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {"version": "1.0.1", "files": files, "sha256": sha256_map}
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    cancelled_flag = {"cancelled": False}
    original_move = updater._move_staged_to_live

    def move_and_cancel(files_arg):
        # Отмена "запаздывает" — пользователь нажал кнопку ровно в момент,
        # когда подмена файлов уже физически идёт.
        cancelled_flag["cancelled"] = True
        return original_move(files_arg)

    monkeypatch.setattr(updater, "_move_staged_to_live", move_and_cancel)

    ok = updater.apply_update(files, sha256_map=sha256_map, cancelled_flag=cancelled_flag)

    assert (
        ok is True
    ), "отмена, поступившая во время подмены файлов, не должна прерывать/портить обновление"
    assert (isolated_project / "a.txt").read_bytes() == content_a
    assert os.path.exists(
        updater.ROLLBACK_MARKER
    ), "обновление должно было завершиться нормально, с маркером отката"


# ───────────────────────── removed_files: удаление устаревших файлов ─────────────────────────


def test_apply_update_deletes_removed_files(isolated_project, monkeypatch):
    (isolated_project / "old_module.py").write_bytes(b"legacy code content")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    removed = ["old_module.py"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {
        "version": "1.0.1",
        "files": files,
        "sha256": sha256_map,
        "removed_files": removed,
    }
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    ok = updater.apply_update(files, sha256_map=sha256_map, removed_files=removed)

    assert ok is True
    assert not (isolated_project / "old_module.py").exists(), "устаревший файл должен быть удалён"
    assert (isolated_project / "a.txt").read_bytes() == content_a


def test_apply_update_removes_now_empty_directories(isolated_project, monkeypatch):
    nested = isolated_project / "engine" / "old_package"
    nested.mkdir(parents=True)
    (nested / "legacy.py").write_bytes(b"old module content")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    removed = ["engine/old_package/legacy.py"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {
        "version": "1.0.1",
        "files": files,
        "sha256": sha256_map,
        "removed_files": removed,
    }
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    ok = updater.apply_update(files, sha256_map=sha256_map, removed_files=removed)

    assert ok is True
    assert not nested.exists(), "опустевшая папка старого пакета должна быть удалена"


def test_apply_update_keeps_directory_if_other_files_remain(isolated_project, monkeypatch):
    """Если в папке остались другие файлы (не входящие в removed_files),
    папку удалять нельзя — только пустые."""
    nested = isolated_project / "engine" / "mixed_package"
    nested.mkdir(parents=True)
    (nested / "legacy.py").write_bytes(b"old module content")
    (nested / "still_used.py").write_bytes(b"still used content")

    content_a = b"NEW CONTENT"
    files = ["a.txt", "engine/mixed_package/still_used.py"]
    removed = ["engine/mixed_package/legacy.py"]
    sha256_map = {
        "a.txt": _sha256(content_a),
        "engine/mixed_package/still_used.py": _sha256(b"still used content"),
    }
    remote_info = {
        "version": "1.0.1",
        "files": files,
        "sha256": sha256_map,
        "removed_files": removed,
    }
    _mock_urlopen(
        {"a.txt": content_a, "engine/mixed_package/still_used.py": b"still used content"},
        remote_info,
        monkeypatch,
    )

    ok = updater.apply_update(files, sha256_map=sha256_map, removed_files=removed)

    assert ok is True
    assert nested.exists(), "папка не должна удаляться, пока в ней остались нужные файлы"
    assert not (nested / "legacy.py").exists()
    assert (nested / "still_used.py").exists()


def test_apply_update_bad_checksum_does_not_delete_removed_files(isolated_project, monkeypatch):
    """Если проверка SHA256 не прошла — весь апдейт отменяется, включая
    шаг удаления устаревших файлов. Иначе можно было бы потерять старый
    файл, даже когда новое обновление не применилось."""
    (isolated_project / "old_module.py").write_bytes(b"legacy code content")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    removed = ["old_module.py"]
    wrong_sha256_map = {"a.txt": "0" * 64}
    remote_info = {
        "version": "1.0.1",
        "files": files,
        "sha256": wrong_sha256_map,
        "removed_files": removed,
    }
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    ok = updater.apply_update(files, sha256_map=wrong_sha256_map, removed_files=removed)

    assert ok is False
    assert (
        isolated_project / "old_module.py"
    ).exists(), "устаревший файл НЕ должен удаляться при провале обновления"


# ───────────────────────── removed_files: откат восстанавливает удалённое ─────────────────────────


def test_rollback_restores_deleted_removed_file(isolated_project, monkeypatch):
    (isolated_project / "old_module.py").write_bytes(b"legacy code content")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    removed = ["old_module.py"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {
        "version": "1.0.1",
        "files": files,
        "sha256": sha256_map,
        "removed_files": removed,
    }
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    assert updater.apply_update(files, sha256_map=sha256_map, removed_files=removed) is True
    assert not (isolated_project / "old_module.py").exists()

    ok = updater.rollback_update()

    assert ok is True
    assert (
        isolated_project / "old_module.py"
    ).read_bytes() == b"legacy code content", (
        "откат должен вернуть удалённый устаревший файл обратно"
    )


def test_confirm_update_success_after_removed_files_clears_backup(isolated_project, monkeypatch):
    (isolated_project / "old_module.py").write_bytes(b"legacy code content")

    content_a = b"NEW CONTENT"
    files = ["a.txt"]
    removed = ["old_module.py"]
    sha256_map = {"a.txt": _sha256(content_a)}
    remote_info = {
        "version": "1.0.1",
        "files": files,
        "sha256": sha256_map,
        "removed_files": removed,
    }
    _mock_urlopen({"a.txt": content_a}, remote_info, monkeypatch)

    assert updater.apply_update(files, sha256_map=sha256_map, removed_files=removed) is True
    updater.confirm_update_success()

    assert not os.path.exists(updater.ROLLBACK_MARKER)
    assert not os.path.isdir(updater.BACKUP_DIR)
    assert not (
        isolated_project / "old_module.py"
    ).exists(), "после подтверждения устаревший файл остаётся удалённым"
