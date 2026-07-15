import base64
import hashlib
import json
from pathlib import Path

import pytest

pytest.importorskip("cryptography", reason="release signing test dependency is not installed")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from engine import update_signing
from tools.build_reproducible_release import build


def test_same_tree_produces_identical_archive(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("print('ok')\n", encoding="utf-8")
    digest = hashlib.sha256((source / "app.py").read_bytes()).hexdigest()
    manifest = tmp_path / "version.json"
    manifest.write_text(
        json.dumps({"version": "1.0.0", "files": ["app.py"], "sha256": {"app.py": digest}}),
        encoding="utf-8",
    )
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    monkeypatch.setattr(update_signing, "UPDATE_MANIFEST_PUBLIC_KEY_PEM", public)
    signature = tmp_path / "version.json.sig"
    signature.write_bytes(
        base64.b64encode(
            private.sign(update_signing.canonical_manifest_bytes(manifest.read_bytes()))
        )
    )

    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    assert build(source, manifest, signature, first) == build(source, manifest, signature, second)
    assert first.read_bytes() == second.read_bytes()
