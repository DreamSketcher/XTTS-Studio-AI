from __future__ import annotations

"""Общий контекст зависимостей модульного окна настроек AI.

Строители страниц получают этот объект вместо одной гигантской closure.
Контекст содержит только ссылки, которые раньше захватывал open_gpt_settings().
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class SettingsContext:
    """Runtime-ссылки, общие для строителей страниц настроек."""

    win: Any
    canvas: Any
    canvas_frame: Any
    gpt_client: Any
    local_llm_client: Any
    scroll_over_child: dict
    invalidate_page: Optional[Callable[[str], None]] = None
    show_page: Optional[Callable[[str], None]] = None
    show_page_with_style: Optional[Callable[[str], None]] = None
