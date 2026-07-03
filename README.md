<div align="center">

# 🎙️ XTTS Studio

**Portable offline voice cloning & speech synthesis app powered by XTTS v2**

[![Windows](https://img.shields.io/badge/Windows-10%2F11%20x64-0078D6?logo=windows&logoColor=white)]()
[![Offline](https://img.shields.io/badge/100%25-Offline-2da44e)]()
[![Portable](https://img.shields.io/badge/Portable-no%20install-orange)]()
[![RU/EN](https://img.shields.io/badge/UI-RU%20%2F%20EN-58a6ff)]()
[![Themes](https://img.shields.io/badge/Themes-Dark%20%2F%20Light-7c3aed)]()

🇷🇺 [Русская версия](./README.md)

</div>

---

## 🚀 About

**XTTS Studio** is a fully offline tool for speech synthesis and voice cloning.
Runs in portable mode — no installation, no internet required.
The AI module is optional and connects via any OpenAI-compatible provider.

---

## 📥 Download

> ⚠️ Google Drive may show a large-file warning before downloading — that's normal: the file is not scanned by Google's antivirus because of its size, not because of any threat.

| Edition | Size | Link |
|---|---|---|
| ⚙️ CPU-only | 5 GB | [📥 Download XTTS Studio (Google Drive)](https://drive.google.com/file/d/1RJfaMjVHV_NUaaHgg4uSd0B8DI9noxRs/view?usp=drive_link) |
| 🚀 NVIDIA CUDA | 10 GB | [📥 Download XTTS Studio (GitHub Releases)](https://github.com/DreamSketcher/XTTS-Studio-portable-/releases) |

📜 **License:** [LICENSE.md](./LICENSE.md) — free to use with mandatory author attribution

---

## ✨ Features

### 🎤 Synthesis & cloning
- Fully offline — no external requests
- Portable — a single folder, runs on any Windows PC
- Voice cloning from a 10–20 second reference
- Voice library with Speaker Embedding cache
- Unlimited text length support
- Automatic RU/EN language switching within a single text

### 🖥 Interface
- 🌗 **Two themes:** dark and a soft light ("milky") one — switched with a single button
- 🌐 **Two UI languages:** Russian and English (RU/EN), including the AI chat and provider settings
- 📐 Adaptive toolbar — panels stretch to fit the window size
- ◀ Collapsible left panel that remembers its state
- 🔠 Adjustable text size in the input field ("Aa" slider)
- All appearance settings persist between sessions

### 🧠 Text processing
- Numbers → words automatically
- Abbreviations → phonetic dictionary (auto + manual)
- Semantic and punctuation pauses — automatic
- Text normalization before generation

### 🎛 Quality control
- 4 presets: ⭐ High Quality / 📖 Narrative / ⚡ Dynamic / 🎭 Expressive
- Fine-tuning: temperature, top_p, repetition_penalty, speed, trim
- Chunk quality control — auto-regeneration on repeats and cut-offs
- De-esser, RMS loudness normalization, automatic silence trimming
- Chunk cache — regenerating the same text takes no extra time

### 🤖 AI module (optional)
- **AI Conductor** — analyzes the text and assigns XTTS parameters to every chunk individually
  - Level 1: temperature, speed, pauses based on context and intonation
  - Level 2: text rewrite for a given genre or mood (with a negative prompt)
  - Both levels work independently and can be combined
- **AI Chat** — built-in chat assistant with session history and search
  - Text-editor mode and free-chat mode
  - "Improve" button — technical text rewrite for better TTS output
- Provider chain support: Groq, OpenRouter, custom OpenAI-compatible endpoints
- Provider catalogue, API key library

### 📋 More
- Task queue with cancellation
- Batch processing of TXT files
- Generation history with text restore
- Real-time highlighting of the current chunk
- Statistics: time, chunks, voice, speed
- Settings auto-saved between sessions
- WAV and MP3 export

---

## 🖼 Screenshots

<p align="center">
  <img src="images/main.PNG" width="45%" />
  <img src="images/ai-assist.PNG" width="45%" />
</p>
<p align="center">
  <img src="images/mail-light.PNG" width="45%" />
  <img src="images/settings.PNG" width="45%" />
</p>

---

## 🚀 Quick start

1. Download and unpack the archive
2. Avoid paths with Cyrillic characters
3. Run `XTTS Studio.exe`
4. Pick or load a voice reference
5. Enter your text
6. Press **🚀 GENERATE**
7. The result is saved to `outputs/` — see the **🎵 Audio** button

---

## ⚙️ How it works

```
Reference → auto-processing → voice library
   ↓
Text → normalization → numbers to words → abbreviations
   ↓
(optional) AI improvement / text rewrite
   ↓
Chunking → pause placement
   ↓
(optional) AI Conductor — per-chunk parameters
   ↓
Generation with quality control and caching
   ↓
Merge → loudness normalization → de-esser → WAV / MP3
```

---

## 🧠 Pronunciation dictionary

Examples of built-in rules:

```
AI      → эй ай
CPU     → си-пи-ю
GPU     → джи-пи-ю
OpenAI  → ОпенЭйАй
```

The dictionary grows automatically during generation and via AI Conductor.
Editing — the **📖 Dictionary** button (add, edit, delete rules).

---

## 💻 Requirements

| | CPU edition | CUDA edition |
|---|---|---|
| OS | Windows 10/11 x64 | Windows 10/11 x64 |
| Memory | 8+ GB RAM | 8+ GB RAM |
| GPU | — | NVIDIA, 4+ GB VRAM, Compute Capability 6.0+ |
| Speed | slower than real-time | faster than real-time |

---

## ⚠️ Important

Do not use paths with Cyrillic characters:

```
✔ C:\XTTS\
✘ C:\Новая папка\XTTS\
```

---

# 🗂 Full project structure

**Entry point:** `XTTS Studio.exe` → BAT → `python\runtime\python.exe` → `gui.py` → dependencies from `python\xtts_env`

The project has a modular architecture: a thin entry point, the technical core `engine/` (no GUI dependencies) and the interface layer `engine/gui/`.

## Project tree

```
XTTS Studio (portable)
│
├── gui.py                        ← entry point: interface launch only
├── i18n.py                       ← UI localization (RU / EN)
├── settings.json                 ← session settings: presets, theme, language, panel (auto)
├── gpt_settings.json             ← AI provider, keys, models (auto)
├── word_rules.json               ← pronunciation dictionary (auto + ai_corrected)
├── chat_history.json             ← AI chat session history
├── history.json                  ← generation history
│
├── engine/                       ═══ TECHNICAL CORE (no tkinter) ═══
│   │
│   │   ── generation pipeline ──
│   ├── tts_runner.py             ← main pipeline: normalize → chunk → generate → merge
│   ├── chunker.py                ← text chunking
│   ├── normalizer.py             ← numbers→words, abbreviations, punctuation
│   ├── word_replacer.py          ← phonetic dictionary replacements
│   ├── text_utils.py             ← shared text helpers
│   ├── smart_pauses.py           ← inter-chunk pauses (without the Conductor)
│   ├── prosody_layer.py          ← semantic prosody (without the Conductor)
│   ├── de_esser.py               ← sibilance suppression
│   │
│   │   ── AI module ──
│   ├── ai_conductor.py           ← AI Conductor (per-chunk params + rewrite)
│   ├── gpt_client.py             ← AI client: providers, keys, fallback chain
│   │
│   │   ── voice & audio ──
│   ├── reference_processor.py    ← reference conversion and normalization
│   ├── voice_manager.py          ← voice library
│   ├── audio_backend.py          ← audio init (pygame)
│   │
│   │   ── infrastructure ──
│   ├── task_manager.py           ← multi-threaded task queue
│   ├── task_models.py            ← Task model
│   ├── task_queue.py             ← thread-safe queue
│   ├── updater.py                ← auto-update (check/apply/restart)
│   ├── paths.py                  ← project base directories
│   ├── settings_store.py         ← settings.json reader
│   ├── history_store.py          ← generation history store
│   ├── output_naming.py          ← output file naming
│   ├── text_tools.py             ← GUI-side text normalization
│   └── logging_utils.py          ← file logging
│
│   └── gui/                      ═══ INTERFACE (tkinter / customtkinter) ═══
│       │
│       │   ── window core ──
│       ├── main_window.py        ← main window assembly (orchestrator)
│       ├── layout.py             ← layout + collapsible left panel
│       ├── theme.py              ← themes (dark / light), titlebar
│       ├── colors.py             ← both theme palettes
│       ├── widgets.py            ← widget factories, CTk compatibility
│       ├── tooltip.py            ← tooltips
│       ├── gradient.py           ← gradient background
│       │
│       │   ── main window panels ──
│       ├── header_panel.py       ← header: Update / AI Status / RU-EN
│       ├── voice_panel.py        ← reference + voice library
│       ├── player.py             ← reference player
│       ├── queue_panel.py        ← task queue
│       ├── console.py            ← built-in console
│       ├── textbox.py            ← input field: DnD, chunk highlighting, text size
│       ├── toolbar.py            ← adaptive toolbar: File / AI / Output / Action
│       ├── statusbar.py          ← progress bar and status
│       │
│       │   ── GUI logic ──
│       ├── generation.py         ← generation start/cancel, callbacks
│       ├── presets.py            ← quality presets + settings window
│       ├── settings_ui.py        ← saving and applying settings
│       ├── styles_menu.py        ← "Styles" menu
│       ├── updates.py            ← update checks (GUI wrapper)
│       │
│       │   ── separate windows ──
│       ├── chat_window.py        ← AI chat (sessions, search, export, AI settings)
│       ├── ai_conductor.py       ← AI Conductor window
│       ├── ai_status_window.py   ← "AI Status" window
│       ├── history_window.py     ← "History" window
│       ├── output_window.py      ← "Audio" window with built-in player
│       ├── batch_window.py       ← batch TXT processing
│       ├── word_replacer_window.py ← pronunciation dictionary
│       └── dialogs.py            ← synthesis language, help
│
├── models/xtts_v2/               ← the model (offline)
├── library/[voice_name]/         ← voice profiles + embedding cache (CPU/CUDA)
├── outputs/_cache/               ← output files + chunk cache (md5)
├── logs/                         ← error logs
├── reference/                    ← source reference files
├── ffmpeg/bin/                   ← ffmpeg.exe, ffprobe.exe
└── python/
    ├── xtts_env/                 ← venv with dependencies
    └── runtime/                  ← Python 3.11 portable
```

---

## 🔬 engine/ modules — by responsibility

### Generation pipeline
- **`tts_runner.py`** — `run_tts()`: normalize → word replacer → chunk → conductor → generate → merge. Lazy model loading (`get_tts()`, thread-safe singleton), CUDA/CPU auto-detection, embedding and finished-chunk cache (md5), QC (loop detector + duration validator), silence-based auto-trim, RMS loudness normalization.
- **`chunker.py`** — sentence splitting, cutting long chunks, merging short ones, bad chunk start/end checks.
- **`normalizer.py`** — numbers→words, abbreviations, punctuation; separate rhythm handling for Latin/Cyrillic abbreviations and CamelCase.
- **`word_replacer.py`** — dictionary-based phonetic replacements, auto-transliteration of abbreviations and terms.
- **`smart_pauses.py` / `prosody_layer.py`** — pauses and semantic prosody; **both are skipped when AI Conductor is active** — pauses and the temperature schedule then come from `conductor_map`.

### AI module
- **`ai_conductor.py`** — `conduct()`: a single call per text, analyzes the chunks and returns voicing parameters (temperature/top_p/repetition_penalty/speed/pause_after_ms) for each. Optionally — style-driven text rewrite (`rewrite_enabled`) and transliteration checks (`corrections` → `word_rules.json`). On AI failure — fallback to default parameters, generation never breaks.
- **`gui/chat_window.py`** — chat window with two modes (text editor / free chat), "Improve" button for a technical rewrite before TTS. Fully localized (RU/EN).
- **`gpt_client.py`** — provider chain (active → built-in → custom), key and model management, provider catalogue, localized labels.

### Voice & audio
- **`reference_processor.py`** — reference conversion to WAV, SNR check, cache.
- **`voice_manager.py`** — `library/` scanning, voice list, active voice.
- **`de_esser.py`** — sibilance suppression on the final file.

### Infrastructure
- **`task_manager.py` / `task_queue.py` / `task_models.py`** — multi-threaded generation queue with cancellation by id.
- **`updater.py`** — update check/apply, self-restart.
- **`i18n.py`** — RU/EN translation dictionary (350+ keys), auto-loading of the saved language.

---

## 🎚 How AI Conductor works (important for debugging)

Two independent levels, each with its own flag:

| Level | Flag | What it does |
|---|---|---|
| 1 — parameters | `ai_conductor_enabled` | temperature/top_p/repetition_penalty/speed/pause per chunk |
| 2 — rewrite | `ai_rewrite_enabled` | style/genre-driven text rewrite (only when level 1 is on) |

Level 2 is applied **only** with an explicit `rewrite_enabled=True` — this check is duplicated in two places (`ai_conductor.py: conduct()` and `tts_runner.py: run_tts()`) so that neither the model nor future edits can accidentally sneak a text rewrite in while the level-2 flag is off.

---

## 🗃 Data & configs

| File | Purpose |
|---|---|
| `settings.json` | session: presets, flags, theme, UI language, panel state, text size |
| `gpt_settings.json` | AI provider, keys, models |
| `word_rules.json` | pronunciation dictionary (manual + `ai_corrected` from the Conductor) |
| `chat_history.json` | AI chat session history |
| `history.json` | generation history |

---

## 🧩 Development

The app was built with the help of AI tools: **Claude**, **ChatGPT** and others.

The architecture refactoring (splitting into `engine/` + `engine/gui/`), RU/EN localization, the light theme and interface improvements were done with **Arena.ai Agent Mode** (a multi-model agent: Claude, ChatGPT, Gemini and more).

---

## ⚖️ Third-party components

This project uses the **XTTS v2** model (Coqui), distributed under the [Coqui Public Model License (CPML)](https://coqui.ai/cpml). Use of the model is governed by the CPML terms regardless of this project's license.

---

## ☕ Support the project

**BTC:** `bc1qz78u3lvagt3v886359glv57ct6rnlh506wjmdy`

---

<div align="center">

**XTTS Studio** · by EXIZ10TION · Made with 🎙️ and ❤️

</div>
