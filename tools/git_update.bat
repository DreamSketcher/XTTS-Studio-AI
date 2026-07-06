@echo off
setlocal

title XTTS Studio - Git Manager

cd /d "%~dp0.."

REM =============================================
REM  Detect Python interpreter
REM =============================================

set "PY=python"

if exist "python\runtime\python.exe" (
    set "PY=python\runtime\python.exe"
) else if exist "python\xtts_env\python.exe" (
    set "PY=python\xtts_env\python.exe"
) else if exist "python\xtts_env\Scripts\python.exe" (
    set "PY=python\xtts_env\Scripts\python.exe"
)

REM =============================================
REM  Run git manager
REM =============================================

"%PY%" "tools\git_update.py"
exit /b %ERRORLEVEL%
