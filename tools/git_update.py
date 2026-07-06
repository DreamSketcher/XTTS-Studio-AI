#!/usr/bin/env python3
"""
git_update.py — Git manager for XTTS Studio.
Place in tools/, run via git_update.bat.

Safe flow: commit first, then pull, then push.
Files are NEVER lost — everything is committed BEFORE any remote sync.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
    print("\n[1/3] Committing local changes...")
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

    # --- 2. Pull with rebase ---
    print("\n[2/3] Pulling from remote...")
    r = git_show("pull", "--rebase", "--no-edit", "origin", branch)
    if r.returncode != 0:
        print("\n[!] Conflict during rebase!")
        print("    Your commits are saved. To abort the rebase:")
        print("    git rebase --abort")
        print("    (Your local commits will still be there)")
        input("\nPress Enter...")
        return

    # --- 3. Push ---
    print("\n[3/3] Pushing to remote...")
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
    print("  [0] Exit")
    choice = input("\nChoose: ").strip()

    if choice == "1":
        do_update()
    elif choice == "2":
        do_rollback()
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
