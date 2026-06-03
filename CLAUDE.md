# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

**雀魂牌谱抓取 + 基础统计**的本地工具。注意：尽管目录名为 `mjai-reviewer`，本仓库**并非** mjai-reviewer 本身，而是一个产出"天凤格式 json"的前置抓取工具，可把结果喂给 mjai-reviewer / NAGA 做 AI 复盘。第三方 mjai-reviewer 源码克隆在 `参考资料/三方代码/mjai-reviewer/`，与本工具无运行依赖。

不做：单局逐手 AI 复盘、单局复盘 UI。

## 常用命令

```bash
# 一次性安装
python3 -m pip install --user playwright && python3 -m playwright install chromium
cd inject && npm install && npm run build && cd -    # 产出 inject/dist/inject.js (~3.9MB IIFE)

# 首次登录（必做一次，存 profile 到 data/profile/）
python3 fetch.py --login-only

# 抓单局 / 多局（多局自动加 30~120s 随机延迟）
python3 fetch.py "https://game.maj-soul.com/1/?paipu=<UUID>_<seat>"
python3 fetch.py --headed --force "<url>"            # 可见窗口 + 重抓
python3 fetch.py --delay-min 120 --delay-max 300 <url1> <url2> ...   # 批量更稳

# 统计（终端 markdown 输出，聚合多局到玩家维度）
python3 stats.py data/games/<paipu>.json
python3 stats.py data/games/*.json

# 报告（生成 viewer 用的事实粒度 JSON）
python3 report.py data/games/*.json              # 输出 ./report.json
python3 report.py data/games/*.json -o foo.json
# 然后浏览器打开 viewer.html，文件选择器加载 report.json

# 调试 WS 帧（每帧 dump 到 /tmp/maj-frames/）
MAJ_DUMP_FRAMES=1 python3 fetch.py "<url>"

# 协议变更后只需重 build inject（详见 docs/架构说明.md §四）
cd inject && npm run build
```

仓库无 lint / test 配置；改完后用 `python3 stats.py data/games/<已有>.json` 验下游、`python3 fetch.py --force <已有url>` 验上游。

## 架构核心

```
fetch.py → src/fetcher/cli.py → browser.py (Playwright + 注入) → capture.py (hook WS) → tenhou_export.py (写盘)
                                                                       ↓
                                                          调 window.__majDecoder (inject/dist/inject.js)
                                                                       ↓
                                                                  data/games/*.json   (天凤格式，下游 mjai-reviewer/NAGA 直接吃)
                                                                       ↓
                              ┌────────────────────────────────────────┴───────────────────────────────────────┐
                              ↓                                                                                 ↓
                  stats.py (终端 md)                                                            report.py → report.json (事实粒度)
                  src/parser/tenhou.py + tiles.py + localize.py                                                 ↓
                                                                                                          viewer.html (浏览器看板)
```

**三个独立子项目**，通过文件交付：

1. **Python 抓取/解析侧** (`src/fetcher`, `src/parser`, `fetch.py`, `stats.py`, `report.py`)：起浏览器、抓 WS 帧、解析天凤 json、出统计/报告。
2. **JS 注入侧** (`inject/`)：唯一自写文件 `inject/src/entry.ts`，把 `vendored/kbkn3/` 的解码内核打包成 IIFE 注到雀魂页，挂在 `window.__majDecoder`。esbuild 构建产物 `inject/dist/inject.js` 由 Python 侧用 `add_init_script()` 在 document_start 注入。
3. **Viewer 网页侧** (`viewer.html`)：纯前端单文件，无依赖。文件选择器读 `report.json`，前端实时聚合（牌谱/玩家筛选、次数↔比例切换、表头点击排序、番型表三种排序）。**不要把渲染逻辑挪回 Python**：viewer 长期复用，加新视图只改 HTML，避免重跑 Python。

**关键技术点**（修代码前必读 `docs/架构说明.md` §三）：

