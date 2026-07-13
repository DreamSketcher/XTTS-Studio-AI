"""
engine/gui/chat_window/auto_install_local_ai.py

"Мозги" автоматической установки локального ИИ (llama-cpp-python).
Отвечает за:
  - проверку CPU/GPU и выбор backend;
  - установку/удаление llama-cpp-python в фоновом потоке;
  - буферизацию лога и управление процессом;
  - callback-уведомления для UI.

Без зависимости от tkinter — чистая логика, которую можно тестировать
и вызывать из любого UI.

PATCH: shared singleton + ring-buffer лога, чтобы при rebuild страницы
настроек (show_page / _invalidate_page) прогресс проверки/установки
НЕ сбрасывался. UI только переподписывается на callbacks.
"""

from __future__ import annotations

import re
import threading
import traceback
from typing import Callable, Optional, List


# ── Shared process state (живёт, пока жив процесс Python) ──────────────────
_SHARED_LOCK = threading.Lock()
_SHARED = {
    "controller": None,
    "log_lines": [],
    "status_text": "",
    "status_color": "dim",
    "checking": False,
    "installing": False,
    "op_kind": None,
    "max_log_lines": 5000,
}

# «Файлы не менялись…» во время check/init — ложный сигнал зависания.
_STALE_FILE_RE = re.compile(
    r"файл(ы|ов)?\s+не\s+менял|files?\s+(have\s+)?not\s+changed|\bstale\b|завис",
    re.IGNORECASE,
)


def get_shared_state() -> dict:
    """Снимок shared-state для UI (копии коллекций)."""
    with _SHARED_LOCK:
        ctrl = _SHARED["controller"]
        running = bool(ctrl is not None and ctrl.is_running())
        return {
            "log_lines": list(_SHARED["log_lines"]),
            "status_text": _SHARED["status_text"],
            "status_color": _SHARED["status_color"],
            "checking": bool(_SHARED["checking"]),
            "installing": bool(_SHARED["installing"]),
            "op_kind": _SHARED["op_kind"],
            "running": running,
        }


def clear_shared_log():
    with _SHARED_LOCK:
        _SHARED["log_lines"] = []


def _shared_append_log(line: str):
    with _SHARED_LOCK:
        lines = _SHARED["log_lines"]
        lines.append(line)
        max_n = int(_SHARED["max_log_lines"])
        if len(lines) > max_n:
            del lines[: len(lines) - max_n]


def _shared_set_status(text: str, color: str):
    with _SHARED_LOCK:
        _SHARED["status_text"] = text
        _SHARED["status_color"] = color


def _shared_set_buttons(checking: bool, installing: bool):
    with _SHARED_LOCK:
        _SHARED["checking"] = bool(checking)
        _SHARED["installing"] = bool(installing)


def _filter_progress_line(line: str, op_kind: Optional[str]) -> Optional[str]:
    """Переписывает/глушит вводящие в заблуждение progress-строки.

    None — не показывать; str — показать (возможно переписанную).
    """
    if not line:
        return line
    raw = line[1:] if line.startswith("\r") else line
    if _STALE_FILE_RE.search(raw):
        # check / init: файлы install-dir не обязаны меняться
        if op_kind in ("check", None):
            return None
        m = re.search(r"(\d+)\s*сек", raw)
        secs = m.group(1) if m else "?"
        return (
            f"ℹ️ Нет изменений файлов в каталоге сборки уже {secs} сек — "
            f"это нормально на этапах configure/compile/import. "
            f"Ждём вывод процесса…"
        )
    return line


