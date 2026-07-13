# 📖 XTTS Studio — Documentation

**[English](./DOCUMENTATION.EN.md)** · **[Русский](./DOCUMENTATION.RU.md)**

Technical reference for architecture, features, data files, and the full project tree.

> Product pitch: **[README.EN.md](./README.EN.md)** · **[README.RU.md](./README.RU.md)**

---

## Table of contents

1. [About](#about)
2. [Quick start](#quick-start)
3. [Pipeline overview](#pipeline-overview)
4. [Features (detailed)](#features-detailed)
5. [RVC voice enhancement](#rvc-voice-enhancement)
6. [AI module](#ai-module)
7. [Pronunciation dictionary](#pronunciation-dictionary)
8. [Diagnostics & self-healing](#diagnostics--self-healing)
9. [Update system](#update-system)
10. [Requirements](#requirements)
11. [Data & config files](#data--config-files)
12. [Project structure](#project-structure)
13. [engine/ by responsibility](#engine-by-responsibility)
14. [Development](#development)
15. [Third-party / license notes](#third-party--license-notes)

---

## About

**XTTS Studio** is a portable, fully offline text-to-speech and voice-cloning application built on **XTTS v2**.

- Entry: `XTTS Studio.exe` → BAT → `python\runtime\python.exe` → `gui.py`
- Dependencies live in `python\xtts_env`
- Architecture: thin entry point · technical core in `engine/` (no GUI) · UI in `engine/gui/`

The optional **AI module** can use cloud OpenAI-compatible providers and/or **local LLMs** (no keys, offline).

---

## Quick start

1. Download and unpack the archive  
2. **Do not** use a path with Cyrillic characters  
3. Run `XTTS Studio.exe`  
4. Pick or upload a voice reference (≈10–20 s)  
5. Enter text  
6. Click **🚀 GENERATE**  
7. Result → `outputs/` (or **🎵 Audio** button)

```text
✔  C:\XTTS\
✘  C:\Новая папка\XTTS\
```

---

## Pipeline overview

```text
Reference → auto-processing → voice library (+ embedding cache)
   ↓
Text → (optional GPT improve on raw text) → normalize → word replacer
   ↓
(optional) AI Conductor rewrite / per-chunk map
   ↓
Chunker (SBD / initials / merge-split) → (optional) prosody / smart pauses*
   ↓
Per chunk:
   · XTTS inference (with QC retries if enabled)
   · (optional) RVCPostProcessor on that chunk WAV
   · chunk cache key includes RVC settings
   ↓
Merge chunks + pauses → loudness normalize → de-esser → WAV / MP3
```

\* Smart pauses / prosody layer are skipped when AI Conductor is active (pauses come from `conductor_map`).

**Important:** RVC runs **per chunk** after XTTS (not only on the final file). De-esser runs once on the **merged** export.

---

## Features (detailed)

### Synthesis and cloning

- Fully offline synthesis (no external requests for TTS itself)
- Portable single-folder layout
- Voice cloning from a short reference clip
- Voice library with cached speaker embeddings (CPU/CUDA aware)
- No hard limit on text length
- Automatic language handling for Russian / English content
- **On-demand CUDA**: CPU by default; **⚙ Settings → Acceleration** installs GPU packages for the detected NVIDIA card when requested

### Interface

- **⚙ Settings** panel:
  1. **Updates** — auto-check on startup, manual check  
  2. **Acceleration (CPU/GPU)** — hardware detection, PyTorch variant, preference, install with live log  
  3. **Diagnostics** — garbage scan, library diagnostics, recovery  
- Themes: dark + soft light; **theme constructor** (colors, fonts, layout presets); immersive Windows titlebar  
- Customizable layout: sidebar side, collapse, dockable panels, auto-save  
- Adaptive UI / toolbar  
- UI languages: **RU / EN** (including AI chat and provider UI)  
- Input font size (`Aa`)  
- Neon button glow (toggle + color)  
- **Auto-update**: staged download, **SHA256**, backup + rollback, `min_app_version` full reinstall path  

### Text processing

| Module | Class / API | Notes |
|--------|-------------|--------|
| `engine/normalizer.py` | `TextNormalizer.normalize`, `safe_character_filter` | Numbers→words, ordinals, time/ratio, Latin/Cyrillic abbrev rhythm, **ё-restoration** (`_yoficator`), then optional strict filter |
| `engine/word_replacer.py` | `WordReplacer.apply`, `add_rule`, `remove_rule` | Categories **builtin → auto → ai_corrected → custom** (later wins); auto-translit; JSON-only truth (`word_rules.json`); backups (max 30) |
| `engine/chunker.py` | `TextChunker.chunk_text` | Limits max=175 / target=150 / min=50; bad start/end tokens; **initials SBD** via negative lookbehind |
| `engine/prosody_layer.py` | `ProsodyLayer.process` / `process_chunks` | Semantic pauses (contrast/conclusion/emphasis/example); list prosody; **skipped when AI Conductor active** |
| `engine/smart_pauses.py` | `SmartPauseEngine.get_pause_ms` | Pause ms by punctuation/length/list; **skipped when Conductor active** (uses `pause_after_ms` from map) |

### Quality control

- 4 presets: ⭐ High Quality / 📖 Narrative / ⚡ Dynamic / 🎭 Expressive  
- Per-preset settings UI (tabbed): **RVC · Trim · Output · XTTS**  
  - Last tab remembered in `settings.json` (`quality_settings_last_tab`)  
  - Sticky tab bar (does not scroll away)  
- Fine controls: temperature, top_p, top_k, repetition_penalty, speed, prosody, trim (+ mode), export format, QC, de-esser, RVC  
- Chunk-level QC — regenerate on loops / bad duration  
- De-esser (on merge), RMS loudness normalization, silence trim  
- Chunk cache — identical chunks generated once (cache key includes RVC settings)  

**Persistence (verified):** `engine/gui/settings_ui.py` → `save_settings()` writes the full `quality_params` tree (every preset, every key including `rvc_*`) into `settings.json` using **read-modify-write** (does not wipe `ui_theme` / other keys). `apply_settings()` restores any known key with `.set(value)`. Real sessions already store e.g. `rvc_enable`, `rvc_model`, `rvc_index_rate`, `rvc_pitch_shift`, `rvc_f0_method` per preset.

### Other

- Cancelable task queue  
- Batch TXT processing  
- Generation history with text recall  
- Live highlighting of the current chunk  
- Stats: time, chunks, voice, speed  
- Settings persisted between sessions  
- Export WAV / MP3  

---

## RVC voice enhancement

Optional **Retrieval-based Voice Conversion** stage after XTTS. Implemented as three layers: **setup** (install), **catalog** (models), **pipeline** (infer), plus a **GUI dropdown**.

### Where RVC is called (generation)

In `engine/tts/__init__.py` → `run_tts()`:

1. Pop `rvc_enable`, `rvc_model`, `rvc_index_rate`, `rvc_pitch_shift`, `rvc_f0_method` from the preset so they never reach XTTS `inference()`.
2. Include those values in the **chunk cache key** (`_rvc_*` fields) so cache does not mix “same text / different RVC”.
3. After XTTS writes the chunk WAV (and QC accepts it), if `rvc_enable and rvc_model`:
   - `get_rvc_processor()` → lazy singleton `RVCPostProcessor`
   - `run_inference_via_lib(chunk_path, chunk_path, model_name=..., ...)` (in-place convert)
4. On `RVCPipelineError` / unexpected error: **log and keep the XTTS chunk** (generation does not abort).

Facade: `engine/tts_runner.py` re-exports `run_tts`, `get_tts`, `detect_device`, `word_replacer` from `engine.tts`.

GUI entry: `engine/gui/generation.py` → `generate()` builds a `Task` with `quality_params={**preset vars including rvc_*}`, queues via `task_manager`.

### Pipeline classes (`engine/rvc_pipeline.py`)

| Name | Role |
|------|------|
| `RVCPipelineError` | Raised on missing model / API mismatch / failed infer |
| `RVCPostProcessor` | Loads `.pth` (+ optional `.index`), runs `rvc-python` |
| `XTTSWithRVCPipeline` | XTTS → temp WAV → RVC → final path; skips RVC if no model |

**`RVCPostProcessor.run_inference_via_lib(...)`** (production path):

1. Lazy-import `rvc_python.infer.RVCInference`  
2. `load_model(model_path, version="v2", index_path=...)`  
3. `set_params(f0up_key=pitch_shift, f0method=..., index_rate=..., filter_radius=3, resample_sr=0, rms_mix_rate=0.25, protect=0.33)`  
4. `infer_file(input_path, output_path)` — **exactly two arguments** (pitch is **not** passed here)

Device strings are normalized to `cpu:0` / `cuda:0`.  
Optional CLI path: `run_inference_via_cli` (`tools/RVC_CLI` / global `rvc`).

### Catalog (`engine/rvc_catalog.py`)

| Path | Purpose |
|------|---------|
| `json/rvc_catalog_seed.json` | Offline seed shipped with the app (**28** HF-oriented entries) |
| `models/rvc/` | Downloaded `.pth` / `.index` |
| `models/rvc/catalog_cache.json` | Last successful remote catalog cache |

**Public API**

| Function | Description |
|----------|-------------|
| `get_catalog(force_refresh=False)` | Cache/seed first; GitHub raw catalog only if empty or forced; **1 attempt**, **6h cooldown** after 404 |
| `search_catalog(query, max_results=30, live=True)` | Local seed/cache match, then optional live search |
| `search_voice_models(query, ...)` | voice-models.com (`fetch_data.php` + autocomplete); timeouts fail soft → seed only |
| `download_model(entry, progress_callback, cancelled_flag)` | HF `/resolve/`, direct zip/pth, best-effort Google Drive **file**; zip → largest `.pth` + best `.index` |
| `is_downloaded` / `local_model_path` / `delete_local_model` | Local file helpers (always `.pth` as canonical local name) |
| `open_model_page(entry)` | Browser for non-direct links (folders / model page) |

Catalog entry **must** have: `id`, `name`, `url`. Optional: `filename`, `author`, `license`, `description`, `source`, `page_url`, `size`, `sha256`, `downloadable`.

### Install stack (`engine/env_core/rvc_setup.py`)

| Function | Description |
|----------|-------------|
| `rvc_status()` | Subprocess probe: can import `RVCInference`? |
| `install_rvc(progress_cb=None)` | Install into portable `python/xtts_env/Lib/site-packages` |
| `uninstall_rvc(progress_cb=None)` | Remove rvc_python + fairseq tails (keeps shared packages like `portalocker`) |
| `detect_torch_build(site_packages)` | Same torch variant as base install (`cu118` / `cpu`) |

**Install highlights (Windows-safe)**

- Prebuilt **fairseq** wheels by CPython version (avoids MSVC compile)  
- `rvc-python --no-deps`, then real deps from package METADATA  
- Dynamic constraints so existing **torch+cu118/cpu** is not re-downloaded (~GB)  
- Retry without `--upgrade` on WinError 5 (locked `.pyd` while app is running)  
- Auto-heal missing modules after install (import probe loop)  
- PyYAML force-reinstall (common breakage with `--target` installs)  

### GUI (`engine/gui/rvc_model_dropdown.py`)

`RVCModelDropdown` — custom picker for preset settings:

- Trigger button shows current model + ▾  
- Popup is a `Frame.place()` on the modal settings window (works under `grab_set`)  
- Rows: local models (🗑), catalog/search remotes (⬇ / ✕ / 🔗)  
- Search: debounced; local results first, live second  
- Scrollable list (canvas + scrollbar + wheel over rows)  

### Preset settings UI (`engine/gui/presets.py`)

Sticky tabs (do not scroll away): **RVC · Trim · Output · XTTS**

- RVC tab: enable, model dropdown, index, pitch, f0 method  
- Output tab: export format, **de-esser**, QC  
- Last tab stored as `quality_settings_last_tab` in `settings.json`  
- Closing the window (button or ✕) calls `save_settings` so **RVC fields persist** inside `quality_params[preset]`  

### Settings keys (per quality preset)

```text
rvc_enable, rvc_model, rvc_index_rate, rvc_pitch_shift, rvc_f0_method
```

Plus window-level: `quality_settings_last_tab` ∈ `rvc | trim | out | xtts`.

---

## TTS core (`engine/tts/`)

| Symbol | File | Role |
|--------|------|------|
| `run_tts(...)` | `tts/__init__.py` | Full job: normalize → chunk → generate → RVC → merge/export |
| `get_tts()` | `tts/__init__.py` | Thread-safe lazy XTTS singleton |
| `get_rvc_processor()` | `tts/__init__.py` | Thread-safe lazy `RVCPostProcessor` |
| `tts_runner.py` | package root | Thin re-export of `run_tts` / `get_tts` / … |
| `_detect_repeats` | `tts/qc.py` | Loop detector (corr threshold) |
| `_validate_duration` | `tts/qc.py` | Too short / empty / implausible duration |
| `_adaptive_trim` | `tts/qc.py` | Silence/tail trim (modes: auto/manual/off) |
| `_normalize_loudness` | `tts/qc.py` | RMS-style loudness toward target |
| `export_audio(...)` | `tts/export.py` | Merge chunks, pauses, de-esser, WAV/MP3 |
| `DeEsser` / `create_de_esser` | `engine/de_esser.py` | Split-band sibilance reduction on final mix |

### QC behaviour

- Controlled by `quality_params["qc_enabled"]` (default True).
- Up to **3** inference attempts per sub-chunk when enabled; temperature nudged +0.05 on reject.
- Reject if `_detect_repeats` or `_validate_duration` flags the candidate.

### De-esser

- Applied in **`export_audio`** on the combined `AudioSegment` when `de_esser_intensity > 0`.
- UI lives under preset tab **Output** (not XTTS generation params).
- `create_de_esser(intensity, sample_rate=24000)` → `process_segment` / `process_array` (FFT split-band, ~4–9 kHz).

### Export

- Merge with conductor or `SmartPauseEngine` pauses.
- Loudness normalize + optional de-esser + short silence + fade-out.
- `export_format`: `wav` or `mp3` (192k).

---

## AI module

### AI Conductor — `engine/ai_conductor.py`

**Entry:** `conduct(text, chunks, quality_params=None, chunks_wr=None, rewrite_enabled=False, rewrite_context="", rewrite_negative="")`

| Returns | When |
|---------|------|
| `list[dict]` | Normal path — one param object per chunk |
| `dict{"rewritten_text", "chunks"}` | Only if `rewrite_enabled` and model returned rewrite |
| `None` | AI unavailable / empty chunks (caller uses defaults) |
| fallback list | Invalid JSON / structure — `_fallback_params(chunks)` |

**Per-chunk fields (clamped by `_validate_map`):**

| Field | Range | Default |
|-------|-------|---------|
| `temperature` | 0.50–0.90 | 0.70 |
| `top_p` | 0.70–0.95 | 0.82 |
| `repetition_penalty` | 5.0–12.0 | 9.0 |
| `length_penalty` | 0.5–2.0 | 1.0 |
| `speed` | 0.75–1.25 | 1.0 |
| `pause_after_ms` | 0–1200 (0 on last chunk) | 450 |
| `corrections` | optional `dict` | AI translit fixes → WordReplacer `ai_corrected` |

**Behaviour notes**

- Calls cloud/local via `gpt_client._call_with_chain`
- `rewritten_text` is **ignored** unless `rewrite_enabled=True` (model sometimes returns it unprompted)
- On `AIUnavailable` → `None` (no hard crash)
- Levels 1 (params) and 2 (rewrite) are gated so rewrite cannot leak when disabled

### GPT client — `engine/gpt_client.py`

OpenAI-compatible multi-provider client. Settings file: **`gpt_settings.json`**.

| API | Role |
|-----|------|
| `get_provider` / `set_provider` | Active provider id |
| `get_api_key` / `set_api_key` / key library CRUD | Keys |
| `get_model` / `set_model` / `get_fallback_model` | Models |
| `list_custom_providers` / `add_custom_provider` / … | Custom OpenAI-compatible endpoints |
| `hide_provider` / `show_provider` | Chain visibility |
| `_call_api` / `_call_groq` | Low-level HTTP |
| `_build_provider_chain` | **active → other builtins with key → customs** |
| `_call_with_chain` | **Main call** with fallback across chain |
| `get_chain_diagnostics` | Structured status for AI Status window |
| `chat` / `improve_for_tts` / `preprocess_for_tts` | High-level text APIs |
| `validate_key` | Key check |
| `fetch_models_from_url` | List models from OpenAI-compatible `/models` |

**Exceptions:** `AIUnavailable`, `GroqRateLimitError`, `GroqNetworkError`.

**Provider availability:** cloud needs API key; `local` needs `local_llm_client.get_active_model()`.

Built-ins include Groq, OpenRouter, RU OpenAI-compatible proxy, and **local** (no key).

### Local LLMs — `engine/local_llm_client.py`

In-process **GGUF** inference via `llama-cpp-python` (no Ollama server).

| API | Role |
|-----|------|
| `LOCAL_MODEL_CATALOG` | Built-in HF GGUF catalog (TinyLlama, Phi-3, Qwen2.5, Llama 3.1, Mistral, …) |
| `get_compatible_models(ram_gb, vram_gb)` | Filter catalog by estimated memory |
| `download_model(url, filename, progress_cb, cancelled_flag, resume=False)` | Resume + cancel; `.tmp` + checkpoint |
| `install_catalog_model(model_id, ...)` | Catalog entry → download + register |
| `list_installed_models` / `register_model` / `remove_model` / `move_model_file` | Library |
| `get_active_model` / `set_active_model_id` | Selection |
| `_get_llm(path)` | Lazy load Llama; GPU layers with **CPU fallback** if backend broken |
| `call_local_llm(messages, model=None, max_tokens=2048) -> str` | Chat completion (CPU max_tokens capped at 256) |

Models dir: `{BASE}/models/`. Marks broken GPU backends via `env_setup.mark_backend_broken` + `gpu_backend_broken` setting.

> `local_env_section.py` mirrors much of the local-model catalog/download API for the **settings UI section** (parallel surface over the same domain). Prefer `local_llm_client` for inference truth.

### GUI entry / self-heal — `gui.py`

| Function | Role |
|----------|------|
| `_acquire_single_instance_lock` | Windows named mutex / file lock — single instance |
| `_ensure_dependencies_before_startup` | Full diagnostics via `env_setup.run_full_diagnostics`; `get_broken_critical`; recovery dialog |
| `_show_startup_recovery_window` | Repair broken **critical** packages |
| `_show_startup_install_window` | Safe reinstall path after restart (`install_variant_on_startup`) |
| `main` | `updater.check_startup_health()` first → `create_main_window` → mainloop |

Optional components (e.g. `llama_cpp`, `rvc_python`) are **not** treated as critical startup blockers.

---

## Pronunciation dictionary

Implemented by `WordReplacer` (`engine/word_replacer.py`). **Single source of truth:** root `word_rules.json` (no hard-coded seed that resurrects deleted words).

Examples of letter-style rules (auto / historical):

```text
AI      → ay-eye
CPU     → C-P-U
GPU     → G-P-U
OpenAI  → Open-Eh-Eye
```

- Category priority when building flat rules: **`builtin → auto → ai_corrected → custom`** (later overrides earlier)  
- `apply(text, persist_new=True)` — main pass; can auto-add heuristic terms  
- Conductor may `add_rule(..., category="ai_corrected")` mid-generation  
- UI: **📖 Dictionary** — add / edit / remove; optional dry-run path in window backend  
- Backups: timestamped copies under backup dir (keeps last **30**) before save  

---

## Diagnostics & self-healing

Core lives in **`engine/env_core/`**, re-exported via `engine/env_core/__init__.py` (and often `engine.env_setup` as a facade).

### Package surface (`env_core/__init__.py`)

Re-exports:

| Area | Symbols |
|------|---------|
| CPU/GPU | `detect_cpu`, `detect_gpu`, `PYTHON_EXE`, `PROJECT_ROOT` |
| Torch | `install_torch`, `uninstall_torch`, `torch_status`, `cancel_install_torch`, `clean_torch_cache`, variant helpers, `SITE_PACKAGES`, version constants |
| llama-cpp | `install_llama_cpp`, `uninstall_llama_cpp`, `llama_cpp_status`, `get_installed_backend`, `resolve_backend`, `get_startup_install_state`, `cleanup_orphaned_checkpoint` |
| RVC | `install_rvc`, `uninstall_rvc`, `rvc_status` |
| Diagnostics | `run_full_diagnostics`, `scan_for_garbage`, `finalize_deletion`, `run_error_recovery`, `get_broken_critical`, `get_optional_status`, `CRITICAL_COMPONENTS`, `OPTIONAL_COMPONENTS`, cache helpers, env info |

### Hardware detect — `cpu_gpu.py`

| Function | Returns |
|----------|---------|
| `detect_cpu()` | `{name, flags, avx, avx2, fma, f16c}` via `py-cpuinfo` when available |
| `detect_gpu()` | `{vendor, name, cuda_version, vram_gb}` — NVIDIA via `nvidia-smi`; AMD/Intel via WMI + registry VRAM |

### Diagnostics — `diagnostics.py`

| Constant / API | Role |
|----------------|------|
| `CRITICAL_COMPONENTS` | `numpy`, `torch`, `torchaudio`, `torchvision`, (+ TTS/GUI audio stack as implemented) — **must work** for app audio/GUI |
| `OPTIONAL_COMPONENTS` | `{llama_cpp, rvc_python}` — missing ≠ critical failure |
| `run_full_diagnostics(force_refresh=False)` | **Isolated subprocess** probes all key libs (never locks `.pyd` in app process); hybrid cache on site-packages mtime/count |
| `get_broken_critical(results)` | Broken **critical** only (excludes optional + SKIPPED-waiting-numpy) |
| `get_optional_status(results)` | `ok` / `not_installed` / `broken` for optional modules |
| `scan_for_garbage(mode="fast", progress_cb=None)` | Scan temp/logs/cache; transactional quarantine; baseline diagnostics before/after |
| `finalize_deletion(quarantined_list)` | Commit quarantine deletion after successful post-scan |
| `run_error_recovery(progress_cb=None)` | Reinstall packages from deletion history; adaptive torch variant; log to `logs/recovery_pip_output.log` |
| `clear_diagnostics_cache` / `clean_pip_download_cache` | Force re-check / free pip cache |
| `parse_requirements_txt` | Frozen pins for recovery |
| `_clean_dataclasses_backport` | Remove shadowing `dataclasses` package that breaks torch/pip on 3.11 |
| `_read_pip_output` / `_install_watchdog` | Shared install UX helpers |

Paths: `SITE_PACKAGES` = `python/xtts_env/Lib/site-packages`, quarantine under env, `.known_safe_files.json`, `.env_diagnostics_cache.json`.

### Torch setup — `torch_setup.py`

| API | Role |
|-----|------|
| `torch_status()` | Subprocess import probe + version + CUDA available |
| `install_torch(progress_cb, resume, variant)` | Install torch/torchaudio/torchvision to portable target |
| `uninstall_torch` / `cancel_install_torch` / `clean_torch_cache` | Lifecycle |
| `_pick_torch_variant(gpu_info)` | `cu118` vs `cpu` from preference + GPU + broken list |
| `mark_torch_variant_broken` / `get_broken_torch_variants` | Persist bad variants |
| Checkpoint helpers | Resume interrupted install |

Aligns with RVC install (`rvc_setup.detect_torch_build` reuses the same variant logic).

### llama-cpp setup — `llama_setup.py`

| API | Role |
|-----|------|
| `llama_cpp_status()` | Integrity + import probe |
| `install_llama_cpp(progress_cb, resume, backend, model_path)` | CPU source build or CUDA/Vulkan prebuilt wheels |
| `uninstall_llama_cpp` | Remove package |
| `_pick_llama_backend(gpu_info)` | nvidia+cuda → CUDA wheel; amd/intel → Vulkan; else CPU |
| `mark_backend_broken` / `get_broken_backends` | `.llama_broken_backends.json` |
| `smoke_test_gpu_init(backend, model_path)` | Real Llama init with `n_gpu_layers=-1` |
| `resolve_backend()` | CPU/GPU + install command preview |
| `get_startup_install_state` / `cleanup_orphaned_checkpoint` | Resume safety |

### RVC setup — `rvc_setup.py`

See [RVC voice enhancement](#rvc-voice-enhancement) (`install_rvc`, `rvc_status`, fairseq wheels, constraints).

### Startup wiring

`gui.py` → `_ensure_dependencies_before_startup` uses `run_full_diagnostics` + `get_broken_critical` and may open recovery UI. Optional modules do not block launch.

---

## Update system

Implemented in **`engine/updater.py`** (function API, not a class named `Updater`).

### Public API

| Function | Description |
|----------|-------------|
| `get_local_version()` | Read local version |
| `get_remote_version_info()` | Fetch remote `version.json` |
| `check_update()` | Compare local/remote; returns `available`, `files`, `sha256`, `removed_files`, `changelog`, `min_app_version`, `needs_manual_reinstall`, `commit_sha` |
| `apply_update(files, sha256_map=None, removed_files=None, progress_callback=None, cancelled_flag=None, commit_sha=None)` | Full safe apply cycle |
| `check_startup_health() -> "ok"\|"first_attempt"\|"rolled_back"` | **First** call at app start (before GUI) |
| `confirm_update_success()` | Call after main window opens successfully |
| `has_pending_update_confirmation()` | Marker present? |
| `rollback_update()` | Restore from backup |
| `collect_update_diagnostics(check_result=None)` | Text dump for support |
| `restart()` | Relaunch process |
| `_urlopen_with_retry` / `_is_cancelled` | Shared by other modules (e.g. RVC catalog) |

### Apply cycle (`apply_update`)

1. Download **all** files to staging (cancelable; SHA256 if in manifest; retries on mismatch)  
2. Fail any → abort, leave live tree untouched  
3. **Point of no return:** backup current (+ files to be removed)  
4. Move staged → live  
5. Delete `removed_files` (refactors / renames)  
6. Write local `version.json` + **rollback marker**  
7. Clear staging  

Cancel works through download/verify; not mid file-swap.

### Startup confirmation

```text
check_startup_health()
  no marker → "ok"
  first launch after update → "first_attempt" (must later call confirm_update_success)
  second launch without confirm → auto rollback_update() → "rolled_back"
```

`gui.main()` calls health check first; main window success path must call `confirm_update_success()`.

Manual reinstall when `local < min_app_version` (`needs_manual_reinstall`).

---

## Requirements

| | Default (CPU) | With CUDA |
|---|---|---|
| OS | Windows 10/11 x64 | Windows 10/11 x64 |
| Memory | 8+ GB RAM | 8+ GB RAM |
| GPU | — | NVIDIA, 4+ GB VRAM, Compute Capability 6.0+ |
| Speed | slower than real-time | often faster than real-time |

Works on CPU right after unpack. CUDA is optional via **⚙ Settings → Acceleration**.

---

## Data & config files

| File | Purpose |
|---|---|
| `settings.json` | session: presets (`quality_params` incl. RVC), theme, UI language, panel, text size, last settings tab |
| `gpt_settings.json` | AI provider, keys, models |
| `word_rules.json` | pronunciation dictionary |
| `word_rules_backups/` | dictionary backups |
| `chat_history.json` | AI chat sessions |
| `history.json` | generation history |
| `version.json` | version + updater (`min_app_version`) |
| `checksums.txt` | SHA256 for updates |
| `env_cache.cfg` | environment scan cache |
| `theme_settings.json` | theme constructor state |
| `json/rvc_catalog_seed.json` | offline RVC catalog seed |
| `models/rvc/` | local RVC models + catalog cache |
| `.known_safe_files.json` | diagnostics / recovery registry |
| `.llama_broken_backends.json` | failed llama.cpp backends (skip next time) |

---

## Project structure

**Entry point:** `XTTS Studio.exe` → BAT → `python\runtime\python.exe` → `gui.py` → `python\xtts_env`

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

## engine/ by responsibility

### Generation pipeline

- **`tts_runner.py`** — thin entry; real `run_tts()` in **`engine/tts/`**: normalize → word replacer → chunk → conductor → generate → merge. Lazy model singleton, embedding + chunk cache (md5), silence trim, RMS normalize.  
- **`engine/tts/qc.py`** — loop detector, duration validator, retries.  
- **`engine/tts/device.py`** — CUDA/CPU detection.  
- **`engine/tts/cache.py` / `export.py`** — cache + WAV/MP3.  
- **`chunker.py`** — sentences, merge/split, initials SBD, bad boundary checks.  
- **`normalizer.py`** — numbers, abbreviations, punctuation, ё-fication.  
- **`word_replacer.py` / `word_replacer_window.py`** — dictionary categories, dry-run, backups.  
- **`smart_pauses.py` / `prosody_layer.py`** — skipped when AI Conductor is active (pauses/schedule from `conductor_map`).  
- **`rvc_pipeline.py`** — `RVCPostProcessor` / `XTTSWithRVCPipeline` via `rvc-python` (not a class named `RVCPipeline`).  
- **`rvc_catalog.py`** — seed / cache / GitHub catalog / voice-models search / download.  
- **`env_core/rvc_setup.py`** — `install_rvc` / `uninstall_rvc` / `rvc_status` for portable env.  

### AI module

- **`ai_conductor.py`** — `conduct()`, rewrite, corrections → dictionary; levels gated; never aborts TTS on AI failure.  
- **`gui/chat_window.py` + `gui/chat_window/`** — chat UI + modules.  
- **`gpt_client.py`** — cloud chain, keys, catalog.  
- **`local_llm_client.py` / `local_env_section.py` / `env_setup.py`** — offline LLMs.  
- **`gui/ai_status_window.py`** — chain diagnostics.  

### Voice and audio

- **`reference_processor.py`** — WAV convert, SNR, cache.  
- **`voice_manager.py`** — `library/` scan, active voice.  
- **`de_esser.py`** — sibilance on final file.  

### Infrastructure

- **`task_manager.py` / `task_models.py`** — `TaskManager`: queue worker calling `run_tts`; `add_task`, `cancel_task` (flag on current or queued), `get_queue`, UI notify.  
- **`history_store.py`** — `save_history(task)` → prepend to `history.json` (max **100** entries: date, text, voice, quality, output, duration, chunks).  
- **`updater.py`** — see [Update system](#update-system).  
- **`i18n.py`** — RU/EN dictionary (incl. RVC/search keys).  
- **`gui/settings_ui.py`** — `save_settings` / `apply_settings`: full `quality_params` dump (incl. RVC), merge write.  

### Voice library & reference

- **`voice_manager.py`** — `VoiceManager` / `VoiceProfile`: scan `library/`, list/get/set_active, delete, rename; profile fields `original` / `converted` / `normalized` / `embedding`.  
- **`reference_processor.py`** — `ReferenceProcessor` + `AdaptiveSilenceTrimmer` + `SNRAnalyzer`:
  - convert/normalize reference into voice folder under `library/`
  - adaptive silence trim (hard limit 250 ms + padding)
  - SNR quality: excellent ≥25 dB · good ≥15 · poor ≥8 · bad &lt;3 (optional `snr_callback` for GUI)

---

## Development

Built with AI-assisted tooling (Claude, ChatGPT, and others). Architecture refactor (`engine/` + `engine/gui/`), localization, light theme, and UI polish used **[Arena.ai](https://arena.ai) Agent Mode** (multi-model agent).

Tests: **pytest** in `test/` (`RUN_TESTS.bat`) covering updater, chunker, normalizer, smart pauses, etc.

Tools in `tools/`:

- `generate_version_files.py` — `version.json` / update manifest  
- `convert_py_to_txt.bat` — `.py` → `.txt` for AI paste  
- `analyze.ps1` — structure snapshot for AI context  
- `git_update.py` / `git_update.bat` — publish to GitHub (app updates still via `updater.py`, not git pull)  
- `cleanup_project.ps1` / `restore_quarantine.ps1` — quarantine instead of hard delete  

---

## Third-party / license notes

- **XTTS v2** (Coqui) — [Coqui Public Model License (CPML)](https://coqui.ai/cpml). Model use is governed by CPML regardless of this project’s license.  
- Project license: see **[LICENSE.md](./LICENSE.md)** (attribution required).  
- Community RVC models (voice-models.com / Hugging Face / etc.) remain under their own licenses; the app only indexes/downloads what the user requests.  

---

## Support

**BTC:** `bc1qz78u3lvagt3v886359glv57ct6rnlh506wjmdy`

---

**XTTS Studio** · by EXIZ10TION · [README EN](./README.EN.md) · [README RU](./README.RU.md) · [License](./LICENSE.md)
