"""Ed25519 verification for immutable XTTS Studio update manifests."""

import base64
import json
import sys
from pathlib import Path

_BUNDLED_SITE_PACKAGES = (
    Path(__file__).resolve().parents[1] / "python" / "xtts_env" / "Lib" / "site-packages"
)
if _BUNDLED_SITE_PACKAGES.is_dir() and str(_BUNDLED_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_BUNDLED_SITE_PACKAGES))

# Release verification key. The matching private key must never be committed or
# placed in a portable build. Rotate only through a separately authenticated
# application release.
UPDATE_MANIFEST_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAgQpSKuteEEMxT8VNCTGZtlwkZttf8bu+BxsBjyJFaiA=
-----END PUBLIC KEY-----
"""


class ManifestSignatureError(RuntimeError):
    pass


def canonical_manifest_bytes(manifest_bytes: bytes) -> bytes:
    """Canonical JSON representation, independent of indentation and CRLF."""
    try:
        document = json.loads(manifest_bytes.decode("utf-8"))
        if not isinstance(document, dict):
            raise ValueError("manifest must be a JSON object")
        return json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception as exc:
        raise ManifestSignatureError(f"некорректный update-манифест: {exc}") from exc


def verify_manifest_signature(manifest_bytes: bytes, signature_bytes: bytes) -> None:
    """Verify manifest semantics in a stable canonical JSON representation."""
    if not manifest_bytes or not signature_bytes:
        raise ManifestSignatureError("манифест или подпись пусты")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = serialization.load_pem_public_key(UPDATE_MANIFEST_PUBLIC_KEY_PEM)
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError("ожидался Ed25519 public key")
        signature = base64.b64decode(signature_bytes.strip(), validate=True)
        key.verify(signature, canonical_manifest_bytes(manifest_bytes))
    except ManifestSignatureError:
        raise
    except Exception as exc:
        raise ManifestSignatureError(f"подпись update-манифеста недействительна: {exc}") from exc
