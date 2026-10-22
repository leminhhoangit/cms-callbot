@echo off
REM ============================================================
REM  Cap nhat du lieu TTHC cho callbot - chay hang thang
REM  Danh sach tinh can cap nhat: file tinh.txt (moi dong 1 ma, vd H19)
REM  Ket qua: thu muc out\   -  Nhat ky: thu muc logs\
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM --- tim Python ---
set "PY="
for %%P in (py.exe python.exe) do (
  if not defined PY (
    where %%P >nul 2>nul && set "PY=%%P"
  )
)
if not defined PY if exist "%USERPROFILE%\miniconda3\python.exe" set "PY=%USERPROFILE%\miniconda3\python.exe"
if not defined PY if exist "%USERPROFILE%\anaconda3\python.exe" set "PY=%USERPROFILE%\anaconda3\python.exe"
if not defined PY (
  echo [LOI] Khong tim thay Python. Cai Python tu https://www.python.org roi chay lai.
  exit /b 1
)

for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmm"') do set STAMP=%%d
set LOG=logs\capnhat_%STAMP%.log
echo ==== Bat dau %DATE% %TIME% (Python: %PY%) ==== > "%LOG%"

"%PY%" -m pip install --quiet --disable-pip-version-check requests openpyxl >> "%LOG%" 2>&1

set ERR=0
for /f "usebackq eol=# tokens=1" %%T in ("tinh.txt") do (
  echo. >> "%LOG%"
  echo ---- %%T ---- >> "%LOG%"
  "%PY%" scripts\update_tthc.py %%T >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo [LOI] %%T that bai - xem %LOG% >> "%LOG%"
    set ERR=1
  )
)
echo. >> "%LOG%"
echo ==== Ket thuc %DATE% %TIME% ==== >> "%LOG%"
type "%LOG%"
exit /b %ERR%
