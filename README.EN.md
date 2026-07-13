<div align="center">

**[English](./README.EN.md)** · **[Русский](./README.RU.md)**

# 🎙️ XTTS Studio

### Clone any voice. Speak any text. Stay offline.

**Portable offline voice cloning & text-to-speech for Windows — powered by XTTS v2**

<br/>

[![Windows](https://img.shields.io/badge/Windows-10%2F11%20x64-0078D6?logo=windows&logoColor=white)](#-download)
[![Offline](https://img.shields.io/badge/100%25-Offline-2da44e)](#-why-xtts-studio)
[![Portable](https://img.shields.io/badge/Portable-no%20install-orange)](#-download)
[![RU/EN](https://img.shields.io/badge/UI-RU%20%2F%20EN-58a6ff)](#-features-at-a-glance)
[![RVC](https://img.shields.io/badge/RVC-voice%20enhance-e11d48)](#-features-at-a-glance)
[![Themes](https://img.shields.io/badge/Themes-Dark%20%2F%20Light-7c3aed)](#-features-at-a-glance)

<br/>

<!-- DEMO VIDEO: drop a short product trailer here
[![Watch the demo](images/demo-thumb.png)](https://youtu.be/YOUR_DEMO_VIDEO)
-->

<!-- HERO GIF: main UI walkthrough
![XTTS Studio in action](images/demo-hero.gif)
-->

**[📥 Download](#-download)** · **[🎧 Hear samples](#-hear-it)** · **[📖 Full documentation](./DOCUMENTATION.EN.md) · [RU](./DOCUMENTATION.RU.md)** · **[📜 License](./LICENSE.md)**

</div>

---

## Why XTTS Studio

Most voice tools want your data, your subscription, and a permanent internet connection.

**XTTS Studio is different:**

| | Cloud TTS | XTTS Studio |
|---|---|---|
| Internet required | Always | **Never** (AI module is optional) |
| Install | App + accounts + drivers | **Unpack & run** |
| Your voice / text leave the PC | Yes | **No** |
| Long scripts | Often limited | **No length limit** |
| GPU | Sometimes locked behind tiers | **CPU free · CUDA on demand** |

One portable folder. One double-click. Your machine, your rules.

---

## Hear it

> Drop real demos here — they sell better than any feature list.

<!-- AUDIO SAMPLES
### Same text · different voices
| Sample | Listen |
|--------|--------|
| Narrative RU | [▶ sample-narrative-ru.mp3](media/sample-narrative-ru.mp3) |
| Dynamic EN | [▶ sample-dynamic-en.mp3](media/sample-dynamic-en.mp3) |
| Clone A → Clone B | [▶ sample-clone-ab.mp3](media/sample-clone-ab.mp3) |
| XTTS only vs XTTS+RVC | [▶ sample-rvc-compare.mp3](media/sample-rvc-compare.mp3) |
-->

```text
[ media/demo-before-after.mp3 ]   ← placeholder
[ media/demo-rvc-enhance.mp3 ]    ← placeholder
[ media/demo-long-form.mp3 ]      ← placeholder
```

---

## Features at a glance

### 🎤 Voice that sounds like *someone*

- Clone from a **10–20 s** reference clip  
- Voice library with cached embeddings (fast re-use)  
- **RVC post-processing** — per-chunk second stage for tighter timbre (index rate, pitch, f0 method)  
- **Built-in RVC model picker** — local models + offline seed catalog + optional online search (voice-models / Hugging Face)  
- One-click install of the RVC stack into the portable env (Windows-safe fairseq wheels, no “compile hell”)  
- Long-form ready: books, scripts, ads, narration  

### 🧠 Text that reads the way people speak

- Numbers → words, abbreviations → dictionary  
- Russian **ё-restoration**, smart pauses, clean prosody  
- Initials protected so “А. С. Пушкин” never tears into junk chunks  

### 🎛 Quality you control

- **4 presets:** High Quality · Narrative · Dynamic · Expressive  
- **Tabbed preset settings** (sticky): RVC · Trim · Output · XTTS — no endless scrolling  
- Per-preset fine-tuning (temperature, speed, trim, de-esser, QC, RVC…) — **saved between sessions**  
- Chunk QC with auto-retry on loops / bad cuts  
- Export **WAV** or **MP3**  

### 🤖 AI when you want it — offline when you don’t

- Optional **AI Conductor** — per-chunk temperature/speed/pauses (+ optional style rewrite)  
- Built-in **AI chat** + multi-provider fallback chain (Groq / OpenRouter / RU proxy / custom)  
- **Local GGUF LLMs** in-process (llama-cpp) — catalog download, resume, CPU/GPU with safe fallback  

### 🖥 Desktop app, not a browser toy

- Dark / light themes + full theme constructor  
- RU / EN interface  
- Portable layout, neon accents, adaptive toolbar  
- Safe auto-update with **SHA256** + rollback  

---

## See it

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
</p>

<!-- MORE VISUALS
### UI walkthrough GIF
![Settings tabs](images/demo-settings-tabs.gif)

### RVC model picker
![RVC dropdown](images/demo-rvc-dropdown.gif)

### Generation flow
![Generate](images/demo-generate.gif)
-->

---

## Download

> ⚠️ Google Drive may show *“file too large to scan”* — expected for a full portable build, not a virus warning.

**One build for everyone** — [📥 Download XTTS Studio](https://YOUR_DOWNLOAD_LINK_HERE)

- Runs on **CPU** immediately after unpack  
- Have an **NVIDIA GPU**? Turn on CUDA in **⚙ Settings → Acceleration** — installs only what your card needs  

📜 **License:** [LICENSE.md](./LICENSE.md) — free to use, attribution required  

---

## 60-second start

1. Unpack the archive (**no Cyrillic in the path**)  
2. Run `XTTS Studio.exe`  
3. Pick a **10–20 s** voice reference  
4. Paste text → **🚀 GENERATE**  
5. Find audio in `outputs/` (or open **🎵 Audio**)  

```text
✔  C:\XTTS\
✘  C:\Новая папка\XTTS\
```

---

## Who it’s for

- **Creators** — YouTube, ads, podcasts, character VO  
- **Authors & studios** — audiobooks, long narration  
- **Privacy-first teams** — scripts that must not leave the LAN  
- **Power users** — presets, RVC, local AI, full theme control  

---

## Requirements

| | CPU (default) | CUDA (optional) |
|---|---|---|
| OS | Windows 10/11 x64 | Windows 10/11 x64 |
| RAM | 8+ GB | 8+ GB |
| GPU | — | NVIDIA, 4+ GB VRAM, CC 6.0+ |
| Speed | slower than real-time | often faster than real-time |

---

## Documentation

This page is the **product pitch**.

| Language | Docs | Function reference |
|----------|------|--------------------|
| English | [DOCUMENTATION.EN.md](./DOCUMENTATION.EN.md) | [unified_function_reference.EN.md](./unified_function_reference.EN.md) |
| Русский | [DOCUMENTATION.RU.md](./DOCUMENTATION.RU.md) | [unified_function_reference.RU.md](./unified_function_reference.RU.md) |

Includes: pipeline (reference → text → chunks → RVC → export), AI / local LLMs, dictionary, diagnostics, updater, full tree.

---

## Support the project

If XTTS Studio saves you time or money:

**BTC:** `bc1qz78u3lvagt3v886359glv57ct6rnlh506wjmdy`

---

## Third-party

Uses **XTTS v2** (Coqui) under the [Coqui Public Model License (CPML)](https://coqui.ai/cpml). Model use is governed by CPML independently of this project’s license.

---

<div align="center">

**XTTS Studio** · by EXIZ10TION · Made with ❤️

[Download](#-download) · [Docs EN](./DOCUMENTATION.EN.md) · [Docs RU](./DOCUMENTATION.RU.md) · [License](./LICENSE.md)

</div>
