@echo off
setlocal EnableDelayedExpansion

set "SRC=C:\XTTS Studio\engine"
set "DST=%USERPROFILE%\Desktop\XTTS_PY_TXT"

echo.
echo ============================================
echo      PY ^> TXT Converter
echo ============================================
echo.

if not exist "%SRC%" (
    echo Папка не найдена:
    echo %SRC%
    pause
    exit /b
)

if exist "%DST%" rd /s /q "%DST%"
mkdir "%DST%"

for /R "%SRC%" %%F in (*.py) do (
    set "FULL=%%~dpF"
    set "REL=!FULL:%SRC%\=!"

    if not exist "%DST%\!REL!" mkdir "%DST%\!REL!" >nul

    copy /Y "%%F" "%DST%\!REL!%%~nF.txt" >nul
    echo %%~fF
)

echo.
echo ============================================
echo Готово!
echo.
pause