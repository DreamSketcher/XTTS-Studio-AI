import hashlib
import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine.updater as upd


@pytest.fixture
def tmp_base_dir(tmp_path: Path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir()
    # Патчим все пути, которые зависят от BASE_DIR
    monkeypatch.setattr(upd, "BASE_DIR", str(base))
    monkeypatch.setattr(upd, "LOCAL_VERSION_PATH", str(base / "version.json"))
    monkeypatch.setattr(upd, "STAGING_DIR", str(base / "_update_staging"))
    monkeypatch.setattr(upd, "BACKUP_DIR", str(base / "_update_backup"))
    monkeypatch.setattr(upd, "ROLLBACK_MARKER", str(base / "_update_pending.json"))
    yield base


class TestVersionParsing:
    def test_version_gt(self):
        assert upd._version_gt("1.0.1", "1.0.0") is True
        assert upd._version_gt("1.0.0", "1.0.0") is False
        assert upd._version_gt("1.0.0", "1.0.1") is False
        assert upd._version_gt("2.0", "1.9.9") is True
        assert upd._version_gt("invalid", "0.0.0") is False  # parse -> (0,0,0)

    def test_version_lt(self):
        assert upd._version_lt("1.0.0", "1.0.1") is True
        assert upd._version_lt("1.0.1", "1.0.0") is False

    def test_get_local_version_missing(self, tmp_base_dir):
        assert upd.get_local_version() == "0.0.0"

    def test_get_local_version_exists(self, tmp_base_dir):
        (tmp_base_dir / "version.json").write_text(
            json.dumps({"version": "2.3.4"}), encoding="utf-8"
        )
        assert upd.get_local_version() == "2.3.4"


class TestSha256:
    def test_sha256_of_file(self, tmp_path):
        file = tmp_path / "test.bin"
        file.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert upd._sha256_of_file(str(file)) == expected


class TestIsCancelled:
    def test_none(self):
        assert upd._is_cancelled(None) is False

    def test_dict(self):
        assert upd._is_cancelled({"cancelled": True}) is True
        assert upd._is_cancelled({"cancelled": False}) is False
        assert upd._is_cancelled({}) is False

    def test_list(self):
        assert upd._is_cancelled([True]) is True
        assert upd._is_cancelled([False]) is False
        assert upd._is_cancelled([]) is False
        assert upd._is_cancelled((True,)) is True


class TestUrlopenRetry:
    def test_retry_success_on_second_attempt(self, monkeypatch):
        calls = {"count": 0}

        def fake_urlopen(req, timeout=0, context=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise Exception("transient")
            mock_resp = MagicMock()
            mock_resp.read.return_value = b'{"key":"val"}'
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = lambda s, *a: False
            return mock_resp

        monkeypatch.setattr(upd.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(upd.time, "sleep", lambda x: None)

        resp = upd._urlopen_with_retry("http://example.com", max_retries=2)
        assert calls["count"] == 2

    def test_retry_exhausted_raises(self, monkeypatch):
        def always_fail(*a, **kw):
            raise Exception("always fail")

        monkeypatch.setattr(upd.urllib.request, "urlopen", always_fail)
        monkeypatch.setattr(upd.time, "sleep", lambda x: None)

        with pytest.raises(Exception, match="always fail"):
            upd._urlopen_with_retry("http://example.com", max_retries=2)


class TestCheckUpdate:
    def test_available(self, tmp_base_dir, monkeypatch):
        # local 1.0.0, remote 1.0.1
        (tmp_base_dir / "version.json").write_text(
            json.dumps({"version": "1.0.0"}), encoding="utf-8"
        )
        monkeypatch.setattr(
            upd,
            "get_remote_version_info",
            lambda commit_sha=None: {
                "version": "1.0.1",
                "files": ["a.py"],
                "sha256": {},
                "changelog": "fix",
                "archive_sha256": "ab" * 32,
                "archive_url": "https://example.com/a.zip",
            },
        )

        result = upd.check_update()
        assert result["available"] is True
        assert result["local"] == "1.0.0"
        assert result["remote"] == "1.0.1"
        assert result["archive_sha256"] == "ab" * 32
        assert result["archive_url"] == "https://example.com/a.zip"

    def test_not_available(self, tmp_base_dir, monkeypatch):
        (tmp_base_dir / "version.json").write_text(
            json.dumps({"version": "2.0.0"}), encoding="utf-8"
        )
        monkeypatch.setattr(
            upd, "get_remote_version_info", lambda commit_sha=None: {"version": "1.0.0"}
        )

        result = upd.check_update()
        assert result["available"] is False

    def test_needs_manual_reinstall(self, tmp_base_dir, monkeypatch):
        (tmp_base_dir / "version.json").write_text(
            json.dumps({"version": "1.0.0"}), encoding="utf-8"
        )
        monkeypatch.setattr(
            upd,
            "get_remote_version_info",
            lambda commit_sha=None: {"version": "2.0.0", "min_app_version": "1.5.0", "files": []},
        )

        result = upd.check_update()
        assert result["needs_manual_reinstall"] is True

    def test_error_handling(self, tmp_base_dir, monkeypatch):
        monkeypatch.setattr(
            upd,
            "get_remote_version_info",
            lambda commit_sha=None: (_ for _ in ()).throw(Exception("fail")),
        )

        result = upd.check_update()
        assert result["available"] is False
        assert "error" in result


class TestManifestPathSecurity:
    @pytest.mark.parametrize(
        "unsafe",
        [
            "../outside.py",
            "engine/../../outside.py",
            r"..\outside.py",
            r"C:\Windows\Temp\payload.py",
            r"\\server\share\payload.py",
            "/absolute/payload.py",
            "engine//module.py",
            "./engine/module.py",
            "engine/module.py:stream",
            "",
        ],
    )
    def test_rejects_unsafe_manifest_paths(self, unsafe):
        with pytest.raises(ValueError):
            upd._safe_relative_path(unsafe)

    def test_normalizes_windows_separators(self):
        assert upd._safe_relative_path(r"engine\module.py") == "engine/module.py"

    def test_safe_path_stays_under_root(self, tmp_base_dir):
        result = Path(upd._safe_path_under(str(tmp_base_dir), "engine/module.py"))
        result.relative_to(tmp_base_dir.resolve())

    def test_apply_update_rejects_traversal_before_network(self, tmp_base_dir, monkeypatch):
        network_called = {"value": False}

        def should_not_call(*args, **kwargs):
            network_called["value"] = True
            raise AssertionError("network must not be called for an unsafe manifest")

        monkeypatch.setattr(upd, "_urlopen_with_retry", should_not_call)
        outside = tmp_base_dir.parent / "outside.py"
        assert upd.apply_update(["../outside.py"], {"../outside.py": "0" * 64}) is False
        assert network_called["value"] is False
        assert not outside.exists()

    def test_apply_update_rejects_update_remove_overlap(self, tmp_base_dir):
        assert (
            upd.apply_update(
                ["engine/a.py"],
                {"engine/a.py": "0" * 64},
                removed_files=["engine/a.py"],
            )
            is False
        )

    def test_existing_symlink_cannot_escape_root(self, tmp_base_dir, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        link = tmp_base_dir / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks are unavailable in this environment")
        with pytest.raises(ValueError):
            upd._safe_path_under(str(tmp_base_dir), "linked/payload.py")


class TestDownloadToStaging:
    def test_no_sha256_rejects(self, tmp_base_dir, monkeypatch):
        # без expected_sha256 должен вернуть False
        monkeypatch.setattr(upd, "_urlopen_with_retry", lambda *a, **kw: MagicMock())
        result = upd._download_to_staging("some/file.py", expected_sha256=None)
        assert result is False

    def test_success_with_correct_sha(self, tmp_base_dir, monkeypatch, tmp_path):
        content = b"print('hello')"
        expected_sha = hashlib.sha256(content).hexdigest()

        class FakeResp:
            def __init__(self):
                self._pos = 0

            def read(self, size=-1):
                if self._pos >= len(content):
                    return b""
                chunk = content[self._pos : self._pos + size]
                self._pos += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(upd, "_urlopen_with_retry", lambda url, timeout=30: FakeResp())
        monkeypatch.setattr(upd.time, "sleep", lambda x: None)

        result = upd._download_to_staging("folder/file.py", expected_sha256=expected_sha)
        assert result is True
        staged_path = Path(tmp_base_dir) / "_update_staging" / "folder" / "file.py"
        assert staged_path.exists()
        assert staged_path.read_bytes() == content

    def test_sha_mismatch_fails(self, tmp_base_dir, monkeypatch):
        content = b"real content"
        wrong_sha = "0" * 64

        class FakeResp:
            def read(self, size=-1):
                return b"" if hasattr(self, "_done") else setattr(self, "_done", True) or content

            def __enter__(self):
                self._done = False
                return self

            def __exit__(self, *a):
                return False

        # Простой фейк с одним чтением
        class SimpleResp:
            def read(self, size=-1):
                if not hasattr(self, "called"):
                    self.called = True
                    return content
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(upd, "_urlopen_with_retry", lambda url, timeout=30: SimpleResp())
        monkeypatch.setattr(upd.time, "sleep", lambda x: None)

        result = upd._download_to_staging(
            "file.py", expected_sha256=wrong_sha, sha_mismatch_retries=0
        )
        assert result is False

    def test_cancelled_during_download(self, tmp_base_dir, monkeypatch):
        content = b"x" * 100000
        expected_sha = hashlib.sha256(content).hexdigest()

        class SlowResp:
            def __init__(self):
                self.pos = 0

            def read(self, size=-1):
                if self.pos >= len(content):
                    return b""
                chunk = content[self.pos : self.pos + 8192]
                self.pos += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(upd, "_urlopen_with_retry", lambda *a, **kw: SlowResp())
        monkeypatch.setattr(upd.time, "sleep", lambda x: None)

        cancelled = {"cancelled": True}
        with pytest.raises(InterruptedError):
            upd._download_to_staging(
                "file.py", expected_sha256=expected_sha, cancelled_flag=cancelled
            )


class TestBackupAndMove:
    def test_backup_and_move(self, tmp_base_dir):
        base = Path(tmp_base_dir)
        # создаём рабочие файлы
        (base / "module").mkdir()
        (base / "module" / "a.py").write_text("old", encoding="utf-8")
        (base / "version.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")

        upd._backup_current_files(["module/a.py"])

        backup_dir = base / "_update_backup"
        assert (backup_dir / "module" / "a.py").exists()
        assert (backup_dir / "version.json").exists()

        # создаём staged файлы
        staging = base / "_update_staging"
        (staging / "module").mkdir(parents=True)
        (staging / "module" / "a.py").write_text("new", encoding="utf-8")

        upd._move_staged_to_live(["module/a.py"])

        assert (base / "module" / "a.py").read_text(encoding="utf-8") == "new"

    def test_delete_removed_files(self, tmp_base_dir):
        base = Path(tmp_base_dir)
        (base / "old").mkdir()
        (base / "old" / "unused.py").write_text("x", encoding="utf-8")

        upd._delete_removed_files(["old/unused.py"])
        assert not (base / "old" / "unused.py").exists()
        # пустая папка должна удалиться
        assert not (base / "old").exists()

    def test_rollback(self, tmp_base_dir):
        base = Path(tmp_base_dir)
        (base / "file.py").write_text("new version", encoding="utf-8")
        (base / "_update_backup").mkdir()
        (base / "_update_backup" / "file.py").write_text("old version", encoding="utf-8")
        (base / "_update_backup" / "version.json").write_text(
            json.dumps({"version": "1.0.0"}), encoding="utf-8"
        )
        marker = {
            "old_version": "1.0.0",
            "new_version": "2.0.0",
            "files": ["file.py"],
            "removed_files": [],
        }
        (base / "_update_pending.json").write_text(json.dumps(marker), encoding="utf-8")

        result = upd.rollback_update()
        assert result is True
        assert (base / "file.py").read_text(encoding="utf-8") == "old version"
        assert not (base / "_update_pending.json").exists()
        assert not (base / "_update_backup").exists()

    def test_pending_confirmation(self, tmp_base_dir):
        assert upd.has_pending_update_confirmation() is False
        (Path(tmp_base_dir) / "_update_pending.json").write_text("{}", encoding="utf-8")
        assert upd.has_pending_update_confirmation() is True

    def test_check_startup_health(self, tmp_base_dir):
        # нет маркера → ok
        assert upd.check_startup_health() == "ok"

        # первый запуск
        (Path(tmp_base_dir) / "_update_pending.json").write_text(
            json.dumps({"attempt": 0, "files": []}), encoding="utf-8"
        )
        assert upd.check_startup_health() == "first_attempt"
        data = json.loads((Path(tmp_base_dir) / "_update_pending.json").read_text(encoding="utf-8"))
        assert data["attempt"] == 1

        # второй запуск без подтверждения → rolled_back
        # нужно создать backup папку, чтобы rollback не упал из-за отсутствия
        (Path(tmp_base_dir) / "_update_backup").mkdir(exist_ok=True)
        assert upd.check_startup_health() == "rolled_back"

    def test_confirm_success(self, tmp_base_dir):
        base = Path(tmp_base_dir)
        (base / "_update_pending.json").write_text("{}", encoding="utf-8")
        (base / "_update_backup").mkdir()
        (base / "_update_backup" / "file.py").write_text("x")

        upd.confirm_update_success()
        assert not (base / "_update_pending.json").exists()
        assert not (base / "_update_backup").exists()

    def test_collect_diagnostics(self, tmp_base_dir):
        base = Path(tmp_base_dir)
        (base / "version.json").write_text(json.dumps({"version": "1.2.3"}), encoding="utf-8")
        diag = upd.collect_update_diagnostics({"available": False})
        assert "local_version" in diag
        assert "1.2.3" in diag


class TestApplyUpdateIntegration:
    def test_apply_update_success(self, tmp_base_dir, monkeypatch):
        base = Path(tmp_base_dir)
        # local version
        (base / "version.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")
        # existing file to be backed up
        (base / "mod").mkdir()
        (base / "mod" / "a.py").write_text("old", encoding="utf-8")

        content_new = b"new content"
        sha_new = hashlib.sha256(content_new).hexdigest()

        class FakeResp:
            def __init__(self):
                self._returned = False

            def read(self, size=-1):
                if not self._returned:
                    self._returned = True
                    return content_new
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(upd, "_urlopen_with_retry", lambda *a, **kw: FakeResp())
        monkeypatch.setattr(
            upd, "get_remote_version_info", lambda commit_sha=None: {"version": "1.0.1"}
        )
        monkeypatch.setattr(upd.time, "sleep", lambda x: None)

        result = upd.apply_update(
            files=["mod/a.py"],
            sha256_map={"mod/a.py": sha_new},
            removed_files=[],
            commit_sha="abc",
            sha_mismatch_retries=0,
            sha_mismatch_delay=0,
        )
        assert result is True
        assert (base / "mod" / "a.py").read_bytes() == content_new
        assert (base / "_update_pending.json").exists()

    def test_apply_update_cancelled(self, tmp_base_dir, monkeypatch):
        base = Path(tmp_base_dir)
        (base / "version.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")

        monkeypatch.setattr(upd.time, "sleep", lambda x: None)
        cancelled = {"cancelled": True}

        result = upd.apply_update(
            files=["f.py"],
            sha256_map={"f.py": "a" * 64},
            cancelled_flag=cancelled,
            sha_mismatch_delay=0,
        )
        assert result is False
        assert not (base / "_update_staging").exists() or not any(
            (base / "_update_staging").rglob("*")
        )


class TestArchiveUpdate:
    def _make_zip(self, tmp_path, members: dict) -> tuple[Path, str]:
        import zipfile

        archive = tmp_path / "payload.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            for name, content in members.items():
                zf.writestr(name, content)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        return archive, digest

    def test_extract_archive_rejects_zip_slip(self, tmp_base_dir, tmp_path):
        archive = tmp_path / "evil.zip"
        import zipfile

        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("../outside.py", b"pwned")
        with pytest.raises(ValueError):
            upd._extract_archive_safely(str(archive), dest_dir=str(tmp_base_dir / "out"))

    def test_extract_archive_safe_members(self, tmp_base_dir, tmp_path):
        archive, _ = self._make_zip(tmp_path, {"engine/a.py": b"print(1)"})
        dest = tmp_base_dir / "out"
        dest.mkdir()
        extracted = upd._extract_archive_safely(str(archive), dest_dir=str(dest))
        assert extracted == ["engine/a.py"]
        assert (dest / "engine" / "a.py").read_bytes() == b"print(1)"

    def test_apply_update_from_archive_success(self, tmp_base_dir, monkeypatch, tmp_path):
        base = Path(tmp_base_dir)
        (base / "version.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")
        (base / "mod").mkdir()
        (base / "mod" / "a.py").write_text("old", encoding="utf-8")

        content_new = b"new content"
        sha_new = hashlib.sha256(content_new).hexdigest()
        archive, archive_sha = self._make_zip(tmp_path, {"mod/a.py": content_new})

        class FakeResp:
            def __init__(self, data: bytes):
                self._data = data
                self._pos = 0

            def read(self, size=-1):
                if self._pos >= len(self._data):
                    return b""
                if size is None or size < 0:
                    chunk = self._data[self._pos :]
                else:
                    chunk = self._data[self._pos : self._pos + size]
                self._pos += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        payload = archive.read_bytes()
        monkeypatch.setattr(upd, "_urlopen_with_retry", lambda *a, **kw: FakeResp(payload))
        monkeypatch.setattr(
            upd,
            "get_remote_version_info",
            lambda commit_sha=None: {
                "version": "1.0.1",
                "files": ["mod/a.py"],
                "sha256": {"mod/a.py": sha_new},
                "archive_sha256": archive_sha,
            },
        )

        result = upd.apply_update(
            files=["mod/a.py"],
            sha256_map={"mod/a.py": sha_new},
            archive_sha256=archive_sha,
            archive_url="https://example.com/payload.zip",
            remote_info={
                "version": "1.0.1",
                "files": ["mod/a.py"],
                "sha256": {"mod/a.py": sha_new},
            },
        )
        assert result is True
        assert (base / "mod" / "a.py").read_bytes() == content_new
        assert (base / "_update_pending.json").exists()
        local = json.loads((base / "version.json").read_text(encoding="utf-8"))
        assert local["version"] == "1.0.1"

    def test_apply_update_archive_bad_hash(self, tmp_base_dir, monkeypatch, tmp_path):
        base = Path(tmp_base_dir)
        (base / "version.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")
        archive, _ = self._make_zip(tmp_path, {"mod/a.py": b"new"})
        payload = archive.read_bytes()

        class FakeResp:
            def __init__(self, data: bytes):
                self._data = data
                self._pos = 0

            def read(self, size=-1):
                if self._pos >= len(self._data):
                    return b""
                chunk = self._data[
                    self._pos : self._pos + (size if size and size > 0 else len(self._data))
                ]
                self._pos += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(upd, "_urlopen_with_retry", lambda *a, **kw: FakeResp(payload))
        result = upd.apply_update(
            files=["mod/a.py"],
            sha256_map={"mod/a.py": "0" * 64},
            archive_sha256="0" * 64,
            archive_url="https://example.com/payload.zip",
        )
        assert result is False
        assert not (base / "_update_pending.json").exists()
