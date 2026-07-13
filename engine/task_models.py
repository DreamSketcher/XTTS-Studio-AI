# engine/task_models.py
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import uuid


@dataclass
class Task:
    text: str
    voice: str

    output_path: Optional[str] = None

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # 👇 ВАЖНО ДЛЯ UI
    name: Optional[str] = None
    raw_text: str = ""

    status: str = "queued"
    progress: int = 0
    cancelled: bool = False

    speed: float = 1.0
    language: str = "auto"
    quality: str = "Баланс"

    quality_params: dict = field(default_factory=dict)

    created_at: datetime = field(default_factory=datetime.now)

    error: Optional[str] = None
    stats: Optional[dict] = None
