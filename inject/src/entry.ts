// 注入页面后挂在 window.__majDecoder 上的极简 API。
// 单一职责：把一段 fetchGameRecord 响应的二进制 payload 转成天凤 json。
// 不做任何浏览器侧抓帧/落盘，那些归 Python。

import { decodeGameRecord } from "../../vendored/kbkn3/lib/record-decode";
import { parse } from "../../vendored/kbkn3/content-scripts/dd";

declare global {
  interface Window {
    __majDecoder: {
      // base64 解出来的二进制 → 天凤 TenhouMessage 对象
      toTenhou: (b64: string) => any;
      version: string;
    };
  }
}

function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

window.__majDecoder = {
  toTenhou(b64: string) {
    const bytes = b64ToBytes(b64);
    const decoded = decodeGameRecord(bytes);
    return parse(decoded);
  },
  version: "1.0.0+kbkn3-v1.5.1",
};
