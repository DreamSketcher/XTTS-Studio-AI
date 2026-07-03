# -*- coding: utf-8 -*-
"""
i18n.py — Internationalization module for XTTS Studio.
Supports Russian (ru) and English (en) UI languages.
The synthesis language (lang_var / lang_split_enabled) is NOT affected.

Usage:
    from i18n import t, set_language, get_language, LANGUAGES

    set_language("en")
    label_text = t("generate")  # -> "GENERATE"
"""

import json
import os

_current_lang = "ru"

LANGUAGES = {
    "ru": {
        # ── Header / Left Panel ──
        "app_title": "XTTS Studio",
        "app_author": " by EXIZ10TION",
        "btn_update": "🆕 Обновить",
        "btn_ai_status": "🔌 AI статус",

        # ── Voice Reference Card ──
        "card_voice_ref": "🎤 Голос-референс",
        "btn_pick_ref": "📁 Выбрать",
        "ref_info": "✅ Конвертирован в WAV\n✅ Обрезан\n✅ Нормализован\n✅ Сохранён в библиотеку",

        # ── Voice Library ──
        "card_voice_lib": "📚 Библиотека голосов",
        "tip_pick_from_lib": "Выбрать голос из библиотеки",
        "active_voice": "🎤 Активный голос: {}",

        # ── Queue ──
        "card_queue": "📋 Очередь задач",
        "btn_batch": "📦 Пакетная обработка",

        # ── Console ──
        "console_show": "📋 Console ▼",
        "console_hide": "📋 Console ▲",
        "btn_clear_console": "🗑",

        # ── Right Panel / Text ──
        "card_text": "📝 Текст",
        "btn_help": "❓ Справка",
        "placeholder": "Перетащите текстовый файл или введите текст...",

        # ── Toolbar: File Group ──
        "group_file": "Файл",
        "btn_load": "📁 Загрузить",
        "btn_paste": "📋 Вставить",
        "btn_clear": "🗑 Очистить",

        # ── Toolbar: AI Group ──
        "group_ai": "AI",
        "chk_ai_edit": "✨ AI edit",
        "btn_ai_assistant": "💬 AI Помощник",
        "btn_ai_conductor": "🤖 AI",
        "tip_ai_edit": "Улучшить текст через AI перед озвучкой",
        "tip_ai_assistant": "Открыть AI-чат-панель под редактором.\nТребует API-ключ (см. в ⚙ Настройки).",
        "tip_ai_conductor": "AI Conductor — управляет параметрами каждого чанка через AI.",

        # ── Toolbar: Output Group ──
        "group_output": "Вывод",
        "btn_language": "🌐 Язык генерации",
        "btn_dictionary": "📖 Словарь",
        "btn_styles": "🎨 Стили ▾",
        "btn_quality_default": "⭐ Высокое качество",
        "tip_language": "Текущий язык: {}\nМожно менять акцент",
        "tip_dictionary": "Словарь произношений.\n\nАнглийские слова из текста автоматически\nраспознаются и добавляются — они будут\nчитаться кириллицей без артефактов.\n\nМожно добавлять и править — приоритет на пользовательское решение.",
        "tip_styles": "Открыть список стилей:\nНарратив / Динамика / Экспрессия.\nМногое зависит от референса",
        "tip_quality_default": "Режим по умолчанию.\nДвойной клик — открыть доп. параметры.",

        # ── Toolbar: Action Group ──
        "group_action": "Действие",
        "btn_history": "📜 История",
        "btn_audio": "🎵 Аудио",
        "btn_generate": "🚀  ГЕНЕРИРОВАТЬ",
        "btn_cancel": "⛔ ОТМЕНА",

        # ── Status Bar ──
        "status_init": "🔄 Инициализация модели...",
        "status_ready": "✅ Модель готова",
        "status_waiting": "⏳ Ожидание...",
        "status_queued": "📥 Добавлено в очередь...",
        "status_queue_wait": "⏳ В очереди...",
        "status_running": "🔄 Генерация... {}%",
        "status_done": "✅ Готово",
        "status_done_detail": "✅ Готово | {} | Чанков: {} | Голос: {}",
        "status_error": "❌ Ошибка",
        "status_cancelled": "⛔ Отменено",
        "status_cancelling": "⛔ Отмена задачи...",
        "status_update_check": "🔄 Проверка обновлений...",
        "status_update_download": "📥 Загрузка обновления...",

        # ── Dialogs ──
        "dlg_done_title": "✅ Готово",
        "dlg_done_msg": "Файл сохранён:\n{}",
        "dlg_error_title": "❌ XTTS Error",
        "dlg_error_empty": "Текст пустой",
        "dlg_error_no_ref": "Выберите reference audio",
        "dlg_error_open_file": "Не удалось открыть файл",
        "dlg_audio_unavailable": "Аудио-устройство недоступно",
        "dlg_pick_ref_first": "Сначала выберите референс",
        "dlg_clipboard_empty": "Нет текста",
        "dlg_play_error": "Не удалось воспроизвести: {}",

        # ── Context Menu ──
        "ctx_copy": "Копировать",
        "ctx_paste": "Вставить",
        "ctx_cut": "Вырезать",
        "ctx_select_all": "Выделить всё",
        "ctx_clear": "Очистить",

        # ── Language Picker ──
        "lang_picker_title": "🌐 Язык модели",
        "lang_picker_header": "Выберите язык модели",
        "lang_auto_switch": "🔀 Авто-переключение языка",
        "lang_auto_switch_tip": "Английские слова от трёх и больше слов читаются на английском автоматически.\nОтключите если хотите поменять акцент.",
        "btn_close": "✓  Закрыть",

        # ── Outputs Window ──
        "win_audio_title": "🎵 Аудио файлы",
        "btn_open_folder": "📂 Открыть папку",
        "btn_delete_all": "🗑 Удалить все",
        "btn_clear_cache": "🧹 Очистить кэш",
        "files_count": "{} файлов",
        "no_file": "Нет файла",
        "dlg_delete_title": "Удалить?",
        "dlg_delete_msg": "Удалить файл:\n{}?",
        "dlg_delete_all_title": "Удалить всё?",
        "dlg_delete_all_msg": "Удалить все {} WAV-файлов?",
        "cache_cleared": "Кэш очищен",
        "cache_cleared_msg": "Удалено файлов кэша: {}",
        "cache_already_empty": "Кэш уже пуст.",
        "dlg_empty": "Пусто",
        "dlg_empty_msg": "Нет файлов для удаления.",

        # ── History Window ──
        "win_history_title": "📜 История генераций",
        "entries_count": "{} записей",
        "btn_clear_history": "🗑 Очистить историю",
        "dlg_clear_history": "Удалить всю историю генераций?",
        "history_empty": "История пуста",
        "chunks_word": "чанков",

        # ── Help Window ──
        "win_help_title": "❓ Справка",

        # ── Quality Presets ──
        "preset_high": "Высокое качество",
        "preset_narrative": "Нарратив",
        "preset_dynamic": "Динамика",
        "preset_expressive": "Экспрессия",
        "preset_narrative_desc": "📖 Нарратив\nСпокойное, плавное чтение.\nМедленный темп, ровная интонация.\nИдеально для книг и озвучки текста\nНажмите чтобы открыть настройки.",
        "preset_dynamic_desc": "⚡ Динамика\nБодрый, энергичный голос.\nУскоренный темп, живые интонации.\nПодходит для рекламы и роликов\nНажмите чтобы открыть настройки.",
        "preset_expressive_desc": "🎭 Экспрессия\nМаксимально эмоциональная подача.\nЯркие интонации и выразительность.\nДля драматичных сцен и эмоций\nНажмите чтобы открыть настройки.",

        # ── Quality Settings Window ──
        "win_settings_title": "⚙ Настройки — {}",
        "lbl_temperature": "Temperature",
        "lbl_top_p": "Top P",
        "lbl_top_k": "Top K",
        "lbl_rep_penalty": "Repetition Penalty",
        "lbl_speed": "Скорость речи",
        "lbl_prosody": "Просодия",
        "lbl_deesser": "Де-эссер",
        "lbl_trim": "Trim конца (мс)",
        "lbl_trim_mode": "Режим Trim:",
        "trim_auto": "Авто",
        "trim_manual": "Ручной",
        "trim_off": "Выкл",
        "lbl_export_format": "Формат экспорта:",
        "chk_qc": "🛡 Контроль качества (авто-перегенерация бракованных чанков)",
        "tip_qc": "Включает детектор повторов и валидатор длительности.\nПри браке — автоматическая перегенерация чанка (до 3 попыток).\nНемного замедляет генерацию.",
        "btn_reset": "🔄 Сбросить",

        # ── AI Status Window ──
        "win_ai_status_title": "🔌 AI провайдеры — статус",
        "ai_xtts_device": "🖥 XTTS модель: {}",
        "ai_active_provider": "🤖 Активный AI-провайдер: {}",
        "ai_key_set": "✅ Ключ задан",
        "ai_key_missing": "❌ Ключ не задан — этот провайдер будет пропущен",
        "ai_fallback_order": "Порядок fallback: {}",
        "ai_fallback_empty": "пусто — ни у одного провайдера нет ключа",
        "ai_builtin": "Встроенный",
        "ai_custom": "Кастомный",
        "ai_model_label": "Модель: {}",

        # ── AI Conductor Window ──
        "win_conductor_title": "🤖 AI Conductor",
        "conductor_header": "🤖 AI Conductor",
        "conductor_desc": "Анализирует весь текст одним вызовом и назначает\nпараметры XTTS для каждого чанка индивидуально.\nПросодия, смарт-паузы и словарь отключаются — AI управляет ими.",
        "conductor_enabled": "✅ Включён — нажмите чтобы выключить",
        "conductor_disabled": "❌ Выключен — нажмите чтобы включить",
        "conductor_apply_to": "Применять к:",
        "conductor_all_presets": "Все пресеты",
        "conductor_experimental": "⚠ Экспериментальная функция",
        "conductor_warning_text": "AI Conductor управляет параметрами каждого чанка.\nРезультат может быть неожиданным — особенно\nесли референсный голос записан в нейтральном\nили неподходящем настроении.",
        "conductor_dont_show": "Больше не показывать",
        "conductor_understood": "Понятно",
        "conductor_rewrite_on": "✅ Стиль текста — нажмите чтобы выключить",
        "conductor_rewrite_off": "❌ Стиль текста — нажмите чтобы включить",
        "conductor_rewrite_desc": "AI переработает текст под заданный жанр или настроение\nперед генерацией. Параметры движка назначаются под новый текст.",
        "conductor_style_prompt": "Задание на стиль:",
        "conductor_negative_prompt": "Negative prompt (чего избегать):",
        "conductor_provider_label": "Провайдер: {}",
        "conductor_provider_none": "Провайдер: не настроен",
        "btn_save": "✓  Сохранить",
        "btn_cancel_dialog": "Отмена",

        # ── Updater ──
        "update_installed": "Обновление до версии {} установлено.",
        "update_changelog": "\n\nЧто изменилось:\n{}",
        "update_restart": "\n\nПриложение перезапустится после нажатия ОК.",
        "update_partial": "Некоторые файлы не удалось обновить.\nПроверьте соединение.",
        "update_no_updates": "У вас актуальная версия {}",
        "update_available": "Версия {} доступна.\nСейчас у вас {}.\n",
        "update_whats_new": "\nЧто нового:\n{}\n",
        "update_confirm": "\nОбновить?",
        "update_title": "🆕 Доступно обновление",
        "update_done_title": "✅ Готово",
        "update_partial_title": "⚠ Частичное обновление",
        "update_no_title": "✅ Обновлений нет",
        "update_error_title": "❌ Ошибка",

        # ── UI Language Switch ──
        "lang_ui_label": "UI",

        # ── Text size slider ──
        "tip_font_size": "Размер текста в окне ввода",

        # ── Theme switch ──
        "tip_theme": "Переключить тему (тёмная/светлая)",
        "theme_title": "Тема",

        # ── AI Providers (labels / notes) ──
        "prov_groq": "Groq (нужен VPN из РФ)",
        "prov_openrouter": "OpenRouter (работает из РФ без VPN)",
        "prov_proxy": "Российский прокси (без VPN)",
        "cat_openrouter_notes": "Работает из РФ без VPN. Сотни моделей.",
        "cat_together_notes": "Много открытых моделей, быстрый.",
        "cat_mistral_notes": "Официальный API Mistral.",
        "cat_deepinfra_notes": "Дешёвые GPU-инференс модели.",
        "cat_vsegpt_label": "VseGPT (РФ)",
        "cat_vsegpt_notes": "Российский агрегатор, оплата в рублях.",
        "cat_aitunnel_label": "AITUNNEL (РФ)",
        "cat_aitunnel_notes": "Российский прокси, оплата в рублях.",
        "cat_proxyapi_label": "ProxyAPI (РФ)",
        "cat_proxyapi_notes": "Российский прокси OpenAI, оплата в рублях.",
        "prov_reason_active": "Активный, используется первым",
        "prov_reason_hidden": "Скрыт пользователем",
        "prov_reason_no_key": "Пропущен — нет API-ключа",
        "prov_reason_fallback": "Доступен как fallback",

        # ── Misc ──
        "time_today": "сегодня {}",
        "time_yesterday": "вчера {}",
        "time_format_m_s": "{}м {}с",
        "time_format_s": "{}с",

        # ── AI Chat Window ──
        "chat_win_title": "💬 AI Чат — XTTS Studio",
        "chat_header": "AI Чат",
        "chat_btn_new_chat": "＋ Новый чат",
        "chat_btn_delete_chat": "🗑 Удалить чат",
        "chat_search_label": "Поиск: Ctrl+F",
        "chat_btn_down": "↓ Вниз",
        "chat_btn_export": "⬇ Экспорт",
        "chat_btn_settings": "⚙ Настройки",
        "chat_ready": "Готов к работе",
        "chat_btn_improve": "✨ Улучшить",
        "chat_btn_from_editor": "📋 Из редактора",
        "chat_btn_clear": "🧹 Очистить",
        "chat_new_chat_title": "Новый чат",
        "chat_welcome": "Спросите AI о тексте, дикторе, TTS или улучшите текст для озвучки.",
        "chat_placeholder_input": "Напишите сообщение…",
        "chat_hint_default": "Enter — отправить · Shift+Enter — новая строка · Ctrl+F — поиск",
        "chat_hint_editor": "Enter — отправить · Ctrl+Enter — отправить без комментария · Shift+Enter — новая строка",
        "chat_hint_editor2": "Enter — отправить · Ctrl+Enter — без комментария · ✕ — отмена",
        "chat_editor_preview_title": "📋 Текст из редактора",
        "chat_new_reply_notice": "↓ Новый ответ — нажмите, чтобы прокрутить",
        "chat_btn_cancel": "Отмена",
        "chat_btn_ok": "ОК",
        "chat_prompt_editor_comment": "Текст из редактора:\n{}\n\nКомментарий:\n{}",
        "chat_display_with_comment": "{}\n\nКомментарий:\n{}",
        "chat_err_save_history": "Не удалось сохранить историю: {}",
        "chat_clear_title": "Очистить чат",
        "chat_clear_msg": "Очистить сообщения текущего чата?",
        "chat_clear_done": "История текущего чата очищена",
        "chat_session_loaded": "Сессия загружена",
        "chat_err_switch_session": "Ошибка переключения сессии: {}",
        "chat_created_new": "Создан новый чат",
        "chat_delete_title": "Удалить чат",
        "chat_delete_msg": "Удалить чат «{}» без возможности восстановления?",
        "chat_deleted": "Чат удалён",
        "chat_author_you": "Вы",
        "chat_role_system": "Система",
        "chat_meta_format": "{} · {} · ≈{} ток.",
        "chat_msg_copied": "Сообщение скопировано",
        "chat_err_copy": "Не удалось скопировать: {}",
        "chat_selection_cleared": "Выбор снят",
        "chat_msg_selected": "Сообщение выбрано · нажмите «→» на нём, чтобы отправить в редактор",
        "chat_sent_to_editor_sys": "Текст отправлен в редактор ({} симв.)",
        "chat_sent_to_editor": "✅ Текст отправлен в редактор TTS",
        "chat_err_generic": "Ошибка: {}",
        "chat_ctx_copy": "📋 Копировать",
        "chat_ctx_to_editor": "📝 В редактор TTS",
        "chat_ctx_to_input": "↩ В поле ввода чата",
        "chat_ai_typing": "AI печатает",
        "chat_ai_typing_status": "AI печатает...",
        "chat_token_counter": "Ввод: ≈{} ток. · Чат: ≈{} ток.",
        "chat_reply_received": "Ответ получен",
        "chat_unknown_error": "Неизвестная ошибка",
        "chat_ai_unavailable": "ИИ временно недоступен. Попробуйте позже.",
        "chat_err_ai_status": "Ошибка AI: {}",
        "chat_err_ai_title": "Ошибка AI",
        "chat_generation_stopped": "Генерация остановлена",
        "chat_ai_edit_off_title": "AI edit выключен",
        "chat_ai_edit_off_msg": "Включите флажок ✨ AI edit в главном окне.",
        "chat_err_title": "Ошибка",
        "chat_err_get_text": "Не удалось получить текст из редактора: {}",
        "chat_empty_title": "Пустой текст",
        "chat_empty_editor": "Текст в редакторе пустой.",
        "chat_improving": "Улучшаю текст для TTS...",
        "chat_improved_sys": "Текст улучшен для TTS: {} → {} символов",
        "chat_text_updated": "Текст обновлён в редакторе",
        "chat_err_insert": "Не удалось вставить результат в редактор: {}",
        "chat_err_insert_status": "Ошибка вставки результата",
        "chat_err_improve": "Ошибка улучшения текста: {}",
        "chat_err_no_editor_fns": "Функции доступа к редактору не инициализированы.",
        "chat_no_text_in_editor": "В редакторе нет текста.",
        "chat_no_text_top": "Нет текста в верхнем окне.",
        "chat_editor_source_label": "Текст из редактора",
        "chat_editor_hint": "Выделите фрагмент сверху и нажмите «В редактор». Ниже можно написать комментарий для AI.",
        "chat_editor_win_hint": "Enter — отправить и закрыть · Shift+Enter — новая строка · Ctrl+Enter — отправить и закрыть · Ctrl+Shift+Enter — вставить в поле ввода · Ctrl+F — поиск",
        "chat_source_label": "Источник",
        "chat_source_updated": "Источник обновлён из редактора",
        "chat_err_update_text": "Не удалось обновить текст: {}",
        "chat_empty_selection_title": "Пустое выделение",
        "chat_empty_selection_msg": "Выделите фрагмент текста в верхнем окне.",
        "chat_editor_overwritten_sys": "Редактор перезаписан выделенным фрагментом ({} символов)",
        "chat_editor_overwritten": "Редактор перезаписан выделением",
        "chat_err_overwrite": "Не удалось перезаписать редактор: {}",
        "chat_btn_to_editor": "↩ В редактор",
        "chat_comment_label": "Комментарий к тексту",
        "chat_what_to_do": "Что сделать с текстом?",
        "chat_comment_placeholder": "Комментарий к тексту…",
        "chat_stats_format": "Источник: {} симв. · Комментарий: {} симв. · Итого: {} симв.",
        "chat_editor_hint3": "Enter — отправить и закрыть · Esc — закрыть",
        "chat_source_comment_empty": "Источник и комментарий пустые.",
        "chat_inserted_to_input": "Текст вставлен в поле ввода",
        "chat_sent_to_chat": "Текст отправлен в чат",
        "chat_improving_fallback": "Улучшаю текст… (авто-fallback при лимите)",
        "chat_done_chars": "Готово: {} → {} симв.",
        "chat_btn_send": "➤ Отправить",
        "chat_btn_to_input": "↪ В поле ввода",
        "chat_btn_close_x": "✕ Закрыть",
        "chat_err_paste": "Ошибка вставки: {}",
        "chat_editor_empty": "Редактор пуст",
        "chat_placeholder_comment": "Добавьте комментарий… или нажмите Enter чтобы отправить как есть",
        "chat_editor_ready": "Текст из редактора готов · добавьте комментарий или нажмите Enter",
        "chat_export_title": "Экспорт",
        "chat_export_empty": "В текущем чате нет сообщений.",
        "chat_export_dialog_title": "Экспорт текущего чата",
        "chat_exported": "Чат экспортирован: {}",
        "chat_export_err_title": "Ошибка экспорта",
        "chat_search_win_title": "Поиск по истории",
        "chat_search_header": "Поиск по истории чатов",
        "chat_search_hint": "Enter — поиск · Double click / Enter — открыть · Esc — закрыть · Ctrl+F — фокус в строке поиска",
        "chat_search_enter_query": "Введите запрос",
        "chat_search_match_title": "Совпадение в названии: {}",
        "chat_search_found": "Найдено: {}",
        "chat_search_opened": "Открыт чат из результатов поиска",
        "chat_settings_title": "Настройки AI",
        "chat_err_load_gpt": "Не удалось загрузить engine.gpt_client: {}",
        "chat_settings_win_title": "⚙ Настройки AI",
        "chat_provider_edit": "Редактировать провайдер",
        "chat_provider_add": "Добавить провайдер",
        "chat_field_label": "Название",
        "chat_field_url": "URL эндпоинта (/v1/chat/completions)",
        "chat_field_models": "Модели (каждая с новой строки)",
        "chat_field_fallback": "Fallback модель (при лимите)",
        "chat_field_headers": "Доп. заголовки (необязательно, формат «Key: Value», каждый с новой строки)",
        "chat_url_empty": "URL не может быть пустым",
        "chat_need_model": "Укажите хотя бы одну модель",
        "chat_btn_cancel_x": "✕ Отмена",
        "chat_btn_save": "💾 Сохранить",
        "chat_catalogue_title": "Каталог",
        "chat_catalogue_unavailable": "Каталог провайдеров недоступен.",
        "chat_catalogue_win": "Каталог провайдеров",
        "chat_catalogue_header": "Выберите провайдера из каталога",
        "chat_catalogue_hint": "Двойной клик или «Добавить» — подключить провайдера",
        "chat_already_added": "  ✓ уже добавлен",
        "chat_catalogue_select": "Выберите провайдера из списка",
        "chat_key_hint": "{}  |  Ключ: {}",
        "chat_select_provider": "Выберите провайдера.",
        "chat_provider_exists": "Провайдер «{}» уже добавлен.",
        "chat_loading_models": "Загружаю список моделей...",
        "chat_models_failed": "Модели не загрузились — добавлю провайдера без списка моделей. Введите вручную.",
        "chat_models_loaded": "Загружено моделей: {}",
        "chat_btn_add": "＋ Добавить",
        "chat_providers_header": "Провайдеры AI",
        "chat_key_set": "✅ ключ задан",
        "chat_key_none": "❌ нет ключа",
        "chat_active_label": "АКТИВНЫЙ",
        "chat_model_label": "Модель",
        "chat_models_empty": "Список моделей пуст.",
        "chat_saved": "💾 Сохранено",
        "chat_check_unavailable": "Проверка недоступна",
        "chat_checking_key": "Проверка ключа...",
        "chat_btn_check": "🔑 Проверить",
        "chat_btn_activate": "✓ Активным",
        "chat_provider_delete_title": "Удалить провайдер",
        "chat_provider_delete_msg": "Удалить «{}» без возможности восстановления?",
        "chat_provider_hide_title": "Скрыть провайдер",
        "chat_provider_hide_msg": "Скрыть «{}»? Ключ и модель будут забыты.",
        "chat_btn_hide": "🚫 Скрыть",
        "chat_btn_catalogue": "🌐 Каталог",
        "chat_free_mode": "💬 Свободный чат",
        "chat_free_mode_on": "💬 Свободный чат ✓",
        "chat_mode_free": "Режим: свободный чат",
        "chat_mode_editor": "Режим: редактор текста",
        "chat_mode_free_small": "режим: свободный чат",
        "chat_mode_editor_small": "режим: редактор",
        "chat_switch_mode": "сменить режим",
    },

    "en": {
        # ── Header / Left Panel ──
        "app_title": "XTTS Studio",
        "app_author": " by EXIZ10TION",
        "btn_update": "🆕 Update",
        "btn_ai_status": "🔌 AI Status",

        # ── Voice Reference Card ──
        "card_voice_ref": "🎤 Voice Reference",
        "btn_pick_ref": "📁 Browse",
        "ref_info": "✅ Converted to WAV\n✅ Trimmed\n✅ Normalized\n✅ Saved to library",

        # ── Voice Library ──
        "card_voice_lib": "📚 Voice Library",
        "tip_pick_from_lib": "Pick voice from library",
        "active_voice": "🎤 Active voice: {}",

        # ── Queue ──
        "card_queue": "📋 Task Queue",
        "btn_batch": "📦 Batch Processing",

        # ── Console ──
        "console_show": "📋 Console ▼",
        "console_hide": "📋 Console ▲",
        "btn_clear_console": "🗑",

        # ── Right Panel / Text ──
        "card_text": "📝 Text",
        "btn_help": "❓ Help",
        "placeholder": "Drop a text file here or start typing...",

        # ── Toolbar: File Group ──
        "group_file": "File",
        "btn_load": "📁 Load",
        "btn_paste": "📋 Paste",
        "btn_clear": "🗑 Clear",

        # ── Toolbar: AI Group ──
        "group_ai": "AI",
        "chk_ai_edit": "✨ AI edit",
        "btn_ai_assistant": "💬 AI Assistant",
        "btn_ai_conductor": "🤖 AI",
        "tip_ai_edit": "Improve text with AI before synthesis",
        "tip_ai_assistant": "Open AI chat panel below the editor.\nRequires an API key (see ⚙ Settings).",
        "tip_ai_conductor": "AI Conductor — assigns per-chunk XTTS parameters via AI.",

        # ── Toolbar: Output Group ──
        "group_output": "Output",
        "btn_language": "🌐 Synthesis Language",
        "btn_dictionary": "📖 Dictionary",
        "btn_styles": "🎨 Styles ▾",
        "btn_quality_default": "⭐ High Quality",
        "tip_language": "Current language: {}\nYou can change the accent",
        "tip_dictionary": "Pronunciation dictionary.\n\nEnglish words from the text are automatically\nrecognized and added — they will be\nread in Cyrillic without artefacts.\n\nYou can add and edit — user entries take priority.",
        "tip_styles": "Open style list:\nNarrative / Dynamic / Expressive.\nReference voice matters a lot",
        "tip_quality_default": "Default mode.\nDouble-click to open detailed settings.",

        # ── Toolbar: Action Group ──
        "group_action": "Action",
        "btn_history": "📜 History",
        "btn_audio": "🎵 Audio",
        "btn_generate": "🚀  GENERATE",
        "btn_cancel": "⛔ CANCEL",

        # ── Status Bar ──
        "status_init": "🔄 Initializing model...",
        "status_ready": "✅ Model ready",
        "status_waiting": "⏳ Waiting...",
        "status_queued": "📥 Added to queue...",
        "status_queue_wait": "⏳ In queue...",
        "status_running": "🔄 Generating... {}%",
        "status_done": "✅ Done",
        "status_done_detail": "✅ Done | {} | Chunks: {} | Voice: {}",
        "status_error": "❌ Error",
        "status_cancelled": "⛔ Cancelled",
        "status_cancelling": "⛔ Cancelling task...",
        "status_update_check": "🔄 Checking for updates...",
        "status_update_download": "📥 Downloading update...",

        # ── Dialogs ──
        "dlg_done_title": "✅ Done",
        "dlg_done_msg": "File saved:\n{}",
        "dlg_error_title": "❌ XTTS Error",
        "dlg_error_empty": "Text is empty",
        "dlg_error_no_ref": "Select a reference audio first",
        "dlg_error_open_file": "Could not open file",
        "dlg_audio_unavailable": "Audio device not available",
        "dlg_pick_ref_first": "Select a reference first",
        "dlg_clipboard_empty": "Clipboard is empty",
        "dlg_play_error": "Could not play: {}",

        # ── Context Menu ──
        "ctx_copy": "Copy",
        "ctx_paste": "Paste",
        "ctx_cut": "Cut",
        "ctx_select_all": "Select All",
        "ctx_clear": "Clear",

        # ── Language Picker ──
        "lang_picker_title": "🌐 Model Language",
        "lang_picker_header": "Select model language",
        "lang_auto_switch": "🔀 Auto language switch",
        "lang_auto_switch_tip": "English words (3+ words) are automatically read in English.\nDisable to change accent.",
        "btn_close": "✓  Close",

        # ── Outputs Window ──
        "win_audio_title": "🎵 Audio Files",
        "btn_open_folder": "📂 Open Folder",
        "btn_delete_all": "🗑 Delete All",
        "btn_clear_cache": "🧹 Clear Cache",
        "files_count": "{} files",
        "no_file": "No file",
        "dlg_delete_title": "Delete?",
        "dlg_delete_msg": "Delete file:\n{}?",
        "dlg_delete_all_title": "Delete all?",
        "dlg_delete_all_msg": "Delete all {} WAV files?",
        "cache_cleared": "Cache Cleared",
        "cache_cleared_msg": "Cache files removed: {}",
        "cache_already_empty": "Cache is already empty.",
        "dlg_empty": "Empty",
        "dlg_empty_msg": "No files to delete.",

        # ── History Window ──
        "win_history_title": "📜 Generation History",
        "entries_count": "{} entries",
        "btn_clear_history": "🗑 Clear History",
        "dlg_clear_history": "Delete all generation history?",
        "history_empty": "History is empty",
        "chunks_word": "chunks",

        # ── Help Window ──
        "win_help_title": "❓ Help",

        # ── Quality Presets ──
        "preset_high": "Высокое качество",
        "preset_narrative": "Нарратив",
        "preset_dynamic": "Динамика",
        "preset_expressive": "Экспрессия",
        "preset_narrative_desc": "📖 Narrative\nCalm, flowing narration.\nSlow pace, even intonation.\nIdeal for audiobooks and lectures\nClick to open settings.",
        "preset_dynamic_desc": "⚡ Dynamic\nEnergetic, lively voice.\nFast pace, vivid intonation.\nGreat for ads and videos\nClick to open settings.",
        "preset_expressive_desc": "🎭 Expressive\nMaximum emotional delivery.\nRich intonation and expression.\nFor dramatic scenes and emotions\nClick to open settings.",

        # ── Quality Settings Window ──
        "win_settings_title": "⚙ Settings — {}",
        "lbl_temperature": "Temperature",
        "lbl_top_p": "Top P",
        "lbl_top_k": "Top K",
        "lbl_rep_penalty": "Repetition Penalty",
        "lbl_speed": "Speech Speed",
        "lbl_prosody": "Prosody",
        "lbl_deesser": "De-esser",
        "lbl_trim": "Trim End (ms)",
        "lbl_trim_mode": "Trim Mode:",
        "trim_auto": "Auto",
        "trim_manual": "Manual",
        "trim_off": "Off",
        "lbl_export_format": "Export Format:",
        "chk_qc": "🛡 Quality Control (auto-regenerate bad chunks)",
        "tip_qc": "Enables repeat detector and duration validator.\nBad chunks are regenerated automatically (up to 3 attempts).\nSlightly slower generation.",
        "btn_reset": "🔄 Reset",

        # ── AI Status Window ──
        "win_ai_status_title": "🔌 AI Providers — Status",
        "ai_xtts_device": "🖥 XTTS model: {}",
        "ai_active_provider": "🤖 Active AI provider: {}",
        "ai_key_set": "✅ Key is set",
        "ai_key_missing": "❌ Key not set — this provider will be skipped",
        "ai_fallback_order": "Fallback order: {}",
        "ai_fallback_empty": "empty — no provider has a key",
        "ai_builtin": "Built-in",
        "ai_custom": "Custom",
        "ai_model_label": "Model: {}",

        # ── AI Conductor Window ──
        "win_conductor_title": "🤖 AI Conductor",
        "conductor_header": "🤖 AI Conductor",
        "conductor_desc": "Analyzes the entire text in one call and assigns\nXTTS parameters for each chunk individually.\nProsody, smart pauses and dictionary are disabled — AI controls them.",
        "conductor_enabled": "✅ Enabled — click to disable",
        "conductor_disabled": "❌ Disabled — click to enable",
        "conductor_apply_to": "Apply to:",
        "conductor_all_presets": "All presets",
        "conductor_experimental": "⚠ Experimental Feature",
        "conductor_warning_text": "AI Conductor controls parameters for each chunk.\nResults may be unexpected — especially\nif the reference voice is recorded in a neutral\nor unsuitable mood.",
        "conductor_dont_show": "Don't show again",
        "conductor_understood": "Got it",
        "conductor_rewrite_on": "✅ Text Style — click to disable",
        "conductor_rewrite_off": "❌ Text Style — click to enable",
        "conductor_rewrite_desc": "AI will rework the text to a given genre or mood\nbefore generation. Engine parameters are assigned to the new text.",
        "conductor_style_prompt": "Style prompt:",
        "conductor_negative_prompt": "Negative prompt (what to avoid):",
        "conductor_provider_label": "Provider: {}",
        "conductor_provider_none": "Provider: not configured",
        "btn_save": "✓  Save",
        "btn_cancel_dialog": "Cancel",

        # ── Updater ──
        "update_installed": "Update to version {} installed.",
        "update_changelog": "\n\nChangelog:\n{}",
        "update_restart": "\n\nThe app will restart after clicking OK.",
        "update_partial": "Some files could not be updated.\nCheck your connection.",
        "update_no_updates": "You have the latest version {}",
        "update_available": "Version {} available.\nCurrently on {}.\n",
        "update_whats_new": "\nWhat's new:\n{}\n",
        "update_confirm": "\nUpdate?",
        "update_title": "🆕 Update Available",
        "update_done_title": "✅ Done",
        "update_partial_title": "⚠ Partial Update",
        "update_no_title": "✅ No Updates",
        "update_error_title": "❌ Error",

        # ── UI Language Switch ──
        "lang_ui_label": "UI",

        # ── Text size slider ──
        "tip_font_size": "Text size in the input field",

        # ── Theme switch ──
        "tip_theme": "Toggle theme (dark/light)",
        "theme_title": "Theme",

        # ── AI Providers (labels / notes) ──
        "prov_groq": "Groq (VPN required in Russia)",
        "prov_openrouter": "OpenRouter (works in Russia without VPN)",
        "prov_proxy": "Russian proxy (no VPN needed)",
        "cat_openrouter_notes": "Works from Russia without VPN. Hundreds of models.",
        "cat_together_notes": "Many open models, fast.",
        "cat_mistral_notes": "Official Mistral API.",
        "cat_deepinfra_notes": "Cheap GPU inference models.",
        "cat_vsegpt_label": "VseGPT (Russia)",
        "cat_vsegpt_notes": "Russian aggregator, payment in rubles.",
        "cat_aitunnel_label": "AITUNNEL (Russia)",
        "cat_aitunnel_notes": "Russian proxy, payment in rubles.",
        "cat_proxyapi_label": "ProxyAPI (Russia)",
        "cat_proxyapi_notes": "Russian OpenAI proxy, payment in rubles.",
        "prov_reason_active": "Active, used first",
        "prov_reason_hidden": "Hidden by user",
        "prov_reason_no_key": "Skipped — no API key",
        "prov_reason_fallback": "Available as fallback",

        # ── Misc ──
        "time_today": "today {}",
        "time_yesterday": "yesterday {}",
        "time_format_m_s": "{}m {}s",
        "time_format_s": "{}s",

        # ── AI Chat Window ──
        "chat_win_title": "💬 AI Chat — XTTS Studio",
        "chat_header": "AI Chat",
        "chat_btn_new_chat": "＋ New chat",
        "chat_btn_delete_chat": "🗑 Delete chat",
        "chat_search_label": "Search: Ctrl+F",
        "chat_btn_down": "↓ Down",
        "chat_btn_export": "⬇ Export",
        "chat_btn_settings": "⚙ Settings",
        "chat_ready": "Ready",
        "chat_btn_improve": "✨ Improve",
        "chat_btn_from_editor": "📋 From editor",
        "chat_btn_clear": "🧹 Clear",
        "chat_new_chat_title": "New chat",
        "chat_welcome": "Ask AI about the text, narrator, TTS, or improve the text for voiceover.",
        "chat_placeholder_input": "Type a message…",
        "chat_hint_default": "Enter — send · Shift+Enter — new line · Ctrl+F — search",
        "chat_hint_editor": "Enter — send · Ctrl+Enter — send without comment · Shift+Enter — new line",
        "chat_hint_editor2": "Enter — send · Ctrl+Enter — without comment · ✕ — cancel",
        "chat_editor_preview_title": "📋 Text from editor",
        "chat_new_reply_notice": "↓ New reply — click to scroll",
        "chat_btn_cancel": "Cancel",
        "chat_btn_ok": "OK",
        "chat_prompt_editor_comment": "Text from editor:\n{}\n\nComment:\n{}",
        "chat_display_with_comment": "{}\n\nComment:\n{}",
        "chat_err_save_history": "Failed to save history: {}",
        "chat_clear_title": "Clear chat",
        "chat_clear_msg": "Clear all messages in the current chat?",
        "chat_clear_done": "Current chat history cleared",
        "chat_session_loaded": "Session loaded",
        "chat_err_switch_session": "Session switch error: {}",
        "chat_created_new": "New chat created",
        "chat_delete_title": "Delete chat",
        "chat_delete_msg": "Delete chat \u00ab{}\u00bb permanently?",
        "chat_deleted": "Chat deleted",
        "chat_author_you": "You",
        "chat_role_system": "System",
        "chat_meta_format": "{} · {} · ≈{} tok.",
        "chat_msg_copied": "Message copied",
        "chat_err_copy": "Failed to copy: {}",
        "chat_selection_cleared": "Selection cleared",
        "chat_msg_selected": "Message selected · press «→» on it to send to the editor",
        "chat_sent_to_editor_sys": "Text sent to the editor ({} chars)",
        "chat_sent_to_editor": "✅ Text sent to the TTS editor",
        "chat_err_generic": "Error: {}",
        "chat_ctx_copy": "📋 Copy",
        "chat_ctx_to_editor": "📝 To TTS editor",
        "chat_ctx_to_input": "↩ To chat input",
        "chat_ai_typing": "AI is typing",
        "chat_ai_typing_status": "AI is typing...",
        "chat_token_counter": "Input: ≈{} tok. · Chat: ≈{} tok.",
        "chat_reply_received": "Reply received",
        "chat_unknown_error": "Unknown error",
        "chat_ai_unavailable": "AI is temporarily unavailable. Try again later.",
        "chat_err_ai_status": "AI error: {}",
        "chat_err_ai_title": "AI Error",
        "chat_generation_stopped": "Generation stopped",
        "chat_ai_edit_off_title": "AI edit is off",
        "chat_ai_edit_off_msg": "Enable the ✨ AI edit checkbox in the main window.",
        "chat_err_title": "Error",
        "chat_err_get_text": "Failed to get text from the editor: {}",
        "chat_empty_title": "Empty text",
        "chat_empty_editor": "The editor text is empty.",
        "chat_improving": "Improving text for TTS...",
        "chat_improved_sys": "Text improved for TTS: {} → {} characters",
        "chat_text_updated": "Text updated in the editor",
        "chat_err_insert": "Failed to insert the result into the editor: {}",
        "chat_err_insert_status": "Result insertion error",
        "chat_err_improve": "Text improvement error: {}",
        "chat_err_no_editor_fns": "Editor access functions are not initialized.",
        "chat_no_text_in_editor": "No text in the editor.",
        "chat_no_text_top": "No text in the upper window.",
        "chat_editor_source_label": "Text from editor",
        "chat_editor_hint": "Select a fragment above and press «To editor». Below you can write a comment for AI.",
        "chat_editor_win_hint": "Enter — send and close · Shift+Enter — new line · Ctrl+Enter — send and close · Ctrl+Shift+Enter — paste to input · Ctrl+F — search",
        "chat_source_label": "Source",
        "chat_source_updated": "Source updated from the editor",
        "chat_err_update_text": "Failed to update text: {}",
        "chat_empty_selection_title": "Empty selection",
        "chat_empty_selection_msg": "Select a text fragment in the upper window.",
        "chat_editor_overwritten_sys": "Editor overwritten with the selected fragment ({} characters)",
        "chat_editor_overwritten": "Editor overwritten with selection",
        "chat_err_overwrite": "Failed to overwrite the editor: {}",
        "chat_btn_to_editor": "↩ To editor",
        "chat_comment_label": "Comment for the text",
        "chat_what_to_do": "What to do with the text?",
        "chat_comment_placeholder": "Comment for the text…",
        "chat_stats_format": "Source: {} chars · Comment: {} chars · Total: {} chars",
        "chat_editor_hint3": "Enter — send and close · Esc — close",
        "chat_source_comment_empty": "Source and comment are empty.",
        "chat_inserted_to_input": "Text pasted to the input field",
        "chat_sent_to_chat": "Text sent to the chat",
        "chat_improving_fallback": "Improving text… (auto-fallback on limit)",
        "chat_done_chars": "Done: {} → {} chars",
        "chat_btn_send": "➤ Send",
        "chat_btn_to_input": "↪ To input field",
        "chat_btn_close_x": "✕ Close",
        "chat_err_paste": "Paste error: {}",
        "chat_editor_empty": "Editor is empty",
        "chat_placeholder_comment": "Add a comment… or press Enter to send as is",
        "chat_editor_ready": "Editor text is ready · add a comment or press Enter",
        "chat_export_title": "Export",
        "chat_export_empty": "The current chat has no messages.",
        "chat_export_dialog_title": "Export current chat",
        "chat_exported": "Chat exported: {}",
        "chat_export_err_title": "Export error",
        "chat_search_win_title": "History search",
        "chat_search_header": "Search chat history",
        "chat_search_hint": "Enter — search · Double click / Enter — open · Esc — close · Ctrl+F — focus search field",
        "chat_search_enter_query": "Enter a query",
        "chat_search_match_title": "Match in title: {}",
        "chat_search_found": "Found: {}",
        "chat_search_opened": "Chat opened from search results",
        "chat_settings_title": "AI Settings",
        "chat_err_load_gpt": "Failed to load engine.gpt_client: {}",
        "chat_settings_win_title": "⚙ AI Settings",
        "chat_provider_edit": "Edit provider",
        "chat_provider_add": "Add provider",
        "chat_field_label": "Name",
        "chat_field_url": "Endpoint URL (/v1/chat/completions)",
        "chat_field_models": "Models (one per line)",
        "chat_field_fallback": "Fallback model (on limit)",
        "chat_field_headers": "Extra headers (optional, «Key: Value» format, one per line)",
        "chat_url_empty": "URL cannot be empty",
        "chat_need_model": "Specify at least one model",
        "chat_btn_cancel_x": "✕ Cancel",
        "chat_btn_save": "💾 Save",
        "chat_catalogue_title": "Catalogue",
        "chat_catalogue_unavailable": "Provider catalogue is unavailable.",
        "chat_catalogue_win": "Provider catalogue",
        "chat_catalogue_header": "Choose a provider from the catalogue",
        "chat_catalogue_hint": "Double click or «Add» — connect the provider",
        "chat_already_added": "  ✓ already added",
        "chat_catalogue_select": "Choose a provider from the list",
        "chat_key_hint": "{}  |  Key: {}",
        "chat_select_provider": "Choose a provider.",
        "chat_provider_exists": "Provider \u00ab{}\u00bb is already added.",
        "chat_loading_models": "Loading model list...",
        "chat_models_failed": "Models failed to load — the provider will be added without a model list. Enter manually.",
        "chat_models_loaded": "Models loaded: {}",
        "chat_btn_add": "＋ Add",
        "chat_providers_header": "AI Providers",
        "chat_key_set": "✅ key set",
        "chat_key_none": "❌ no key",
        "chat_active_label": "ACTIVE",
        "chat_model_label": "Model",
        "chat_models_empty": "Model list is empty.",
        "chat_saved": "💾 Saved",
        "chat_check_unavailable": "Check unavailable",
        "chat_checking_key": "Checking key...",
        "chat_btn_check": "🔑 Check",
        "chat_btn_activate": "✓ Set active",
        "chat_provider_delete_title": "Delete provider",
        "chat_provider_delete_msg": "Delete \u00ab{}\u00bb permanently?",
        "chat_provider_hide_title": "Hide provider",
        "chat_provider_hide_msg": "Hide \u00ab{}\u00bb? Key and model will be forgotten.",
        "chat_btn_hide": "🚫 Hide",
        "chat_btn_catalogue": "🌐 Catalogue",
        "chat_free_mode": "💬 Free chat",
        "chat_free_mode_on": "💬 Free chat ✓",
        "chat_mode_free": "Mode: free chat",
        "chat_mode_editor": "Mode: text editor",
        "chat_mode_free_small": "mode: free chat",
        "chat_mode_editor_small": "mode: editor",
        "chat_switch_mode": "switch mode",
    },
}


def t(key: str, *args) -> str:
    """Return translated string for *key* in the current UI language.
    Positional arguments are forwarded to ``str.format`` if the string
    contains ``{}`` placeholders.
    """
    text = LANGUAGES.get(_current_lang, LANGUAGES["ru"]).get(key)
    if text is None:
        text = LANGUAGES["ru"].get(key, key)
    if args:
        try:
            return text.format(*args)
        except (IndexError, KeyError):
            return text
    return text



def set_language(lang: str) -> None:
    global _current_lang
    if lang in LANGUAGES:
        _current_lang = lang


def _load_saved_language() -> None:
    """Подключение сохранённого языка интерфейса при импорте модуля.

    Читает ui_language из settings.json (лежит рядом с i18n.py в корне
    проекта), чтобы весь интерфейс — включая виджеты, создаваемые до
    вызова apply_settings() — сразу строился на выбранном языке.
    """
    try:
        settings_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "settings.json"
        )
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        lang = data.get("ui_language")
        if lang in LANGUAGES:
            set_language(lang)
    except Exception:
        pass  # нет settings.json / повреждён — остаёмся на языке по умолчанию


_load_saved_language()


def get_language() -> str:
    return _current_lang
