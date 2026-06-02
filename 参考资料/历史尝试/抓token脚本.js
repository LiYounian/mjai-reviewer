// ============================================================
// 雀魂 access_token 抓取探针
// 用法:
//   1. 浏览器打开雀魂国服 https://game.maj-soul.com/1/ (先别登录，或先退出登录)
//   2. F12 -> Console，把本文件全部内容粘贴进去回车
//   3. 看到 "✅ WS hook 已安装" 后，去登录(账号密码/扫码都行)
//   4. 登录过程中 Console 会用红字打印 [可能的 access_token]
//   5. 把那串 32 位以上的十六进制字符串发给 Claude
//
// 原理: hook WebSocket 的收发，把 protobuf 二进制帧里的可见字符串抠出来,
//        匹配长十六进制串(access_token 的典型形态) 并高亮打印。
// 只读不改任何数据，登录完即可关页面。
// ============================================================
(function () {
  function bytesToAscii(data) {
    let u8;
    try {
      u8 = new Uint8Array(data instanceof ArrayBuffer ? data : (data.buffer || data));
    } catch (e) { return ""; }
    let s = "";
    for (const b of u8) s += (b >= 32 && b < 127) ? String.fromCharCode(b) : ".";
    return s;
  }

  function scan(tag, data) {
    const s = bytesToAscii(data);
    // access_token: 一长串十六进制(>=32位)；顺带把 login 帧整体打印备查
    const hex = s.match(/[0-9a-f]{32,}/gi);
    if (hex && hex.length) {
      console.log("%c[可能的 access_token] (" + tag + ")", "color:#fff;background:#c00;padding:2px 6px;font-weight:bold");
      hex.forEach(h => console.log("%c    " + h, "color:#c00;font-size:14px"));
    }
    if (/oauth|[Ll]ogin/.test(s)) {
      console.log("%c[login 帧可读内容] (" + tag + ")", "color:#06c;font-weight:bold", s);
    }
  }

  const origSend = WebSocket.prototype.send;
  WebSocket.prototype.send = function (data) {
    try { scan("发送", data); } catch (e) {}
    return origSend.apply(this, arguments);
  };

  const origAdd = WebSocket.prototype.addEventListener;
  WebSocket.prototype.addEventListener = function (type, fn, ...rest) {
    if (type === "message") {
      const wrapped = function (ev) {
        try { scan("接收", ev.data); } catch (e) {}
        return fn.apply(this, arguments);
      };
      return origAdd.call(this, type, wrapped, ...rest);
    }
    return origAdd.apply(this, arguments);
  };

  console.log("%c✅ WS hook 已安装，现在去登录(或退出后重新登录)，留意红字输出", "color:#0a0;font-weight:bold;font-size:14px");
})();
