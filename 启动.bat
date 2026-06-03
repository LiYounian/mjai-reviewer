@echo off
REM Windows 双击启动入口。会启 server.py 并自动打开浏览器。
REM 关闭：cmd 窗口右上角 X 或 Ctrl+C。
cd /d "%~dp0"
python server.py
pause
