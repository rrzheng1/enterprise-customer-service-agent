@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create a Python 3.11 virtual environment and install requirements.lock first. See docs/DEVELOPMENT.md.
  exit /b 1
)
echo Open http://127.0.0.1:8001/ in your browser.
".venv\Scripts\python.exe" scripts/run_dev.py --host 127.0.0.1 --port 8001 --no-reload
pause
