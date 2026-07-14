# engine/../test/test_smoke_startup.py
"""
Smoke-тест полной сборки главного окна.

Отличие от остальных unit-тестов: здесь НЕ мокаются внутренние GUI-модули —
цель ровно в том, чтобы поймать класс багов, который unit-тесты с моками
принципиально не видят: потерянные импорты / глобальные переменные / имена
при разбиении файлов (например: `_tts_lock`, `BASE_DIR`, `detect_device`
терялись именно так при прошлых рефакторингах chat_window.py и tts_runner.py).

Тестируем engine.gui.main_window.create_main_window(), а НЕ gui.py:
gui.py при импорте захватывает single-instance mutex (может sys.exit(0),
если уже запущен другой инстанс), переопределяет sys.excepthook и может
открыть реальный сплэш со своим mainloop() — импортировать его в тесте
небезопасно. create_main_window() строит окно, но сама mainloop() не
вызывает — этим управляет уже gui.py.

Требует реального Tk (это так же верно для test_header_panel.py и т.п.) —
тест предназначен для локального запуска на машине разработчика, не для
headless CI без дисплея.
"""
import pytest


@pytest.fixture
def _no_network_autoupdate(monkeypatch):
    """Не даём фоновому потоку проверки обновлений стучаться в сеть во время теста."""
    from engine.gui import env_settings

    monkeypatch.setattr(env_settings, "_auto_check_update", lambda *a, **kw: None, raising=False)


class TestMainWindowSmoke:
    def test_create_main_window_builds_without_exceptions(self, _no_network_autoupdate):
        from engine.gui.main_window import create_main_window

        root = None
        try:
            root = create_main_window(startup_status=None)
        except Exception as e:
            pytest.fail(
                f"create_main_window() упал с исключением — сборка интерфейса "
                f"сломана (возможно, потерян импорт/атрибут при рефакторинге): {e!r}"
            )
        finally:
            # Окно не должно быть видно на экране во время тестового прогона
            try:
                if root is not None:
                    root.withdraw()
            except Exception:
                pass

        assert root is not None
        assert root.winfo_exists()
        assert root.title() == "XTTS Studio"

        # Точечные проверки, что ключевые подмодули реально собрались,
        # а не просто "функция не упала на первой строке"
        from engine.gui import textbox, toolbar, header_panel

        assert textbox.text_box is not None
        assert toolbar.update_gen_btn is not None
        assert header_panel.root is root

        # Уборка: без mainloop() фоновые root.after(...) коллбэки (прогрев
        # модели, автопроверка обновлений) не выполнятся — можно просто
        # уничтожить окно.
        try:
            root.destroy()
        except Exception:
            pass
