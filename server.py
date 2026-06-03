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
import json
import os
import queue
import random
import re
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = Path(__file__).resolve().parent
GAMES_DIR = PROJECT_ROOT / "data" / "games"
VIEWER_HTML = PROJECT_ROOT / "viewer.html"

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
            out_path = tenhou_export.DEFAULT_OUTDIR / f"{tenhou_export.safe_filename(pid)}.json"
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
                    tenhou = capture.fetch_record(ctx, url, timeout_s=this_timeout)
                    out = tenhou_export.write_tenhou(tenhou, pid)
                    task.emit("log", f"✅ [{i+1}/{len(plan)}] 落盘: {out}")
                    wrote.append({"pid": pid, "path": str(out)})
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
        if not GAMES_DIR.exists():
            self._send_json(200, {"games": []})
            return
        items = []
        for f in sorted(GAMES_DIR.glob("*.json")):
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
        path = GAMES_DIR / f"{ref}.json"
        if not path.exists():
            self.send_error(404)
            return
        self._send_file(path, "application/json; charset=utf-8")

    def _handle_delete_game(self, ref: str):
        if not ref or "/" in ref or ".." in ref:
            self.send_error(400)
            return
        path = GAMES_DIR / f"{ref}.json"
        if not path.exists():
            self.send_error(404)
            return
        try:
            path.unlink()
            self._send_json(200, {"deleted": ref})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

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


def main():
    ap = argparse.ArgumentParser(description="启 viewer + 抓取 server (本地 only)")
    ap.add_argument("--port", type=int, default=9233)
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = ap.parse_args()

    if not VIEWER_HTML.exists():
        print(f"❌ 找不到 {VIEWER_HTML}", file=sys.stderr)
        sys.exit(1)

    addr = ("127.0.0.1", args.port)
    httpd = ThreadingHTTPServer(addr, Handler)
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


if __name__ == "__main__":
    main()
