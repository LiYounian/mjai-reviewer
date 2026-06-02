"""雀魂牌谱链接解析 + 直提探测。

只用标准库 + requests，先搞清楚"不登录能不能拿到牌谱数据"。
用法: python3 src/parse_link.py "<牌谱链接>"
"""
import sys
import re
import json
from urllib.parse import urlparse, parse_qs

import requests


def parse_paipu_link(url: str) -> dict:
    """从分享链接里抽出 server 前缀、牌谱 UUID、视角账号 ID。

    链接形如:
      https://game.maj-soul.com/1/?paipu=<UUID>_<accountid>
    其中 /1/ 是国服(中国)，国际服/日服前缀不同。
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    paipu = qs.get("paipu", [""])[0]
    # paipu = UUID_accountid，UUID 本身含多个 '-'，所以从最后一个 '_' 拆
    if "_" in paipu:
        uuid, _, account = paipu.rpartition("_")
    else:
        uuid, account = paipu, ""
    # seat 形如字母前缀+数字，去掉前缀字母拿到 account_id
    account_id = re.sub(r"^[a-zA-Z]+", "", account)
    return {
        "raw": url,
        "host": parsed.netloc,
        "path_prefix": parsed.path,        # 如 /1/  →  服务器分区
        "paipu_field": paipu,
        "uuid": uuid,
        "viewer_account_raw": account,
        "viewer_account_id": account_id,
    }


def probe_direct_access(info: dict) -> None:
    """探测: 不登录直接请求，看能拿到什么。

    雀魂的牌谱内容走 WebSocket+protobuf 的 Lobby.fetchGameRecord，
    需要登录态。这里只验证 HTTP 层面到底返回什么，确认直提是否可行。
    """
    print("=" * 60)
    print("【探测】直接 HTTP 访问分享链接")
    print("=" * 60)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0 Safari/537.36",
    }
    try:
        r = requests.get(info["raw"], headers=headers, timeout=15)
        print(f"  状态码: {r.status_code}")
        print(f"  Content-Type: {r.headers.get('Content-Type')}")
        print(f"  正文长度: {len(r.text)} 字节")
        # 看看牌谱 UUID / 任何对局数据有没有出现在返回的 HTML 里
        if info["uuid"] in r.text:
            print("  ✓ 返回内容里出现了 UUID（可能是 JS 模板，不代表有对局数据）")
        else:
            print("  ✗ 返回内容里没有 UUID —— 说明是个空壳 SPA 页面，数据靠登录后 JS 拉取")
        snippet = r.text[:300].replace("\n", " ")
        print(f"  正文开头: {snippet}")
    except Exception as e:
        print(f"  请求失败: {e!r}")

    print()
    print("=" * 60)
    print("【结论提示】")
    print("=" * 60)
    print("  雀魂牌谱内容不在分享链接的 HTML 里，而是登录后由前端调用")
    print("  WebSocket 网关 .lq.Lobby.fetchGameRecord(game_uuid=...) 取回的 protobuf。")
    print("  → 要拿到对局数据，下一步必须解决登录态(token)。")


def main():
    if len(sys.argv) < 2:
        print("用法: python3 src/parse_link.py \"<牌谱链接>\"")
        sys.exit(1)
    url = sys.argv[1]
    info = parse_paipu_link(url)
    print("=" * 60)
    print("【链接解析结果】")
    print("=" * 60)
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print()
    probe_direct_access(info)


if __name__ == "__main__":
    main()
