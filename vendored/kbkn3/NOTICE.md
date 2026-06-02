# Vendored from kbkn3/MahjongSoul-review-supporter

Source: <https://github.com/kbkn3/MahjongSoul-review-supporter>
Tag: **v1.5.1** (commit on tag, downloaded 2026-06-01)
License: **Apache-2.0** (full text in `./LICENSE`)

## What's vendored

雀魂牌谱二进制 → 天凤 json 的解码内核，共 9 个 TS 文件 + 5 个 JSON + 1 个 protobuf 静态生成器。

```
lib/
  liqi-schema.ts        unchanged
  liqi-frame.ts         unchanged
  record-decode.ts      unchanged
  constants.ts          unchanged
  tile.ts               unchanged
  kyoku.ts              unchanged
  points.ts             unchanged
  cfg.ts                unchanged
content-scripts/
  dd.ts                 unchanged
assets/majsoul/
  liqi-proto.js         unchanged (4.67 MB, pbjs 静态生成)
  liqi-proto.d.ts       unchanged
  cfg/{fan,level,matchmode,character}.json   unchanged
LICENSE                 Apache-2.0 全文
```

## What's NOT vendored (deliberately removed)

裁掉了 95% 的上游内容，全部为浏览器扩展专用、与"protobuf → 天凤 json"无关：

- `lib/ws-capture.ts` — 浏览器内 WebSocket hook（Python 侧自己做）
- `lib/viewer.ts`, `lib/naga.ts` — NAGA URL 生成（不需要）
- `lib/messages.ts` — Chrome 扩展消息类型
- `entrypoints/` 整个目录 — MV3 background / content / popup
- `components/`, `composables/`, `options/` — Vue UI
- `public/`, `imgs/`, `docs/`, `mise.toml`, `package*.json`, `tsconfig*` 等

## Modifications

**截至当前：未修改任何 vendored 文件。** 上游代码逐字保留。

如以后修改任一 vendored 文件，按 Apache-2.0 §4(b) 要求，须在该文件顶部加显著修改声明，并在此处追记。

## How it's used

外部包装 `inject/src/entry.ts`（在项目根，不在本目录）import 这些文件，esbuild 打成单文件 IIFE `inject/dist/inject.js`，由 Python 侧 Playwright 通过 `page.add_init_script()` 注入到雀魂页面。详见项目根 `docs/架构说明.md`。
