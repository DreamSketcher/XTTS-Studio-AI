"""
Запускать перед каждым релизом из корня проекта (там же, где version.json).

Что делает:
  1. Берёт список "files" из текущего version.json (или из --files-from)
  2. Считает SHA256 каждого файла
  3. Записывает их в version.json -> "sha256"
  4. Дополнительно создаёт checksums.txt — человекочитаемый список хэшей
     для ручной проверки пользователем (без установщика/git)

Использование:
  python generate_version_manifest.py --version 1.0.11 --min-app-version 1.0.0
"""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

# На Windows стандартный вывод по умолчанию в кодировке консоли (cp1251 на
# русских системах, cp1252 на англоязычных). print() с кириллицей падает на
# cp1252 с UnicodeEncodeError (например, в CI на windows-latest). Принудительно
# переключаем stdout/stderr на UTF-8, чтобы скрипт работал на любой локали.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8")
        except Exception:
            pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BUNDLED_SITE_PACKAGES = os.path.join(BASE_DIR, "python", "xtts_env", "Lib", "site-packages")
if os.path.isdir(BUNDLED_SITE_PACKAGES) and BUNDLED_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, BUNDLED_SITE_PACKAGES)

VERSION_PATH = os.path.join(BASE_DIR, "version.json")
CHECKSUMS_PATH = os.path.join(BASE_DIR, "checksums.txt")
SIGNATURE_PATH = os.path.join(BASE_DIR, "version.json.sig")
# These files describe/sign the payload and must never be members of that same
# payload. In particular, including version.json.sig creates an impossible
# self-referential checksum that becomes stale immediately after signing.
SELF_GENERATED_FILES = {"version.json", "version.json.sig", "checksums.txt"}


_TEXT_SUFFIXES = {
    ".py", ".pyi", ".md", ".txt", ".json", ".toml", ".yaml", ".yml",
    ".ini", ".cfg", ".bat", ".cmd", ".ps1", ".html", ".htm", ".css",
    ".js", ".svg",
}
_TEXT_NAMES = {".gitignore", ".gitattributes", ".pre-commit-config.yaml", "requirements.txt"}


