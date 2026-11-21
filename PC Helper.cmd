@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\pythonw.exe" (
  echo Python environment not found. Install requirements into venv first.
  pause
  exit /b 1
)
if exist ".pc-helper-runtime\direct.json" (
  start "" "venv\Scripts\pythonw.exe" -X utf8 -m pc_remote.desktop --direct
) else (
  start "" "venv\Scripts\pythonw.exe" -X utf8 -m pc_remote.desktop --public
)
