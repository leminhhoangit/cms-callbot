@echo off
REM ============================================================
REM  Dang ky lich chay tu dong: 08:00 ngay 1 hang thang
REM  Chay file nay 1 lan (nhap dup chuot). Muon go lich: chay go_lich_tu_dong.bat
REM ============================================================
cd /d "%~dp0"
set TASK=TTHC Callbot - Cap nhat hang thang
schtasks /Create /TN "%TASK%" /TR "\"%~dp0capnhat_hang_thang.bat\"" /SC MONTHLY /D 1 /ST 08:00 /F
if errorlevel 1 (
  echo [LOI] Khong tao duoc lich. Thu chuot phai - Run as administrator.
  pause
  exit /b 1
)
REM Neu den gio ma may tat/ngu, se tu chay bu khi may bat lai; chay tren pin cung duoc
powershell -NoProfile -Command "$t=Get-ScheduledTask -TaskName '%TASK%'; $t.Settings.StartWhenAvailable=$true; $t.Settings.DisallowStartIfOnBatteries=$false; $t.Settings.StopIfGoingOnBatteries=$false; $t.Settings.ExecutionTimeLimit='PT4H'; Set-ScheduledTask -InputObject $t | Out-Null"
echo.
echo Da dat lich: 08:00 ngay 1 hang thang  ^(ten lich: %TASK%^)
schtasks /Query /TN "%TASK%" /FO LIST | findstr /i "TaskName Next Status"
echo.
echo Muon chay thu ngay bay gio: nhap dup capnhat_hang_thang.bat
pause
