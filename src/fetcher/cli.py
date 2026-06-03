"""薄 CLI：参数解析，串起 browser / capture / export 三块。

支持多 URL：每局之间随机延迟，模拟人类间隔，**禁止短间隔批量**。
"""
from __future__ import annotations
import argparse
import random
import sys
import time

# tenhou_export 是纯 Python 无重依赖；browser/capture 依赖 playwright，延迟 import
from . import tenhou_export


def _sleep_jitter(lo: float, hi: float) -> None:
    """随机睡 [lo, hi] 秒，每秒打一行进度。"""
    secs = random.uniform(lo, hi)
    end = time.time() + secs
    print(f"[fetch] 随机延迟 {secs:.0f}s 后拉下一局…", flush=True)
    while True:
        remain = end - time.time()
        if remain <= 0:
            break
        time.sleep(min(remain, 5))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="fetch.py",
        description="拉取雀魂牌谱并存为天凤 json。首次跑会开窗扫码登录。",
    )
    p.add_argument(
        "urls",
        nargs="*",
        help="一个或多个牌谱链接/paipu id。多个时每局之间随机延迟。",
    )
    p.add_argument(
        "--headed",
        action="store_true",
        help="强制可见窗口（默认：已登录则无头，未登录则可见）",
    )
    p.add_argument(
        "--login-only",
        action="store_true",
        help="只开浏览器让你登录然后保存 profile，不抓牌谱",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="抓 fetchGameRecord 的超时秒数（默认 60）",
    )
    p.add_argument(
        "--delay-min",
        type=float,
        default=30.0,
        help="多 URL 时每局之间最小延迟秒数（默认 30）",
    )
    p.add_argument(
        "--delay-max",
        type=float,
        default=120.0,
        help="多 URL 时每局之间最大延迟秒数（默认 120）",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="即使本地已有同名 json 也重抓（默认跳过，避免不必要的请求）",
    )
    args = p.parse_args(argv)

    if args.delay_min < 0 or args.delay_max < args.delay_min:
        print("[fetch] --delay-max 必须 ≥ --delay-min ≥ 0", file=sys.stderr)
        return 2

    headless = False if args.headed else None
    from . import browser, capture

    if args.login_only:
        with browser.open_context(headless=False) as ctx:
            page = ctx.new_page()
            page.goto("https://game.maj-soul.com/1/")
            print("浏览器已打开。完成登录后回到这里按 Enter 关窗保存 profile。", flush=True)
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                pass
            page.close()
        return 0

    if not args.urls:
        print("[fetch] 至少需要一个牌谱链接（或 --login-only）", file=sys.stderr)
        return 2

    # 预解析 + 跳过已有
    from src.config import get_games_dir
    games_dir = get_games_dir()
    plan: list[tuple[str, str]] = []  # (url, paipu_id)
    for url in args.urls:
        pid = tenhou_export.parse_paipu_id(url)
        out_path = games_dir / f"{tenhou_export.safe_filename(pid)}.json"
        if out_path.exists() and not args.force:
            print(f"[fetch] skip {pid}: 已存在 {out_path}（用 --force 覆盖）", flush=True)
            continue
        plan.append((url, pid))

    if not plan:
        print("[fetch] 全部已存在，无事可做。", flush=True)
        return 0

    print(f"[fetch] 计划拉 {len(plan)} 局；profile already logged in: {browser.is_logged_in()}", flush=True)
    if len(plan) > 1:
        print(
            f"[fetch] 每局间随机延迟 [{args.delay_min:.0f}, {args.delay_max:.0f}]s，"
            f"避免触发雀魂风控（参考项目封号教训）。",
            flush=True,
        )

    # 第 1 局是冷启动（Unity 首次加载资源），明显比后续慢。给它额外 buffer。
    cold_timeout = max(args.timeout, args.timeout + 90)

    failures: list[tuple[str, Exception]] = []
    with browser.open_context(headless=headless) as ctx:
        for i, (url, pid) in enumerate(plan):
            if i > 0:
                _sleep_jitter(args.delay_min, args.delay_max)
            this_timeout = cold_timeout if i == 0 else args.timeout
            print(f"[fetch] [{i+1}/{len(plan)}] {pid} (timeout={this_timeout:.0f}s)", flush=True)
            try:
                res = capture.fetch_record(ctx, url, timeout_s=this_timeout)
                out = tenhou_export.write_tenhou(res["tenhou"], pid)
                raw_out = tenhou_export.write_majsoul_raw(res["majsoul"], pid)
                print(f"[fetch] [{i+1}/{len(plan)}] wrote tenhou: {out}", flush=True)
                print(f"[fetch] [{i+1}/{len(plan)}] wrote majsoul-raw: {raw_out}", flush=True)
            except Exception as e:
                print(f"[fetch] [{i+1}/{len(plan)}] FAIL: {e}", flush=True)
                failures.append((pid, e))

    if failures:
        print(f"[fetch] 完成，失败 {len(failures)}/{len(plan)}：", flush=True)
        for pid, e in failures:
            print(f"  - {pid}: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
