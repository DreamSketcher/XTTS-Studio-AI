@echo off
setlocal enabledelayedexpansion

rem ============================================================
rem apply_diff.bat - pick and apply a .diff file to the project
rem
rem Folder layout (relative to this script, which lives in tools\):
rem   ..\                   - project root (git repo)
rem   diffs\                - drop new .diff files here
rem   diffs\applied\        - diffs are moved here after apply
rem   diff_exclude.txt      - one protected path per line
rem                           (files/folders a diff must never touch)
rem ============================================================

set "PROJECT_ROOT=%~dp0.."
set "DIFF_DIR=%~dp0diffs"
set "APPLIED_DIR=%DIFF_DIR%\applied"
set "EXCLUDE_FILE=%~dp0diff_exclude.txt"

if not exist "%DIFF_DIR%" mkdir "%DIFF_DIR%"
if not exist "%APPLIED_DIR%" mkdir "%APPLIED_DIR%"
if not exist "%EXCLUDE_FILE%" (
    echo # One protected path per line, e.g.:> "%EXCLUDE_FILE%"
    echo # python/>> "%EXCLUDE_FILE%"
    echo # models/>> "%EXCLUDE_FILE%"
    echo # requirements.txt>> "%EXCLUDE_FILE%"
)

where git >nul 2>nul
if errorlevel 1 (
    echo Git not found in PATH. Install Git for Windows.
    pause
    exit /b 1
)

rem ---- collect .diff files, newest first ----
set "COUNT=0"
for /f "delims=" %%F in ('dir /b /o:-d "%DIFF_DIR%\*.diff" 2^>nul') do (
    set /a COUNT+=1
    set "DIFF!COUNT!=%%F"
)

if "%COUNT%"=="0" (
    echo No .diff files found in:
    echo   %DIFF_DIR%
    echo Drop diff files there and run this script again.
    pause
    exit /b 0
)

echo Found %COUNT% diff file(s) in %DIFF_DIR%:
echo.
for /l %%I in (1,1,%COUNT%) do (
    echo   %%I^) !DIFF%%I!
    call :list_targets "%DIFF_DIR%\!DIFF%%I!"
)
echo.

set /p "CHOICE=Enter number to apply (0 to cancel): "
if "%CHOICE%"=="0" exit /b 0

set "SELECTED=!DIFF%CHOICE%!"
if "%SELECTED%"=="" (
    echo Invalid choice.
    pause
    exit /b 1
)

set "DIFF_PATH=%DIFF_DIR%\%SELECTED%"
echo.
echo Selected: %SELECTED%
echo Files this diff touches:
call :list_targets "%DIFF_PATH%"
echo.

rem ---- check targets against exclusion list ----
set "BLOCKED=0"
for /f "delims=" %%T in ('powershell -NoProfile -Command "Get-Content -LiteralPath '%DIFF_PATH%' | Where-Object { $_ -like '+++ b/*' } | ForEach-Object { $_.Substring(6) }"') do (
    set "TARGET=%%T"
    for /f "usebackq delims=" %%E in ("%EXCLUDE_FILE%") do (
        set "RULE=%%E"
        if not "!RULE!"=="" if not "!RULE:~0,1!"=="#" (
            if not "!TARGET:%%E=!"=="!TARGET!" (
                echo BLOCKED: "!TARGET!" matches exclude rule "%%E"
                set "BLOCKED=1"
            )
        )
    )
)

if "%BLOCKED%"=="1" (
    echo.
    echo This diff touches excluded files/folders - aborting.
    echo Edit %EXCLUDE_FILE% if this is intentional.
    pause
    exit /b 1
)

pushd "%PROJECT_ROOT%"

echo Checking if the diff applies cleanly...
git apply --check "%DIFF_PATH%"
if errorlevel 1 (
    echo.
    echo ERROR: diff does not apply cleanly to current files.
    echo The file may already be modified, or the diff is stale.
    popd
    pause
    exit /b 1
)

echo Diff is valid, applying...
git apply "%DIFF_PATH%"
if errorlevel 1 (
    echo ERROR while applying the diff.
    popd
    pause
    exit /b 1
)

echo.
echo Done! Changed files:
git diff --name-only
popd

move "%DIFF_PATH%" "%APPLIED_DIR%\%SELECTED%" >nul
echo.
echo Diff moved to: %APPLIED_DIR%\%SELECTED%
pause
exit /b 0

:list_targets
for /f "delims=" %%L in ('powershell -NoProfile -Command "Get-Content -LiteralPath '%~1' | Where-Object { $_ -like '+++ b/*' } | ForEach-Object { $_.Substring(6) }"') do (
    echo        - %%L
)
goto :eof
