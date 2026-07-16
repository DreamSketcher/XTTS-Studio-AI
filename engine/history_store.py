# -*- coding: utf-8 -*-
"""engine/history_store.py — хранилище истории генераций (перенесено из gui.py: HISTORY_PATH, _save_history)."""
import json
import os
from datetime import datetime

from engine.paths import BASE_DIR
from engine.atomic_write import atomic_write_json

HISTORY_PATH = os.path.join(BASE_DIR, "history.json")


def _save_history(task):
    try:
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
        entry = {
            "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "text": task.text or "",
            "voice": os.path.basename(os.path.dirname(task.voice or "")),
            "quality": task.quality or "",
            "output": task.output_path or "",
            "duration": task.stats.get("time_sec", 0) if task.stats else 0,
            "chunks": task.stats.get("chunks", 0) if task.stats else 0,
        }
        history.insert(0, entry)
        history = history[:100]
        atomic_write_json(HISTORY_PATH, history, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[History] Save error: {e}")


# Публичный псевдоним
save_history = _save_history
