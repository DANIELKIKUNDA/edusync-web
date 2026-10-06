@echo off
chcp 65001 >nul
title EduSync
cd /d "%~dp0..\.."
".venv\Scripts\python.exe" "tools\local\edusync_local.py" start %*
if errorlevel 1 (
  echo.
  echo   Le demarrage n'a pas abouti. Utilisez le raccourci "Journaux EduSync" pour le detail.
  pause
  exit /b 1
)
timeout /t 4 >nul