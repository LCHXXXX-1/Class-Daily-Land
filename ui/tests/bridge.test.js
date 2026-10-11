// ============================================================================
//  桥接协议测试：在 Node 里用最小桩件跑通 host.js 的两条宿主路径。
//  验证这套方案里唯一「必须写两遍」的部分 —— 宿主适配器是否真的成立。
//
//  跑法： node tests/bridge.test.js
//  不依赖任何 npm 包，也不需要浏览器。
// ============================================================================
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const HOST_JS = fs.readFileSync(path.join(__dirname, "..", "host.js"), "utf8");

const GLOBALS = {
  console, setTimeout, clearTimeout, JSON, Map, Set, Promise, Error,
  Object, Array, Math, String, Number,
};

/**
 * 真浏览器里 window 一定有 addEventListener（host.js 用它挂全局错误上报），
 * 但这里的 window 是个手搓对象，得补上，否则跑不到桥接逻辑就崩在注册那一步。
 * 返回的 handlers 让用例可以手动触发一个「脚本错误」。
 */
function stubWindow(extra) {
  const handlers = new Map();
  const win = Object.assign({
    addEventListener(type, fn) {
      if (!handlers.has(type)) handlers.set(type, []);
      handlers.get(type).push(fn);
    },
  }, extra);
  win.__fire = (type, event) => (handlers.get(type) || []).forEach((fn) => fn(event));
  return win;
}

// ---------------------------------------------------------------- 用例 1：.NET / WebView2 路径
async function testWebView2() {
  const out = { host: null, calls: [], rpc: null, event: null, errorPath: null, notifications: [], hookReport: null };
  let listener = null;

  const win = stubWindow({
    chrome: {
      webview: {
        postMessage(json) {
          const req = JSON.parse(json);

          // 通知（单程、无 id）：记下来，不回包
          if (req.event) {
            out.notifications.push(req);
            if (req.event === "ui.error" && !out.hookReport) out.hookReport = req.payload;
            return;
          }

          out.calls.push(req.method);
          // 模拟 C# 侧：收到请求 → 派发 → PostWebMessageAsString 回包
          setTimeout(() => {
            const reply =
              req.method === "app.getVersion"
                ? { id: req.id, result: { version: "4.3.0", host: "webview2" } }
                : req.method === "boom"
                  ? { id: req.id, error: "宿主报错：磁盘只读" }
                  : { id: req.id, result: { ok: true } };
            listener({ data: JSON.stringify(reply) });
            // 顺便验宿主主动推事件
            listener({ data: JSON.stringify({ event: "island.state", payload: { visible: true } }) });
          }, 5);
        },
        addEventListener(_evt, fn) { listener = fn; },
      },
    },
  });

  const sandbox = Object.assign({}, GLOBALS, { window: win });

  vm.runInContext(HOST_JS, vm.createContext(sandbox));
  const host = sandbox.window.host;
  out.host = host.HOST;

  host.on("island.state", (p) => { out.event = p; });
  out.rpc = await host.invoke("app.getVersion");
  try { await host.invoke("boom"); } catch (e) { out.errorPath = e.message; }

  // 通知通道：页面 → 宿主，单程
  host.notify("ui.ready", { page: "general" });

  // 全局错误钩子：脚本抛错应当被上报成 ui.error
  win.__fire("error", { message: "canvas.getContext 不是函数", filename: "pages/settings.js", lineno: 42 });

  return out;
}

// ---------------------------------------------------------------- 用例 2：Python / QtWebEngine 路径
async function testQtWebEngine() {
  const out = { host: null, calls: [], rpc: null, handshaked: false, notified: [] };
  const handlers = [];

  const fakeBridge = {
    reply: { connect(fn) { handlers.push(fn); out.handshaked = true; } },
    invoke(json) {
      const req = JSON.parse(json);

      // 通知（ui.ready / ui.error）没有 id，Python 侧的桥必须原样放过去、不回包
      if (req.event) { out.notified.push(req.event); return; }

      out.calls.push(req.method);
      // 模拟 Python 侧：Slot invoke → reply 信号
      setTimeout(() => handlers.forEach((fn) => fn(JSON.stringify(
        { id: req.id, result: { version: "4.3.0", host: "qtwebengine" } }))), 5);
    },
  };

  const sandbox = Object.assign({}, GLOBALS, {
    // Qt 把 qt / QWebChannel 注入成全局（浏览器里裸名即可解析），这里照样给
    qt: { webChannelTransport: { __transport: true } },
    window: stubWindow({ qt: { webChannelTransport: { __transport: true } } }),
    QWebChannel: function (_transport, cb) { cb({ objects: { bridge: fakeBridge } }); },
  });

  vm.runInContext(HOST_JS, vm.createContext(sandbox));
  const host = sandbox.window.host;
  out.host = host.HOST;

  await host.ready;                       // 等 QWebChannel 握手
  out.rpc = await host.invoke("app.getVersion");
  host.notify("ui.ready", { page: "general" });
  return out;
}

(async () => {
  const wv2 = await testWebView2();
  const qt = await testQtWebEngine();
  console.log("=== .NET / WebView2 路径 ===");
  console.log(JSON.stringify(wv2, null, 2));
  console.log("\n=== Python / QtWebEngine 路径 ===");
  console.log(JSON.stringify(qt, null, 2));

  const pass =
    wv2.host === "webview2" && wv2.rpc && wv2.rpc.host === "webview2" &&
    wv2.event && wv2.event.visible === true && /宿主报错/.test(wv2.errorPath || "") &&
    // 通知通道：单程消息不带 id，宿主认得出来
    wv2.notifications.length === 2 &&
    wv2.notifications[0].event === "ui.ready" && wv2.notifications[0].id === undefined &&
    wv2.notifications[1].event === "ui.error" &&
    // 全局错误钩子：脚本抛错 → ui.error 上报
    wv2.hookReport && /不是函数/.test(wv2.hookReport.message) &&
    qt.host === "qtwebengine" && qt.handshaked && qt.rpc && qt.rpc.host === "qtwebengine" &&
    qt.notified.length === 1 && qt.notified[0] === "ui.ready";
  console.log("\n判定:", pass ? "两条宿主路径全部通过" : "存在失败项");
  process.exit(pass ? 0 : 1);
})();
