import hashlib

from engine.release_hashing import (
    canonicalize_release_bytes,
    release_sha256_bytes,
)


def test_text_hash_is_identical_for_lf_and_crlf():
    lf = b"line one\nline two\n"
    crlf = b"line one\r\nline two\r\n"
    assert release_sha256_bytes(lf, "DOCUMENTATION.EN.md") == release_sha256_bytes(
        crlf, "DOCUMENTATION.EN.md"
    )


def test_binary_hash_preserves_bytes():
    data = b"binary\r\n\x00payload"
    assert canonicalize_release_bytes(data, "model.pth") == data
    assert release_sha256_bytes(data, "model.pth") == hashlib.sha256(data).hexdigest()


def test_dotfiles_and_batch_are_text():
    assert canonicalize_release_bytes(b"a\r\n", ".gitignore") == b"a\n"
    assert canonicalize_release_bytes(b"@echo off\r\n", "run.bat") == b"@echo off\n"
