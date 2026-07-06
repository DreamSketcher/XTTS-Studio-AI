@echo off
cd /d "%~dp0"
echo Zapusk cleanup_project.ps1 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0cleanup_project.ps1"
echo.
echo Kod vyhoda: %ERRORLEVEL%
pause