@echo off
cd /d "%~dp0"
call venv\Scripts\activate
echo Starting TASKHUB Bot + Web Server...
start http://localhost:8000
python -m uvicorn bot.main:app --host 0.0.0.0 --port 8000 --reload
pause