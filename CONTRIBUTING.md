# Contributing to XTTS Studio AI

Спасибо за интерес к проекту! Этот документ описывает, как настроить окружение разработки,
прислать изменения и какие правила действуют в репозитории.

## 1. Fork → dev-окружение → тесты

1. Сделайте fork репозитория и клонируйте свою копию.
2. Развёртывание целевой сборки — Windows 10/11 x64 с bundled Python
   (`python\runtime\python.exe`) и portable-окружением `python\xtts_env`.
   Для тестов и линтера отдельный Python 3.11 тоже подходит.
3. Установите dev-инструменты (версии закреплены — см. `.github/workflows/ci.yml`,
   `.pre-commit-config.yaml`):

   ```bash
   pip install ruff==0.6.9 black==24.10.0 pytest pytest-timeout cryptography==50.0.0
   ```
4. Запустите тесты:

   ```bash
   pytest test/
   ```
5. Перед коммитом — pre-commit (`black` + `ruff --fix`).

## 2. Ветки и PR

- `main` — защищённая ветка релизов. Прямые пуш-коммиты запрещены; только через PR.
- Вести работу в ветке `feature/<topic>` или `fix/<topic>` от актуального `main`.
- PR должен пройти CI: `black --check .`, `ruff check .`, `tools/ruff_new_files_gate.py`,
  `tools/pip_audit_gate.py` и полный `pytest test/`.
- Каждый PR — самостоятельная, атомарная единица: одно логическое изменение на PR.

## 3. Code style

- **Black** (line-length 100) + **Ruff** — единый стиль. Конфиг в `pyproject.toml`.
- `ruff check .` должен быть зелёным; базовый набор — `E, F, W`, `F821` включён.
- **Новые файлы** дополнительно проверяются строгим набором `E, F, W, B, SIM, UP`
  (см. `tools/ruff_new_files_gate.py`). Bare except (`E722`) в новом коде запрещён —
  ловите конкретные исключения. Новые файлы нельзя «прятать» в `per-file-ignores`
  без review — CI это блокирует.
- Не включайте `N` (pep8-naming) и `I` (isort): в проекте умышленные локальные
  константы ЗАГЛАВНЫМИ и отложенные импорты.

## 4. PR, меняющий updater / env_core / security → обязан обновить docs в том же PR

Если ваш PR затрагивает update-манифест, `engine/env_core/`, безопасность (CI,
подписание, allowlist, threat model) или поведение, описанное в `docs/DOCUMENTATION.*.md`,
`docs/SECURITY*.md`, `docs/SECURITY_BASELINE*.md` — обновите соответствующую документацию
в **том же** PR. Документация не должна разъезжаться с реальным поведением кода/CI.
При изменении `requirements.txt` — перегенерируйте SBOM (`tools/generate_sbom.py`)
и `THIRD_PARTY_NOTICES.md` (`tools/generate_third_party_notices.py`).

## 5. Политика AI-generated PR

- PR, целиком или в значительной части сгенерированные AI, **принимаются**, но должны:
  - проходить CI наравне с ручными (black/ruff/pytest/security-gate);
  - содержать в описании пометку, что код AI-assisted, и краткое объяснение логики;
  - не добавлять новые файлы в `per-file-ignores` (TASK-009) и не подавлять
    security-finding без per-CVE обоснования в `.security/pip-audit-allowlist.yml`;
- AI-сгенерированный код не освобождает от code review. Мейнтейнер проверяет
  безопасность и совместимость так же строго.

## 6. Как добавить RVC-модель в seed-каталог

Seed-каталог — `json/rvc_catalog_seed.json` (версионируется в git, доступен офлайн).
Каждая запись обязана содержать: `id`, `name`, `url`. Опционально: `filename`,
`author`, `license`, `description`, `page_url`, `sha256`.

1. Убедитесь, что у модели есть **прямая** ссылка на `.pth` или `.zip` (HuggingFace
   `/resolve/` или Google Drive file).
2. Добавьте запись в `json/rvc_catalog_seed.json`, проверьте, что `url` реально скачивается.
3. При наличии — укажите `license` и `author` (честно: каталог не означает разрешения
   на коммерческое использование).
4. Запустите `pytest test/test_rvc_catalog.py` — структура должна остаться валидной.

## 7. Responsible disclosure для security-багов

**Не открывайте** публичный Issue для непатченой уязвимости. Используйте
GitHub Private Vulnerability Reporting: `Security` → `Advisories` → `Report a vulnerability`.
Подробности — в [docs/SECURITY.md](./docs/SECURITY.md). Подтверждение отчёта — в течение 7 дней.

## Ссылки

- Документация: [docs/DOCUMENTATION.RU.md](./docs/DOCUMENTATION.RU.md) · [EN](./docs/DOCUMENTATION.EN.md)
- Безопасность: [docs/SECURITY.md](./docs/SECURITY.md) · [SECURITY_BASELINE.md](./docs/SECURITY_BASELINE.md)
- Лицензии: [LICENSE.md](./LICENSE.md) · [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)
