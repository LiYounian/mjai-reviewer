"""天凤牌谱的牌面编码 <-> 人类可读。

天凤编码:
  11-19  : 一~九万 (m)
  21-29  : 一~九饼 (p)
  31-39  : 一~九索 (s)
  41-47  : 东南西北 白发中 (z, 字牌)
  51/52/53: 赤五万/赤五饼/赤五索
  60     : 摸切标记 (tsumogiri，仅出现在弃牌里，代表摸到即打)
"""

_SUIT = {1: "m", 2: "p", 3: "s", 4: "z"}
_ZNAME = {1: "东", 2: "南", 3: "西", 4: "北", 5: "白", 6: "发", 7: "中"}


def decode_tile(t) -> str:
    """单张天凤编码牌 -> 可读字符串。容错: 非法值原样返回。"""
    if isinstance(t, str):
        return t  # 已是字符串(鸣牌串)，交给上层处理
    if t == 60:
        return "摸切"
    if t in (51, 52, 53):
        return f"0{_SUIT[t - 50]}(赤)"
    suit = t // 10
    num = t % 10
    if suit in (1, 2, 3) and 1 <= num <= 9:
        return f"{num}{_SUIT[suit]}"
    if suit == 4 and 1 <= num <= 7:
        return _ZNAME[num]
    return f"?{t}"


def normalize_tile(t) -> int:
    """把赤5归一成普通5，便于统计(51->15, 52->25, 53->35)。摸切(60)返回 -1。"""
    if isinstance(t, str):
        return -1
    if t == 60:
        return -1
    if t in (51, 52, 53):
        return (t - 50) * 10 + 5
    return t


def is_aka(t) -> bool:
    return t in (51, 52, 53)


# 鸣牌串前缀: c=吃 p=碰 m=大明杠 k=加杠 a=暗杠 f=拔北(三麻)
CALL_PREFIXES = "cpmkaf"


def is_call_str(x) -> bool:
    """draws/discards 里的元素若为字符串，则是一次鸣牌/杠。"""
    return isinstance(x, str) and any(p in x for p in CALL_PREFIXES)


def call_type(x: str) -> str:
    """识别鸣牌串类型。返回: chi/pon/daiminkan/kakan/ankan/kita/unknown。"""
    if x.startswith("c"):
        return "chi"
    if x.startswith("p") or ("p" in x and "k" not in x and "a" not in x):
        return "pon"
    if "m" in x:
        return "daiminkan"
    if "k" in x:
        return "kakan"
    if "a" in x:
        return "ankan"
    if "f" in x:
        return "kita"
    return "unknown"


def is_riichi_discard(x) -> bool:
    """弃牌里以 'r' 开头表示立直宣言打牌(如 'r60' / 'r25')。"""
    return isinstance(x, str) and x.startswith("r")
