# 方案 B — 自做雀魂牌谱提取器（Python CLI）

> 决策时点：2026-06-02。token 路线已证伪（见 `参考资料/历史文档/token获取_2026-06-01结论.md`）；方案 A（kbkn3 扩展）能用但要浏览器手动一局一局点，故走 B：自己做。
>
> **2026-06-02 修订**：原计划是油猴脚本（B1），用户明确表示要 **Python CLI 形态**——`python fetch.py <牌谱链接> → 出天凤 json`。改走原计划里的 B3 路线。

## 一、目标与边界

**目标**：单条命令拉一局牌谱出天凤 json，喂给现有 `src/stats.py`。

```bash
python fetch.py "https://game.maj-soul.com/1/?paipu=xxx_yyy"
# → data/games/xxx.json   （天凤格式）
```

**边界**：
- 单局抓取（用户给链接），不批量循环（避免封号）。
- 输出锁定**天凤 json（tenhou.net/6）**，对接现有 `parse_tenhou.py`。
- 首次跑要交互登录（开可见窗口扫码），之后复用 profile 全无头。

## 二、为什么是 Python CLI（B3），不是油猴脚本（B1）

| 维度 | B1 油猴 | **B3 Python CLI** |
|---|---|---|
| 调用方式 | 浏览器开着，点一下脚本按钮 | 终端一句命令 |
| 自动化批量 | 难 | 容易（但要警惕封号） |
| 与项目栈一致 | 不一致（JS） | **一致（Python）** |
| 首次登录 | 手动登录浏览器 | 脚本开窗、用户扫码 |
| 二次起 | 浏览器开着即可 | 全无头 |
| 依赖 | Tampermonkey | Playwright + Chromium（~150MB） |

## 三、架构（关键：功能解耦）

```
方案B/
├── kbkn3-vendored/             # ← 抄的解码内核（Apache-2.0，保留 LICENSE+NOTICE）
│   ├── lib/                    # ws-capture 不抄（Python 自己 hook）；
│   │                           # liqi-frame / record-decode / kyoku / tile / points / viewer / cfg 全抄
│   ├── assets/majsoul/         # liqi-proto.js (4.67MB) + liqi.json + cfg/*.json
│   └── LICENSE, NOTICE.md
│
├── inject/                     # ← 注入页面的 JS（解码内核打包成单文件）
│   ├── entry.ts                # 我们写的：把 vendored 解码 API 挂到 window.__majDecoder
│   ├── tsconfig.json
│   ├── package.json            # 仅 esbuild + protobufjs
│   └── dist/inject.js          # 构建产物，给 Python 注入用
│
├── fetcher/                    # ← Python 侧
│   ├── __init__.py
│   ├── browser.py              # ★ 单一职责：起 Playwright + 复用 profile + 注入 inject.js
│   ├── capture.py              # ★ 单一职责：监听 WS 帧 + 找 fetchGameRecord 响应 + 调 window.__majDecoder
│   ├── tenhou_export.py        # ★ 单一职责：把解码结果写成天凤 json 文件
│   └── cli.py                  # 仅做参数解析+串起上面三块
│
├── fetch.py                    # 极薄 entry：python fetch.py <url>
│
├── data/                       # 已有，落盘到这里
│   ├── games/<uuid>.json       # 天凤 json
│   └── profile/                # ← 新增：Playwright 持久化登录态（chmod 700）
│
└── README.md                   # 用法、首次扫码、二次无头跑
```

### 解耦原则（用户明确要求）

每个模块**只暴露一个函数/类**，彼此通过纯数据传递，不共享状态：

| 模块 | 输入 | 输出 | 不关心什么 |
|---|---|---|---|
| `browser.py` | profile 路径、headless 开关 | 一个 `BrowserContext` | 雀魂、协议、牌谱格式 |
| `capture.py` | `BrowserContext` + 牌谱 URL | 一个 dict（解码后的 GameRecord） | 文件、用户参数 |
| `tenhou_export.py` | dict + 输出路径 | 写文件、返回路径 | 浏览器、网络 |
| `cli.py` | 命令行参数 | exit code | 任何业务逻辑 |
| `inject/entry.ts` | 二进制帧 | 解码后对象 | 怎么被调用、怎么落盘 |

任意一块换实现（比如 Playwright 换成 chrome-devtools-mcp）不影响其他。

## 四、关键技术点

### 4.1 浏览器侧抓 WebSocket 的两条选择

| 路线 | 怎么实现 | 优 | 劣 |
|---|---|---|---|
| **A. `page.add_init_script` 注入 hook** | 在 `document_start` 替换 `window.WebSocket`，转给 Playwright 通过 `page.evaluate` 取 | 跟 kbkn3 同套，最稳 | 注入时机需要确保早于 Unity |
| B. CDP `Network.webSocketFrameReceived` | Playwright 暴露 `page.on("websocket")` 直接拿帧 | 不动页面 JS | 帧是原始 binary，仍要走我们注入的 decoder |

**选 A**：跟 kbkn3 同源，跑通过；`add_init_script` 保证在任何脚本前执行。

