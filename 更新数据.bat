@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY="C:\Users\wei\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist %PY% set PY=python
echo 正在更新数据（约 1~3 分钟）...
%PY% update_daily.py
echo.
echo ---------- 当日简报 ----------
%PY% notify.py
echo.
pause
