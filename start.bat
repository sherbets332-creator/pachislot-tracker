@echo off
cd /d "%~dp0"
echo Starting Pachislot Tracker...
echo From this PC:    http://localhost:5000/
echo From your phone: http://192.168.1.3:5000/
echo (Close this window or press Ctrl+C to stop)
venv\Scripts\python.exe run.py
pause
