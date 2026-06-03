# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：把 server + viewer + inject + Playwright 打成单文件夹。

入口: server.py
模式: --onedir
产物: dist/mjai-tool/

⚠️ chromium 不在这里收 — 它是个完整 .app bundle (mac) / 目录 (win)，
PyInstaller 走 binary 流程会试图给里面所有 mach-O ad-hoc 重签，破坏 bundle。
所以 spec 只收 playwright 的 python + driver/node 部分，chromium 由 build.py
在 PyInstaller 完成后整目录 cp 进去（保 bundle 结构完整）。

运行时 server.py 自己会 export PLAYWRIGHT_BROWSERS_PATH=0，
让 playwright 在包内 (driver/package/.local-browsers/) 找 chromium。
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()

# Playwright python 包数据 - 不含 chromium .app
all_playwright_datas = collect_data_files("playwright", include_py_files=False)
playwright_datas = [
    (src, dst) for (src, dst) in all_playwright_datas
    if ".local-browsers" not in src.replace("\\", "/")
]
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
