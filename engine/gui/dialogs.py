# -*- coding: utf-8 -*-
"""engine/gui/dialogs.py — диалоги «Язык озвучки» и «Справка»
(перенесено из gui.py: pick_language, show_help)."""
import tkinter as tk

import customtkinter as ctk

from i18n import t

from engine.gui.colors import Colors
from engine.gui.tooltip import ToolTip

# Внедряются из main_window: root, lang_var, lang_split_enabled, save_settings
root = None
lang_var = None
lang_split_enabled = None
save_settings = None


def init(**deps):
    """Внедрение зависимостей из engine.gui.main_window (имена совпадают с
    именами глобальных переменных исходного gui.py)."""
    globals().update(deps)


def pick_language():
    win = tk.Toplevel(root)
    win.title(t("lang_picker_title"))
    win.resizable(False, False)
    win.configure(bg=Colors.BG_CARD)
    win.grab_set()
    langs = [
        ("Авто", "auto"), ("RU", "ru"), ("EN", "en"),
        ("ES", "es"), ("FR", "fr"), ("DE", "de"),
        ("IT", "it"), ("PT", "pt"), ("PL", "pl"),
        ("TR", "tr"), ("NL", "nl"), ("CS", "cs"),
        ("AR", "ar"), ("ZH", "zh-cn"), ("HU", "hu"),
        ("KO", "ko"), ("JA", "ja"), ("HI", "hi"),
    ]
    tk.Label(win, text=t("lang_picker_header"), bg=Colors.BG_CARD, fg=Colors.TEXT_MAIN,
             font=("Segoe UI", 12, "bold")).pack(pady=(15, 10))
    grid = tk.Frame(win, bg=Colors.BG_CARD)
    grid.pack(padx=15, pady=(0, 15))
    for i, (label, value) in enumerate(langs):
        tk.Radiobutton(
            grid, text=label, variable=lang_var, value=value,
            indicatoron=False, width=6,
            bg=Colors.BG_INPUT, fg=Colors.TEXT_MAIN,
            selectcolor=Colors.ACCENT, activebackground=Colors.BG_HOVER,
            font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2"
        ).grid(row=i // 6, column=i % 6, padx=3, pady=3)
    tk.Frame(win, bg=Colors.BG_CARD, height=1).pack(fill="x", padx=15, pady=(5, 0))
    split_row = tk.Frame(win, bg=Colors.BG_CARD)
    split_row.pack(fill="x", padx=15, pady=(8, 0))
    cb = ctk.CTkCheckBox(
        split_row, text=t("lang_auto_switch"), variable=lang_split_enabled,
        fg_color=Colors.BG_ACTIVE, hover_color=Colors.BG_HOVER,
        border_color=Colors.BORDER, text_color=Colors.TEXT_MAIN,
        font=("Segoe UI", 9)
    )
    cb.pack(side="left")
    ToolTip(cb, t("lang_auto_switch_tip"))
    tk.Button(
        win, text=t("btn_close"), command=lambda: [win.destroy(), save_settings()],
        bg=Colors.BG_ACTIVE, fg=Colors.TEXT_MAIN, relief="flat",
        font=("Segoe UI", 10, "bold"), cursor="hand2", padx=20, pady=5
    ).pack(pady=(0, 15))


def show_help():
    win = tk.Toplevel(root)
    win.title(t("win_help_title"))
    win.geometry("650x550")
    win.resizable(True, True)
    win.configure(bg=Colors.BG_CARD)
    win.grab_set()
    frame = tk.Frame(win, bg=Colors.BG_CARD)
    frame.pack(fill="both", expand=True, padx=15, pady=15)
    scrollbar = tk.Scrollbar(frame, bg=Colors.BG_INPUT, troughcolor=Colors.BG_DARK)
    scrollbar.pack(side="right", fill="y")
    text = tk.Text(
        frame, wrap="word", yscrollcommand=scrollbar.set,
        font=("Consolas", 12), bg=Colors.BG_DARK, fg=Colors.TEXT_MAIN,
        padx=15, pady=15, state="normal", relief="flat", highlightthickness=0
    )
    text.pack(fill="both", expand=True)
    scrollbar.config(command=text.yview)
    text.tag_configure("header", foreground=Colors.ACCENT, font=("Consolas", 11))
    text.tag_configure("symbol", foreground="#ffd600", font=("Consolas", 9))
    text.tag_configure("good", foreground=Colors.TEXT_SUCCESS)
    text.tag_configure("bad", foreground=Colors.TEXT_ERROR)
    text.tag_configure("normal", foreground=Colors.TEXT_MAIN)
    text.tag_configure("comment", foreground=Colors.TEXT_DIM)
    content = [
        ("header", "\n🤖 AI ФУНКЦИИ\n"),
        ("good", "Флажок ✨ AI (главное окно) — улучшение текста перед генерацией\n"),
        ("comment", "Технический редактор: раскрывает сокращения, убирает спецсимволы,\nразбивает длинные предложения. Смысл и стиль не меняет.\n\n"),
        ("good", "Кнопка 🤖 AI — AI Conductor\n"),
        ("comment", "Анализирует весь текст и назначает параметры XTTS для каждого чанка.\nПросодия и смарт-паузы отключаются — AI управляет ими напрямую.\nЭкспериментальная функция: результат зависит от провайдера и модели.\n\n"),
        ("good", "AI Conductor — Уровень 1: параметры движка\n"),
        ("comment", "Temperature, speed, паузы и прочие параметры назначаются индивидуально\nдля каждого чанка на основе контекста и интонации.\n\n"),
        ("good", "AI Conductor — Уровень 2: стиль текста\n"),
        ("comment", "Включается отдельным переключателем внутри окна кондуктора.\nAI переписывает текст под заданный жанр или настроение перед генерацией.\nФакты и названия сохраняются — меняется форма подачи.\nМожно добавить negative prompt: чего избегать при переработке.\n\n"),
        ("normal", "Оба уровня работают независимо и могут комбинироваться\n"),
        ("comment", "Сначала текст переписывается (уровень 2), затем под новый текст\nназначаются параметры чанков (уровень 1).\n\n"),
        ("good", "Настроение референса влияет на результат не менее параметров\n"),
        ("comment", "Если референс записан нейтрально — драматический стиль даст слабый эффект.\nДля лучшего результата подбирайте референс под заданный стиль.\n"),
        ("header", "🎯 АВТОМАТИЧЕСКАЯ ОБРАБОТКА\n"),
        ("good", "Числа → слова (авто)\n"),
        ("comment", "«2024» → «две тысячи двадцать четыре», «3.5» → «три целых пять»\n\n"),
        ("good", "Аббревиатуры → словарь произношений\n"),
        ("comment", "Английские слова автоматически распознаются и добавляются в словарь.\nНеизвестные термины читаются кириллицей по фонетике.\n\n"),
        ("good", "Пунктуационные и смысловые паузы → автоматически\n"),
        ("comment", "Модель сама расставляет паузы по знакам препинания и контексту.\n\n"),
        ("good", "Нормализация текста → автоматически\n"),
        ("comment", "Лишние пробелы, двойные знаки, артефакты — убираются до генерации.\n\n"),
        ("good", "Контроль качества чанков → авто-перегенерация\n"),
        ("comment", "Если модель выдала повторы или обрыв — чанк перегенерируется\nдо 3 раз. Включается в настройках пресета (🛡 QC).\n\n"),
        ("header", "\n⏸ ПАУЗЫ\n"),
        ("symbol", ".  "), ("normal", "стандартная пауза (~400 мс)\n"),
        ("symbol", ",  "), ("normal", "короткая пауза (~150 мс)\n"),
        ("symbol", "?  "), ("normal", "вопросительная интонация\n"),
        ("symbol", "!  "), ("normal", "восклицательная интонация\n"),
        ("symbol", "—  "), ("normal", "нормализуется в запятую\n"),
        ("symbol", ":  "), ("normal", "пауза перед пояснением\n"),
        ("symbol", "…  "), ("normal", "длинная пауза с затуханием\n\n"),
        ("header", "\n💬 СМЫСЛОВЫЕ ПАУЗЫ\n"),
        ("normal", "Перед «но», «однако», «хотя» → короткая пауза\n"),
        ("normal", "После «поэтому», «итак», «таким образом» → пауза вывода\n"),
        ("normal", "Перед «важно», «главное», «ключевое» → выделение\n"),
        ("normal", "Перед «например», «к примеру», «допустим» → пауза пояснения\n"),
        ("comment", "Паузы вставляются автоматически — вручную ничего расставлять не нужно.\n\n"),
        ("header", "\n📋 СПИСКИ\n"),
        ("good", "1. Первый пункт → читается как «первый»\n"),
        ("good", "2. Второй пункт → читается как «второй»\n"),
        ("comment", "Пункты 1–20 читаются порядковыми числительными, далее — цифрами.\nКаждый пункт получает паузу после номера автоматически.\n\n"),
        ("header", "\n🎨 ПРЕСЕТЫ\n"),
        ("normal", "⭐ Высокое качество — стабильный нейтральный голос\n"),
        ("normal", "📖 Нарратив — медленно, плавно, для книг и лекций\n"),
        ("normal", "⚡ Динамика — бодро, быстро, для рекламы и роликов\n"),
        ("normal", "🎭 Экспрессия — эмоционально, для драматичных сцен\n"),
        ("comment", "Двойной клик на пресете открывает тонкие настройки.\n\n"),
        ("header", "\n🎤 РЕФЕРЕНС\n"),
        ("good", "Оптимальная длина: 10–20 секунд\n"),
        ("good", "Тихая комната, без музыки и эха\n"),
        ("good", "Нейтральная эмоция, разборчивая речь\n"),
        ("good", "Автоматическая обрезка тишины и нормализация громкости\n"),
        ("good", "Файл сохраняется в библиотеку для повторного использования\n"),
        ("comment", "Чем чище референс — тем стабильнее клонирование.\nSNR ниже 8 dB даст заметные артефакты.\n\n"),
        ("header", "\n⚙ СОВЕТЫ\n"),
        ("normal", "Длинный текст автоматически бьётся на чанки — ограничений нет\n"),
        ("normal", "Словарь произношений — первая помощь при артефактах на конкретном слове\n"),
        ("normal", "Если голос «плывёт» к концу — уменьши Temperature в настройках пресета\n"),
        ("normal", "Повторы и «каша» — увеличь Repetition Penalty\n"),
        ("comment", "Кэш чанков ускоряет повторную генерацию того же текста тем же голосом.\n"),
    ]
    for tag, content_text in content:
        text.insert("end", content_text, tag)
    text.config(state="disabled")

    def close_window():
        # ИСПРАВЛЕНО: раньше save_settings() вызывался ДО win.destroy() и
        # без try/except. Если save_settings() бросало исключение (например,
        # проблема с записью settings.json) — выполнение прерывалось прямо
        # тут, строка win.destroy() не выполнялась, и окно "Справка"
        # оставалось висеть навсегда — крестик (X) выглядел так, будто
        # совсем не реагирует. Сравните с pick_language() выше в этом же
        # файле — там уже применён безопасный порядок: [win.destroy(),
        # save_settings()] (сначала закрыть, потом сохранить). Здесь делаем
        # то же самое + оборачиваем save_settings() в try/except на всякий
        # случай, чтобы окно гарантированно закрывалось при любом исходе.
        win.destroy()
        try:
            save_settings()
        except Exception:
            pass
    win.protocol("WM_DELETE_WINDOW", close_window)
