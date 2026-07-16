"""Cross-platform SHA-256 for release payloads.

Git/Windows may expose text as CRLF while GitHub raw serves LF. Release hashes
canonicalize line endings for known text formats and preserve binary bytes.
"""

import hashlib
from pathlib import Path

_TEXT_SUFFIXES = {
    ".py",
    ".pyi",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".bat",
    ".cmd",
    ".ps1",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".svg",
}
_TEXT_NAMES = {
    ".gitignore",
    ".gitattributes",
    ".pre-commit-config.yaml",
    "requirements.txt",
    "checksums.txt",
}


def is_release_text_path(relative_path: str) -> bool:
    normalized = str(relative_path or "").replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1].lower()
    return name in _TEXT_NAMES or Path(name).suffix.lower() in _TEXT_SUFFIXES


def canonicalize_release_bytes(data: bytes, relative_path: str) -> bytes:
    if not is_release_text_path(relative_path):
        return data
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def release_sha256_bytes(data: bytes, relative_path: str) -> str:
    return hashlib.sha256(canonicalize_release_bytes(data, relative_path)).hexdigest()


def release_sha256_file(path, relative_path: str) -> str:
    return release_sha256_bytes(Path(path).read_bytes(), relative_path)
