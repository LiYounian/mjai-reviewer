@echo off
REM Windows 双击启动入口。
REM 第一次运行会自动检测和安装依赖：
REM   1) Python + Playwright + Chromium（约 200MB）
REM   2) Node.js + 构建 inject.js（约 100MB，仅 entry.ts 改动后才重 build）
REM 关闭：cmd 窗口右上角 X 或 Ctrl+C。

setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ================================================================
echo    雀魂牌谱抓取 + 统计 - 本地 server
echo ================================================================
echo 浏览器会自动打开 http://127.0.0.1:9233/
echo 要关掉服务就在这个窗口按  Ctrl + C
echo ================================================================
echo.

REM ---------- 1. Python ----------
where python >nul 2>&1
if errorlevel 1 (
  echo [X] 缺少命令: python
  echo     请先装 Python 3.9+: https://www.python.org/downloads/
  pause
  exit /b 1
)

REM Playwright Python 包
python -c "import playwright" 2>nul
if errorlevel 1 (
  echo [+] 首次启动: 安装 Playwright Python 包...
  python -m pip install --user --quiet playwright
  if errorlevel 1 (
    echo [X] pip install playwright 失败
    pause
    exit /b 1
  )
)

REM Playwright 的 Chromium
set "PW_DIR=%LOCALAPPDATA%\ms-playwright"
if defined PLAYWRIGHT_BROWSERS_PATH set "PW_DIR=%PLAYWRIGHT_BROWSERS_PATH%"
dir "%PW_DIR%\chromium*" >nul 2>&1
if errorlevel 1 (
  echo [+] 首次启动: 下载 Playwright Chromium 约 170MB，几分钟...
  python -m playwright install chromium
  if errorlevel 1 (
    echo [X] playwright install chromium 失败
    pause
    exit /b 1
  )
)

REM ---------- 2. inject.js ----------
set NEED_REBUILD=0
if not exist inject\dist\inject.js (
  echo [+] inject.js 不存在，需要构建...
  set NEED_REBUILD=1
) else (
  REM entry.ts 比 inject.js 新就重 build。用 PowerShell 比时间戳。
  for /f %%i in ('powershell -nop -c "if ((Get-Item inject\src\entry.ts).LastWriteTime -gt (Get-Item inject\dist\inject.js).LastWriteTime) {1} else {0}"') do set NEED_REBUILD=%%i
  if "!NEED_REBUILD!"=="1" echo [+] inject\src\entry.ts 比 inject.js 新，需要重新构建...
)

if "!NEED_REBUILD!"=="1" (
  where node >nul 2>&1
  if errorlevel 1 (
    echo [X] 缺少命令: node
    echo     请先装 Node.js 20+: https://nodejs.org/
    pause
    exit /b 1
  )
  where npm >nul 2>&1
  if errorlevel 1 (
    echo [X] 缺少命令: npm  Node.js 通常自带 npm，重装 Node.js 试试
    pause
    exit /b 1
  )

  if not exist inject\node_modules (
    echo [+] 首次构建: 安装 npm 依赖几十秒...
    pushd inject
    call npm install
    set NPM_INSTALL_RC=!errorlevel!
    popd
    if !NPM_INSTALL_RC! neq 0 (
      echo [X] npm install 失败
      pause
      exit /b 1
    )
  )

  echo [+] 构建 inject.js...
  pushd inject
  call npm run build
  set NPM_BUILD_RC=!errorlevel!
  popd
  if !NPM_BUILD_RC! neq 0 (
    echo [X] npm run build 失败
    pause
    exit /b 1
  )
)

REM ---------- 3. 启动 server ----------
echo [^>] 启动 server...
echo.
python server.py
echo.
echo ================================================================
if errorlevel 1 (
  echo [!] server 异常退出，看上面的错误信息。
) else (
  echo server 正常退出。
)
pause
