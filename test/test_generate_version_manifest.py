# -*- coding: utf-8 -*-
"""
test_generate_version_manifest.py — тесты для generate_version_manifest.py.

Проверяет:
  1. SHA256 честно считается по реальному содержимому файлов на диске.
  2. removed_files — файлы, пропавшие из списка files, накапливаются между
     релизами (а не только diff с последним коммитом).
  3. Самоисправление: если файл, ранее помеченный как удалённый, снова
     появился в files — он должен пропасть из removed_files.
  4. UTF-8: кириллица в changelog не роняет чтение предыдущего манифеста
     через `git show HEAD:version.json` (регрессия на cp1251-баг).
  5. Файлы из missing (нет на диске) не попадают в sha256, но и не ломают
     обработку остальных.

Работает в реальном (временном) git-репозитории — subprocess пишет туда
коммиты, generate_version_manifest.py запускается как подпроцесс, чтобы
проверка была максимально близка к тому, как он реально используется в
git_update.py.

Запуск:
    pytest test_generate_version_manifest.py -v
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "generate_version_manifest.py"
if not SCRIPT_PATH.exists():
    # Позволяет класть тест и скрипт рядом в одной папке при локальном запуске
    SCRIPT_PATH = Path(__file__).resolve().parent / "generate_version_manifest.py"


def _run_git(repo: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=30,
    )


import shutil


def _run_generator(repo: Path, *args) -> subprocess.CompletedProcess:
    # BASE_DIR в generate_version_manifest.py вычисляется от os.path.dirname(__file__),
    # а не от cwd — поэтому сам скрипт должен физически лежать в тестовом репозитории.
    script_in_repo = repo / "generate_version_manifest.py"
    if not script_in_repo.exists():
        shutil.copy(SCRIPT_PATH, script_in_repo)
    return subprocess.run(
        [sys.executable, str(script_in_repo)] + list(args),
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@test.com")
    _run_git(repo, "config", "user.name", "Test")
    return repo


def _write_version_json(repo: Path, data: dict):
    (repo / "version.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _commit(repo: Path, message: str):
    _run_git(repo, "add", "-A")
    r = _run_git(repo, "commit", "-q", "-m", message)
    assert r.returncode == 0, f"commit failed: {r.stderr}"


# ───────────────────────── базовое поведение: sha256 ─────────────────────────


def test_sha256_matches_real_file_content(git_repo):
    (git_repo / "a.py").write_text("print('hello')", encoding="utf-8")
    _write_version_json(
        git_repo,
        {
            "version": "1.0.0",
            "files": ["a.py"],
            "changelog": "init",
            "sha256": {},
        },
    )
    _commit(git_repo, "release 1.0.0")

    r = _run_generator(git_repo, "--version", "1.0.1")
    assert r.returncode == 0, r.stdout + r.stderr

    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    import hashlib

    expected = hashlib.sha256(b"print('hello')").hexdigest()
    assert manifest["sha256"]["a.py"] == expected
    assert manifest["version"] == "1.0.1"


def test_missing_file_is_skipped_without_crashing(git_repo):
    _write_version_json(
        git_repo,
        {
            "version": "1.0.0",
            "files": ["a.py", "does_not_exist.py"],
            "changelog": "init",
            "sha256": {},
        },
    )
    (git_repo / "a.py").write_text("code", encoding="utf-8")
    _commit(git_repo, "release 1.0.0")

    r = _run_generator(git_repo, "--version", "1.0.1")
    assert r.returncode == 0, r.stdout + r.stderr

    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    assert "a.py" in manifest["sha256"]
    assert "does_not_exist.py" not in manifest["sha256"]


# ───────────────────────── removed_files: базовый diff ─────────────────────────


def test_removed_files_detects_file_missing_from_new_release(git_repo):
    (git_repo / "old.py").write_text("old code", encoding="utf-8")
    (git_repo / "keep.py").write_text("kept code", encoding="utf-8")
    _write_version_json(
        git_repo,
        {
            "version": "1.0.0",
            "files": ["old.py", "keep.py"],
            "changelog": "init",
            "sha256": {},
        },
    )
    _commit(git_repo, "release 1.0.0")

    # Симулируем рефакторинг: old.py убран из проекта и из списка files
    # (как это сделал бы generate_version_files.py перед этим скриптом)
    (git_repo / "old.py").unlink()
    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    manifest["files"] = ["keep.py"]
    _write_version_json(git_repo, manifest)

    r = _run_generator(git_repo, "--version", "1.0.1")
    assert r.returncode == 0, r.stdout + r.stderr

    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    assert manifest["removed_files"] == ["old.py"]


def test_removed_files_empty_when_nothing_removed(git_repo):
    (git_repo / "a.py").write_text("code", encoding="utf-8")
    _write_version_json(
        git_repo,
        {
            "version": "1.0.0",
            "files": ["a.py"],
            "changelog": "init",
            "sha256": {},
        },
    )
    _commit(git_repo, "release 1.0.0")

    r = _run_generator(git_repo, "--version", "1.0.1")
    assert r.returncode == 0, r.stdout + r.stderr

    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    assert manifest["removed_files"] == []


def test_removed_files_empty_on_first_ever_release(git_repo):
    """Нет предыдущего коммита -> git show HEAD:version.json не сработает ->
    removed_files должен быть пустым, а не падать с ошибкой."""
    (git_repo / "a.py").write_text("code", encoding="utf-8")
    _write_version_json(
        git_repo,
        {
            "version": "1.0.0",
            "files": ["a.py"],
            "changelog": "init",
            "sha256": {},
        },
    )
    # НЕ коммитим — HEAD ещё не существует

    r = _run_generator(git_repo, "--version", "1.0.0")
    assert r.returncode == 0, r.stdout + r.stderr

    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    assert manifest["removed_files"] == []


# ───────────────────────── removed_files: накопление между релизами ─────────────────────────


def test_removed_files_accumulate_across_multiple_releases(git_repo):
    (git_repo / "a.py").write_text("a", encoding="utf-8")
    (git_repo / "b.py").write_text("b", encoding="utf-8")
    (git_repo / "c.py").write_text("c", encoding="utf-8")
    _write_version_json(
        git_repo,
        {
            "version": "1.0.0",
            "files": ["a.py", "b.py", "c.py"],
            "changelog": "init",
            "sha256": {},
        },
    )
    _commit(git_repo, "release 1.0.0")

    # Релиз 1.0.1: убираем a.py
    (git_repo / "a.py").unlink()
    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    manifest["files"] = ["b.py", "c.py"]
    _write_version_json(git_repo, manifest)
    r = _run_generator(git_repo, "--version", "1.0.1")
    assert r.returncode == 0, r.stdout + r.stderr
    _commit(git_repo, "release 1.0.1")

    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    assert manifest["removed_files"] == ["a.py"]

    # Релиз 1.0.2: убираем ещё и b.py — a.py должен остаться в списке
    (git_repo / "b.py").unlink()
    manifest["files"] = ["c.py"]
    _write_version_json(git_repo, manifest)
    r = _run_generator(git_repo, "--version", "1.0.2")
    assert r.returncode == 0, r.stdout + r.stderr

    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    assert sorted(manifest["removed_files"]) == [
        "a.py",
        "b.py",
    ], "removed_files должен накапливаться, а не только отражать diff с последним коммитом"


def test_removed_files_self_heals_when_file_reappears(git_repo):
    """Если файл, ранее помеченный на удаление, снова оказался в files
    (например, откатили рефакторинг) — он должен пропасть из removed_files,
    иначе апдейтер удалит у пользователей файл, который на самом деле нужен."""
    (git_repo / "a.py").write_text("a", encoding="utf-8")
    (git_repo / "b.py").write_text("b", encoding="utf-8")
    _write_version_json(
        git_repo,
        {
            "version": "1.0.0",
            "files": ["a.py", "b.py"],
            "changelog": "init",
            "sha256": {},
        },
    )
    _commit(git_repo, "release 1.0.0")

    # 1.0.1: убрали a.py
    (git_repo / "a.py").unlink()
    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    manifest["files"] = ["b.py"]
    _write_version_json(git_repo, manifest)
    r = _run_generator(git_repo, "--version", "1.0.1")
    assert r.returncode == 0, r.stdout + r.stderr
    _commit(git_repo, "release 1.0.1")

    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    assert manifest["removed_files"] == ["a.py"]

    # 1.0.2: a.py вернули обратно в проект
    (git_repo / "a.py").write_text("a again", encoding="utf-8")
    manifest["files"] = ["a.py", "b.py"]
    _write_version_json(git_repo, manifest)
    r = _run_generator(git_repo, "--version", "1.0.2")
    assert r.returncode == 0, r.stdout + r.stderr

    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    assert (
        manifest["removed_files"] == []
    ), "файл, вернувшийся в files, не должен оставаться в removed_files"
    assert "a.py" in manifest["sha256"]


# ───────────────────────── UTF-8 / кириллица (регрессия на cp1251-баг) ─────────────────────────


def test_handles_cyrillic_changelog_without_crashing(git_repo):
    """Регрессионный тест: раньше _get_previous_files_list() использовал
    text=True без явной кодировки, что на Windows брало cp1251 консоли и
    падало на кириллице в changelog. Тут явно проверяем, что кириллица
    не мешает как минимум на уровне text= кодирования (эмулируем то, что
    может пойти не так, декодируя строго как UTF-8)."""
    (git_repo / "a.py").write_text("code", encoding="utf-8")
    (git_repo / "old.py").write_text("old", encoding="utf-8")
    _write_version_json(
        git_repo,
        {
            "version": "1.0.0",
            "files": ["a.py", "old.py"],
            "changelog": "- Редизайн интерфейса\n- Исправлены ошибки — оптимизация",
            "sha256": {},
        },
    )
    _commit(git_repo, "release 1.0.0")

    (git_repo / "old.py").unlink()
    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    manifest["files"] = ["a.py"]
    _write_version_json(git_repo, manifest)

    r = _run_generator(
        git_repo, "--version", "1.0.1", "--changelog", "- Новая кириллическая строка чейнджлога"
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "UnicodeDecodeError" not in r.stdout
    assert "UnicodeDecodeError" not in r.stderr

    manifest = json.loads((git_repo / "version.json").read_text(encoding="utf-8"))
    assert manifest["removed_files"] == [
        "old.py"
    ], "removed_files должен посчитаться корректно даже при кириллице в предыдущем коммите"
    assert manifest["changelog"] == "- Новая кириллическая строка чейнджлога"


# ───────────────────────── checksums.txt ─────────────────────────


def test_checksums_txt_is_created(git_repo):
    (git_repo / "a.py").write_text("code", encoding="utf-8")
    _write_version_json(
        git_repo,
        {
            "version": "1.0.0",
            "files": ["a.py"],
            "changelog": "init",
            "sha256": {},
        },
    )
    _commit(git_repo, "release 1.0.0")

    r = _run_generator(git_repo, "--version", "1.0.1")
    assert r.returncode == 0, r.stdout + r.stderr

    checksums = (git_repo / "checksums.txt").read_text(encoding="utf-8")
    assert "a.py" in checksums
