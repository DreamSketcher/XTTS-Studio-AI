# -*- coding: utf-8 -*-
"""engine/gui/chat_panel.py — привязка окна AI-чата к главному окну
(перенесено из gui.py: chat_window.init(...), toggle_chat_panel,
append_chat_message, set_chat_status)."""
from engine.gui import chat_window
from engine.gui.colors import Colors
from engine.gui.widgets import create_button
from engine.gui.textbox import _get_textbox_content, set_textbox_content, PLACEHOLDER


def setup(root, use_gpt):
    chat_window.init(
        root=root,
        colors=Colors,
        create_button_fn=create_button,
        get_text_fn=_get_textbox_content,
        set_text_fn=set_textbox_content,
        placeholder=PLACEHOLDER,
        use_gpt_var=use_gpt,
    )


def toggle_chat_panel():
    chat_window.open_chat_window()


def append_chat_message(role, message):
    chat_window.append_chat_message(role, message)


def set_chat_status(message):
    chat_window.set_chat_status(message)
