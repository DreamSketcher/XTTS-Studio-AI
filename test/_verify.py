#!/usr/bin/env python3
"""
_verify.py — Project verification for XTTS Studio.
Called by run_tests.bat with the project root as first argument.

Usage:
    python _verify.py "C:\XTTS Studio"
"""

import sys
import os
import ast
import json
import importlib
import site
import tempfile
from pathlib import Path


class Tee:
    """Write to both stdout and a log file simultaneously."""

    def __init__(self, filepath: Path):
        self.file = open(filepath, "w", encoding="utf-8")
        self.stdout = sys.stdout

    def write(self, message):
        self.stdout.write(message)
        self.file.write(message)

    def flush(self):
        self.stdout.flush()
        self.file.flush()

    def close(self):
        self.file.close()


def _strip_bom(source: str) -> str:
    """Remove UTF-8 BOM (U+FEFF) if present at the start of the source."""
    if source and source[0] == "\ufeff":
        return source[1:]
    return source


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: _verify.py <project_root>")
        return 1

    PROJECT_ROOT = Path(sys.argv[1]).resolve()
    LOG_FILE = (PROJECT_ROOT / "test" / "verify_report.txt").resolve()

    # Tee output to console + log file
    tee = Tee(LOG_FILE)
    sys.stdout = tee

    print("=" * 70)
    print(f"REAL PROJECT VERIFICATION: {PROJECT_ROOT}")
    print(f"Python  : {sys.executable}")
    print(f"Version : {sys.version.split()[0]}")
    print("=" * 70)

    # ----------------------------------------------------------------
    # 0. Portable Python environment
    # ----------------------------------------------------------------
    print()
    print("[0/5] Portable Python environment...")
    portable_root = PROJECT_ROOT / "python"
    found_sp = []
    if portable_root.is_dir():
        for child in sorted(portable_root.iterdir()):
            if child.is_dir():
                for pat in ("Lib/site-packages", "lib/site-packages"):
                    cand = child / pat
                    if cand.is_dir():
                        sp = str(cand.resolve())
                        if sp not in found_sp:
                            found_sp.append(sp)
    if found_sp:
        print(f"  Detected {len(found_sp)} site-packages location(s):")
        for sp in found_sp:
            print(f"    -> {sp}")
            sys.path.insert(0, sp)
            try:
                site.addsitedir(sp)
            except Exception:
                pass
    else:
        print("  No portable env found — using system sys.path only.")
    sys.path.insert(0, str(PROJECT_ROOT))

    critical = 0
    warnings_total = 0

    # ----------------------------------------------------------------
    # 1. Critical files (auto-discover, WARN only if none found)
    # ----------------------------------------------------------------
    print()
    print("[1/5] Critical files...")
    # Accept any of these patterns for the engine entry point:
    engine_entry_patterns = [
        "engine/__init__.py",
        "engine/tts/__init__.py",
        "engine/tts.py",
        "engine/tts_runner.py",
        "engine/task_manager.py",
    ]
    found_engine = False
    for pat in engine_entry_patterns:
        if (PROJECT_ROOT / pat).is_file():
            found_engine = True
            break
    if found_engine:
        print("  OK — engine module found")
    else:
        print("  [WARN] No engine entry point found (checked common patterns)")
        warnings_total += 1

    # ----------------------------------------------------------------
    # 2. JSON configs (auto-discover, WARN only if NONE found)
    # ----------------------------------------------------------------
    print()
    print("[2/5] JSON configs...")
    json_candidates = [
        "config.json", "config.yaml", "config.yml",
        "config/tts_config.json", "config/tts_config.yaml",
        "config/gui_config.json", "config/gui_config.yaml",
        "config/presets.json", "config/presets.yaml",
        "settings.json", "settings.yaml",
    ]
    found_configs = []
    broken_configs = []
    for rel in json_candidates:
        p = PROJECT_ROOT / rel
        if p.is_file():
            found_configs.append(rel)
            if p.suffix in (".json",):
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        json.load(fh)
                except json.JSONDecodeError as e:
                    print(f"  [FAIL] Invalid JSON in {rel}: {e}")
                    critical += 1
                    broken_configs.append(rel)
                except Exception as e:
                    print(f"  [FAIL] Cannot read {rel}: {e}")
                    critical += 1
                    broken_configs.append(rel)
    if broken_configs:
        pass  # already printed above
    elif found_configs:
        print(f"  OK — {len(found_configs)} config(s) found: {', '.join(found_configs)}")
    else:
        print("  [WARN] No JSON/YAML configs found (checked common paths)")
        warnings_total += 1

    # ----------------------------------------------------------------
    # 3. Syntax check (with BOM tolerance)
    # ----------------------------------------------------------------
    print()
    print("[3/5] Syntax check of .py files...")
    EXCLUDE = {
        "__pycache__", ".git", ".venv", "venv",
        "python", "node_modules", "dist", "build", "test",
    }
    py_files = [
        p for p in PROJECT_ROOT.rglob("*.py")
        if not (set(p.parts) & EXCLUDE)
    ]
    syntax_errors = 0
    bom_stripped = 0
    for pf in sorted(py_files):
        try:
            with open(pf, "r", encoding="utf-8-sig") as fh:
                source = fh.read()
            # utf-8-sig already strips BOM, but just in case:
            source = _strip_bom(source)
            ast.parse(source, filename=str(pf))
        except SyntaxError as e:
            rel = pf.relative_to(PROJECT_ROOT)
            print(f"  [FAIL] Syntax error in {rel}: {e}")
            critical += 1
            syntax_errors += 1
        except UnicodeDecodeError:
            # Try with BOM explicitly
            try:
                with open(pf, "r", encoding="utf-8") as fh:
                    source = _strip_bom(fh.read())
                ast.parse(source, filename=str(pf))
                bom_stripped += 1
            except SyntaxError as e:
                rel = pf.relative_to(PROJECT_ROOT)
                print(f"  [FAIL] Syntax error in {rel}: {e}")
                critical += 1
                syntax_errors += 1
            except Exception as e:
                rel = pf.relative_to(PROJECT_ROOT)
                print(f"  [FAIL] Cannot read {rel}: {e}")
                critical += 1
                syntax_errors += 1
        except Exception as e:
            rel = pf.relative_to(PROJECT_ROOT)
            print(f"  [FAIL] Cannot read {rel}: {e}")
            critical += 1
            syntax_errors += 1
    info = f"  Checked: {len(py_files)} files, errors: {syntax_errors}"
    if bom_stripped:
        info += f", BOM stripped: {bom_stripped}"
    print(info)

    # ----------------------------------------------------------------
    # 4. Import check
    # ----------------------------------------------------------------
    STDLIB = {
        "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
        "asyncore", "atexit", "audioop", "base64", "bdb", "binascii", "binhex",
        "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb", "chunk",
        "cmath", "cmd", "code", "codecs", "codeop", "collections", "colorsys",
        "compileall", "concurrent", "configparser", "contextlib", "contextvars",
        "copy", "copyreg", "cProfile", "crypt", "csv", "ctypes", "curses",
        "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis",
        "distutils", "doctest", "email", "encodings", "enum", "errno",
        "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch", "formatter",
        "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
        "gettext", "glob", "grp", "gzip", "hashlib", "heapq", "hmac", "html",
        "http", "idlelib", "imaplib", "imghdr", "imp", "importlib", "inspect",
        "io", "ipaddress", "itertools", "json", "keyword", "lib2to3",
        "linecache", "locale", "logging", "lzma", "mailbox", "mailcap",
        "marshal", "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
        "netrc", "nis", "nntplib", "numbers", "operator", "optparse", "os",
        "ossaudiodev", "pathlib", "pdb", "pickle", "pickletools", "pipes",
        "pkgutil", "platform", "plistlib", "poplib", "posix", "posixpath",
        "pprint", "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
        "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
        "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
        "selectors", "shelve", "shlex", "shutil", "signal", "site", "smtpd",
        "smtplib", "sndhdr", "socket", "socketserver", "sqlite3", "ssl",
        "stat", "statistics", "string", "stringprep", "struct", "subprocess",
        "sunau", "symtable", "sys", "sysconfig", "tabnanny", "tarfile",
        "telnetlib", "tempfile", "termios", "test", "textwrap", "threading",
        "time", "timeit", "tkinter", "token", "tokenize", "trace", "traceback",
        "tracemalloc", "tty", "turtle", "turtledemo", "types", "typing",
        "unicodedata", "unittest", "urllib", "uu", "uuid", "venv", "warnings",
        "wave", "weakref", "webbrowser", "winreg", "winsound", "wsgiref",
        "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib",
        "graphlib", "zoneinfo", "tomllib",
    }
    KNOWN_3RD = {
        "pygame", "numpy", "customtkinter", "pydub",
        "torch", "torchaudio", "transformers", "TTS",
        "soundfile", "sounddevice", "librosa", "scipy",
        "pyaudio", "pydantic", "requests",
        "PIL", "pandas", "matplotlib",
    }

    print()
    print("[4/5] Import check of engine.* modules...")
    engine_dir = PROJECT_ROOT / "engine"
    missing_deps = {}
    checked = 0

    if engine_dir.is_dir():
        for pyf in sorted(engine_dir.rglob("*.py")):
            rel = pyf.relative_to(PROJECT_ROOT)
            parts = list(rel.with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if not parts:
                continue
            mod = ".".join(parts)
            checked += 1
            try:
                importlib.import_module(mod)
            except ModuleNotFoundError as e:
                mn = e.name or str(e)
                if mn.startswith("engine."):
                    print(
                        f"  [FAIL] Import error in {mod}: "
                        f'internal module "{mn}" not found'
                    )
                    critical += 1
                else:
                    top = mn.split(".")[0]
                    missing_deps.setdefault(top, []).append(mod)
            except SyntaxError as e:
                print(f"  [FAIL] Syntax error prevents import of {mod}: {e}")
                critical += 1
            except Exception as e:
                missing_deps.setdefault("other", []).append(
                    f"{mod} ({type(e).__name__})"
                )

    if missing_deps:
        print()
        print("  --- Missing third-party packages ---")
        for pkg in sorted(missing_deps):
            mods = missing_deps[pkg]
            warnings_total += 1
            print(f'  [WARN] Package "{pkg}" is not installed.')
            for m in mods[:5]:
                print(f"         -> needed by {m}")
            if len(mods) > 5:
                print(f"         ... and {len(mods) - 5} more modules")
        print()
        print(f"  -> Install: pip install {' '.join(sorted(missing_deps))}")
    elif critical == 0:
        print(f"  OK — {checked} modules imported successfully")

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    print()
    print("-" * 70)
    print(f"CRITICAL: {critical}  |  WARNINGS: {warnings_total}")
    print("=" * 70)
    if critical == 0 and warnings_total == 0:
        print("RESULT: PROJECT IS FULLY OPERATIONAL")
    elif critical == 0:
        print("RESULT: PROJECT OK (some warnings)")
    else:
        print("RESULT: CRITICAL ISSUES FOUND")
    print("=" * 70)

    tee.close()
    sys.stdout = tee.stdout
    print(f"\nReport saved: {LOG_FILE}")

    return 0 if critical == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
