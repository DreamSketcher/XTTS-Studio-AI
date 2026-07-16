"""Build a deterministic XTTS Studio update archive from a signed manifest."""

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(source_root: Path, manifest_path: Path, signature_path: Path, output: Path):
    from engine.update_signing import verify_manifest_signature
    from engine.updater import _validate_manifest_paths

    manifest_bytes = manifest_path.read_bytes()
    verify_manifest_signature(manifest_bytes, signature_path.read_bytes())
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    files, _removed = _validate_manifest_paths(manifest.get("files", []), [])
    from engine.release_hashing import release_sha256_file

    expected = manifest.get("sha256", {})
    missing = []
    mismatched = []
    for relative in files:
        path = source_root / Path(*relative.split("/"))
        if not path.is_file():
            missing.append(relative)
        elif release_sha256_file(path, relative).lower() != str(expected.get(relative, "")).lower():
            mismatched.append(relative)
    if missing or mismatched:
        raise RuntimeError(f"release tree invalid; missing={missing}, mismatched={mismatched}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        payload = [(relative, source_root / Path(*relative.split("/"))) for relative in files]
        payload += [("version.json", manifest_path), ("version.json.sig", signature_path)]
        seen = set()
        for relative, path in sorted(payload, key=lambda item: item[0]):
            if relative in seen:
                continue
            seen.add(relative)
            info = zipfile.ZipInfo(relative, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
            )
    return sha256(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path("."))
    parser.add_argument("--manifest", type=Path, default=Path("version.json"))
    parser.add_argument("--signature", type=Path, default=Path("version.json.sig"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.source_root, args.manifest, args.signature, args.output))


if __name__ == "__main__":
    main()