- **不在 Python 侧解 protobuf**：`capture.py` 通过裸搜请求名字符串 `b".lq.Lobby.fetchGameRecord"` 在 sent 帧里匹配、按 index 在 recv 帧里配对。完整解码全在浏览器侧由 inject.js 做。
- **雀魂帧首 3 字节** = `type(1) + index(2 LE)`；`type=0x02` 是 request，`0x03` 是 response。
- **protobufjs 必须 v8**：kbkn3 的 `liqi-proto.js` 用了 `reader.tag()`，v7 没这个 API。`inject/package.json` 锁了 `^8.4.0`。
- **vendored 软链**：`vendored/kbkn3/node_modules` 软链到 `inject/node_modules`，否则 esbuild 找不到 `protobufjs/minimal.js`。clone 后跑 `cd inject && npm install` 让软链指向有效目标。
- **登录态** 在 `data/profile/`（Playwright 持久化目录，约 250~310MB），含 cookie/localStorage，强制 `chmod 700` + `.gitignore`，**绝不入库**。

## 目录角色

| 路径 | 说明 |
|---|---|
| `src/fetcher/` | 抓取链：`browser.py`(浏览器+注入) / `capture.py`(WS hook+解码调用) / `tenhou_export.py`(落盘) / `cli.py`(参数+调度)。每模块单一职责，靠 dict 传数据。 |
| `src/parser/` | 天凤 json → 结构化局对象。无外向网络依赖。`localize.py` 把 kbkn3 输出的日文役名/段位/打点串归化为简体（按 key 长度降序替换）。 |
| `src/reporter/` | 报告器：`datafile.py` 把 parsed games 转成事实粒度 JSON（每场/每局/每和/每役都拆开存）供 viewer 用。 |
| `viewer.html` | 长期复用的浏览器看板。读 report.json，前端聚合。 |
| `inject/` | TypeScript + esbuild 子项目。只 `entry.ts` 是自写，其它都是构建配置。 |
| `vendored/kbkn3/` | 第三方解码内核，**逐字保留不修改**（Apache-2.0 要求标注修改）。要改包装写在 `inject/src/entry.ts`。来源 `https://github.com/kbkn3/MahjongSoul-review-supporter`。 |
| `data/games/` | 抓到的天凤 json，gitignore。 |
| `data/profile/` | Playwright 登录态，gitignore + chmod 700。 |
| `参考资料/` | 历史尝试、废弃文档、第三方源码（mjai-reviewer / tensoul / MajsoulPaipuAnalyzer / kbkn3 上游解压）。**与运行无关**，只为查证设计来源。 |
| `docs/架构说明.md` | 模块解耦原则、关键技术点、协议变更应对流程。改架构前先读。 |

## 强制约束

- **封号红线**：批量抓取 `--delay-min` **不要小于 30 秒**。参考项目 MajsoulPaipuAnalyzer 当年因短间隔批量被封号，CLI 默认 30~120s 随机延迟，**禁止禁用**（`cli.py:_sleep_jitter`）。
- **不修改 vendored/**：协议变更时跟随上游 kbkn3，重新拉 tarball 覆盖到 `vendored/kbkn3/`，更新 `NOTICE.md` 里的 commit/tag，然后 `cd inject && npm run build`。流程见 `docs/架构说明.md` §四。
- **不要尝试 token 路线**：从 localStorage 读 token 直接 oauth2Login 已被雀魂 Unity WebGL 封死，详见 `参考资料/历史文档/token获取_2026-06-01结论.md`。
- **`data/games/*.json` 不可改**：这是要喂下游 mjai-reviewer/NAGA 的天凤格式牌谱，里面的日文役名是它们识别役种的 key。**任何归化/翻译/字段重命名只能在 `src/parser/localize.py` 和 stats/报告层做**，落盘前不得引入 localize。日文来源是 `vendored/kbkn3/` 解码内核硬编码（fan.json 只有日/英两套），用户切登录语言无法影响。
