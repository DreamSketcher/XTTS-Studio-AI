# -*- coding: utf-8 -*-
"""СОВМЕСТИМОСТЬ: старое расположение окна «Словарь произношений».

Реальный модуль переехал в engine/gui/word_replacer_window.py.
Этот файл-мост оставлен на случай старых импортов `engine.word_replacer_window`
— он полностью делегирует новой версии.
"""
from engine.gui.word_replacer_window import init, open_word_replacer  # noqa: F401
