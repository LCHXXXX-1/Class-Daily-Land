// ============================================================================
//  渲染冒烟测试：用 jsdom 把 index.html 真跑起来，逐个页面点过去。
//  ---------------------------------------------------------------------------
//  用途：验证「页面能不能真的渲染出来」—— 导航切换、控件回写、主题切换、
//        搜索过滤、对话框、插件列表、重置默认，全部走一遍。
//  跑法：node tests/render.test.mjs（需要 jsdom，仅测试用，产品代码零依赖）
// ============================================================================
import fs from "node:fs";
import path from "node:path";
import { JSDOM } from "jsdom";

const ROOT = path.resolve(import.meta.dirname, "..");
const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
const url = "file:///" + path.join(ROOT, "index.html").replace(/\\/g, "/");

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  resources: "usable",
  pretendToBeVisual: true,
  url: url,
  beforeParse(window) {
    // jsdom 没有 matchMedia，补一个（页面用它判断「跟随系统」）
    window.matchMedia = (query) => ({
      matches: false, media: query, onchange: null,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
  },
});

const win = dom.window;
const doc = win.document;

let failures = 0;
const check = (label, condition, detail) => {
  if (condition) { console.log("  ✓ " + label); }
  else { console.log("  ✗ " + label + (detail ? " :: " + detail : "")); failures++; }
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, ms = 4000) {
  const t0 = Date.now();
  for (;;) {
    const value = fn();
    if (value) return value;
    if (Date.now() - t0 > ms) return null;
    await sleep(25);
  }
}
const click = (node) => node.dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
const q = (sel) => doc.querySelector(sel);
const qa = (sel) => [...doc.querySelectorAll(sel)];
const navByLabel = (label) => qa(".nav-item").find((n) => n.textContent.trim() === label);

await new Promise((r) => win.addEventListener("load", r));

// 记录宿主调用
const calls = [];
const originalInvoke = win.host.invoke.bind(win.host);
win.host.invoke = (method, params) => { calls.push({ method, params }); return originalInvoke(method, params); };

console.log("[1] 外壳与导航");
const nav = await until(() => qa(".nav-item").length === 8 ? qa(".nav-item") : null);
check("渲染出 8 个导航项", !!nav, nav ? "" : "实际 " + qa(".nav-item").length);
const labels = nav ? nav.map((n) => n.textContent.trim()) : [];
check("导航标签与两个项目一致",
  labels.join("/") === "通用/外观/灵动岛/课表与提醒/作业/插件/高级/关于", labels.join("/"));
check("默认停在「通用」", q(".page-title") && q(".page-title").textContent === "通用",
  q(".page-title") && q(".page-title").textContent);
check("标题栏显示当前宿主", !!q(".app-titlebar .win-badge"),
  q(".app-titlebar .win-badge") && q(".app-titlebar .win-badge").textContent);

console.log("[2] 逐页渲染");
const pages = [
  ["通用", 3, 10], ["外观", 3, 6], ["灵动岛", 2, 9], ["课表与提醒", 1, 3],
  ["作业", 1, 0], ["插件", 3, 0], ["高级", 2, 0], ["关于", 1, 0],
];
for (const [label, minGroups, minRows] of pages) {
  click(navByLabel(label));
  await sleep(30);
  const groups = qa(".card-group").length;
  const rows = qa(".row, .win-linkrow, .plugin-row").length;
  check(`${label}：卡片组 ${groups}（≥${minGroups}）、设置行 ${rows}（≥${minRows}）`,
    groups >= minGroups && rows >= minRows, `实际 ${groups} 组 / ${rows} 行`);
}
check("课表页有 5 个二级入口",
  (() => { click(navByLabel("课表与提醒")); return qa(".win-linkrow").length === 5; })(),
  String(qa(".win-linkrow").length));

console.log("[3] 控件回写");
click(navByLabel("通用"));
await sleep(30);
const toggle = q(".win-toggle");
const before = toggle.getAttribute("aria-checked");
click(toggle);
await sleep(30);
check("开关可切换", toggle.getAttribute("aria-checked") !== before,
  before + " → " + toggle.getAttribute("aria-checked"));
check("开关回写 settings.patch",
  calls.some((c) => c.method === "settings.patch" && "show_main_window" in (c.params || {})));

