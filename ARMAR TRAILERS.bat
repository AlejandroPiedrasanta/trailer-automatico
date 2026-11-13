@echo off
rem ? TRAILER AUTOMATICO (Windows) - doble clic para abrir el programa.
cd /d "%~dp0PROGRAMA"
python -c "import PySide6, librosa, PIL" 1>nul 2>nul || (
  echo Preparando el programa ^(solo la primera vez^)...
  python -m pip install --user -r config\requisitos.txt
)
start "" pythonw interfaz\trailer_xv.py
