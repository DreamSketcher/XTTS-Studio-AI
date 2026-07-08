<div align="center">

# 🎙️ XTTS Studio

**A portable, fully offline voice-cloning and text-to-speech app built on XTTS v2**

[![Windows](https://img.shields.io/badge/Windows-10%2F11%20x64-0078D6?logo=windows&logoColor=white)]()
[![Offline](https://img.shields.io/badge/100%25-Offline-2da44e)]()
[![Portable](https://img.shields.io/badge/Portable-no%20install-orange)]()
[![RU/EN](https://img.shields.io/badge/UI-RU%20%2F%20EN-58a6ff)]()
[![Themes](https://img.shields.io/badge/Themes-Dark%20%2F%20Light-7c3aed)]()

</div>

---

## 🚀 About

**XTTS Studio** is a fully offline text-to-speech and voice-cloning tool.
It runs in portable mode, needs no installation, and never touches the internet.
The AI module is optional and connects through any OpenAI-compatible provider.

---

## 📥 Download

> ⚠️ Google Drive may show a "file too large to scan" warning before download — that's expected, the file just isn't scanned by Google's antivirus due to its size, not because of any threat.

| Version | Size | Link |
|---|---|---|
| ⚙️ CPU-only | 5 GB | [📥 Download XTTS Studio (Google Drive)](https://drive.google.com/file/d/1GINiNWjvMMayfOdK6JiSzIqVU6UhpG5x/view?usp=drive_link) |
| 🚀 NVIDIA CUDA | 10 GB | [📥 Download XTTS Studio (GitHub Releases)](https://github.com/DreamSketcher/XTTS-Studio-portable-/releases) |

📜 **License:** [LICENSE.md](./LICENSE.md) — free to use, attribution to the author required

---

## ✨ Features

### 🎤 Synthesis and cloning
- Fully offline — no external requests
- Portable — a single folder, any Windows PC
- Voice cloning from a 10–20 second reference clip
- Voice library with cached speaker embeddings
- No limit on text length
- Automatic RU/EN language switching within a single text
- CUDA/CPU auto-detection with a CPU fallback if the graphics card isn't supported

### 🖥 Interface
- 🌗 **Themes:** dark and a soft light ("milk") theme out of the box, plus a built-in **theme constructor** — build your own color scheme, not just toggle presets
- 🌐 **Two UI languages:** Russian and English (RU/EN), including the AI chat and provider settings
- 📐 Adaptive toolbar — panels resize with the window
- ◀ Collapsible left panel that remembers its position
- 🔠 Adjustable text size in the input box (the "Aa" slider)
- All view settings persist between sessions
- 🔄 **Auto-update** — staged download of the new version, integrity check via **SHA256**, automatic backup and rollback on failure, full-reinstall detection via `min_app_version`

### 🧠 Text processing
- Numbers → words, automatically
- Abbreviations → phonetic dictionary (automatic + manual)
- Semantic and punctuation-based pauses, automatically
- Text normalization before generation

### 🎛 Quality control
- 4 presets: ⭐ High Quality / 📖 Narrative / ⚡ Dynamic / 🎭 Expressive
- Fine-grained tuning: temperature, top_p, repetition_penalty, speed, trim
- Chunk-level QC — automatic regeneration on repeats or cut-offs
- De-esser, RMS loudness normalization, automatic silence trimming
- Chunk cache — regenerating the same text doesn't cost time again

### 🤖 AI module (optional)
- **AI Conductor** — analyzes the text and assigns XTTS parameters per chunk
  - Level 1: temperature, speed, and pauses driven by context and intonation
  - Level 2: rewriting the text for a target genre or mood (with a negative prompt)
  - The two levels are fully independent — toggling one never affects the other (the check is duplicated in both the conductor's logic and the runner)
- **AI chat** — a built-in chat assistant with session history and search
  - Text-editor mode and free-chat mode
  - An "Improve" button — a technical rewrite of the text to make it more TTS-friendly
  - Collapsible provider-setting cards (accordion style) instead of one long form
- **"AI Status" window** — shows the provider chain and each provider's live status
- Provider chain support: Groq, OpenRouter, local (offline) LLMs, and custom OpenAI-compatible providers
- A provider catalog and key library; the provider you pick is always first in the chain
- **Local LLMs (offline, no keys, no internet)**
  - Automatic scan of your PC's environment (GPU presence, CUDA, VRAM/RAM) to pick a compatible configuration
  - Automatic installation of the libraries the selected model needs — no manual pip wrangling
  - A built-in catalog of supported local models, downloadable right from the interface
  - Bring your own model — just point it at a folder with the model files

### 📋 Other
- Cancelable task queue
- Batch processing of TXT files
- Generation history with text recall
- Real-time highlighting of the current chunk
- Stats: time, chunks, voice, speed
- Auto-saved settings between sessions
- Export to WAV and MP3

---

## 🖼 Screenshots

<p align="center">
  <img src="images/main.PNG" width="45%" />
  <img src="images/ai-assist.PNG" width="45%" />
</p>
<p align="center">
  <img src="images/mail-light.PNG" width="45%" />
  <img src="images/ai-settings.PNG" width="45%" />
  <img src="images/settings.PNG" width="45%" />
</p>

---

## 🚀 Quick start

1. Download and unpack the archive
2. Don't use a path with Cyrillic characters
3. Run `XTTS Studio.exe`
4. Pick or upload a voice reference
5. Enter your text
6. Click **🚀 GENERATE**
7. The result is saved to `outputs/` — the **🎵 Audio** button

---

## ⚙️ How it works

```
Reference → auto-processing → voice library
   ↓
Text → normalization → numbers to words → abbreviations
   ↓
(optional) AI improvement / text rewrite
   ↓
Split into chunks → pause placement
   ↓
(optional) AI Conductor — per-chunk parameters
   ↓
Generation with quality control and caching
   ↓
Assembly → loudness normalization → de-esser → WAV / MP3
```

---

## 🧠 Pronunciation dictionary

Examples of built-in rules:

```
AI      → ay-eye
CPU     → C-P-U
GPU     → G-P-U
OpenAI  → Open-Eh-Eye
```

The dictionary grows automatically during generation, and when the **AI Conductor** is enabled it also helps the dictionary along: it analyzes transliteration and adds corrections into the `ai_corrected` category itself — so an active conductor effectively keeps "training" the dictionary alongside generation.
Edit it with the **📖 Dictionary** button (add, change, or remove rules).

- **Prioritized rule categories:** `builtin → auto → ai_corrected → custom` — a more specific rule overrides a more general one
- **Diagnostic dry-run mode** — preview what would change without writing to the file
- **Automatic timestamped backups** in `word_rules_backups/` before every save
- Metadata on every entry (category, source)

---

## 💻 Requirements

| | CPU version | CUDA version |
|---|---|---|
| OS | Windows 10/11 x64 | Windows 10/11 x64 |
| Memory | 8+ GB RAM | 8+ GB RAM |
| GPU | — | NVIDIA, 4+ GB VRAM, Compute Capability 6.0+ |
| Speed | slower than real-time | faster than real-time |

> ℹ️ The CUDA build includes universal dependencies and detects on its own whether your GPU is supported; if not (or CUDA isn't available), it automatically falls back to CPU with no extra setup.

---

## ⚠️ Important

Don't use paths with Cyrillic characters:

```
✔ C:\XTTS\
✘ C:\New Folder\XTTS\
```

---

# 🗂 Full project structure

**Entry point:** `XTTS Studio.exe` → BAT → `python\runtime\python.exe` → `gui.py` → dependencies from `python\xtts_env`

The project has a modular architecture: a thin entry point, a technical core in `engine/` (no GUI dependencies), and an interface layer in `engine/gui/`.

## Project tree

```
XTTS Studio (portable)
│
├── gui.py                        ← entry point: launches the interface only
├── i18n.py                       ← UI localization (RU / EN)
├── settings.json                 ← session settings: presets, theme, language, panel (auto)
├── gpt_settings.json             ← AI provider, keys, models (auto)
├── word_rules.json               ← pronunciation dictionary (builtin/auto/ai_corrected/custom)
├── chat_history.json             ← AI chat session history
├── history.json                  ← generation history
├── version.json                  ← version and update-system data (min_app_version)
├── env_cache.cfg                  ← environment-scan cache (GPU/CUDA/libraries)
├── generate_version_manifest.py  ← generates the version manifest for the update system
├── ProjectAnalyzer.ps1            ← project structure snapshot for AI context between dev sessions
│
├── engine/                       ═══ TECHNICAL CORE (no tkinter) ═══
│   │
│   │   ── generation pipeline ──
│   ├── tts_runner.py             ← thin entry point (logic itself lives in engine/tts/)
│   ├── chunker.py                ← splits text into chunks
│   ├── normalizer.py             ← numbers→words, abbreviations, punctuation
│   ├── word_replacer.py          ← phonetic substitutions, rule categories
│   ├── word_replacer_window.py   ← dictionary-window backend (dry-run, backups)
│   ├── text_utils.py             ← shared text helpers
│   ├── smart_pauses.py           ← pauses between chunks (without the conductor)
│   ├── prosody_layer.py          ← semantic prosody (without the conductor)
│   ├── de_esser.py               ← sibilance suppression
│   │
│   │   ── AI module ──
│   ├── ai_conductor.py           ← AI Conductor (per-chunk parameters + rewrite)
│   ├── chat_window.py            ← chat business logic: providers, session history
│   ├── gpt_client.py             ← AI client: cloud providers, keys, fallback chain
│   ├── local_llm_client.py       ← client for local (offline) LLMs
│   ├── local_env_section.py      ← local AI environment configuration
│   ├── env_setup.py              ← setup/check of the AI module's environment
│   │
│   │   ── voice and audio ──
│   ├── reference_processor.py    ← reference conversion and normalization
│   ├── voice_manager.py          ← voice library
│   ├── audio_backend.py          ← audio init (pygame)
│   │
│   │   ── infrastructure ──
│   ├── task_manager.py           ← multithreaded, cancelable task queue
│   ├── task_models.py            ← Task model
│   ├── batch_window.py           ← batch-processing business logic
│   ├── updater.py                ← Git-based auto-update (no re-downloading the archive), check/apply/restart
│   ├── paths.py                  ← base project directories
│   ├── settings_store.py         ← reads settings.json
│   ├── history_store.py          ← generation-history storage
│   ├── output_naming.py          ← output-file naming
│   ├── text_tools.py             ← text normalization for the GUI
│   └── logging_utils.py          ← file logging
│
│   ├── tts/                      ═══ TTS support utilities ═══
│   │   ├── __init__.py           ← generation core (normalize → chunk → generate → merge)
│   │   ├── cache.py              ← chunk cache (md5)
│   │   ├── device.py             ← CUDA/CPU auto-detection
│   │   ├── export.py             ← WAV/MP3 export
│   │   ├── qc.py                 ← quality control: loop detector, duration validator
│   │   └── utils.py              ← shared TTS helpers
│   │
│   └── gui/                      ═══ INTERFACE (tkinter / customtkinter) ═══
│       │
│       │   ── window core ──
│       ├── main_window.py        ← main window assembly (orchestrator)
│       ├── layout.py             ← layout + collapsible left panel
│       ├── theme.py              ← themes (dark / light) + custom theme constructor, titlebar
│       ├── theme_manager.py      ← applying and switching the theme
│       ├── colors.py             ← both themes' palettes
│       ├── widgets.py            ← widget factories, CTk compatibility
│       ├── tooltip.py            ← tooltips
│       ├── gradient.py           ← gradient background
│       ├── helpers.py            ← shared GUI helpers
│       │
│       │   ── main window panels ──
│       ├── header_panel.py       ← header: Update / AI Status / RU-EN
│       ├── voice_panel.py        ← reference + voice library
│       ├── player.py             ← reference player
│       ├── queue_panel.py        ← task queue
│       ├── batch_panel.py        ← launcher panel for batch processing
│       ├── chat_panel.py         ← launcher panel for the AI chat
│       ├── word_replacer_panel.py← launcher panel for the dictionary window
│       ├── console.py            ← built-in console
│       ├── textbox.py            ← input box: DnD, chunk highlighting, text size
│       ├── toolbar.py            ← adaptive toolbar: File / AI / Output / Action
│       ├── statusbar.py          ← progress bar and status
│       │
│       │   ── GUI logic ──
│       ├── generation.py         ← start/cancel generation, callbacks
│       ├── presets.py            ← quality presets + settings window
│       ├── settings_ui.py        ← saving and applying settings
│       ├── styles_menu.py        ← "Styles" menu
│       ├── updates.py            ← update checking (GUI wrapper)
│       │
│       │   ── standalone windows ──
│       ├── chat_window.py        ← main interface for the AI chat window, built on the modules and core in chat_window/
│       ├── ai_conductor.py       ← AI Conductor window
│       ├── ai_status_window.py   ← "AI Status" window: provider chain
│       ├── history_window.py     ← "History" window
│       ├── output_window.py      ← "Audio" window with a built-in player
│       ├── batch_window.py       ← TXT batch-processing window
│       ├── word_replacer_window.py ← pronunciation dictionary window (dry-run, backups)
│       ├── dialogs.py            ← voice language, help
│       │
│       └── chat_window/          ═══ modular AI chat window (package) ═══
│           ├── chat_window.py    ← chat window assembly
│           ├── chat_messages.py  ← message rendering
│           ├── chat_input.py     ← input field
│           ├── chat_actions.py   ← message actions (copy/delete/read aloud…)
│           ├── chat_editor.py    ← text-editor mode
│           ├── chat_export.py    ← conversation export
│           ├── chat_history.py   ← session list and loading
│           ├── chat_scroll.py    ← scrolling behavior
│           ├── chat_search.py    ← message search
│           ├── chat_settings.py  ← accordion of provider-setting cards
│           ├── chat_typing.py    ← typing indicator
│           ├── custom_widgets.py ← custom chat widgets
│           ├── hotkeys.py        ← chat hotkeys
│           ├── placeholders.py   ← empty-state placeholders
│           ├── state.py          ← shared window state
│           ├── theme_manager.py  ← chat theme
│           ├── theme_settings.py ← chat theme settings
│           ├── ui_utils.py       ← chat UI helpers
│           └── engine/           ← chat logic, decoupled from the UI
│               ├── generation.py ← runs the assistant's reply generation
│               ├── sessions.py   ← chat session management
│               └── utils.py      ← helpers
│
├── models/xtts_v2/               ← model (offline)
├── library/[voice_name]/         ← voice profiles + embedding cache (CPU/CUDA)
├── outputs/_cache/                ← finished files + chunk cache (md5)
├── logs/                         ← error logs
├── reference/                    ← source reference files
├── word_rules_backups/           ← timestamped backups of the pronunciation dictionary
├── test/                         ← pytest: chunker, normalizer, smart pauses, updater
├── tools/                        ← development support utilities
├── ffmpeg/bin/                   ← ffmpeg.exe, ffprobe.exe
└── python/
    ├── xtts_env/                 ← venv with dependencies
    └── runtime/                  ← Python 3.11 portable
```

> ℹ️ `engine/gui/chat_window.py` is the main interface file for the chat window (UI assembly and layout). The `engine/gui/chat_window/` package holds its internals: submodules (messages, input, history, search, export, etc.) plus a nested `chat_window/engine/` with the reply-generation and session logic that `chat_window.py` relies on.

---

## 🔬 engine/ modules by area of responsibility

### Generation pipeline
- **`tts_runner.py`** — a thin entry point; the actual `run_tts()` logic lives in the **`engine/tts/`** package: normalize → word replacer → chunk → conductor → generate → merge. Lazy model loading (a thread-safe singleton), embedding and finished-chunk caching (md5), automatic silence trimming, RMS loudness normalization.
- **`engine/tts/qc.py`** — quality control: loop detector + duration validator, automatic regeneration.
- **`engine/tts/device.py`** — CUDA/CPU auto-detection with a CPU fallback if the GPU isn't supported.
- **`engine/tts/cache.py`** / **`export.py`** — chunk caching and WAV/MP3 export.
- **`chunker.py`** — splits into sentences, cuts long ones, merges short ones, checks for a bad chunk start/end.
- **`normalizer.py`** — numbers→words, abbreviations, punctuation; separate rhythm handling for Latin/Cyrillic abbreviations and CamelCase.
- **`word_replacer.py`** — phonetic substitutions from the dictionary with category priority (`builtin → auto → ai_corrected → custom`), auto-transliteration of terms; **`word_replacer_window.py`** adds a diagnostic dry-run mode and automatic timestamped backups in `word_rules_backups/` before every save.
- **`smart_pauses.py` / `prosody_layer.py`** — pauses and semantic prosody; **both are skipped when the AI Conductor is active** — in that case pauses and the temperature schedule come from `conductor_map`.

### AI module
- **`ai_conductor.py`** — `conduct()`: one call for the whole text, analyzing chunks and returning per-chunk voice parameters (temperature/top_p/repetition_penalty/speed/pause_after_ms). Optionally rewrites the text for style (`rewrite_enabled`) and checks transliteration (`corrections` → `word_rules.json`). On an AI error it falls back to default parameters — generation is never interrupted. Levels 1 and 2 are explicitly gated by flags both in this module and in `tts_runner.py`, so they can never accidentally influence each other.
- **`gui/chat_window.py` + `gui/chat_window/`** — the AI chat window: `chat_window.py` is the main interface file (UI assembly), while the `chat_window/` package holds its submodules: message rendering, input, session history and search, conversation export, text-editor mode and free-chat mode, an accordion of provider settings, hotkeys, a typing indicator. Reply-generation logic and session management live in the nested `chat_window/engine/`. Fully localized (RU/EN).
- **`gpt_client.py`** — the cloud-provider chain (active → built-in → custom), key and model management, provider catalog.
- **`local_llm_client.py`** / **`local_env_section.py`** / **`env_setup.py`** — support for local (offline) LLMs as an alternative to cloud providers: automatic scan of the PC's environment (GPU/CUDA/VRAM), automatic installation of the libraries the selected model needs, a built-in catalog of supported models, and the ability to plug in your own model from a folder.
- **`gui/ai_status_window.py`** — a diagnostic window showing the provider chain and each provider's status.

### Voice and audio
- **`reference_processor.py`** — reference conversion to WAV, SNR check, caching.
- **`voice_manager.py`** — scans `library/`, lists voices, tracks the active voice.
- **`de_esser.py`** — sibilance suppression on the final file.

### Infrastructure
- **`task_manager.py` / `task_models.py`** — a multithreaded generation queue with cancel-by-id.
- **`updater.py`** — the update system: staged download of the new version, integrity check of every file via **SHA256**, automatic backup of the current version with rollback on failure, full-reinstall detection via `min_app_version` (correct URL-encoding for filenames with spaces), self-restart.
- **`i18n.py`** — the RU/EN translation dictionary (350+ keys), auto-loads the saved language.

---

## 🔐 How the update system works

The update system follows a "safe even if something goes wrong" principle:

1. **Version check** — the current version is compared against `version.json`; the `min_app_version` field determines whether a regular patch is enough or a full reinstall is required.
2. **Staged download** — the new version is downloaded into a temporary folder, without touching the app's working files.
3. **SHA256 verification** — every downloaded file is checked against its checksum; on a mismatch the update is aborted and the working version is left untouched.
4. **Backup and rollback** — a backup of the current version is made before files are replaced; if applying the update fails, the app automatically rolls back to that backup.
5. **Self-restart** — once the update is applied successfully, the app restarts itself.

If auto-update still fails, `XTTS_DIAG.bat` provides a forced recovery/reinstall option.

---

## 🗃 Data and config files

| File | Purpose |
|---|---|
| `settings.json` | session: presets, flags, theme, UI language, panel position, text size |
| `gpt_settings.json` | AI provider, keys, models |
| `word_rules.json` | pronunciation dictionary (`builtin` / `auto` / `ai_corrected` / `custom`) |
| `word_rules_backups/` | timestamped dictionary backups before every save |
| `chat_history.json` | AI chat session history |
| `history.json` | generation history |
| `version.json` | current version and update-system data (including `min_app_version`) |
| `env_cache.cfg` | environment-scan cache (GPU/CUDA/libraries) |

---

## 🧩 Development

Built using AI tools: **Claude**, **ChatGPT**, and others.

Architecture refactoring (splitting into `engine/` + `engine/gui/`), RU/EN localization, the light theme, and interface polish were done with **Arena.ai Agent Mode** (a multi-model agent combining Claude, ChatGPT, Gemini, and others).

Key modules (`updater.py`, `chunker.py`, `normalizer.py`, `smart_pauses.py`) are covered by **pytest** tests (`test/`, run via `RUN_TESTS.bat`).

Development support tools live in `tools/`: generating `version.json` and the update manifest, converting `.py` to `.txt` for pasting into an AI chat, icon generation, a GitHub publishing script. `ProjectAnalyzer.ps1` at the project root builds a structure snapshot used as AI context across development sessions.

---

## ⚖️ Third-party components

The project uses the **XTTS v2** model (Coqui), distributed under the [Coqui Public Model License (CPML)](https://coqui.ai/cpml). Use of the model is governed by the CPML regardless of this project's own license.

---

## ☕ Support the project

**BTC:** `bc1qz78u3lvagt3v886359glv57ct6rnlh506wjmdy`

---

<div align="center">

**XTTS Studio** · by EXIZ10TION · Made with 🎙️ and ❤️

</div>
