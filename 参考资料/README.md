# 参考资料

跟当前抓取/解析链路**没有运行依赖**的一切：历史尝试、废弃文档、第三方源码。

留着是因为：
- **历史尝试** 记录了"为什么不走那些路"——下次有人想读 token、想用油猴脚本，先看这里别再撞墙
- **历史文档** 记录了项目演进的判断脉络
- **三方代码** 是当初调研/抄解码内核时的对比对象，将来雀魂协议变了还要回来看

主目录的代码（`src/` / `inject/` / `vendored/` / `fetch.py` / `stats.py`）**完全不依赖本目录**，删掉本目录不影响项目运行。

## 子目录

### 历史尝试/

token 路线探索期写的代码，**已全部废弃**：

| 文件 | 当初做什么 | 为什么废弃 |
|---|---|---|
| `parse_link.py` | 探测能否匿名 HTTP GET 雀魂分享链接拿到牌谱 | 拿不到，HTML 是空壳 SPA。结论：必须登录后走 WebSocket |
| `majsoul_config.py` | 复现 tensoul 的服务器配置探测（取 liqi.json + 网关） | 走通了，但 token 路线本身错（见下条），下游用不上 |
| `抓token脚本.js` / `抓token精简版.js` | 浏览器 Console 粘贴脚本，hook WebSocket 抓 access_token | 雀魂 Unity WebGL 把 token 封进 wasm 闭包，且即便抓到 UUID 也是 random_key 不是登录 token。详见 `历史文档/token获取_2026-06-01结论.md` |
| `liqi.json` | majsoul_config.py 当初下回来的雀魂 protobuf schema (~316KB) | 现在用的是 `vendored/kbkn3/` 里的版本，这份是早期备份 |
| `sample_tenhou.json` | 手写的天凤 json 样例，用于在还没拉到真牌谱前先开发 stats.py | 现在已有真牌谱，留作 stats.py 的最小回归测试样本 |
| `config.json.敏感_勿入库` | token 路线时存的雀魂账号 + access_token（**含真实邮箱+token**） | **本地 chmod 600 + .gitignore 双重保护，绝不入库**。token 已无效（雀魂会过期），留作"格式参考"——若后人想复现 token 路线（不推荐），看它格式 |

### 历史文档/

| 文件 | 内容 |
|---|---|
| `最初方案.md` | 项目最早的设计方案。**已被替代**（数据获取方案已变），但记录了原始需求和指标体系（顺位/和了率/立直收支/段位...），新版 README 只给浓缩版 |
| `方案B_自做提取器.md` | 调研期"方案 A vs B vs C"的对比与选型记录。当时这条路被命名为"方案 B"，现已成为正式实现（即根目录的代码）。读它能理解当初为什么这么选 |
| `token获取_2026-06-01结论.md` | token 路线证伪的实测过程：试了 oauth2Login、网页内 fetchGameRecord，撞到 error 109、Unity 闭包两堵墙的全过程 |
| `参考项目通读笔记.md` | 当初对 MajsoulPaipuAnalyzer（Cocos 时代的注入式爬虫）的逐文件技术笔记 (46KB)。新版雀魂下其代码已失效，但架构判断仍有价值（数据流分层、API 名）|

### 三方代码/

参考用的开源项目，**未修改**（除 tensoul 的国服补丁外）：

| 目录 | 项目 | 当初为什么参考 | 现在状态 |
|---|---|---|---|
| `MajsoulPaipuAnalyzer/` | [zyr17/MajsoulPaipuAnalyzer](https://github.com/zyr17/MajsoulPaipuAnalyzer) | Cocos 时代的注入式爬虫（C++ + Electron） | 新版雀魂已失效，作为架构对比 |
| `tensoul/` | [Equim-chan/tensoul](https://github.com/Equim-chan/tensoul) | 雀魂 protobuf → 天凤 json 的 Node 转换器；曾尝试用它（含国服补丁 `server_config.js`） | 作者已弃坑（2025-06）；token 路线证伪后未投入使用 |
| `mjai-reviewer/` | [Equim-chan/mjai-reviewer](https://github.com/Equim-chan/mjai-reviewer) | 单局 AI 复盘工具（Mortal/akochan 模型）。本项目可拿天凤 json 直接喂它 | 备选 AI 复盘引擎 |
| `kbkn3.tar.gz` | [kbkn3/MahjongSoul-review-supporter v1.5.1](https://github.com/kbkn3/MahjongSoul-review-supporter) | 当前唯一适配 Unity WebGL 的开源解码实现 | **核心来源**：方案 B 的 protobuf 解码内核全部抄自此处，见 `方案B/kbkn3-vendored/` |
| `kbkn3-上游解压/` | 同上的解压目录 | 留它做溯源（包含 fixture / 测试，验证 vendored 解码内核用） | vendor 完后未再修改 |

## 想恢复某段尝试

直接拷文件到顶层即可（依赖：见各文件头部 docstring 或 import 行）。
