#!/usr/bin/env python3
"""
git_update.py — Git manager for XTTS Studio.
Place in tools/, run via git_update.bat.

Safe flow: commit first, then pull, then push.
Files are NEVER lost — everything is committed BEFORE any remote sync.
"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENERATE_FILES_SCRIPT = PROJECT_ROOT / "tools" / "generate_version_files.py"
GENERATE_MANIFEST_SCRIPT = PROJECT_ROOT / "generate_version_manifest.py"
VERSION_JSON_PATH = PROJECT_ROOT / "version.json"


def run_python_script(script_path: Path, args: list) -> int:
    """Run a Python script with the same interpreter that's running this script."""
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
    print("\n  Current changelog:")
    if current:
        for line in current.split("\n"):
            print(f"    {line}")
    else:
        print("    (empty)")

    choice = input("\n  Write a new changelog for this release? (y/n, Enter=keep current): ").strip().lower()
    if choice != "y":
        return current

    print("  Enter changelog lines one by one. Empty line to finish:")
    lines = []
    while True:
        line = input("    ").strip()
        if not line:
            break
        lines.append(line if line.startswith("-") else f"- {line}")

    if not lines:
        print("  No lines entered — keeping current changelog.")
        return current

    return "\n".join(lines)


def update_version_manifest():
    """
    Rebuilds version.json's file list, lets the user (re)write the changelog,
    then generates SHA256 checksums for this release.

    Returns:
      - the version string on success (files/changelog/sha256 regenerated)
      - "SKIP" if the user intentionally chose not to release this push
        (e.g. just pushing test results or other non-release files)
      - None on a real failure (missing script, empty version, generation error)
    """
    do_release = input(
        "\n  Bump version and regenerate SHA256 checksums for this push? (y/n, Enter=y): "
    ).strip().lower()
    if do_release == "n":
        print("  Skipping version/SHA256 update — this push will not be tagged as a release.")
        return "SKIP"

    if not GENERATE_FILES_SCRIPT.exists():
        print(f"  [ERROR] {GENERATE_FILES_SCRIPT} not found.")
        return None

    print("  Rebuilding file list...")
    if run_python_script(GENERATE_FILES_SCRIPT, []) != 0:
        print("  [ERROR] generate_version_files.py failed.")
        return None

    if not GENERATE_MANIFEST_SCRIPT.exists():
        print(f"  [ERROR] {GENERATE_MANIFEST_SCRIPT} not found.")
        return None

    version = input("  Version for this release (e.g. 1.1.56): ").strip()
    if not version:
        print("  [ERROR] Version is required.")
        return None
    min_app_version = input("  Min app version for incremental update (Enter to skip): ").strip()

    changelog = _prompt_changelog(_read_current_changelog())

    args = ["--version", version, "--changelog", changelog]
    if min_app_version:
        args += ["--min-app-version", min_app_version]

    print(f"  Generating SHA256 checksums for {version}...")
    if run_python_script(GENERATE_MANIFEST_SCRIPT, args) != 0:
        print("  [ERROR] generate_version_manifest.py failed.")
        return None

    print("  [OK] version.json + checksums.txt updated.")
    return version


def git(*args: str) -> subprocess.CompletedProcess:
    """Run git command from project root, return CompletedProcess."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def git_show(*args: str) -> subprocess.CompletedProcess:
    """Run git with output shown directly in console (pull, push, rebase)."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(PROJECT_ROOT),
        timeout=120,
    )


def check_git() -> bool:
    r = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    if r.returncode != 0:
        print("[ERROR] Git not found. Install Git and add to PATH.")
        return False
    if not (PROJECT_ROOT / ".git").exists():
        print(f"[ERROR] {PROJECT_ROOT} is not a Git repository.")
        return False
    return True


def get_branch() -> str:
    r = git("rev-parse", "--abbrev-ref", "HEAD")
    return r.stdout.strip() or "main"


def has_staged() -> bool:
    r = git("diff", "--cached", "--quiet")
    return r.returncode != 0


# ----------------------------------------------------------------
#  UPDATE  (commit first → pull → push)
# ----------------------------------------------------------------

