"""复现 tensoul/server_config.js: 获取雀魂服务器配置(版本/liqi proto/网关)。

这一步纯 HTTP、不需要登录态，零封号风险。用来确认:
  1. 服务器可达
  2. 能下到 liqi.json (protobuf 协议定义)
  3. 能拿到 WebSocket 网关地址

雀魂各服 base:
  国服 CN : https://game.maj-soul.com   (链接前缀 /1/)
  日服 JP : https://game.mahjongsoul.com
  国际 EN : https://mahjongsoul.game.yo-star.com
"""
import sys
import time
import random

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 注意: 国服资源在 /1/ 子路径下(链接前缀也是 /1/)，与日/国际服不同
BASES = {
    "cn": "https://game.maj-soul.com/1",
    "jp": "https://game.mahjongsoul.com",
    "en": "https://mahjongsoul.game.yo-star.com",
}


def _get(url, **kw):
    return requests.get(url, headers={"User-Agent": UA}, timeout=15, **kw)


def get_server_config(base: str) -> dict:
    """复现 getServerConfig: version -> resversion -> liqi.json -> 服务发现服务器。"""
    # 1) version.json
    randv = int((1 + random.random()) * time.time() * 1000)
    v = _get(f"{base}/version.json", params={"randv": randv}).json()
    version = v["version"]
    print(f"  version = {version}")

    # 2) resversion{version}.json -> liqi.json 的资源前缀
    rv = _get(f"{base}/resversion{version}.json").json()
    liqi_prefix = rv["res"]["res/proto/liqi.json"]["prefix"]
    print(f"  liqi prefix = {liqi_prefix}")

    # 3) liqi.json (protobuf 定义)
    liqi = _get(f"{base}/{liqi_prefix}/res/proto/liqi.json").json()
    n_types = len(liqi.get("nested", {}).get("lq", {}).get("nested", {}))
    print(f"  liqi.json 下载成功, lq 命名空间下定义数 = {n_types}")

    # 4) config.json: 服务发现服务器 / 网关。日服用 region_urls，国服直接给 gateways
    cfg = _get(f"{base}/v{version}/config.json").json()
    ip0 = cfg["ip"][0]
    sds = []
    gateways = []
    if "region_urls" in ip0:  # 日服/国际服: 需再查服务发现
        sds = [o["url"] for o in ip0["region_urls"]]
        print(f"  服务发现服务器 {len(sds)} 个: {sds}")
    elif "gateways" in ip0:   # 国服: 直接给出 HTTPS 网关，转成 wss
        gateways = [g["url"] for g in ip0["gateways"]]
        print(f"  国服网关 {len(gateways)} 个(HTTPS): {gateways}")

    return {
        "version": version,
        "liqi_prefix": liqi_prefix,
        "liqi": liqi,
        "service_discovery_servers": sds,
        "gateways_https": gateways,
    }


def get_gateways(sds_url: str) -> list:
    """复现 getCtlEndpoints: 查 ws-gateway 网关列表。"""
    r = _get(sds_url, params={"protocol": "ws", "ssl": "true", "service": "ws-gateway"})
    servers = r.json().get("servers", [])
    return [f"wss://{p}/gateway" for p in servers]


def main():
    region = sys.argv[1] if len(sys.argv) > 1 else "cn"
    base = BASES[region]
    print(f"=== 探测雀魂 {region} 服 ({base}) ===")
    try:
        scfg = get_server_config(base)
    except Exception as e:
        print(f"  ✗ 获取服务器配置失败: {e!r}")
        sys.exit(1)

    print("\n=== WebSocket 网关 ===")
    if scfg["gateways_https"]:
        # 国服: HTTPS route-N -> wss://route-N/gateway
        for url in scfg["gateways_https"]:
            host = url.replace("https://", "")
            print(f"      wss://{host}/gateway")
    else:
        for sds in scfg["service_discovery_servers"]:
            try:
                gws = get_gateways(sds)
                print(f"  {sds} -> {len(gws)} 个网关")
                for g in gws[:3]:
                    print(f"      {g}")
                if gws:
                    break
            except Exception as e:
                print(f"  {sds} 查询失败: {e!r}")

    # 把 liqi.json 存下来，供后续 protobuf 解析用
    import json
    with open("data/liqi.json", "w", encoding="utf-8") as f:
        json.dump(scfg["liqi"], f, ensure_ascii=False)
    print("\n  ✓ liqi.json 已存到 data/liqi.json")


if __name__ == "__main__":
    main()