def _is_release_text(relative_path: str) -> bool:
    name = str(relative_path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name in _TEXT_NAMES or Path(name).suffix.lower() in _TEXT_SUFFIXES


def sha256_of_file(path: str, relative_path: str = "") -> str:
    data = Path(path).read_bytes()
    if relative_path and _is_release_text(relative_path):
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def _get_previous_files_list() -> list:
    """
    Читает список "files" из version.json, каким он был в предыдущем коммите
    (git HEAD), т.е. ДО того как generate_version_files.py перезаписал его
    новым списком для текущего релиза. Нужно, чтобы понять, какие файлы
    пропали в этом релизе (переименованы/перенесены/объединены).

    Если git недоступен или это первый коммит — возвращает пустой список
    (это безопасно: просто не найдём "потерянных" файлов на этот раз).
    """
    try:
        result = subprocess.run(
            ["git", "show", "HEAD:version.json"],
            cwd=BASE_DIR,
            capture_output=True,
            timeout=15,
        )
        if result.returncode != 0:
            return []
        # version.json — UTF-8 (там кириллица в changelog). Декодируем явно,
        # а не полагаемся на text=True: на Windows subprocess по умолчанию
        # берёт кодировку консоли (обычно cp1251), которая падает на
        # кириллических байтах и роняет фоновый поток _readerthread.
        old_manifest = json.loads(result.stdout.decode("utf-8"))
        return old_manifest.get("files", [])
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Новая версия, например 1.0.11")
    parser.add_argument(
        "--min-app-version",
        default=None,
        help="Минимальная версия приложения, с которой поддерживается инкрементальное обновление",
    )
    parser.add_argument(
        "--changelog",
        default=None,
        help="Текст changelog (если не указан — берётся текущий из version.json)",
    )
    parser.add_argument(
        "--signing-key",
        default=os.environ.get("XTTS_UPDATE_SIGNING_KEY"),
        help="Ed25519 private key. Также читается из XTTS_UPDATE_SIGNING_KEY.",
    )
    args = parser.parse_args()

    if not os.path.exists(VERSION_PATH):
        print(f"Не найден {VERSION_PATH}")
        sys.exit(1)
    if os.path.exists(SIGNATURE_PATH) and not args.signing_key:
        print(
            "[!] version.json.sig существует: изменение manifest без новой подписи запрещено. "
            "Передайте --signing-key или XTTS_UPDATE_SIGNING_KEY."
        )
        sys.exit(2)

    with open(VERSION_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    files = manifest.get("files", [])
    if not files:
        print("В version.json нет списка files — нечего хэшировать.")
        sys.exit(1)
    excluded_generated = [path for path in files if path in SELF_GENERATED_FILES]
    files = [path for path in files if path not in SELF_GENERATED_FILES]
    manifest["files"] = files
    if excluded_generated:
        print(
            "[i] Исключены self-generated release-файлы: " + ", ".join(sorted(excluded_generated))
        )

    sha256_map = {}
    missing = []
    for rel in files:
        full = os.path.join(BASE_DIR, rel.replace("/", os.sep))
        if not os.path.exists(full):
            missing.append(rel)
            continue
        sha256_map[rel] = sha256_of_file(full, rel)
        print(f"  {rel}: {sha256_map[rel]}")

    if missing:
        print("\n[!] Файлы из списка не найдены на диске (пропущены):")
        for m in missing:
            print(f"    - {m}")

    # ── Устаревшие файлы (removed_files) ────────────────────────────────
    # Клиент качает только САМЫЙ ПОСЛЕДНИЙ version.json и обновляется сразу
    # до актуальной версии, минуя промежуточные релизы. Поэтому список
    # "что удалить" должен быть НАКОПИТЕЛЬНЫМ — иначе, например, файл,
    # убранный в 1.0.50, никогда не будет удалён у пользователя, который
    # обновляется прямо с 1.0.40 на 1.0.60 (там сравнивался бы только
    # предыдущий коммит, 1.0.59 -> 1.0.60).
    existing_removed = set(manifest.get("removed_files", []))
    old_files = set(_get_previous_files_list())
    new_files_set = set(files)
    newly_removed = old_files - new_files_set
    # Если файл когда-то был помечен как удалённый, а потом снова появился
    # в проекте — убираем его из списка "на удаление" (самоисправление).
    removed_files = sorted(
        ((existing_removed | newly_removed) - new_files_set) - SELF_GENERATED_FILES
    )

    if newly_removed:
        print("\n[i] Новые файлы, пропавшие из списка (будут удалены у клиентов при обновлении):")
        for r in sorted(newly_removed):
            print(f"    - {r}")

    manifest["removed_files"] = removed_files

    manifest["version"] = args.version
    if args.min_app_version:
        manifest["min_app_version"] = args.min_app_version
    if args.changelog:
        manifest["changelog"] = args.changelog
    manifest["sha256"] = sha256_map

    with open(VERSION_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if args.signing_key:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from engine.update_signing import canonical_manifest_bytes

        with open(args.signing_key, "rb") as key_file:
            key = serialization.load_pem_private_key(key_file.read(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise TypeError("update signing key must be Ed25519")
        with open(VERSION_PATH, "rb") as manifest_file:
            signature = key.sign(canonical_manifest_bytes(manifest_file.read()))
        with open(SIGNATURE_PATH, "wb") as signature_file:
            signature_file.write(base64.b64encode(signature) + b"\n")
        print("  version.json.sig: Ed25519 подпись обновлена")

    with open(CHECKSUMS_PATH, "w", encoding="utf-8") as f:
        f.write(f"XTTS Studio — контрольные суммы SHA256 для версии {args.version}\n")
        f.write('Проверка (Windows PowerShell): certutil -hashfile "имя_файла" SHA256\n')
        f.write("Проверка (Linux/macOS): sha256sum имя_файла\n\n")
        for rel, h in sha256_map.items():
            f.write(f"{h}  {rel}\n")

    print(f"\nГотово. version.json обновлён ({len(sha256_map)} файлов), checksums.txt создан.")
    if removed_files:
        print(f"К удалению у клиентов при следующем обновлении: {len(removed_files)} файл(ов).")


if __name__ == "__main__":
    main()