### 4.2 fetchGameRecord 配对

雀魂 WS 上心跳/订阅/牌谱响应混在一条连接，按 **wrapper.name + index** 配对：
- send 时记 `index → "fetchGameRecord"`
- recv 时若 index 匹配，解码内层为 `ResGameRecord`

kbkn3 的 `record-decode.ts` 已实现，直接抄。

### 4.3 解码链

```
binary frame
  ↓ liqi-frame.ts: 解 Wrapper 双重包装（外层 .lq.Wrapper -> 内层 ResGameRecord）
  ↓ record-decode.ts: 处理 records[] / actions[].result 两种结构
  ↓ kyoku.ts: 归一化为局对象
  ↓ viewer.ts + points.ts + tile.ts: 出天凤 json
天凤 json
```

每一步都是纯函数，不依赖浏览器/扩展环境，所以能在 Playwright 里 `page.evaluate` 调用。

### 4.4 登录态管理

```python
# fetcher/browser.py
context = playwright.chromium.launch_persistent_context(
    user_data_dir="data/profile/",   # chmod 700
    headless=should_be_headless(),    # 首次 False，之后 True
    viewport={"width": 1280, "height": 800},
)
```

- **首次跑**：检测 profile 空 → headed 模式开窗 → 用户扫码 → 检测 `localStorage.account_id` 出现 → 关窗保存 profile
- **二次起**：profile 非空 → headless → 直接导航牌谱 URL

⚠️ profile 里会有雀魂 cookie/localStorage，**chmod 700**，写进 `.gitignore`（项目根加一份）。

## 五、落地分阶段（每阶段一个可验证产出）

### Phase 0 — vendor 解码内核（半小时）

只抄 7 个 lib 文件 + 4 个 assets，删 kbkn3 其余 95% 内容（Vue/UI/NAGA/MV3/popup）。写 NOTICE.md 标明出处和裁剪范围。

**产出**：`方案B/kbkn3-vendored/` 目录，能 `import` 不报错。

### Phase 1 — 打包 inject.js（半小时）

写极简 `inject/entry.ts`，调用 vendored 解码函数，把入口挂 `window.__majDecoder`。esbuild 打成单文件 IIFE。

**产出**：`方案B/inject/dist/inject.js` 单文件，能在浏览器 Console 里手动测试解码一段 binary。

### Phase 2 — Python 三模块（半天）

按上面架构表写 `browser.py` / `capture.py` / `tenhou_export.py`，每个不超过 50 行（用户要求"简单"）。`cli.py` 不超过 20 行串起来。

**产出**：模块单独 `python -m fetcher.browser` 能开窗、`python -m fetcher.capture` 能 print 帧。

### Phase 3 — 端到端联调（要用户配合扫码）

1. 用户跑 `python fetch.py <今天那条牌谱链接>` → 弹窗扫码登录
2. 第二次跑同一条 URL → 无头模式，落盘
3. `python3 src/stats.py data/games/<uuid>.json` → 出统计
4. 跟 mjai-reviewer 跑同一局对比，确认天凤 json 字段对齐

**产出**：end-to-end 跑通，README 写清用法。

## 六、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| Unity WebGL 加载慢导致 hook 时机不稳 | 中 | 偶尔抓不到首次 fetchGameRecord | 加重试：抓不到就 reload + 等 |
| 雀魂改 liqi 协议 | 中 | 解码挂 | 跟 kbkn3 升级 |
| Playwright Chromium 版本与雀魂检测冲突 | 低 | 雀魂可能识别为爬虫 | 留 channel="chrome" 选项用系统 Chrome |
| profile 泄露 | 低 | 登录态被复用 | chmod 700 + .gitignore |
| 批量误用导致封号 | **高（如果用户后期跑循环）** | 账号封禁 | README 显式警告：单条 URL 调用，**禁止循环遍历**；必要时加随机延迟 |
| 抄解码 bug | 中 | 统计偏差 | 跟 mjai-reviewer 输出对比一局 |

## 七、与现有项目对接

```
方案B/fetch.py <url>           # 浏览器侧拿数据
        ↓
data/games/<uuid>.json          # 天凤 json
        ↓
src/parse_tenhou.py             # 已写好
src/stats.py <files...>         # 已写好
```

`src/` 任何代码不改。

## 八、完成定义

执行 `python fetch.py "<URL>"` 拿到合法天凤 json，能被 `stats.py` 解析出统计指标，**且**与 mjai-reviewer 输出的同一局 json 字段一致 → 方案 B 成功。

## 九、放进 .gitignore（即便当前非 git 仓库，未来可能转）

```
方案B/data/profile/
方案B/inject/node_modules/
方案B/inject/dist/
data/games/*.json
data/config.json
```

## 十、立刻可做 vs 要等用户的

**立刻做**（Phase 0/1/2，全本地代码工作）：
- vendor kbkn3、写 inject、写三个 Python 模块、写 esbuild 打包

**要等用户做**（Phase 3）：
- 装 Playwright（`pip install playwright && playwright install chromium`）
- 首次跑脚本扫码登录
- 提供测试牌谱链接（已有：今天那条）
