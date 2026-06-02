"""单一职责：在已注入 inject.js 的页面上抓一局牌谱。

输入：BrowserContext + 牌谱 URL
输出：dict（天凤 TenhouMessage）

不碰文件、不碰 CLI 参数。
"""
from __future__ import annotations
import base64
import os
import time
from pathlib import Path
from playwright.sync_api import BrowserContext, WebSocket


# Wrapper 协议头第 0 字节是 type，雀魂消息类型常量
_RESPONSE_TYPE = 0x03      # 服务端对客户端请求的响应
# 雀魂帧首 3 字节：type(1) + index(2 LE)
# fetchGameRecord 是 Lobby 上的请求-响应

# 调试模式：环境变量 MAJ_DUMP_FRAMES=1 时把抓到的帧写到 /tmp 供分析
_DUMP = os.environ.get("MAJ_DUMP_FRAMES") == "1"
_DUMP_DIR = Path("/tmp/maj-frames")


def _index_of_frame(frame_bytes: bytes) -> int:
    """前 3 字节: type(1) + index(2 LE)"""
    if len(frame_bytes) < 3:
        return -1
    return int.from_bytes(frame_bytes[1:3], "little")


def _frame_type(frame_bytes: bytes) -> int:
    return frame_bytes[0] if frame_bytes else -1


class _Capturer:
    """抓帧状态机。隔离在内部，不暴露。"""

    def __init__(self) -> None:
        # request index → request name (e.g. ".lq.Lobby.fetchGameRecord")
        self._pending: dict[int, str] = {}
        # 第一个匹配的 fetchGameRecord 响应原始字节
        self.captured: bytes | None = None
        # 调试用：所有看到的 sent/recv 摘要
        self._dump_seq = 0

    def on_websocket(self, ws: WebSocket) -> None:
        ws.on("framesent", self._on_sent)
        ws.on("framereceived", self._on_recv)

    def _maybe_dump(self, tag: str, data: bytes) -> None:
        if not _DUMP:
            return
        _DUMP_DIR.mkdir(exist_ok=True, parents=True)
        self._dump_seq += 1
        fname = _DUMP_DIR / f"{self._dump_seq:04d}-{tag}-t{data[0]:02x}.bin"
        fname.write_bytes(data)

    def _on_sent(self, payload) -> None:
        data = payload if isinstance(payload, (bytes, bytearray)) else None
        if data is None:
            return
        self._maybe_dump("sent", bytes(data))
        if _frame_type(data) != 0x02:  # 0x02 = REQUEST
            return
        body = bytes(data[3:])
        # 雀魂 request name 形如 ".lq.Lobby.fetchGameRecord"
        if b".lq.Lobby.fetchGameRecord" in body:
            self._pending[_index_of_frame(data)] = "fetchGameRecord"

    def _on_recv(self, payload) -> None:
        data = payload if isinstance(payload, (bytes, bytearray)) else None
        if data is None:
            return
        self._maybe_dump("recv", bytes(data))
        if self.captured is not None:
            return
        if _frame_type(data) != _RESPONSE_TYPE:
            return
        idx = _index_of_frame(data)
        if self._pending.pop(idx, None) == "fetchGameRecord":
            self.captured = bytes(data)


def fetch_record(
    ctx: BrowserContext,
    paipu_url: str,
    timeout_s: float = 60.0,
) -> dict:
    """打开牌谱页 → 等抓到 fetchGameRecord 响应 → 调 window.__majDecoder 出天凤 json。

    阻塞，直到拿到结果或超时。
    """
    page = ctx.new_page()
    cap = _Capturer()
    page.on("websocket", cap.on_websocket)

    page.goto(paipu_url, wait_until="commit")  # 不等整页加载，雀魂 Unity 会持续加载

    deadline = time.time() + timeout_s
    while cap.captured is None and time.time() < deadline:
        page.wait_for_timeout(500)

    if cap.captured is None:
        raise TimeoutError(
            f"{timeout_s}s 内未抓到 fetchGameRecord 响应。"
            "请确认：① 已登录 ② URL 正确 ③ 雀魂 Unity 加载完成（首次开窗可能要 30-60s）"
        )

    # 抓到了：失败前先把帧落到 /tmp，这样我们能事后离线分析
    fail_dump = Path("/tmp/maj-last-captured.bin")
    fail_dump.write_bytes(cap.captured)

    b64 = base64.b64encode(cap.captured).decode("ascii")
    try:
        tenhou: dict = page.evaluate(
            "(b64) => window.__majDecoder.toTenhou(b64)", b64
        )
    except Exception as e:
        raise RuntimeError(
            f"decoder 解码失败: {e}. "
            f"原始帧已保存到 {fail_dump} ({len(cap.captured)} 字节)，请离线分析。"
        ) from e
    page.close()
    return tenhou
