"""把 parsed games 转成 viewer 友好的事实表 JSON。

Schema: mjai-reviewer/stats/v1

设计原则:
  数据文件存"事实"（每场/每局/每和/每役），不存预聚合。
  viewer 端按 (牌谱筛选, 玩家筛选, 次数/比例) 实时聚合，避免 Python 端枚举所有切片。
"""
import re
from datetime import datetime, timezone

from src.parser.localize import localize


_YAKU_LINE = re.compile(r"^(.+?)\((\d+)飜\)$")


def _parse_yaku_entries(yaku_strs):
    """把 ['30符3飜3900点', '立直(1飜)', 'ドラ(2飜)', ...] 拆成 [{name, han}, ...]。

    第 0 项是总打点串，跳过。每条形如 'X(Y飜)'，正则抽出，name 归化为简体。
    解析不出来的条目原样保留为 name，han=0。
    """
    out = []
    for raw in yaku_strs[1:]:
        if not isinstance(raw, str):
            continue
        m = _YAKU_LINE.match(raw)
        if m:
            out.append({"name": localize(m.group(1)), "han": int(m.group(2))})
        else:
            out.append({"name": localize(raw), "han": 0})
    return out


def _round_deltas(ending, nplayers):
    """整局每家净 delta（合并多和、流局的 delta）。"""
    d = [0] * nplayers
    if ending["type"] == "和了":
        for a in ending.get("agaris", []):
            ad = a.get("delta") or []
            for i in range(min(nplayers, len(ad))):
                d[i] += ad[i]
    elif ending["type"] == "流局":
        ed = ending.get("delta") or []
        for i in range(min(nplayers, len(ed))):
            d[i] += ed[i]
    return d


def _placement_of(final):
    """final 数组按点数降序得到顺位（同分按 final 列表里的 seat 序保持稳定）。"""
    ranked = sorted(final, key=lambda x: -x["point"])
    return {f["seat"]: i + 1 for i, f in enumerate(ranked)}


def build(games):
    """parse_game 出来的对象列表 -> viewer 数据 dict。"""
    # 按 ref 排序，方便顺序展示
    games = sorted(games, key=lambda g: g.get("ref") or "")

    out_games = []
    for idx, g in enumerate(games, 1):
        ref = g.get("ref") or ""
        ref_prefix = ref.split("-")[0] if ref else ""
        label = f"#{idx} {ref_prefix}".strip() or f"#{idx}"
        nplayers = g["nplayers"]
        place_of = _placement_of(g["final"])
        final = [
            {
                "seat": f["seat"],
                "name": g["names"][f["seat"]],
                "point": f["point"],
                "score_delta": f.get("score_delta", 0),
                "placement": place_of[f["seat"]],
            }
            for f in g["final"]
        ]

        out_rounds = []
        for r in g["rounds"]:
            ending = r["ending"]
            etype = ending["type"]
            deltas = _round_deltas(ending, nplayers)

            players = []
            for p in r["players"]:
                seat = p["seat"]
                players.append({
                    "seat": seat,
                    "name": g["names"][seat],
                    "is_dealer": seat == r["dealer_seat"],
                    "riichi": p["riichi"],
                    "fulu_count": p["fulu_count"],
                    "menzen": p["menzen"],
                    "riichi_outcome": p.get("riichi_outcome", "none"),
                    "delta": deltas[seat] if seat < len(deltas) else 0,
                })

            agaris = []
            if etype == "和了":
                for a in ending["agaris"]:
                    who = a["who"]
                    delta = a.get("delta") or []
                    point_won = max(delta[who], 0) if (who is not None and who < len(delta)) else 0
                    agaris.append({
                        "who": who,
                        "who_name": g["names"][who] if who is not None else None,
                        "from": a["from"],
                        "from_name": g["names"][a["from"]] if a["from"] is not None else None,
                        "tsumo": a["tsumo"],
                        "han": a.get("han", 0),
                        "score_class": a.get("score_class"),
                        "yaku": _parse_yaku_entries(a.get("yaku", [])),
                        "point_won": point_won,
                    })

            out_rounds.append({
                "round_name": r["round_name"],
                "honba": r["honba"],
                "dealer_seat": r["dealer_seat"],
                "ending_type": etype,
                "ending_reason": ending.get("reason"),
                "players": players,
                "agaris": agaris,
            })

        out_games.append({
            "ref": ref,
            "label": label,
            "title": g.get("title", []),
            "rule_disp": localize(g.get("rule", {}).get("disp", "")),
            "names": g["names"],
            "nplayers": nplayers,
            "final": final,
            "rounds": out_rounds,
        })

    return {
        "schema": "mjai-reviewer/stats/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "games": out_games,
    }
