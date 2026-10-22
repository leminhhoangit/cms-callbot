@echo off
REM API iCC GIA LAP (train callbot) - http://127.0.0.1:8790 . Chi de thu, KHONG phai bot that.
cd /d "%~dp0"
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m uvicorn mock_icc.app:app --host 127.0.0.1 --port 8790
