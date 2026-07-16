# -*- coding: utf-8 -*-
"""engine/atomic_write.py — atomary file writes (mkstemp + fsync + replace)

Unifies pattern used correctly in gpt_client.py (_write_all_settings) but
incorrectly as plain open(..., "w") in settings_store.py, history_store.py,
theme_manager.py etc.

Why atomic:
- plain open("w") truncates file immediately; if process crashes between
  truncate and write, file becomes empty/corrupt → load_settings returns {}.
- mkstemp writes to temp file in same directory, fsync, then os.replace
  which is atomic on POSIX and Windows (replace).

Risk: low, behavior same on success, only failure mode improved.
"""

from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(path: str | os.PathLike, text: str, encoding: str = "utf-8") -> None:
    """Write text atomically: temp file + fsync + replace."""
    path = Path(path)
    directory = str(path.parent) if str(path.parent) else "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="." + path.name + "_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def atomic_write_json(path: str | os.PathLike, data: Any, ensure_ascii: bool = False, indent: int = 2) -> None:
    """Write JSON atomically."""
    path = Path(path)
    directory = str(path.parent) if str(path.parent) else "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="." + path.name + "_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise

def atomic_write_bytes(path: str | os.PathLike, data: bytes) -> None:
    """Write bytes atomically."""
    path = Path(path)
    directory = str(path.parent) if str(path.parent) else "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="." + path.name + "_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
