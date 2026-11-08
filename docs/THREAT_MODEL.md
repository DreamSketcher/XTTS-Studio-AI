# Threat Model — XTTS Studio AI

Документ описывает поверхность атаки и меры защиты XTTS Studio AI. Цель — явная
модель, а не имплицитные допущения: какие активы защищаем, какие trust boundaries,
кто attacker, что реализовано и что пока нет. Обновляется вместе с кодом (PR,
меняющий updater/env_core/security, обязан актуализировать этот файл — см. CONTRIBUTING).

## 1. Trust boundaries (границы доверия)

Данные пересекают эти границы; каждое пересечение — точка возможной атаки.

| Boundary | Описание | Уровень доверия по умолчанию |
|----------|----------|------------------------------|
| **App release** | Файлы релиза, которые приложение само себе обновляет | Доверяем ТОЛЬКО при валидной Ed25519-подписи manifest (`version.json.sig`) + SHA-256 каждого update-файла |
| **Update manifest** | `json/version.json` + `.sig` с GitHub | Недоверенный, пока Ed25519-подпись не проверена ДО разбора JSON |
| **User text** | Текст, вводимый пользователем для озвучки | Доверенный (данные пользователя), но безграничный по объёму |
| **Voice reference** | Загружаемый пользователем образец голоса | Недоверенный по содержимому: нормализуется, проверяется SNR, ограничивается 30 c |
| **RVC `.pth` / `.index`** | Сторонние community-чекпоинты | **Недоверенный.** Требует явного подтверждения доверия, привязанного к SHA-256 байтов; pickle-RCE поверхность |
| **GGUF `.gguf`** | Локальные LLM-модели (каталог или ручные) | Каталог — проверка sha256+size; ручные — `verified=False`, warning-модал |
| **Custom API endpoint** | Пользовательский OpenAI-совместимый провайдер | Недоверенный URL: только HTTPS (HTTP только loopback); extra-заголовки проходят denylist |
| **Bundled Python env** | `python/xtts_env`, `python/runtime` | Доверенный (управляется проектом); не системный Python |
| **XTTS engine download** | Файлы движка XTTS v2 в `models/xtts_v2/`, скачиваемые при первом запуске | Список — закреплённая ревизия `coqui/XTTS-v2` (HF); SHA-256 для `.pth`, точные размеры, JSON-проверки; атомарная установка |
| **Logs** | `logs/`, диагностика | Могут содержать пути/ошибки; API-ключи защищены DPAPI, но логи считаем чувствительными при репортинге |

## 2. Assets (активы)

| Актив | Где | Угроза при компрометации |
|-------|-----|--------------------------|
| **API-ключи** AI-провайдеров | `json/gpt_settings.json` (DPAPI) | Кража → несанкционированные вызовы/расход |
| **Voice samples** (референсы) | `library/<voice>/` | Утечка биометрии (голос) |
| **Generated audio** | `outputs/` | Утечка приватного контента |
| **User text** | Рантайм (редактор) + `history.json` | Утечка приватного/конфиденциального текста |
| **XTTS/RVC/GGUF models** | `models/` | Подмена → RCE через pickle/unsafe-load (движок XTTS v2 докачивается с проверкой SHA-256) |

## 3. Attackers (модели нарушителя)

| Attacker | Возможности | Мотив |
|----------|-------------|-------|
| **Malicious model author** | Публикует `.pth`/`.gguf` с вредоносным pickle payload в каталог | RCE через unsafe-load на машинах пользователей |
| **MITM на update-канал** | Перехват трафика GitHub/release | Подмена update-файлов → персистентный бэкдор |
| **Malicious custom endpoint** | Пользователь вводит атакующий API URL | Попытка перехвата Authorization/текста; downgrade |
| **Local malware** | Доступ к файлам пользователя | Чтение/подмена `gpt_settings.json`, models, логов |
| **Compromised dependency** | Злонамеренный/уязвимый PyPI-пакет в граф | RCE/DoS через уязвимость рантайма |

## 4. Mitigations (что реализовано)

