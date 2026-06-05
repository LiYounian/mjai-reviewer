<!--
这个文件是给 GitHub Release 页面用的"用户向更新内容"。
每次发新 tag 前，把里面的内容改成那个版本的变更。
风格指南: 写用户能看到/感受到的变化，不写 commit hash / 内部代码改动。

下载:
- macOS (Apple Silicon): mjai-tool-macos-arm64.zip
- Windows (x64): mjai-tool-windows-x64.zip
打开方式见 README "给非程序员朋友的简易用法"。
-->

## ✨ 新功能

- **番型先达成榜**：每行一种番型，看每个番型是谁先胡的、在第几局达成。支持「全部 / 无副露(门清) / 有副露」三种过滤切换
- **总览表新增三列**：单次最高赢、单次最高放铳、单次最高被自摸（按每条和了单独算）
- **浏览器界面化抓取**：双击启动后浏览器打开 → 登录雀魂 → 粘链接 → 实时进度日志 → 抓完直接看分析。零命令行
- **保存位置可改**：抓取页面顶部"💾 保存位置"一行可以改到任意目录
- **抓取产物双输出**：除了天凤格式（喂给 mjai-reviewer / NAGA 等 AI 工具用），同时多存一份"雀魂中间态 JSON"，含完整事件流和准确时间戳

## 🛠 改进

- 启动脚本一次性自动检测/安装 Python + Chromium + 构建 inject.js，朋友拿到包啥都不用准备
- 端口冲突（重复双击启动）会友好询问"杀掉重启 / 用现有的 / 退出"，不再闪退报错
- 粘 URL 兼容多种格式：「雀魂牌谱:https://...」「https://...」「paipu=...」「裸 ID」都能识别
- 番型表去掉排序下拉，固定按字典序

## 🐛 修复

- Windows 抓取时报「No such file or directory: \tmp\maj-last-captured.bin」
- macOS 上抓取链路签名相关错误

## 📦 下载

- **macOS** (Apple Silicon, M1/M2/M3): `mjai-tool-macos-arm64.zip`
- **Windows** (x64): `mjai-tool-windows-x64.zip`

解压后双击文件夹里的 `mjai-tool` (mac) 或 `mjai-tool.exe` (win)。第一次打开系统会拦截，按下面方式绕过：

- **macOS**：在 Finder 里右键点 `mjai-tool` → 打开 → 弹窗里再点"打开"
- **Windows**：SmartScreen 提示时点"更多信息" → "仍要运行"

数据保存在 `~/.mjai-tool/`（mac）或 `%USERPROFILE%\.mjai-tool\`（win），里面会自动建 games/raw/profile 三个子目录。
