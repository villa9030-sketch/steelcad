@echo off
rem SteelCAD: doppio clic per aprire. Un progetto si puo' trascinare su questo file.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" "app\main.py" %*
