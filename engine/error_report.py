"""
error_report.py

Отправка отчётов об ошибках пользователем через предзаполненный GitHub Issue.
Никаких токенов и секретов на клиенте — просто открывается браузер
с уже готовым issue, юзер сам решает, отправлять или нет.
"""

import os
import re
import getpass
import platform
import traceback
import webbrowser
from urllib.parse import quote

# ==== НАСТРОЙ ПОД СЕБЯ ====
GITHUB_OWNER = "DreamSketcher"
GITHUB_REPO = "XTTS-Studio-portable-"
ISSUE_LABELS = "bug,auto-report"        # необязательно, можно убрать
# ===========================

MAX_BODY_LEN = 7000  # GitHub режет длинные query-параметры, оставляем запас


def _sanitize(text: str) -> str:
    """Убирает потенциально приватные данные из лога перед отправкой."""
    if not text:
        return text

    username = getpass.getuser()
    if username:
        # Windows-пути вида C:\Users\Vinnipoh\... -> C:\Users\<user>\...
        text = re.sub(
            re.escape(username), "<user>", text, flags=re.IGNORECASE
        )

    # Общий паттерн на случай если getpass не сработал (иногда бывает под GUI)
    text = re.sub(r"([Uu]sers)\\[^\\]+\\", r"\1\\<user>\\", text)
    text = re.sub(r"(/home/)[^/]+/", r"\1<user>/", text)

    # На всякий случай — email-подобные строки и IPv4
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", text)
    text = re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "<ip>", text)

    return text


def _truncate(text: str, limit: int = MAX_BODY_LEN) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2:]
    return f"{head}\n\n... [лог обрезан, слишком длинный] ...\n\n{tail}"


def build_issue_url(
    title: str,
    log_text: str,
    app_version: str = "unknown",
    extra_context: str = "",
) -> str:
    """Формирует URL для создания GitHub issue с предзаполненными полями."""

    safe_log = _sanitize(log_text)
    safe_log = _truncate(safe_log)

    body_parts = [
        "### Автоматический отчёт об ошибке",
        "",
        f"**Версия приложения:** {app_version}",
        f"**ОС:** {platform.platform()}",
        f"**Python:** {platform.python_version()}",
    ]
    if extra_context:
        body_parts += ["", "**Контекст:**", extra_context]

    body_parts += [
        "",
        "**Лог:**",
        "```",
        safe_log,
        "```",
        "",
        "_Пользователь может отредактировать или удалить любую часть перед отправкой._",
    ]

    body = "\n".join(body_parts)

    url = (
        f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/issues/new"
        f"?title={quote(title)}"
        f"&body={quote(body)}"
    )
    if ISSUE_LABELS:
        url += f"&labels={quote(ISSUE_LABELS)}"

    return url


def send_error_report(
    log_text: str,
    title: str = "Автоматический отчёт об ошибке",
    app_version: str = "unknown",
    extra_context: str = "",
) -> bool:
    """
    Открывает браузер с предзаполненным issue.
    Возвращает True если браузер удалось открыть, False при ошибке.
    """
    try:
        url = build_issue_url(title, log_text, app_version, extra_context)
        webbrowser.open(url)
        return True
    except Exception:
        return False


def report_exception(exc: BaseException, app_version: str = "unknown") -> bool:
    """Удобная обёртка: собрать traceback из исключения и отправить."""
    tb_text = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    title = f"Ошибка: {type(exc).__name__}: {str(exc)[:80]}"
    return send_error_report(tb_text, title=title, app_version=app_version)


if __name__ == "__main__":
    # Быстрый тест
    try:
        1 / 0
    except Exception as e:
        ok = report_exception(e, app_version="1.0.0-test")
        print("Открыт браузер:" , ok)
