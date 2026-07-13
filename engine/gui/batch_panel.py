# -*- coding: utf-8 -*-
"""engine/gui/batch_panel.py — привязка окна «Пакетная обработка»
(перенесено из gui.py: batch_window.init(...), open_batch_window)."""
from engine.text_tools import normalize_text
from engine.gui import batch_window
from engine.gui.colors import Colors
from engine.gui.helpers import clean_path


def setup(
    root,
    output_dir,
    task_manager,
    ref_var,
    quality_var,
    quality_params,
    word_replacer_enabled,
    lang_split_enabled,
    use_gpt,
    lang_var,
):
    batch_window.init(
        root=root,
        colors=Colors,
        output_dir=output_dir,
        task_manager=task_manager,
        ref_var=ref_var,
        quality_var=quality_var,
        quality_params=quality_params,
        word_replacer_enabled_var=word_replacer_enabled,
        lang_split_enabled_var=lang_split_enabled,
        use_gpt_var=use_gpt,
        lang_var=lang_var,
        normalize_text_fn=normalize_text,
        clean_path_fn=clean_path,
    )


def open_batch_window():
    batch_window.open_batch_window()
