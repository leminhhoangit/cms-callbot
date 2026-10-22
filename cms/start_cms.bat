@echo off
REM ============================================================
REM  CMS du lieu Callbot TTHC - chay tren may nay: http://127.0.0.1:8780
REM  Lan dau: tu tao moi truong Python (.venv) va cai thu vien.
REM ============================================================
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
  echo Tao moi truong Python lan dau...
  py -m venv .venv || python -m venv .venv
  if errorlevel 1 ( echo [LOI] Khong tao duoc .venv - cai Python 3.11+ & pause & exit /b 1 )
)
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if not defined CMS_PORT set CMS_PORT=8780
start "" "http://127.0.0.1:%CMS_PORT%/"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %CMS_PORT%
