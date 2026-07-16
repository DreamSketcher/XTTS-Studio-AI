<div align="center">

**[Русский](./README.ru.md)** · **[English](./README.md)**

# 🎙️ XTTS Studio

### Local voice cloning and text-to-speech without a subscription

**A portable Windows application built on XTTS v2: reference + text → WAV or MP3**

<br/>

[![CI](https://github.com/DreamSketcher/XTTS-Studio/actions/workflows/ci.yml/badge.svg)](https://github.com/DreamSketcher/XTTS-Studio/actions/workflows/ci.yml)
[![Windows](https://img.shields.io/badge/Windows-10%2F11%20x64-0078D6?logo=windows&logoColor=white)](https://github.com/DreamSketcher/XTTS-Studio/releases)
[![Core Offline](https://img.shields.io/badge/Core-Offline-2da44e)](https://github.com/DreamSketcher/XTTS-Studio)
[![Portable](https://img.shields.io/badge/Portable-no%20install-orange)](https://github.com/DreamSketcher/XTTS-Studio/releases)
[![RU/EN](https://img.shields.io/badge/UI-RU%20%2F%20EN-58a6ff)](https://github.com/DreamSketcher/XTTS-Studio)
[![RVC](https://img.shields.io/badge/RVC-voice%20conversion-e11d48)](https://github.com/DreamSketcher/XTTS-Studio)

<br/>

**[📥 Download](https://github.com/DreamSketcher/XTTS-Studio/releases)** · **[📖 Documentation EN](./docs/DOCUMENTATION.EN.md)** · **[📖 Документация RU](./docs/DOCUMENTATION.RU.md)** · **[📜 License](./LICENSE.md)**

</div>

---

## What it is

XTTS Studio runs XTTS v2 locally and provides the surrounding workflow that otherwise has to be assembled by hand:

- voice-reference preparation;
- long-text normalization and chunking;
- task queue and chunk quality control;
- voice library and embedding cache;
- RVC post-processing;
- generation history with waveforms;
- WAV/MP3 export;
- optional cloud or local AI.

Core synthesis does not send the reference or text to a cloud service. A network connection is used only for features that inherently need one: cloud AI, model catalogues/downloads, update checks, and installation of some optional components.

| Task | Internet |
|------|----------|
| XTTS with a local reference | not required |
| RVC with an installed model | not required |
| Installed local GGUF model | not required |
| RVC catalogue, model downloads, updates | required |
| Groq / OpenRouter / another cloud AI | required |

---

## Why XTTS Studio

- **Local core:** normal XTTS/RVC generation does not upload your reference or text.
- **Portable:** no separate Python installation or manual environment assembly.
- **Long-form workflow:** chunking, queue, QC, cache, and history are built for more than one short sentence.
- **RVC is part of the workflow:** catalogue, demos, parameter preview, downloads, and cache cleanup are in the same UI.
- **AI is optional:** use cloud providers, a local GGUF model, or no AI at all.
- **The application maintains its environment:** diagnostics, quarantine, recovery, checkpoints, and CPU fallback.
- **Normal updates do not require the full archive:** the updater downloads changed files, verifies SHA256, and can roll back.

### More than another XTTS wrapper

The project is not only a button around `TTS.api`. It handles the less glamorous parts of a portable desktop application: reference preparation, dependency health, recovery before heavy GUI imports, safe backup/rollback updates, and useful generation history.

It also does not promise that every reference or RVC model will sound good. The practical order is: **clean reference → short XTTS test → preset tuning → only then RVC and AI**.

---

## What you can do

### 🎤 Clone a voice

- use a reference of roughly **10–20 seconds**;
- automatically convert to mono 24 kHz WAV, trim, normalize, and estimate SNR;
- keep voices under `library/<voice>/`;
- reuse cached speaker embeddings;
- process long-form text in chunks and merge it into one file.

### 🎭 Change timbre with RVC

- use local `.pth` and optional `.index` files;
- browse **★ Curated · 🆕 New · 🔥 Top** and live search;
- hear a model demo before downloading;
- preview an already installed model;
- render a separate parameter preview on the first 6 seconds of your reference;
- adjust Index, Pitch shift, and f0 method;
- clear preview cache and leftovers from interrupted downloads.

> Index is meaningful only when a matching `.index` exists. RVC changes the timbre of generated audio, but it does not repair poor base-XTTS pronunciation.

### 📚 Produce long-form narration

- chapters, scripts, lectures, and voice-over;
- four presets: **High Quality · Narrative · Dynamic · Expressive**;
- QC with automatic retries for suspicious chunks;
- smart pauses, prosody, trim, and de-esser;
- batch processing for multiple TXT files;
- sequential queue with cancellation.

### 📝 Prepare text for speech

- numbers and dates → spoken words;
- pronunciation dictionary with custom rules taking priority;
- Russian ё restoration;
- protected initials such as `А. С. Пушкин`;
- automatic chunking at roughly 50–175 characters;
- RU/EN text and adaptive language detection.

### 🤖 Use AI only when needed

- AI Conductor assigns parameters and pauses per chunk;
- optional style rewrite;
- AI chat with provider fallback;
- Groq, OpenRouter, and custom OpenAI-compatible APIs;
- local GGUF models through `llama-cpp-python`.

### 🎧 Return to previous results

History keeps the latest 100 generations. Every card has a waveform: play, stop, click to seek, and use **↩** to return the text to the editor.

---

## Practical workflows

- **Audiobook:** clean calm reference → Narrative preset → full chapter → inspect questionable places in History.
- **Character voice:** intelligible XTTS first → `.pth` model → parameter preview → tune Pitch/Index/f0.
- **A set of lines:** multiple TXT files through batch → queue → separate WAV/MP3 outputs.
- **Private text:** disable cloud AI or use a local GGUF model; synthesis and installed RVC stay on the machine.

---

## Interface

- dark and light themes;
- theme constructor for colors, font size, layout, and neon effects;
- sidebar on the left or right;
- RU/EN interface;
- persistent quality-preset settings;
- normal Ctrl+A/C/V/X/Z/Y and context menu in API-key fields.

### Performance and security

- event-driven animation scheduling keeps no 60-FPS timer alive while idle;
- `ultra / balanced / performance / reduced / off` profiles affect visual motion only;
- the update manifest is verified with Ed25519 and SHA-256 before application;
- API credentials are protected by Windows DPAPI;
- unsigned RVC `.pth` checkpoints require explicit trust bound to SHA-256;
- the project publishes a CycloneDX SBOM plus security and privacy policies.

See **[Security](./docs/SECURITY.md)** · **[Privacy](./docs/PRIVACY.md)** · **[Dependency baseline](./docs/SECURITY_BASELINE.md)**.

### Screenshots

<p align="center">
  <img src="images/main.PNG" width="45%" alt="Main window" />
  <img src="images/mail-light.PNG" width="45%" alt="Light theme" />
</p>

<p align="center">
  <img src="images/ai-assist.PNG" width="45%" alt="AI assistant" />
  <img src="images/settings.PNG" width="45%" alt="Settings" />
</p>

<p align="center">
  <img src="images/ai-settings.PNG" width="45%" alt="AI settings" />
  <img src="images/preset-settings.PNG" width="45%" alt="Preset settings" />
</p>

<!--
Optional README improvement: one 20–30 second GIF.
Flow: select a voice → enter a short text → Generate → open the finished WAV.
When `images/quick-start.gif` exists, this is the best place to show it.
-->

---

## What is inside

| Component | Responsibility |
|-----------|----------------|
| **XTTS v2** | speech synthesis and cloning from a short reference |
| **PyTorch** | CPU/CUDA inference |
| **RVC / fairseq** | optional timbre conversion |
| **FFmpeg + pydub + SoundFile** | audio conversion, reading, merge, and export |
| **llama.cpp** | local GGUF models for AI chat and Conductor |
| **Tkinter + CustomTkinter** | desktop interface |
| **pygame** | reference, history, and RVC-preview playback |
| **env_core** | hardware detection, installation, diagnostics, quarantine, and recovery |

Heavy optional components are installed into portable `python/xtts_env`, not system Python.

---

## Installation

1. Download the portable archive from [GitHub Releases](https://github.com/DreamSketcher/XTTS-Studio/releases).
2. Unpack it into a path without Cyrillic characters.
3. Run `XTTS Studio.exe`.
4. Select a reference and generate a short test sentence.
5. Start a chapter or batch only after the short test succeeds.

```text
✔ C:\XTTS\
✔ D:\Apps\XTTS-Studio\
✘ C:\Новая папка\XTTS\
```

The build runs on CPU immediately. For a compatible NVIDIA GPU, install the CUDA variant through **⚙ Settings → Acceleration**.

> The portable archive is several gigabytes because it includes the Python environment and models. Do not install its dependencies over system Python.

---

## What `XTTS Studio.exe` is

`XTTS Studio.exe` is a small launcher converted from the startup BAT file. It does not contain the XTTS model, user settings, or the application source. It stores only the bundled-Python launch path, the path to `gui.py`, and the application icon.

The launcher is part of the update system. If the portable folder layout changes and runtime/environment paths need to be rewritten, the updater replaces the `.exe` together with the other changed files.

---

## How updates work

The full archive is needed for the first installation or for a rare incompatible upgrade. Normal releases are installed by the built-in client-side updater without downloading the entire heavy build again.

```text
version check
  → changed-file list
  → staging download
  → SHA256
  → backup
  → file replacement
  → successful-start confirmation
```

If the new startup is not confirmed, the updater can restore the backup. A full reinstall is required when the installed version is below `min_app_version` or the portable folder structure changed incompatibly.

---

## Requirements

| | Minimum | Recommended |
|---|---------|-------------|
| OS | Windows 10/11 x64 | Windows 10/11 x64 |
| RAM | 8 GB | 16+ GB for long jobs and local LLM |
| CPU | modern x64 | more cores reduce waiting time |
| GPU | not required | NVIDIA, 4+ GB VRAM, CC 6.0+ |
| Disk | portable build + models | extra space for RVC, GGUF, outputs, and caches |

CPU works out of the box, but XTTS, RVC, and local LLM may be noticeably slower than real time. CUDA accelerates supported workloads but requires a compatible NVIDIA GPU and the matching PyTorch build.

---

## Documentation and help

- [Full documentation in English](./docs/DOCUMENTATION.EN.md)
- [Полная документация на русском](./docs/DOCUMENTATION.RU.md)
- [License](./LICENSE.md)
- [Issues](https://github.com/DreamSketcher/XTTS-Studio/issues)

If a result sounds poor, start with the reference rather than the sliders: disable RVC, test base XTTS on a short sentence, and add RVC and AI only after the base output is intelligible.

---

## Licenses

- XTTS Studio code is covered by [LICENSE.md](./LICENSE.md).
- XTTS v2 is used under the [Coqui Public Model License (CPML)](https://coqui.ai/cpml).
- RVC and GGUF models may have their own licenses. A file being listed in a catalogue does not imply permission for commercial use.

---

## Support the project

If XTTS Studio saves you time or money:

**BTC:** `bc1qz78u3lvagt3v886359glv57ct6rnlh506wjmdy`

---

<div align="center">

**XTTS Studio** · by EXIZ10TION · Made with ❤️

[Download](https://github.com/DreamSketcher/XTTS-Studio/releases) · [Documentation](./docs/DOCUMENTATION.EN.md) · [License](./LICENSE.md)

</div>
