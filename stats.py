"""从解析后的牌谱计算每位玩家的基础统计指标。

支持单局/单牌谱，也支持累积多牌谱(传入多个 game 对象)。
指标对标天凤/雀魂常用项，第一版覆盖核心:
  顺位、和了率、自摸率、放铳率、立直率、副露率、被自摸率、流局率、
  平均和了打点、平均放铳打点、平均顺位、点数收支。
"""
from collections import defaultdict

from src.parser.tenhou import parse_game


class PlayerStat:
    def __init__(self, name):
        self.name = name
        self.games = 0            # 参与的对局(整场)数
        self.placements = []      # 每场顺位
        self.rounds = 0           # 参与局数
        self.hule = 0             # 和了局数
        self.zimo = 0             # 自摸局数
        self.hule_point = 0       # 和了总得点(用 delta 正值)
        self.fangchong = 0        # 放铳局数
        self.fangchong_point = 0  # 放铳总失点(绝对值)
        self.beizimo = 0          # 被自摸局数(别人自摸时我付点)
        self.reach = 0            # 立直局数
        self.fulu = 0             # 副露局数
        self.liuju = 0            # 流局(参与)局数
        self.liuju_tenpai = 0     # 流局时听牌

    def _r(self, a, b):
        return a / b if b else 0.0

    def summary(self):
        return {
            "玩家": self.name,
            "对局数": self.games,
            "总局数": self.rounds,
            "平均顺位": round(sum(self.placements) / len(self.placements), 3) if self.placements else 0,
            "顺位分布": {f"{i}位": self.placements.count(i) for i in (1, 2, 3, 4)},
            "和了率": round(self._r(self.hule, self.rounds), 4),
            "自摸率(和了中)": round(self._r(self.zimo, self.hule), 4),
            "放铳率": round(self._r(self.fangchong, self.rounds), 4),
            "立直率": round(self._r(self.reach, self.rounds), 4),
            "副露率": round(self._r(self.fulu, self.rounds), 4),
            "被自摸率": round(self._r(self.beizimo, self.rounds), 4),
            "流局率": round(self._r(self.liuju, self.rounds), 4),
            "流局听牌率": round(self._r(self.liuju_tenpai, self.liuju), 4),
            "平均和了打点": round(self._r(self.hule_point, self.hule), 1),
            "平均放铳打点": round(self._r(self.fangchong_point, self.fangchong), 1),
        }


def accumulate(games, stats=None):
    """把若干 game 对象累加进 stats(玩家名 -> PlayerStat)。支持跨牌谱累积。"""
    if stats is None:
        stats = {}

    def get(name):
        if name not in stats:
            stats[name] = PlayerStat(name)
        return stats[name]

    for g in games:
        names = g["names"]
        nplayers = g["nplayers"]
        # 整场顺位
        final = sorted(g["final"], key=lambda x: -x["point"])
        place_of = {f["seat"]: i + 1 for i, f in enumerate(final)}
        for seat in range(nplayers):
            ps = get(names[seat])
            ps.games += 1
            ps.placements.append(place_of.get(seat, nplayers))

        for r in g["rounds"]:
            ending = r["ending"]
            for p in r["players"]:
                seat = p["seat"]
                ps = get(names[seat])
                ps.rounds += 1
                if p["riichi"]:
                    ps.reach += 1
                if p["fulu_count"] > 0:
                    ps.fulu += 1

            if ending["type"] == "和了":
                for a in ending["agaris"]:
                    w = a["who"]
                    if w is None:
                        continue
                    ps = get(names[w])
                    ps.hule += 1
                    delta = a["delta"]
                    if delta and w < len(delta):
                        ps.hule_point += max(delta[w], 0)
                    if a["tsumo"]:
                        ps.zimo += 1
                        # 其他人被自摸
                        for seat in range(nplayers):
                            if seat != w:
                                get(names[seat]).beizimo += 1
                    else:
                        frm = a["from"]
                        if frm is not None:
                            fps = get(names[frm])
                            fps.fangchong += 1
                            if delta and frm < len(delta):
                                fps.fangchong_point += abs(min(delta[frm], 0))
            elif ending["type"] == "流局":
                delta = ending.get("delta", [0, 0, 0, 0])
                for seat in range(nplayers):
                    ps = get(names[seat])
                    ps.liuju += 1
                    # 流局点数为正 => 听牌(收到不听罚符)
                    if delta and seat < len(delta) and delta[seat] > 0:
                        ps.liuju_tenpai += 1
    return stats


def report(stats):
    lines = []
    for name, ps in stats.items():
        s = ps.summary()
        lines.append(f"### {s['玩家']}")
        lines.append(f"- 对局数 {s['对局数']} / 总局数 {s['总局数']}  平均顺位 **{s['平均顺位']}**")
        d = s["顺位分布"]
        lines.append(f"- 顺位分布: 1位×{d['1位']} 2位×{d['2位']} 3位×{d['3位']} 4位×{d['4位']}")
        lines.append(
            f"- 和了率 {s['和了率']:.1%}  放铳率 {s['放铳率']:.1%}  "
            f"立直率 {s['立直率']:.1%}  副露率 {s['副露率']:.1%}"
        )
        lines.append(
            f"- 自摸率(和了中) {s['自摸率(和了中)']:.1%}  被自摸率 {s['被自摸率']:.1%}  "
            f"流局率 {s['流局率']:.1%}  流局听牌率 {s['流局听牌率']:.1%}"
        )
        lines.append(
            f"- 平均和了打点 {s['平均和了打点']:.0f}  平均放铳打点 {s['平均放铳打点']:.0f}"
        )
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python3 stats.py <tenhou.json> [更多.json ...]")
        sys.exit(1)
    from src.parser.tenhou import load
    games = [parse_game(load(p)) for p in sys.argv[1:]]
    stats = accumulate(games)
    print(report(stats))
