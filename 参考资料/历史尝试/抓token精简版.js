(function(){function scan(t,d){try{var u=new Uint8Array(d.buffer||d);if(u.length>=4096)return;var s='';for(var i=0;i<u.length;i++)s+=(u[i]>31&&u[i]<127?String.fromCharCode(u[i]):'.');if(/oauth|[Ll]ogin|token|[Aa]uth/.test(s)){console.log('%c['+t+'帧] '+s,'color:#06c');var m=s.match(/[0-9a-f]{32,}/gi);if(m)m.forEach(function(h){console.log('%cTOKEN? '+h,'color:red;font-size:16px;font-weight:bold')});}}catch(e){}}
var os=WebSocket.prototype.send;WebSocket.prototype.send=function(d){scan('发送',d);return os.apply(this,arguments)};
var od=Object.getOwnPropertyDescriptor(WebSocket.prototype,'onmessage');
Object.defineProperty(WebSocket.prototype,'onmessage',{configurable:true,set:function(fn){var w=function(ev){scan('接收',ev.data);return fn.apply(this,arguments)};od.set.call(this,w)},get:function(){return od.get.call(this)}});
var oa=WebSocket.prototype.addEventListener;WebSocket.prototype.addEventListener=function(t,fn){if(t==='message'){var w=function(ev){scan('接收',ev.data);return fn.apply(this,arguments)};return oa.call(this,t,w)}return oa.apply(this,arguments)};
console.log('%c✅ hook 已装(收+发)，现在去登录','color:#0a0;font-size:14px;font-weight:bold')})()
