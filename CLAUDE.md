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

# 起本地 server（推荐：浏览器 UI 全功能 — 登录/抓取/管理/分析）
python3 server.py                    # 默认 9233 端口，自动开浏览器
# 双击 启动.command (mac) / 启动.bat (win) 等价；启动脚本会先自动检测
# python/playwright/chromium/inject.js 缺啥装啥/build 啥再起 server。

# 或走 CLI 直抓
python3 fetch.py --login-only                                       # 首次扫码
python3 fetch.py "https://game.maj-soul.com/1/?paipu=<UUID>_<seat>"
python3 fetch.py --delay-min 120 --delay-max 300 <url1> <url2> ...  # 批量更稳

# 统计（终端 markdown 输出）
python3 stats.py data/games/*.json

# 报告（事实粒度 JSON，给 viewer 加载）
python3 report.py data/games/*.json -o report.json

# 调试 WS 帧（每帧 dump 到临时目录, 跨平台走 tempfile.gettempdir()）
MAJ_DUMP_FRAMES=1 python3 fetch.py "<url>"

# 协议变更后只需重 build inject（详见 docs/架构说明.md §四）
cd inject && npm run build

# 打 PyInstaller 包（产 dist/mjai-tool/, ~500MB, 给朋友双击用）
python3 build.py
```

仓库无 lint / test 配置。改完后建议:
- 总览/番型/先达成榜口径变化 → `python3 server.py` 起 viewer 看 UI 表
- 抓取链路变 → `python3 fetch.py --force <已有url>` 重抓一局
- frozen 模式改 → `python3 build.py && ./dist/mjai-tool/mjai-tool` 跑通

## 架构核心

```
                                  ┌── fetch.py (CLI)
                                  │
浏览器 UI ──→ server.py ──→ 都用同一个 src/fetcher 链路:
                                  │   browser.py (Playwright + 注入)
                                  │   capture.py (hook WS, decode 走 inject.js)
                                  │   tenhou_export.py (写盘 data/games + data/raw)
                                  └── 调 window.__majDecoder (inject/dist/inject.js)
                                                       │
                                                       ▼
                                          ┌── data/games/*.json (天凤格式, 喂下游 AI)
                                          └── data/raw/*.json   (kbkn3 中间态, 含完整事件流)
                                                       │
                                                       ▼
                                stats.py (终端 md)  /  report.py → report.json
                                src/parser/{tenhou,tiles,localize}.py
                                                       │
                                                       ▼
                              viewer.html (浏览器看板, 双源:
                                  原始天凤 json 多选 -> 前端实时解析+聚合,
                                  或 report.json 直接加载)
                                                       │
                              build.py + mjai-tool.spec (PyInstaller)
                              .github/workflows/release.yml (CI 出 mac/win zip)
```

**四个独立子项目**，通过文件 / HTTP API 交付：

1. **Python 抓取/解析侧** (`src/fetcher`, `src/parser`, `src/reporter`, `fetch.py`, `stats.py`, `report.py`)：起浏览器、抓 WS 帧、解析天凤 json、出统计/报告。
2. **本地 server** (`server.py`)：stdlib http.server，端口 9233，仅 127.0.0.1。提供 GET / (viewer.html) / GET /api/games (列文件) / GET /api/games/raw / DELETE /api/games/:ref / POST /api/login / POST /api/login/done / POST /api/fetch (后台线程跑) / GET /api/fetch/stream (SSE 进度) / GET POST /api/config (data_dir 读写)。同时只允许一个抓取任务跑，写 `.server.pid` 给端口冲突检测用 (`--on-conflict ask|kill|abort|open`)。
3. **JS 注入侧** (`inject/`)：唯一自写文件 `inject/src/entry.ts`，把 `vendored/kbkn3/` 的解码内核打包成 IIFE 注到雀魂页，挂 `window.__majDecoder.{toTenhou, toMajsoul, decode}`。esbuild 构建产物 `inject/dist/inject.js` 由 Python 侧用 `add_init_script()` 在 document_start 注入。
4. **Viewer 网页侧** (`viewer.html`)：纯前端单文件，无外部依赖（CDN 离线也能用）。两种输入：① 原始天凤 `data/games/*.json` 多选 → 前端跑等价于 `src/parser` + `src/reporter/datafile.py` 的解析逻辑（`window.MJAI.parseGame/buildReport/localize` 暴露给调试），② 已生成的 `report.json` 走快路径。功能：抓取 tab（登录/URL 列表/SSE 日志/牌谱列表多选/data_dir 设置）+ 统计 tab（总览 28 列含单次极值/番型字典序表/番型先达成榜含副露过滤）。
   **不要把渲染逻辑挪回 Python** — 加新视图只改 HTML，前端 + Python 解析两份代码必须保持口径一致。

**关键技术点**（修代码前必读 `docs/架构说明.md` §三）：

- **不在 Python 侧解 protobuf**：`capture.py` 通过裸搜请求名字符串 `b".lq.Lobby.fetchGameRecord"` 在 sent 帧里匹配、按 index 在 recv 帧里配对。完整解码全在浏览器侧由 inject.js 做。
- **雀魂帧首 3 字节** = `type(1) + index(2 LE)`；`type=0x02` 是 request，`0x03` 是 response。
- **protobufjs 必须 v8**：kbkn3 的 `liqi-proto.js` 用了 `reader.tag()`，v7 没这个 API。`inject/package.json` 锁了 `^8.4.0`。
- **vendored 软链**：`vendored/kbkn3/node_modules` 软链到 `inject/node_modules`，否则 esbuild 找不到 `protobufjs/minimal.js`。clone 后跑 `cd inject && npm install` 让软链指向有效目标。
- **登录态** 在 `data/profile/`（Playwright 持久化目录，约 250~310MB），含 cookie/localStorage，强制 `chmod 700` + `.gitignore`，**绝不入库**。

## 目录角色

| 路径 | 说明 |
|---|---|
| `src/config.py` | 单点路径管理：`get_data_dir/get_games_dir/get_raw_dir/get_profile_dir`，每次读 `config.json`（lazy）。区分 RESOURCE_ROOT（静态资源）vs USER_DATA_ROOT（用户数据），frozen 模式下后者切到 `~/.mjai-tool/`。 |
| `src/fetcher/` | 抓取链：`browser.py`(浏览器+注入) / `capture.py`(WS hook+解码调用，返 `{tenhou, majsoul}`) / `tenhou_export.py`(落盘 games + raw + URL sanitize) / `cli.py`(参数+调度)。每模块单一职责，靠 dict 传数据。 |
| `src/parser/` | 天凤 json → 结构化局对象。无外向网络依赖。`localize.py` 把 kbkn3 输出的日文役名/段位/打点串归化为简体（按 key 长度降序替换）。 |
| `src/reporter/` | 报告器：`datafile.py` 把 parsed games 转成事实粒度 JSON（每场/每局/每和/每役都拆开存，**`agari.delta` 4 元素明细必须保留** — 单次极值统计要用）供 viewer 用。 |
| `server.py` | 本地 HTTP server，详见架构核心 §2。 |
| `viewer.html` | 长期复用的浏览器看板。功能详见架构核心 §4。 |
| `build.py` + `mjai-tool.spec` | PyInstaller 打包。**spec 里 chromium .app 不能直接收**（datas 走会让 PyInstaller 重签破坏 bundle），build.py 临时把 `.local-browsers/` 从 site-packages 搬走 → 跑 PyInstaller → 整目录 copy 进产物（`shutil.copytree(symlinks=True)` 保 bundle 软链）。瘦身删 `chromium_headless_shell-*` (190MB) + `ffmpeg-*` (2.5MB)，所以代码必须用 `channel='chromium'` 走完整 chromium 不走 headless-shell。 |
| `.github/workflows/release.yml` | tag v* 触发，matrix mac/win 跑 build.py 出 zip → Release。 |
| `启动.command` / `启动.bat` | mac/win 双击启动 server。自动检测/装 python+playwright+chromium、按需 build inject.js（`vendored/kbkn3/node_modules` 是 git symlink 指向 `inject/node_modules`，Win checkout 会变占位符；build.py `_ensure_kbkn3_node_modules()` 每次幂等重建）。 |
| `inject/` | TypeScript + esbuild 子项目。只 `entry.ts` 是自写，其它都是构建配置。 |
| `vendored/kbkn3/` | 第三方解码内核，**逐字保留不修改**（Apache-2.0 要求标注修改）。要改包装写在 `inject/src/entry.ts`。来源 `https://github.com/kbkn3/MahjongSoul-review-supporter`。 |
| `data/games/` | 天凤格式 json，喂下游 AI 复盘工具。gitignore。 |
| `data/raw/` | kbkn3 decoder 输出的雀魂中间态 json，含完整事件流（每次摸打吃碰立直）+ `head.start_time/end_time` 等 metadata。gitignore。 |
| `data/profile/` | Playwright 登录态，gitignore + chmod 700。 |
| `config.json` | 用户运行时配置（含 `data_dir`），gitignore。 |
| `参考资料/` | 历史尝试、废弃文档、第三方源码（mjai-reviewer / tensoul / MajsoulPaipuAnalyzer / kbkn3 上游解压）。**与运行无关**，只为查证设计来源。 |
| `docs/架构说明.md` | 模块解耦原则、关键技术点、协议变更应对流程。改架构前先读。 |

## 强制约束

- **封号红线**：批量抓取 `--delay-min` **不要小于 30 秒**。参考项目 MajsoulPaipuAnalyzer 当年因短间隔批量被封号，CLI 默认 30~120s 随机延迟，**禁止禁用**（`cli.py:_sleep_jitter`）。
- **不修改 vendored/**：协议变更时跟随上游 kbkn3，重新拉 tarball 覆盖到 `vendored/kbkn3/`，更新 `NOTICE.md` 里的 commit/tag，然后 `cd inject && npm run build`。流程见 `docs/架构说明.md` §四。
- **不要尝试 token 路线**：从 localStorage 读 token 直接 oauth2Login 已被雀魂 Unity WebGL 封死，详见 `参考资料/历史文档/token获取_2026-06-01结论.md`。
- **`data/games/*.json` 不可改**：这是要喂下游 mjai-reviewer/NAGA 的天凤格式牌谱，里面的日文役名是它们识别役种的 key。**任何归化/翻译/字段重命名只能在 `src/parser/localize.py` 和 stats/报告层做**，落盘前不得引入 localize。日文来源是 `vendored/kbkn3/` 解码内核硬编码（fan.json 只有日/英两套），用户切登录语言无法影响。
- **commit 不带 Claude 署名**：commit message / PR body 不加 `Co-Authored-By: Claude` 行，也不加 `🤖 Generated with` 行。仅在用户明确要求时加。
- **viewer JS 与 Python 解析口径必须一致**：`viewer.html` 里的 `parseGame/buildReport/localize` 与 `src/parser/{tenhou,localize}.py` + `src/reporter/datafile.py` 是两份等价代码。改任一边的解析逻辑（映射表、riichi outcome 判定、agari.delta 等）时另一边必须同步——否则 viewer "拖原始 json" 路径和 "加载 report.json" 路径会出不同结果。
