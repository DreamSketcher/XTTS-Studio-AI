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
import hashlib
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_PATH = os.path.join(BASE_DIR, "version.json")
CHECKSUMS_PATH = os.path.join(BASE_DIR, "checksums.txt")


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, help="Новая версия, например 1.0.11")
    parser.add_argument("--min-app-version", default=None,
                         help="Минимальная версия приложения, с которой поддерживается инкрементальное обновление")
    parser.add_argument("--changelog", default=None, help="Текст changelog (если не указан — берётся текущий из version.json)")
    args = parser.parse_args()

    if not os.path.exists(VERSION_PATH):
        print(f"Не найден {VERSION_PATH}")
        sys.exit(1)

    with open(VERSION_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    files = manifest.get("files", [])
    if not files:
        print("В version.json нет списка files — нечего хэшировать.")
        sys.exit(1)

    sha256_map = {}
    missing = []
    for rel in files:
        full = os.path.join(BASE_DIR, rel.replace("/", os.sep))
        if not os.path.exists(full):
            missing.append(rel)
            continue
        sha256_map[rel] = sha256_of_file(full)
        print(f"  {rel}: {sha256_map[rel]}")

    if missing:
        print("\n[!] Файлы из списка не найдены на диске (пропущены):")
        for m in missing:
            print(f"    - {m}")

    manifest["version"] = args.version
    if args.min_app_version:
        manifest["min_app_version"] = args.min_app_version
    if args.changelog:
        manifest["changelog"] = args.changelog
    manifest["sha256"] = sha256_map

    with open(VERSION_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    with open(CHECKSUMS_PATH, "w", encoding="utf-8") as f:
        f.write(f"XTTS Studio — контрольные суммы SHA256 для версии {args.version}\n")
        f.write("Проверка (Windows PowerShell): certutil -hashfile \"имя_файла\" SHA256\n")
        f.write("Проверка (Linux/macOS): sha256sum имя_файла\n\n")
        for rel, h in sha256_map.items():
            f.write(f"{h}  {rel}\n")

    print(f"\nГотово. version.json обновлён ({len(sha256_map)} файлов), checksums.txt создан.")


if __name__ == "__main__":
    main()