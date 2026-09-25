@echo off
rem Double-click on Windows. Launches run.py.
cd /d "%~dp0"
where py >nul 2>&1 && (py -3 run.py & goto :end)
where python >nul 2>&1 && (python run.py & goto :end)
echo Python 3 not found. Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH").
:end
pause
