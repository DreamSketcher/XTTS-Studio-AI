# История изменений

Все заметные изменения проекта записываются в этот файл.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект придерживается [семантического версионирования](https://semver.org/lang/ru/).

> Этот файл можно править вручную. Агент дополняет его новыми разделами
> и никогда не переписывает уже написанное без явного подтверждения.

## [Не выпущено]

### Добавлено

- eliminate non-ML-stack CVE findings; renew frozen-stack allowlist (CI pip-audit gate)
- новый файл `engine/cpml_consent.py`
- новый файл `engine/gui/engine_download.py`
- новый файл `engine/gui/license_consent.py`
- новый файл `engine/xtts_engine.py`
- новый файл `test/test_cpml_consent.py`
- новый файл `test/test_license_consent.py`
- новый файл `test/test_model_probe.py`
- новый файл `test/test_provider_models.py`
- новый файл `test/test_xtts_engine.py`

### Изменено

- заглушить _request_engine_offer в mock_gen_deps, движок есть в preload-тестах get_tts
- align dependency baseline assertion with nltk 3.10.4 bump
- Провайдеры AI: каталог из 21 провайдера, живые списки моделей (/v1/models) и трекинг состояния
- CPML: перенести недостающие части параллельного фикса issue #4 (ветка arena/f2b6307f)
- Автозагрузка движка XTTS v2 при первом запуске (софт и движок отдельно)
- bump yarl 1.24.2 -> 1.25.1 (aiohttp 3.14.4 requires yarl>=1.25.1)
- engine.batch_window.open_batch_window → engine.gui.license_consent.confirm_coqui_tos (calls)
- engine.cpml_consent._file_agreed → engine.cpml_consent.cpml_consent_path (calls)
- engine.cpml_consent.cpml_consent_path → engine.cpml_consent._base_dir (calls)
- engine.cpml_consent.ensure_coqui_tos_agreed → engine.cpml_consent.is_coqui_tos_agreed (calls)
- engine.cpml_consent.ensure_coqui_tos_agreed → engine.cpml_consent.set_coqui_tos_agreed (calls)
- engine.cpml_consent.ensure_coqui_tos_agreed → engine.tts.__init__.is_coqui_tos_agreed (calls)
- engine.cpml_consent.ensure_coqui_tos_agreed → engine.tts.__init__.set_coqui_tos_agreed (calls)
- engine.cpml_consent.is_coqui_tos_agreed → engine.cpml_consent._env_agreed (calls)
- engine.cpml_consent.is_coqui_tos_agreed → engine.cpml_consent._file_agreed (calls)
- engine.cpml_consent.set_coqui_tos_agreed → engine.cpml_consent.cpml_consent_path (calls)
- engine.gpt_client._live_chain_models → engine.gpt_client.get_models_cache_meta (calls)
- engine.gpt_client.effective_models_url → engine.gpt_client._catalogue_entry (calls)
- engine.gpt_client.effective_models_url → engine.gpt_client.derive_models_url (calls)
- engine.gpt_client.get_cached_models → engine.gpt_client._read_cache (calls)
- engine.gpt_client.get_gone_models → engine.gpt_client.get_model_health (calls)
- engine.cpml_consent.set_coqui_tos_agreed → CPML (calls)
- обновлён `.github/workflows/ci.yml`
- обновлён `.github/workflows/release.yml`
- обновлён `.gitignore`
- обновлён `CONTRIBUTING.md`
- обновлён `README.md`
- обновлён `THIRD_PARTY_NOTICES.md`
- обновлён `docs/DOCUMENTATION.EN.md`
- обновлён `docs/DOCUMENTATION.RU.md`
- обновлён `docs/PRIVACY.RU.md`
- обновлён `docs/PRIVACY.md`
- обновлён `docs/THREAT_MODEL.md`
- обновлён `docs/workflows/ci.yml`
- обновлён `docs/workflows/release.yml`
- обновлён `engine/batch_window.py`
- обновлён `engine/env_core/diagnostics.py`
- обновлён `engine/gpt_client.py`
- обновлён `engine/gui/batch_window.py`
- обновлён `engine/gui/chat_window/services/settings_api.py`
- обновлён `engine/gui/env_settings.py`
- обновлён `engine/gui/generation.py`
- обновлён `engine/rvc_catalog.py`
- обновлён `engine/tts/__init__.py`
- обновлён `gui.py`
- обновлён `i18n.py`
- обновлён `json/sbom.cdx.json`
- обновлён `requirements.lock`
- обновлён `requirements.txt`
- обновлён `test/run_tests.bat`
- обновлён `test/test_dependency_baseline.py`
- обновлён `test/test_generation.py`
- обновлён `tools/rebuild_release_files.py`

### Исправлено

- Fix CoquiTosNotAgreedError persisting despite COQUI_TOS_AGREED=1 (issue #4)

### Удалено

- AI-провайдеры: проверка доступности всех моделей одним ключом, автоподбор живой модели и удаление гео-примечаний
- удалён `json/cpml_consent.json`

### Безопасность

- обновлён `.security/pip-audit-allowlist.yml`
- обновлён `docs/SECURITY_BASELINE.RU.md`
- обновлён `docs/SECURITY_BASELINE.md`
