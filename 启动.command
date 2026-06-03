#!/usr/bin/env bash
# macOS 双击启动入口。会启 server.py 并自动打开浏览器。
# 关闭：终端窗口 ⌘+Q 或 Ctrl+C。
set -e
cd "$(dirname "$0")"
exec python3 server.py