def do_update() -> None:
    branch = get_branch()
    print()
    print("=" * 50)
    print("  UPDATE")
    print("=" * 50)
    print(f"\nCurrent changes:")
    r = git("status", "--short")
    if r.stdout.strip():
        print(r.stdout)
    else:
        print("  (no changes)")

    print()
    confirm = input("Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        return

    # --- 1. Stage ALL local changes ---
    print("\n[1/4] Committing local changes...")
    git_show("add", "-A")

    if has_staged():
        msg = input("  Commit message (Enter=Update): ").strip() or "Update"
        r = git("commit", "-m", msg)
        if r.returncode != 0:
            if "nothing to commit" in r.stderr.lower() + r.stdout.lower():
                print("  Nothing to commit.")
            else:
                print(f"  [ERROR] Commit failed:\n{r.stderr}")
                input("\nPress Enter...")
                return
        print(f"  [OK] Committed: {msg}")
    else:
        print("  Nothing to stage.")

    # --- 2. Rebuild version.json + SHA256 checksums (optional per push) ---
    print("\n[2/4] Version / SHA256 checksums...")
    version = update_version_manifest()
    if version == "SKIP":
        pass  # user intentionally skipped — not an error, just proceed to pull/push
    elif version:
        git_show("add", "-A")
        if has_staged():
            r = git("commit", "-m", f"Release {version}")
            if r.returncode != 0 and "nothing to commit" not in (r.stderr.lower() + r.stdout.lower()):
                print(f"  [ERROR] Commit failed:\n{r.stderr}")
                input("\nPress Enter...")
                return
            print(f"  [OK] Committed: Release {version}")
        else:
            print("  version.json unchanged, nothing new to commit.")
    else:
        cont = input("\n  Continue push WITHOUT updated version.json/SHA256? (y/n): ").strip().lower()
        if cont != "y":
            print("  Aborted. Fix the issue above and run Update again.")
            input("\nPress Enter...")
            return

    # --- 3. Pull with rebase ---
    print("\n[3/4] Pulling from remote...")
    r = git_show("pull", "--rebase", "--no-edit", "origin", branch)
    if r.returncode != 0:
        print("\n[!] Conflict during rebase!")
        print("    Your commits are saved. To abort the rebase:")
        print("    git rebase --abort")
        print("    (Your local commits will still be there)")
        input("\nPress Enter...")
        return

    # --- 4. Push ---
    print("\n[4/4] Pushing to remote...")
    r = git_show("push", "origin", branch)
    if r.returncode != 0:
        print("\n[ERROR] Push failed. Check remote access.")
        input("\nPress Enter...")
        return

    print("\n" + "=" * 50)
    print("  DONE!")
    print("=" * 50)
    input("\nPress Enter...")


# ----------------------------------------------------------------
#  ROLLBACK
# ----------------------------------------------------------------

def do_rollback() -> None:
    print()
    print("=" * 50)
    print("  RECENT COMMITS")
    print("=" * 50)

    r = git("log", "--oneline", "-10")
    print("\n" + (r.stdout if r.stdout.strip() else "(no commits)"))

    print("\n" + "-" * 40)
    print("  [1] Soft reset  — undo commit, keep files staged")
    print("  [2] Mixed reset — undo commit, unstage (default)")
    print("  [3] Hard reset  — DELETE files permanently !!!")
    print("  [0] Cancel")

    choice = input("\nType (1/2/3, Enter=2): ").strip() or "2"
    if choice == "0":
        return

    flags = {"1": "--soft", "2": "--mixed", "3": "--hard"}
    flag = flags.get(choice)
    if not flag:
        print("Invalid.")
        input("Press Enter...")
        return

    if choice == "3":
        print("\n[!] HARD RESET — files will be PERMANENTLY DELETED!")

    commit = input("\nCommit hash to roll back to: ").strip()
    if not commit:
        return

    print("\nWill undo:")
    r = git("log", "--oneline", f"{commit}..HEAD")
    print(r.stdout if r.stdout.strip() else "  (none)")

    c = input("\nType 'yes' to confirm: ").strip().lower()
    if c != "yes":
        print("Cancelled.")
        input("Press Enter...")
        return

    print(f"\nRolling back to {commit}...")
    r = git_show("reset", flag, commit)
    if r.returncode != 0:
        print("\n[ERROR] Reset failed.")
    else:
        print(f"\n[OK] Rolled back.")
        print(f"Push this: git push --force-with-lease origin {get_branch()}")

    input("\nPress Enter...")


# ----------------------------------------------------------------
#  UNTRACK IGNORED FILES  (remove from Git index, keep on disk)
# ----------------------------------------------------------------

def do_untrack_ignored() -> None:
    print()
    print("=" * 50)
    print("  UNTRACK IGNORED FILES")
    print("=" * 50)
    print("\nRemoves files matching .gitignore from Git tracking.")
    print("Files stay on your disk — only the Git index is affected.")
    print("\nSteps: git rm -r --cached . -> git add -A -> review -> commit")

    confirm = input("\nProceed? (y/n): ").strip().lower()
    if confirm != "y":
        return

    print("\n[1/3] Removing all files from the Git index (kept on disk)...")
    r = subprocess.run(
        ["git", "rm", "-r", "--cached", "-q", "."],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if r.returncode != 0:
        print(f"  [ERROR] {r.stderr}")
        input("\nPress Enter...")
        return
    print("  [OK] Index cleared.")

    print("\n[2/3] Re-adding files (this time .gitignore is respected)...")
    r = git("add", "-A")
    if r.returncode != 0:
        print(f"  [ERROR] {r.stderr}")
        input("\nPress Enter...")
        return
    print("  [OK] Re-added.")

    print("\n[3/3] Changes staged for commit:")
    r = git("status", "--short")
    if not r.stdout.strip():
        print("  (nothing changed — the index already matched .gitignore)")
        input("\nPress Enter...")
        return
    print(r.stdout)

    print("\nOnly 'D' (removed-from-index) lines for ignored paths are expected.")
    print("If something unexpected shows up, fix .gitignore, then run this again")
    print("before committing (nothing has been committed yet).")

    confirm2 = input("\nCommit these changes now? (y/n): ").strip().lower()
    if confirm2 != "y":
        print("Left staged, not committed. Re-run or commit manually when ready.")
        input("\nPress Enter...")
        return

    msg = input("  Commit message (Enter=Untrack ignored files): ").strip() or "Untrack ignored files"
    r = git("commit", "-m", msg)
    if r.returncode != 0:
        print(f"  [ERROR] Commit failed:\n{r.stderr}")
        input("\nPress Enter...")
        return
    print(f"  [OK] Committed: {msg}")

    push = input("\nPush now? (y/n): ").strip().lower()
    if push == "y":
        branch = get_branch()
        print("\nPushing...")
        r = git_show("push", "origin", branch)
        if r.returncode != 0:
            print("\n[ERROR] Push failed. Check remote access.")
        else:
            print("\n[OK] Pushed.")

    input("\nPress Enter...")


# ----------------------------------------------------------------
#  MENU
# ----------------------------------------------------------------

def menu() -> None:
    print("\n" * 2)
    print("=" * 50)
    print("       XTTS Studio Git Manager")
    print("=" * 50)
    print(f"\nProject : {PROJECT_ROOT}")
    print(f"Branch  : {get_branch()}")

    r = git("status", "--short")
    print("\n" + (r.stdout if r.stdout.strip() else "(clean tree)"))

    print("\n  [1] Update   (commit + pull + push)")
    print("  [2] Rollback (revert to earlier commit)")
    print("  [3] Untrack ignored files (remove from Git, keep on disk)")
    print("  [0] Exit")
    choice = input("\nChoose: ").strip()

    if choice == "1":
        do_update()
    elif choice == "2":
        do_rollback()
    elif choice == "3":
        do_untrack_ignored()
    elif choice == "0":
        print("Bye.")
        sys.exit(0)


if __name__ == "__main__":
    if not check_git():
        input("Press Enter to exit.")
        sys.exit(1)

    try:
        while True:
            menu()
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)