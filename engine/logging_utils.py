# -*- coding: utf-8 -*-
"""engine/logging_utils.py — файловое логирование (перенесено из gui.py: write_log, _log)."""
import os
from datetime import datetime

from engine.paths import LOG_DIR

LOG_FILE = os.path.join(LOG_DIR, "xtts_studio.log")
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 МБ — при превышении лог обнуляется


def reset_session_log():
    """Полностью очищает xtts_studio.log в начале каждой сессии (запуска приложения).

    Лог перезаписывается (truncate) — старые записи предыдущих сеансов не
    накапливаются. В течение сессии write_log дописывает лог (append), поэтому
    история текущего запуска сохраняется. Вызывается при импорте модуля
    (один раз за процесс = один запуск приложения = одна сессия).
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        # 'w' создаёт пустой файл или обнуляет существующий, не бросая
        # исключения, если файла ещё нет.
        with open(LOG_FILE, "w", encoding="utf-8"):
            pass
    except Exception:
        pass


def write_log(text: str):
    """Пишет строку в единый лог-файл logs/xtts_studio.log (диагностика, установки
    зависимостей, RVC/torch/llama и т.п. — всё в одном месте, без вывода в консоль GUI).
    При достижении 10 МБ файл обнуляется перед записью, чтобы не расти бесконечно
    на портативной установке.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) >= MAX_LOG_SIZE:
            os.remove(LOG_FILE)
    except Exception:
        pass
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")


def _log(msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    boot_log = os.path.join(LOG_DIR, "boot.log")
    with open(boot_log, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


# ── Перезапись лога при старте каждой сессии ──
# Модуль импортируется ровно один раз за процесс (один запуск приложения),
# поэтому вызов здесь гарантирует чистый лог на старте сессии, до первой
# записи через write_log().
reset_session_log()
