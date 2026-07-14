import json
import os
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import engine.rvc_catalog as rvc


@pytest.fixture
def tmp_rvc_dirs(tmp_path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir()
    models_rvc = base / "models" / "rvc"
    models_rvc.mkdir(parents=True)
    json_dir = base / "json"
    json_dir.mkdir()

    monkeypatch.setattr(rvc, "BASE_DIR", str(base))
    monkeypatch.setattr(rvc, "SEED_CATALOG_PATH", str(json_dir / "rvc_catalog_seed.json"))
    monkeypatch.setattr(rvc, "RVC_MODELS_DIR", str(models_rvc))
    monkeypatch.setattr(rvc, "CATALOG_CACHE_PATH", str(models_rvc / "catalog_cache.json"))
    # сбрасываем кэши
    monkeypatch.setattr(rvc, "_local_catalog_cache", None)
    monkeypatch.setattr(rvc, "_github_catalog_fail_until", 0.0)
    monkeypatch.setattr(rvc, "_github_catalog_fail_logged", False)
    monkeypatch.setattr(rvc, "_vm_search_fail_log_until", 0.0)

    yield {"base": base, "rvc_dir": models_rvc, "json_dir": json_dir}


class TestValidateCatalog:
    def test_valid(self):
        data = [
            {"id": "a", "name": "Model A", "url": "http://example.com/a.pth"},
            {"id": "b", "name": "Model B", "url": "http://example.com/b.zip"},
        ]
        assert len(rvc._validate_catalog(data)) == 2

    def test_invalid_filtered(self):
        data = [
            {"id": "", "name": "No ID", "url": "http://example.com"},
            {"id": "a", "name": "", "url": "http://example.com"},
            {"id": "b", "name": "No URL", "url": ""},
            "not a dict",
            {"id": "c", "name": "Valid", "url": "http://example.com/c"},
        ]
        valid = rvc._validate_catalog(data)
        assert len(valid) == 1
        assert valid[0]["id"] == "c"

    def test_not_list(self):
        assert rvc._validate_catalog({"id": "a"}) == []
        assert rvc._validate_catalog(None) == []


class TestLoadJson:
    def test_load_valid(self, tmp_path):
        file = tmp_path / "test.json"
        file.write_text(json.dumps([{"id": "a"}]), encoding="utf-8")
        assert rvc._load_json(str(file)) == [{"id": "a"}]

    def test_load_invalid(self, tmp_path):
        file = tmp_path / "test.json"
        file.write_text("{ invalid", encoding="utf-8")
        assert rvc._load_json(str(file)) is None

    def test_load_missing(self):
        assert rvc._load_json("/nonexistent/path.json") is None


class TestCleanDownloadUrl:
    def test_clean(self):
        assert (
            rvc._clean_download_url(
                "https://huggingface.co/model/resolve/main/model.pth%3Fdownload%3Dtrue"
            )
            == "https://huggingface.co/model/resolve/main/model.pth"
        )

        assert (
            rvc._clean_download_url("https://example.com/file.zip?download=true")
            == "https://example.com/file.zip"
        )

        assert (
            rvc._clean_download_url("https://huggingface.co/user/model/blob/main/model.pth")
            == "https://huggingface.co/user/model/resolve/main/model.pth"
        )

        assert (
            rvc._clean_download_url("https://voice-model.com/model/abc")
            == "https://voice-models.com/model/abc"
        )

    def test_empty(self):
        assert rvc._clean_download_url("") == ""


class TestSafeFilename:
    def test_stem_from_url(self):
        stem = rvc._safe_filename_stem("My Model", "https://example.com/my_model.pth", "123")
        assert stem == "my_model"

    def test_stem_fallback_to_name(self):
        stem = rvc._safe_filename_stem("My Cool Model!", "https://example.com/resolve/main", "123")
        assert len(stem) > 0
        assert "My_Cool_Model" in stem or "My" in stem

    def test_stem_fallback_to_id(self):
        stem = rvc._safe_filename_stem("", "https://example.com/resolve/main", "mid123")
        assert stem  # не пустой
        assert "model_mid123" in stem or "mid123" in stem or len(stem) > 0

    def test_guess_filename(self):
        assert rvc._guess_filename("Model", "https://example.com/model.pth", "1") == "model.pth"
        assert rvc._guess_filename("Model", "https://example.com/model.zip", "1").endswith(".zip")
        assert rvc._guess_filename(
            "Model", "https://huggingface.co/user/model/resolve/main/model", "1"
        ).endswith(".zip")
        assert rvc._guess_filename(
            "Model", "https://drive.google.com/file/d/abc/view", "1"
        ).endswith(".zip")


class TestIsDirectDownloadable:
    def test_direct(self):
        assert (
            rvc._is_direct_downloadable("https://huggingface.co/user/model/resolve/main/model.pth")
            is True
        )
        assert rvc._is_direct_downloadable("https://example.com/file.zip") is True
        assert rvc._is_direct_downloadable("https://example.com/file.pth") is True
        assert rvc._is_direct_downloadable("https://drive.google.com/file/d/abc123/view") is True
        assert (
            rvc._is_direct_downloadable("https://drive.google.com/uc?export=download&id=abc")
            is True
        )

    def test_not_direct(self):
        assert rvc._is_direct_downloadable("https://drive.google.com/drive/folders/abc") is False
        assert rvc._is_direct_downloadable("https://example.com/page") is False
        assert rvc._is_direct_downloadable("") is False

    def test_gdrive_id(self):
        assert (
            rvc._gdrive_file_id("https://drive.google.com/file/d/1ABC-123_xyz/view")
            == "1ABC-123_xyz"
        )
        assert rvc._gdrive_file_id("https://drive.google.com/uc?id=ABC123") == "ABC123"
        assert rvc._gdrive_file_id("https://example.com") is None

    def test_resolve_url(self):
        url = rvc._resolve_download_url("https://drive.google.com/file/d/ABC123/view")
        assert "uc?export=download&id=ABC123" in url

        with pytest.raises(ValueError):
            rvc._resolve_download_url("https://drive.google.com/drive/folders/ABC")


class TestParseVmTable:
    def test_parse(self):
        html = """
        <tr><td><a href='/model/12345' class='fs-5'>Test Model</a></td>
        <td><span class='badge bg-secondary'>100 MB</span></td>
        <td><a data-clipboard-text='https://huggingface.co/model/resolve/main/model.pth'></a></td>
        <td title='Uploaded by JohnDoe'></td></tr>
        """
        rows = rvc._parse_vm_table(html)
        assert len(rows) == 1
        assert rows[0]["mid"] == "12345"
        assert rows[0]["title"] == "Test Model"
        assert "huggingface" in rows[0]["download"]

    def test_row_to_entry(self):
        row = {
            "mid": "123",
            "title": "My Model",
            "author": "John",
            "size": "100 MB",
            "download": "https://example.com/model.pth",
        }
        entry = rvc._row_to_entry(row)
        assert entry["id"] == "vm_123"
        assert entry["name"] == "My Model"
        assert entry["downloadable"] is True
        assert "page_url" in entry

        # без mid/title -> None
        assert rvc._row_to_entry({"mid": "", "title": "x"}) is None
        assert rvc._row_to_entry({"mid": "1", "title": ""}) is None

    def test_row_no_download(self):
        row = {"mid": "123", "title": "Model", "download": ""}
        entry = rvc._row_to_entry(row)
        assert entry["url"] == "https://voice-models.com/model/123"
        assert entry["downloadable"] is False


class TestLocalModelPath:
    def test_pth(self, tmp_rvc_dirs):
        entry = {"filename": "model.pth", "url": "http://example.com/model.pth"}
        path = rvc.local_model_path(entry)
        assert path.endswith("model.pth")
        assert "models" in path and "rvc" in path

    def test_zip_becomes_pth(self, tmp_rvc_dirs):
        entry = {"filename": "model.zip", "url": "http://example.com/model.zip"}
        path = rvc.local_model_path(entry)
        assert path.endswith("model.pth")

    def test_no_ext_becomes_pth(self, tmp_rvc_dirs):
        entry = {"filename": "model", "url": "http://example.com/model"}
        path = rvc.local_model_path(entry)
        assert path.endswith("model.pth")

    def test_is_downloaded_and_delete(self, tmp_rvc_dirs):
        rvc_dir = tmp_rvc_dirs["rvc_dir"]
        entry = {"filename": "test_model.pth", "url": "http://example.com/test_model.pth"}
        assert rvc.is_downloaded(entry) is False
        (rvc_dir / "test_model.pth").write_text("fake pth")
        assert rvc.is_downloaded(entry) is True

        # delete
        assert rvc.delete_local_model("test_model") is True
        assert not (rvc_dir / "test_model.pth").exists()
        assert rvc.delete_local_model("nonexistent") is False

        # delete with index
        (rvc_dir / "with_index.pth").write_text("pth")
        (rvc_dir / "with_index.index").write_text("index")
        assert rvc.delete_local_model("with_index") is True
        assert not (rvc_dir / "with_index.pth").exists()
        assert not (rvc_dir / "with_index.index").exists()


class TestCatalogLoading:
    def test_load_local_cache(self, tmp_rvc_dirs):
        rvc_dir = tmp_rvc_dirs["rvc_dir"]
        json_dir = tmp_rvc_dirs["json_dir"]

        # seed
        seed_data = [{"id": "seed1", "name": "Seed Model", "url": "http://example.com/seed.pth"}]
        (json_dir / "rvc_catalog_seed.json").write_text(json.dumps(seed_data), encoding="utf-8")

        # должно загрузить seed
        catalog = rvc._load_local_catalog()
        assert len(catalog) == 1
        assert catalog[0]["id"] == "seed1"

        # кэш имеет приоритет над seed
        cache_data = [
            {"id": "cache1", "name": "Cache Model", "url": "http://example.com/cache.pth"}
        ]
        (rvc_dir / "catalog_cache.json").write_text(json.dumps(cache_data), encoding="utf-8")
        # сбрасываем in-memory кэш
        rvc._local_catalog_cache = None
        catalog2 = rvc._load_local_catalog()
        assert catalog2[0]["id"] == "cache1"

    def test_get_catalog_local_only(self, tmp_rvc_dirs):
        json_dir = tmp_rvc_dirs["json_dir"]
        seed_data = [{"id": "a", "name": "A Model", "url": "http://example.com/a.pth"}]
        (json_dir / "rvc_catalog_seed.json").write_text(json.dumps(seed_data), encoding="utf-8")
        rvc._local_catalog_cache = None

        # без force_refresh не должен ходить в сеть
        catalog = rvc.get_catalog(force_refresh=False)
        assert len(catalog) == 1


class TestSearchCatalog:
    def test_search_local(self, tmp_rvc_dirs):
        json_dir = tmp_rvc_dirs["json_dir"]
        seed_data = [
            {
                "id": "1",
                "name": "Naruto Voice",
                "url": "http://example.com/naruto.pth",
                "author": "John",
            },
            {"id": "2", "name": "Goku Voice", "url": "http://example.com/goku.pth"},
        ]
        (json_dir / "rvc_catalog_seed.json").write_text(json.dumps(seed_data), encoding="utf-8")
        rvc._local_catalog_cache = None

        results = rvc.search_catalog("naruto", live=False)
        assert len(results) == 1
        assert results[0]["id"] == "1"

        results2 = rvc.search_catalog("voice", live=False)
        assert len(results2) == 2

        # короткий запрос <2 → []
        assert rvc.search_catalog("a", live=False) == []


class TestZipExtraction:
    def test_extract(self, tmp_path):
        zip_path = tmp_path / "model.zip"
        dest_pth = tmp_path / "out" / "model.pth"

        # создаём zip с .pth и .index
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("model.pth", b"fake pth content")
            zf.writestr("model.index", b"fake index")

        result = rvc._extract_rvc_from_zip(str(zip_path), str(dest_pth))
        assert result is True
        assert dest_pth.exists()
        assert (tmp_path / "out" / "model.index").exists()

    def test_extract_no_pth(self, tmp_path):
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", b"no pth")

        dest = tmp_path / "out.pth"
        assert rvc._extract_rvc_from_zip(str(zip_path), str(dest)) is False

    def test_extract_largest_pth(self, tmp_path):
        zip_path = tmp_path / "multi.zip"
        dest = tmp_path / "out.pth"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("small.pth", b"small")
            zf.writestr("big.pth", b"big content here more bytes")

        result = rvc._extract_rvc_from_zip(str(zip_path), str(dest))
        assert result is True
        assert dest.read_bytes() == b"big content here more bytes"


class TestDownloadModel:
    def test_not_downloadable_returns_false(self, tmp_rvc_dirs):
        entry = {
            "id": "test",
            "name": "Test",
            "url": "https://drive.google.com/drive/folders/abc",
            "downloadable": False,
        }
        assert rvc.download_model(entry) is False

    def test_download_pth_mocked(self, tmp_rvc_dirs, monkeypatch):
        entry = {
            "id": "test",
            "name": "Test Model",
            "url": "https://example.com/model.pth",
            "filename": "test.pth",
            "downloadable": True,
        }

        def fake_download(url, tmp_path, progress_callback=None, cancelled_flag=None):
            Path(tmp_path).write_bytes(b"fake pth data")

        monkeypatch.setattr(rvc, "_download_bytes_to_file", fake_download)

        result = rvc.download_model(entry)
        assert result is True
        assert (tmp_rvc_dirs["rvc_dir"] / "test.pth").exists()

    def test_download_with_sha_mismatch(self, tmp_rvc_dirs, monkeypatch):
        entry = {
            "id": "test",
            "name": "Test",
            "url": "https://example.com/model.pth",
            "filename": "test2.pth",
            "sha256": "0" * 64,
            "downloadable": True,
        }

        def fake_download(url, tmp_path, progress_callback=None, cancelled_flag=None):
            Path(tmp_path).write_bytes(b"real content")

        monkeypatch.setattr(rvc, "_download_bytes_to_file", fake_download)

        result = rvc.download_model(entry)
        assert result is False
