@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title XTTS ENGINE — AUTO ENV FINDER
color 0A

:: ==========================================
:: РУЧНОЙ ПУТЬ К ПРОЕКТУ (самый надёжный способ)
:: Впишите сюда полный путь к папке проекта (где лежит python\runtime\).
:: Если оставить пустым (""), скрипт попробует определить путь автоматически.
:: ==========================================
set "MANUAL_BASE="
:: Пример: set "MANUAL_BASE=C:\XTTS Studio\"

if not "%MANUAL_BASE%"=="" (
    set "BASE=%MANUAL_BASE%"
) else if defined b2eprogrampathname (
    set "BASE=%b2eprogrampathname%\"
) else (
    set "BASE=%~dp0"
)
cd /d "%BASE%"

:: ==========================================
:: ОКРУЖЕНИЕ: python\runtime\python.exe — реальный интерпретатор.
:: xtts_env\python.exe — ПУСТЫШКА, никогда не запускается.
:: Из xtts_env подхватываются только тяжёлые библиотеки через PYTHONPATH.
:: ==========================================
set "SITE_PACKAGES=%BASE%python\xtts_env\Lib\site-packages"
if not exist "%SITE_PACKAGES%" mkdir "%SITE_PACKAGES%" 2>nul
set "PYTHONPATH=%SITE_PACKAGES%"

echo ==================================================
echo        XTTS DIAGNOSTIC
echo        PORTABLE AUTO ENV FINDER
echo ==================================================
echo.
echo PYTHONPATH = %PYTHONPATH%
echo.

set "PRIMARY_PY=%BASE%python\runtime\python.exe"
set "CACHE_FILE=%BASE%env_cache.cfg"
set "BEST_PY="
set "BEST_SCORE=-999"
set "FOUND_COUNT=0"

:: ==========================================
:: 0. КЭШ — если уже находили рабочее окружение раньше
:: ==========================================
if exist "%CACHE_FILE%" (
    set "CACHED_PY="
    set /p CACHED_PY=<"%CACHE_FILE%"
    if exist "!CACHED_PY!" (
        echo [КЭШ] Проверяю сохранённое окружение: !CACHED_PY!
        call :SCAN "!CACHED_PY!"
        if not "!BEST_PY!"=="" (
            echo ✔ Кэш валиден, сканирование пропущено.
            goto ENV_READY
        )
    )
    echo ⚠ Сохранённое окружение больше не работает, ищу заново...
    echo.
)

:: ==========================================
:: 1. БЫСТРАЯ ПРОВЕРКА — известный путь проекта
:: ==========================================
if exist "%PRIMARY_PY%" (
    echo [БЫСТРАЯ ПРОВЕРКА] %PRIMARY_PY%
    call :SCAN "%PRIMARY_PY%"
    if not "!BEST_PY!"=="" (
        echo ✔ Основное окружение рабочее, полное сканирование пропущено.
        goto ENV_READY
    )
    echo   ⚠ Основной python.exe не прошёл проверку, запускаю полное сканирование...
    echo.
) else (
    echo ⚠ Основной путь не найден: %PRIMARY_PY%
    echo   Запускаю полное сканирование проекта...
    echo.
)

:: ==========================================
:: 2. ПОЛНОЕ СКАНИРОВАНИЕ (fallback, если быстрый путь сломан)
:: ==========================================
echo [SCANNING PROJECT FOR ALL python.exe...]
echo ------------------------------------------

if exist "%BASE%.venv\Scripts\python.exe" call :SCAN "%BASE%.venv\Scripts\python.exe"
if exist "%BASE%venv\Scripts\python.exe" call :SCAN "%BASE%venv\Scripts\python.exe"

for /r "%BASE%" %%F in (python.exe) do (
    if %%~zF GTR 0 (
        set /a FOUND_COUNT+=1
        call :SCAN "%%F"
    )
)

where python >nul 2>&1 && (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        call :SCAN "%%P"
    )
)

