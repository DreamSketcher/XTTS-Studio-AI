# -*- coding: utf-8 -*-
"""
test/test_sha256_verification.py

Проверяет, что механизм SHA256 в engine/updater.py реально работает:
  1. Правильный хэш -> файл проходит проверку и остаётся в staging.
  2. Неправильный хэш -> файл отклоняется и удаляется.
  3. Хэш отсутствует в манифесте (None) -> файл отклоняется (это та дыра,
     которая раньше тихо пропускала проверку — теперь должна блокировать).

Работает БЕЗ сети: подменяет сетевую загрузку локальными тестовыми
данными, и без риска для реального проекта: STAGING_DIR подменяется на
временную папку pytest (tmp_path), а не на настоящий _update_staging/.

Раньше эти проверки жили в обычной функции run(), которую можно было
запустить только вручную (`python test/test_sha256_verification.py`) —
pytest её не видел и не запускал через "Run ALL tests". Теперь это
настоящие test_*() функции, которые pytest собирает и гоняет наравне
со всеми остальными.

Запуск:
    pytest test/test_sha256_verification.py -v
"""
import io
import os
import sys
from pathlib import Path

import pytest

# Нужно для запуска и как pytest-теста (через rootdir), и как отдельного
# скрипта (python test/test_sha256_verification.py) — во втором случае
# "engine" не будет в sys.path без этой строчки.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import updater  # noqa: E402

FAKE_CONTENT = b"XTTS Studio SHA256 self-test payload - do not modify"
CORRECT_HASH = __import__("hashlib").sha256(FAKE_CONTENT).hexdigest()
WRONG_HASH = "0" * 64
TEST_RELATIVE_PATH = "test/_sha256_selftest.tmp"


def _fake_urlopen(url, timeout=15, max_retries=None):
    """Заменяет реальный сетевой запрос локальными тестовыми байтами."""
    return io.BytesIO(FAKE_CONTENT)


@pytest.fixture
def isolated_staging(tmp_path, monkeypatch):
    """
    Подменяет STAGING_DIR на временную папку pytest и _urlopen_with_retry —
    на фейковый ответ. Никогда не трогает реальный проект/сеть.
    """
    staging = tmp_path / "_update_staging"
    monkeypatch.setattr(updater, "STAGING_DIR", str(staging))
    monkeypatch.setattr(updater, "_urlopen_with_retry", _fake_urlopen)
    # SHA256-mismatch retry в _download_to_staging делает реальные time.sleep()
    # (4с+8с+12с = ~24с backoff) — без мока test_wrong_hash_rejected честно
    # тормозит на эти секунды при каждом прогоне, что выглядит как зависание
    # при redirect-в-файл запуске (run_tests.bat, пункт [6]).
    monkeypatch.setattr(updater.time, "sleep", lambda s: None)
    os.makedirs(staging, exist_ok=True)
    return staging


def _staged_path(staging_dir) -> str:
    return os.path.join(str(staging_dir), TEST_RELATIVE_PATH.replace("/", os.sep))


# ───────────────────────── правильный хэш ─────────────────────────


def test_correct_hash_accepted(isolated_staging):
    ok = updater._download_to_staging(TEST_RELATIVE_PATH, CORRECT_HASH)

    assert ok is True
    assert os.path.exists(
        _staged_path(isolated_staging)
    ), "файл с верным хэшем должен остаться в staging"


# ───────────────────────── неправильный хэш ─────────────────────────


def test_wrong_hash_rejected(isolated_staging):
    ok = updater._download_to_staging(TEST_RELATIVE_PATH, WRONG_HASH)

    assert ok is False
    assert not os.path.exists(
        _staged_path(isolated_staging)
    ), "файл с неверным хэшем должен быть удалён из staging"


# ───────────────────────── хэш отсутствует в манифесте ─────────────────────────


def test_missing_hash_rejected(isolated_staging):
    """
    Раньше отсутствие хэша в манифесте (None) тихо пропускало проверку —
    файл применялся без верификации целостности вообще. Это была дыра:
    сломанный/неполный релизный манифест приводил к обновлению без всякой
    проверки. Теперь отсутствующий хэш должен блокировать файл так же, как
    и неверный.
    """
    ok = updater._download_to_staging(TEST_RELATIVE_PATH, None)

    assert ok is False
    assert not os.path.exists(
        _staged_path(isolated_staging)
    ), "файл без хэша в манифесте должен быть отклонён, а не тихо принят"


if __name__ == "__main__":
    # Совместимость с прежним способом запуска
    # (python\runtime\python.exe test\test_sha256_verification.py) —
    # просто делегируем в pytest на этот же файл.
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
