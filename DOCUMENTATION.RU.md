# 📖 XTTS Studio — Документация

**[English](./DOCUMENTATION.EN.md)** · **[Русский](./DOCUMENTATION.RU.md)**

Технический справочник: архитектура, функции, данные, дерево проекта.

> Продающий обзор: **[README.RU.md](./README.RU.md)** · **[README.EN.md](./README.EN.md)**  
> Справочник API: **[unified_function_reference.RU.md](./unified_function_reference.RU.md)** · **[EN](./unified_function_reference.EN.md)**

---

## Содержание

1. [О продукте](#о-продукте)
2. [Быстрый старт](#быстрый-старт)
3. [Пайплайн](#пайплайн)
4. [Возможности (подробно)](#возможности-подробно)
5. [RVC — улучшение голоса](#rvc--улучшение-голоса)
6. [Ядро TTS (`engine/tts/`)](#ядро-tts-enginettss)
7. [AI-модуль](#ai-модуль)
8. [Словарь произношений](#словарь-произношений)
9. [Диагностика и self-heal](#диагностика-и-self-heal)
10. [Система обновлений](#система-обновлений)
11. [Требования](#требования)
12. [Файлы данных и конфиги](#файлы-данных-и-конфиги)
13. [Структура проекта](#структура-проекта)
14. [Модули engine/ по зонам](#модули-engine-по-зонам)
15. [Разработка](#разработка)
16. [Сторонние компоненты / лицензии](#сторонние-компоненты--лицензии)

---

## О продукте

**XTTS Studio** — портативное полностью офлайн-приложение text-to-speech и клонирования голоса на **XTTS v2**.

- Точка входа: `XTTS Studio.exe` → BAT → `python\runtime\python.exe` → `gui.py`
- Зависимости: `python\xtts_env`
- Архитектура: тонкий entry · ядро `engine/` (без GUI) · UI `engine/gui/`

Опциональный **AI-модуль**: облачные OpenAI-compatible провайдеры и/или **локальные LLM** (без ключей, офлайн).

---

## Быстрый старт

1. Скачайте и распакуйте архив  
2. **Не** используйте путь с кириллицей  
3. Запустите `XTTS Studio.exe`  
4. Выберите референс (~10–20 с)  
5. Введите текст  
6. **🚀 ГЕНЕРИРОВАТЬ**  
7. Результат → `outputs/` (или **🎵 Аудио**)

```text
✔  C:\XTTS\
✘  C:\Новая папка\XTTS\
```

---

## Пайплайн

```text
Референс → автообработка → библиотека голосов (+ кэш эмбеддингов)
   ↓
Текст → (опц. GPT improve на сыром тексте) → normalize → word replacer
   ↓
(опц.) AI Conductor rewrite / per-chunk map
   ↓
Chunker (SBD / инициалы / merge-split) → (опц.) prosody / smart pauses*
   ↓
На каждый чанк:
   · XTTS inference (QC-ретраи при включённом QC)
   · (опц.) RVCPostProcessor на WAV чанка
   · ключ кэша чанка учитывает настройки RVC
   ↓
Merge + паузы → loudness normalize → de-esser → WAV / MP3
```

\* Smart pauses / prosody **пропускаются**, если активен AI Conductor (паузы из `conductor_map`).

**Важно:** RVC работает **на каждый чанк** после XTTS (не только на финальный файл). Де-эссер — один раз на **склеенном** экспорте.

---

## Возможности (подробно)

### Синтез и клонирование

- Полностью офлайн TTS  
- Portable-папка  
- Клонирование с короткого референса  
- Библиотека голосов + кэш эмбеддингов  
- Без жёсткого лимита длины текста  
- RU/EN контент  
- **CUDA по запросу**: CPU по умолчанию; **⚙ Настройки → Ускорение**  

### Интерфейс

- **⚙ Настройки**: обновления · ускорение CPU/GPU · диагностика  
- Темы dark/light + конструктор; immersive titlebar  
- Раскладка, dock-панели, auto-save  
- UI **RU / EN**  
- Размер шрифта ввода, neon glow  
- Авто-обновления: SHA256, backup, rollback  

### Текст

| Модуль | API | Заметки |
|--------|-----|---------|
| `normalizer.py` | `TextNormalizer.normalize`, `safe_character_filter` | Числа→слова, ординалы, время, аббревиатуры, **ёфикация** |
| `word_replacer.py` | `WordReplacer.apply`, `add_rule`, `remove_rule` | **builtin → auto → ai_corrected → custom**; JSON-only; бэкапы ≤30 |
| `chunker.py` | `TextChunker.chunk_text` | max 175 / target 150 / min 50; SBD для инициалов |
| `prosody_layer.py` | `ProsodyLayer.process` | Семантические паузы; **off при Conductor** |
| `smart_pauses.py` | `SmartPauseEngine.get_pause_ms` | Паузы merge; **off при Conductor** |

### Качество

- 4 пресета; UI вкладок **RVC · Обрезка · Вывод · XTTS** (sticky)  
- `quality_settings_last_tab` в `settings.json`  
- QC, де-эссер (на merge), trim, кэш чанков (ключ включает RVC)  

**Сохранение (проверено):** `settings_ui.save_settings()` пишет всё дерево `quality_params` (включая `rvc_*`) через **read-modify-write**. Живые сессии уже хранят `rvc_enable`, `rvc_model`, `rvc_index_rate`, `rvc_pitch_shift`, `rvc_f0_method`.

### Прочее

Очередь задач, batch TXT, история, подсветка чанка, статистика, WAV/MP3.

---

## RVC — улучшение голоса

Опциональный **Retrieval-based Voice Conversion** после XTTS. Три слоя: **setup** · **catalog** · **pipeline** + GUI dropdown.

### Классы пайплайна (`engine/rvc_pipeline.py`)

| Имя | Роль |
|-----|------|
| `RVCPipelineError` | Ошибки RVC |
| `RVCPostProcessor` | `.pth` (+ `.index`), `rvc-python` |
| `XTTSWithRVCPipeline` | XTTS → temp → RVC → финал |

**Где вызывается:** `engine/tts/__init__.py` → `run_tts()`:

1. `rvc_*` вынимаются из preset (нельзя в XTTS `inference`)  
2. Попадают в **ключ кэша** (`_rvc_*`)  
3. После XTTS+QC: `get_rvc_processor().run_inference_via_lib(chunk, chunk, ...)`  
4. Ошибка RVC → log, **XTTS-чанк сохраняется**  

API: `set_params(f0up_key=..., f0method=..., index_rate=...)` + `infer_file(in, out)` — **ровно 2 аргумента**.

Facade: `tts_runner.py` реэкспортирует `run_tts`.  
GUI: `generation.py` → `Task` с полным `quality_params` (включая RVC).

### Каталог (`engine/rvc_catalog.py`)

| Путь | Назначение |
|------|------------|
| `json/rvc_catalog_seed.json` | Офлайн seed (**28** HF-ориентированных записей) |
| `models/rvc/` | Скачанные `.pth` / `.index` |
| `models/rvc/catalog_cache.json` | Кэш remote-каталога |

**API:** `get_catalog`, `search_catalog` / `search_voice_models`, `download_model`, `is_downloaded`, `local_model_path`, `delete_local_model`, `open_model_page`.  
GitHub raw catalog: 1 попытка, cooldown **6 ч** после 404.  
Entry: обязательно `id`, `name`, `url`.

### Установка (`engine/env_core/rvc_setup.py`)

`rvc_status` · `install_rvc` · `uninstall_rvc` · `detect_torch_build`.  
Windows: prebuilt fairseq wheels, `--no-deps` + METADATA, constraint к установленному torch, retry без `--upgrade` при WinError 5, auto-heal missing modules, force PyYAML.

### GUI (`engine/gui/rvc_model_dropdown.py`)

`RVCModelDropdown`: place-popup при `grab_set`, 🗑 / ⬇ / ✕ / 🔗, debounced search, scroll.

### Пресеты (`engine/gui/presets.py`)

Sticky tabs: **RVC · Обрезка · Вывод · XTTS**.  
Вывод: формат + **де-эссер** + QC.  
Ключи: `rvc_enable`, `rvc_model`, `rvc_index_rate`, `rvc_pitch_shift`, `rvc_f0_method` + `quality_settings_last_tab`.

---

## Ядро TTS (`engine/tts/`)

| Символ | Файл | Роль |
|--------|------|------|
| `run_tts(...)` | `tts/__init__.py` | Полный job |
| `get_tts()` / `get_rvc_processor()` | `tts/__init__.py` | Lazy singleton'ы |
| `tts_runner.py` | корень | Re-export |
| QC helpers | `tts/qc.py` | repeats, duration, trim, loudness |
| `export_audio` | `tts/export.py` | Merge + de-esser + WAV/MP3 |
| `DeEsser` / `create_de_esser` | `engine/de_esser.py` | 4–9 kHz split-band |

QC: до **3** попыток при `qc_enabled`. Де-эссер: `export_audio` при `de_esser_intensity > 0`.

---

## AI-модуль

### Conductor — `ai_conductor.py`

`conduct(...)` → list / `{rewritten_text, chunks}` / None / fallback.  
Диапазоны: temperature 0.50–0.90, top_p 0.70–0.95, speed 0.75–1.25, pause 0–1200.  
`rewritten_text` только при `rewrite_enabled=True`. Транспорт: `_call_with_chain`.

### GPT client — `gpt_client.py`

`gpt_settings.json`. Цепочка: **active → builtins с ключом → custom**.  
`_call_with_chain`, `chat`, `improve_for_tts`, key library, `get_chain_diagnostics`.  
Исключения: `AIUnavailable`, rate limit / network.

### Локальные LLM — `local_llm_client.py`

GGUF in-process (`llama-cpp-python`). Каталог HF, download+resume, `call_local_llm` (CPU max_tokens ≤256). GPU→CPU fallback + broken backend.  
`local_env_section.py` — UI/хелперы.

### `gui.py`

Single-instance, `_ensure_dependencies_before_startup`, recovery UI, `main` + `updater.check_startup_health`.  
`llama_cpp` / `rvc_python` **не** critical.

---

## Словарь произношений

`WordReplacer`. Истина: `word_rules.json`.  
Приоритет: **builtin → auto → ai_corrected → custom**.  
Бэкапы ≤30. UI **📖 Словарь**. Conductor может писать `ai_corrected`.

---

## Диагностика и self-heal

Пакет **`engine/env_core/`** (re-export в `__init__.py` / facade `env_setup`).

| Модуль | Главное |
|--------|---------|
| `cpu_gpu.py` | `detect_cpu`, `detect_gpu` |
| `diagnostics.py` | `run_full_diagnostics` (изолированный процесс), `get_broken_critical`, `scan_for_garbage` + quarantine, `run_error_recovery`; CRITICAL vs OPTIONAL=`{llama_cpp,rvc_python}` |
| `torch_setup.py` | `install_torch` / `torch_status` / variant cu118\|cpu |
| `llama_setup.py` | cuda/vulkan/cpu, broken backends, smoke test |
| `rvc_setup.py` | install/probe RVC |

Startup: `gui.py` → full diagnostics → recovery только для critical.

---

## Система обновлений

**`engine/updater.py`** (не класс `Updater`).

| Функция | Описание |
|---------|----------|
| `check_update()` | Сравнение версий + files + sha256 + manual reinstall |
| `apply_update(...)` | staging → verify → backup → live → removed_files → marker |
| `check_startup_health()` | `ok` / `first_attempt` / `rolled_back` |
| `confirm_update_success()` | После успешного открытия GUI |
| `rollback_update()` / `restart()` | Откат / рестарт |

Отмена работает до подмены файлов. При `local < min_app_version` — полная переустановка.

---

## Требования

| | CPU | CUDA |
|---|---|---|
| ОС | Windows 10/11 x64 | то же |
| RAM | 8+ ГБ | 8+ ГБ |
| GPU | — | NVIDIA 4+ ГБ VRAM, CC 6.0+ |

---

## Файлы данных и конфиги

| Файл | Назначение |
|------|------------|
| `settings.json` | сессия, `quality_params` (вкл. **rvc_***), `quality_settings_last_tab`, тема, язык |
| `gpt_settings.json` | AI-провайдеры, ключи, модели |
| `word_rules.json` | словарь |
| `word_rules_backups/` | бэкапы словаря |
| `chat_history.json` / `history.json` | чат / генерации (history max 100) |
| `version.json` / `checksums.txt` | обновления |
| `json/rvc_catalog_seed.json` | офлайн RVC seed (28) |
| `models/rvc/` | RVC-модели + catalog_cache |
| `.llama_broken_backends.json` / `.known_safe_files.json` | backend / diagnostics |

---

## Полная структура проекта (как в EN)

**Точка входа:** `XTTS Studio.exe` → BAT → `python\runtime\python.exe` → `gui.py` → `python\xtts_env`

```text
XTTS Studio (portable)
│
├── gui.py                        ← entry point: launches the interface only
├── i18n.py                       ← UI localization (RU / EN)
├── settings.json                 ← session settings (auto)
├── gpt_settings.json             ← AI provider, keys, models (auto)
├── word_rules.json               ← pronunciation dictionary
├── chat_history.json             ← AI chat session history
├── history.json                  ← generation history
├── version.json                  ← version and update-system data
├── env_cache.cfg                 ← environment-scan cache
├── generate_version_manifest.py  ← generates version manifest for updates
├── theme_settings.json           ← user theme/color scheme
├── checksums.txt                 ← SHA256 for update verification
├── .llama_broken_backends.json   ← broken llama.cpp backends (auto)
│
├── engine/                       ═══ TECHNICAL CORE (no tkinter) ═══
│   │
│   │   ── generation pipeline ──
│   ├── tts_runner.py
│   ├── chunker.py
│   ├── normalizer.py
│   ├── word_replacer.py
│   ├── word_replacer_window.py
│   ├── text_utils.py
│   ├── smart_pauses.py
│   ├── prosody_layer.py
│   ├── de_esser.py
│   ├── rvc_pipeline.py           ← RVC post-process (rvc-python)
│   ├── rvc_catalog.py            ← RVC catalog / download / seed / search
│   │
│   │   ── AI module ──
│   ├── ai_conductor.py
│   ├── chat_window.py
│   ├── gpt_client.py
│   ├── local_llm_client.py
│   ├── local_env_section.py
│   ├── env_setup.py
│   │
│   │   ── voice and audio ──
│   ├── reference_processor.py
│   ├── voice_manager.py
│   ├── audio_backend.py
│   │
│   │   ── infrastructure ──
│   ├── task_manager.py
│   ├── task_models.py
│   ├── batch_window.py
│   ├── updater.py
│   ├── paths.py
│   ├── settings_store.py
│   ├── history_store.py
│   ├── output_naming.py
│   ├── text_tools.py
│   └── logging_utils.py
│
│   ├── tts/
│   │   ├── __init__.py           ← generation core
│   │   ├── cache.py
│   │   ├── device.py
│   │   ├── export.py
│   │   ├── qc.py
│   │   └── utils.py
│   │
│   └── gui/                      ═══ INTERFACE (tkinter / customtkinter) ═══
│       ├── main_window.py
│       ├── layout.py
│       ├── theme.py
│       ├── theme_manager.py
│       ├── colors.py
│       ├── widgets.py
│       ├── tooltip.py
│       ├── gradient.py
│       ├── neon_widgets.py
│       ├── helpers.py
│       ├── header_panel.py
│       ├── voice_panel.py
│       ├── player.py
│       ├── queue_panel.py
│       ├── batch_panel.py
│       ├── chat_panel.py
│       ├── word_replacer_panel.py
│       ├── console.py
│       ├── textbox.py
│       ├── toolbar.py
│       ├── statusbar.py
│       ├── generation.py
│       ├── presets.py            ← quality presets + settings window (tabs)
│       ├── rvc_model_dropdown.py ← RVC model picker + search UI
│       ├── settings_ui.py
│       ├── styles_menu.py
│       ├── updates.py
│       ├── chat_window.py
│       ├── ai_conductor.py
│       ├── ai_status_window.py
│       ├── history_window.py
│       ├── output_window.py
│       ├── batch_window.py
│       ├── word_replacer_window.py
│       ├── dialogs.py
│       └── chat_window/          ═══ modular AI chat ═══
│           ├── ...
│           └── engine/
│
├── json/
│   └── rvc_catalog_seed.json     ← offline RVC seed catalog
│
├── models/
│   ├── xtts_v2/                  ← XTTS model (offline)
│   └── rvc/                      ← RVC .pth/.index + catalog_cache.json
├── library/<voice_name>/         ← voice profiles + embedding cache
├── outputs/_cache/               ← finished files + chunk cache
├── logs/
├── reference/
├── word_rules_backups/
├── test/                         ← pytest
├── tools/
├── ffmpeg/bin/
└── python/
    ├── xtts_env/
    └── runtime/                  ← Python 3.11 portable
```

> `engine/gui/chat_window.py` assembles the chat UI; `engine/gui/chat_window/` holds submodules and nested `engine/` for generation/sessions.

---


---

## Модули engine/ по зонам

### Пайплайн генерации
`tts_runner` (facade) · `tts/*` · `chunker` · `normalizer` · `word_replacer` · `smart_pauses` / `prosody_layer` (off при Conductor) · `rvc_pipeline` · `rvc_catalog` · `de_esser`

### AI
`ai_conductor` · `gpt_client` · `local_llm_client` · `local_env_section` · chat UI

### Голос
`reference_processor` (trim + SNR) · `voice_manager` · `de_esser`

### Инфраструктура
`task_manager` · `history_store` · `updater` · `settings_ui` · `i18n` · `env_core/*`

---

## Разработка

AI-assisted tooling; pytest в `test/`; утилиты в `tools/`.  
Архитектура и UI-полировка — в т.ч. с Arena.ai Agent Mode.

---

## Сторонние компоненты / лицензии

- **XTTS v2** (Coqui) — [CPML](https://coqui.ai/cpml)  
- Лицензия проекта: [LICENSE.md](./LICENSE.md)  
- Community RVC-модели — по своим лицензиям  

---

## Поддержка

**BTC:** `bc1qz78u3lvagt3v886359glv57ct6rnlh506wjmdy`

---

**XTTS Studio** · by EXIZ10TION · [README RU](./README.RU.md) · [README EN](./README.EN.md) · [EN docs](./DOCUMENTATION.EN.md) · [License](./LICENSE.md)
