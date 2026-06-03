"""从解析后的牌谱计算每位玩家的统计指标。

支持单局/单牌谱，也支持累积多牌谱(传入多个 game 对象)。
v2 指标:
  顺位、和了率、自摸率、放铳率、立直率、副露率、被自摸率、流局率、流局听牌率、
  平均和了打点、平均放铳打点、平均顺位、点数收支、亲家和了率、连庄数、
  打点分布(满贯/跳满/倍满/三倍满/役满)、立直收支(和/铳/听/不听 占比 + 平均收益)、
  副露和了率、副露放铳率。
日文役名/段位/规则一律走 src/parser/localize 归化为简体后再展示。
"""
from collections import defaultdict, Counter

from src.parser.tenhou import parse_game
from src.parser.localize import localize


class PlayerStat:
    def __init__(self, name):
        self.name = name
        self.games = 0
        self.placements = []
        self.score_balance = 0      # 累计点数收支(基于 final.score_delta，单位千点)

        self.rounds = 0
        self.dealer_rounds = 0      # 当亲家的局数
        self.dealer_keep = 0        # 连庄(亲家和了或亲家流局听牌)累计

        self.hule = 0
        self.zimo = 0
        self.dealer_hule = 0        # 亲家时和了
        self.hule_point = 0
        self.fangchong = 0
        self.fangchong_point = 0
        self.beizimo = 0
        self.beizimo_point = 0      # 被自摸失点累计

        self.reach = 0
        # 立直归宿
        self.reach_won = 0
        self.reach_dealin = 0
        self.reach_draw_tenpai = 0
        self.reach_draw_noten = 0
        self.reach_other = 0
        self.reach_balance = 0      # 立直局的净点数收支

        self.fulu = 0
        self.fulu_hule = 0
        self.fulu_fangchong = 0

        self.liuju = 0
        self.liuju_tenpai = 0

        # 打点分布: 满贯 跳满 倍满 三倍满 役满 (键即归化后字符串)
        self.score_class = Counter()

    def _r(self, a, b):
        return a / b if b else 0.0

    def summary(self):
        return {
            "玩家": self.name,
            "对局数": self.games,
            "总局数": self.rounds,
            "平均顺位": round(sum(self.placements) / len(self.placements), 3) if self.placements else 0,
            "顺位分布": {f"{i}位": self.placements.count(i) for i in (1, 2, 3, 4)},
            "点数收支": round(self.score_balance, 1),

            "和了率": self._r(self.hule, self.rounds),
            "自摸率(和了中)": self._r(self.zimo, self.hule),
            "放铳率": self._r(self.fangchong, self.rounds),
            "立直率": self._r(self.reach, self.rounds),
            "副露率": self._r(self.fulu, self.rounds),
            "被自摸率": self._r(self.beizimo, self.rounds),
            "流局率": self._r(self.liuju, self.rounds),
            "流局听牌率": self._r(self.liuju_tenpai, self.liuju),

            "平均和了打点": self._r(self.hule_point, self.hule),
            "平均放铳打点": self._r(self.fangchong_point, self.fangchong),
            "平均被自摸失点": self._r(self.beizimo_point, self.beizimo),

            "亲和率": self._r(self.dealer_hule, self.dealer_rounds),
            "连庄数": self.dealer_keep,

            "副露和了率": self._r(self.fulu_hule, self.fulu),
            "副露放铳率": self._r(self.fulu_fangchong, self.fulu),

            "立直次数": self.reach,
            "立直和了率": self._r(self.reach_won, self.reach),
            "立直放铳率": self._r(self.reach_dealin, self.reach),
            "立直流局听牌率": self._r(self.reach_draw_tenpai, self.reach),
            "立直流局不听率": self._r(self.reach_draw_noten, self.reach),
            "立直平均收支": self._r(self.reach_balance, self.reach),

            "打点分布": dict(self.score_class),
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
        # 整场顺位 + 收支
        # 注: 同分玩家应按起家顺序保留稳定顺位(天凤/雀魂规则)，sorted 是稳定排序所以 OK
        ranked = sorted(g["final"], key=lambda x: -x["point"])
        place_of = {f["seat"]: i + 1 for i, f in enumerate(ranked)}
        for f in g["final"]:
            ps = get(names[f["seat"]])
            ps.games += 1
            ps.placements.append(place_of[f["seat"]])
            ps.score_balance += f.get("score_delta", 0)

        for r in g["rounds"]:
            ending = r["ending"]
            dealer = r["dealer_seat"]
            delta_for_round = [0] * nplayers

            # 先从 ending 收集每家本局净 delta(用于立直收支)
            if ending["type"] == "和了":
                for a in ending["agaris"]:
                    if a["delta"]:
                        for i in range(min(nplayers, len(a["delta"]))):
                            delta_for_round[i] += a["delta"][i]
            elif ending["type"] == "流局":
                for i, v in enumerate(ending.get("delta", [])):
                    if i < nplayers:
                        delta_for_round[i] += v

            # 玩家级累计
            for p in r["players"]:
                seat = p["seat"]
                ps = get(names[seat])
                ps.rounds += 1
                if seat == dealer:
                    ps.dealer_rounds += 1
                if p["riichi"]:
                    ps.reach += 1
                    ps.reach_balance += delta_for_round[seat]
                    outcome = p.get("riichi_outcome", "other")
                    if outcome == "won":
                        ps.reach_won += 1
                    elif outcome == "dealin":
                        ps.reach_dealin += 1
                    elif outcome == "draw_tenpai":
                        ps.reach_draw_tenpai += 1
                    elif outcome == "draw_noten":
                        ps.reach_draw_noten += 1
                    else:
                        ps.reach_other += 1
                if p["fulu_count"] > 0:
                    ps.fulu += 1

            # ending 类型分支
            if ending["type"] == "和了":
                # 连庄: 亲家本局是否和了
                dealer_won_or_tenpai = False
                for a in ending["agaris"]:
                    w = a["who"]
                    if w is None:
                        continue
                    ps = get(names[w])
                    ps.hule += 1
                    delta = a["delta"]
                    if delta and w < len(delta):
                        ps.hule_point += max(delta[w], 0)
                    if a.get("score_class"):
                        ps.score_class[a["score_class"]] += 1
                    if w == dealer:
                        ps.dealer_hule += 1
                        dealer_won_or_tenpai = True
                    # 和牌时是否副露(暗杠不算副露)
                    win_player = next((pp for pp in r["players"] if pp["seat"] == w), None)
                    if win_player and win_player["fulu_count"] > 0:
                        ps.fulu_hule += 1
                    if a["tsumo"]:
                        ps.zimo += 1
                        for seat in range(nplayers):
                            if seat != w:
                                bps = get(names[seat])
                                bps.beizimo += 1
                                if delta and seat < len(delta):
                                    bps.beizimo_point += abs(min(delta[seat], 0))
                    else:
                        frm = a["from"]
                        if frm is not None:
                            fps = get(names[frm])
                            fps.fangchong += 1
                            if delta and frm < len(delta):
                                fps.fangchong_point += abs(min(delta[frm], 0))
                            from_player = next((pp for pp in r["players"] if pp["seat"] == frm), None)
                            if from_player and from_player["fulu_count"] > 0:
                                fps.fulu_fangchong += 1
                if dealer_won_or_tenpai:
                    get(names[dealer]).dealer_keep += 1
            elif ending["type"] == "流局":
                delta = ending.get("delta", [0, 0, 0, 0])
                dealer_tenpai = (dealer < len(delta) and delta[dealer] > 0)
                for seat in range(nplayers):
                    ps = get(names[seat])
                    ps.liuju += 1
                    if delta and seat < len(delta) and delta[seat] > 0:
                        ps.liuju_tenpai += 1
                if dealer_tenpai:
                    get(names[dealer]).dealer_keep += 1
            # 中途流局: 不计连庄(雀魂规则: 九種九牌 等会连庄，但本工具暂略，
            # 只数和了/流局这两种确定情形，避免误差扩散到统计)
    return stats


def report(stats):
    lines = []
    for name, ps in sorted(stats.items(), key=lambda kv: kv[1].summary()["平均顺位"]):
        s = ps.summary()
        lines.append(f"### {s['玩家']}")
        lines.append(
            f"- 对局 {s['对局数']} / 局 {s['总局数']}  "
            f"平均顺位 **{s['平均顺位']}**  收支 {s['点数收支']:+.1f}"
        )
        d = s["顺位分布"]
        lines.append(
            f"- 顺位: 1×{d['1位']} 2×{d['2位']} 3×{d['3位']} 4×{d['4位']}  "
            f"亲和率 {s['亲和率']:.1%}  连庄 {s['连庄数']}"
        )
        lines.append(
            f"- 和了 {s['和了率']:.1%} (自摸 {s['自摸率(和了中)']:.1%})  "
            f"放铳 {s['放铳率']:.1%}  被自摸 {s['被自摸率']:.1%}  "
            f"流局 {s['流局率']:.1%} (听牌 {s['流局听牌率']:.1%})"
        )
        lines.append(
            f"- 立直 {s['立直率']:.1%}  副露 {s['副露率']:.1%} "
            f"(副露和了 {s['副露和了率']:.1%} / 副露铳 {s['副露放铳率']:.1%})"
        )
        lines.append(
            f"- 平均和了 {s['平均和了打点']:.0f}  平均放铳 {s['平均放铳打点']:.0f}  "
            f"平均被自摸失点 {s['平均被自摸失点']:.0f}"
        )
        if s["立直次数"]:
            lines.append(
                f"- 立直 {s['立直次数']}次: 和 {s['立直和了率']:.0%} / "
                f"铳 {s['立直放铳率']:.0%} / 流听 {s['立直流局听牌率']:.0%} / "
                f"流不听 {s['立直流局不听率']:.0%}  平均收支 {s['立直平均收支']:+.0f}"
            )
        if s["打点分布"]:
            order = ["满贯", "跳满", "倍满", "三倍满", "役满", "切上满贯", "流满"]
            seg = [f"{k}×{s['打点分布'][k]}" for k in order if s["打点分布"].get(k)]
            if seg:
                lines.append(f"- 大点: " + " / ".join(seg))
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
