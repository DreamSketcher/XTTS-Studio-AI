@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title XTTS Studio - Tests (pytest)

cd /d "%~dp0"

REM =============================================
REM  Detect Python interpreter
REM =============================================

set "PY=python"

if exist "%~dp0..\python\runtime\python.exe" (
    set "PY=%~dp0..\python\runtime\python.exe"
) else if exist "%~dp0..\python\xtts_env\python.exe" (
    set "PY=%~dp0..\python\xtts_env\python.exe"
) else if exist "%~dp0..\python\xtts_env\Scripts\python.exe" (
    set "PY=%~dp0..\python\xtts_env\Scripts\python.exe"
) else if exist "%~dp0..\.venv\Scripts\python.exe" (
    set "PY=%~dp0..\.venv\Scripts\python.exe"
) else if exist "%~dp0..\venv\Scripts\python.exe" (
    set "PY=%~dp0..\venv\Scripts\python.exe"
) else if exist "%~dp0python\xtts_env\python.exe" (
    set "PY=%~dp0python\xtts_env\python.exe"
) else if exist "%~dp0python\xtts_env\Scripts\python.exe" (
    set "PY=%~dp0python\xtts_env\Scripts\python.exe"
)

REM =============================================
REM  Detect test folder
REM =============================================

set "TESTDIR=%~dp0"
if exist "%~dp0test_updater.py" (
    set "TESTDIR=%~dp0."
) else if exist "%~dp0test\test_updater.py" (
    set "TESTDIR=%~dp0test"
)

set "PYTHONPATH=%~dp0..;%PYTHONPATH%"
set "PYTEST_LOG=%~dp0result\pytest_report.txt"

REM  Ensure result folder exists
if not exist "%~dp0result" mkdir "%~dp0result"

REM =============================================
REM  CLI mode (no menu)
REM =============================================

if /i "%~1"=="real" (
    "%PY%" "%~dp0_verify.py" "%~dp0.."
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="all" (
    "%PY%" -m pytest "%TESTDIR%" -v > "%PYTEST_LOG%" 2>&1
    type "%PYTEST_LOG%"
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="lf" (
    "%PY%" -m pytest "%TESTDIR%" --lf -v > "%PYTEST_LOG%" 2>&1
    type "%PYTEST_LOG%"
    exit /b %ERRORLEVEL%
)

if not "%~1"=="" (
    echo Unknown mode: %~1  ^(valid: real, all, lf^)
    exit /b 1
)

REM =============================================
REM  Check if pytest is installed
REM =============================================

"%PY%" -m pytest --version >nul 2>&1

if errorlevel 1 (
    echo.
    echo [!] pytest not found in this Python environment.
    echo     Interpreter: %PY%
    echo.
    set "INSTALL_CONFIRM="
    set /p INSTALL_CONFIRM="Install pytest now? (y/n): "
    if /i "!INSTALL_CONFIRM!"=="y" (
        "%PY%" -m pip install pytest
        if errorlevel 1 (
            echo Failed to install pytest.
            pause
            exit /b 1
        )
    ) else (
        echo Cannot run tests without pytest. Exiting.
        pause
        exit /b 1
    )
)

REM =============================================
REM  MAIN MENU
REM =============================================

:MENU
cls
echo ==================================================
echo   XTTS Studio - Test Runner
echo   Python: %PY%
echo   Tests : %TESTDIR%
echo ==================================================
echo.
echo   [1] Run ALL tests
echo.
echo   [2] test_updater.py       ^(updates^)
echo   [3] test_normalizer.py    ^(numbers, abbreviations^)
echo   [4] test_chunker.py       ^(text chunking^)
echo   [5] test_smart_pauses.py  ^(pauses, emotions^)
echo.
echo   [6] Run all tests - verbose ^(-v^)
echo   [7] Run only last failed  ^(--lf^)
echo.
echo   [8] Project verification  ^(syntax/imports/JSON^)
echo.
echo   [0] Exit
echo.
set /p CHOICE="Select option: "

if "%CHOICE%"=="1" goto RUN_ALL
if "%CHOICE%"=="2" goto RUN_ONE
if "%CHOICE%"=="3" goto RUN_ONE
if "%CHOICE%"=="4" goto RUN_ONE
if "%CHOICE%"=="5" goto RUN_ONE
if "%CHOICE%"=="6" goto RUN_ALL_VERBOSE
if "%CHOICE%"=="7" goto RUN_LAST_FAILED
if "%CHOICE%"=="8" call :RUN_VERIFY
if "%CHOICE%"=="0" goto END

echo Invalid option.
pause
goto MENU

REM =============================================
REM  Run single test file
REM =============================================

:RUN_ONE
if "%CHOICE%"=="2" set "FILE=%TESTDIR%\test_updater.py"
if "%CHOICE%"=="3" set "FILE=%TESTDIR%\test_normalizer.py"
if "%CHOICE%"=="4" set "FILE=%TESTDIR%\test_chunker.py"
if "%CHOICE%"=="5" set "FILE=%TESTDIR%\test_smart_pauses.py"

if not exist "%FILE%" (
    echo.
    echo [!] File not found: %FILE%
    pause
    goto MENU
)

echo.
echo Running: %FILE%
echo --------------------------------------------------------------
"%PY%" -m pytest "%FILE%" -v > "%PYTEST_LOG%" 2>&1
type "%PYTEST_LOG%"
goto RESULT

REM =============================================
REM  Run all tests
REM =============================================

:RUN_ALL
echo.
echo Running all tests from: %TESTDIR%
echo --------------------------------------------------------------
"%PY%" -m pytest "%TESTDIR%" > "%PYTEST_LOG%" 2>&1
type "%PYTEST_LOG%"
goto RESULT

:RUN_ALL_VERBOSE
echo.
echo Running all tests ^(verbose^) from: %TESTDIR%
echo --------------------------------------------------------------
"%PY%" -m pytest "%TESTDIR%" -v > "%PYTEST_LOG%" 2>&1
type "%PYTEST_LOG%"
goto RESULT

:RUN_LAST_FAILED
echo.
echo Re-running only previously failed tests...
echo --------------------------------------------------------------
"%PY%" -m pytest "%TESTDIR%" --lf -v > "%PYTEST_LOG%" 2>&1
type "%PYTEST_LOG%"
goto RESULT

REM =============================================
REM  Project verification
REM  Calls _verify.py (same folder) with the
REM  project root as argument. No quoting hell.
REM =============================================

:RUN_VERIFY
echo.
echo Project verification ^(syntax / imports / JSON^)...
echo --------------------------------------------------------------
echo Python: %PY%
echo.
"%PY%" "%~dp0_verify.py" "%~dp0.."
echo.
echo ==================================================
if errorlevel 1 (
    echo   RESULT: ISSUES FOUND
) else (
    echo   RESULT: PROJECT OK
)
echo ==================================================
echo   Log saved: %~dp0verify_report.txt
echo.
pause
goto MENU

REM =============================================
REM  Test results
REM =============================================

:RESULT
echo.
echo ==================================================
if errorlevel 1 (
    echo   RESULT: SOME TESTS FAILED
) else (
    echo   RESULT: ALL TESTS PASSED
)
echo ==================================================
echo   Log saved: %PYTEST_LOG%
echo.
pause
goto MENU

REM =============================================

:END
endlocal
exit /b 0
