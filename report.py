"""把若干牌谱聚合成 viewer 数据文件 (JSON)。

用法:
  python3 report.py data/games/*.json
  python3 report.py data/games/*.json -o stats.json

打开 viewer.html，加载生成的 JSON 看报表。
"""
import argparse
import json
import sys

from src.parser.tenhou import parse_game, load
from src.reporter.datafile import build


def main():
    ap = argparse.ArgumentParser(description="生成 viewer 数据文件 (JSON)")
    ap.add_argument("paths", nargs="+", help="天凤格式 json 文件")
    ap.add_argument("-o", "--out", default="report.json", help="输出 JSON 路径")
    args = ap.parse_args()

    games = [parse_game(load(p)) for p in args.paths]
    data = build(games)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(
        f"已生成 {args.out}  ({len(games)} 场牌谱)  -- 用 viewer.html 打开",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
