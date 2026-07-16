"""Rebuild version.json payload from the current project tree.

Only application/runtime payload is included. Tests, developer tools, GitHub
workflows, user data, models, caches, and self-generated release metadata are
excluded.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "version.json"

ROOT_FILES = {
    ".gitattributes",
    ".pre-commit-config.yaml",
    "DOCUMENTATION.EN.md",
    "DOCUMENTATION.RU.md",
    "PRIVACY.md",
    "SECURITY.md",
    "SECURITY_BASELINE.md",
    "XTTS Studio.exe",
    "XTTS_DIAG.bat",
    "demo_video_storyboard_template.html",
    "generate_version_manifest.py",
    "gui.py",
    "i18n.py",
    "pyproject.toml",
    "requirements.txt",
    "sbom.cdx.json",
    "update_manifest_public.pem",
}
SELF_GENERATED = {"version.json", "version.json.sig", "checksums.txt"}


def git_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def included(relative: str) -> bool:
    path = relative.replace("\\", "/")
    if path in SELF_GENERATED:
        return False
    if path in ROOT_FILES:
        return True
    if path.startswith("engine/") and path.endswith(".py"):
        return True
    if path.startswith("json/") and path.endswith(".json"):
        return True
    return False


def main():
    if not MANIFEST.is_file():
        raise SystemExit(f"Missing {MANIFEST}")
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    old = list(data.get("files", []))
    files = sorted(
        path
        for path in git_paths()
        if included(path) and (ROOT / Path(*path.split("/"))).is_file()
    )
    data["files"] = files
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    added = sorted(set(files) - set(old))
    removed = sorted(set(old) - set(files))
    print("Список полностью пересобран по текущему состоянию проекта.")
    print(f"Файлов в списке: {len(files)}")
    if added:
        print("Добавлены:")
        for path in added:
            print(f"  + {path}")
    if removed:
        print("Убраны:")
        for path in removed:
            print(f"  - {path}")
    if not added and not removed:
        print("Изменений нет — список совпадает с прошлым запуском.")


if __name__ == "__main__":
    main()
