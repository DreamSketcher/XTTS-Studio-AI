"""engine/cpml_consent.py — явное согласие пользователя с Coqui Public Model License (CPML).

Единая точка истины для файла согласия ``json/cpml_consent.json`` (именно так
называет его экран согласия при старте и эта документация). Вынесено из
``engine/tts/__init__.py`` в отдельный модуль без тяжёлых зависимостей
(только stdlib), чтобы:

1. Экран согласия при старте (``gui.py``) и обработчик ошибки генерации
   (``engine/gui/generation.py``) работали даже когда torch/TTS недоступны
   или повреждены. Раньше они делали ``from engine.tts import
   is_coqui_tos_agreed, ...`` — при сбое импорта экран согласия молча
   пропускался, а генерация падала с ``CoquiTosNotAgreedError``
   (issue #4: «I cannot find a visible Coqui license acceptance control»).
2. Логику согласия можно было покрыть unit-тестами без torch/TTS.

Переменная окружения ``COQUI_TOS_AGREED``: если пользователь ЯВНО выставил
её в «1» (как велит документация Coqui TTS), это считается согласием.
Раньше приложение молча игнорировало эту переменную, из-за чего шаги 7–8
из issue #4 (Windows env var / ``set COQUI_TOS_AGREED=1`` + restart)
не помогали. Согласие, полученное из переменной окружения, дополнительно
фиксируется в файле (best-effort) с ``source: "env:COQUI_TOS_AGREED"``,
чтобы состояние было прозрачно видно в ``json/cpml_consent.json``.

Путь к файлу согласия можно переопределить переменной окружения
``XTTS_CPML_CONSENT_PATH`` (используется тестами и портативными сборками).
"""

import contextlib
import json
import os
import sys
import time

CPML_URL = "https://coqui.ai/cpml"


class CoquiTosNotAgreedError(RuntimeError):
    """Пользователь ещё не подтвердил согласие с CPML."""


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cpml_consent_path() -> str:
    """Путь к файлу согласия (json/cpml_consent.json рядом с приложением)."""
    override = os.environ.get("XTTS_CPML_CONSENT_PATH")
    if override:
        return override
    return os.path.join(_base_dir(), "json", "cpml_consent.json")


def _env_agreed() -> bool:
    """True, только если пользователь явно выставил COQUI_TOS_AGREED в true-подобное значение."""
    return os.environ.get("COQUI_TOS_AGREED", "").strip().lower() in ("1", "true", "yes", "on")


def _file_agreed() -> bool:
    """True, только если файл согласия существует, читаем и содержит agreed=true."""
    try:
        with open(cpml_consent_path(), encoding="utf-8") as f:
            record = json.load(f)
        return bool(isinstance(record, dict) and record.get("agreed"))
    except Exception:
        return False


def is_coqui_tos_agreed() -> bool:
    """Было ли явное согласие с CPML зафиксировано ранее (файл или переменная окружения)."""
    return _file_agreed() or _env_agreed()


def set_coqui_tos_agreed(source: str = "user-confirmed") -> None:
    """
    Фиксирует явное согласие пользователя с CPML (https://coqui.ai/cpml)
    и включает переменную окружения, которую ожидает библиотека TTS.
    Вызывать только ПОСЛЕ того, как пользователь реально увидел текст/ссылку
    на лицензию и подтвердил согласие — не по умолчанию при импорте модуля.

    Бросает исключение, если файл согласия не удалось записать (например,
    папка приложения недоступна на запись) — вызывающий код обязан показать
    пользователю видимое сообщение об этом.
    """
    record = {
        "agreed": True,
        "source": str(source or "user-confirmed"),
        "confirmed_at": int(time.time()),
    }
    dest = cpml_consent_path()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    os.replace(tmp, dest)
    os.environ["COQUI_TOS_AGREED"] = "1"


def ensure_coqui_tos_agreed() -> None:
    """
    Вызывается перед первой загрузкой модели (см. get_tts()). Если согласие
    уже было явно дано — в файле или через явно выставленную пользователем
    переменную окружения COQUI_TOS_AGREED=1 — тихо выставляет переменную
    окружения и продолжает. Если нет — поднимает CoquiTosNotAgreedError,
    чтобы вызывающий (GUI) показал пользователю реальный экран согласия
    с CPML и вызвал set_coqui_tos_agreed() сам.
    """
    if is_coqui_tos_agreed():
        os.environ["COQUI_TOS_AGREED"] = "1"
        if not _file_agreed():
            # Согласие получено из переменной окружения — фиксируем его
            # в файле (best-effort), чтобы состояние было прозрачным и
            # не зависело от того, выставлена ли переменная в конкретном
            # способе запуска (ярлык / cmd / планировщик).
            with contextlib.suppress(Exception):
                set_coqui_tos_agreed("env:COQUI_TOS_AGREED")
        return
    raise CoquiTosNotAgreedError(
        "CoquiTosNotAgreedError: пользователь ещё не подтвердил согласие с Coqui "
        "Public Model License (CPML, https://coqui.ai/cpml).\n"
        "Как исправить: запустите приложение заново и нажмите «Согласен, продолжить» "
        "на экране согласия, который появляется при первом запуске после установки, "
        "ИЛИ выставите переменную окружения COQUI_TOS_AGREED=1 и перезапустите "
        "приложение, ИЛИ удалите файл json/cpml_consent.json и запустите приложение "
        "снова, чтобы увидеть экран согласия.\n"
        "User has not consented to the Coqui Public Model License (CPML, "
        "https://coqui.ai/cpml). Restart the app and accept the consent screen "
        "shown on first launch, or set the COQUI_TOS_AGREED=1 environment variable "
        "and restart, or delete json/cpml_consent.json and start the app again to "
        "see the consent screen."
    )
