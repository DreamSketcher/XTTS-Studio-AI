# 📖 XTTS Studio — Documentation

**[English](./DOCUMENTATION.EN.md)** · **[Русский](./DOCUMENTATION.RU.md)**

This guide explains how to use XTTS Studio, what actually affects the result, and where to look when something goes wrong.

> Quick overview: **[README.EN.md](./README.md)** · **[README.RU.md](./README.ru.md)**  
> Source code: **[github.com/DreamSketcher/XTTS-Studio](https://github.com/DreamSketcher/XTTS-Studio)**

---

## Contents

1. [What the application does](#what-the-application-does)
2. [Quick start](#quick-start)
3. [Preparing a good reference](#preparing-a-good-reference)
4. [Practical workflows](#practical-workflows)
5. [How generation works](#how-generation-works)
6. [Quality presets and parameters](#quality-presets-and-parameters)
7. [RVC: models, previews, and cache](#rvc-models-previews-and-cache)
8. [Text processing](#text-processing)
9. [Queue, history, and batch processing](#queue-history-and-batch-processing)
10. [AI features and offline use](#ai-features-and-offline-use)
11. [CPU, CUDA, and performance](#cpu-cuda-and-performance)
12. [System environment and recovery](#system-environment-and-recovery)
13. [Files, caches, and settings](#files-caches-and-settings)
14. [Troubleshooting](#troubleshooting)
15. [Project architecture](#project-architecture)
16. [Development and tests](#development-and-tests)
17. [Licenses](#licenses)

---

## What the application does

**XTTS Studio** is a portable Windows application for local speech synthesis and voice cloning based on **XTTS v2**.

The basic workflow is:

```text
short voice sample + text → finished WAV or MP3
```

The following features work locally after installation:

- XTTS generation;
- reference processing;
- text normalization and chunking;
- task queue and generation history;
- local RVC conversion after an RVC model has been installed;
- local GGUF models through `llama-cpp-python`.

The application does not always need an internet connection. Internet access is used by cloud AI providers, RVC model search/download, local-LLM catalogue downloads, update checks, and installation of some optional components.

> **Important:** “offline” describes synthesis and installed local models. Online catalogues and cloud APIs require a network connection by design.

---

## Quick start

1. Unpack XTTS Studio into a path without Cyrillic characters.
2. Run `XTTS Studio.exe`.
3. Select a voice reference of roughly **10–20 seconds**.
4. Enter your text.
5. Choose a preset.
6. Click **🚀 GENERATE**.
7. The result appears in `outputs/` and in the **🎵 Audio** window.

```text
✔ C:\XTTS\
✔ D:\Apps\XTTS-Studio\
✘ C:\Новая папка\XTTS\
```

### What `XTTS Studio.exe` is

`XTTS Studio.exe` is not another copy of the speech engine and it does not contain the full application. It is a small launcher converted from the startup BAT file. It contains only the launch paths for the bundled Python runtime, the path to `gui.py`, and the application icon.

The launcher is included in updates because the paths to the runtime or portable environment may need to change when the folder layout changes. Models, settings, and user data are not stored inside the `.exe`.

### How release updates work

The full release archive is required for the first installation or for a rare incompatible upgrade. Normal releases are installed by the client-side updater:

1. the application receives a list of changed files;
2. only those files are downloaded into temporary staging;
3. SHA256 is checked when a hash is present in the manifest;
4. files that will be replaced are backed up;
5. the update is applied and waits for a successful-start confirmation;
6. a failed startup can trigger rollback.

This means users do not need to download and unpack the multi-gigabyte portable archive for every normal release. A full reinstall is requested only when the installed version is below `min_app_version` or the portable folder layout changed incompatibly.

`XTTS Studio.exe` is part of the update manifest as well. If launch paths change, the updater replaces the launcher together with the other changed files.

### First run on CPU

The application can run on CPU immediately. This is the most compatible mode, but long texts and RVC take more time.

### Enabling NVIDIA CUDA

If a compatible NVIDIA GPU is installed:

```text
⚙ Settings → Acceleration → install the GPU PyTorch variant
```

Do not install dependencies into system Python. XTTS Studio uses its own environment in `python/xtts_env`.

---

## Preparing a good reference

The reference recording affects the result more than most sliders.

A good sample contains:

- one speaker;
- 10–20 seconds of continuous speech;
- no music or other voices;
- little room echo, reverb, or aggressive denoising;
- no clipping;
- preferably the same language and a similar speaking style to the desired result.

Poor example: quiet speech under music in a large reverberant room.  
Good example: normal speech recorded 15–30 cm from a microphone in a quiet room.

### What the application does with a reference

`engine/reference_processor.py`:

1. creates a voice folder under `library/`;
2. converts the file to mono 24 kHz WAV;
3. trims a limited amount of silence from both ends;
4. processes at most 30 seconds;
5. applies compression and normalizes to roughly −16 dBFS;
6. saves `normalized.wav`;
7. estimates signal-to-noise ratio (SNR).

SNR ratings:

| SNR | Rating | Expected result |
|-----|--------|-----------------|
| ≥25 dB | excellent | clean and stable reference |
| 15–25 dB | good | normally sufficient |
| 8–15 dB | poor | possible noise, unstable timbre, or breathing artifacts |
| <8 dB | bad | record a cleaner sample if possible |

A previously prepared `library/<voice>/normalized.wav` is not normalized again. This prevents compression from accumulating every time the voice is selected.

---

## Practical workflows

### 1. An audiobook chapter

1. Choose a clean, calm reference.
2. Start with the **Narrative** preset.
3. Paste the whole chapter.
4. Keep QC enabled.
5. After generation, use the waveform in **History** to inspect questionable places.
6. Use **↩** to return the text of a history item to the editor and regenerate only the problematic part.

The application splits the text into chunks and merges them with pauses. The UI has no hard text-length limit, but processing time, RAM use, and cache size grow with the input.

### 2. A character voice through RVC

1. First make sure the XTTS output is intelligible without RVC.
2. Enable RVC and select an installed `.pth` model.
3. Test it with the separate parameter-preview button.
4. Adjust Pitch shift.
5. Adjust Index only if the matching `.index` exists.
6. Compare the result with RVC disabled, not only with the website demo.

If the base XTTS audio is unintelligible, RVC normally will not repair pronunciation. It changes the timbre of audio that has already been generated.

### 3. Multiple TXT files

Use batch processing for multiple chapters, dialogue files, or ad variants. Every item enters the same queue with its own text and selected settings. A task can be cancelled before it starts or while it is running.

### 4. Russian text with numbers and abbreviations

Example:

```text
В 2026 году А. С. Пушкин не мог пользоваться GPU, API и OpenAI.
```

Before XTTS, the text goes through normalization, pronunciation rules, and safe chunking. Initials such as `А. С. Пушкин` should not become three separate sentences.

### 5. Narration with AI Conductor

Conductor is useful when one long text contains different scenes: a calm introduction, dialogue, and an emotional ending. It can assign different parameters and pauses to individual chunks. For a uniform technical text, a normal preset is often more predictable.

---

## How generation works

```text
reference
  → conversion / normalization / SNR
  → speaker embedding and embedding cache

text
  → optional AI preprocessing
  → normalizer
  → pronunciation dictionary
  → chunker
  → optional AI Conductor / prosody / smart pauses

each chunk
  → XTTS
  → QC and optional retry
  → optional RVC
  → chunk cache

final output
  → merge with pauses
  → loudness normalization
  → optional de-esser
  → WAV or MP3
```

### What a chunk is

A chunk is a small piece of text generated independently by XTTS. `TextChunker` uses approximately:

```text
minimum: 50 characters
target:  150 characters
maximum: 175 characters
```

The split is selected around punctuation. The chunker also tries not to leave standalone conjunctions such as “and”, “but”, or relative words at a boundary.

### QC

When `qc_enabled` is active, a rejected chunk can be generated up to three times. Checks include suspicious repetition and implausible duration.

### Chunk cache

Text generated with the same voice and parameters can be reused. The cache key includes RVC settings, so an XTTS-only result is not confused with an RVC-processed result.

---

## Quality presets and parameters

XTTS Studio includes four presets:

| Preset | Typical use |
|--------|-------------|
| **High Quality** | general starting point |
| **Narrative** | books, lectures, calm voice-over |
| **Dynamic** | videos, short ads, energetic delivery |
| **Expressive** | emotional lines and scenes; needs a suitable reference |

Each preset stores its own values. Changing Narrative does not have to change Dynamic.

Settings tabs:

- **RVC** — model, Index, Pitch shift, f0;
- **Trim** — trim mode and amount;
- **Output** — WAV/MP3, QC, de-esser;
- **XTTS** — temperature, top_p, top_k, repetition penalty, speed, prosody.

Preset values are stored under `quality_params` in `settings.json`. Saving uses read-modify-write, so unrelated theme and UI keys should not disappear.

### A controlled way to tune parameters

1. Start with the preset defaults.
2. Change one parameter at a time.
3. Compare on the same short text.
4. Test a question, a statement, and a longer sentence before judging a voice.
5. Theme/layout presets are for UI appearance; voice-generation values belong to quality presets.

---

## RVC: models, previews, and cache

RVC is a second processing stage: it receives a WAV generated by XTTS and changes its timbre. In this project RVC runs **for every chunk accepted by QC**. If RVC fails, the whole job is not discarded: the original XTTS chunk is kept.

### Model files

```text
models/rvc/<name>.pth       required model weights
models/rvc/<name>.index     optional feature index
```

- `.pth` is always required;
- `.index` can improve similarity for models trained with an index;
- the Index slider cannot provide the expected effect without a matching `.index`;
- a model of unknown origin may still sound poor regardless of its epoch count.

### Model catalogues

The browser contains:

| Section | Data source |
|---------|-------------|
| **★ Curated** | local seed and `catalog_cache.json`; available offline |
| **🆕 New** | first page of the public voice-models.com catalogue |
| **🔥 Top** | public `/top` section |
| Search | local entries plus live voice-models.com search |

The network catalogue is a convenient index, not a quality or license guarantee.

Row actions:

- **▶ / ■** — play/stop a demo;
- **⬇** — download a direct `.pth` or `.zip`;
- **✕** — cancel a download;
- **🔗** — open the model page when no direct file is available;
- **🗑** — delete a local model and its matching `.index`.

### Two different previews

A **catalogue demo** is a finished example supplied by the model source. It helps identify the general timbre, but it does not show how the model will process your own reference.

The **parameter preview** beside the model selector performs a real local RVC pass:

- source: the first 6 seconds of the current voice reference;
- current Index, Pitch shift, and f0 method are used;
- rendering runs in the background;
- an identical combination is reused from cache;
- up to six recent variants are kept per model;
- if parameters change during rendering, the stale result is not played automatically.

This is the most useful way to compare parameters on your own source voice.

### Practical tuning

- **Pitch shift**: change it one semitone at a time until the result sounds natural. `+12` and `−12` are octave shifts, not universal “gender” presets.
- **Index**: start around the middle of the range. Excessive values may strengthen artifacts; without `.index` it will not help.
- **f0 method**: `rmvpe` is a reasonable default. Alternatives are useful when one model tracks the source pitch poorly.

### Cache and metadata

| Path | Contents |
|------|----------|
| `.preview_cache/` | short demos from the website |
| `.parameter_preview_cache/<model>/` | WAV variants of your parameter preview |
| `.metadata/<model>.json` | model page, URL, author, and local preview path |
| `catalog_cache.json` | catalogue cache |

The **🧹** button calls `clear_rvc_cache()`. It removes orphan previews, temporary files, and interrupted downloads. It does not remove installed `.pth`, `.index`, or previews attached to an installed model. Model-specific cache is removed together with the model.

### A local model has no ▶ button

A `.pth` file does not contain demo audio. For an older download, the application tries to restore metadata from the seed, New/Top catalogues, and the current search results. If no match is found, the model remains usable for conversion but preview is unavailable.

---

## Text processing

| Stage | Purpose | Example |
|-------|---------|---------|
| `normalizer.py` | numbers, dates, abbreviations, safe characters | `2026` → words |
| `word_replacer.py` | user-defined and automatically discovered pronunciations | `GPU`, brand names, foreign terms |
| `chunker.py` | splits long text into safe parts | does not treat `А. С. Пушкин` as three sentences |
| `prosody_layer.py` | semantic pauses and emphasis | a list, contrast, or conclusion |
| `smart_pauses.py` | pause duration during merge | a period is longer than a comma |

Dictionary priority:

```text
builtin → auto → ai_corrected → custom
```

A custom rule has the highest priority. Backups are created before changes; up to 30 are retained.

When AI Conductor is active, normal prosody/smart pauses are skipped because pauses come from `conductor_map`.

---

## Queue, history, and batch processing

### Queue

`TaskManager` runs tasks sequentially in a worker thread. Cancelling the current task sets a flag checked inside `run_tts`. A queued task can be marked cancelled before it starts.

When the application closes, the manager:

- cancels the current task;
- drains waiting tasks;
- wakes a blocked `queue.get()` with a sentinel;
- waits for the worker with a timeout.

### History

`history.json` stores the last **100** generations: date, text, voice, preset, output path, duration, and chunk count.

In the History window:

- each card contains its waveform;
- clicking the waveform seeks;
- **▶ / ■** plays and stops;
- volume is next to playback;
- **↩** returns the text to the editor.

### Batch processing

Batch mode is intended for multiple TXT files. It uses the same queue and quality parameters as normal generation.

---

## AI features and offline use

### What may use the network

| Action | Internet required? |
|--------|--------------------|
| XTTS with a local reference | no |
| RVC with an installed model | no |
| RVC catalogue/search/download | yes |
| Cloud AI provider | yes |
| Installed local GGUF model | no |
| Update checks / CUDA component installation | yes |

### AI preprocessing

When AI edit is enabled, raw text is sent to the selected AI provider before the local normalizer runs. If AI is unavailable, the function should return the original text rather than aborting TTS.

### AI Conductor

Conductor can:

- assign parameters per chunk;
- set `pause_after_ms`;
- add pronunciation corrections;
- rewrite the text style when rewrite is enabled.

For maximum privacy, use a local GGUF model or disable AI features.

### API settings

Keys are stored in `gpt_settings.json`. Providers can form a fallback chain: active → other configured built-ins → custom. Never publish `gpt_settings.json` with real API keys.

---

## CPU, CUDA, and performance

| Mode | Advantages | Limitations |
|------|------------|-------------|
| CPU | works on most systems; no NVIDIA required | XTTS, RVC, and local LLM are significantly slower |
| CUDA | faster XTTS and some local workloads | requires a compatible NVIDIA GPU and matching PyTorch |

Practical advice:

- test a short sentence first;
- start a chapter or batch only after the short test succeeds;
- RVC adds a separate stage for every chunk;
- parameter preview may take several seconds on CPU;
- a stationary progress bar does not always mean a hang: model loading and the first inference are the slowest steps;
- do not manually install a different torch build over the portable environment.

---

## System environment and recovery

XTTS Studio does not use system Python. Managed packages are installed into:

```text
python/xtts_env/Lib/site-packages
```

Build files and the shared pip cache live in `python/temp` and `python/pip_cache`. Torch, RVC, and llama.cpp use these locations together, so multiple installers must not run at the same time.

The public facade is `engine/env_core/__init__.py`. It re-exports hardware detection, Torch/llama.cpp/RVC installers, diagnostics, cleanup, and recovery.

| Area | Main public API |
|------|-----------------|
| Hardware | `detect_cpu`, `detect_gpu`, `PYTHON_EXE`, `PROJECT_ROOT` |
| Torch | `install_torch`, `uninstall_torch`, `torch_status`, `cancel_install_torch`, checkpoints, broken variants |
| llama.cpp | `install_llama_cpp`, `uninstall_llama_cpp`, `llama_cpp_status`, `resolve_backend`, startup state |
| RVC | `install_rvc`, `uninstall_rvc`, `rvc_status` |
| Diagnostics | `run_full_diagnostics`, `scan_for_garbage`, `finalize_deletion`, `run_error_recovery`, cache helpers |

### CPU and GPU detection

`engine/env_core/cpu_gpu.py` collects hardware information without importing heavy ML libraries.

**CPU**

- uses `py-cpuinfo`;
- can install that small pure-Python package into the bundled `site-packages` if it is missing;
- reads CPU name and AVX, AVX2, FMA/FMA3, and F16C flags;
- these flags control which instructions are disabled for a local CPU build of `llama-cpp-python`.

**GPU**

- NVIDIA is detected through `nvidia-smi`;
- GPU name, reported CUDA version, and VRAM are collected;
- AMD/Intel are detected through PowerShell/WMI;
- AMD/Intel VRAM is also read from the 64-bit registry value because `Win32_VideoController.AdapterRAM` is limited to 32 bits.

An AMD/Intel GPU does not provide CUDA. In this project Torch GPU acceleration means NVIDIA CUDA, while local llama.cpp may separately use Vulkan on AMD/Intel.

### Torch installation

`engine/env_core/torch_setup.py` manages a matching package set:

```text
torch       2.2.2
torchaudio  2.2.2
torchvision 0.17.2
```

Available variants:

- `cu118` — NVIDIA CUDA 11.8;
- `cpu` — universal CPU build.

Variant selection:

1. respect the saved CPU/GPU preference;
2. require NVIDIA with reported CUDA 11.8 or newer;
3. skip variants previously marked broken;
4. force CPU when CUDA is requested on a non-NVIDIA machine.

The installer:

- uses a shared install lock so two pip processes cannot modify the environment concurrently;
- stores its stage in `.torch_install_checkpoint.json` and supports resume;
- removes previous `torch*`, `functorch`, `triton`, and `nvidia_*` target folders;
- uses the local `python/pip_cache`;
- verifies import in a separate process;
- requires `torch.cuda.is_available() == True` for the CUDA variant;
- marks a failed variant broken and falls back to CPU;
- records the successful variant in `.torch_installed_variant.json`.

`cancel_install_torch()` terminates the active pip process and releases the install lock. `clean_torch_cache()` removes shared temp/pip cache and the Torch checkpoint.

**Real case:** a CUDA wheel installs but the driver/GPU still makes `torch.cuda.is_available()` false. The application records `cu118` in `.torch_broken_variants.json` and installs the CPU build instead of keeping a non-working GPU setup.

### Local llama.cpp installation

`engine/env_core/llama_setup.py` chooses its backend independently from Torch:

| Hardware | Preferred backend |
|----------|-------------------|
| NVIDIA + CUDA | CUDA prebuilt wheel |
| AMD / Intel | Vulkan prebuilt wheel |
| no suitable GPU or backend marked broken | CPU build |

The CPU variant may be built from source. `build_cmake_args()` disables AVX/AVX2/FMA/F16C instructions that the detected CPU does not support, and compilation uses the available cores.

`llama_cpp_status()` first checks package integrity (`__init__.py`, `llama.py`, `llama_cache.py`), then imports it in a separate process. An incomplete directory is treated as an interrupted installation, not a working package.

Installation has two verification stages:

1. import `llama_cpp` in a separate process;
2. `smoke_test_gpu_init()` for a GPU backend: actually create `Llama(..., n_gpu_layers=-1)` with an available GGUF model.

If a CUDA/Vulkan wheel imports but crashes during real model initialization, that backend is recorded in `.llama_broken_backends.json` and installation falls back to CPU. This test is stronger than a plain `import llama_cpp`.

Interrupted state is stored in `.llama_install_checkpoint.json`; the successful backend is stored in `.llama_installed_backend.json`. An orphan checkpoint is cleared automatically when the library already works.

During a long CPU build, a watchdog checks file activity. “No files changed recently” is a possible-stall warning, not an automatic cancellation.

### RVC environment installation

`engine/env_core/rvc_setup.py` installs `rvc-python` and its dependency tree into the same portable environment.

Why this is more involved than a normal `pip install`:

- fairseq often requires compilation on Windows;
- old dependency metadata contains incompatible strict pins;
- `pip --target` does not always recognize Torch already present in the target;
- a naive install could download multi-gigabyte CUDA Torch again;
- the running application may temporarily lock `.pyd`/DLL files.

The installer:

- detects the installed Torch build (`cpu` or `cu118`) and reuses the same package index;
- creates dynamic constraints from versions actually present in `site-packages`;
- installs `rvc-python --no-deps`, then reads real `Requires-Dist` entries from its METADATA;
- uses prebuilt fairseq wheels for Windows Python 3.10/3.11/3.12 when available;
- avoids installing the obsolete `dataclasses` backport over Python 3.11;
- installs fairseq/sacrebleu dependencies separately while preserving shared `portalocker`;
- force-restores compatible NumPy and PyYAML;
- retries without `--upgrade` after WinError 5 to avoid overwriting locked files;
- can install up to six discovered missing modules;
- finally verifies `from rvc_python.infer import RVCInference` in a separate process.

`uninstall_rvc()` removes RVC/fairseq-specific packages but intentionally leaves `portalocker` because it is a shared dependency.

**Real case:** RVC is installed into a CPU environment. Dynamic constraints pin the existing `torch+cpu`, preventing pip from replacing it with `cu118` and downloading several gigabytes again.

### Full diagnostics

`run_full_diagnostics()` checks 11 components in **one isolated subprocess**:

```text
critical:
  numpy, torch, torchaudio, torchvision, TTS,
  soundfile, pygame, customtkinter, num2words

optional:
  llama_cpp, rvc_python
```

An optional component can simply be absent. That is a normal state and does not block base XTTS startup. `get_optional_status()` distinguishes `ok`, `not_installed`, and `broken`; only the last state should be reported as an actual failure.

Isolation is also important for recovery. Importing Torch/TTS inside the GUI process may keep `.pyd` and DLL files locked on Windows; a finished subprocess releases them before pip repair begins.

If NumPy fails, dependent Torch/TTS checks are marked `SKIPPED`: repair the root cause before reinstalling everything else.

A fully successful result is cached in `.env_diagnostics_cache.json`. The cache remains valid only while these values match:

- Python executable path;
- `site-packages` mtime;
- number of entries in `site-packages`.

Before probing, diagnostics removes an accidentally installed `dataclasses` backport that can shadow the Python 3.11 standard library and break Torch, torchvision, and pip itself.

`clear_diagnostics_cache()` forces the next check to run again. `clean_pip_download_cache()` removes the shared `python/temp` and `python/pip_cache` for Torch, RVC, and llama.cpp; it must not be used during an active installation.

### Garbage scan and quarantine

`scan_for_garbage(mode="fast" | "deep")` does not delete candidates immediately.

Flow:

1. run baseline diagnostics;
2. scan `python/temp`, `python/pip_cache`, `logs`, `__pycache__`, `.pytest_cache`, and known temporary extensions;
3. exclude `models`, `outputs`, `library`, `reference`, and `.git` from the broad project scan;
4. move candidates to `python/xtts_env/Quarantine`;
5. run diagnostics again;
6. restore files automatically and mark them unsafe if a new failure appears;
7. permanently remove only the confirmed list through `finalize_deletion()`.

**Fast** mode reuses the known-safe cache and skips new unknown files.  
**Deep** mode tests the full candidate set through quarantine and post-scan diagnostics.

Safe/unsafe/deleted history is stored in `.known_safe_files.json` and later used by recovery.

### Dependency recovery

`run_error_recovery()` maps deletion history to packages and pinned versions from `requirements.txt`, then checks the live environment before installing anything. A working package is not reinstalled merely because an old deletion record still exists.

Special cases:

- RVC recovery delegates to specialized `install_rvc()`;
- Torch variant is inferred from installed metadata and saved backend state;
- working Torch is not downloaded again while repairing SoundFile or torchvision;
- incompatible PyAV (`av.logging`) is repaired before/after torchvision;
- pip exit code 0 is not enough — imports are tested again;
- the shadowing `dataclasses` backport is removed both before and after recovery;
- full output is stored in `logs/recovery_pip_output.log`.

**Real case:** garbage cleanup removed an `av`-related file and torchvision stopped importing. Recovery repairs the compatible PyAV build and checks `av.logging`; if torchvision imports again, its wheel is not downloaded unnecessarily.

### Important environment files

| Path | Purpose |
|------|---------|
| `.env_diagnostics_cache.json` | cache of a fully successful diagnostics run |
| `.known_safe_files.json` | scanner safe/unsafe/deleted history |
| `.torch_install_checkpoint.json` | interrupted Torch installation stage |
| `.torch_installed_variant.json` | last successful `cpu` / `cu118` selection |
| `.torch_broken_variants.json` | Torch variants that automatic selection should skip |
| `.llama_install_checkpoint.json` | llama.cpp installation stage |
| `.llama_installed_backend.json` | last successful llama.cpp backend |
| `.llama_broken_backends.json` | CUDA/Vulkan backends that failed verification |
| `python/temp/` | temporary pip/build files |
| `python/pip_cache/` | shared installer download cache |
| `python/xtts_env/Quarantine/` | temporary isolation for deletion candidates |
| `logs/recovery_pip_output.log` | complete recovery log |

Do not delete a checkpoint file during an active installation: it is needed for resume and interrupted-stage diagnostics.

---

## Files, caches, and settings

| Path | Purpose | Safe to delete manually? |
|------|---------|--------------------------|
| `XTTS Studio.exe` | small launcher: bundled-Python path, `gui.py` path, and icon | no, if this is how you start the application |
| `version.json`, `checksums.txt` | installed version, update manifest, and file verification | not recommended |
| `settings.json` | GUI settings and all quality presets | yes, but settings reset |
| `theme_settings.json` | theme, layout, neon, UI presets | yes, but theme settings reset |
| `gpt_settings.json` | AI providers, models, and keys | only if you are ready to configure them again |
| `word_rules.json` | pronunciation dictionary | avoid without a backup |
| `history.json` | last 100 generations | yes; history is cleared |
| `library/<voice>/` | `normalized.wav`, converted audio, and embedding cache; the source file may remain at its original path | use the UI when possible |
| `outputs/` | finished audio | yes, after saving needed files elsewhere |
| `outputs/_cache/` | chunk cache | yes; repeated generation becomes slower |
| `models/rvc/` | RVC models and related caches | remove models through the RVC browser |
| `models/` | XTTS, RVC, and local GGUF files | do not delete blindly |
| `.env_diagnostics_cache.json` | cache of successful diagnostics | yes; the next check will be full |
| `.known_safe_files.json` | quarantine/safe/unsafe/deleted history | do not remove before recovery |
| `.torch_*`, `.llama_*` | checkpoints and selected/broken backends | do not remove during installation or investigation |
| `python/temp/`, `python/pip_cache/` | shared installer temp and cache | clear through the UI, never during installation |
| `python/xtts_env/Quarantine/` | files temporarily isolated by the scanner | do not delete manually before diagnostics finishes |
| `logs/` | diagnostics and recovery logs | yes, when no investigation is needed |

Quality presets are saved as a complete tree. Theme and other independent keys should survive changes to language or voice because `settings_ui.save_settings()` uses read-modify-write.

---

## Troubleshooting

### The application does not start after moving it

Check the path. Cyrillic characters and some unusual symbols break parts of the portable dependency stack.

### The cloned voice is not similar enough

1. Disable RVC.
2. Test XTTS with a clean reference.
3. Remove music, echo, and other speakers.
4. Try a sample with the same language and speaking style.
5. Add RVC only after the base voice is intelligible.

### The result sounds noisy or metallic

Typical causes are a poor reference, excessive Index, a weak RVC model, or an extreme Pitch shift. Compare with RVC disabled and change one parameter at a time.

### Index does not change anything

Check for a matching file:

```text
models/rvc/<model name>.index
```

Without it, `index_rate` cannot have the expected effect.

### A local RVC model has no preview

The `.pth` file does not contain audio. Preview requires stored metadata or a match in the catalogue.

### An RVC model downloaded but cannot be loaded

An error such as `invalid load key, '<'` usually means an HTML page was saved instead of model weights. Such files should be rejected by checkpoint validation. Download a direct `.pth`/`.zip` or open the source page through **🔗**.

### CPU generation is slow

This is expected for XTTS, RVC, and local LLM. Test a short sentence, close heavy applications, or enable CUDA on a compatible NVIDIA GPU.

### GPU was selected, but the application fell back to CPU

Check runtime verification, not only wheel installation. Torch requires `torch.cuda.is_available() == True`; a llama.cpp GPU backend must actually open a GGUF model with `n_gpu_layers=-1`. A failed variant is marked broken so it is not selected automatically again.

### Torch or llama.cpp installation was interrupted

Do not delete the checkpoint manually. Open environment settings: the installer can identify the stage and offer resume. If the package already works, an orphan checkpoint is cleaned automatically.

### Diagnostics says RVC or llama.cpp is not installed

These are optional components. Their absence is not a base-XTTS failure. Install RVC only for voice conversion and llama.cpp only for local AI.

### Something stopped importing after garbage cleanup

The scanner uses quarantine and post-move diagnostics before permanent deletion. Do not manually delete `python/xtts_env/Quarantine`: files may need to be restored automatically. If deletion was already confirmed, run recovery and inspect `logs/recovery_pip_output.log`.

### A cloud AI provider does not respond

Check the API key, selected model, provider availability, and VPN requirements. For a fully local workflow, select a GGUF model or disable AI.

### The application rolled back after an update

The updater first applies files through staging and writes a confirmation marker. If the next startup is not confirmed, the backup is restored. Check logs and the system-settings window for diagnostics.

---

## Project architecture

Code is separated by responsibility:

| Path | Responsibility |
|------|----------------|
| `gui.py` | application entry and startup checks |
| `engine/tts/` | generation pipeline, QC, export, and cache |
| `engine/gui/` | main window and user-facing panels |
| `engine/env_core/__init__.py` | public system-environment facade |
| `engine/env_core/cpu_gpu.py` | CPU flags and GPU vendor/CUDA/VRAM detection |
| `engine/env_core/torch_setup.py` | Torch install, resume, verification, and CPU fallback |
| `engine/env_core/llama_setup.py` | CPU/CUDA/Vulkan selection, smoke test, and llama.cpp fallback |
| `engine/env_core/rvc_setup.py` | Windows-safe `rvc-python`/fairseq installation |
| `engine/env_core/diagnostics.py` | isolated probes, cache, quarantine, and recovery |
| `engine/reference_processor.py` | reference preparation and SNR |
| `engine/normalizer.py` | text normalization |
| `engine/chunker.py` | safe text splitting |
| `engine/word_replacer.py` | pronunciation dictionary |
| `engine/rvc_pipeline.py` | local RVC inference |
| `engine/rvc_catalog.py` | catalogues, parsing, download, previews, metadata, cache lifecycle |
| `engine/task_manager.py` | task queue and worker |
| `engine/updater.py` | staging, SHA256, backup, rollback |
| `engine/gui/chat_window/` | AI chat and AI settings |

### Main entry points

```text
XTTS Studio.exe
  → gui.py
  → engine/gui/main_window.py
  → engine/gui/layout.py + panels

GENERATE button
  → engine/gui/generation.py
  → engine/task_manager.py
  → engine/tts/run_tts()
```

### Modular AI settings

AI settings are divided by responsibility:

```text
engine/gui/chat_window/chat_settings.py        facade
engine/gui/chat_window/engine/settings_window.py
engine/gui/chat_window/engine/settings_api.py
engine/gui/chat_window/engine/settings_local.py
engine/gui/chat_window/engine/settings_environment.py
engine/gui/chat_window/engine/settings_general.py
engine/gui/chat_window/engine/settings_context.py
```

`chat_settings.py` keeps the existing `open_gpt_settings` import while specialized modules build individual pages.

---

## Development and tests

Configuration is stored in `pyproject.toml`:

- Black and Ruff target Python 3.10/3.11;
- Ruff checks E/F/W; `F821` remains enabled for real undefined names;
- pytest adds the project root to `pythonpath`;
- `pytest-timeout` limits one test to 60 seconds.

Run:

```text
test\run_tests.bat
```

or from a prepared environment:

```bash
pytest test
```

Tests cover the pipeline, chunker, normalizer, updater, environment setup, RVC, task manager, UI modules, and other project areas. The exact count changes with the code; check the current CI run instead of keeping a hard-coded number in documentation.

When refactoring GUI code, keep public facades stable. For example, `chat_settings.py` remains a compatible import/re-export layer even though the settings implementation is split across several files.

---

## Requirements

| | Minimum | Comfortable |
|---|---------|-------------|
| OS | Windows 10/11 x64 | Windows 10/11 x64 |
| RAM | 8 GB | 16+ GB for long jobs and local LLM |
| CPU | modern x64 | more cores reduce waiting time |
| GPU | not required | NVIDIA, 4+ GB VRAM, CC 6.0+ |
| Disk | portable build + model storage | extra space for XTTS, RVC, GGUF, and caches |

---

## Licenses

- **XTTS v2** is used under the [Coqui Public Model License (CPML)](https://coqui.ai/cpml).
- Project code is covered by [LICENSE.md](./LICENSE.md).
- RVC and GGUF models may have their own licenses. Availability in a catalogue does not imply permission for commercial use.

---

## Support

**BTC:** `bc1qz78u3lvagt3v886359glv57ct6rnlh506wjmdy`

---

**XTTS Studio** · by EXIZ10TION · [GitHub](https://github.com/DreamSketcher/XTTS-Studio) · [README EN](./README.md) · [README RU](./README.ru.md) · [License](./LICENSE.md)
