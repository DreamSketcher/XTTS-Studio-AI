#!/usr/bin/env python3
"""
git_update.py — Менеджер Git для XTTS Studio.
Разместите в папке tools/ и запускайте через git_update.bat.

Безопасный рабочий процесс: stash локальных изменений → pull/rebase → restore →
generate+sign+verify → один атомарный commit → final pull/rebase → push.
Release metadata никогда не отправляется при ошибке подписи или SHA256.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENERATE_FILES_SCRIPT = PROJECT_ROOT / "tools" / "rebuild_release_files.py"
GENERATE_MANIFEST_SCRIPT = PROJECT_ROOT / "generate_version_manifest.py"
VERSION_JSON_PATH = PROJECT_ROOT / "json" / "version.json"
SIGNATURE_PATH = PROJECT_ROOT / "json" / "version.json.sig"
DEFAULT_SIGNING_KEY = PROJECT_ROOT / "keys" / "XTTS-Studio-signing-private.pem"
FALLBACK_SIGNING_KEY = Path(r"C:\XTTS Signing Keys\XTTS-Studio-signing-private.pem")
REGENERATED_RELEASE_FILES = {
    "version.json",
    "version.json.sig",
    "json/version.json",
    "json/version.json.sig",
    "checksums.txt",
}
BUNDLED_SITE_PACKAGES = PROJECT_ROOT / "python" / "xtts_env" / "Lib" / "site-packages"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if BUNDLED_SITE_PACKAGES.is_dir() and str(BUNDLED_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(BUNDLED_SITE_PACKAGES))


def get_signing_key() -> Path | None:
    configured = os.environ.get("XTTS_UPDATE_SIGNING_KEY", "").strip()
    if configured:
        p = Path(configured)
        if p.is_file():
            return p
    if DEFAULT_SIGNING_KEY.is_file():
        return DEFAULT_SIGNING_KEY
    if FALLBACK_SIGNING_KEY.is_file():
        return FALLBACK_SIGNING_KEY
    return None


def run_python_script(script_path: Path, args: list) -> int:
    """Запускает Python-скрипт с тем же интерпретатором, в котором работает текущий скрипт."""
    r = subprocess.run(
        [sys.executable, str(script_path)] + args,
        cwd=str(PROJECT_ROOT),
    )
    return r.returncode


def _read_current_changelog() -> str:
    if not VERSION_JSON_PATH.exists():
        return ""
    try:
        with open(VERSION_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("changelog", "")
    except Exception:
        return ""


def _prompt_changelog(current: str) -> str:
    print("\n  Текущий список изменений (changelog):")
    if current:
        for line in current.split("\n"):
            print(f"    {line}")
    else:
        print("    (пусто)")

    choice = (
        input(
            "\n  Написать новый список изменений для этого релиза? (y/n, Enter=оставить текущий): "
        )
        .strip()
        .lower()
    )
    if choice not in ("y", "д", "yes", "да"):
        return current

    print("  Вводите строки изменений по одной. Пустая строка для завершения:")
    lines = []
    while True:
        line = input("    ").strip()
        if not line:
            break
        lines.append(line if line.startswith("-") else f"- {line}")

    if not lines:
        print("  Строки не введены — оставляем текущий список изменений.")
        return current

    return "\n".join(lines)


def update_version_manifest():
    """
    Пересобирает список файлов в version.json, предлагает обновить changelog
    и генерирует контрольные суммы SHA256 для текущего релиза.

    Возвращает:
      - строку версии при успешном обновлении
      - "SKIP", если пользователь решил не оформлять этот коммит как релиз
        (например, при отправке тестовых или вспомогательных файлов)
      - None при ошибке (отсутствие скриптов, пустая версия, ошибка генерации)
    """
    do_release = (
        input(
            "\n  Обновить версию и пересчитать SHA256 контрольные суммы для этого коммита? (y/n, Enter=y): "
        )
        .strip()
        .lower()
    )
    if do_release in ("n", "н", "no", "нет"):
        print(
            "  Пропуск обновления версии/SHA256 — эти изменения не будут отмечены как новый релиз."
        )
        return "SKIP"

    signing_key = get_signing_key()
    if signing_key is None:
        print("  [ОШИБКА] Не найден приватный Ed25519 signing key.")
        print(f"            Ожидаемый путь: {DEFAULT_SIGNING_KEY}")
        print("            Либо задайте XTTS_UPDATE_SIGNING_KEY.")
        print("  Release manifest не будет изменён.")
        return None

    # Collect all release input before touching version.json.
    version = input("  Версия для этого релиза (например, 1.1.56): ").strip()
    if not version:
        print("  [ОШИБКА] Необходимо указать версию. Файлы не изменялись.")
        return None
    min_app_version = input(
        "  Минимальная версия приложения для инкрементального обновления (Enter чтобы пропустить): "
    ).strip()
    changelog = _prompt_changelog(_read_current_changelog())

    if not GENERATE_FILES_SCRIPT.exists():
        print(f"  [ОШИБКА] Файл {GENERATE_FILES_SCRIPT} не найден.")
        return None

    print("  Обновление списка файлов...")
    if run_python_script(GENERATE_FILES_SCRIPT, []) != 0:
        print("  [ОШИБКА] Сбой выполнения rebuild_release_files.py.")
        return None

    if not GENERATE_MANIFEST_SCRIPT.exists():
        print(f"  [ОШИБКА] Файл {GENERATE_MANIFEST_SCRIPT} не найден.")
        return None

    args = [
        "--version",
        version,
        "--changelog",
        changelog,
        "--signing-key",
        str(signing_key),
    ]
    if min_app_version:
        args += ["--min-app-version", min_app_version]

    print(f"  Генерация SHA256 контрольных сумм для версии {version}...")
    if run_python_script(GENERATE_MANIFEST_SCRIPT, args) != 0:
        print("  [ОШИБКА] Сбой выполнения generate_version_manifest.py.")
        return None

    print("  [OK] version.json, version.json.sig и checksums.txt успешно обновлены.")
    return version


def git(*args: str) -> subprocess.CompletedProcess:
    """Выполняет команду git из корневой папки проекта и возвращает CompletedProcess."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def git_show(*args: str) -> subprocess.CompletedProcess:
    """Выполняет команду git с выводом напрямую в консоль (для push, reset, rebase --abort и т.д.)."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(PROJECT_ROOT),
        timeout=120,
    )


def auto_resolve_structure_conflicts(verbose: bool = True) -> bool:
    """
    Таблетка для автоматического разрешения конфликтов структуры
    (перенос файлов из корня в json/ и docs/).
    Принудительно берет локальные изменённые файлы (--theirs), удаляет
    устаревшие дубликаты из корня, индексирует новые пути и чистит stash.
    """
    if verbose:
        print("\n  [Таблетка] Разрешаем конфликты структуры (перенос в json/)...")

    # 1. Принимаем локальную/новую версию с новой структурой
    git("checkout", "--theirs", ".")

    # 2. Окончательно вычищаем устаревшие дубликаты из корня
    legacy_root_files = [
        "version.json",
        "version.json.sig",
        "settings.json",
        "theme_settings.json",
        "sbom.cdx.json",
        "PRIVACY.md",
        "SECURITY.md",
        "SECURITY_BASELINE.md",
    ]
    for rel in legacy_root_files:
        p = PROJECT_ROOT / rel
        if p.is_file():
            try:
                git("rm", "-f", rel)
            except Exception:
                pass
            if p.is_file():
                try:
                    p.unlink()
                except Exception:
                    pass

    # 3. Добавляем всю новую структуру в индекс
    git("add", "-A")

    # 4. Сбрасываем застрявший stash при наличии
    stashes = git("stash", "list")
    if "xtts-manager-presync-" in (stashes.stdout or ""):
        git("stash", "drop")

    if verbose:
        print(
            "  [Таблетка] [OK] Конфликты разрешены: новая структура json/ принята, старый корень очищен."
        )
    return True


def cleanup_stuck_rebase(verbose: bool = True) -> bool:
    """
    Таблетка от зависших состояний Git rebase / merge / cherry-pick / stash pop.
    Проверяет наличие папок .git/rebase-merge, .git/rebase-apply, REBASE_HEAD и т.д.
    Если они есть, пытается штатно отменить процесс через git rebase --abort / git merge --abort,
    а также гарантированно очищает блокирующие папки на диске и автоматически разрешает
    структурные конфликты переноса файлов в json/.
    Возвращает True, если было зависшее состояние и оно очищено.
    """
    rebase_merge = PROJECT_ROOT / ".git" / "rebase-merge"
    rebase_apply = PROJECT_ROOT / ".git" / "rebase-apply"
    rebase_head = PROJECT_ROOT / ".git" / "REBASE_HEAD"
    merge_head = PROJECT_ROOT / ".git" / "MERGE_HEAD"

    status_r = git("status", "--porcelain")
    status_out = (status_r.stdout or "").lower()
    has_unmerged = "unmerged" in status_out or any(
        m in status_out for m in ("uu ", "aa ", "ud ", "du ", "both modified")
    )

    has_stuck = (
        rebase_merge.exists()
        or rebase_apply.exists()
        or rebase_head.exists()
        or merge_head.exists()
        or has_unmerged
    )
    if not has_stuck:
        r = subprocess.run(["git", "status"], cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        combined = (r.stdout or "").lower() + (r.stderr or "").lower()
        if (
            "rebase in progress" in combined
            or "merge in progress" in combined
            or "rebase-merge" in combined
        ):
            has_stuck = True

    if not has_stuck:
        return False

    if verbose:
        print(
            "\n  [Таблетка] Обнаружено незавершённое/зависшее состояние Git или конфликт структуры."
        )
        print("  [Таблетка] Автоматически отменяем зависший процесс и разрешаем конфликты...")

    # 1. Попытка штатно отменить через Git
    subprocess.run(
        ["git", "rebase", "--abort"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "merge", "--abort"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "cherry-pick", "--abort"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    # 2. Если остались unmerged paths — автоматически разрешаем в пользу json/ структуры
    if has_unmerged:
        auto_resolve_structure_conflicts(verbose=verbose)

    # 3. Гарантированное удаление директорий/файлов, если Git сам их не удалил
    if rebase_merge.exists():
        shutil.rmtree(rebase_merge, ignore_errors=True)
    if rebase_apply.exists():
        shutil.rmtree(rebase_apply, ignore_errors=True)
    if rebase_head.exists():
        rebase_head.unlink(missing_ok=True)
    if merge_head.exists():
        merge_head.unlink(missing_ok=True)

    if verbose:
        print("  [Таблетка] [OK] Зависшее состояние очищено, репозиторий готов к работе.")
    return True


_NETWORK_ERROR_MARKERS = (
    "could not resolve host",
    "could not read from remote repository",
    "connection timed out",
    "unable to access",
    "failed to connect",
    "network is unreachable",
    "ssl_error",
    "the remote end hung up unexpectedly",
    "empty reply from server",
)

_STUCK_REBASE_MARKERS = (
    "already a rebase-merge directory",
    "middle of another rebase",
    "rebase-apply",
    "it seems that there is already a rebase",
    "cannot rebase: you have unstaged changes",
    "cannot pull with rebase: you have unstaged changes",
)


def git_pull_rebase(branch: str) -> tuple:
    """
    Как git_show, но перехватывает вывод pull --rebase, чтобы отличить
    временный сбой сети/DNS или зависшую блокирующую папку rebase-merge
    от настоящего конфликта содержимого.

    Возвращает (CompletedProcess, is_network_error: bool, is_stuck_rebase: bool).
    """
    r = subprocess.run(
        ["git", "pull", "--rebase", "--no-edit", "origin", branch],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.stdout:
        print(r.stdout, end="")
    if r.stderr:
        print(r.stderr, end="")

    combined = ((r.stdout or "") + (r.stderr or "")).lower()
    is_network_error = any(marker in combined for marker in _NETWORK_ERROR_MARKERS)
    is_stuck_rebase = any(marker in combined for marker in _STUCK_REBASE_MARKERS) or (
        r.returncode != 0
        and (
            (PROJECT_ROOT / ".git" / "rebase-merge").exists()
            or (PROJECT_ROOT / ".git" / "rebase-apply").exists()
        )
        and "conflict" not in combined
    )

    # Таблетка: если ошибка вызвана именно старой/зависшей папкой .git/rebase-merge — сразу лечим и повторяем pull
    if r.returncode != 0 and is_stuck_rebase and not is_network_error:
        print("\n[Таблетка] Запущена автоочистка блокирующей папки .git/rebase-merge...")
        cleanup_stuck_rebase(verbose=False)
        print("           Повторная попытка pull --rebase после очистки...")
        r = subprocess.run(
            ["git", "pull", "--rebase", "--no-edit", "origin", branch],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.stdout:
            print(r.stdout, end="")
        if r.stderr:
            print(r.stderr, end="")
        combined = ((r.stdout or "") + (r.stderr or "")).lower()
        is_network_error = any(marker in combined for marker in _NETWORK_ERROR_MARKERS)
        is_stuck_rebase = any(marker in combined for marker in _STUCK_REBASE_MARKERS)

    return r, is_network_error, is_stuck_rebase


def check_git() -> bool:
    r = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    if r.returncode != 0:
        print("[ОШИБКА] Git не найден. Установите Git и добавьте его в системный PATH.")
        return False
    if not (PROJECT_ROOT / ".git").exists():
        print(f"[ОШИБКА] Папка {PROJECT_ROOT} не является репозиторием Git.")
        return False
    return True


def get_branch() -> str:
    r = git("rev-parse", "--abbrev-ref", "HEAD")
    return r.stdout.strip() or "main"


def has_staged() -> bool:
    r = git("diff", "--cached", "--quiet")
    return r.returncode != 0


def _working_tree_dirty() -> bool:
    return bool(git("status", "--porcelain").stdout.strip())


def _git_tree_matches_worktree(tree_ref: str) -> bool:
    """Compare every blob in a Git tree with the current worktree; extra HEAD files are allowed."""
    listed = git("ls-tree", "-r", "--name-only", tree_ref)
    if listed.returncode != 0:
        return False
    for relative in listed.stdout.splitlines():
        relative = relative.strip()
        if not relative:
            continue
        current = PROJECT_ROOT / Path(*relative.split("/"))
        if not current.is_file():
            return False
        blob = subprocess.run(
            ["git", "show", f"{tree_ref}:{relative}"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=60,
        )
        if blob.returncode != 0 or blob.stdout != current.read_bytes():
            return False
    return True


def _git_tree_matches_head(tree_ref: str) -> bool:
    """Compare every blob in a tree with the corresponding blob in HEAD."""
    listed = git("ls-tree", "-r", "--name-only", tree_ref)
    if listed.returncode != 0:
        return False
    for relative in listed.stdout.splitlines():
        relative = relative.strip()
        if not relative or relative.replace("\\", "/") in REGENERATED_RELEASE_FILES:
            continue
        tree_blob = subprocess.run(
            ["git", "show", f"{tree_ref}:{relative}"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=60,
        )
        head_blob = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=60,
        )
        if (
            tree_blob.returncode != 0
            or head_blob.returncode != 0
            or tree_blob.stdout != head_blob.stdout
        ):
            return False
    return True


def _stash_matches_current_tree(stash_ref: str = "stash@{0}") -> bool:
    """Compare tracked stash tree and its optional untracked third parent with worktree."""
    if not _git_tree_matches_worktree(stash_ref):
        return False
    third_parent = git("rev-parse", "--verify", f"{stash_ref}^3")
    if third_parent.returncode != 0:
        return True
    return _git_tree_matches_worktree(f"{stash_ref}^3")


def _stash_matches_head(stash_ref: str = "stash@{0}") -> bool:
    """Compare old manager stash with remote-synchronized HEAD, ignoring new worktree edits."""
    if not _git_tree_matches_head(stash_ref):
        return False
    third_parent = git("rev-parse", "--verify", f"{stash_ref}^3")
    if third_parent.returncode != 0:
        return True
    return _git_tree_matches_head(f"{stash_ref}^3")


def sync_remote_before_build(branch: str) -> bool:
    """Sync remote before generating release files, preserving local work."""
    # Recover all consecutive stashes left by previous manager runs.
    while True:
        existing = git("stash", "list", "-1", "--format=%gd%x09%s")
        if "xtts-manager-presync-" not in (existing.stdout or ""):
            break
        if _stash_matches_head("stash@{0}"):
            print("\n[PRE-SYNC] Старый manager stash уже полностью содержится в HEAD; удаляем его.")
            dropped = git("stash", "drop", "stash@{0}")
            if dropped.returncode != 0:
                print(f"  [ОШИБКА] Не удалось удалить stash: {dropped.stderr}")
                return False
            continue
        print("\n[БЛОКИРОВКА] Найден manager stash с изменениями, которых нет в HEAD.")
        print("  Stash сохранён. Сравните его с HEAD перед продолжением.")
        return False

    stash_created = False
    if _working_tree_dirty():
        label = f"xtts-manager-presync-{int(time.time())}"
        print("\n[PRE-SYNC] Временно сохраняем локальные изменения (включая untracked)...")
        result = git("stash", "push", "--include-untracked", "-m", label)
        if result.returncode != 0:
            print(f"  [ОШИБКА] Не удалось создать stash:\n{result.stderr or result.stdout}")
            return False
        stash_created = "No local changes" not in (result.stdout or "")

    print("\n[PRE-SYNC] Получение remote до генерации manifest...")
    pull, network_error, stuck = git_pull_rebase(branch)
    if pull.returncode != 0:
        # Never leave the manager in a half-rebased state.
        subprocess.run(
            ["git", "rebase", "--abort"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        if stash_created:
            git_show("stash", "pop")
        if network_error:
            print("  [ОШИБКА] GitHub недоступен. Локальные изменения восстановлены.")
        elif stuck:
            print("  [ОШИБКА] Незавершённый rebase. Используйте пункт [4].")
        else:
            print("  [ОШИБКА] Не удалось синхронизировать remote до сборки релиза.")
        return False

    if stash_created:
        if _stash_matches_current_tree("stash@{0}"):
            print("[PRE-SYNC] Remote уже содержит идентичные локальные изменения.")
            print("           Удаляем дублирующий stash без повторного checkout файлов.")
            dropped = git("stash", "drop", "stash@{0}")
            if dropped.returncode != 0:
                print(f"  [ОШИБКА] Не удалось удалить дублирующий stash: {dropped.stderr}")
                return False
        else:
            print("[PRE-SYNC] Возвращаем локальные изменения...")
            restored = git_show("stash", "pop")
            if restored.returncode != 0:
                print("  [ОШИБКА] Конфликт при восстановлении stash.")
                print("  [Таблетка] Автоматически разрешаем конфликт структуры (корень → json/)...")
                auto_resolve_structure_conflicts(verbose=True)
    return True


def verify_release_state() -> bool:
    """Fail closed unless signature and every payload SHA-256 are valid."""
    try:
        from engine.release_hashing import release_sha256_file
        from engine.update_signing import verify_manifest_signature

        manifest_bytes = VERSION_JSON_PATH.read_bytes()
        verify_manifest_signature(manifest_bytes, SIGNATURE_PATH.read_bytes())
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        files = manifest.get("files", [])
        hashes = manifest.get("sha256", {})
        forbidden = {
            "version.json",
            "version.json.sig",
            "json/version.json",
            "json/version.json.sig",
            "checksums.txt",
        }
        overlap = forbidden.intersection(files)
        if overlap:
            raise RuntimeError(f"self-generated files попали в payload: {sorted(overlap)}")
        if len(files) != len(hashes):
            raise RuntimeError(f"files={len(files)}, sha256={len(hashes)}")
        for relative in files:
            path = PROJECT_ROOT / Path(*relative.split("/"))
            if not path.is_file():
                raise RuntimeError(f"payload file отсутствует: {relative}")
            digest = release_sha256_file(path, relative)
            if digest.lower() != str(hashes.get(relative, "")).lower():
                raise RuntimeError(f"SHA256 mismatch: {relative}")
        print("  [OK] Ed25519 signature и все payload SHA256 проверены.")
        return True
    except Exception as exc:
        print(f"  [ОШИБКА] Release verification failed: {exc}")
        return False


# ----------------------------------------------------------------
#  ОБНОВЛЕНИЕ  (pre-sync → generate/sign → one commit → verify → push)
# ----------------------------------------------------------------


def do_update() -> None:
    branch = get_branch()
    print("\n" + "=" * 50)
    print("  ОБНОВЛЕНИЕ (UPDATE)")
    print("=" * 50)

    cleanup_stuck_rebase(verbose=True)

    # Remote must be integrated before generated release files exist.
    if not sync_remote_before_build(branch):
        input("\nНажмите Enter для продолжения...")
        return

    print("\nТекущие локальные изменения после синхронизации:")
    status = git("status", "--short")
    print(status.stdout if status.stdout.strip() else "  (нет изменений)")
    confirm = input("\nПродолжить? (y/n, Enter=y): ").strip().lower()
    if confirm in ("n", "н", "no", "нет"):
        return

    print("\n[1/5] Подготовка release manifest (опционально)...")
    version = update_version_manifest()
    if version is None:
        print("\n[БЛОКИРОВКА] Manifest/signature не созданы. Push запрещён.")
        input("\nНажмите Enter для продолжения...")
        return
    is_release = version != "SKIP"

    if is_release:
        print("\n[2/5] Проверка Ed25519 и SHA256 до коммита...")
        if not verify_release_state():
            print("\n[БЛОКИРОВКА] Невалидный release не будет закоммичен или отправлен.")
            input("\nНажмите Enter для продолжения...")
            return
    else:
        print("\n[2/5] Non-release push: manifest намеренно не изменялся.")

    print("\n[3/5] Один атомарный коммит исходников и release-файлов...")
    add_result = git_show("add", "-A")
    if add_result.returncode != 0:
        print("  [ОШИБКА] git add завершился ошибкой.")
        input("\nНажмите Enter для продолжения...")
        return

    if has_staged():
        default_message = f"Release {version}" if is_release else "Update"
        message = input(f"  Сообщение коммита (Enter={default_message}): ").strip()
        message = message or default_message
        committed = git("commit", "-m", message)
        if committed.returncode != 0:
            print(
                f"  [ОШИБКА] Не удалось выполнить коммит:\n{committed.stderr or committed.stdout}"
            )
            input("\nНажмите Enter для продолжения...")
            return
        print(f"  [OK] Сохранено: {message}")
    else:
        print("  Нет новых файлов для коммита; будут отправлены существующие локальные коммиты.")

    # Close the small race between pre-sync and push. At this point the working
    # tree is clean, so a final rebase cannot mix uncommitted generated files.
    print("\n[4/5] Финальная проверка remote перед push...")
    pull, network_error, stuck = git_pull_rebase(branch)
    if pull.returncode != 0:
        subprocess.run(
            ["git", "rebase", "--abort"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        if network_error:
            print("  [ОШИБКА] GitHub недоступен. Коммит сохранён локально; push не выполнялся.")
        elif stuck:
            print("  [ОШИБКА] Git заблокирован незавершённым rebase.")
        else:
            print("  [ОШИБКА] Remote изменился и возник конфликт. Rebase отменён, push запрещён.")
        input("\nНажмите Enter для продолжения...")
        return

    if is_release:
        # Rebase may rewrite commits but must not alter checked-out payload.
        if not verify_release_state():
            print("  [БЛОКИРОВКА] После final rebase release verification не прошла.")
            input("\nНажмите Enter для продолжения...")
            return

    print("\n[5/5] Отправка изменений на GitHub...")
    pushed = git_show("push", "origin", branch)
    if pushed.returncode != 0:
        print("  [ОШИБКА] Push не выполнен. Проверяйте сеть и права доступа.")
        input("\nНажмите Enter для продолжения...")
        return

    print("\n" + "=" * 50)
    print(
        "  ГОТОВО! Release проверен и отправлен."
        if is_release
        else "  ГОТОВО! Изменения отправлены."
    )
    print("=" * 50)
    input("\nНажмите Enter для продолжения...")


# ----------------------------------------------------------------
#  ОТКАТ  (Rollback)
# ----------------------------------------------------------------


def do_rollback() -> None:
    print()
    print("=" * 50)
    print("  ОТКАТ К ПРЕДЫДУЩИМ КОММИТАМ (ROLLBACK)")
    print("=" * 50)

    r = git("log", "--oneline", "-10")
    print("\n" + (r.stdout if r.stdout.strip() else "(нет коммитов)"))

    print("\n" + "-" * 40)
    print("  [1] Мягкий сброс (Soft reset)   — отменить коммит, оставить файлы в индексе (staged)")
    print("  [2] Смешанный сброс (Mixed reset) — отменить коммит, убрать из индекса (по умолчанию)")
    print("  [3] Жёсткий сброс (Hard reset)    — НАВСЕГДА УДАЛИТЬ изменения в файлах !!!")
    print("  [0] Отмена")

    choice = input("\nВыберите режим (1/2/3, Enter=2): ").strip() or "2"
    if choice == "0":
        return

    flags = {"1": "--soft", "2": "--mixed", "3": "--hard"}
    flag = flags.get(choice)
    if not flag:
        print("Неверный выбор.")
        input("Нажмите Enter для продолжения...")
        return

    if choice == "3":
        print(
            "\n[!] ВНИМАНИЕ: ЖЁСТКИЙ СБРОС (HARD RESET) — незакоммиченные изменения в файлах БУДУТ БЕЗВОЗВРАТНО УДАЛЕНЫ!"
        )

    commit = input("\nВведите хеш коммита, к которому нужно откатиться: ").strip()
    if not commit:
        return

    print("\nБудут отменены следующие коммиты:")
    r = git("log", "--oneline", f"{commit}..HEAD")
    print(r.stdout if r.stdout.strip() else "  (нет)")

    c = input("\nВведите 'yes' (или 'да') для подтверждения: ").strip().lower()
    if c not in ("yes", "y", "да", "д"):
        print("Отменено.")
        input("Нажмите Enter для продолжения...")
        return

    print(f"\nВыполняется откат к коммиту {commit}...")
    r = git_show("reset", flag, commit)
    if r.returncode != 0:
        print("\n[ОШИБКА] Не удалось выполнить сброс.")
    else:
        print("\n[OK] Откат успешно выполнен.")
        print(
            f"Для принудительной отправки на сервер используйте команду:\n  git push --force-with-lease origin {get_branch()}"
        )

    input("\nНажмите Enter для продолжения...")


# ----------------------------------------------------------------
#  УДАЛЕНИЕ ИГНОРИРУЕМЫХ ФАЙЛОВ ИЗ ОТСЛЕЖИВАНИЯ  (Untrack)
# ----------------------------------------------------------------


def do_untrack_ignored() -> None:
    print()
    print("=" * 50)
    print("  УДАЛЕНИЕ ИГНОРИРУЕМЫХ ФАЙЛОВ ИЗ GIT (UNTRACK)")
    print("=" * 50)
    print("\nУдаляет файлы, подпадающие под .gitignore, из отслеживания Git.")
    print("Сами файлы ОСТАЮТСЯ на вашем диске — очищается только индекс Git.")
    print("\nШаги: git rm -r --cached . -> git add -A -> проверка -> коммит")

    confirm = input("\nПродолжить? (y/n, Enter=y): ").strip().lower()
    if confirm in ("n", "н", "no", "нет"):
        return

    print("\n[1/3] Удаление всех файлов из индекса Git (файлы на диске не затрагиваются)...")
    r = subprocess.run(
        ["git", "rm", "-r", "--cached", "-q", "."],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if r.returncode != 0:
        print(f"  [ОШИБКА] {r.stderr}")
        input("\nНажмите Enter для продолжения...")
        return
    print("  [OK] Индекс Git очищен.")

    print("\n[2/3] Повторное добавление файлов в индекс (с учётом правил .gitignore)...")
    r = git("add", "-A")
    if r.returncode != 0:
        print(f"  [ОШИБКА] {r.stderr}")
        input("\nНажмите Enter для продолжения...")
        return
    print("  [OK] Файлы добавлены обратно (кроме игнорируемых).")

    print("\n[3/3] Список изменений, подготовленных к коммиту:")
    r = git("status", "--short")
    if not r.stdout.strip():
        print("  (ничего не изменилось — индекс уже точно соответствовал .gitignore)")
        input("\nНажмите Enter для продолжения...")
        return
    print(r.stdout)

    print("\nОжидаются только строки с буквой 'D' (удалено из индекса) для путей из .gitignore.")
    print(
        "Если в списке появились неожиданные файлы, исправьте .gitignore и запустите эту операцию снова"
    )
    print("перед коммитом (пока ничего не было сохранено в историю Git).")

    confirm2 = (
        input("\nСоздать коммит с этими изменениями сейчас? (y/n, Enter=y): ").strip().lower()
    )
    if confirm2 in ("n", "н", "no", "нет"):
        print(
            "Изменения оставлены в индексе (staged), но не закоммичены. Можете запустить снова или закоммитить вручную."
        )
        input("\nНажмите Enter для продолжения...")
        return

    msg = (
        input(
            "  Сообщение коммита (Enter=Удаление игнорируемых файлов из отслеживания Git): "
        ).strip()
        or "Удаление игнорируемых файлов из отслеживания Git"
    )
    r = git("commit", "-m", msg)
    if r.returncode != 0:
        print(f"  [ОШИБКА] Не удалось выполнить коммит:\n{r.stderr}")
        input("\nНажмите Enter для продолжения...")
        return
    print(f"  [OK] Сохранено: {msg}")

    push = (
        input("\nОтправить (push) эти изменения на удалённый сервер сейчас? (y/n, Enter=y): ")
        .strip()
        .lower()
    )
    if push not in ("n", "н", "no", "нет"):
        branch = get_branch()
        print("\nОтправка на удалённый сервер...")
        r = git_show("push", "origin", branch)
        if r.returncode != 0:
            print("\n[ОШИБКА] Не удалось отправить (push). Проверьте доступ к сети.")
        else:
            print("\n[OK] Изменения успешно отправлены.")

    input("\nНажмите Enter для продолжения...")


# ----------------------------------------------------------------
#  ГЛАВНОЕ МЕНЮ
# ----------------------------------------------------------------


def do_status_check() -> None:
    """Read-only health/status report for Git and signed release metadata."""
    branch = get_branch()
    print("\n" + "=" * 58)
    print("  ТЕКУЩИЙ СТАТУС ПРОЕКТА / RELEASE HEALTH")
    print("=" * 58)

    status = git("-c", "core.quotepath=false", "status", "--short")
    print("\n[Рабочая директория]")
    if status.stdout.strip():
        print(status.stdout.rstrip())
    else:
        print("  [OK] Чистая")

    git_dir = PROJECT_ROOT / ".git"
    in_progress = [
        name
        for name in (
            "rebase-merge",
            "rebase-apply",
            "MERGE_HEAD",
            "REBASE_HEAD",
            "CHERRY_PICK_HEAD",
        )
        if (git_dir / name).exists()
    ]
    print("\n[Git operation]")
    print(
        f"  [!] Незавершённое состояние: {', '.join(in_progress)}"
        if in_progress
        else "  [OK] Нет rebase/merge/cherry-pick"
    )

    print("\n[Remote]")
    fetched = git("fetch", "--quiet", "origin", branch)
    if fetched.returncode != 0:
        print(f"  [!] Не удалось обновить origin/{branch}: {fetched.stderr.strip()}")
    remote_ref = f"origin/{branch}"
    counts = git("rev-list", "--left-right", "--count", f"HEAD...{remote_ref}")
    try:
        ahead, behind = [int(value) for value in counts.stdout.split()[:2]]
        print(f"  Ветка: {branch} | ahead: {ahead} | behind: {behind}")
        if behind:
            print("  [!] Сначала требуется pull/rebase.")
        elif ahead:
            print("  [i] Есть локальные коммиты для push.")
        else:
            print("  [OK] HEAD синхронизирован с remote.")
    except Exception:
        ahead = behind = -1
        print("  [!] Не удалось определить ahead/behind.")

    print("\n[Stash]")
    stashes = git("stash", "list")
    if stashes.stdout.strip():
        lines = stashes.stdout.splitlines()
        print(f"  [!] Записей: {len(lines)}")
        for line in lines[:10]:
            print(f"      {line}")
    else:
        print("  [OK] Stash пуст")

    print("\n[Signing key]")
    key = get_signing_key()
    if key:
        print(f"  [OK] Найден: {key}")
    else:
        print(f"  [!] Не найден. Ожидается: {DEFAULT_SIGNING_KEY}")

    print("\n[Release manifest]")
    version = "?"
    try:
        manifest = json.loads(VERSION_JSON_PATH.read_text(encoding="utf-8"))
        version = str(manifest.get("version", "?"))
        files = manifest.get("files", [])
        hashes = manifest.get("sha256", {})
        print(f"  version: {version} | files: {len(files)} | sha256: {len(hashes)}")
    except Exception as exc:
        print(f"  [ОШИБКА] version.json не читается: {exc}")

    clean = not status.stdout.strip()
    if clean:
        release_ok = verify_release_state()
    else:
        # Old manifest describes HEAD, not current uncommitted files. A payload
        # mismatch is expected until [1] regenerates it; still verify that the
        # currently published manifest itself has a valid signature.
        try:
            from engine.update_signing import verify_manifest_signature

            verify_manifest_signature(VERSION_JSON_PATH.read_bytes(), SIGNATURE_PATH.read_bytes())
            print("  [OK] Текущая Ed25519 signature валидна.")
            print("  [i] Payload SHA256 будет проверен после регенерации в пункте [1].")
            release_ok = None
        except Exception as exc:
            print(f"  [ОШИБКА] Текущая signature невалидна: {exc}")
            release_ok = False

    print("\n[Итог]")
    no_operation = not in_progress
    remote_ready = behind == 0
    if clean and no_operation and remote_ready and release_ok is True and key:
        print(f"  [OK] Проект готов к безопасному release/push (version {version}).")
    else:
        print("  [!] Проект пока не готов к release.")
        if not clean:
            print("      - есть изменения; выберите [1], чтобы пересчитать manifest")
        if not no_operation:
            print("      - незавершённая Git operation")
        if behind not in (0, -1):
            print("      - локальная ветка отстаёт от remote")
        if release_ok is False:
            print("      - Ed25519 signature не прошла проверку")
        if not key:
            print("      - отсутствует signing key")

    input("\nНажмите Enter для продолжения...")


# ----------------------------------------------------------------
#  ОТПРАВКА ОДИНОЧНОГО ФАЙЛА  (Push single file)
#  Коммитит и пушит ТОЛЬКО выбранный файл, не трогая остальные
#  изменения и НЕ пересобирая version.json / SHA256 (это точечная
#  отправка, а не релиз).
# ----------------------------------------------------------------


def do_push_single_file() -> None:
    print()
    print("=" * 50)
    print("  ОТПРАВКА ОДИНОЧНОГО ФАЙЛА (PUSH SINGLE FILE)")
    print("=" * 50)

    branch = get_branch()

    # Собираем список изменённых/новых файлов (staged + unstaged + untracked).
    # git status --porcelain даёт по строке на файл: "XY <путь>".
    # -c core.quotepath=false — чтобы кириллица в именах файлов выводилась
    # как есть, а не в виде escape-последовательностей (\321\204...).
    r = git("-c", "core.quotepath=false", "status", "--porcelain")
    entries = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        # Первые два символа — статус, дальше пробел и путь.
        path = line[3:].strip()
        # Переименование: "old -> new" — берём новый путь.
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        # Путь может быть в кавычках (если есть кириллица/пробелы) — снимаем их.
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if path and path not in entries:
            entries.append(path)

    if not entries:
        print("\n  Нет изменённых файлов для отправки.")
        input("\nНажмите Enter для продолжения...")
        return

    print("\nИзменённые файлы:\n")
    for i, path in enumerate(entries, start=1):
        print(f"  [{i}] {path}")
    print("\n  [0] Отмена")

    raw = input("\nВыберите файл (номер) или введите путь вручную: ").strip()
    if not raw or raw == "0":
        print("Отменено.")
        input("\nНажмите Enter для продолжения...")
        return

    # Пользователь мог ввести номер из списка или путь напрямую.
    if raw.isdigit():
        idx = int(raw)
        if not (1 <= idx <= len(entries)):
            print("  [ОШИБКА] Неверный номер.")
            input("\nНажмите Enter для продолжения...")
            return
        target = entries[idx - 1]
    else:
        target = raw

    if not (PROJECT_ROOT / target).exists():
        print(f"  [ОШИБКА] Файл не найден на диске: {target}")
        input("\nНажмите Enter для продолжения...")
        return

    release_only = {
        "version.json",
        "version.json.sig",
        "json/version.json",
        "json/version.json.sig",
        "checksums.txt",
    }
    if target.replace("\\", "/") in release_only:
        print("  [БЛОКИРОВКА] Release metadata нельзя отправлять по одному.")
        print("  Используйте [1] Обновление для атомарного manifest/signature/checksums.")
        input("\nНажмите Enter для продолжения...")
        return

    print(f"\n  Будет отправлен только: {target}")
    confirm = input("  Продолжить? (y/n, Enter=y): ").strip().lower()
    if confirm not in ("", "y", "yes", "д", "да"):
        print("Отменено.")
        input("\nНажмите Enter для продолжения...")
        return

    # --- 1. Коммит только выбранного файла ---
    print("\n[1/3] Коммит выбранного файла...")
    add_r = git("add", "--", target)
    if add_r.returncode != 0:
        print(f"  [ОШИБКА] Не удалось добавить файл:\n{add_r.stderr}")
        input("\nНажмите Enter для продолжения...")
        return

    default_msg = f"Update {target}"
    msg = input(f"  Сообщение коммита (Enter={default_msg}): ").strip() or default_msg
    # Коммитим ТОЛЬКО этот путь, даже если в индексе есть другое.
    commit_r = git("commit", "-m", msg, "--", target)
    if commit_r.returncode != 0:
        # Возможно, файл не изменился относительно HEAD (нечего коммитить).
        combined = (commit_r.stdout or "") + (commit_r.stderr or "")
        if "nothing to commit" in combined.lower() or "no changes added" in combined.lower():
            print("  [ИНФО] Нечего коммитить — файл не отличается от последнего коммита.")
        else:
            print(f"  [ОШИБКА] Не удалось выполнить коммит:\n{commit_r.stderr or commit_r.stdout}")
            input("\nНажмите Enter для продолжения...")
            return
    else:
        print(f"  [OK] Закоммичено: {msg}")

    # --- 2. Pull --rebase (чтобы push не отклонился) ---
    print("\n[2/3] Получение изменений с сервера (Pull)...")
    pull_r, is_network_error, is_stuck_rebase = git_pull_rebase(branch)
    if pull_r.returncode != 0:
        if is_network_error:
            print("\n[!] Нет связи с GitHub (сеть/DNS/VPN недоступны). Push отменён.")
        elif is_stuck_rebase:
            print("\n[!] Git заблокирован процессом rebase. Выберите [4] Таблетка и повторите.")
        else:
            print(
                "\n[!] Конфликт при объединении изменений. Запустите [1] Обновление для разрешения."
            )
        input("\nНажмите Enter для продолжения...")
        return

    # --- 3. Push ---
    print("\n[3/3] Отправка изменений на удалённый сервер (Push)...")
    push_r = git_show("push", "origin", branch)
    if push_r.returncode != 0:
        print(
            "\n[ОШИБКА] Не удалось отправить изменения (Push). Проверьте доступ к сети/репозиторию."
        )
        input("\nНажмите Enter для продолжения...")
        return

    print("\n" + "=" * 50)
    print(f"  ГОТОВО! Файл отправлен: {target}")
    print("=" * 50)
    input("\nНажмите Enter для продолжения...")


def menu() -> None:
    print("\n" * 2)
    print("=" * 50)
    print("       Менеджер Git для XTTS Studio")
    print("=" * 50)
    print(f"\nПроект  : {PROJECT_ROOT}")
    print(f"Ветка   : {get_branch()}")

    # Индикация в меню, если есть зависший процесс rebase/merge
    rebase_merge = PROJECT_ROOT / ".git" / "rebase-merge"
    rebase_apply = PROJECT_ROOT / ".git" / "rebase-apply"
    if rebase_merge.exists() or rebase_apply.exists():
        print("\n[!] ВНИМАНИЕ: Обнаружен незавершённый процесс Git rebase (.git/rebase-merge).")
        print("    Для автоматического сброса выберите пункт [4] или запустите [1] Обновление.")

    r = git("status", "--short")
    print("\n" + (r.stdout if r.stdout.strip() else "(чистая рабочая директория — нет изменений)"))

    print("\n  [1] Обновление (Update)    — коммит + получение изменений + отправка (pull & push)")
    print("  [2] Откат (Rollback)       — возврат к более раннему коммиту")
    print(
        "  [3] Игнорируемые (Untrack) — удалить файлы из .gitignore из отслеживания (оставив на диске)"
    )
    print("  [4] Таблетка (Сброс)       — сбросить зависший rebase (.git/rebase-merge)")
    print("  [5] Один файл (Push file)  — коммит + отправка ТОЛЬКО одного файла (без релиза/SHA)")
    print("  [6] Проверка статуса        — Git/remote/stash/signature/SHA256 (read-only)")
    print("  [0] Выход (Exit)")
    choice = input("\nВыберите действие: ").strip()

    if choice == "1":
        do_update()
    elif choice == "2":
        do_rollback()
    elif choice == "3":
        do_untrack_ignored()
    elif choice == "4":
        cleanup_stuck_rebase(verbose=True)
        input("\nНажмите Enter для продолжения...")
    elif choice == "5":
        do_push_single_file()
    elif choice == "6":
        do_status_check()
    elif choice == "0":
        print("До свидания.")
        sys.exit(0)


if __name__ == "__main__":
    if not check_git():
        input("Нажмите Enter для выхода...")
        sys.exit(1)

    try:
        while True:
            menu()
    except KeyboardInterrupt:
        print("\nДо свидания.")
        sys.exit(0)
