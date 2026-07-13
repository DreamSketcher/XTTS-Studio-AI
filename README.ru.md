<div align="center">

**[English](./README.EN.md)** · **[Русский](./README.RU.md)**

# 🎙️ XTTS Studio

### Клонируй любой голос. Озвучивай любой текст. Без интернета.

**Портативный офлайн voice cloning и text-to-speech для Windows — на базе XTTS v2**

<br/>

[![Windows](https://img.shields.io/badge/Windows-10%2F11%20x64-0078D6?logo=windows&logoColor=white)](#-скачать)
[![Offline](https://img.shields.io/badge/100%25-Offline-2da44e)](#почему-xtts-studio)
[![Portable](https://img.shields.io/badge/Portable-без%20установки-orange)](#-скачать)
[![RU/EN](https://img.shields.io/badge/UI-RU%20%2F%20EN-58a6ff)](#возможности-кратко)
[![RVC](https://img.shields.io/badge/RVC-улучшение%20голоса-e11d48)](#возможности-кратко)
[![Themes](https://img.shields.io/badge/Темы-Тёмная%20%2F%20Светлая-7c3aed)](#возможности-кратко)

<br/>

<!-- DEMO VIDEO
[![Смотреть демо](images/demo-thumb.png)](https://youtu.be/YOUR_DEMO_VIDEO)
-->

<!-- HERO GIF
![XTTS Studio в деле](images/demo-hero.gif)
-->

**[📥 Скачать](# -скачать (https://github.com/DreamSketcher/XTTS-Studio/releases/tag/v1)** · **[🎧 Примеры звука](#-послушать)** · **[📖 Документация RU](./DOCUMENTATION.RU.md)** · **[📖 Docs EN](./DOCUMENTATION.EN.md)** · **[📜 Лицензия](./LICENSE.md)**

</div>

---

## Почему XTTS Studio

Большинство голосовых сервисов хотят ваши данные, подписку и постоянный интернет.

**XTTS Studio — иначе:**

| | Облачный TTS | XTTS Studio |
|---|---|---|
| Нужен интернет | Всегда | **Никогда** (AI-модуль — по желанию) |
| Установка | Аккаунты, драйверы, клиенты | **Распаковал — запустил** |
| Голос и текст уходят с ПК | Да | **Нет** |
| Длинные тексты | Часто лимиты | **Без лимита длины** |
| GPU | Часто только в платных тарифах | **CPU бесплатно · CUDA по запросу** |

Одна папка. Один двойной клик. Ваш компьютер — ваши правила.

---

## Послушать

> Секция ДЕМО.

<!-- АУДИО
### Один текст · разные голоса
| Пример | Слушать |
|--------|---------|
| Нарратив RU | [▶ sample-narrative-ru.mp3](media/sample-narrative-ru.mp3) |
| Динамика EN | [▶ sample-dynamic-en.mp3](media/sample-dynamic-en.mp3) |
| Клон A → клон B | [▶ sample-clone-ab.mp3](media/sample-clone-ab.mp3) |
| Только XTTS vs XTTS+RVC | [▶ sample-rvc-compare.mp3](media/sample-rvc-compare.mp3) |
-->

```text
[ media/demo-before-after.mp3 ]   ← placeholder
[ media/demo-rvc-enhance.mp3 ]    ← placeholder
[ media/demo-long-form.mp3 ]      ← placeholder
```

---

## Возможности (кратко)

### 🎤 Голос, который звучит *как человек*

- Клонирование с референса **10–20 с**  
- Библиотека голосов с кэшем эмбеддингов  
- **RVC-постобработка** — второй этап на каждый чанк (index, pitch, f0)  
- **Встроенный выбор RVC-модели** — локальные + офлайн seed + опциональный online-поиск (voice-models / Hugging Face)  
- Установка RVC-стека в portable-окружение в один клик (fairseq wheel под Windows)  
- Длинные формы: книги, сценарии, реклама, закадр  

### 🧠 Текст, который читается естественно

- Числа → слова, аббревиатуры → словарь  
- **Ёфикация**, умные паузы, чистая просодия  
- Защита инициалов: «А. С. Пушкин» не рвётся на мусорные куски  

### 🎛 Качество под контролем

- **4 пресета:** Высокое качество · Нарратив · Динамика · Экспрессия  
- **Вкладки настроек пресета** (закреплены сверху): RVC · Обрезка · Вывод · XTTS  
- Тонкая настройка (temperature, speed, trim, де-эссер, QC, RVC…) — **сохраняется между сессиями**  
- QC чанков с авто-перегенерацией при зацикливании / обрывах  
- Экспорт **WAV** и **MP3**  

### 🤖 AI — когда нужно; офлайн — когда не нужно

- Опциональный **AI Conductor** — temperature/speed/паузы по чанкам (+ rewrite стиля)  
- Встроенный **AI-чат** + цепочка провайдеров (Groq / OpenRouter / RU proxy / custom)  
- **Локальные GGUF LLM** in-process (llama-cpp) — каталог, докачка, CPU/GPU с безопасным fallback  

### 🖥 Десктоп, а не «страница в браузере»

- Тёмная / светлая тема + конструктор тем  
- Интерфейс **RU / EN**  
- Портативная раскладка, неон, адаптивный toolbar  
- Безопасные авто-обновления: **SHA256** + откат  

---

## Скриншоты

<p align="center">
  <img src="images/main.PNG" width="45%" alt="Главное окно" />
  <img src="images/mail-light.PNG" width="45%" alt="Светлая тема" />
</p>

<p align="center">
  <img src="images/ai-assist.PNG" width="45%" alt="AI-ассистент" />
  <img src="images/settings.PNG" width="45%" alt="Настройки" />
</p>

<p align="center">
  <img src="images/ai-settings.PNG" width="45%" alt="AI-настройки" />
</p>

<!-- ЕЩЁ ВИЗУАЛ
### GIF по UI
![Вкладки настроек](images/demo-settings-tabs.gif)

### Выбор RVC-модели
![RVC dropdown](images/demo-rvc-dropdown.gif)

### Генерация
![Generate](images/demo-generate.gif)
-->

---

## Скачать

> ⚠️ Google Drive может показать *«файл слишком большой для проверки»* — это нормально для portable-сборки, не признак вируса.

**Одна сборка для всех** — [📥 Скачать XTTS Studio](https://YOUR_DOWNLOAD_LINK_HERE)

- Сразу после распаковки работает на **CPU**  
- Есть **NVIDIA GPU**? Включите CUDA в **⚙ Настройки → Ускорение** — поставит только нужные пакеты  

📜 **Лицензия:** [LICENSE.md](./LICENSE.md) — бесплатно, с указанием автора  

---

## Старт за 60 секунд

1. Распакуйте архив (**без кириллицы в пути**)  
2. Запустите `XTTS Studio.exe`  
3. Выберите референс **10–20 с**  
4. Вставьте текст → **🚀 ГЕНЕРИРОВАТЬ**  
5. Аудио — в `outputs/` (или **🎵 Аудио**)  

```text
✔  C:\XTTS\
✘  C:\Новая папка\XTTS\
```

---

## Кому подойдёт

- **Креаторы** — YouTube, реклама, подкасты, character VO  
- **Авторы и студии** — аудиокниги, длинный закадр  
- **Команды с приватностью** — тексты, которые не должны уходить в облако  
- **Продвинутые** — пресеты, RVC, локальный AI, конструктор тем  

---

## Требования

| | CPU (по умолчанию) | CUDA (опционально) |
|---|---|---|
| ОС | Windows 10/11 x64 | Windows 10/11 x64 |
| RAM | 8+ ГБ | 8+ ГБ |
| GPU | — | NVIDIA, 4+ ГБ VRAM, CC 6.0+ |
| Скорость | медленнее real-time | часто быстрее real-time |

---

## Документация

Эта страница — **продуктовый pitch**.

Архитектура, карта модулей, словарь, диагностика, updater, дерево проекта:

### 👉 **[DOCUMENTATION.RU.md](./DOCUMENTATION.RU.md)** · **[DOCUMENTATION.EN.md](./DOCUMENTATION.EN.md)**

Внутри:

- Пайплайн: референс → текст → чанки → RVC → экспорт  
- AI-модуль, локальные LLM, провайдеры  
- Словарь произношений и бэкапы  
- Диагностика / self-heal  
- Обновления (SHA256, staging, rollback)  
- Полная структура папок  

Справочник функций: [unified_function_reference.RU.md](./unified_function_reference.RU.md) · [EN](./unified_function_reference.EN.md)

---

## Поддержать проект

Если XTTS Studio экономит вам время или деньги:

**BTC:** `bc1qz78u3lvagt3v886359glv57ct6rnlh506wjmdy`

---

## Сторонние компоненты

Используется **XTTS v2** (Coqui) по [Coqui Public Model License (CPML)](https://coqui.ai/cpml). Использование модели регулируется CPML независимо от лицензии проекта.

---

<div align="center">

**XTTS Studio** · by EXIZ10TION · Made with ❤️

[Скачать](#-скачать) · [Docs RU](./DOCUMENTATION.RU.md) · [Docs EN](./DOCUMENTATION.EN.md) · [Лицензия](./LICENSE.md)

</div>
