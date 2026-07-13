# -*- coding: utf-8 -*-
"""engine/paths.py — централизованные пути проекта XTTS Studio

Совместимая версия для патча расположения панелей (2026-07-09):
- экспортирует все исторически использовавшиеся константы
- для неизвестных имён — fallback через __getattr__ (PEP 562),
  чтобы не падать с ImportError при расхождении версий модулей
"""
import os

# Базовая директория проекта: <repo_root>
# Файл находится в <repo_root>/engine/paths.py
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Основные директории (классические имена из проекта) ---
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
BACKUP_DIR = os.path.join(BASE_DIR, "reference", "backup")  # совместимо с VoiceManager
REF_DIR = os.path.join(BASE_DIR, "reference")
MODEL_DIR = os.path.join(BASE_DIR, "models")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LIBRARY_DIR = os.path.join(BASE_DIR, "library")
CACHE_DIR = os.path.join(BASE_DIR, "cache")

# --- Файлы ---
ICON_PATH = os.path.join(BASE_DIR, "icon.ico")
ICON_PNG_PATH = os.path.join(BASE_DIR, "icon.png")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
THEME_SETTINGS_PATH = os.path.join(BASE_DIR, "theme_settings.json")
CHAT_HISTORY_PATH = os.path.join(BASE_DIR, "chat_history.json")
HISTORY_PATH = os.path.join(BASE_DIR, "history.json")
WORD_RULES_PATH = os.path.join(BASE_DIR, "word_rules.json")

# Для обратной совместимости — старые алиасы
VOICE_DIR = REF_DIR
VOICES_DIR = REF_DIR
AUDIO_OUTPUT_DIR = OUTPUT_DIR

# --- Динамический fallback ---
# Если какой-то модуль делает: from engine.paths import SOMETHING_UNKNOWN
# мы не падаем с ImportError, а отдаём разумный путь по умолчанию.
# Это решает рассинхрон версий (например logging_utils → LOG_DIR),
# о котором сообщил пользователь 2026-07-09.
_FALLBACK_MAP = {
    # явные маппинги, если имя неочевидно
    "LOG_DIR": LOG_DIR,
    "LOGS_DIR": LOG_DIR,
    "OUTPUTS_DIR": OUTPUT_DIR,
    "BACKUPS_DIR": BACKUP_DIR,
    "REFERENCE_DIR": REF_DIR,
    "VOICE_BACKUP_DIR": BACKUP_DIR,
    "TEMP_DIR": os.path.join(BASE_DIR, "temp"),
    "TMP_DIR": os.path.join(BASE_DIR, "temp"),
    "CACHE_DIR": CACHE_DIR,
    "MODEL_PATH": MODEL_DIR,
    "MODELS_DIR": MODEL_DIR,
}


def __getattr__(name: str):
    """PEP 562: динамический атрибут модуля.
    Позволяет импортировать любое имя из engine.paths без ImportError.
    """
    # 1. явный fallback
    if name in _FALLBACK_MAP:
        return _FALLBACK_MAP[name]
    # 2. *_DIR → <BASE_DIR>/<name_lower_without__dir>
    if name.endswith("_DIR"):
        sub = name[:-4].lower()
        # частые варианты
        guess = os.path.join(BASE_DIR, sub)
        return guess
    # 3. *_PATH → <BASE_DIR>/<name_lower>.json/.ico ?
    if name.endswith("_PATH"):
        base = name[:-5].lower()
        # пробуем несколько расширений
        for ext in (".json", ".ico", ".png", ".txt", ".log", ""):
            cand = os.path.join(BASE_DIR, base + ext)
            # возвращаем первый вариант, даже если файла нет — вызывающий код
            # обычно сам проверяет существование
            return cand
        return os.path.join(BASE_DIR, base)
    # 4. общий случай — вложенная папка по имени в нижнем регистре
    return os.path.join(BASE_DIR, name.lower())


def __dir__():
    return sorted(
        list(globals().keys())
        + list(_FALLBACK_MAP.keys())
        + [
            "LOG_DIR",
            "REF_DIR",
            "MODEL_DIR",
            "LIBRARY_DIR",
            "CACHE_DIR",
            "SETTINGS_PATH",
            "THEME_SETTINGS_PATH",
            "VOICE_DIR",
            "VOICES_DIR",
            "AUDIO_OUTPUT_DIR",
            "TEMP_DIR",
            "TMP_DIR",
        ]
    )
