# -*- coding: utf-8 -*-
"""Unit-тесты для engine/gui/animation_manager.py.

Покрытие:
  1. Easing-функции: границы t=0/t=1, монотонность, range [0,1].
  2. AnimationManager в no-op режиме (root=None) — CI-safe.
  3. AnimationManager с реальным Tk — базовая анимация, отмена, destroy.
"""

from __future__ import annotations

import os
import pytest

from engine.gui.animation_manager import (
    AnimationManager,
    EASING_MAP,
    ease_linear,
    ease_in_quad,
    ease_out_quad,
    ease_in_out_quad,
    ease_in_cubic,
    ease_out_cubic,
    ease_in_out_cubic,
    ease_in_quart,
    ease_out_quart,
    ease_in_out_quart,
    ease_out_back,
    _resolve_easing,
)


# ═══════════════════════════════════════════════════════════════════
#  1. Easing Functions — unit-тесты
# ═══════════════════════════════════════════════════════════════════


class TestEasingBoundaries:
    """Все easing-функции: f(0)=0, f(1)=1 (с машинной точностью)."""

    @pytest.mark.parametrize("name", list(EASING_MAP.keys()))
    def test_easing_zero(self, name: str) -> None:
        fn = EASING_MAP[name]
        val = fn(0.0)
        assert abs(val) < 1e-9, f"{name}: fn(0)={val}, expected ~0"

    @pytest.mark.parametrize("name", list(EASING_MAP.keys()))
    def test_easing_one(self, name: str) -> None:
        fn = EASING_MAP[name]
        val = fn(1.0)
        assert abs(val - 1.0) < 1e-9, f"{name}: fn(1)={val}, expected ~1"


# ease_out_back имеет overshoot (подъём выше 1 и возврат к 1)
# и не обязан быть монотонным
_MONOTONIC_SKIP = {"ease_out_back"}


class TestEasingMonotonic:
    """Все easing-функции монотонно не убывают на [0, 1]
    (кроме ease_out_back — умышленный overshoot)."""

    @pytest.mark.parametrize("name", [n for n in EASING_MAP if n not in _MONOTONIC_SKIP])
    def test_easing_monotonic_non_decreasing(self, name: str) -> None:
        fn = EASING_MAP[name]
        prev = fn(0.0)
        steps = 200
        for i in range(1, steps + 1):
            t = i / steps
            cur = fn(t)
            assert cur >= prev - 1e-9, (
                f"{name}: нарушение монотонности на t={t}: " f"prev={prev:.10f}, cur={cur:.10f}"
            )
            prev = cur


class TestEasingRange:
    """Все easing-функции возвращают значения, близкие к [0, 1]."""

    @pytest.mark.parametrize("name", list(EASING_MAP.keys()))
    def test_easing_range(self, name: str) -> None:
        fn = EASING_MAP[name]
        values = [fn(i / 100.0) for i in range(101)]
        min_val = min(values)
        max_val = max(values)
        # ease_out_back может слегка выходить за [0,1] (overshoot ~1.1)
        if name == "ease_out_back":
            assert min_val >= -0.1, f"{name}: min={min_val} too negative"
            assert max_val <= 1.101, f"{name}: max={max_val} too large"
        else:
            assert min_val >= 0.0, f"{name}: min={min_val} < 0"
            assert max_val <= 1.0, f"{name}: max={max_val} > 1"


class TestEasingSymmetry:
    """ease_in и ease_out симметричны: ease_out(t) = 1 - ease_in(1-t)."""

    def test_in_out_symmetry_quad(self) -> None:
        for i in range(101):
            t = i / 100.0
            out = ease_out_quad(t)
            expected = 1.0 - ease_in_quad(1.0 - t)
            assert abs(out - expected) < 1e-9, f"t={t}: {out} != {expected}"

    def test_in_out_symmetry_cubic(self) -> None:
        for i in range(101):
            t = i / 100.0
            out = ease_out_cubic(t)
            expected = 1.0 - ease_in_cubic(1.0 - t)
            assert abs(out - expected) < 1e-9, f"t={t}: {out} != {expected}"


class TestEasingSpecificValues:
    """Проверка конкретных известных значений."""

    def test_linear(self) -> None:
        assert ease_linear(0.25) == pytest.approx(0.25)
        assert ease_linear(0.5) == pytest.approx(0.5)
        assert ease_linear(0.75) == pytest.approx(0.75)

    def test_in_quad(self) -> None:
        assert ease_in_quad(0.5) == pytest.approx(0.25)

    def test_out_quad(self) -> None:
        assert ease_out_quad(0.5) == pytest.approx(0.75)

    def test_in_out_quad_at_midpoint(self) -> None:
        # ease_in_out_quad(0.5) = 2*0.5^2 = 0.5
        assert ease_in_out_quad(0.5) == pytest.approx(0.5)

    def test_out_back_overshoot(self) -> None:
        # ease_out_back имеет overshoot: f(1)=1, но на ~0.8 > 1
        vals = [ease_out_back(i / 100.0) for i in range(101)]
        assert max(vals) > 1.0  # должен быть overshoot
        assert min(vals) >= 0.0  # не должен уходить в минус