class LocalAIInstallController:
    """Контроллер установки llama-cpp-python.

    Используйте get_or_create_controller() из UI, чтобы не терять
    прогресс при перестроении страницы настроек.
    """

    def __init__(
        self,
        log_cb: Callable[[str], None] = None,
        status_cb: Callable[[str, str], None] = None,
        buttons_cb: Callable[[bool, bool], None] = None,
        error_cb: Callable[[str, str], None] = None,
    ):
        self._log_cb = log_cb or (lambda x: None)
        self._status_cb = status_cb or (lambda t, c: None)
        self._buttons_cb = buttons_cb or (lambda c, i: None)
        self._error_cb = error_cb or (lambda t, m: None)

        self._lock = threading.Lock()
        self._running = False
        self._cancelled = False
        self._thread: Optional[threading.Thread] = None
        self._op_kind: Optional[str] = None
        self._cached_resolved: Optional[dict] = None

    def bind_ui(
        self,
        log_cb: Callable[[str], None] = None,
        status_cb: Callable[[str, str], None] = None,
        buttons_cb: Callable[[bool, bool], None] = None,
        error_cb: Callable[[str, str], None] = None,
        replace: bool = True,
    ):
        """Переподписать UI-колбэки (после destroy/rebuild страницы local)."""
        if log_cb is not None:
            self._log_cb = log_cb
        if status_cb is not None:
            self._status_cb = status_cb
        if buttons_cb is not None:
            self._buttons_cb = buttons_cb
        if error_cb is not None:
            self._error_cb = error_cb

    def replay_to_ui(self):
        """Проиграть буфер лога + статус + кнопки в только что привязанный UI."""
        st = get_shared_state()
        try:
            self._status_cb(st["status_text"] or "", st["status_color"] or "dim")
        except Exception:
            pass
        try:
            self._buttons_cb(st["checking"], st["installing"])
        except Exception:
            pass
        for line in st["log_lines"]:
            try:
                self._log_cb(line)
            except Exception:
                pass

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def current_op(self) -> Optional[str]:
        with self._lock:
            return self._op_kind

    def request_cancel(self):
        with self._lock:
            if self._running:
                self._cancelled = True
        self._log("Отмена операции...")

    def _start_operation(self, kind: str) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._cancelled = False
            self._op_kind = kind
        with _SHARED_LOCK:
            _SHARED["op_kind"] = kind
        return True

    def _finish_operation(self):
        with self._lock:
            self._running = False
            self._cancelled = False
            self._op_kind = None
        with _SHARED_LOCK:
            _SHARED["op_kind"] = None
            _SHARED["checking"] = False
            _SHARED["installing"] = False
        try:
            self._buttons_cb(False, False)
        except Exception:
            pass

    def _log(self, line: str):
        with self._lock:
            op = self._op_kind
        filtered = _filter_progress_line(line, op)
        if filtered is None:
            return
        store = filtered[1:] if filtered.startswith("\r") else filtered
        _shared_append_log(store)
        try:
            self._log_cb(filtered)
        except Exception:
            pass

    def _status(self, text: str, color: str):
        _shared_set_status(text, color)
        try:
            self._status_cb(text, color)
        except Exception:
            pass

    def _buttons(self, checking: bool = False, installing: bool = False):
        _shared_set_buttons(checking, installing)
        try:
            self._buttons_cb(checking, installing)
        except Exception:
            pass

    def _report_error(self, title: str, exc: Exception):
        tb = traceback.format_exc()
        try:
            self._error_cb(title, tb)
        except Exception:
            pass
        return tb

    def get_cached_backend(self) -> Optional[dict]:
        return self._cached_resolved

    def resolve_backend(self, force: bool = False) -> dict:
        if self._cached_resolved is not None and not force:
            return self._cached_resolved
        from engine import env_setup

        self._cached_resolved = env_setup.resolve_backend()
        return self._cached_resolved

    def check_environment(self):
        if not self._start_operation("check"):
            self._log("⏳ Уже выполняется другая операция — дождитесь окончания.")
            return

        self._buttons(checking=True)
        self._log("── Проверка окружения ──")
        self._status("Идёт проверка окружения…", "dim")

        def worker():
            try:
                from engine import env_setup

                resolved = self.resolve_backend(force=True)
                cpu = resolved["cpu"]
                gpu = resolved["gpu"]
                backend = resolved["backend"]
                llama_status = env_setup.llama_cpp_status()

                flags = [f for f in ("avx", "avx2", "fma", "f16c") if cpu.get(f)]
                flags_str = ", ".join(flags) if flags else "базовый набор"
                gpu_text = (
                    f"{gpu['vendor'].upper()} {gpu['name']}"
                    if gpu.get("vendor") != "unknown"
                    else "не обнаружена"
                )
                backend_text = {"cuda": "CUDA", "vulkan": "Vulkan", "cpu": "CPU"}.get(
                    backend, backend
                )

                self._log(f"CPU: {cpu['name']}")
                self._log(f"GPU: {gpu_text}")
                self._log(f"Инструкции CPU: {flags_str}")
                self._log(f"Выбран backend: {backend_text}")

                if llama_status["installed"]:
                    text = (
                        f"CPU: {cpu['name']}\n"
                        f"GPU: {gpu_text}\n"
                        f"Инструкции: {flags_str}\n"
                        f"Backend: {backend_text}\n"
                        f"llama-cpp-python установлен"
                    )
                    color = "success"
                    self._log(f"llama-cpp-python найден → {llama_status.get('path', '')}")
                else:
                    text = (
                        f"CPU: {cpu['name']}\n"
                        f"GPU: {gpu_text}\n"
                        f"Инструкции: {flags_str}\n"
                        f"Backend: {backend_text}\n"
                        f"llama-cpp-python: {llama_status['error']}"
                    )
                    color = "error"
                    self._log(f"llama-cpp-python не найден: {llama_status['error']}")
                    self._log("Диагностика окружения:")
                    self._log(env_setup.format_env_info(env_setup.get_python_env_info()))

                self._status(text, color)
            except Exception as e:
                self._report_error("Ошибка проверки окружения", e)
                self._log(f"Ошибка: {e}")
                self._status(f"Ошибка проверки: {e}", "error")
            finally:
                self._finish_operation()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def list_local_model_files(self) -> list:
        try:
            from engine import env_setup
            import os as _os

            models_dir = _os.path.join(env_setup.BASE_DIR, "models")
            if not _os.path.isdir(models_dir):
                return []
            return sorted(f for f in _os.listdir(models_dir) if f.lower().endswith(".gguf"))
        except Exception:
            return []

    def install(self, resume: bool = False, model_path: Optional[str] = None):
        if not self._start_operation("install"):
            self._log("⏳ Уже выполняется другая операция — дождитесь окончания.")
            return

        self._buttons(installing=True)
        if model_path:
            import os as _os

            self._log(
                f"── Установка llama-cpp-python под модель: {_os.path.basename(model_path)} ──"
            )
        else:
            self._log("── Установка llama-cpp-python ──")
        self._status("Установка зависимостей…", "dim")

        def worker():
            try:
                from engine import env_setup

                env_setup.install_llama_cpp(
                    progress_cb=self._log, resume=resume, model_path=model_path
                )
                self._status("llama-cpp-python установлен и работает", "success")
                self._log("✅ Установка завершена")
            except Exception as e:
                self._report_error("Ошибка установки llama-cpp-python", e)
                self._log(f"Ошибка установки: {e}")
                self._status("Установка не удалась", "error")
            finally:
                self._finish_operation()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def uninstall(self):
        if not self._start_operation("uninstall"):
            self._log("⏳ Уже выполняется другая операция — дождитесь окончания.")
            return

        self._buttons(checking=False, installing=True)
        self._log("── Удаление llama-cpp-python ──")
        self._status("Удаление llama-cpp-python…", "dim")

        def worker():
            try:
                from engine import env_setup

                env_setup.uninstall_llama_cpp(progress_cb=self._log)
                self._status("llama-cpp-python удалён", "error")
            except Exception as e:
                self._report_error("Ошибка удаления llama-cpp-python", e)
                self._log(f"Ошибка удаления: {e}")
                self._status("Ошибка удаления", "error")
            finally:
                self._finish_operation()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def get_resume_stage(self) -> Optional[str]:
        try:
            from engine import env_setup

            checkpoint = env_setup._load_checkpoint()
            stage = checkpoint.get("stage")
            if stage and stage not in (None, "", "done"):
                return stage
        except Exception:
            pass
        return None

    def has_resume_checkpoint(self) -> bool:
        return self.get_resume_stage() is not None

    def cleanup_orphaned_checkpoint(self):
        try:
            from engine import env_setup

            env_setup.cleanup_orphaned_checkpoint()
        except Exception:
            pass

    def describe_startup_state(self) -> str:
        try:
            from engine import env_setup

            info = env_setup.get_startup_install_state()
        except Exception as e:
            return f"Не удалось проверить состояние установки: {e}"

        state = info.get("state")
        if state == "clean":
            return "Незавершённых установок не обнаружено."
        if state == "installed":
            return f"llama-cpp-python установлен и работает ({info.get('path', '')})."
        if state == "interrupted":
            age = info.get("age_seconds")
            age_text = f"{int(age // 60)} мин назад" if age is not None else "неизвестно когда"
            files = info.get("target_dir_files", 0)
            return (
                f"Обнаружена прерванная установка (этап: {info.get('stage')}, "
                f"последнее изменение чекпоинта: {age_text}, файлов в целевой папке: {files}). "
                f"Можно продолжить (Resume) или начать заново."
            )
        return "Не удалось определить состояние установки."


def get_or_create_controller(**ui_cbs) -> LocalAIInstallController:
    """Singleton-контроллер: один процесс — один контроллер.

    UI при rebuild страницы вызывает get_or_create_controller(...)
    и затем controller.replay_to_ui(), чтобы восстановить лог/статус/кнопки.
    """
    with _SHARED_LOCK:
        ctrl = _SHARED["controller"]
        if ctrl is None:
            ctrl = LocalAIInstallController()
            _SHARED["controller"] = ctrl
    if ui_cbs:
        ctrl.bind_ui(
            log_cb=ui_cbs.get("log_cb"),
            status_cb=ui_cbs.get("status_cb"),
            buttons_cb=ui_cbs.get("buttons_cb"),
            error_cb=ui_cbs.get("error_cb"),
            replace=True,
        )
    return ctrl
