"""本地打包脚本：产出 dist/mjai-tool/ 单目录可执行包。

用法:
  python3 build.py

步骤:
  1. 重新构建 inject/dist/inject.js（确保最新）
  2. 把 chromium 装进 playwright 包内 (PLAYWRIGHT_BROWSERS_PATH=0)
  3. 跑 pyinstaller mjai-tool.spec
  4. 报告产物大小

撞坑了？看 mjai-tool.spec 顶部注释 + dist/mjai-tool/ 试运行 stack trace。
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd, **kw):
    print(f"\n$ {' '.join(cmd) if isinstance(cmd, list) else cmd}", flush=True)
    kw.setdefault("cwd", ROOT)
    return subprocess.run(cmd, check=True, **kw)


def step_inject():
    print("\n=== 1/4 重建 inject.js ===")
    inject_dir = ROOT / "inject"
    if not (inject_dir / "node_modules").exists():
        run(["npm", "install"], cwd=inject_dir)
    run(["npm", "run", "build"], cwd=inject_dir)


def step_playwright():
    print("\n=== 2/4 装 chromium 到 playwright 包内 ===")
    # 让 chromium 装进 site-packages/playwright/driver/package/.local-browsers/
    # 这样 PyInstaller 的 collect_data_files('playwright') 能扫到
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    print("$ PLAYWRIGHT_BROWSERS_PATH=0 python3 -m playwright install chromium")
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
        env=env,
        cwd=ROOT,
    )


def step_pyinstaller():
    print("\n=== 3/4 PyInstaller 打包 ===")
    # 清干净旧 build artifacts
    for d in ("build", "dist"):
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)

    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "mjai-tool.spec"])


def step_slim():
    """瘦身：删 playwright 不必要的浏览器副本（headless_shell + ffmpeg）。"""
    print("\n=== 4/5 瘦身 ===")
    browsers = ROOT / "dist" / "mjai-tool" / "_internal" / "playwright" / "driver" / "package" / ".local-browsers"
    if not browsers.exists():
        print(f"   跳过：找不到 {browsers}")
        return
    saved = 0
    for sub in browsers.iterdir():
        name = sub.name
        # 只保留 chromium-XXXX；删 chromium_headless_shell（我们用 headed/headless 都走完整 chromium）和 ffmpeg
        if name.startswith("chromium_headless_shell") or name.startswith("ffmpeg"):
            sz = sum(p.stat().st_size for p in sub.rglob("*") if p.is_file())
            saved += sz
            shutil.rmtree(sub)
            print(f"   删 {name} ({sz / 1024 / 1024:.1f} MB)")
    if saved:
        print(f"   共省 {saved / 1024 / 1024:.1f} MB")


def step_report():
    print("\n=== 5/5 产物报告 ===")
    out_dir = ROOT / "dist" / "mjai-tool"
    if not out_dir.exists():
        print("❌ 找不到 dist/mjai-tool/")
        return

    total = 0
    for p in out_dir.rglob("*"):
        if p.is_file():
            total += p.stat().st_size

    mb = total / 1024 / 1024
    print(f"📦 产物目录: {out_dir}")
    print(f"   大小: {mb:.1f} MB ({total} bytes)")
    exe = out_dir / "mjai-tool"
    if exe.exists():
        print(f"   入口: {exe}")
        print(f"\n   测试运行: ./dist/mjai-tool/mjai-tool")


def main():
    t0 = time.time()
    step_inject()
    step_playwright()
    step_pyinstaller()
    step_slim()
    step_report()
    print(f"\n✅ 完成 (耗时 {time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