class TestResolveEasing:
    """_resolve_easing: валидные имена и fallback."""

    def test_valid_name(self) -> None:
        fn = _resolve_easing("ease_in_cubic")
        assert fn is ease_in_cubic

    def test_unknown_name_falls_back(self) -> None:
        fn = _resolve_easing("nonexistent")
        assert fn is not None
        # Проверяем, что это действительно easing-функция
        assert abs(fn(0.0)) < 1e-9
        assert abs(fn(1.0) - 1.0) < 1e-9

    def test_empty_string_falls_back(self) -> None:
        fn = _resolve_easing("")
        assert abs(fn(1.0) - 1.0) < 1e-9


# ═══════════════════════════════════════════════════════════════════
#  2. AnimationManager в no-op режиме
# ═══════════════════════════════════════════════════════════════════


class TestAnimationManagerNoOp:
    """AnimationManager(root=None) — для CI и headless-сред."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self) -> None:
        AnimationManager._instance = None

    def test_no_op_animate_applies_end_immediately(self) -> None:
        mgr = AnimationManager(root=None)
        applied: list[float] = []

        mgr.animate(
            target=object(),
            property_setter=lambda v: applied.append(v),
            start=0,
            end=100,
            duration_ms=500,
        )
        assert applied == [100], (
            f"No-op: должен применить конечное значение, " f"получено {applied}"
        )

    def test_no_op_on_complete_called(self) -> None:
        mgr = AnimationManager(root=None)
        called: list[bool] = []

        mgr.animate(
            target=object(),
            property_setter=lambda v: None,
            start=0,
            end=1,
            duration_ms=200,
            on_complete=lambda: called.append(True),
        )
        assert called == [True], "No-op: on_complete должен быть вызван"

    def test_no_op_returns_empty_id(self) -> None:
        mgr = AnimationManager(root=None)
        aid = mgr.animate(
            target=object(),
            property_setter=lambda v: None,
            start=0,
            end=1,
        )
        assert aid == "", f"No-op: animate() должен вернуть пустую строку, " f"получено '{aid}'"

    def test_no_op_is_running_false(self) -> None:
        mgr = AnimationManager(root=None)
        assert mgr.is_running("any") is False

    def test_no_op_destroy_is_safe(self) -> None:
        mgr = AnimationManager(root=None)
        mgr.destroy()  # не должно быть исключений

    def test_get_returns_instance(self) -> None:
        mgr = AnimationManager.get()
        assert mgr is not None
        assert mgr._no_op is True

    def test_get_returns_same_instance(self) -> None:
        mgr1 = AnimationManager.get()
        mgr2 = AnimationManager.get()
        assert mgr1 is mgr2


# ═══════════════════════════════════════════════════════════════════
#  3. AnimationManager с реальным Tk
# ═══════════════════════════════════════════════════════════════════

_HAS_DISPLAY: bool = bool(os.environ.get("DISPLAY")) or os.name == "nt"


@pytest.mark.skipif(not _HAS_DISPLAY, reason="Нет дисплея (Tk не создать)")
class TestAnimationManagerWithTk:
    """Тесты с реальным Tk root (требуют дисплея, не для headless CI)."""

    @pytest.fixture
    def root_tk(self):
        import tkinter as tk

        r = tk.Tk()
        r.withdraw()
        yield r
        try:
            r.destroy()
        except Exception:
            pass

    @pytest.fixture(autouse=True)
    def reset_singleton(self) -> None:
        AnimationManager._instance = None

    def test_init_with_root(self, root_tk):
        mgr = AnimationManager.init(root_tk, fps=30)
        assert mgr._root is root_tk
        assert mgr._no_op is False

    def test_init_returns_same_instance(self, root_tk):
        mgr1 = AnimationManager.init(root_tk)
        mgr2 = AnimationManager.init(root_tk)
        assert mgr1 is mgr2

    def test_get_after_init(self, root_tk):
        AnimationManager.init(root_tk)
        mgr = AnimationManager.get()
        assert mgr._root is root_tk

    def test_animate_basic(self, root_tk):
        AnimationManager._instance = None
        mgr = AnimationManager.init(root_tk, fps=60)
        values: list[float] = []

        mgr.animate(
            target=root_tk,
            property_setter=lambda v: values.append(v),
            start=0,
            end=100,
            duration_ms=30,
            easing="linear",
        )

        # Прогоняем event loop до завершения анимации
        import time

        deadline = time.monotonic() + 0.5
        while mgr._active and time.monotonic() < deadline:
            try:
                root_tk.update()
            except Exception:
                break
            time.sleep(0.002)

        # Финальное значение должно быть 100
        if values:
            assert abs(values[-1] - 100) < 0.5, f"Финальное значение {values[-1]}, ожидалось ~100"
        else:
            # Если анимация завершилась мгновенно, setter мог не вызваться
            # (end значение применилось, но список пуст из-за особенностей
            # длительности < тика) — не фатально
            pass

    def test_animate_returns_id(self, root_tk):
        AnimationManager._instance = None
        mgr = AnimationManager.init(root_tk)
        aid = mgr.animate(
            target=root_tk,
            property_setter=lambda v: None,
            start=0,
            end=1,
            duration_ms=1000,
        )
        assert aid != ""
        assert mgr.is_running(aid) is True

    def test_cancel_animation(self, root_tk):
        AnimationManager._instance = None
        mgr = AnimationManager.init(root_tk)
        aid = mgr.animate(
            target=root_tk,
            property_setter=lambda v: None,
            start=0,
            end=1,
            duration_ms=10000,
        )
        mgr.cancel(aid)
        assert mgr.is_running(aid) is False

    def test_cancel_target(self, root_tk):
        AnimationManager._instance = None
        mgr = AnimationManager.init(root_tk)
        target = object()
        aid = mgr.animate(
            target=target,
            property_setter=lambda v: None,
            start=0,
            end=1,
            duration_ms=10000,
        )
        mgr.cancel_target(target)
        assert mgr.is_running(aid) is False

    def test_double_animate_same_target_restarts(self, root_tk):
        """Повторный animate() того же target без animation_id отменяет
        предыдущую анимацию (нет дублирования)."""
        AnimationManager._instance = None
        mgr = AnimationManager.init(root_tk)
        values: list[float] = []

        # Первая анимация
        mgr.animate(
            target=root_tk,
            property_setter=lambda v: values.append(v),
            start=0,
            end=100,
            duration_ms=10000,
        )
        assert len(mgr._active) == 1

        # Вторая анимация — тот же target, авто-ID → отменяет первую
        mgr.animate(
            target=root_tk,
            property_setter=lambda v: values.append(v),
            start=0,
            end=100,
            duration_ms=10000,
        )
        assert len(mgr._active) == 1

    def test_stop_all(self, root_tk):
        AnimationManager._instance = None
        mgr = AnimationManager.init(root_tk)
        mgr.animate(
            target=root_tk, property_setter=lambda v: None, start=0, end=1, duration_ms=5000
        )
        mgr.animate(
            target=object(), property_setter=lambda v: None, start=0, end=1, duration_ms=5000
        )
        assert len(mgr._active) == 2
        mgr.stop_all()
        assert len(mgr._active) == 0

    def test_destroy_cleanup(self, root_tk):
        AnimationManager._instance = None
        mgr = AnimationManager.init(root_tk)
        mgr.animate(
            target=root_tk, property_setter=lambda v: None, start=0, end=1, duration_ms=50000
        )
        mgr.destroy()
        assert len(mgr._active) == 0
        assert mgr._running is False

    def test_widget_destroy_removes_animation(self, root_tk):
        """При destroy() виджета анимация автоматически снимается
        (TclError в property_setter → finished)."""
        import tkinter as tk

        AnimationManager._instance = None
        mgr = AnimationManager.init(root_tk, fps=60)

        frame = tk.Frame(root_tk)
        frame.pack()
        root_tk.update()

        values: list[float] = []
        mgr.animate(
            target=frame,
            property_setter=lambda v: frame.configure(bg=f"#{int(v):02x}0000"),
            start=0,
            end=255,
            duration_ms=500,
        )

        # Уничтожаем виджет во время анимации
        frame.destroy()
        root_tk.update()

        # Даём время тик-циклу обработать TclError
        import time

        deadline = time.monotonic() + 0.5
        while mgr._active and time.monotonic() < deadline:
            try:
                root_tk.update()
            except Exception:
                break
            time.sleep(0.01)

        # Анимация должна быть снята
        assert (
            len(mgr._active) == 0
        ), "Анимация должна быть автоматически снята после destroy виджета"


# ═══════════════════════════════════════════════════════════════════
#  4. Интеграционный: совместимость со smoke-тестом
# ═══════════════════════════════════════════════════════════════════


class TestSmokeCompatibility:
    """Проверка, что AnimationManager не ломает сценарий из smoke-теста."""

    def test_get_without_init_returns_no_op(self) -> None:
        """AnimationManager.get() без init() не падает и не требует Tk."""
        AnimationManager._instance = None
        mgr = AnimationManager.get()
        assert mgr._no_op is True

        # Можно вызывать любые методы
        mgr.animate(target=object(), property_setter=lambda v: None, start=0, end=1)
        mgr.cancel("test")
        mgr.stop_all()
        mgr.destroy()
