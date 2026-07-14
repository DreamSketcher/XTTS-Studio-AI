import queue
import threading
import traceback

from engine.tts_runner import run_tts


# Служебный маркер для мгновенной разблокировки q.get() в _loop() при stop().
# Никогда не попадает в get_queue()/UI — фильтруется явно.
_STOP_SENTINEL = object()


class TaskManager:
    def __init__(self, ui_callback=None):
        self.q = queue.Queue()
        self.current_task = None
        self.running = False
        self.ui_callback = ui_callback
        self._thread = None

    # =========================
    # ДОБАВИТЬ ЗАДАЧУ В ОЧЕРЕДЬ
    # =========================
    def add_task(self, task):
        self.q.put(task)
        self._notify(task)
        if self.ui_callback:
            self.ui_callback({"stage": "queue_update"})
        if not self.running:
            self.start()

    # =========================
    # ПОЛУЧИТЬ ОЧЕРЕДЬ ДЛЯ UI
    # =========================
    def get_queue(self):
        result = []
        if self.current_task is not None:
            result.append(self.current_task)
        result.extend(t for t in list(self.q.queue) if t is not _STOP_SENTINEL)
        return result

    # =========================
    # ОТМЕНА ЗАДАЧИ
    # =========================
    def cancel_task(self, task_id):
        # текущая задача — помечаем флагом; run_tts проверит его сам
        if self.current_task and self.current_task.id == task_id:
            self.current_task.cancelled = True
            return

        # задача ещё в очереди — помечаем и уведомляем GUI
        for task in list(self.q.queue):
            if task is _STOP_SENTINEL:
                continue
            if task.id == task_id:
                task.cancelled = True
                task.status = "cancelled"
                self._notify(task)
                return

    # =========================
    # ЗАПУСК WORKER-ПОТОКА
    # =========================
    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # =========================
    # ОСТАНОВКА WORKER-ПОТОКА (критично при закрытии приложения!)
    # =========================
    def stop(self, wait=True, timeout=5.0):
        """Останавливает воркер-поток осознанно, а не полагается на то,
        что daemon-поток сам умрёт вместе с процессом.

        - помечает текущую (уже выполняющуюся) задачу отменённой — run_tts
          сам проверяет is_cancelled() и должен прерваться на ближайшей
          внутренней проверке;
        - вычищает и отменяет все ещё не начатые задачи из очереди —
          при закрытии приложения запускать их незачем;
        - кладёт служебный sentinel, чтобы разблокировать q.get(), если
          поток сейчас простаивает в ожидании новых задач;
        - если wait=True, дожидается фактического завершения потока
          (join с таймаутом), чтобы вызывающий код мог быть уверен, что
          воркер реально остановился, а не просто "помечен как остановленный".
        """
        if not self.running:
            return
        self.running = False

        if self.current_task is not None:
            self.current_task.cancelled = True

        drained = []
        try:
            while True:
                item = self.q.get_nowait()
                if item is _STOP_SENTINEL:
                    continue
                drained.append(item)
        except queue.Empty:
            pass
        for task in drained:
            task.cancelled = True
            task.status = "cancelled"
            self._notify(task)

        # Разблокируем q.get() в _loop, если поток сейчас простаивает
        self.q.put(_STOP_SENTINEL)

        thread = self._thread
        if wait and thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    # =========================
    # ОБРАБОТКА ОЧЕРЕДИ
    # =========================
    def _loop(self):
        while self.running:
            task = self.q.get()

            if task is _STOP_SENTINEL:
                self.q.task_done()
                break

            self.current_task = task

            # задача отменена до старта
            if getattr(task, "cancelled", False):
                task.status = "cancelled"
                self._notify(task)
                self.q.task_done()
                continue

            try:
                task.status = "running"
                task.progress = 5
                self._notify(task)

                output = run_tts(
                    text=task.text,
                    raw_text=getattr(task, "raw_text", task.text),
                    ref_path=task.voice,
                    status_callback=self._make_progress_cb(task),
                    # ← передаём лямбду-проверку флага отмены
                    is_cancelled=lambda: getattr(task, "cancelled", False),
                    speed=getattr(task, "speed", 1.0),
                    language=getattr(task, "language", "auto"),
                    quality=getattr(task, "quality", "Баланс"),
                    quality_params=getattr(task, "quality_params", None),
                )

                # run_tts вернул None — значит была отмена изнутри
                if output is None or getattr(task, "cancelled", False):
                    task.status = "cancelled"
                    task.progress = 0
                else:
                    task.output_path = output
                    task.status = "done"
                    task.progress = 100

            except Exception:
                task.status = "error"
                task.error = traceback.format_exc()

            self._notify(task)
            self.q.task_done()

        self.current_task = None

    # =========================
    # КОЛБЭК ПРОГРЕССА
    # =========================
    def _make_progress_cb(self, task):
        def callback(data):
            if getattr(task, "cancelled", False):
                return

            if isinstance(data, dict):
                if data.get("stage") == "chunk":
                    if self.ui_callback:
                        self.ui_callback(data)
                    return

                if data.get("stage") == "normalized_text":
                    if self.ui_callback:
                        self.ui_callback(data)
                    return

                if data.get("stage") == "check_textbox_ready":
                    if self.ui_callback:
                        return self.ui_callback(data)
                    return False

                # ↓ ДОБАВИТЬ ЭТИ ДВА БЛОКА
                if data.get("stage") == "ai_conductor_on":
                    if self.ui_callback:
                        self.ui_callback(data)
                    return

                if data.get("stage") == "ai_conductor_off":
                    if self.ui_callback:
                        self.ui_callback(data)
                    return
                # ↑ КОНЕЦ ДОБАВЛЕНИЯ

                if data.get("stage"):
                    task.status = data["stage"]
                if data.get("progress") is not None:
                    task.progress = int(data["progress"])
                if data.get("final"):
                    task.output_path = data["final"]
                    task.status = "done"
                    task.progress = 100
                if data.get("stage") == "stats":
                    task.stats = data
                self._notify(task)

        return callback

    # =========================
    # УВЕДОМЛЕНИЕ GUI
    # =========================
    def _notify(self, task=None):
        if self.ui_callback:
            self.ui_callback(task)