echo.
echo ------------------------------------------
echo Found executables: %FOUND_COUNT%
echo ------------------------------------------
echo.

:ENV_READY
if "%BEST_PY%"=="" (
    echo ❌ НЕТ НИ ОДНОГО РАБОЧЕГО Python окружения!
    echo    Установите Python или запустите REPAIR.
    pause
    exit /b 1
)

echo ✔ ЛУЧШЕЕ ОКРУЖЕНИЕ:
echo   %BEST_PY%
echo   SCORE: %BEST_SCORE%
echo ==================================================
echo.

set "PY=%BEST_PY%"
> "%CACHE_FILE%" echo %BEST_PY%

:: ==========================================
:: CORE CHECK
:: ==========================================
echo [ПРОВЕРКА ЗАВИСИМОСТЕЙ]  (PYTHONPATH = %PYTHONPATH%)
echo ------------------------------------------
"%PY%" -c "import sys; print('  python:        ', sys.version.split()[0], '|', sys.executable)"
"%PY%" -c "import torch; print('  torch:         ', torch.__version__)" 2>nul || echo   ❌ torch        MISSING
"%PY%" -c "from TTS import __version__; print('  TTS:            OK')" 2>nul || echo   ❌ TTS           MISSING
"%PY%" -c "import customtkinter; print('  customtkinter: ', customtkinter.__version__)" 2>nul || echo   ❌ customtkinter MISSING
"%PY%" -c "import tkinterdnd2; print('  tkinterdnd2:    OK')" 2>nul || echo   ❌ tkinterdnd2   MISSING
"%PY%" -c "import pygame; print('  pygame:        ', pygame.__version__)" 2>nul || echo   ❌ pygame        MISSING
"%PY%" -c "import PIL; print('  Pillow:        ', PIL.__version__)" 2>nul || echo   ❌ Pillow         MISSING
"%PY%" -c "import llama_cpp; print('  llama_cpp:      OK')" 2>nul || echo   ❌ llama_cpp     MISSING
echo.

:: ==========================================
:: МЕНЮ
:: ==========================================
:MAIN
echo ==================================================
echo  [1] БЫСТРЫЙ СТАРТ (свёрнуто, как в проде)
echo  [2] ОТЛАДОЧНЫЙ СТАРТ (с консолью, видны ошибки)
echo  [3] ГЛУБОКИЙ ОТЧЁТ (sys.path, site-packages)
echo  [4] DEBUG окружения
echo  [5] REPAIR — установить зависимости
echo  [6] СМЕНИТЬ окружение вручную
echo  [7] ОЧИСТИТЬ кэш и пересканировать
echo  [8] ВОССТАНОВИТЬ файлы приложения с GitHub
echo  [0] ВЫХОД
echo ==================================================
echo.
set /p MODE=Выбор: 
if "%MODE%"=="1" goto START_FAST
if "%MODE%"=="2" goto START_DEBUG
if "%MODE%"=="3" goto DEEP
if "%MODE%"=="4" goto DEBUG
if "%MODE%"=="5" goto REPAIR
if "%MODE%"=="6" goto MANUAL
if "%MODE%"=="7" goto CLEARCACHE
if "%MODE%"=="8" goto FORCE_UPDATE
if "%MODE%"=="0" exit /b 0
goto MAIN

:: ==========================================
:: ПРИНУДИТЕЛЬНОЕ ВОССТАНОВЛЕНИЕ С GITHUB
:: ==========================================
:FORCE_UPDATE
echo.
echo ===== ВОССТАНОВЛЕНИЕ ФАЙЛОВ ПРИЛОЖЕНИЯ =====
echo.
echo Это перекачает все файлы из репозитория заново
echo (поверх текущих), независимо от версии.
echo.
set /p CONFIRM=Продолжить? (y/n): 
if /I not "%CONFIRM%"=="y" goto MAIN
echo.

set "TMP_PY=%TEMP%\xtts_force_update.py"
set "BASE_NOSLASH=%BASE:~0,-1%"

