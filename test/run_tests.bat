@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title XTTS Studio - Tests (pytest)

cd /d "%~dp0"

REM =============================================
REM  SELF = folder of this .bat WITHOUT trailing backslash
REM  (: %~dp0   "\",  pytest "path\" 
REM   -  \"  )
REM =============================================
set "SELF=%~dp0"
if "%SELF:~-1%"=="\" set "SELF=%SELF:~0,-1%"

REM Project root = parent of test folder, also without trailing backslash
for %%I in ("%SELF%\..") do set "ROOT=%%~fI"

REM =============================================
REM  Detect Python interpreter
REM =============================================
set "PY=python"
if exist "%ROOT%\python\runtime\python.exe" (
    set "PY=%ROOT%\python\runtime\python.exe"
) else if exist "%ROOT%\python\xtts_env\python.exe" (
    set "PY=%ROOT%\python\xtts_env\python.exe"
) else if exist "%ROOT%\python\xtts_env\Scripts\python.exe" (
    set "PY=%ROOT%\python\xtts_env\Scripts\python.exe"
) else if exist "%ROOT%\.venv\Scripts\python.exe" (
    set "PY=%ROOT%\.venv\Scripts\python.exe"
) else if exist "%ROOT%\venv\Scripts\python.exe" (
    set "PY=%ROOT%\venv\Scripts\python.exe"
)

REM =============================================
REM  Detect test folder (no trailing backslash)
REM =============================================
set "TESTDIR=%SELF%"
if exist "%SELF%\test_updater.py" (
    set "TESTDIR=%SELF%"
) else if exist "%SELF%\test\test_updater.py" (
    set "TESTDIR=%SELF%\test"
)

set "PYTHONPATH=%ROOT%;%PYTHONPATH%"
set "PYTEST_LOG=%SELF%\result\pytest_report.txt"

if not exist "%SELF%\result" mkdir "%SELF%\result"

REM =============================================
REM  CLI mode (no menu)
REM =============================================
if /i "%~1"=="real" (
    "%PY%" "%SELF%\_verify.py" "%ROOT%"
    exit /b %ERRORLEVEL%
)
if /i "%~1"=="all" (
    call :RUN_PYTEST "%TESTDIR%" "-v"
    exit /b %ERRORLEVEL%
)
if /i "%~1"=="lf" (
    call :RUN_PYTEST "%TESTDIR%" "--lf -v"
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
echo   [9] test_updater_cancel_and_removed_files.py  ^(update cancel + removed_files^)
echo   [10] test_generate_version_manifest.py         ^(release manifest, removed_files diff^)
echo   [11] test_local_llm_client_download.py         ^(model download retry/resume^)
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
if "%CHOICE%"=="9" goto RUN_ONE
if "%CHOICE%"=="10" goto RUN_ONE
if "%CHOICE%"=="11" goto RUN_ONE
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
if "%CHOICE%"=="9" set "FILE=%TESTDIR%\test_updater_cancel_and_removed_files.py"
if "%CHOICE%"=="10" set "FILE=%TESTDIR%\test_generate_version_manifest.py"
if "%CHOICE%"=="11" set "FILE=%TESTDIR%\test_local_llm_client_download.py"

if not exist "%FILE%" (
    echo.
    echo [!] File not found: %FILE%
    pause
    goto MENU
)
call :RUN_PYTEST "%FILE%" "-v"
goto RESULT

REM =============================================
REM  Run all tests
REM =============================================
:RUN_ALL
call :RUN_PYTEST "%TESTDIR%" ""
goto RESULT

:RUN_ALL_VERBOSE
call :RUN_PYTEST "%TESTDIR%" "-v"
goto RESULT

:RUN_LAST_FAILED
echo.
echo Re-running only previously failed tests...
call :RUN_PYTEST "%TESTDIR%" "--lf -v"
goto RESULT

REM =============================================
REM  Project verification
REM =============================================
:RUN_VERIFY
echo.
echo Project verification ^(syntax / imports / JSON^)...
echo --------------------------------------------------------------
echo Python: %PY%
echo.
"%PY%" "%SELF%\_verify.py" "%ROOT%"
echo.
echo ==================================================
if errorlevel 1 (
    echo   RESULT: ISSUES FOUND
) else (
    echo   RESULT: PROJECT OK
)
echo ==================================================
echo   Log saved: %SELF%\result\verify_report.txt
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
REM  Shared pytest runner
REM  Runs pytest with output streamed to the console
REM  in real time (via PowerShell Tee-Object) while
REM  simultaneously saving it to PYTEST_LOG.
REM  %1 = target path (file or folder), %2 = extra pytest args (may be empty)
REM =============================================
:RUN_PYTEST
set "PT_TARGET=%~1"
set "PT_ARGS=%~2"
echo.
echo Running: %PT_TARGET% %PT_ARGS%
echo --------------------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "& '%PY%' -m pytest '%PT_TARGET%' %PT_ARGS% 2>&1 | Tee-Object -Variable ptOut; $ptOut | Out-File -FilePath '%PYTEST_LOG%' -Encoding utf8; exit $LASTEXITCODE"
exit /b %ERRORLEVEL%

REM =============================================
:END
endlocal
exit /b 0