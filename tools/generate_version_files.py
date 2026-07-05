"""
generate_version_files.py

Автоматически формирует поле "files" в version.json на основе того,
какие файлы реально относятся к проекту прямо сейчас — то есть каждый
запуск ПОЛНОСТЬЮ пересобирает список с нуля (а не дополняет старый).
Это значит:
  - новые файлы, которые появились в проекте — добавляются;
  - файлы, которых больше нет (удалены/переименованы/пропали из git) —
    автоматически убираются из списка, без ручной чистки.

ИСТОЧНИК КАНДИДАТОВ:
1. Файлы, уже закоммиченные в git (git ls-files).
2. Файлы, которые ЕЩЁ НЕ закоммичены, но и не игнорируются git'ом
   (git ls-files --others --exclude-standard).

ЧЁРНЫЙ СПИСОК (version_ignore.txt, лежит рядом с этим скриптом):
   Файлы/папки/маски, которые НЕ должны попасть в version.json, даже если
   они видны git'у (документация, сам манифест, dev-инструменты, локальные
   бэкапы и т.п.). Синтаксис как у .gitignore. Редактируется вручную,
   в код лезть не нужно.

ПРИНУДИТЕЛЬНОЕ ВКЛЮЧЕНИЕ (version_force_include.txt, рядом с этим скриптом):
   Файлы, которые ДОЛЖНЫ попасть в version.json, даже если git их не видит
   (обычно собранный .exe — бинарник, обычно сам лежит в .gitignore).

Поля "version" и "changelog" в version.json НЕ трогаются — их по-прежнему
правишь вручную перед релизом. Скрипт перезаписывает только "files".
"""

import fnmatch
import json
import subprocess
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
IGNORE_FILE = TOOLS_DIR / "version_ignore.txt"
FORCE_INCLUDE_FILE = TOOLS_DIR / "version_force_include.txt"


def _load_list_file(path: Path) -> list[str]:
    """Читает текстовый файл со списком, пропуская пустые строки и комментарии (#)."""
    if not path.exists():
        return []
    lines = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _is_ignored(file_path: str, patterns: list[str]) -> bool:
    """
    Проверяет путь против чёрного списка (синтаксис как у .gitignore):
      - "papka/"      -> исключает всю папку целиком (и всё внутри неё)
      - "*.png"       -> маска (fnmatch) по полному пути ИЛИ по имени файла
      - "exact/path"  -> точное совпадение по полному пути или по имени файла
    """
    name = Path(file_path).name
    for pattern in patterns:
        if pattern.endswith("/"):
            prefix = pattern.rstrip("/")
            if file_path == prefix or file_path.startswith(prefix + "/"):
                return True
            continue

        if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(name, pattern):
            return True

    return False


def _run_git(args: list[str], repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def get_repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip())


def get_relevant_files(repo_root: Path) -> list[str]:
    tracked = _run_git(["ls-files"], repo_root)
    untracked_but_not_ignored = _run_git(
        ["ls-files", "--others", "--exclude-standard"], repo_root
    )
    return sorted(set(tracked) | set(untracked_but_not_ignored))


def build_files_list(repo_root: Path) -> list[str]:
    ignore_patterns = _load_list_file(IGNORE_FILE)
    force_include = _load_list_file(FORCE_INCLUDE_FILE)

    candidates = get_relevant_files(repo_root)

    # ВАЖНО: git ls-files показывает то, что записано в индексе git, а не
    # то, что реально лежит на диске. Если файл удалили через проводник, но
    # ещё не сделали "git add -A" / коммит удаления — git всё ещё считает
    # его отслеживаемым. Поэтому дополнительно проверяем реальное наличие
    # файла на диске: если его физически нет — в version.json он не попадёт,
    # независимо от того, что думает git.
    existing_on_disk = [f for f in candidates if (repo_root / f).exists()]

    filtered = [f for f in existing_on_disk if not _is_ignored(f, ignore_patterns)]

    for extra in force_include:
        if extra in filtered:
            continue
        if _is_ignored(extra, ignore_patterns):
            # Если файл одновременно в чёрном и принудительном списке —
            # принудительное включение побеждает, но явно предупреждаем,
            # чтобы не было сюрпризов.
            print(f"[ИНФО] {extra!r} в чёрном списке, но принудительно включён "
                  f"через version_force_include.txt.")
        if (repo_root / extra).exists():
            filtered.append(extra)
        else:
            print(f"[ПРЕДУПРЕЖДЕНИЕ] {extra!r} указан в version_force_include.txt, "
                  f"но не найден на диске — пропущен.")

    return sorted(filtered)


def main():
    repo_root = get_repo_root()
    version_json_path = repo_root / "version.json"

    if version_json_path.exists():
        with open(version_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        print("[ИНФО] version.json не найден — создаю новый со значениями по умолчанию.")
        data = {"version": "0.0.1", "files": [], "changelog": ""}

    old_files = set(data.get("files", []))
    new_files = build_files_list(repo_root)
    new_files_set = set(new_files)

    data["files"] = new_files

    with open(version_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    added = sorted(new_files_set - old_files)
    removed = sorted(old_files - new_files_set)

    print(f"\nСписок полностью пересобран по текущему состоянию проекта.")
    print(f"Файлов в списке: {len(new_files)}")

    if added:
        print("\nДобавлены (новые в проекте):")
        for a in added:
            print(f"  + {a}")

    if removed:
        print("\nУбраны (пропали из проекта/git, либо теперь в чёрном списке):")
        for r in removed:
            print(f"  - {r}")

    if not added and not removed:
        print("Изменений нет — список совпадает с прошлым запуском.")

    print(f"\nТекущая version в файле: {data.get('version')!r}")
    print("Не забудь вручную обновить version и changelog перед публикацией релиза.")


if __name__ == "__main__":
    main()
