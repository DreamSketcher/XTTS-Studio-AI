import base64

import pytest

pytest.importorskip("cryptography", reason="Ed25519 test dependency is not installed")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from engine import update_signing


def _temporary_keypair(monkeypatch):
    private = Ed25519PrivateKey.generate()
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    monkeypatch.setattr(update_signing, "UPDATE_MANIFEST_PUBLIC_KEY_PEM", public_pem)
    return private


def test_valid_signature(monkeypatch):
    private = _temporary_keypair(monkeypatch)
    manifest = b'{"version":"1.2.3"}'
    signature = base64.b64encode(private.sign(update_signing.canonical_manifest_bytes(manifest)))
    update_signing.verify_manifest_signature(manifest, signature)


def test_modified_manifest_is_rejected(monkeypatch):
    private = _temporary_keypair(monkeypatch)
    original = b'{"version":"1.0.0"}'
    signature = base64.b64encode(private.sign(update_signing.canonical_manifest_bytes(original)))
    with pytest.raises(update_signing.ManifestSignatureError):
        update_signing.verify_manifest_signature(b'{"version":"2.0.0"}', signature)


def test_whitespace_and_crlf_do_not_break_signature(monkeypatch):
    private = _temporary_keypair(monkeypatch)
    compact = b'{"files":["a.py"],"version":"1.0.0"}'
    formatted = b'{\r\n  "version": "1.0.0",\r\n  "files": ["a.py"]\r\n}\r\n'
    signature = base64.b64encode(private.sign(update_signing.canonical_manifest_bytes(compact)))
    update_signing.verify_manifest_signature(formatted, signature)


@pytest.mark.parametrize("signature", [b"", b"not-base64", base64.b64encode(b"short")])
def test_invalid_signature_is_rejected(monkeypatch, signature):
    _temporary_keypair(monkeypatch)
    with pytest.raises(update_signing.ManifestSignatureError):
        update_signing.verify_manifest_signature(b"manifest", signature)
