"""本地 HTTP server，给 viewer.html 提供"抓取/管理"能力。

设计原则:
- 仅监听 127.0.0.1，绝不公网暴露（账号互串风险）
- 单进程单线程顺序抓，复用现有 src/fetcher 的 browser/capture 模块
- 抓取进度走 SSE 流式返回；UI 实时显示
- 任何时候只允许一个抓取任务在跑

用法:
  python3 server.py                # 默认端口 9233，自动开浏览器
  python3 server.py --no-browser   # 不自动开浏览器
  python3 server.py --port 12345   # 自定端口
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import queue
import random
import re
import signal
import socket
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Playwright 在 frozen 包里要找 chromium：让它走我们打进包内的 playwright/driver/.../chrome-mac/
# 必须在 import playwright 之前 set
if getattr(sys, "frozen", False):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

from src.config import (  # noqa: E402
    PROJECT_ROOT, RESOURCE_ROOT, USER_DATA_ROOT,
    get_data_dir, get_games_dir, get_raw_dir,
    set_data_dir, ensure_dirs, load_config,
)

VIEWER_HTML = RESOURCE_ROOT / "viewer.html"

# 全局抓取任务状态。任何时刻只有 0 或 1 个 fetch 任务。
_FETCH_LOCK = threading.Lock()
_CURRENT_TASK = None  # type: dict | None


# ============================================================
# 抓取任务（在后台线程跑，SSE 流推进度）
# ============================================================

class FetchTask:
    """一次抓取任务：包含 URL 列表 + 延迟参数 + SSE 订阅队列。"""

    def __init__(self, urls, delay_min, delay_max, force):
        self.urls = urls
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.force = force
        self.events = queue.Queue()  # type: queue.Queue
        self.done = False
        self.subscribers = []  # 多路 SSE 订阅
        self._lock = threading.Lock()

    def emit(self, kind, payload):
        """向所有订阅者推一条事件。"""
        evt = {"kind": kind, "payload": payload, "ts": time.time()}
        with self._lock:
            subs = list(self.subscribers)
        for sub in subs:
            try:
                sub.put_nowait(evt)
            except Exception:
                pass

    def subscribe(self):
        q = queue.Queue()
        with self._lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self.subscribers:
                self.subscribers.remove(q)


def _run_fetch(task: FetchTask):
    """实际跑抓取。在后台线程里调用。"""
    global _CURRENT_TASK
    try:
        # 这里才 import playwright，避免无 fetch 需求时启动开销
        from src.fetcher import browser, capture, tenhou_export

        # 解析 + 跳过已存在
        # 用户粘贴的可能是: "雀魂牌谱:https://...", "https://...", "paipu=...", 裸 ID 任一种。
        # 全部归一为牌谱 ID，再拼回标准 URL 喂给 playwright，避免 goto 收到脏字符串。
        plan = []
        for raw in task.urls:
            try:
                pid = tenhou_export.extract_paipu_id(raw)
            except Exception as e:
                task.emit("log", f"❌ 链接无法识别: {raw} ({e})")
                continue
            url = tenhou_export.url_for(pid)
            out_path = get_games_dir() / f"{tenhou_export.safe_filename(pid)}.json"
            if out_path.exists() and not task.force:
                task.emit("log", f"⏭ 跳过 {pid}（已抓过，要重抓请勾'强制重抓'）")
                continue
            plan.append((url, pid))

        task.emit("log", f"📋 计划抓 {len(plan)} 局；登录态: {'✅ 已登录' if browser.is_logged_in() else '❌ 未登录（会开窗扫码）'}")
        if not plan:
            task.emit("log", "✅ 全部已存在，无事可做。")
            task.emit("done", {"ok": True, "wrote": [], "failed": []})
            return

        if len(plan) > 1:
            task.emit("log", f"⏱  每局间随机延迟 [{task.delay_min:.0f}, {task.delay_max:.0f}]s，避免触发风控")

        cold_timeout = 150.0  # 第一局冷启动给足
        wrote = []
        failed = []

        with browser.open_context(headless=None) as ctx:
            for i, (url, pid) in enumerate(plan):
                if i > 0:
                    secs = random.uniform(task.delay_min, task.delay_max)
                    task.emit("log", f"⏱  延迟 {secs:.0f}s 后抓下一局…")
                    end = time.time() + secs
                    while time.time() < end:
                        time.sleep(min(end - time.time(), 1))

                this_timeout = cold_timeout if i == 0 else 60.0
                task.emit("progress", {"index": i + 1, "total": len(plan), "pid": pid})
                task.emit("log", f"🎯 [{i+1}/{len(plan)}] 抓 {pid} (timeout {this_timeout:.0f}s)")
                try:
                    res = capture.fetch_record(ctx, url, timeout_s=this_timeout)
                    out = tenhou_export.write_tenhou(res["tenhou"], pid)
                    raw_out = tenhou_export.write_majsoul_raw(res["majsoul"], pid)
                    task.emit("log", f"✅ [{i+1}/{len(plan)}] 天凤格式: {out}")
                    task.emit("log", f"   📦 雀魂原始: {raw_out}")
                    wrote.append({"pid": pid, "path": str(out), "raw": str(raw_out)})
                except Exception as e:
                    task.emit("log", f"❌ [{i+1}/{len(plan)}] 失败: {e}")
                    failed.append({"pid": pid, "error": str(e)})

        task.emit("done", {"ok": len(failed) == 0, "wrote": wrote, "failed": failed})
    except Exception as e:
        task.emit("log", f"💥 任务崩溃: {e}\n{traceback.format_exc()}")
        task.emit("done", {"ok": False, "error": str(e)})
    finally:
        task.done = True
        with _FETCH_LOCK:
            if _CURRENT_TASK is task:
                _CURRENT_TASK = None


# ============================================================
# 登录任务（独立路径：开 headed 浏览器，用户扫码后停在那里）
# ============================================================

_LOGIN_THREAD = None  # type: threading.Thread | None
_LOGIN_STATE = {"running": False, "msg": ""}


def _run_login():
    global _LOGIN_STATE
    _LOGIN_STATE = {"running": True, "msg": "浏览器已打开，请在窗口里登录雀魂；登录后点'我已登录完成'按钮"}
    try:
        from src.fetcher import browser
        # 一直阻塞到外部信号；用一个全局事件
        from playwright.sync_api import sync_playwright

        # 直接用 browser.open_context 并保持打开，等待事件
        # 简化做法：起 playwright，开 page，goto 雀魂主页，等 _LOGIN_DONE_EVENT 后关
        with browser.open_context(headless=False) as ctx:
            page = ctx.new_page()
            try:
                page.goto("https://game.maj-soul.com/1/", wait_until="domcontentloaded")
            except Exception as e:
                _LOGIN_STATE["msg"] = f"打开雀魂失败: {e}"
            _LOGIN_DONE_EVENT.wait()
            try:
                page.close()
            except Exception:
                pass
        _LOGIN_STATE = {"running": False, "msg": "登录态已保存（如确认登录成功）"}
    except Exception as e:
        _LOGIN_STATE = {"running": False, "msg": f"登录流程异常: {e}"}
    finally:
        _LOGIN_DONE_EVENT.clear()


_LOGIN_DONE_EVENT = threading.Event()


# ============================================================
# HTTP handler
# ============================================================

class Handler(BaseHTTPRequestHandler):

    # 关掉默认 stderr 噪声
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")

    # ---- 工具 ----
    def _send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_body_json(self):
        try:
            ln = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            ln = 0
        if ln <= 0:
            return {}
        raw = self.rfile.read(ln)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # ---- 路由 ----
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path

        if p == "/" or p == "/viewer.html":
            self._send_file(VIEWER_HTML, "text/html; charset=utf-8")
            return

        if p == "/api/games":
            self._handle_list_games()
            return

        if p == "/api/games/raw":
            qs = parse_qs(u.query)
            ref = qs.get("ref", [""])[0]
            self._handle_get_raw(ref)
            return

        if p == "/api/login/status":
            self._send_json(200, _LOGIN_STATE)
            return

        if p == "/api/fetch/stream":
            self._handle_fetch_stream()
            return

        if p == "/api/status":
            self._send_json(200, {
                "current_task": None if _CURRENT_TASK is None else {
                    "running": not _CURRENT_TASK.done,
                    "urls": len(_CURRENT_TASK.urls),
                },
                "logged_in": self._is_logged_in(),
            })
            return

        if p == "/api/config":
            self._send_json(200, {
                "data_dir": str(get_data_dir()),
                "games_dir": str(get_games_dir()),
                "raw_dir": str(get_raw_dir()),
                "raw": load_config(),  # 原始 config 内容（可能为空）
            })
            return

        self.send_error(404)

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/login":
            self._handle_login_start()
            return
        if p == "/api/login/done":
            self._handle_login_done()
            return
        if p == "/api/fetch":
            self._handle_fetch_start()
            return
        if p == "/api/config":
            self._handle_set_config()
            return
        self.send_error(404)

    def do_DELETE(self):
        u = urlparse(self.path)
        if u.path.startswith("/api/games/"):
            ref = u.path[len("/api/games/"):]
            self._handle_delete_game(ref)
            return
        self.send_error(404)

    # ---- 业务 ----
    def _is_logged_in(self) -> bool:
        try:
            from src.fetcher import browser
            return browser.is_logged_in()
        except Exception:
            return False

    def _handle_list_games(self):
        if not get_games_dir().exists():
            self._send_json(200, {"games": []})
            return
        items = []
        for f in sorted(get_games_dir().glob("*.json")):
            try:
                st = f.stat()
                items.append({
                    "ref": f.stem,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                })
            except Exception:
                pass
        self._send_json(200, {"games": items})

    def _handle_get_raw(self, ref: str):
        if not ref or "/" in ref or ".." in ref:
            self.send_error(400)
            return
        path = get_games_dir() / f"{ref}.json"
        if not path.exists():
            self.send_error(404)
            return
        self._send_file(path, "application/json; charset=utf-8")

    def _handle_delete_game(self, ref: str):
        if not ref or "/" in ref or ".." in ref:
            self.send_error(400)
            return
        path = get_games_dir() / f"{ref}.json"
        if not path.exists():
            self.send_error(404)
            return
        try:
            path.unlink()
            self._send_json(200, {"deleted": ref})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _handle_set_config(self):
        body = self._read_body_json()
        new_dir = (body.get("data_dir") or "").strip()
        if not new_dir:
            self._send_json(400, {"error": "data_dir 必填"})
            return
        try:
            resolved = set_data_dir(new_dir)
            self._send_json(200, {
                "ok": True,
                "data_dir": str(resolved),
                "games_dir": str(get_games_dir()),
                "raw_dir": str(get_raw_dir()),
            })
        except Exception as e:
            self._send_json(500, {"error": f"无法设置 data_dir: {e}"})

    def _handle_login_start(self):
        global _LOGIN_THREAD
        if _LOGIN_STATE["running"]:
            self._send_json(409, {"error": "已有登录窗口在运行"})
            return
        _LOGIN_DONE_EVENT.clear()
        _LOGIN_THREAD = threading.Thread(target=_run_login, daemon=True)
        _LOGIN_THREAD.start()
        # 给一点时间让线程把 state 标 running
        time.sleep(0.1)
        self._send_json(200, _LOGIN_STATE)

    def _handle_login_done(self):
        if not _LOGIN_STATE["running"]:
            self._send_json(409, {"error": "没有进行中的登录"})
            return
        _LOGIN_DONE_EVENT.set()
        self._send_json(200, {"signaled": True})

    def _handle_fetch_start(self):
        global _CURRENT_TASK
        body = self._read_body_json()
        urls = body.get("urls", [])
        if not isinstance(urls, list) or not urls:
            self._send_json(400, {"error": "urls 必填且为非空数组"})
            return

        delay_min = float(body.get("delay_min", 30))
        delay_max = float(body.get("delay_max", 120))
        force = bool(body.get("force", False))

        # 红线：不允许 < 30 秒
        if delay_min < 30:
            self._send_json(400, {"error": "delay_min 不能小于 30 秒（封号红线）"})
            return
        if delay_max < delay_min:
            self._send_json(400, {"error": "delay_max 必须 ≥ delay_min"})
            return

        with _FETCH_LOCK:
            if _CURRENT_TASK is not None and not _CURRENT_TASK.done:
                self._send_json(409, {"error": "已有抓取任务在运行"})
                return
            task = FetchTask(urls, delay_min, delay_max, force)
            _CURRENT_TASK = task

        threading.Thread(target=_run_fetch, args=(task,), daemon=True).start()
        self._send_json(200, {"started": True, "total": len(urls)})

    def _handle_fetch_stream(self):
        """SSE: 把当前任务的进度事件流式推到客户端。客户端断线会自动从 subscribers 移除。"""
        task = _CURRENT_TASK
        if task is None:
            self.send_error(404, "没有进行中的任务")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        q = task.subscribe()
        try:
            while True:
                try:
                    evt = q.get(timeout=15)
                except queue.Empty:
                    # 心跳防止代理断流
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    if task.done:
                        break
                    continue
                line = f"event: {evt['kind']}\ndata: {json.dumps(evt['payload'], ensure_ascii=False)}\n\n"
                try:
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
                if evt["kind"] == "done":
                    break
        finally:
            task.unsubscribe(q)


# ============================================================
# main
# ============================================================

class ThreadingHTTPServer(HTTPServer):
    """允许 SSE 长连接同时不堵其它请求。"""
    daemon_threads = True

    def process_request(self, request, client_address):
        threading.Thread(target=self._handle_request_thread,
                         args=(request, client_address),
                         daemon=True).start()

    def _handle_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


PID_FILE = USER_DATA_ROOT / ".server.pid"


def _port_in_use(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except (ConnectionRefusedError, OSError):
        return False
    finally:
        s.close()


def _read_pid_file() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None


def _is_our_server_alive(port: int, pid: int | None) -> bool:
    """端口被占，确认占用方是我们之前留下的 server.py 实例。

    判定: PID 存在 + /api/status 能 200 返回 + 路径里能拿到我们项目的标识。
    """
    # 1) 同主机 status 探活
    if not _port_in_use(port):
        return False
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1.5) as r:
            if r.status != 200:
                return False
            data = json.loads(r.read().decode("utf-8"))
            # 任何字段是我们设计的就算（current_task / logged_in 都行）
            if "logged_in" not in data:
                return False
    except Exception:
        return False
    # PID 不一定能拿到（旧版没写 pid 文件），不强求
    return True


def _kill_pid(pid: int, timeout_s: float = 5.0) -> bool:
    """优雅杀进程：SIGTERM → 等 → 还活着就 SIGKILL。返回是否成功结束。"""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except Exception:
        return False
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            os.kill(pid, 0)  # 0 = 探活
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    time.sleep(0.2)
    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True


def _write_pid_file():
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception:
        pass


def _cleanup_pid_file():
    try:
        if PID_FILE.exists():
            current = _read_pid_file()
            if current == os.getpid():
                PID_FILE.unlink()
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="启 viewer + 抓取 server (本地 only)")
    ap.add_argument("--port", type=int, default=9233)
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    ap.add_argument(
        "--on-conflict",
        choices=["ask", "kill", "abort", "open"],
        default="ask",
        help="端口被占时的策略：ask=交互问 / kill=直接杀重启 / abort=放弃 / open=打开浏览器指向原 server",
    )
    args = ap.parse_args()

    if not VIEWER_HTML.exists():
        print(f"❌ 找不到 {VIEWER_HTML}", file=sys.stderr)
        sys.exit(1)

    # ---- 端口冲突处理 ----
    existing_pid = _read_pid_file()
    if _is_our_server_alive(args.port, existing_pid):
        url = f"http://127.0.0.1:{args.port}/"
        pid_str = f"PID {existing_pid}" if existing_pid else "未知 PID"
        print(f"⚠️  已有一个 server 在 {url} 运行（{pid_str}）。")
        action = args.on_conflict
        if action == "ask":
            try:
                ans = input("   [k]杀掉重启 / [o]打开浏览器用原 server / [q]退出  默认 o: ").strip().lower()
            except EOFError:
                ans = ""
            if ans in ("k", "kill"):
                action = "kill"
            elif ans in ("q", "quit"):
                action = "abort"
            else:
                action = "open"
        if action == "abort":
            print("👋 已退出，原 server 仍在跑。")
            sys.exit(0)
        if action == "open":
            print(f"🌐 打开浏览器到原 server: {url}")
            webbrowser.open(url)
            sys.exit(0)
        if action == "kill":
            if existing_pid is None:
                print("❌ 没找到 PID 文件，无法定向杀。请手动到那个终端窗口按 Ctrl+C。")
                sys.exit(1)
            print(f"🔪 杀掉旧 server (PID {existing_pid})…")
            if not _kill_pid(existing_pid):
                print("❌ 杀失败。请手动到那个终端窗口按 Ctrl+C 后重试。")
                sys.exit(1)
            # 等端口释放
            for _ in range(20):
                if not _port_in_use(args.port):
                    break
                time.sleep(0.1)
            else:
                print("❌ 端口仍被占，放弃。")
                sys.exit(1)
            print("✅ 旧 server 已结束，开始启新的。")
    elif _port_in_use(args.port):
        # 端口被占但不是我们的 server（别的程序）
        print(f"❌ 端口 {args.port} 被别的程序占用。")
        print(f"   解决：换端口 → python3 server.py --port 9234")
        sys.exit(1)

    ensure_dirs()
    print(f"📂 数据目录: {get_data_dir()}")

    addr = ("127.0.0.1", args.port)
    httpd = ThreadingHTTPServer(addr, Handler)
    _write_pid_file()
    atexit.register(_cleanup_pid_file)

    url = f"http://127.0.0.1:{args.port}/"
    print(f"✅ 已启动: {url}")
    print(f"   按 Ctrl-C 关闭")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 关闭中…")
        httpd.shutdown()
    finally:
        _cleanup_pid_file()


if __name__ == "__main__":
    main()
