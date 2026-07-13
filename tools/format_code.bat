@echo off
setlocal enabledelayedexpansion
title XTTS Studio - Code Formatter

REM ============================================================
REM  format_code.bat  --  auto-format project code
REM  Location: XTTS Studio\tools\format_code.bat
REM
REM  Formats ONLY the project source code.
REM  It NEVER touches the environment (python\), libraries,
REM  models, outputs, etc.
REM
REM  Usage:
REM    format_code.bat          -^> format the code
REM    format_code.bat check    -^> only check, change nothing
REM ============================================================

REM --- Project root = parent folder of this .bat (tools\..) ---
cd /d "%~dp0.."

echo ==================================================
echo   XTTS STUDIO - CODE FORMATTER
echo ==================================================
echo   Root: "%CD%"
echo.

REM --- Find Python: portable first, then py / python ---
set "PY="
if exist "%CD%\python\runtime\python.exe" set "PY=%CD%\python\runtime\python.exe"
if not defined PY (
    where py >nul 2>&1
    if not errorlevel 1 set "PY=py"
)
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)

if not defined PY (
    echo [ERROR] Python not found.
    goto :end
)

echo   Python: "%PY%"
"%PY%" --version
echo.

REM --- Make sure black and ruff are installed ---
"%PY%" -m black --version >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing black and ruff...
    "%PY%" -m pip install black==24.10.0 ruff==0.6.9
    echo.
)

REM --- Targets: only project code, optional ones added if present ---
set "TARGETS=engine"
if exist "%CD%\test" set "TARGETS=!TARGETS! test"
if exist "%CD%\gui.py" set "TARGETS=!TARGETS! gui.py"
if exist "%CD%\i18n.py" set "TARGETS=!TARGETS! i18n.py"
if exist "%CD%\generate_version_manifest.py" set "TARGETS=!TARGETS! generate_version_manifest.py"

echo   Targets: !TARGETS!
echo.

if /i "%~1"=="check" goto :checkmode

REM --- Format mode ---
echo ==================================================
echo   BLACK - formatting
echo ==================================================
"%PY%" -m black !TARGETS!
echo.
echo ==================================================
echo   RUFF - lint auto-fix
echo ==================================================
"%PY%" -m ruff check !TARGETS! --fix
echo.
echo ==================================================
echo   VERIFY
echo ==================================================
"%PY%" -m black --check !TARGETS!
"%PY%" -m ruff check !TARGETS!
echo.
echo [DONE] See results above. If no errors, ready to commit.
goto :end

:checkmode
echo ==================================================
echo   CHECK MODE - nothing will be changed
echo ==================================================
"%PY%" -m black --check !TARGETS!
echo.
"%PY%" -m ruff check !TARGETS!
echo.
echo [CHECK DONE] See results above.

:end
echo.
pause
endlocal
