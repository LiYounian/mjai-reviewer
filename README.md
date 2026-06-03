# 牌谱分析

本地工具：抓取雀魂麻将牌谱、解析、做基础数据统计。

## 它能做什么

1. **抓取**：给一条雀魂分享链接，自动从浏览器拉出**天凤格式 json**（4 玩家、整局牌谱、点数等）
2. **统计**：把抓到的若干局喂给 `stats.py`，按玩家累积出顺位、和了率、放铳率、立直率、副露率、平均打点、立直收支、亲和率、连庄数、打点分布等指标
3. **报告**：用 `report.py` 把若干场牌谱聚合成事实粒度 JSON，浏览器打开 `viewer.html` 看板查阅。支持牌谱/玩家筛选、次数↔比例切换、表头点击排序、番型表多种排序

不做：单局逐手 AI 复盘（那是 mjai-reviewer / NAGA 的事，可以拿本工具产出的 json 直接喂它们）。

## 流程总览

```
雀魂分享链接
     │
     ▼   fetch.py
Playwright 控制 Chromium → 注入 inject.js（vendored 解码内核）
     → hook WebSocket → 截 fetchGameRecord 帧 → 调 decoder
     │
     ▼
data/games/<paipu_id>.json    （天凤格式，下游 mjai-reviewer/NAGA 也吃这个）
     │
     ├─→  stats.py                          → 终端 markdown 输出（玩家级聚合）
     │
     └─→  report.py  →  report.json         事实粒度 JSON（每场/每局/每和/每役）
                              │
                              ▼   双击打开 viewer.html，文件选择器加载
                       浏览器看板（前端实时聚合，可任意切筛选/模式）
```

## 目录结构

```
牌谱分析/
├── README.md
├── fetch.py                 抓取入口
├── stats.py                 统计入口
├── pyproject.toml           （未提供，按需）
├── .gitignore
│
├── src/                     Python 代码
│   ├── fetcher/             抓取（Playwright + WS hook + 解码调用 + 落盘）
│   │   ├── browser.py       起浏览器 + 管 profile + 注入
│   │   ├── capture.py       抓 fetchGameRecord WS 帧 + 调 inject 解码
│   │   ├── tenhou_export.py 写文件
│   │   └── cli.py           参数解析 + 调度
│   ├── parser/              天凤 json 解析（无外向网络）
│   │   ├── tenhou.py        json → 结构化对局对象
│   │   ├── tiles.py         牌面编码 ↔ 可读
│   │   └── localize.py      日文役名/段位/打点 → 简体（仅给统计/报告用）
│   └── reporter/
│       └── datafile.py      parsed games → viewer 用的事实粒度 JSON
│
├── viewer.html              浏览器看板（无依赖，文件选择器读 report.json）
├── report.py                生成 report.json
│
├── inject/                  注入到雀魂页的解码器（TS + esbuild）
│   ├── src/entry.ts         唯一自写的 JS：把解码 API 暴露到 window.__majDecoder
│   ├── package.json
│   └── dist/inject.js       构建产物（gitignore，由 npm run build 生成）
│
├── vendored/                第三方源码（不修改）
│   └── kbkn3/               protobuf 解码内核 + protobufjs 静态生成器
│                            来源：https://github.com/kbkn3/MahjongSoul-review-supporter v1.5.1
│                            许可：Apache-2.0（见 vendored/kbkn3/LICENSE 与 NOTICE.md）
│
├── data/                    运行产生的数据（全部 gitignore）
│   ├── games/               天凤 json 落盘到这里
│   └── profile/             Playwright 持久化登录态（chmod 700）
│
├── docs/
│   └── 架构说明.md           设计要点 / 模块解耦原则 / 关键技术点 / 协议变更怎么办
│
└── 参考资料/                 与运行无关：历史尝试、废弃文档、第三方源码
```

## 给非程序员朋友的简易用法

