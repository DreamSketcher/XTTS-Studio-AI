"""Explicit Coqui Public Model License (CPML) consent storage.

This module deliberately depends only on the standard library and small local
helpers.  License confirmation must remain available even when optional TTS
dependencies (num2words, pydub, torch, ...) cannot be imported.
"""

from __future__ import annotations

import json
import os
import time

from engine.atomic_write import atomic_write_json
from engine.paths import JSON_DIR

CPML_URL = "https://coqui.ai/cpml"


class CoquiTosNotAgreedError(RuntimeError):
    """Raised when XTTS is requested without explicit CPML consent."""


def _cpml_consent_path() -> str:
    # Resolve on every access so portable installs and tests can relocate the
    # JSON directory without being tied to a stale module-level cache.
    return os.path.join(JSON_DIR, "cpml_consent.json")


def _has_saved_consent() -> bool:
    try:
        with open(_cpml_consent_path(), encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError, TypeError):
        return False
    return isinstance(record, dict) and record.get("agreed") is True


def is_coqui_tos_agreed() -> bool:
    """Return whether the user explicitly accepted CPML.

    ``COQUI_TOS_AGREED=1`` is the explicit opt-in understood by Coqui TTS.
    Honour it when the user supplied it before launching the application, but
    never create a persistent consent record merely from an inherited value.
    Importing this module does not accept the license or modify the environment.
    """
    return os.environ.get("COQUI_TOS_AGREED", "").strip() == "1" or _has_saved_consent()


def set_coqui_tos_agreed(source: str = "user-confirmed") -> None:
    """Persist consent only after an explicit user confirmation.

    The environment flag is changed only after the record reaches disk, so a
    failed write is reported to the dialog instead of looking like success.
    """
    record = {
        "agreed": True,
        "source": str(source or "user-confirmed"),
        "confirmed_at": int(time.time()),
    }
    atomic_write_json(_cpml_consent_path(), record, ensure_ascii=False, indent=2)
    os.environ["COQUI_TOS_AGREED"] = "1"


def ensure_coqui_tos_agreed() -> None:
    """Allow model loading only after explicit consent; never auto-accept."""
    if is_coqui_tos_agreed():
        os.environ["COQUI_TOS_AGREED"] = "1"
        return
    raise CoquiTosNotAgreedError(
        "Coqui Public Model License (https://coqui.ai/cpml) has not been accepted. "
        "Open Settings → XTTS v2 license (CPML), review the license and confirm it, "
        "then retry generation. Alternatively, explicitly set COQUI_TOS_AGREED=1 "
        "before launching the application."
    )
