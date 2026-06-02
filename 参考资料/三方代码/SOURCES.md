# 三方代码来源

这些目录原本是 `git clone` 下来的，已删除其内嵌 `.git` 目录（避免与父仓库的 git 冲突），源码作为参考资料整体追踪。**不会从上游同步更新**——若需同步，按下表 URL + commit 重新 clone。

| 目录 | 上游 | 截取 commit | 用途 |
|---|---|---|---|
| `MajsoulPaipuAnalyzer/` | https://github.com/zyr17/MajsoulPaipuAnalyzer | `54795de86224` (master) | 当初参考的 Cocos 时代注入式爬虫，技术对比用 |
| `tensoul/` | https://github.com/Equim-chan/tensoul | `f840fae039b5` (main) | 雀魂 protobuf → 天凤 json 转换器；曾用于 token 路线，含国服补丁 |
| `mjai-reviewer/` | https://github.com/Equim-chan/mjai-reviewer | `2dc5ec5c8b28` (master) | 单局 AI 复盘工具（备选，可拿天凤 json 喂它） |
| `kbkn3.tar.gz` + `kbkn3-上游解压/` | https://github.com/kbkn3/MahjongSoul-review-supporter | tag `v1.5.1` | **核心**：本项目解码内核来源（见 `vendored/kbkn3/NOTICE.md`） |

许可证：各项目源码遵循各自 LICENSE（Apache-2.0 / MIT 等），未修改源码。tensoul 的 `server_config.js` 有国服适配补丁（gateways 兼容 region_urls），属本仓库的修改。
