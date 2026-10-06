@echo off
chcp 65001 >nul
title Arreter EduSync
cd /d "%~dp0..\.."
".venv\Scripts\python.exe" "tools\local\edusync_local.py" stop
timeout /t 4 >nul