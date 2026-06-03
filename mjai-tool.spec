# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：把 server + viewer + inject + Playwright + Chromium 打成单文件夹。

入口: server.py
模式: --onedir (打成目录而非 onefile，因为 chromium 是数据文件不能压成 exe)
产物: dist/mjai-tool/

关键点:
- Playwright 默认从 ~/Library/Caches/ms-playwright/ 找 chromium，PyInstaller 看不到。
  build.py 会先 export PLAYWRIGHT_BROWSERS_PATH=0 重装 chromium 进 playwright 包内，
  spec 这里的 collect_data_files('playwright') 才能把它一起带走。
- 运行时 server.py 自己会 export PLAYWRIGHT_BROWSERS_PATH=0，让打包后的 playwright 找包内的 chromium。
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()

# Playwright 包数据：driver/、bundled chromium（PLAYWRIGHT_BROWSERS_PATH=0 时装在这里）
playwright_datas = collect_data_files("playwright", include_py_files=False)
playwright_hidden = collect_submodules("playwright")

# 项目内静态资源
project_datas = [
    (str(SPEC_DIR / "viewer.html"), "."),
    (str(SPEC_DIR / "inject" / "dist" / "inject.js"), "inject/dist"),
]

a = Analysis(
    ["server.py"],
    pathex=[str(SPEC_DIR)],
    binaries=[],
    datas=playwright_datas + project_datas,
    hiddenimports=playwright_hidden + [
        "src.config",
        "src.fetcher.browser",
        "src.fetcher.capture",
        "src.fetcher.cli",
        "src.fetcher.tenhou_export",
        "src.parser.localize",
        "src.parser.tenhou",
        "src.parser.tiles",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mjai-tool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # upx 会让 chromium / .so 启动慢/坏，关掉
    console=True,    # server 需要终端输出日志
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="mjai-tool",
)
