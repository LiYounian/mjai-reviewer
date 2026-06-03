"""单一职责：起 Playwright + 管 profile + 注入 inject.js。

不关心雀魂、协议、文件落盘。调用方拿到 BrowserContext 后自己用。
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import os
import stat

from playwright.sync_api import sync_playwright, BrowserContext

from src.config import get_profile_dir, PROJECT_ROOT as _PROJECT_ROOT

# inject.js 由 inject/ 子项目 esbuild 构建产生
INJECT_JS = _PROJECT_ROOT / "inject" / "dist" / "inject.js"


def _profile_has_login(profile_dir: Path) -> bool:
    """Profile 是否已经登录过雀魂。粗判：目录存在且非空。"""
    return profile_dir.exists() and any(profile_dir.iterdir())


def _ensure_profile_perms(profile_dir: Path) -> None:
    """Profile 含登录态，强制 chmod 700。"""
    profile_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(profile_dir, stat.S_IRWXU)


@contextmanager
def open_context(
    profile_dir: Path | None = None,
    headless: bool | None = None,
    inject_path: Path = INJECT_JS,
):
    if profile_dir is None:
        profile_dir = get_profile_dir()
    """开一个持久化 Chromium，注入 inject.js 到所有页面的 document_start。

    headless=None 时按 profile 是否有登录态自动选：未登录→headed（让用户扫码）；已登录→headless。
    """
    _ensure_profile_perms(profile_dir)
    if headless is None:
        headless = _profile_has_login(profile_dir)

    if not inject_path.exists():
        raise FileNotFoundError(
            f"inject.js 不存在: {inject_path}。先在 inject/ 下跑 `npm run build`。"
        )
    inject_code = inject_path.read_text(encoding="utf-8")

    with sync_playwright() as pw:
        ctx: BrowserContext = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            viewport={"width": 1280, "height": 800},
        )
        # init script 在每个 frame 的 document_start 执行，早于雀魂 Unity 启动
        ctx.add_init_script(inject_code)
        try:
            yield ctx
        finally:
            ctx.close()


def is_logged_in(profile_dir: Path | None = None) -> bool:
    return _profile_has_login(profile_dir or get_profile_dir())
