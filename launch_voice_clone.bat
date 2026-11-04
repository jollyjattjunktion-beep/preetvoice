@echo off
setlocal
cd /d "%~dp0"

py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.11 was not found.
  echo Install Python 3.11 64-bit and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv-clone\Scripts\python.exe" (
  py -3.11 -m venv .venv-clone
)

".venv-clone\Scripts\python.exe" -m pip install --upgrade pip
".venv-clone\Scripts\python.exe" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
".venv-clone\Scripts\python.exe" -m pip install -r requirements-voice-clone.txt
".venv-clone\Scripts\python.exe" -m streamlit run voice_clone_app.py --server.port 8502

pause
