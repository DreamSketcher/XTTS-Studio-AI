<div align="center">

**[Русский](./README.ru.md)** · **[English](./README.md)**

# 🎙️ XTTS Studio

### Clone any voice. Speak any text. Stay offline.

**Portable offline voice cloning & text-to-speech for Windows — powered by XTTS v2**

<br/>

[![Windows](https://img.shields.io/badge/Windows-10%2F11%20x64-0078D6?logo=windows&logoColor=white)](https://github.com/DreamSketcher/XTTS-Studio/releases/tag/v1)
[![Offline](https://img.shields.io/badge/100%25-Offline-2da44e)](https://github.com/DreamSketcher/XTTS-Studio)
[![Portable](https://img.shields.io/badge/Portable-no%20install-orange)](https://github.com/DreamSketcher/XTTS-Studio/releases/tag/v1)
[![RU/EN](https://img.shields.io/badge/UI-RU%20%2F%20EN-58a6ff)](https://github.com/DreamSketcher/XTTS-Studio)
[![RVC](https://img.shields.io/badge/RVC-voice%20enhance-e11d48)](https://github.com/DreamSketcher/XTTS-Studio)
[![Themes](https://img.shields.io/badge/Themes-Dark%20%2F%20Light-7c3aed)](https://github.com/DreamSketcher/XTTS-Studio)

<br/>

**[📥 Download](https://github.com/DreamSketcher/XTTS-Studio/releases/tag/v1)** · **[🎧 Hear samples](#-hear-it)** · **[📖 Documentation](./DOCUMENTATION.EN.md)** · **[📜 License](./LICENSE.md)**

</div>

---

## Why XTTS Studio

Most voice tools want your data, your subscription, and a permanent internet connection.

**XTTS Studio is different:**

| Feature                  | Cloud TTS          | XTTS Studio                     |
|--------------------------|--------------------|---------------------------------|
| Internet required        | Always             | **Never** (AI optional)         |
| Installation             | App + accounts     | **Unpack & run**                |
| Your voice/text leaves PC| Yes                | **No**                          |
| Long scripts             | Often limited      | **No length limit**             |
| GPU                      | Often paid         | **CPU free · CUDA on demand**   |

One portable folder. One double-click. Your machine, your rules.

---

## Hear it

> Real demos are coming soon — they sell better than any feature list.

```text
[ media/demo-before-after.mp3 ]     ← placeholder
[ media/demo-rvc-enhance.mp3 ]      ← placeholder
[ media/demo-long-form.mp3 ]        ← placeholder
```

---

## Features at a glance

### 🎤 Voice that sounds like *someone*

- Clone from a **10–20 s** reference clip
- Voice library with cached embeddings
- **RVC post-processing** — per-chunk second stage (index rate, pitch, f0)
- Built-in RVC model picker (local + offline catalog + optional Hugging Face search)
- One-click RVC stack installation (Windows-safe wheels)
- Long-form ready: books, scripts, ads, narration

### 🧠 Text that reads naturally

- Numbers → words, abbreviations → dictionary
- Russian **ё-restoration**, smart pauses, clean prosody
- Initials protected (`А. С. Пушкин`)

### 🎛 Quality you control

- **4 presets:** High Quality · Narrative · Dynamic · Expressive
- Sticky tabbed settings (RVC · Trim · Output · XTTS)
- Fine-tuning saved between sessions
- Chunk QC with auto-retry
- Export **WAV** or **MP3**

### 🤖 AI when you want it — offline when you don’t

- Optional **AI Conductor** (per-chunk temperature/speed/pauses + style rewrite)
- Built-in **AI chat** with multi-provider fallback (Groq / OpenRouter / RU proxy)
- **Local GGUF LLMs** (llama-cpp) with safe fallback

### 🖥 Desktop app, not a browser toy

- Dark / light themes + full theme constructor
- RU / EN interface
- Portable layout with neon accents
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

---

## Download

> ⚠️ Google Drive may show *“file too large to scan”* — normal for portable builds.

**[📥 Download XTTS Studio](https://github.com/DreamSketcher/XTTS-Studio/releases/tag/v1)**

- Runs on **CPU** immediately after unpacking
- NVIDIA GPU? Enable CUDA in **⚙ Settings → Acceleration**
- **License:** [LICENSE.md](./LICENSE.md) — free with attribution

---

## 60-second start

1. Unpack the archive (**no Cyrillic in the path**)
2. Run `XTTS Studio.exe`
3. Pick a **10–20 s** voice reference
4. Paste text → **🚀 GENERATE**
5. Find audio in `outputs/` folder

```text
✔  C:\XTTS\
✘  C:\Новая папка\XTTS\
```

---

## Who it’s for

- **Creators** — YouTube, ads, podcasts, character VO
- **Authors & studios** — audiobooks, long narration
- **Privacy-first teams** — scripts that must not leave the LAN
- **Power users** — presets, RVC, local AI, theme control

---

## Requirements

|                  | CPU (default)       | CUDA (optional)               |
|------------------|---------------------|-------------------------------|
| **OS**           | Windows 10/11 x64   | Windows 10/11 x64             |
| **RAM**          | 8+ GB               | 8+ GB                         |
| **GPU**          | —                   | NVIDIA, 4+ GB VRAM, CC 6.0+   |
| **Speed**        | Slower than real-time | Often faster than real-time |

---

## Documentation

This page is the **product pitch**.

| Language | Full Docs                        | Function Reference                     |
|----------|----------------------------------|----------------------------------------|
| English  | [DOCUMENTATION.EN.md](./DOCUMENTATION.EN.md) | [unified_function_reference.EN.md](./unified_function_reference.EN.md) |
| Русский  | [DOCUMENTATION.RU.md](./DOCUMENTATION.RU.md) | [unified_function_reference.RU.md](./unified_function_reference.RU.md) |

---

## Support the project

If XTTS Studio saves you time or money:

**BTC:** `bc1qz78u3lvagt3v886359glv57ct6rnlh506wjmdy`

---

## Third-party components

Uses **XTTS v2** (Coqui) under the [Coqui Public Model License (CPML)](https://coqui.ai/cpml).

---

<div align="center">

**XTTS Studio** · by EXIZ10TION · Made with ❤️

[Download](https://github.com/DreamSketcher/XTTS-Studio/releases) · [Docs EN](./DOCUMENTATION.EN.md) · [Docs RU](./DOCUMENTATION.RU.md) · [License](./LICENSE.md)

</div>