> "%TMP_PY%" echo import sys, io
>>"%TMP_PY%" echo sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
>>"%TMP_PY%" echo sys.path.insert(0, r"%BASE_NOSLASH%")
>>"%TMP_PY%" echo from engine.updater import get_remote_version_info, apply_update
>>"%TMP_PY%" echo info = get_remote_version_info()
>>"%TMP_PY%" echo files = info.get("files", [])
>>"%TMP_PY%" echo print("Найдено файлов: %%d, качаю..." %% len(files))
>>"%TMP_PY%" echo def _cb(i, t):
>>"%TMP_PY%" echo     print("  %%d/%%d" %% (i, t))
>>"%TMP_PY%" echo ok = apply_update(files, progress_callback=_cb)
>>"%TMP_PY%" echo print("[OK] Готово" if ok else "[WARN] Часть файлов не удалось скачать - см. лог выше")

"%PY%" "%TMP_PY%"
del /q "%TMP_PY%" >nul 2>&1

echo.
echo Файлы обновлены. Перезапуск диагностики...
echo.
pause

start "" "%~f0"
exit /b 0

:: ==========================================
:: SCORING ENGINE
:: ==========================================
:SCAN
set "_F=%~1"
set "_SZ=%~z1"
set "_SCORE=0"

if "%_SZ%"=="0" exit /b

:: xtts_env\python.exe — пустышка, никогда не используется как интерпретатор
echo "%_F%" | findstr /I "\\xtts_env\\" >nul 2>&1 && (
    echo   Skipping: %_F%  [пустышка xtts_env, не кандидат]
    exit /b
)

echo   Testing: %_F%

"%_F%" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo             → не запускается, пропуск
    exit /b
)

:: Базовый балл за любой работающий Python
set /a _SCORE+=10

:: Версия Python — предпочитаем 3.8-3.13
"%_F%" -c "import sys; v=sys.version_info; exit(0 if (v.major==3 and v.minor>=8) else 1)" >nul 2>&1
if not errorlevel 1 set /a _SCORE+=20

:: torch (самый важный для XTTS)
"%_F%" -c "import torch" >nul 2>&1 && set /a _SCORE+=50

:: TTS
"%_F%" -c "from TTS import __version__" >nul 2>&1 && set /a _SCORE+=40

:: customtkinter
"%_F%" -c "import customtkinter" >nul 2>&1 && set /a _SCORE+=10

:: tkinterdnd2
"%_F%" -c "import tkinterdnd2" >nul 2>&1 && set /a _SCORE+=10

:: pygame
"%_F%" -c "import pygame" >nul 2>&1 && set /a _SCORE+=5

:: Pillow
"%_F%" -c "import PIL" >nul 2>&1 && set /a _SCORE+=5

:: Бонус за python\runtime — актуальный целевой интерпретатор проекта
echo "%_F%" | findstr /I "\\python\\runtime\\" >nul 2>&1 && set /a _SCORE+=30

echo             → score: %_SCORE%

if %_SCORE% GTR %BEST_SCORE% (
    set "BEST_SCORE=%_SCORE%"
    set "BEST_PY=%_F%"
)
exit /b

:: ==========================================
:: FAST START (свёрнуто)
:: ==========================================
:START_FAST
echo.
echo [ЗАПУСК gui.py свёрнуто через: %PY%]
start "XTTS Studio" /min "%PY%" "%BASE%gui.py"
echo Запущено в фоне.
echo.
pause
goto MAIN

:: ==========================================
:: DEBUG START (с консолью)
:: ==========================================
:START_DEBUG
echo.
echo [ЗАПУСК gui.py с консолью через: %PY%]
echo.
"%PY%" "%BASE%gui.py"
echo.
echo [gui.py завершился]
pause
goto MAIN

