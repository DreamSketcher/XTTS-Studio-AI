<div align="center">

# 📘 XTTS Studio — Unified Function Reference

**Complete reference for all classes, methods, and modules**

[![EN](https://img.shields.io/badge/Language-English-58a6ff)](https://img.shields.io/badge/Language-English-58a6ff)
[![RU](https://img.shields.io/badge/Русский-Доступен-2da44e)](unified_function_reference.md)

</div>

---

## Table of Contents

1. [Text Processing Pipeline](#1-text-processing-pipeline)
2. [AI & LLM Integration](#2-ai--llm-integration)
3. [Diagnostics & Self-Healing](#3-diagnostics--self-healing)
4. [GUI Entry Point](#4-gui-entry-point)
5. [Other Core Modules](#5-other-core-modules)
6. [Complete Module List](#6-complete-module-list)

---

## 1. Text Processing Pipeline

### 1.1 TextNormalizer (`engine/normalizer.py`)

**Class**: `TextNormalizer`

**Purpose**: Full Russian text normalization before synthesis.

#### Main Methods

| Method                  | Signature                                      | Description                              |
|-------------------------|------------------------------------------------|------------------------------------------|
| `normalize`             | `normalize(self, text: str) -> str`            | **Main function**                        |
| `safe_character_filter` | `safe_character_filter(self, text: str) -> str`| Strict filtering (called after WordReplacer) |

#### Internal Methods
- `_yoficator()` — Ё restoration
- `_fix_abbrev_rhythm()`, `_fix_mixed_case_rhythm()`, `_fix_cyrillic_abbrev()`
- `_replace_time_and_ratio()`

---

### 1.2 WordReplacer (`engine/word_replacer.py`)

**Class**: `WordReplacer`

#### Rule Categories

| Category       | Priority | Source             |
|----------------|----------|--------------------|
| `builtin`      | Lowest   | Historical         |
| `auto`         | Medium   | Auto-transliteration |
| `ai_corrected` | High     | AI Conductor       |
| `custom`       | Highest  | Manual edits       |

#### Main Methods

| Method         | Signature                                           | Description             |
|----------------|-----------------------------------------------------|-------------------------|
| `apply`        | `apply(self, text, persist_new=True)`               | **Main function**       |
| `add_rule`     | `add_rule(self, word, replacement, category="custom")` | Add rule             |
| `remove_rule`  | `remove_rule(self, word)`                           | Remove rule             |

---

### 1.3 TextChunker (`engine/chunker.py`)

**Class**: `TextChunker`

**Parameters**: `max_size=175`, `target_size=150`, `min_size=50`

**Safety Rules**:
- Cannot start chunk with: `и, а, но, или, который...`
- Cannot end chunk with: `и, а, но, или, который...`

#### Main Methods

| Method          | Signature             | Description                  |
|-----------------|-----------------------|------------------------------|
| `chunk_text`    | `chunk_text(self, text)` | **Main public function**  |
| `_split_sentences` | —                  | Safe sentence splitting      |
| `_split_long`   | —                     | Split long sentences         |
| `_merge`        | —                     | Merge short chunks           |

---

### 1.4 SmartPauseEngine (`engine/smart_pauses.py`)

**Class**: `SmartPauseEngine`

#### Main Methods

| Method            | Signature                                      | Description             |
|-------------------|------------------------------------------------|-------------------------|
| `get_pause_ms`    | `get_pause_ms(self, chunk, next_chunk="")`     | **Main function**       |
| `detect_emotion`  | `detect_emotion(self, chunk)`                  | Emotion detection       |

> **Important**: Disabled when AI Conductor is active.

---

## 2. AI & LLM Integration

### 2.1 GPT Client (`engine/gpt_client.py`)

**Purpose**: Universal client for OpenAI-compatible providers.

#### Key Functions

| Function                   | Description                              |
|----------------------------|------------------------------------------|
| `get_provider()` / `set_provider()` | Provider management             |
| `chat()`                   | Free chat                                |
| `improve_for_tts()`        | TTS-friendly text improvement            |
| `_call_with_chain()`       | **Main entry point** (fallback chain)    |

**Supported providers**: `groq`, `openrouter`, `proxy`, `local`, custom

---

### 2.2 Local LLM Client (`engine/local_llm_client.py`)

**Purpose**: GGUF inference via `llama-cpp-python`.

#### Key Functions

| Function               | Description                        |
|------------------------|------------------------------------|
| `call_local_llm()`     | **Main generation function**       |
| `download_model()`     | Download with resume support       |
| `_get_llm()`           | Lazy model loading                 |

---

### 2.3 AI Conductor (`engine/ai_conductor.py`)

**Main function**:

```python
def conduct(text, chunks, rewrite_enabled=False, ...) -> list | dict | None
```

#### Returned Parameters

| Parameter         | Range        | Purpose                     |
|-------------------|--------------|-----------------------------|
| `temperature`     | 0.50–0.90    | Intonation variability      |
| `speed`           | 0.75–1.25    | Speech speed                |
| `pause_after_ms`  | 0–1200       | Pause duration after chunk  |

---

## 3. Diagnostics & Self-Healing

### 3.1 Diagnostics (`engine/env_core/diagnostics.py`)

#### Main Functions

| Function                       | Description                              |
|--------------------------------|------------------------------------------|
| `run_full_diagnostics()`       | Full diagnostics in isolated process     |
| `run_error_recovery()`         | **Self-healing** of packages             |
| `scan_for_garbage()`           | Garbage scanning                         |
| `get_broken_critical()`        | Only truly broken critical components    |

---

## 4. GUI Entry Point (`gui.py`)

#### Key Mechanisms

| Function                                      | Description                              |
|-----------------------------------------------|------------------------------------------|
| `_acquire_single_instance_lock()`             | Single instance protection               |
| `_ensure_dependencies_before_startup()`       | Pre-launch diagnostics                   |
| `_show_startup_recovery_window()`             | Library recovery window                  |

---

## 5. Other Core Modules

| Module                        | Key Classes / Functions                    |
|-------------------------------|--------------------------------------------|
| `tts_runner.py`               | `TTSRunner`                                |
| `prosody_layer.py`            | `ProsodyLayer`, `apply_prosody()`          |
| `reference_processor.py`      | `ReferenceProcessor`                       |
| `rvc_pipeline.py`             | `RVCPipeline`                              |
| `voice_manager.py`            | `VoiceManager`                             |
| `task_manager.py`             | `TaskManager`                              |
| `updater.py`                  | `Updater`                                  |
| `history_store.py`            | `HistoryStore`                             |

---

## 6. Complete Module List

The full list of all project files and their locations in the reference is available in the Russian version of this document.

---

<div align="center">

**XTTS Studio** · Complete Documentation · 2026-07-13

</div>