@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY="C:\Users\wei\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist %PY% set PY=python
echo 正在启动 A股市场宽度看板...
start "" http://127.0.0.1:8730/
%PY% server.py
pause
