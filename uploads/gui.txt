# -*- coding: utf-8 -*-
"""gui.py — точка входа XTTS Studio.

Только запуск интерфейса: подготовка окружения, импорт GUI-модулей,
создание главного окна и mainloop(). Вся логика вынесена в engine/
(техника) и engine/gui/ (интерфейс).
"""
import os
import sys

BASE_DIR = os.path.dirname(__file__)
SITE_PACKAGES = os.path.join(BASE_DIR, "python", "xtts_env", "Lib", "site-packages")
if os.path.exists(SITE_PACKAGES):
    sys.path.insert(0, SITE_PACKAGES)

import traceback


def _global_exception_handler(exc_type, exc_value, exc_tb):
    traceback.print_exception(exc_type, exc_value, exc_tb)
    input("Press Enter to exit...")


sys.excepthook = _global_exception_handler

from engine.gui.main_window import create_main_window


def main():
    root = create_main_window()
    root.mainloop()


if __name__ == "__main__":
    main()
