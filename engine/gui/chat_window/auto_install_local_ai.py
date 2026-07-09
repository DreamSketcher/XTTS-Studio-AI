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
"""
import threading
import traceback
from typing import Callable, Optional


class LocalAIInstallController:
    """Контроллер установки llama-cpp-python."""

    def __init__(
        self,
        log_cb: Callable[[str], None] = None,
        status_cb: Callable[[str, str], None] = None,
        buttons_cb: Callable[[bool, bool], None] = None,
        error_cb: Callable[[str, str], None] = None,
    ):
        """
        log_cb(line) — новая строка лога.
        status_cb(text, color) — изменить статусную надпись.
        buttons_cb(checking, installing) — заблокировать/разблокировать кнопки.
        error_cb(title, traceback_text) — сообщить об ошибке (например, записать в лог-файл).
        """
        self._log_cb = log_cb or (lambda x: None)
        self._status_cb = status_cb or (lambda t, c: None)
        self._buttons_cb = buttons_cb or (lambda c, i: None)
        self._error_cb = error_cb or (lambda t, m: None)

        self._lock = threading.Lock()
        self._running = False
        self._cancelled = False
        self._thread: Optional[threading.Thread] = None

        # Кэш результатов проверки окружения
        self._cached_resolved: Optional[dict] = None

    # ── Состояние ─────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def request_cancel(self):
        with self._lock:
            if self._running:
                self._cancelled = True
        self._log("Отмена операции...")

    def _start_operation(self) -> bool:
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._cancelled = False
        return True

    def _finish_operation(self):
        with self._lock:
            self._running = False
            self._cancelled = False
        try:
            self._buttons_cb(False, False)
        except Exception:
            pass

    # ── Лог / статус ──────────────────────────────────────────────────────────

    def _log(self, line: str):
        try:
            self._log_cb(line)
        except Exception:
            pass

    def _status(self, text: str, color: str):
        try:
            self._status_cb(text, color)
        except Exception:
            pass

    def _buttons(self, checking: bool = False, installing: bool = False):
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

    # ── Проверка окружения ────────────────────────────────────────────────────

    def get_cached_backend(self) -> Optional[dict]:
        """Возвращает закэшированный результат resolve_backend() или None."""
        return self._cached_resolved

    def resolve_backend(self, force: bool = False) -> dict:
        """Синхронно определяет CPU/GPU/backend. Результат кэшируется."""
        if self._cached_resolved is not None and not force:
            return self._cached_resolved
        from engine import env_setup
        self._cached_resolved = env_setup.resolve_backend()
        return self._cached_resolved

    def check_environment(self):
        """Запускает проверку окружения в фоновом потоке."""
        if not self._start_operation():
            return

        self._buttons(checking=True)
        self._log("── Проверка окружения ──")

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
                gpu_text = f"{gpu['vendor'].upper()} {gpu['name']}" if gpu.get("vendor") != "unknown" else "не обнаружена"
                backend_text = {"cuda": "CUDA", "vulkan": "Vulkan", "cpu": "CPU"}.get(backend, backend)

                self._log(f"CPU: {cpu['name']}")
                self._log(f"GPU: {gpu_text}")
                self._log(f"Инструкции CPU: {flags_str}")
                self._log(f"Выбран backend: {backend_text}")

                if llama_status["installed"]:
                    text = f"CPU: {cpu['name']}\nGPU: {gpu_text}\nИнструкции: {flags_str}\nBackend: {backend_text}\nllama-cpp-python установлен"
                    color = "success"
                    self._log(f"llama-cpp-python найден → {llama_status.get('path', '')}")
                else:
                    text = f"CPU: {cpu['name']}\nGPU: {gpu_text}\nИнструкции: {flags_str}\nBackend: {backend_text}\nllama-cpp-python: {llama_status['error']}"
                    color = "error"
                    self._log(f"llama-cpp-python не найден: {llama_status['error']}")
                    self._log("Диагностика окружения:")
                    self._log(env_setup.format_env_info(env_setup.get_python_env_info()))

                self._status(text, color)
            except Exception as e:
                tb = self._report_error("Ошибка проверки окружения", e)
                self._log(f"Ошибка: {e}")
                self._status(f"Ошибка проверки: {e}", "error")
            finally:
                self._finish_operation()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    # ── Установка / удаление ──────────────────────────────────────────────────

    def list_local_model_files(self) -> list:
        """Список .gguf файлов в models/ — для выбора конкретной модели
        перед установкой ("установить зависимости под выбранную модель")."""
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
        """
        Запускает установку llama-cpp-python в фоновом потоке.
        model_path — явно выбранная пользователем модель (кнопка "установить
        зависимости под выбранную модель"). Если передан, smoke-тест реальной
        GPU-инициализации (внутри env_setup.install_llama_cpp) проверяется
        именно на ней, а не на первой попавшейся в models/. Если не передан —
        универсальный авто-режим, как раньше.
        """
        if not self._start_operation():
            return

        self._buttons(installing=True)
        if model_path:
            import os as _os
            self._log(f"── Установка llama-cpp-python под модель: {_os.path.basename(model_path)} ──")
        else:
            self._log("── Установка llama-cpp-python ──")

        def worker():
            try:
                from engine import env_setup
                env_setup.install_llama_cpp(progress_cb=self._log, resume=resume, model_path=model_path)
                self._status("llama-cpp-python установлен и работает", "success")
                self._log("✅ Установка завершена")
            except Exception as e:
                tb = self._report_error("Ошибка установки llama-cpp-python", e)
                self._log(f"Ошибка установки: {e}")
                self._status("Установка не удалась", "error")
            finally:
                self._finish_operation()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def uninstall(self):
        """Запускает удаление llama-cpp-python в фоновом потоке."""
        if not self._start_operation():
            return

        self._buttons(checking=False, installing=False)
        self._log("── Удаление llama-cpp-python ──")

        def worker():
            try:
                from engine import env_setup
                env_setup.uninstall_llama_cpp(progress_cb=self._log)
                self._status("llama-cpp-python удалён", "error")
            except Exception as e:
                tb = self._report_error("Ошибка удаления llama-cpp-python", e)
                self._log(f"Ошибка удаления: {e}")
                self._status("Ошибка удаления", "error")
            finally:
                self._finish_operation()

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def get_resume_stage(self) -> Optional[str]:
        """Возвращает этап незавершённой установки или None."""
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
        """Есть ли незавершённый чекпоинт установки?"""
        return self.get_resume_stage() is not None

    def cleanup_orphaned_checkpoint(self):
        """Удаляет чекпоинт, если библиотека уже установлена."""
        try:
            from engine import env_setup
            env_setup.cleanup_orphaned_checkpoint()
        except Exception:
            pass

    def describe_startup_state(self) -> str:
        """
        Человекочитаемая строка для показа в UI при открытии окна настроек:
        отвечает на вопрос "прошлая установка реально завершилась, зависла,
        или её вообще не было" — по фактическому состоянию файлов, а не
        только по чекпоинту.
        """
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