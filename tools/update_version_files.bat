@echo off
chcp 65001 >nul
cd /d "%~dp0.."

echo Project root resolved to: %cd%

set PYTHON_EXE=%cd%\python\runtime\python.exe
set SCRIPT_PATH=%cd%\tools\generate_version_files.py
set PYTHONPATH=%cd%\python\xtts_env\Lib\site-packages

echo Looking for python.exe at: %PYTHON_EXE%
echo Looking for script at:     %SCRIPT_PATH%
echo.

if not exist "%PYTHON_EXE%" (
    echo [ERROR] python.exe NOT FOUND at the path above.
    echo Check the real location of your portable Python and fix PYTHON_EXE in this .bat.
    echo.
    pause
    exit /b 1
)

if not exist "%SCRIPT_PATH%" (
    echo [ERROR] generate_version_files.py NOT FOUND at the path above.
    echo Make sure it's saved inside the tools\ folder.
    echo.
    pause
    exit /b 1
)

echo Updating version.json file list...
"%PYTHON_EXE%" "%SCRIPT_PATH%"

echo.
pause
