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
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Windows cmd 默认 cp1252 不能编码 emoji/中文，print 会 UnicodeEncodeError。
# 强制 stdout/stderr 走 UTF-8。Python 3.7+ 都支持。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
IS_WIN = platform.system() == "Windows"
# Windows 下 npm 实际是 npm.cmd，shell=True 让 PATHEXT 自己解析；mac/linux 直接走 npm
NPM = "npm.cmd" if IS_WIN else "npm"


def run(cmd, **kw):
    print(f"\n$ {' '.join(cmd) if isinstance(cmd, list) else cmd}", flush=True)
    kw.setdefault("cwd", ROOT)
    return subprocess.run(cmd, check=True, **kw)


def step_inject():
    print("\n=== 1/5 重建 inject.js ===")
    inject_dir = ROOT / "inject"
    if not (inject_dir / "node_modules").exists():
        run([NPM, "install"], cwd=inject_dir)
    run([NPM, "run", "build"], cwd=inject_dir)


def step_playwright():
    print("\n=== 2/5 装 chromium 到 playwright 包内 ===")
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
    print("\n=== 3/5 PyInstaller 打包 ===")
    # 清干净旧 build artifacts
    for d in ("build", "dist"):
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)

    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "mjai-tool.spec"])

    # PyInstaller 跳过了 chromium .app（spec 显式排除）。手动整目录复制进去，
    # 不让 PyInstaller 去重签里面的 mach-O — 那会破坏 .app bundle 结构。
    print("   📁 复制 chromium 到产物（绕过 PyInstaller 签名步骤）")
    import playwright as _pw
    src_browsers = Path(_pw.__file__).parent / "driver" / "package" / ".local-browsers"
    dst_browsers = ROOT / "dist" / "mjai-tool" / "_internal" / "playwright" / "driver" / "package" / ".local-browsers"
    if not src_browsers.exists():
        raise SystemError(f"找不到源 chromium 目录: {src_browsers}")
    dst_browsers.parent.mkdir(parents=True, exist_ok=True)
    if dst_browsers.exists():
        shutil.rmtree(dst_browsers)
    # symlinks=True 让 chromium 包内的软链照搬，bundle 不破
    shutil.copytree(src_browsers, dst_browsers, symlinks=True)
    print(f"   ✅ chromium 已复制到 {dst_browsers}")


def step_slim():
    """瘦身：删 playwright 不必要的浏览器副本（headless_shell + ffmpeg）。

    headless_shell 我们在 browser.py 里强制走 channel='chromium' 跳过；
    ffmpeg 是录视频用，我们用不到。
    """
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

    # 统计实际磁盘大小（去重硬链接）
    seen_inodes: set[int] = set()
    total = 0
    for p in out_dir.rglob("*"):
        if not p.is_file():
            continue
        st = p.stat()
        if not IS_WIN:
            # POSIX: 同 inode 的硬链接只计一次
            if st.st_ino in seen_inodes:
                continue
            seen_inodes.add(st.st_ino)
        total += st.st_size

    mb = total / 1024 / 1024
    print(f"📦 产物目录: {out_dir}")
    print(f"   大小: {mb:.1f} MB")
    exe_name = "mjai-tool.exe" if IS_WIN else "mjai-tool"
    exe = out_dir / exe_name
    if exe.exists():
        print(f"   入口: {exe}")


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