| Угроза | Реализованная мера | Где |
|--------|--------------------|-----|
| MITM на update | Ed25519 manifest signature, проверяемая **до** разбора JSON; SHA-256 обязателен для каждого update-файла | `engine/update_signing.py`, `engine/updater.py`, `test/test_sha256_verification.py` |
| Path traversal в updater | Операции updater ограничены корнем приложения | `engine/updater.py` |
| Подмена XTTS-движка при скачивании | Закреплённая ревизия официального репозитория `coqui/XTTS-v2` (HF); SHA-256 `.pth` (официальные LFS-хешы) + md5 model.pth из официального `hash.md5`; точный размер всех файлов; JSON-валидация config/vocab; атомарная установка; докачка Range; `.part` не исполняется | `engine/xtts_engine.py`, `engine/gui/engine_download.py` |
| Malicious RVC `.pth` (pickle RCE) | Доверие чекпоинту — явное, привязано к SHA-256 байтов; HTML/пустой файл детектится | `engine/rvc_pipeline.py` (`mark_rvc_checkpoint_trusted`/`require_rvc_checkpoint_trusted`), `test_rvc_pipeline.py` |
| Malicious GGUF filename / traversal | `safe_filename` + containment-check `commonpath` | `engine/local_llm_client.py` (TASK-004), `test_local_llm_security.py` |
| Подмена GGUF из каталога | Обязательные `sha256`/`size_bytes`; проверка после скачивания + удаление при несовпадении | `engine/local_llm_client.py` (TASK-007) |
| Embedding cache (torch.load RCE) | `weights_only=True` + строгая схема | `engine/tts/` |
| Compromised dependency | pip-audit blocking gate (High/Critical) + allowlist; SBOM; (PLAN) hash-locked `requirements.lock` | `tools/pip_audit_gate.py`, `json/sbom.cdx.json`, `requirements.lock` (TASK-001/017) |
| Custom endpoint override sensitive headers | Denylist (Authorization/Host/Cookie/и т.п.), override → warning + ignore | `engine/gpt_client.py` (TASK-005) |
| Plaintext API keys | Windows DPAPI + миграция из legacy plaintext при первом чтении | `engine/secret_store.py`, `gpt_client.py` |
| HTTP downgrade для AI | HTTPS обязательно; HTTP только для loopback | `gpt_client._validate_api_url` |
| RVC CLI / system-python injection | Абсолютный `PYTHON_EXE`; отсутствие `tools/RVC_CLI/rvc.py` → `RVCNotAvailableError` (не fallback на system `rvc`/`python`) | `engine/rvc_pipeline.py` (TASK-006) |
| Race при settings write | Атомарная запись (temp + `os.replace` + fsync) | `gpt_client._write_all_settings` |
| Single-instance (гонка над settings) | Windows named mutex / файловый lock | `gui.py` |

## 5. Gap analysis (что НЕ реализовано / частично)

| Зазор | Статус | План |
|-------|--------|------|
| **Authenticode EXE-подпись** | Не применяется (нет code-signing сертификата) | До сертификата integrity обеспечивает Ed25519 manifest; после — code-signing gate |
| **rvc-python/fairseq transitive CVE** | Не в `requirements.txt`/pip-audit (ставятся отдельно через `--no-deps`) | Периодическая ручная проверка версий в `engine/env_core/rvc_setup.py` |
| **Hash-locked runtime graph** | `requirements.lock` существует, но без `--hash` (генерация требует сетевого доступа мейнтейнером) | TASK-017: первый прогон `generate_requirements_lock.py` + installer с `--require-hashes` |
| **CodeQL/Dependabot** | Настроены (TASK-016), но первый прогон в CI покажет реальный набор находок | Triage после первого запуска |
| **Voice reference abuse** (слишком длинный/противоречивый) | Ограничение 30 c + SNR-оценка; нет detection malicious audio | Приемлемо: voice reference — данные доверенного пользователя |
| **UI security-уведомления** | License-notice перед RVC/GGUF download; unverified-model warning — реализованы (TASK-007/010) | — |

## 6. Out of scope

- Защита от local malware с правами администратора (выше возможностей приложения);
- Валидация семантической безопасности сторонних моделей (только целостность/доверие байтов);
- Защита cloud AI-провайдеров от компрометации (зона ответственности провайдера).

## Связанные документы

- [SECURITY.md](./SECURITY.md) — политика disclosure, gate уязвимостей;
- [SECURITY_BASELINE.md](./SECURITY_BASELINE.md) — зафиксированные версии и задокументированные исключения;
- [PRIVACY.md](./PRIVACY.md) — обработка персональных данных.
