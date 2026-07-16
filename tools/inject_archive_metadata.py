"""Inject archive_sha256/url/size into version.json and re-sign.

Used by .github/workflows/release.yml after the reproducible zip is built.
Accepts the private key via XTTS_UPDATE_SIGNING_KEY (PEM with literal \\n,
raw PEM, base64 PEM, or base64 PKCS8 DER). Never writes the key to disk.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_ARCHIVE_URL = (
    "https://github.com/DreamSketcher/XTTS-Studio-AI/releases/latest/download/"
    "XTTS-Studio-portable.zip"
)


def _load_private_key(key_material: str):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    material = (key_material or "").strip()
    if not material:
        raise ValueError("empty signing key")

    if os.path.isfile(material):
        material = Path(material).read_text(encoding="utf-8").strip()

    if "\\n" in material and "BEGIN" in material:
        key_bytes = material.replace("\\n", "\n").encode("utf-8")
    elif "BEGIN" in material:
        key_bytes = material.encode("utf-8")
    else:
        try:
            key_bytes = base64.b64decode(material)
        except Exception as exc:
            raise ValueError(f"cannot decode XTTS_UPDATE_SIGNING_KEY: {exc}") from exc

    if b"BEGIN" in key_bytes:
        key = serialization.load_pem_private_key(key_bytes, password=None)
    else:
        key = serialization.load_der_private_key(key_bytes, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("update signing key must be Ed25519")
    return key


def inject(
    archive_path: Path,
    manifest_path: Path,
    signature_path: Path,
    checksums_path: Path,
    archive_url: str,
    signing_key: str | None,
) -> str:
    from engine.update_signing import canonical_manifest_bytes, verify_manifest_signature
    from generate_version_manifest import SELF_GENERATED_FILES, sha256_of_file

    archive_bytes = archive_path.read_bytes()
    archive_sha = hashlib.sha256(archive_bytes).hexdigest()
    archive_size = len(archive_bytes)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["archive_sha256"] = archive_sha
    manifest["archive_url"] = archive_url
    manifest["archive_size"] = archive_size

    files = [p for p in manifest.get("files", []) if p not in SELF_GENERATED_FILES]
    sha_map: dict[str, str] = {}
    for rel in files:
        full = Path(rel.replace("/", os.sep))
        if full.is_file():
            sha_map[rel] = sha256_of_file(str(full), rel)
    manifest["files"] = files
    manifest["sha256"] = sha_map

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    version = manifest.get("version", "?")
    lines = [
        f"XTTS Studio — контрольные суммы SHA256 для версии {version}",
        'Проверка (Windows PowerShell): certutil -hashfile "имя_файла" SHA256',
        "Проверка (Linux/macOS): sha256sum имя_файла",
        "",
        f"{archive_sha}  {archive_path.name}",
    ]
    for rel, digest in sha_map.items():
        lines.append(f"{digest}  {rel}")
    checksums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if signing_key:
        try:
            key = _load_private_key(signing_key)
            signature = key.sign(canonical_manifest_bytes(manifest_path.read_bytes()))
            signature_path.write_bytes(base64.b64encode(signature) + b"\n")
            verify_manifest_signature(manifest_path.read_bytes(), signature_path.read_bytes())
            print(
                f"Injected archive_sha256={archive_sha} archive_size={archive_size}; "
                "version.json re-signed and verified successfully."
            )
        except Exception as exc:
            print(f"[!] Warning: Could not re-sign version.json with provided key: {exc}")
    else:
        print(
            f"Injected archive_sha256={archive_sha} archive_size={archive_size} into version.json and checksums.txt."
        )
        print(
            "[!] Notice: XTTS_UPDATE_SIGNING_KEY secret is not set in GitHub Repository Secrets.\n"
            "    To enable post-build Ed25519 re-signing on GitHub Actions, add your PEM key to:\n"
            "    GitHub Repo -> Settings -> Secrets and variables -> Actions -> Secret name: XTTS_UPDATE_SIGNING_KEY"
        )

    return archive_sha


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=Path("XTTS-Studio-portable.zip"))
    parser.add_argument("--manifest", type=Path, default=Path("json/version.json"))
    parser.add_argument("--signature", type=Path, default=Path("json/version.json.sig"))
    parser.add_argument("--checksums", type=Path, default=Path("checksums.txt"))
    parser.add_argument("--archive-url", default=DEFAULT_ARCHIVE_URL)
    parser.add_argument(
        "--signing-key",
        default=os.environ.get("XTTS_UPDATE_SIGNING_KEY"),
        help="Ed25519 private key material, or set XTTS_UPDATE_SIGNING_KEY",
    )
    args = parser.parse_args()
    signing_key = args.signing_key or os.environ.get("XTTS_UPDATE_SIGNING_KEY")
    if not signing_key:
        default_key = PROJECT_ROOT / "keys" / "XTTS-Studio-signing-private.pem"
        win_key = Path(r"C:\XTTS Signing Keys\XTTS-Studio-signing-private.pem")
        if default_key.is_file():
            signing_key = str(default_key)
        elif win_key.is_file():
            signing_key = str(win_key)

    inject(
        archive_path=args.archive,
        manifest_path=args.manifest,
        signature_path=args.signature,
        checksums_path=args.checksums,
        archive_url=args.archive_url,
        signing_key=signing_key,
    )


if __name__ == "__main__":
    main()