const slider = q(".win-slider");
slider.value = "42";
slider.dispatchEvent(new win.Event("input", { bubbles: true }));
await sleep(280);   // 滑块回写是拖动合并的（150ms 去抖），等它落地
check("滑块回写 main_width_ratio=0.42",
  calls.some((c) => c.method === "settings.patch" && c.params.main_width_ratio === 0.42),
  JSON.stringify(calls.filter((c) => c.method === "settings.patch").slice(-2)));
check("滑块右侧数值同步", q(".win-slider-value").textContent === "42%", q(".win-slider-value").textContent);

// 滑块外观是「轨道 + 填充段 + 外圆 + 内点」四件纯 DOM 元素画出来的，位置只由一个
// --pct（0..1 的纯数字）驱动。以前是靠输入元素的 ::-webkit-slider-thumb 伪元素 +
// transform 做，Chromium 下伪元素会被逐帧重新栅格化，拖动时看着一直在抖。
const sliderField = q(".win-slider-field");
check("滑块是 WinUI 式的四件结构（轨道 / 填充段 / 外圆 / 内点）",
  !!(q(".win-slider-track") && q(".win-slider-fill") && q(".win-slider-thumb") && q(".win-slider-dot")),
  [".win-slider-track", ".win-slider-fill", ".win-slider-thumb", ".win-slider-dot"]
    .filter((sel) => !q(sel)).join(",") || "四件齐了");
check("交互层仍是 input[type=range]（拖动 / 点击跳转 / 方向键都靠它）",
  q(".win-slider").tagName === "INPUT" && q(".win-slider").getAttribute("type") === "range");
check("位置由 --pct 驱动，且是纯数字（calc 里要拿它当乘数）",
  sliderField.style.getPropertyValue("--pct") === "0.7714",
  sliderField.style.getPropertyValue("--pct"));
