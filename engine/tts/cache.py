from typing import Any, List, Optional, Tuple
import re
import os
import sys
import time
from datetime import datetime
import unicodedata as _unicodedata
import threading as _threading
import hashlib
import torch
import gc


def _chunk_cache_key(
    chunk: str,
    lang: str,
    preset: dict,
    speed: float,
    ref_path: str = "",
    conductor_active: bool = False,
) -> str:
    ref_hash = hashlib.md5(ref_path.encode("utf-8")).hexdigest()[:8] if ref_path else ""
    mode_tag = "conductor" if conductor_active else "standard"
    raw = f"v6_{mode_tag}|{ref_hash}|{chunk}|{lang}|{speed}|{sorted(preset.items())}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _chunk_cache_path(output_dir: str, key: str) -> str:
    cache_dir = os.path.join(output_dir, "_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{key}.wav")


def _chunk_cache_get(output_dir: str, key: str):
    p = _chunk_cache_path(output_dir, key)
    if os.path.exists(p):
        print(f"[CACHE] Hit: {key[:8]}...")
        return p
    return None


def _chunk_cache_set(output_dir: str, key: str, wav_path: str):
    dst = _chunk_cache_path(output_dir, key)
    try:
        import shutil

        shutil.copy2(wav_path, dst)
    except Exception as e:
        print(f"[CACHE] Save failed: {e}")