> **不想装环境的：** 去 [Releases 页](https://github.com/LiYounian/mjai-reviewer/releases) 下载最新版的预编译包。
> - macOS：`mjai-tool-macos-arm64.zip`（Apple Silicon，M1 及以后）
> - Windows：`mjai-tool-windows-x64.zip`
>
> 解压后双击文件夹里的 `mjai-tool`（mac）/ `mjai-tool.exe`（win）即可。第一次打开后浏览器会自动开 http://127.0.0.1:9233/，登录雀魂 → 粘链接抓 → 看统计。
>
> ### macOS 第一次打开会被拦
>
> 因为没花 99 美刀做苹果开发者签名，macOS 会提示"无法验证开发者"。三选一处理：
>
> 1. **右键 → 打开**：在 Finder 里**右键** `mjai-tool` 点"打开"，弹窗里再点一次"打开"。以后就不拦了。
> 2. **系统设置 → 隐私与安全性**：拦截后下方会有"仍要打开"按钮，点一下输密码。
> 3. **命令行清隔离属性**：终端跑 `xattr -dr com.apple.quarantine /path/to/mjai-tool`，一劳永逸。
>
> ### Windows 第一次打开会被拦
>
> Windows SmartScreen 会提示"已保护你的电脑"。点"更多信息" → "仍要运行"。
>
> 数据存在 `~/.mjai-tool/`（mac）或 `%USERPROFILE%\.mjai-tool\`（win）下，里面会自动建 `data/games/`、`data/raw/`、`data/profile/` 三个子目录。

---

## 给会一点命令行的朋友：源码运行

如果你想"双击就用"但 Releases 上没你的平台（比如 Intel Mac、Linux），按下面安装环境后，双击仓库根目录的 **`启动.command`**（macOS）或 **`启动.bat`**（Windows）：

- 终端窗口会启动一个本地 server，浏览器自动打开
- 顶部两个 tab：`📊 统计` 看牌谱分析；`🌐 抓取` 登录雀魂、粘贴牌谱链接抓
- 关闭：终端窗口 Ctrl+C 或 ⌘+Q

> macOS 第一次双击 `启动.command` 可能被拦"无法验证开发者"。解决：在 Finder 里**右键点它 → 打开**，弹窗里再点一次"打开"，以后就不会拦了。

## 一次性安装（开发/手装）

```bash
# Python 端
python3 -m pip install --user playwright
python3 -m playwright install chromium

# JS 端：构建 inject.js（约 3.9MB IIFE）
cd inject && npm install && npm run build && cd -
```

## 使用

### 第一次：扫码登录一次

```bash
python3 fetch.py --login-only
```

弹出 Chromium 自动开雀魂主页，**你扫码或账密登录**到大厅后回终端按 Enter，登录态自动保存到 `data/profile/`。下次复用，不用再登录。

### 抓单局

```bash
python3 fetch.py "https://game.maj-soul.com/1/?paipu=xxxxx_yyy"
# → data/games/xxxxx_yyy.json
```

无头跑（看不见浏览器）。冷启动 60~90 秒（Unity 资源首次加载），后续每局 30~60 秒。

### 抓批量

```bash
python3 fetch.py "<url1>" "<url2>" "<url3>"
# 默认每局间随机延迟 30~120 秒
```

⚠️ **封号红线**：`--delay-min` **不要小于 30 秒**。批量几十局以上建议 `--delay-min 120 --delay-max 300`。参考项目 MajsoulPaipuAnalyzer 当年因短间隔批量被封号。

```bash
# 自定义延迟范围
python3 fetch.py --delay-min 60 --delay-max 180 "<url1>" "<url2>"

# 看着它跑（可见窗口）
python3 fetch.py --headed "<url>"

# 已存在的本地 json 默认跳过；要重抓加 --force
python3 fetch.py --force "<url>"
```

### 出统计（终端）

```bash
# 单局
python3 stats.py data/games/<paipu>.json

# 多局累积（同一玩家自动合并）
python3 stats.py data/games/*.json
```

按玩家分组，输出顺位 / 和了率 / 放铳率 / 立直率 / 副露率 / 平均打点 / 立直收支 / 连庄数 / 大点分布等。日文役名/段位会归化为简体显示（落盘 json 仍保留日文，喂给下游 mjai-reviewer / NAGA 的）。

### 出报告（浏览器看板）

`viewer.html` 直接接受**两种输入**，挑一种即可：

**方式 A（推荐给只看不抓的朋友）**：直接拖入原始 `data/games/*.json`（可多选）
浏览器双击打开 `viewer.html` → 文件选择器选一或多个原始天凤格式牌谱 → 前端实时解析 + 聚合。**完全不需要 Python**，把 json 文件发给朋友，他双击 viewer.html 就能看。

**方式 B（适合预先归档大批量）**：先用 Python 出 `report.json`，再加载

```bash
python3 report.py data/games/*.json              # 输出 ./report.json
python3 report.py data/games/*.json -o my.json   # 自定输出路径
```

报告生成后，viewer 会自动识别 `schema` 字段走快路径。也可以在前端用方式 A 加载完后点 **导出 report.json** 按钮把当前数据归档成报告文件。

看板提供：

- **牌谱下拉**：全部 / 单场（一场牌谱 = 东风/半庄全场）
- **玩家下拉**：全部 / 单人
- **次数 ↔ 比例**：一键切换；比例模式下排序键也跟着切换
- **总览表**（26 列）：表头点击排序，活动列加 ↑/↓ 标记
- **番型表**（行=役、列=玩家）：三种排序——出现先后 / 占比最大 / 役名字典序

viewer 是纯前端单文件、无外部依赖（离线无 CDN 也能用）。前端解析逻辑与 Python 端字节级一致。

## 风险与边界

- **封号风险**：单局接近 0（被动 hook 浏览器自己发的 WebSocket）；批量短间隔会触发风控，**已加默认 30~120s 随机延迟，禁止禁用**
- **登录态保护**：profile 含 cookie / localStorage，强制 `chmod 700` + `.gitignore`
- **协议变更**：雀魂改 liqi 协议时（kbkn3 上游会跟），重新拉新版到 `vendored/kbkn3/` 后 `cd inject && npm run build`

## 进一步阅读

- `docs/架构说明.md` — 模块解耦原则、关键技术点、协议变更如何同步
- `vendored/kbkn3/NOTICE.md` — vendored 内容清单与裁剪范围
- `参考资料/README.md` — 历史尝试与废弃文档索引（含已证伪的 token 路线，避免后人重蹈覆辙）