:: ==========================================
:: DEEP REPORT
:: ==========================================
:DEEP
echo.
echo ===== ГЛУБОКИЙ ОТЧЁТ =====
echo.
echo Активное окружение:
echo   %PY%
echo.
echo PYTHONPATH:
echo   %PYTHONPATH%
echo.
echo Python версия:
"%PY%" -c "import sys; print(' ', sys.version)"
echo.
echo sys.executable:
"%PY%" -c "import sys; print(' ', sys.executable)"
echo.
echo sys.path (включая PYTHONPATH):
"%PY%" -c "import sys; [print(' ', p) for p in sys.path]"
echo.
echo Топ установленных пакетов:
"%PY%" -m pip list --format=columns 2>nul | findstr /I "torch TTS custom tkinter pygame pillow numpy"
echo.
pause
goto MAIN

:: ==========================================
:: DEBUG
:: ==========================================
:DEBUG
echo.
echo ===== ENGINE DEBUG =====
echo.
echo Python:
"%PY%" -c "import sys; print(sys.executable, '|', sys.version)"
echo.
echo PYTHONPATH:
echo   %PYTHONPATH%
echo.
echo torch:
"%PY%" -c "import torch; print(torch.__version__, '| CUDA:', torch.cuda.is_available())" 2>nul || echo   missing
echo.
echo TTS:
"%PY%" -c "from TTS import __version__; print(__version__)" 2>nul || echo   missing
echo.
echo Все python.exe найденные в проекте (размер ^> 0):
for /r "%BASE%" %%F in (python.exe) do (
    if %%~zF GTR 0 echo   %%F  [%%~zF bytes]
)
echo.
echo Пустышки (size = 0):
for /r "%BASE%" %%F in (python.exe) do (
    if %%~zF EQU 0 echo   %%F  [ПУСТЫШКА — 0 bytes]
)
pause
goto MAIN

:: ==========================================
:: REPAIR
:: ==========================================
:REPAIR
echo.
echo ===== REPAIR MODE =====
echo Окружение: %PY%
echo Зависимости ставятся в xtts_env (через PYTHONPATH = %PYTHONPATH%)
echo.
set /p CONFIRM=Установить/обновить зависимости? (y/n): 
if /I not "%CONFIRM%"=="y" goto MAIN
echo.
echo [pip upgrade...]
"%PY%" -m pip install --upgrade pip --target "%BASE%python\xtts_env\Lib\site-packages"
echo.
echo [core deps...]
"%PY%" -m pip install -r "%BASE%requirements.txt" --target "%BASE%python\xtts_env\Lib\site-packages"
echo.
echo [torch (CPU, если нет GPU)...]
"%PY%" -c "import torch" >nul 2>&1 || (
    "%PY%" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --target "%BASE%python\xtts_env\Lib\site-packages"
)
echo.
echo Готово. Перезапустите батник для проверки.
pause
goto MAIN

:: ==========================================
:: РУЧНОЙ ВЫБОР
:: ==========================================
:MANUAL
echo.
echo ===== ВЫБОР ОКРУЖЕНИЯ ВРУЧНУЮ =====
echo.
echo Найденные рабочие python.exe:
echo.
set "_IDX=0"
for /r "%BASE%" %%F in (python.exe) do (
    if %%~zF GTR 0 (
        echo "%%F" | findstr /I "\\xtts_env\\" >nul 2>&1 || (
            set /a _IDX+=1
            echo   [!_IDX!] %%F  [%%~zF bytes]
        )
    )
)
echo.
echo Введите полный путь к python.exe вручную:
set /p MANUAL_PY=Path: 
if exist "%MANUAL_PY%" (
    set "PY=%MANUAL_PY%"
    > "%CACHE_FILE%" echo %MANUAL_PY%
    echo ✔ Окружение сменено на: %MANUAL_PY%
) else (
    echo ❌ Файл не найден: %MANUAL_PY%
)
echo.
pause
goto MAIN

:: ==========================================
:: ОЧИСТКА КЭША
:: ==========================================
:CLEARCACHE
if exist "%CACHE_FILE%" del /q "%CACHE_FILE%"
echo ✔ Кэш очищен. Перезапустите батник для полного пересканирования.
echo.
pause
exit /b 0
