#!/usr/bin/env bash
# macOS 双击启动入口。
# 第一次运行会自动检测和安装依赖：
#   1) Python + Playwright + Chromium（约 200MB）
#   2) Node.js + 构建 inject.js（约 100MB，仅 entry.ts 改动后才重 build）
# 关闭：在终端窗口里按 Ctrl+C，或直接 ⌘+W。

cd "$(dirname "$0")"

cat <<'BANNER'

================================================================
   雀魂牌谱抓取 + 统计 — 本地 server
================================================================
浏览器会自动打开 http://127.0.0.1:9233/
要关掉服务就在这个窗口按  Ctrl + C
================================================================

BANNER

# ---------- 工具函数 ----------
need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "❌ 缺少命令: $1"
    echo "   $2"
    echo "按回车键关闭…"
    read -r _
    exit 1
  fi
}

# ---------- 1. Python ----------
need_cmd python3 "请先装 Python 3.9+：https://www.python.org/downloads/  或 brew install python"

# Playwright Python 包
if ! python3 -c "import playwright" 2>/dev/null; then
  echo "📦 首次启动：安装 Playwright Python 包…"
  python3 -m pip install --user --quiet playwright || {
    echo "❌ pip install playwright 失败"
    echo "按回车键关闭…"
    read -r _
    exit 1
  }
fi

# Playwright 的 Chromium
PW_BROWSERS="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"
if [ ! -d "$PW_BROWSERS" ] || [ -z "$(ls -A "$PW_BROWSERS" 2>/dev/null | grep -i chromium)" ]; then
  echo "📦 首次启动：下载 Playwright Chromium（约 170MB，几分钟）…"
  python3 -m playwright install chromium || {
    echo "❌ playwright install chromium 失败"
    echo "按回车键关闭…"
    read -r _
    exit 1
  }
fi

# ---------- 2. inject.js（按需 build） ----------
need_rebuild=0
if [ ! -f inject/dist/inject.js ]; then
  echo "📦 inject.js 不存在，需要构建…"
  need_rebuild=1
elif [ inject/src/entry.ts -nt inject/dist/inject.js ]; then
  echo "📦 inject/src/entry.ts 比 inject.js 新，需要重新构建…"
  need_rebuild=1
fi

if [ "$need_rebuild" = "1" ]; then
  need_cmd node "请先装 Node.js 20+：https://nodejs.org/  或 brew install node"
  need_cmd npm "Node.js 通常自带 npm，重装 Node.js 试试"

  if [ ! -d inject/node_modules ]; then
    echo "📦 首次构建：安装 npm 依赖（几十秒）…"
    (cd inject && npm install) || {
      echo "❌ npm install 失败"
      echo "按回车键关闭…"
      read -r _
      exit 1
    }
  fi

  echo "🔨 构建 inject.js…"
  (cd inject && npm run build) || {
    echo "❌ npm run build 失败"
    echo "按回车键关闭…"
    read -r _
    exit 1
  }
fi

# ---------- 3. 启动 server ----------
echo "🚀 启动 server…"
echo
python3 server.py
status=$?

echo
echo "================================================================"
if [ $status -eq 0 ]; then
  echo "server 正常退出。"
else
  echo "⚠️  server 异常退出 (exit code $status)，看上面的错误信息。"
fi
echo "按回车键关闭窗口…"
read -r _
