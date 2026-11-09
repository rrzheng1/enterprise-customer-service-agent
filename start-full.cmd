@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create a Python 3.11 virtual environment and install requirements.lock first. See README_CN.md.
  exit /b 1
)
".venv\Scripts\python.exe" scripts/run_full.py
pause