// 只看真正的规则，不看注释（注释里正好写了这条老路的名字）
const sliderCss = fs.readFileSync(path.join(ROOT, "styles", "app.css"), "utf8")
  .replace(/\/\*[\s\S]*?\*\//g, "");
check("没有回到 ::-webkit-slider-thumb 那条老路", !sliderCss.includes("::-webkit-slider-thumb"));

const numInput = q(".win-numberbox input");
numInput.value = "18";
numInput.dispatchEvent(new win.Event("change", { bubbles: true }));
await sleep(30);
check("数字框回写 main_font_size=18",
  calls.some((c) => c.method === "settings.patch" && c.params.main_font_size === 18));

console.log("[4] 主题三档");
click(navByLabel("外观"));
await sleep(30);
const bar = q(".win-selectorbar");
check("颜色模式是三档分段控件", bar && bar.querySelectorAll("button").length === 3);
if (bar) { click([...bar.querySelectorAll("button")].find((b) => b.textContent === "深色")); await sleep(30); }
check("切到深色后 html[data-theme=dark]", doc.documentElement.dataset.theme === "dark",
  doc.documentElement.dataset.theme);
check("主题也回写宿主", calls.some((c) => c.method === "settings.patch" && c.params.theme_mode === "dark"));
if (bar) { click([...bar.querySelectorAll("button")].find((b) => b.textContent === "浅色")); await sleep(30); }
check("切回浅色", doc.documentElement.dataset.theme === "light", doc.documentElement.dataset.theme);

console.log("[5] 搜索过滤");
const search = q('.nav-search input');
search.value = "灵动";
search.dispatchEvent(new win.Event("input", { bubbles: true }));
await sleep(30);
check("搜索「灵动」只剩 1 项", qa(".nav-item").length === 1, String(qa(".nav-item").length));
search.value = "";
search.dispatchEvent(new win.Event("input", { bubbles: true }));
await sleep(30);
check("清空后恢复 8 项", qa(".nav-item").length === 8);

console.log("[6] 插件页（异步数据）");
click(navByLabel("插件"));
// 首屏是「先挂骨架、后拉数据」，等市场卡片落地
const marketCards = await until(() => qa(".market-card").length >= 6 ? qa(".market-card") : null);
check("市场里每条索引都渲染成一张卡片", !!marketCards,
  String(qa(".market-card").length) + " 张");

const names = qa(".mc-name").map((n) => n.textContent);
check("卡片上有插件名", names.includes("时钟") && names.includes("灾害预警"), names.join(" | "));

const statuses = qa(".market-card .win-badge").map((n) => n.textContent);
check("五种状态都画出来了（未安装 / 已安装 / 可更新 / 加载失败 / 装不了）",
  ["未安装", "已安装", "可更新", "加载失败", "装不了"].every((s) => statuses.includes(s)),
  statuses.join(" | "));

check("可更新那条显示版本变化 v1.9.0 → v2.0.1",
  qa(".mc-ver").some((n) => n.textContent === "v1.9.0 → v2.0.1"),
  qa(".mc-ver").map((n) => n.textContent).join(" | "));

check("加载失败的原因挂在卡片上",
  qa(".mc-warn").some((n) => n.textContent.includes("缺少入口程序集 main.dll")),
  qa(".mc-warn").map((n) => n.textContent).join(" | "));

check("索引记录不合法也一样列出来并说明原因",
  qa(".mc-warn").some((n) => n.textContent.includes("缺少 sha256")),
  qa(".mc-warn").map((n) => n.textContent).join(" | "));

// 按钮显隐由状态说了算
const cardOf = (name) => qa(".market-card").find((c) => c.querySelector(".mc-name").textContent === name);
const visibleButtons = (name) => [...cardOf(name).querySelectorAll(".mc-actions .win-btn")]
  .filter((b) => !b.hidden).map((b) => b.textContent.trim());

check("未安装的只给「装上」", visibleButtons("灾害预警").join(",") === "装上",
  visibleButtons("灾害预警").join(","));
check("已安装的给「禁用 / 卸掉」", visibleButtons("时钟").join(",") === "禁用,卸掉",
  visibleButtons("时钟").join(","));
check("可更新的给「更新 / 禁用 / 卸掉」", visibleButtons("天气").join(",") === "更新,禁用,卸掉",
  visibleButtons("天气").join(","));

// 本地插件（plugins.list）单独一列
const localNames = qa(".market-list")[1].querySelectorAll(".mc-name");
check("本地已安装插件单独列出并标明加载失败",
  [...localNames].some((n) => n.textContent === "旧版作业助手"),
  [...localNames].map((n) => n.textContent).join(" | "));

const syncBtn = qa(".win-btn").find((b) => b.textContent.includes("检查更新"));
check("有「检查更新」按钮", !!syncBtn);

// 索引来源是宿主驱动的：mock 给了三项就应当画出来
const sourceSelect = q(".market-source .ed-select");
check("索引来源下拉按宿主给的选项画（3 项）",
  !!sourceSelect && sourceSelect.options.length === 3,
  sourceSelect ? sourceSelect.options.length + " 项" : "无下拉");

if (syncBtn) {
  click(syncBtn);
  await sleep(200);
  const log = q(".market-log");
  check("同步后运行日志被填充", log && log.textContent.includes("拉取索引"),
    log ? log.textContent.slice(0, 24) : "无日志");
  check("同步后状态行带上「上次检查」", q(".market-status").textContent.includes("上次检查"),
    q(".market-status").textContent);
}

console.log("[7] 高级页：恢复默认");
click(navByLabel("高级"));
await sleep(30);
const dangerRow = qa(".win-linkrow").find((r) => r.textContent.includes("恢复全部默认"));
check("有恢复默认入口", !!dangerRow);
if (dangerRow) {
  click(dangerRow);
  await sleep(30);
  const dialog = q(".win-dialog-host");
  check("弹出确认对话框", !!dialog);
  if (dialog) {
    const primary = [...dialog.querySelectorAll(".win-btn")].find((b) => b.textContent === "恢复默认");
    click(primary);
    await sleep(60);
    check("确认后调用 settings.reset", calls.some((c) => c.method === "settings.reset"));
    check("对话框已关闭", !q(".win-dialog-host"));
  }
}

console.log("[8] 关于页");
click(navByLabel("关于"));
await sleep(30);
check("显示版本号", (q(".about-meta") || {}).textContent === "版本 4.3.0",
  (q(".about-meta") || {}).textContent);
check("展示宿主与系统信息", qa(".kv dt").length >= 5, String(qa(".kv dt").length));

// ---------------------------------------------------------------------------
// [10] 二级对话框（页内浮层）
//
// 这六个对话框以前由两端宿主的原生窗口提供，现在搬进了共用 UI。
// 这里只点稳的那几项：注册表、标题、列表格式（照原生逐字抄的）、
// 以及按钮真的调到了对应的 RPC。
// ---------------------------------------------------------------------------
console.log("[10] 二级对话框（页内）");

const dialogs = win.CDLDialogs;
check("已注册迁移完成的对话框", !!dialogs && dialogs.ids().length >= 4,
  dialogs ? dialogs.ids().join(",") : "无");

const closeTopDialog = () => win.document.dispatchEvent(
  new win.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

const panelButton = (text) => qa(".ed-panel .win-btn")
  .find((b) => b.textContent.trim() === text);

// ---- 假期与调休 ----
dialogs.open("holidays");
await sleep(40);
check("假期与调休：标题", (q(".ed-title") || {}).textContent === "假期与调休",
  (q(".ed-title") || {}).textContent);

const holidayTexts = qa(".ed-list-text").map((n) => n.textContent);
check("假期与调休：假期项格式照原生（含名称全角括号）",
  holidayTexts.includes("2026-10-01 ～ 2026-10-07（国庆）"), holidayTexts.join(" | "));
check("假期与调休：调休项格式照原生",
  holidayTexts.includes("2026-10-11 → 补周五"), holidayTexts.join(" | "));

const dateInputs = qa(".ed-panel .ed-input.is-date");
dateInputs[0].value = "2026-12-01";
dateInputs[1].value = "2026-12-03";
qa(".ed-panel .ed-input")[2].value = "校运会";
click(panelButton("加上"));
await sleep(40);
check("假期与调休：「加上」调 schedule.holidays.add",
  calls.some((c) => c.method === "schedule.holidays.add"
    && c.params.start === "2026-12-01" && c.params.name === "校运会"),
  JSON.stringify(calls.filter((c) => c.method === "schedule.holidays.add")));
closeTopDialog();
await sleep(20);
check("Esc 能关掉对话框", qa(".ed-host").length === 0, String(qa(".ed-host").length));

// ---- 周末作息 ----
dialogs.open("weekend");
await sleep(40);
check("周末作息：读到了分界点", q(".ed-panel .ed-input").value === "12:00",
  q(".ed-panel .ed-input").value);
check("周末作息：下午节次两行",
  qa(".ed-card")[0].querySelectorAll(".ed-row").length === 2,
  String(qa(".ed-card")[0].querySelectorAll(".ed-row").length));
check("周末作息：课程多行文本已填充",
  q(".ed-panel .ed-area").value.split("\n").length === 2, q(".ed-panel .ed-area").value);
closeTopDialog();
await sleep(20);

// ---- 值日生名单 ----
dialogs.open("duty");
await sleep(40);
check("值日生名单：三行 + 编号", qa(".ed-li-row").length === 3
  && q(".ed-li-row .ed-li-main").textContent === "1. 张三",
  qa(".ed-li-row").map((n) => n.textContent).join(" | "));
click(qa(".ed-panel .ed-li-actions .win-btn")[0]);
await sleep(40);
check("值日生名单：「删除」调 duty.remove(index=0)",
  calls.some((c) => c.method === "duty.remove" && c.params.index === 0),
  JSON.stringify(calls.filter((c) => c.method === "duty.remove")));
closeTopDialog();
await sleep(20);

// ---- 作业页内嵌编辑器 ----
click(navByLabel("作业"));
await sleep(60);
check("作业页内嵌了编辑器（不再是「阶段 P2 接入」的占位条）",
  qa(".ed-listbox").length === 1 && !q(".page-title ~ * .win-infobar"),
  String(qa(".ed-listbox").length));
check("作业页按科目分组（语文 / 数学 / 英语）",
  qa(".ed-group-title").map((n) => n.textContent).join(",")
    === "语文 (10-12),数学 (10-13),英语",
  qa(".ed-group-title").map((n) => n.textContent).join(","));
check("作业条目带原始序号（跨组连续）",
  qa(".ed-li-main").map((n) => n.textContent).join("|").includes("3. 练习册 P32-35"),
  qa(".ed-li-main").map((n) => n.textContent).join("|"));

// ---------------------------------------------------------------------------
// [11] 无边框窗口的页内标题栏
//
// 两个宿主的设置窗口现在都是无边框的，标题栏、三个窗口按钮都画在页面上。
// 按钮画不画由宿主 app.getVersion 的 window.controls 说了算。
// ---------------------------------------------------------------------------
console.log("[11] 无边框窗口的页内标题栏");

const winButtons = qa(".app-titlebar .tb-win");
check("标题栏画出了三个窗口按钮", winButtons.length === 3, String(winButtons.length));
check("顺序是最小化 / 最大化 / 关闭",
  winButtons.map((b) => b.title).join(",") === "最小化,最大化,关闭",
  winButtons.map((b) => b.title).join(","));

const maximizeButton = winButtons[1];
click(maximizeButton);
await sleep(40);
check("点最大化会调 window.toggleMaximize",
  calls.some((c) => c.method === "window.toggleMaximize"),
  JSON.stringify(calls.filter((c) => c.method === "window.toggleMaximize")));
check("最大化之后图标换成「还原」", maximizeButton.title === "还原", maximizeButton.title);

click(winButtons[2]);
await sleep(40);
check("点关闭会调 window.close", calls.some((c) => c.method === "window.close"));

// 拖动：WebView2 走 app-region（浏览器收不到事件），Qt 走这条 RPC
q(".app-titlebar").dispatchEvent(new win.MouseEvent("pointerdown", { bubbles: true, button: 0 }));
await sleep(30);
check("在标题栏按下会请求宿主接管拖动（Qt 那条路）",
  calls.some((c) => c.method === "window.startMove"));

// ---------------------------------------------------------------------------
// [9] 回归：宿主读不到设置时也必须渲染出界面
//
// 这条是 .NET 端「白屏」的回归用例。以前的 boot() 是先 await 两次 RPC、
// 最后才挂外壳，所以只要 settings.getAll 失败，body 就是空的 ——
// 而 body 的底色在浅色主题下是 #F3F3F3，用户看到的就是一片白。
// ---------------------------------------------------------------------------
console.log("[9] 启动失败不白屏");

const notified = [];
const failDom = new JSDOM(html, {
  runScripts: "dangerously",
  resources: "usable",
  pretendToBeVisual: true,
  url: url,
  beforeParse(window) {
    window.matchMedia = () => ({
      matches: false, media: "", onchange: null,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });

    // host.js 是 `window.host = (function(){...})()`，所以用一个 setter 接住它再包一层：
    // 让 settings.getAll 直接失败，模拟宿主那边抛错 / 通道挂掉。
    let real = null;
    Object.defineProperty(window, "host", {
      configurable: true,
      get() { return real; },
      set(value) {
        const originalInvoke = value.invoke.bind(value);
        value.invoke = (method, params) =>
          (method === "settings.getAll"
            ? Promise.reject(new Error("宿主没有响应（模拟）"))
            : originalInvoke(method, params));

        const originalNotify = value.notify.bind(value);
        value.notify = (event, payload) => { notified.push({ event, payload }); return originalNotify(event, payload); };

        real = value;
      },
    });
  },
});

const failWin = failDom.window;
await new Promise((r) => failWin.addEventListener("load", r));
const booted = await until(() => failWin.document.querySelectorAll(".nav-item").length === 8 ? true : null, 3000);

check("RPC 失败时外壳仍然渲染出来（不再是一片白）", !!booted,
  "导航项 " + failWin.document.querySelectorAll(".nav-item").length);
check("仍然画出页面内容", !!failWin.document.querySelector(".page-title"),
  (failWin.document.querySelector(".page-title") || {}).textContent);
check("顶部给出错误说明而不是沉默",
  !!failWin.document.querySelector(".win-infobar.is-error"),
  failWin.document.querySelector(".win-infobar") ? failWin.document.querySelector(".win-infobar").textContent.slice(0, 40) : "无提示条");
check("错误说明里带上真实原因",
  /宿主没有响应/.test(failWin.document.body.textContent));
check("向宿主上报了 ui.ready（带上 bootError）",
  notified.some((n) => n.event === "ui.ready" && n.payload && /宿主没有响应/.test(n.payload.bootError || "")),
  JSON.stringify(notified.map((n) => n.event)));
failDom.window.close();

console.log(failures === 0 ? "\n渲染冒烟测试通过" : `\n渲染冒烟测试失败 ${failures} 项`);
process.exit(failures === 0 ? 0 : 1);
