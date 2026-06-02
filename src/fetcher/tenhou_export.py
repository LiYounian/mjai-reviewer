"""单一职责：把天凤 dict 写成文件。

不碰浏览器、不碰网络。纯 IO。
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# 项目根 = src/fetcher/tenhou_export.py 上溯三层
DEFAULT_OUTDIR = Path(__file__).resolve().parent.parent.parent / "data" / "games"


def parse_paipu_id(url_or_id: str) -> str:
    """从牌谱链接抠出 game_uuid_seat 字符串；如果传的本来就是 id，原样返回。

    `https://game.maj-soul.com/1/?paipu=<UUID>_<seat>` → `<UUID>_<seat>`
    """
    if "paipu=" not in url_or_id:
        # 假设就是裸 ID
        return url_or_id.strip()
    parsed = urlparse(url_or_id)
    qs = parse_qs(parsed.query)
    val = qs.get("paipu", [""])[0]
    if not val:
        raise ValueError(f"URL 中找不到 paipu 参数: {url_or_id}")
    return val


def safe_filename(paipu_id: str) -> str:
    # 牌谱 id 形如 "<日期>-<UUID>_<seat>"，已经文件系统安全，但保险做一遍 sanitize
    return re.sub(r"[^A-Za-z0-9._\-]", "_", paipu_id)


def write_tenhou(
    tenhou: dict,
    paipu_id: str,
    outdir: Path = DEFAULT_OUTDIR,
) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{safe_filename(paipu_id)}.json"
    out.write_text(json.dumps(tenhou, ensure_ascii=False), encoding="utf-8")
    return out
