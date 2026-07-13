import os
import sys
import re

def has_cyrillic(text: str) -> bool:
    """Checks if the string contains any Russian (Cyrillic) characters."""
    return bool(re.search('[а-яА-ЯёЁ]', text))

def check_project_path():
    """
    Validates the execution paths for Cyrillic characters before loading heavy modules.
    If Cyrillic is found, prints a console warning and displays a native Windows MessageBox
    (if on Windows) to prevent silent loading or execution failures, then exits or warns.
    """
    app_dir = os.path.abspath(os.path.dirname(__file__))
    # Go up if inside engine/
    if os.path.basename(app_dir) == 'engine':
        project_root = os.path.dirname(app_dir)
    else:
        project_root = app_dir

    cwd = os.path.abspath(os.getcwd())
    python_exe = os.path.abspath(sys.executable)

    problematic_paths = []
    
    if has_cyrillic(project_root):
        problematic_paths.append(f"Project directory: '{project_root}'")
    if has_cyrillic(cwd):
        problematic_paths.append(f"Working directory: '{cwd}'")
    if has_cyrillic(python_exe):
        problematic_paths.append(f"Python executable: '{python_exe}'")

    if problematic_paths:
        title = "XTTS Studio - Path Validation Warning"
        message = (
            "⚠️ CRITICAL PATH WARNING ⚠️\n\n"
            "Cyrillic (Russian) characters were detected in your installation paths:\n"
            + "\n".join(f"• {path}" for path in problematic_paths) + "\n\n"
            "XTTS Studio, PyTorch, and CUDA dependencies are highly sensitive to non-ASCII paths. "
            "Running from folders containing spaces, Cyrillic, or special characters frequently causes: \n"
            "  1. Silent crashes during model loading\n"
            "  2. Failed audio generation with obscure C++ file-access errors\n"
            "  3. DLL loading failures for torch / CUDA.\n\n"
            "👉 RECOMMENDED FIX:\n"
            "Move 'XTTS Studio' folder directly to the root of a drive with only English characters, "
            "for example: C:\\XTTS_Studio\\\n\n"
            "Press OK to continue anyway (not recommended), or Cancel to exit and fix the path."
        )

        # Output to console/terminal
        print("!" * 80, file=sys.stderr)
        print(message, file=sys.stderr)
        print("!" * 80, file=sys.stderr)

        # Show native Win32 dialog if on Windows
        if sys.platform == "win32":
            try:
                import ctypes
                # MB_OKCANCEL = 0x1, MB_ICONWARNING = 0x30, IDOK = 1, IDCANCEL = 2
                response = ctypes.windll.user32.MessageBoxW(0, message, title, 0x1 | 0x30)
                if response == 2:  # Cancel clicked
                    print("Execution aborted by the user to fix path encoding issue.", file=sys.stderr)
                    sys.exit(1)
            except Exception as e:
                print(f"Could not display native Windows warning dialog: {e}", file=sys.stderr)
        else:
            # On Linux/macOS, we can print to terminal and offer a prompt if run interactively
            try:
                if sys.stdin.isatty():
                    ans = input("\nDo you want to abort and move the folder? (y/n): ")
                    if ans.lower() in ['y', 'yes', '']:
                        sys.exit(1)
            except Exception:
                pass

if __name__ == "__main__":
    check_project_path()
