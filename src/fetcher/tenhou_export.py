"""单一职责：把天凤 dict 写成文件。

不碰浏览器、不碰网络。纯 IO。
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# 项目根 = src/fetcher/tenhou_export.py 上溯三层
_DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data"
DEFAULT_OUTDIR = _DATA_ROOT / "games"     # 天凤 json，喂下游 mjai-reviewer/NAGA
DEFAULT_RAWDIR = _DATA_ROOT / "raw"       # 雀魂中间态 json，含完整事件流


# 雀魂正式 URL 模板。最终拼出来一定要长这样，浏览器才能正确加载游戏。
_MAJSOUL_URL_TEMPLATE = "https://game.maj-soul.com/1/?paipu={pid}"

# 一段文本里的 http(s) URL（雀魂分享按钮复制出来是 "雀魂牌谱:https://..."）
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
# 单独抓 paipu= 参数的值（兼容用户只粘 "paipu=xxxxx_y" 这种）
_PAIPU_KV_RE = re.compile(r"paipu=([^\s&#]+)", re.IGNORECASE)
# 牌谱 ID 形如 "<日期>-<UUID>_<seat>"，<日期> 是 6 位
_PAIPU_ID_RE = re.compile(r"\d{6}-[0-9a-f-]+_[A-Za-z0-9]+")


def extract_paipu_id(text: str) -> str:
    """从用户粘贴的任意字符串中抽出牌谱 ID。

    支持的输入（user-facing 文档级别保证）：
      - "雀魂牌谱:https://game.maj-soul.com/1/?paipu=260530-..._a935533092"
      - "https://game.maj-soul.com/1/?paipu=260530-..._a935533092"
      - "paipu=260530-..._a935533092"
      - "260530-..._a935533092"
      - 以及上述任一前后带空格/换行/其它无关文字

    找不到时抛 ValueError。
    """
    if not text:
        raise ValueError("空字符串")
    s = text.strip()

    # 1) 含 paipu= 的情况：query 参数提取最稳，能处理 URL 和裸 'paipu=xxx' 两种
    m = _PAIPU_KV_RE.search(s)
    if m:
        # 进一步在值里找规范 ID 模式；找不到就拿原值
        v = m.group(1)
        idm = _PAIPU_ID_RE.search(v)
        return idm.group(0) if idm else v

    # 2) 没有 paipu= 关键字：当裸 ID 处理（仍尝试匹配标准格式以剥可能的尾巴）
    idm = _PAIPU_ID_RE.search(s)
    if idm:
        return idm.group(0)

    raise ValueError(f"找不到牌谱 ID: {text!r}")


def url_for(paipu_id: str) -> str:
    """规范的雀魂牌谱 URL — 给 Playwright goto 用。"""
    return _MAJSOUL_URL_TEMPLATE.format(pid=paipu_id)


# --- 兼容旧接口 (cli.py 仍在调用) ---
def extract_url(text: str) -> str:
    """旧 API。先抽 paipu_id 再拼标准 URL，确保任何输入都给 playwright 一条干净 URL。
    抽不出 ID 时退回首个 http(s) URL 子串，再退回原 strip 文本。
    """
    if not text:
        return ""
    try:
        return url_for(extract_paipu_id(text))
    except ValueError:
        m = _URL_RE.search(text)
        return m.group(0).strip() if m else text.strip()


def parse_paipu_id(url_or_id: str) -> str:
    """旧 API 名保留 — 内部走 extract_paipu_id。"""
    return extract_paipu_id(url_or_id)


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


def write_majsoul_raw(
    majsoul: dict,
    paipu_id: str,
    outdir: Path = DEFAULT_RAWDIR,
) -> Path:
    """落盘雀魂中间态。比天凤详细得多（含每个 RecordAction 事件）。"""
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{safe_filename(paipu_id)}.json"
    out.write_text(json.dumps(majsoul, ensure_ascii=False), encoding="utf-8")
    return out
