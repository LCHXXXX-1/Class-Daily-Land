// ============================================================================
//  host.js —— 宿主桥。整个前端唯一需要分辨 .NET / Python 的地方。
//  ---------------------------------------------------------------------------
//  页面代码只调 host.invoke / host.on，永远不碰 WebView2 或 Qt 的 API。
//  用浏览器直接打开时自动降级为 mock 数据，界面可以脱离宿主开发调试。
//
//  这里用经典脚本（不是 ES module）：file:// 下浏览器会因 CORS 拒绝加载 module，
//  那样预览稿就双击打不开了。宿主里若想用 module，WebView2 可配虚拟主机映射。
// ============================================================================

window.host = (function () {

  const HOST = (() => {
    if (window.chrome && window.chrome.webview) return "webview2";          // .NET：WPF + WebView2
    if (window.qt && window.qt.webChannelTransport) return "qtwebengine";   // Python：PySide6 + QWebEngineView
    return "browser";                                                      // 预览稿：降级 mock
  })();

  let seq = 0;
  const pending = new Map();       // id -> {resolve, reject}
  const listeners = new Map();     // event -> Set<fn>
  let qtBridge = null;             // Qt 握手后拿到的 QObject

  // ---------------------------------------------------------------- 收发

  function fire(event, payload) {
    for (const fn of listeners.get(event) || []) {
      try { fn(payload); } catch (err) { console.error("[host] " + event + " 处理失败", err); }
    }
  }

  function settle(message) {
    const entry = pending.get(message.id);
    if (!entry) return;
    pending.delete(message.id);
    if (message.error) entry.reject(new Error(message.error));
    else entry.resolve(message.result);
  }

  function send(message) {
    const json = JSON.stringify(message);
    if (HOST === "webview2") {
      window.chrome.webview.postMessage(json);   // C# 侧：WebMessageReceived
    } else if (HOST === "qtwebengine") {
      qtBridge.invoke(json);                     // Python 侧：Bridge 的 invoke 槽
    }
  }

  // ---------------------------------------------------------------- 初始化

  // Qt 需要先握手拿到 QWebChannel 对象；WebView2 开箱即用。页面等这个 Promise 即可。
  const ready = (async () => {
    if (HOST !== "qtwebengine") return HOST;
    // qwebchannel.js 由 Qt 提供，HTML 里需引：
    //   <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
    const channel = await new Promise((resolve) => new QWebChannel(qt.webChannelTransport, resolve));
    qtBridge = channel.objects.bridge;
    qtBridge.reply.connect((json) => {
      const message = JSON.parse(json);
      // 与 WebView2 那条路保持一致：带 event 的是宿主主动推送，不能当回包处理。
      // （少了这个分支，宿主推的进度 / 日志事件会全部被丢掉。）
      if (message && message.event) fire(message.event, message.payload);
      else settle(message);
    });
    return HOST;
  })();

  if (HOST === "webview2") {
    window.chrome.webview.addEventListener("message", (e) => {
      const message = typeof e.data === "string" ? JSON.parse(e.data) : e.data;
      if (message && message.event) fire(message.event, message.payload);
      else settle(message);
    });
  }

  // ---------------------------------------------------------------- 公开 API

  /**
   * 调用宿主的一个方法。
   * @param {string} method 例如 "settings.getAll"
   * @param {object} [params]
   * @returns {Promise<any>}
   */
  function invoke(method, params) {
    params = params || {};
    if (HOST === "browser") return Promise.resolve(mock(method, params));

    const id = ++seq;
    return Promise.race([
      new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        send({ id: id, method: method, params: params });
      }),
      // 宿主没响应时不至于永远挂着。
      // 给到 60 秒：安装插件要走下载 + 解包，同步索引要试多个镜像，
      // 15 秒会让正常操作被误判成超时。
      new Promise((_, reject) => setTimeout(() => {
        if (pending.delete(id)) reject(new Error("调用超时：" + method));
      }, 60000)),
    ]);
  }

  /**
   * 订阅宿主主动推送的事件（同步进度、灵动岛状态变化等）。
   * @param {string} event
   * @param {(payload:any)=>void} fn
   */
  function on(event, fn) {
    if (!listeners.has(event)) listeners.set(event, new Set());
    listeners.get(event).add(fn);
  }

  /**
   * 给宿主发一条「通知」：单程，不等回包。
   * 目前两种用途 ——
   *   ui.ready  页面外壳已挂好，宿主可以撤掉「正在加载」并停止启动超时计时
   *   ui.error  页面脚本出错 / 某次 RPC 失败，宿主可以把「一片白」换成一句人话
   * 浏览器里只打日志，不报错。
   */
  function notify(event, payload) {
    if (HOST === "browser") {
      console.debug("[host] " + event, payload || {});
      return;
    }

    // 通道本身断了也不能让页面再抛一个错，否则就是「报错的代码在报错」
    try { send({ event: event, payload: payload || {} }); } catch (err) { /* 无路可走，认了 */ }
  }

  // 页面里任何一处脚本抛错都往上报。宿主拿到之后，兜底面板就能写出真正的原因，
  // 而不是只给用户看一个白窗口。（ES module 之外的老式脚本里，这个监听最靠得住。）
  window.addEventListener("error", (e) => {
    notify("ui.error", {
      phase: "script",
      message: e.message || "脚本错误",
      file: e.filename || "",
      line: e.lineno || 0,
    });
  });

  window.addEventListener("unhandledrejection", (e) => {
    const reason = e.reason;
    notify("ui.error", {
      phase: "promise",
      message: (reason && reason.message) ? reason.message : String(reason || ""),
    });
  });

  // ==========================================================================
  //  以下只服务于「用浏览器直接打开预览稿」的场景，宿主里不会执行。
  //  数据形状与两端宿主的真实返回保持一致。
  // ==========================================================================

  const MOCK_SETTINGS = {
    // 通用 · 主窗口
    show_main_window: true,
    main_width_ratio: 0.28,
    main_opacity: 0.94,
    main_font_size: 14,
    // 通用 · 作业滚动
    main_auto_scroll: true,
    main_scroll_interval: 60,
    main_scroll_step: 2,
    main_scroll_pause: 3,
    // 通用 · 启动与更新
    check_update_on_start: true,
    block_update_on_source: true,
    // 外观
    theme_mode: "system",
    anim_fade_window: true,
    anim_fade_panel: true,
    anim_fade_text: false,
    anim_duration: 320,
    settings_mica: true,
    // 灵动岛 · 主岛
    show_island: true,
    island_top_margin: 8,
    island_alert_width: 420,
    island_alert_hold_ms: 1200,
    island_hide_on_fullscreen: true,
    island_show_wakeup_anim: true,
    // 灵动岛 · 副岛
    show_sub_island: true,
    sub_island_collapsed: false,
    sub_island_auto_collapse_sec: 30,
    // 课表与提醒
    island_countdown_sec: 60,
    schedule_advance_minutes: 2,
    schedule_time_offset_seconds: 0,
    // 插件
    disabled_plugins: [],
  };

  const MOCK_PLUGINS = [
    { id: "class.lchxxxx-1.clock", name: "时钟", version: "1.2.0",
      desc: "在下拉面板显示当前时间与倒数日", requires: [], enabled: true, loaded: true },
    { id: "class.hexwisp72.weather", name: "天气", version: "2.0.1",
      desc: "副岛显示今日温度与天气图标", requires: ["requests"], enabled: true, loaded: true },
    { id: "class.hexwisp72.legacy-hw", name: "旧版作业助手", version: "0.9.0",
      desc: "按 Python 版 API 编写，.NET 宿主无法加载", requires: [], enabled: false, loaded: false,
      failure: "缺少入口程序集 main.dll" },
  ];

  const MOCK_MARKET = {
    id: "class.hexwisp72.disaster-alert", name: "灾害预警", version: "1.0.3",
    desc: "紧急警报条，独占主岛显示", author: "hexwisp72", installedVersion: null,
  };

  /**
   * 市场索引的可变副本。刻意把每种状态都摆一个进去，浏览器预览里
   * 一眼能看出各分支长什么样（也让 render 测试能断言到）。
   */
  const MOCK_MARKET_ENTRIES = [
    { id: "class.lchxxxx-1.clock", name: "时钟", version: "1.2.0", description: "下拉面板显示当前时间与倒数日",
      author: "LCHXXXX-1", installed: true, installedVersion: "1.2.0", status: "installed", updateAvailable: false },
    { id: "class.hexwisp72.weather", name: "天气", version: "2.0.1", description: "副岛显示今日温度与天气图标",
      author: "hexwisp72", installed: true, installedVersion: "1.9.0", status: "update", updateAvailable: true },
    { id: "class.hexwisp72.disaster-alert", name: "灾害预警", version: "1.0.3", description: "紧急警报条，独占主岛显示",
      author: "hexwisp72", installed: false, installedVersion: "", status: "not_installed", updateAvailable: false },
    { id: "class.hexwisp72.legacy-hw", name: "旧版作业助手", version: "0.9.0", description: "按 Python 版 API 编写",
      author: "hexwisp72", installed: true, installedVersion: "0.9.0", status: "failed", updateAvailable: false,
      loadError: "缺少入口程序集 main.dll" },
    { id: "class.lchxxxx-1.broken", name: "索引坏掉的插件", version: "0.0.0", description: "",
      author: "", installed: false, installedVersion: "", status: "invalid", updateAvailable: false,
      problem: "索引里缺少 sha256 字段，无法校验下载内容" },
  ];

  const MOCK_PACKAGES = [
    { name: "requests", version: "2.32.3", installed: true, installedVersion: "2.32.3", manual: false,
      usedBy: ["class.hexwisp72.weather"], status: "installed" },
    { name: "pillow", version: "11.0.0", installed: false, installedVersion: "", manual: false,
      usedBy: [], status: "not_installed" },
    { name: "numpy", version: "2.0.0", installed: true, installedVersion: "1.26.4", manual: false,
      usedBy: ["class.lchxxxx-1.chart"], status: "update" },
    { name: "colorama", version: "0.4.6", installed: true, installedVersion: "0.4.6", manual: true,
      usedBy: [], status: "installed" },
  ];

  const MOCK_MARKET_SOURCES = [
    { value: "official", label: "官方服务器" },
    { value: "github", label: "GitHub" },
    { value: "gitee", label: "Gitee" },
  ];

  const MOCK_MARKET_STATE = { source: "github", packagesSource: "github", lastSync: "" };

  /** 预览稿里的最大化状态（无边框窗口的标题栏按钮要跟着换图标）。 */
  let MOCK_WINDOW_MAXIMIZED = false;

  function mockMarketStatus(extra) {
    const entries = MOCK_MARKET_ENTRIES.map((e) => ({ ...e }));
    return Object.assign({
      count: entries.length,
      source: MOCK_MARKET_STATE.source,
      sourceLabel: (MOCK_MARKET_SOURCES.find((s) => s.value === MOCK_MARKET_STATE.source) || {}).label || "",
      sourceOptions: MOCK_MARKET_SOURCES,
      lastSync: MOCK_MARKET_STATE.lastSync,
      entries: entries,
    }, extra || {});
  }

  function mockPackagesStatus(extra) {
    return Object.assign({
      source: MOCK_MARKET_STATE.packagesSource,
      sourceLabel: (MOCK_MARKET_SOURCES.find((s) => s.value === MOCK_MARKET_STATE.packagesSource) || {}).label || "",
      sourceOptions: MOCK_MARKET_SOURCES,
      lastSync: MOCK_MARKET_STATE.lastSync,
      entries: MOCK_PACKAGES.map((e) => ({ ...e })),
    }, extra || {});
  }

  const SYNC_LOG = [
    "[1/4] 拉取索引 …",
    "  · raw.githubusercontent.com 命中（218 ms）",
    "[2/4] 解析 list.json：3 个条目",
    "[3/4] 比对本地版本 …",
    "  · class.lchxxxx-1.clock 1.1.0 → 1.2.0",
    "[4/4] 完成",
  ];

  // ---- 二级对话框用到的可变数据（浏览器里可以真的改，方便预览稿自测）----

  const MOCK_HOLIDAYS = [{ start: "2026-10-01", end: "2026-10-07", name: "国庆" }];
  const MOCK_MAKEUP = [{ date: "2026-10-11", asWeekday: 4 }];
  const MOCK_WEEKEND = {
    morningSplit: "12:00",
    afternoonPeriods: [
      { name: "午1", start: "13:30", end: "14:15" },
      { name: "午2", start: "14:25", end: "15:10" },
    ],
    courses: ["自习", "班会"],
  };
  const MOCK_DUTY = ["张三", "李四", "王五"];
  const MOCK_HOMEWORK = [
    { subject: "语文", date: "10-12", content: "背诵《岳阳楼记》全文" },
    { subject: "语文", date: "10-12", content: "作文：我的周末" },
    { subject: "数学", date: "10-13", content: "练习册 P32-35" },
    { subject: "英语", date: "", content: "背单词 Unit 4" },
  ];

  /**
   * 把作业按科目归组，形状与两端宿主返回的 homework.get 一致。
   * 注意：**按科目分组**（不按科目+日期），date 取该科目第一个非空的 ——
   * 这是两端服务 HomeworkService.Grouped() 的既有语义，别在这里改成别的分法。
   */
  function mockHomeworkPayload() {
    const items = MOCK_HOMEWORK.map((item, index) => ({ index: index, ...item }));

    const groups = [];
    for (const item of items) {
      const subject = (item.subject || "").trim() || "未分类";
      let group = groups.find((g) => g.subject === subject);
      if (!group) { group = { subject: subject, date: "", entries: [] }; groups.push(group); }
      if (!group.date && item.date) group.date = item.date;
      group.entries.push({ index: item.index, content: item.content });
    }

    return { items: items, groups: groups, count: items.length };
  }


  function mock(method, params) {
    switch (method) {
      case "app.getVersion":
        return {
          version: "4.3.0", platform: "win32", host: "browser", system: "Windows 11 专业版",
          configPath: "C:\\Users\\35350\\AppData\\Roaming\\ClassDailyLand",
          pluginsPath: "C:\\Users\\35350\\AppData\\Roaming\\ClassDailyLand\\plugins",
          // 预览稿照「无边框窗口」显示：两个宿主现在都是自绘标题栏
          window: { frame: "none", controls: ["minimize", "maximize", "close"] },
        };

      // ---------------- 无边框窗口的窗口控制 ----------------

      case "window.minimize":
        MOCK_WINDOW_MAXIMIZED = false;
        return { ok: true };

      case "window.toggleMaximize":
        MOCK_WINDOW_MAXIMIZED = !MOCK_WINDOW_MAXIMIZED;
        return { ok: true, maximized: MOCK_WINDOW_MAXIMIZED };

      case "window.close":
        return { ok: true };

      case "window.startMove":
        return { ok: true };   // 浏览器里没有窗口可拖，静默忽略

      case "settings.getAll":
        return Object.assign({}, MOCK_SETTINGS);

      case "settings.patch":
        Object.assign(MOCK_SETTINGS, params);
        return { ok: true };

      case "settings.reset":
        Object.assign(MOCK_SETTINGS, {
          show_main_window: true, main_width_ratio: 0.28, main_opacity: 0.94, main_font_size: 14,
          main_auto_scroll: true, main_scroll_interval: 60, main_scroll_step: 2, main_scroll_pause: 3,
          check_update_on_start: true, block_update_on_source: true, theme_mode: "system",
          anim_fade_window: true, anim_fade_panel: true, anim_fade_text: false, anim_duration: 320,
          settings_mica: true, show_island: true, island_top_margin: 8, island_alert_width: 420,
          island_alert_hold_ms: 1200, island_hide_on_fullscreen: true, island_show_wakeup_anim: true,
          show_sub_island: true, sub_island_collapsed: false, sub_island_auto_collapse_sec: 30,
          island_countdown_sec: 60, schedule_advance_minutes: 2, schedule_time_offset_seconds: 0,
        });
        return { ok: true };

      case "plugins.list":
        return { plugins: MOCK_PLUGINS };

      case "plugins.setEnabled":
        MOCK_PLUGINS.forEach((p) => { if (p.id === params.id) p.enabled = !!params.enabled; });
        return { ok: true, restartRequired: true };

      case "market.status":
      case "market.rescan":
        return mockMarketStatus();

      case "market.sync": {
        MOCK_MARKET_STATE.lastSync = new Date().toLocaleString("zh-CN", { hour12: false });
        return mockMarketStatus({ log: SYNC_LOG });
      }

      case "market.setSource":
        MOCK_MARKET_STATE.source = String(params.source || "github");
        MOCK_MARKET_STATE.lastSync = new Date().toLocaleString("zh-CN", { hour12: false });
        return mockMarketStatus({ log: ["已切换索引来源：" + MOCK_MARKET_STATE.source] });

      case "market.install": {
        const entry = MOCK_MARKET_ENTRIES.find((e) => e.id === params.id);
        if (!entry) return { ok: false, message: "索引里没有这个插件：" + params.id };
        if (entry.status === "invalid") return { ok: false, message: "索引记录不合法，装不了：" + entry.problem };
        entry.installed = true;
        entry.installedVersion = entry.version;
        entry.status = "installed";
        entry.updateAvailable = false;
        entry.loadError = "";
        return { ok: true, message: "已装上 " + entry.name + " v" + entry.version, restartRequired: true };
      }

      case "market.uninstall": {
        const entry = MOCK_MARKET_ENTRIES.find((e) => e.id === params.id);
        if (!entry) return { ok: false, message: "索引里没有这个插件：" + params.id };
        entry.installed = false;
        entry.installedVersion = "";
        entry.status = "not_installed";
        entry.updateAvailable = false;
        return { ok: true, message: "已卸掉 " + entry.name, restartRequired: true };
      }

      case "market.setEnabled": {
        const entry = MOCK_MARKET_ENTRIES.find((e) => e.id === params.id);
        if (!entry) return { ok: false, message: "索引里没有这个插件：" + params.id };
        if (params.enabled && entry.installed) entry.status = entry.updateAvailable ? "update" : "installed";
        else if (entry.installed) entry.status = "disabled";
        return { ok: true, restartRequired: true };
      }

      case "market.updateAll": {
        const items = [];
        for (const entry of MOCK_MARKET_ENTRIES) {
          if (!entry.updateAvailable) continue;
          const from = entry.installedVersion;
          entry.installedVersion = entry.version;
          entry.updateAvailable = false;
          entry.status = "installed";
          items.push({ id: entry.id, name: entry.name, success: true,
            message: from + " → " + entry.version });
        }
        return { items: items, restartRequired: items.length > 0,
          log: items.length ? [] : ["没有可更新的插件。"] };
      }

      case "packages.status":
      case "packages.sync":
        return mockPackagesStatus();

      case "packages.setSource":
        MOCK_MARKET_STATE.packagesSource = String(params.source || "github");
        return mockPackagesStatus();

      case "packages.install": {
        const pack = MOCK_PACKAGES.find((p) => p.name === params.name);
        if (pack) { pack.installed = true; pack.installedVersion = pack.version; pack.status = "installed"; }
        return { ok: true, message: "已装上依赖包 " + params.name };
      }

      case "packages.uninstall": {
        const pack = MOCK_PACKAGES.find((p) => p.name === params.name);
        if (pack && pack.usedBy.length) {
          return { ok: false, message: "还有插件在用：" + pack.usedBy.join("、") };
        }
        if (pack) { pack.installed = false; pack.installedVersion = ""; pack.status = "not_installed"; }
        return { ok: true, message: "已删除依赖包 " + params.name };
      }

      case "dialog.open":
        return { opened: false, reason: "预览模式下不打开对话框：" + params.id };

      case "app.openFolder":
        return { ok: true, path: "（预览模式）" + params.id };

      case "update.check":
        return { current: "4.3.0", latest: "4.3.0", hasUpdate: false };

      // ---------------- 二级对话框：假期 / 调休 / 周末 ----------------

      case "schedule.holidays.get":
        return { holidays: MOCK_HOLIDAYS.slice(), makeupDays: MOCK_MAKEUP.slice() };

      case "schedule.holidays.add":
        MOCK_HOLIDAYS.push({ start: params.start, end: params.end, name: params.name || "" });
        return { ok: true };

      case "schedule.holidays.remove":
        if (params.index >= 0 && params.index < MOCK_HOLIDAYS.length) MOCK_HOLIDAYS.splice(params.index, 1);
        return { ok: true };

      case "schedule.makeup.add":
        MOCK_MAKEUP.push({ date: params.date, asWeekday: Number(params.asWeekday) || 0 });
        return { ok: true };

      case "schedule.makeup.remove":
        if (params.index >= 0 && params.index < MOCK_MAKEUP.length) MOCK_MAKEUP.splice(params.index, 1);
        return { ok: true };

      case "schedule.weekend.get":
        return JSON.parse(JSON.stringify(MOCK_WEEKEND));

      case "schedule.weekend.set":
        MOCK_WEEKEND.morningSplit = params.morningSplit;
        MOCK_WEEKEND.afternoonPeriods = (params.afternoonPeriods || []).map((p) => ({ ...p }));
        MOCK_WEEKEND.courses = (params.courses || []).slice();
        return { ok: true };

      // ---------------- 二级对话框：值日生 ----------------

      case "duty.get":
        return { list: MOCK_DUTY.slice(), current: MOCK_DUTY[0] || "", index: 0 };

      case "duty.add":
        MOCK_DUTY.push(String(params.name));
        return { ok: true };

      case "duty.addMany":
        for (const name of (params.names || [])) MOCK_DUTY.push(String(name));
        return { ok: true, added: (params.names || []).length };

      case "duty.remove":
        if (params.index >= 0 && params.index < MOCK_DUTY.length) MOCK_DUTY.splice(params.index, 1);
        return { ok: true };

      // ---------------- 二级对话框：作业编辑器 ----------------

      case "homework.get":
        return mockHomeworkPayload();

      case "homework.add":
        if (!String(params.subject || "").trim() || !String(params.content || "").trim()) {
          return { ok: false, reason: "科目和作业内容都不能为空。" };
        }
        MOCK_HOMEWORK.push({
          subject: String(params.subject).trim(),
          content: String(params.content).trim(),
          date: String(params.date || "").trim(),
        });
        return { ok: true };

      case "homework.update":
        if (params.index >= 0 && params.index < MOCK_HOMEWORK.length) {
          MOCK_HOMEWORK[params.index] = {
            subject: String(params.subject || "").trim(),
            content: String(params.content || "").trim(),
            date: String(params.date || "").trim(),
          };
        }
        return { ok: true };

      case "homework.remove":
        if (params.index >= 0 && params.index < MOCK_HOMEWORK.length) MOCK_HOMEWORK.splice(params.index, 1);
        return { ok: true };

      case "homework.clearSubject":
        for (let i = MOCK_HOMEWORK.length - 1; i >= 0; i--) {
          const subject = (MOCK_HOMEWORK[i].subject || "").trim() || "未分类";
          if (subject === params.subject) MOCK_HOMEWORK.splice(i, 1);
        }
        return { ok: true };

      case "homework.save":
        return { ok: true };

      default:
        return null;
    }
  }

  return { HOST: HOST, ready: ready, invoke: invoke, on: on, notify: notify };
})();
