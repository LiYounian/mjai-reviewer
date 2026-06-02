"""天凤 json 牌谱 -> 结构化对局对象。

天凤 json 顶层:
  ref    : 牌谱 ID
  log    : [每一局 ...]，每局是一个数组
  name   : [4个玩家昵称]，下标即座位(0=起家东)
  sc     : [座位0最终点, 座位0得点, 座位1..., ...] 8元素
  rule   : {disp, aka...}
  title  : [房间描述, 时间]
  dan/rate: 段位/分数

每一局 log[i] 的数组结构(固定顺序):
  [0] [场局, 本场, 立直棒]   场局 = 4*场风 + 局数 (0=东1, 4=南1...)
  [1] [4家初始点数]
  [2] [宝牌指示牌...]
  [3] [里宝牌指示牌...]
  [4] 座位0起手13张
  [5] 座位0摸牌序列 (含鸣牌串)
  [6] 座位0弃牌序列 (含鸣牌/立直串)
  [7..9]  座位1 的 起手/摸/弃
  [10..12] 座位2
  [13..15] 座位3
  [16] 结束信息: ["和了", delta, [详情...]] / ["流局", delta] / ["流し満貫", delta] / [中途流局名]
"""
import json

from .tiles import decode_tile, is_call_str, call_type, is_riichi_discard, normalize_tile

ROUND_WIND = {0: "东", 1: "南", 2: "西", 3: "北"}


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def round_name(round_code: int) -> str:
    wind = ROUND_WIND[round_code // 4]
    ju = round_code % 4 + 1
    return f"{wind}{ju}局"


def parse_ending(end) -> dict:
    """解析每局第 [16] 项结束信息。"""
    if not end:
        return {"type": "unknown"}
    tag = end[0]
    if tag == "和了":
        # end = ["和了", [delta4], [who, from, win_who, 役文字...], (可能还有第二个和了...)]
        agaris = []
        i = 1
        while i < len(end):
            delta = end[i]
            detail = end[i + 1] if i + 1 < len(end) else []
            who = detail[0] if len(detail) > 0 else None
            frm = detail[1] if len(detail) > 1 else None
            yaku = detail[3:] if len(detail) > 3 else []
            agaris.append({
                "delta": delta,
                "who": who,
                "from": frm,
                "tsumo": who == frm,        # 自摸: 放铳者=和牌者
                "yaku": yaku,
            })
            i += 2
        return {"type": "和了", "agaris": agaris}
    if tag in ("流局", "流し満贯", "流し満貫"):
        delta = end[1] if len(end) > 1 else [0, 0, 0, 0]
        return {"type": "流局", "nagashi": "満" in tag or "满" in tag, "delta": delta}
    # 中途流局: 九種九牌 / 四風連打 / 四開槓 / 三家和 / 四家立直
    return {"type": "中途流局", "reason": tag, "delta": [0, 0, 0, 0]}


def parse_round(raw: list, nplayers: int = 4) -> dict:
    """解析单局。"""
    round_code = raw[0][0]
    honba = raw[0][1]
    kyoutaku = raw[0][2]
    init_scores = raw[1]
    dora = raw[2]
    ura = raw[3]

    players = []
    for seat in range(nplayers):
        base = 4 + seat * 3
        haipai = raw[base]
        draws = raw[base + 1]
        discards = raw[base + 2]
        # 统计该家行为
        riichi = any(is_riichi_discard(d) for d in discards)
        calls = [call_type(x) for x in draws if is_call_str(x)]
        calls += [call_type(x) for x in discards if is_call_str(x)]
        # 副露 = 吃碰大明杠加杠(暗杠不算副露)
        fulu = [c for c in calls if c in ("chi", "pon", "daiminkan", "kakan")]
        players.append({
            "seat": seat,
            "haipai": haipai,
            "draws": draws,
            "discards": discards,
            "riichi": riichi,
            "calls": calls,
            "fulu_count": len(fulu),
            "menzen": len(fulu) == 0,  # 门清(暗杠仍算门清)
        })

    ending = parse_ending(raw[16] if len(raw) > 16 else None)

    return {
        "round_code": round_code,
        "round_name": round_name(round_code),
        "honba": honba,
        "kyoutaku": kyoutaku,
        "dealer_seat": round_code % 4,
        "init_scores": init_scores,
        "dora": dora,
        "ura": ura,
        "players": players,
        "ending": ending,
    }


def parse_game(data: dict) -> dict:
    """解析整局牌谱(可能含多局)。"""
    names = data.get("name", ["", "", "", ""])
    nplayers = 3 if (len(names) >= 4 and names[3] == "") else 4
    sc = data.get("sc", [])
    final = []
    for seat in range(4):
        if 2 * seat + 1 < len(sc):
            final.append({"seat": seat, "point": sc[2 * seat], "score_delta": sc[2 * seat + 1]})
    rounds = [parse_round(r, nplayers) for r in data.get("log", [])]
    return {
        "ref": data.get("ref"),
        "rule": data.get("rule", {}),
        "title": data.get("title", []),
        "names": names,
        "dan": data.get("dan", []),
        "rate": data.get("rate", []),
        "nplayers": nplayers,
        "final": final,
        "rounds": rounds,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python3 src/parse_tenhou.py <tenhou.json>")
        sys.exit(1)
    g = parse_game(load(sys.argv[1]))
    print(f"牌谱 {g['ref']}  规则: {g['rule'].get('disp', '')}")
    print(f"玩家: {g['names']}")
    print(f"共 {len(g['rounds'])} 局\n")
    for r in g["rounds"]:
        e = r["ending"]
        line = f"  {r['round_name']} {r['honba']}本场"
        if e["type"] == "和了":
            for a in e["agaris"]:
                way = "自摸" if a["tsumo"] else f"荣和(放铳座{a['from']})"
                line2 = f" — 座{a['who']} {way} {'/'.join(a['yaku'])}"
                print(line + line2)
        else:
            print(line + f" — {e.get('reason', e['type'])}")
    print("\n最终:")
    for f in sorted(g["final"], key=lambda x: -x["point"]):
        print(f"  座{f['seat']} {g['names'][f['seat']]}: {f['point']}点 ({f['score_delta']:+})")
