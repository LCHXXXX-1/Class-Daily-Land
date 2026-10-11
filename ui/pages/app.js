// ============================================================================
//  pages/app.js —— 设置中心（2026-10 重写版，设计语言借鉴 Class Widgets 2）
//  ---------------------------------------------------------------------------
//  外壳：左侧「品牌区 + 搜索 + 药丸导航」面板，右侧内容区。
//  页面结构与字段完全照两个项目的真实实现来：
//    · .NET  src/ClassDailyLand.App/Views/SettingsWindow*.cs
//    · Python settings_dialog_v4.py
//  键名用 AppSettings 的 snake_case，宿主实现 RPC 时直接透传即可。
//
//  对外契约（两端宿主依赖，不能改）：
//    · window.settingsApp = { goto(id), reload() }
//    · host.notify("ui.ready" / "ui.error", …)
//    · body dataset：nativeChrome / frameless / platform
//    · URL 参数：?page= ?theme= ?chrome=native ?dialog=
//    · window.CDLDialogs（pages/dialogs.js）、window.CDLMarket（pages/market.js）
// ============================================================================

(function () {

  const { el, nodes, button, toggle, slider, numberBox, combo, selectorBar,
          infoBar, badge, linkRow, settingRow, cardGroup, dialog, progressRing } = C;

  const NAV = [
    { id: "general",    label: "通用",       icon: "gear" },
    { id: "appearance", label: "外观",       icon: "palette" },
    { id: "island",     label: "灵动岛",     icon: "island" },
    { id: "schedule",   label: "课表与提醒", icon: "calendar" },
    { id: "homework",   label: "作业",       icon: "book" },
    { id: "plugins",    label: "插件",       icon: "puzzle" },
    { id: "advanced",   label: "高级",       icon: "tune" },
    { id: "about",      label: "关于",       icon: "info" },
  ];

  const state = {
    page: "general",
    settings: {},
    info: {},          // app.getVersion 的返回
    query: "",
    bootError: null,   // 启动时某次 RPC 失败的原因（界面照常显示，只在顶部说明一下）
    windowMaximized: false,  // 无边框窗口下，标题栏那颗按钮要显示「最大化」还是「还原」
  };

  let pageHost = null;
  let navHost = null;

  // ------------------------------------------------------------------ 工具

  /** 改一个设置项：本地立即生效 + 回传宿主。 */
  function patch(key, value) {
    state.settings[key] = value;
    host.invoke("settings.patch", { [key]: value });
  }

  function isWin11() {
    return /Windows 11/.test(state.info.system || "");
  }

  function toast(page, severity, title, message) {
    const bar = infoBar({ severity, title, message, onClose: true });
    const mount = document.querySelector("[data-toast-slot]");
    if (mount) mount.appendChild(bar);
  }

  function clearToasts() {
    const mount = document.querySelector("[data-toast-slot]");
    if (mount) mount.replaceChildren();
  }

  // ------------------------------------------------------------------ 主题

  /**
   * 换主题。`animate` 为 false 时不做过场 —— 只在**启动时**这么用：
   * 界面还没画出来就淡入一次，看着像是闪了一下。
   *
   * 做法见 styles/tokens.css 的「深浅色交叉淡入」：切换的瞬间给 <html> 挂上
   * data-theme-anim，让所有元素的颜色类属性按 200ms OutQuart 过渡，260ms 后摘掉。
   */
  let themeAnimTimer = 0;

  function applyTheme(mode, animate) {
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const dark = mode === "dark" || (mode === "system" && prefersDark);
    const next = dark ? "dark" : "light";
    const root = document.documentElement;

    if (animate !== false && root.dataset.theme && root.dataset.theme !== next) {
      // 过渡属性必须和颜色变化在同一次样式重算里生效，所以先挂属性、紧接着改主题
      root.dataset.themeAnim = "";
      clearTimeout(themeAnimTimer);
      themeAnimTimer = setTimeout(() => { delete root.dataset.themeAnim; }, 260);
    }

    root.dataset.theme = next;
  }

  // --------------------------------------------------------------- 外壳

  /**
   * 页内标题栏。
   *
   * 宿主把窗口做成无边框时（`app.getVersion` 返回的 `window.controls` 非空），
   * 这条标题栏就是**唯一的**窗口镶边：它既要显示标题，也要承接拖动，
   * 还要画最小化 / 最大化 / 关闭。宿主保留原生标题栏时 controls 为空，
   * 一个按钮都不画（整条还会被 CSS 藏掉）。
   *
   * 拖动有两条路，不冲突：
   *   · WebView2 认 CSS 的 `app-region: drag`（宿主开了非客户区支持），
   *     那条路上浏览器**收不到 pointerdown**，所以下面的 RPC 不会发；
   *   · QtWebEngine 不认 app-region，于是 pointerdown 会走到这里 → 调 window.startMove，
   *     宿主用 QWindow.startSystemMove() 接管。
   */
  function titlebar() {
    const hostName = { webview2: ".NET / WebView2", qtwebengine: "Python / QtWebEngine" }[host.HOST]
      || "浏览器预览";

    const controls = (state.info && state.info.window && state.info.window.controls) || [];

    const bar = el("header", { class: "app-titlebar" }, [
      el("button", {
        class: "tb-back", type: "button", title: "返回", "aria-label": "返回",
        onclick: () => history.length > 1 ? history.back() : null,
      }, [iconEl("back", "i16")]),
      el("span", { class: "tb-title", text: "设置" }),
      el("span", { class: "spacer" }),
      badge(hostName, host.HOST === "browser" ? "" : "accent"),
      controls.indexOf("minimize") >= 0
        ? el("button", {
            class: "tb-win", type: "button", title: "最小化", "aria-label": "最小化",
            onclick: () => host.invoke("window.minimize").catch(() => {}),
          }, [iconEl("minimize", "i16")])
        : null,
      controls.indexOf("maximize") >= 0
        ? el("button", {
            class: "tb-win", type: "button", title: "最大化", "aria-label": "最大化",
            "data-win-maximize": "true",
            onclick: (e) => toggleMaximize(e.currentTarget),
          }, [iconEl(state.windowMaximized ? "restore" : "maximize", "i16")])
        : null,
      controls.indexOf("close") >= 0
        ? el("button", {
            class: "tb-win is-close", type: "button", title: "关闭", "aria-label": "关闭",
            onclick: () => host.invoke("window.close").catch(() => {}),
          }, [iconEl("close", "i16")])
        : null,
    ]);

    bar.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      if (e.target.closest("button")) return;   // 点在按钮上不算拖窗口
      host.invoke("window.startMove").catch(() => {});
    });

    return bar;
  }

  async function toggleMaximize(button) {
    try {
      const result = await host.invoke("window.toggleMaximize");
      state.windowMaximized = !!(result && result.maximized);
      button.replaceChildren(iconEl(state.windowMaximized ? "restore" : "maximize", "i16"));
      button.title = state.windowMaximized ? "还原" : "最大化";
      button.setAttribute("aria-label", button.title);
    } catch (err) { /* 宿主不支持就算了，别弹错 */ }
  }

  /**
   * 拿到 app.getVersion 之后重画一次标题栏。
   *
   * 外壳是「先挂上、后拉数据」的（这条不能反，否则任一 RPC 失败就是一片白），
   * 而窗口按钮要靠 `window.controls` 才知道画不画 —— 所以数据到了得补画一次。
   */
  function refreshTitlebar() {
    const old = document.querySelector(".app-titlebar");
    if (old) old.replaceWith(titlebar());
    refreshBrand();
  }

  /** 品牌区同理：版本号要等 app.getVersion 到了才有。 */
  function refreshBrand() {
    const sub = document.querySelector(".side-brand .brand-sub");
    if (sub) sub.textContent = "设置 · v" + (state.info.version || "—");
  }

  /**
   * 拖边缩放（只有宿主声明 `window.resize === "js"` 时才装）。
   *
   * WebView2 那边窗口自带 WS_THICKFRAME 调整边框，系统自己会处理；
   * Qt 的无边框窗口没得借，只能由页面判断「鼠标落在哪条边上」，
   * 再把边报给宿主（QWindow.startSystemResize）。
   */
  function installResizeEdges() {
    const BAND = 6;

    document.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;

      const width = window.innerWidth;
      const height = window.innerHeight;

      let edge = "";
      if (e.clientX <= BAND) edge += "left";
      else if (e.clientX >= width - BAND) edge += "right";
      if (e.clientY <= BAND) edge += edge ? "-top" : "top";
      else if (e.clientY >= height - BAND) edge += edge ? "-bottom" : "bottom";

      if (edge) host.invoke("window.startResize", { edge: edge }).catch(() => {});
    });
  }

  function navItem(entry) {
    return el("button", {
      class: "nav-item", type: "button", "data-nav": entry.id,
      "aria-current": state.page === entry.id ? "page" : null,
      onclick: () => go(entry.id),
    }, [
      el("span", { class: "nav-icon" }, [iconEl(entry.icon, "i20")]),
      el("span", { class: "nav-label", text: entry.label }),
    ]);
  }

  function renderNav() {
    navHost.replaceChildren();
    const query = state.query.trim().toLowerCase();
    const hits = NAV.filter((n) => !query || n.label.toLowerCase().includes(query));
    if (hits.length === 0) {
      navHost.appendChild(el("div", { class: "empty", text: "没有匹配的设置页" }));
      return;
    }
    hits.forEach((entry) => navHost.appendChild(navItem(entry)));
  }

  function go(id) {
    if (state.page === id && pageHost.childElementCount > 0) return;
    state.page = id;
    navHost.querySelectorAll(".nav-item").forEach((n) =>
      n.setAttribute("aria-current", n.dataset.nav === id ? "page" : null));
    renderPage(id);
  }

  function renderPage(id) {
    clearToasts();

    const inner = el("div", { class: "content-inner" });
    inner.appendChild(el("div", { "data-toast-slot": "" }));

    // 先挂到 DOM 再画内容：页面里如果直接调 toast()，它按 [data-toast-slot] 查找，
    // 没挂上的话会落到上一页那个槽里，然后被这次 replaceChildren 一起扔掉。
    pageHost.replaceChildren(inner);
    pageHost.scrollTop = 0;

    PAGES[id](inner);

    // 启动时没从宿主读到设置：页面照常可用（走默认值），但必须说清楚。
    if (state.bootError) {
      inner.querySelector("[data-toast-slot]").appendChild(infoBar({
        severity: "error",
        title: "没能从宿主读到设置",
        message: state.bootError
          + "。下面显示的是默认值，改动可能无法保存；关掉重开设置窗口可以再试一次。",
        onClose: true,
      }));
    }
  }

  // =====================================================================
  //  分区：彩色图标磁贴 + 标题 + 卡片（CW2 的标志性分区样式）
  // =====================================================================

  function section(cfg) {
    const head = cfg.title
      ? el("h3", { class: "group-title" + (cfg.section ? " is-section" : "") }, [
          el("span", {
            class: "group-tile",
            style: cfg.color ? { "--tile-color": cfg.color } : undefined,
          }, [iconEl(cfg.icon || "gear", "i16")]),
          el("span", { text: cfg.title }),
        ])
      : null;

    return el("section", { class: "card-group" }, [
      head,
      el("div", { class: "card" }, cfg.rows),
      cfg.note ? el("p", { class: "group-note", text: cfg.note }) : null,
    ]);
  }

  // =====================================================================
  //  通用
  // =====================================================================

  function pageGeneral(root) {
    root.appendChild(el("h1", { class: "page-title", text: "通用" }));
    root.appendChild(el("p", { class: "page-lead", text: "班级日常窗口、作业滚动与启动行为" }));

    root.appendChild(section({
      title: "主窗口", icon: "gear", color: "#0F6CBD",
      rows: [
        settingRow({
          title: "显示班级日常窗口",
          hint: "关掉之后，托盘菜单里还能再打开",
          control: toggle(state.settings.show_main_window, (v) => patch("show_main_window", v), { label: "显示班级日常窗口" }),
        }),
        settingRow({
          title: "窗口宽度",
          hint: "占屏幕宽度的百分之多少",
          control: slider({
            min: 15, max: 50, step: 1, suffix: "%", label: "窗口宽度",
            value: Math.round((state.settings.main_width_ratio || 0.28) * 100),
            onChange: (v) => patch("main_width_ratio", +(v / 100).toFixed(2)),
          }),
        }),
        settingRow({
          title: "窗口透明度",
          hint: "设为 0 表示完全透明",
          control: slider({
            min: 0, max: 100, step: 1, suffix: "%", label: "窗口透明度",
            value: Math.round((state.settings.main_opacity ?? 0.94) * 100),
            onChange: (v) => patch("main_opacity", +(v / 100).toFixed(2)),
          }),
        }),
        settingRow({
          title: "正文字号",
          control: numberBox({
            min: 8, max: 30, step: 1, suffix: " px", label: "正文字号",
            value: state.settings.main_font_size,
            onChange: (v) => patch("main_font_size", v),
          }),
        }),
      ],
    }));

    root.appendChild(section({
      title: "作业滚动", icon: "book", color: "#107C10",
      rows: [
        settingRow({
          title: "自动滚动作业",
          control: toggle(!!state.settings.main_auto_scroll, (v) => patch("main_auto_scroll", v), { label: "自动滚动作业" }),
        }),
        settingRow({
          title: "滚动间隔",
          control: numberBox({
            min: 20, max: 200, step: 1, suffix: " ms",
            value: state.settings.main_scroll_interval,
            onChange: (v) => patch("main_scroll_interval", v),
          }),
        }),
        settingRow({
          title: "每步滚动距离",
          control: numberBox({
            min: 1, max: 10, step: 1, suffix: " px",
            value: state.settings.main_scroll_step,
            onChange: (v) => patch("main_scroll_step", v),
          }),
        }),
        settingRow({
          title: "到底暂停",
          control: numberBox({
            min: 0, max: 200, step: 1, suffix: " 次",
            value: state.settings.main_scroll_pause,
            onChange: (v) => patch("main_scroll_pause", v),
          }),
        }),
      ],
    }));

    root.appendChild(section({
      title: "启动与更新", icon: "sync", color: "#8661C5",
      rows: [
        settingRow({
          title: "启动时检查更新",
          hint: "由独立更新器处理，可随时手动检查",
          control: toggle(!!state.settings.check_update_on_start, (v) => patch("check_update_on_start", v), { label: "启动时检查更新" }),
        }),
        settingRow({
          title: "源码运行保护更新",
          hint: "检测到本地主入口源码时不再自动更新，改前先提醒备份",
          control: toggle(!!state.settings.block_update_on_source, (v) => patch("block_update_on_source", v), { label: "源码运行保护更新" }),
        }),
      ],
    }));
  }

  // =====================================================================
  //  外观
  // =====================================================================

  function pageAppearance(root) {
    root.appendChild(el("h1", { class: "page-title", text: "外观" }));
    root.appendChild(el("p", { class: "page-lead", text: "颜色模式、动画与窗口材质" }));

    const micaRow = isWin11()
      ? settingRow({
          title: "云母材质（Mica）",
          hint: "Windows 11 的半透明云母背板，会跟着系统明暗变",
          control: toggle(!!state.settings.settings_mica, (v) => patch("settings_mica", v), { label: "云母材质" }),
        })
      : settingRow({
          title: "云母材质（Mica）",
          hint: "云母材质需要 Windows 11，当前系统使用普通窗口。",
          disabled: true,
          control: badge("当前系统不支持"),
        });

    root.appendChild(section({
      title: "颜色主题", icon: "palette", color: "#F7630C",
      rows: [
        settingRow({
          title: "颜色模式",
          hint: "跟随系统时会随 Windows 的浅色 / 深色实时切换",
          control: selectorBar({
            label: "颜色模式",
            value: state.settings.theme_mode || "system",
            options: [
              { value: "system", label: "跟随系统" },
              { value: "light",  label: "浅色" },
              { value: "dark",   label: "深色" },
            ],
            onChange: (v) => { patch("theme_mode", v); applyTheme(v); },
          }),
        }),
      ],
    }));

    root.appendChild(section({
      title: "淡入淡出", icon: "capsule", color: "#8661C5",
      rows: [
        settingRow({
          title: "窗口打开时渐显",
          control: toggle(!!state.settings.anim_fade_window, (v) => patch("anim_fade_window", v), { label: "窗口打开时渐显" }),
        }),
        settingRow({
          title: "面板展开时渐显",
          control: toggle(!!state.settings.anim_fade_panel, (v) => patch("anim_fade_panel", v), { label: "面板展开时渐显" }),
        }),
        settingRow({
          title: "文字变化时渐显",
          control: toggle(!!state.settings.anim_fade_text, (v) => patch("anim_fade_text", v), { label: "文字变化时渐显" }),
        }),
        settingRow({
          title: "动画时长",
          control: numberBox({
            min: 100, max: 2000, step: 50, suffix: " ms",
            value: state.settings.anim_duration,
            onChange: (v) => patch("anim_duration", v),
          }),
        }),
      ],
    }));

    root.appendChild(section({
      title: "窗口材质", icon: "shield", color: "#038387",
      note: "当前系统：" + (state.info.system || "未知"),
      rows: [micaRow],
    }));
  }

  // =====================================================================
  //  灵动岛
  // =====================================================================

  function pageIsland(root) {
    root.appendChild(el("h1", { class: "page-title", text: "灵动岛" }));
    root.appendChild(el("p", { class: "page-lead", text: "屏幕顶部的提醒条与副岛" }));

    root.appendChild(section({
      title: "主岛", icon: "island", color: "#0F6CBD",
      rows: [
        settingRow({
          title: "显示灵动岛",
          control: toggle(!!state.settings.show_island, (v) => patch("show_island", v), { label: "显示灵动岛" }),
        }),
        settingRow({
          title: "距屏幕顶部距离",
          control: numberBox({
            min: 0, max: 100, step: 1, suffix: " px",
            value: state.settings.island_top_margin,
            onChange: (v) => patch("island_top_margin", v),
          }),
        }),
        settingRow({
          title: "提醒条宽度",
          control: numberBox({
            min: 200, max: 800, step: 1, suffix: " px",
            value: state.settings.island_alert_width,
            onChange: (v) => patch("island_alert_width", v),
          }),
        }),
        settingRow({
          title: "提醒条停留",
          control: numberBox({
            min: 100, max: 5000, step: 50, suffix: " ms",
            value: state.settings.island_alert_hold_ms,
            onChange: (v) => patch("island_alert_hold_ms", v),
          }),
        }),
        settingRow({
          title: "仅全屏时隐藏",
          hint: "全屏看视频 / 演示时自动让位",
          control: toggle(!!state.settings.island_hide_on_fullscreen, (v) => patch("island_hide_on_fullscreen", v), { label: "仅全屏时隐藏" }),
        }),
        settingRow({
          title: "启用唤醒动画",
          hint: "收起时为圆形，展开后为胶囊",
          control: toggle(!!state.settings.island_show_wakeup_anim, (v) => patch("island_show_wakeup_anim", v), { label: "启用唤醒动画" }),
        }),
      ],
    }));

    root.appendChild(section({
      title: "副岛", icon: "capsule", color: "#038387",
      rows: [
        settingRow({
          title: "显示副岛",
          hint: "显示在主岛右侧",
          control: toggle(!!state.settings.show_sub_island, (v) => patch("show_sub_island", v), { label: "显示副岛" }),
        }),
        settingRow({
          title: "默认收成圆形",
          control: toggle(!!state.settings.sub_island_collapsed, (v) => patch("sub_island_collapsed", v), { label: "默认收成圆形" }),
        }),
        settingRow({
          title: "无内容自动收起",
          hint: "设为 0 表示不自动收起",
          control: numberBox({
            min: 0, max: 120, step: 1, suffix: " 秒",
            value: state.settings.sub_island_auto_collapse_sec,
            onChange: (v) => patch("sub_island_auto_collapse_sec", v),
          }),
        }),
      ],
    }));
  }

  // =====================================================================
  //  课表与提醒
  // =====================================================================

  const SCHEDULE_LINKS = [
    { id: "timetable", title: "课表管理", hint: "切换、备份与导入导出课表", icon: "calendar", color: "#107C10" },
    { id: "weekend",   title: "周末作息", hint: "单独设置周末上课时间",       icon: "clock",    color: "#8661C5" },
    { id: "holidays",  title: "假期与调休", hint: "设置假期与调休日",         icon: "calendar", color: "#F7630C" },
    { id: "duty",      title: "值日生名单", hint: "设置值日轮流安排",         icon: "home",     color: "#038387" },
    { id: "statustest", title: "状态测试", hint: "完整演示一节课的状态变化",  icon: "sync",     color: "#5B5FC7" },
  ];

  function pageSchedule(root) {
    root.appendChild(el("h1", { class: "page-title", text: "课表与提醒" }));
    root.appendChild(el("p", { class: "page-lead", text: "上课提醒、课表与值日生" }));

    root.appendChild(section({
      title: "上课提醒", icon: "clock", color: "#F7630C",
      rows: [
        settingRow({
          title: "倒计时时长",
          hint: "上课前显示蓝色倒计时",
          control: numberBox({
            min: 5, max: 600, step: 1, suffix: " 秒",
            value: state.settings.island_countdown_sec,
            onChange: (v) => patch("island_countdown_sec", v),
          }),
        }),
        settingRow({
          title: "提前提醒",
          hint: "整体提前几分钟进上课状态（下课时间不变）",
          control: numberBox({
            min: 0, max: 60, step: 1, suffix: " 分钟",
            value: state.settings.schedule_advance_minutes ?? 0,
            onChange: (v) => patch("schedule_advance_minutes", v),
          }),
        }),
        settingRow({
          title: "时间偏移",
          hint: "负数为提前，正数为延后",
          control: numberBox({
            min: -1800, max: 1800, step: 1, suffix: " 秒",
            value: state.settings.schedule_time_offset_seconds ?? 0,
            onChange: (v) => patch("schedule_time_offset_seconds", v),
          }),
        }),
      ],
    }));

    root.appendChild(section({
      title: "课表与值日", icon: "calendar", color: "#107C10", section: true,
      rows: SCHEDULE_LINKS.map((link) => linkRow({
        title: link.title, hint: link.hint, icon: link.icon, tileColor: link.color,
        onClick: () => openDialog(link.id, link.title),
      })),
    }));
  }

  /**
   * 打开二级对话框。
   *
   * 顺序：先看共用 UI 里有没有页内实现（window.CDLDialogs 注册表）；
   * 没有才回落到宿主的原生对话框（`dialog.open`）。两边都没有就如实说明 ——
   * 不要静默失败，用户点了一下什么都没发生是最糟的。
   */
  async function openDialog(id, title) {
    if (window.CDLDialogs && window.CDLDialogs.open(id)) return;

    const result = await host.invoke("dialog.open", { id: id });
    if (result && result.opened) return;

    document.body.appendChild(dialog({
      title: title,
      message: (result && result.reason)
        ? result.reason
        : "这个对话框还没有搬进 Web 层，宿主也没提供原生实现。",
      closeText: "知道了",
    }));
  }

  // =====================================================================
  //  作业
  // =====================================================================

  function pageHomework(root) {
    root.appendChild(el("h1", { class: "page-title", text: "作业" }));
    root.appendChild(el("p", { class: "page-lead", text: "布置与修改作业，改动即时生效" }));

    // 编辑器整块嵌在这里 —— 对应原生设置中心「作业」页的做法：不带「取消 / 确认」，
    // 改动即时生效。独立的「编辑作业」对话框用的是同一个编辑器（见 pages/dialogs.js）。
    const editor = window.CDLDialogs.homeworkEditor({ embedded: true });

    root.appendChild(section({
      title: "作业编辑器", icon: "book", color: "#107C10",
      rows: [
        el("div", { class: "card-pad stack" }, [
          editor.node,
          el("div", { class: "hstack" }, [
            button("打开作业文件夹", { icon: "folder", onClick: () => host.invoke("app.openFolder", { id: "homework" }) }),
          ]),
        ]),
      ],
    }));
  }

  // =====================================================================
  //  插件
  // =====================================================================

  /**
   * 插件页（插件市场 + 第三方包 + 本地插件 + 运行日志）。
   *
   * 布局照 Python 版的 market_page.py / package_page.py 来，但**更新逻辑不进这一层**：
   * 两端本来就不一样（.NET 索引固定走 by-net 仓库；Python 有 market_source 可选三个源）。
   * 具体实现在 pages/market.js。
   */
  function pagePlugins(root) {
    window.CDLMarket.pluginsPage(root);
  }

  // =====================================================================
  //  高级
  // =====================================================================

  function pageAdvanced(root) {
    root.appendChild(el("h1", { class: "page-title", text: "高级" }));
    root.appendChild(el("p", { class: "page-lead", text: "本地插件与日常维护" }));

    root.appendChild(section({
      title: "本地插件", icon: "puzzle", color: "#0F6CBD",
      note: "程序启动时会加载这些插件",
      rows: [
        linkRow({
          title: "安装本地插件…", hint: "从 .cblplugin 文件安装", icon: "download", tileColor: "#0F6CBD",
          onClick: () => openDialog("install-local", "安装本地插件"),
        }),
        linkRow({
          title: "打开插件文件夹", hint: "在文件资源管理器中打开", icon: "folder", tileColor: "#B146C2",
          onClick: () => host.invoke("app.openFolder", { id: "plugins" }),
        }),
      ],
    }));

    root.appendChild(section({
      title: "日常维护", icon: "tune", color: "#8661C5",
      rows: [
        linkRow({
          title: "打开配置文件夹", hint: "查看 settings.json 等配置文件", icon: "folder", tileColor: "#038387",
          onClick: () => host.invoke("app.openFolder", { id: "config" }),
        }),
        el("button", {
          class: "win-linkrow", type: "button",
          style: { "--tile-color": "#C42B1C" },
          onclick: () => document.body.appendChild(dialog({
            title: "恢复全部默认",
            message: "所有设置都会回到默认值。已经装好的插件、课表和值日名单不受影响。",
            primaryText: "恢复默认", danger: true,
            onPrimary: async () => {
              await host.invoke("settings.reset");
              state.settings = await host.invoke("settings.getAll") || {};
              applyTheme(state.settings.theme_mode);
              renderPage("advanced");
              toast("advanced", "success", "已恢复默认", "所有设置已回到初始值。");
            },
          })),
        }, [
          el("span", { class: "tile" }, [iconEl("restart", "i20")]),
          el("span", {}, [
            el("div", { class: "row-title", style: { color: "var(--system-fill-color-critical)" }, text: "恢复全部默认" }),
            el("div", { class: "row-hint", text: "将所有设置恢复为默认值" }),
          ]),
          el("span", { class: "chev" }),
        ]),
      ],
    }));

    root.appendChild(el("p", {
      class: "group-note",
      text: "配置文件位置：" + (state.info.configPath || "由宿主提供"),
    }));
  }

  // =====================================================================
  //  关于
  // =====================================================================

  function pageAbout(root) {
    root.appendChild(el("h1", { class: "page-title", text: "关于" }));

    const material = (state.settings.settings_mica && isWin11())
      ? "Windows 11 云母（Mica）" : "普通";

    const card = el("div", { class: "card" }, [
      el("div", { class: "card-pad" }, [
        el("div", { class: "about-head" }, [
          el("div", { class: "about-logo", text: "CDL" }),
          el("div", {}, [
            el("div", { class: "about-name", text: "Class Daily Land" }),
            el("div", { class: "about-meta", text: "版本 " + (state.info.version || "—") }),
          ]),
        ]),
        el("dl", { class: "kv" }, [
          el("dt", { text: "简介" }), el("dd", { text: "一个轻量级的班级日常管理小工具" }),
          el("dt", { text: "作者" }), el("dd", { text: "LCHXXXX、hexwisp72" }),
          el("dt", { text: "反馈" }), el("dd", {}, [
            el("a", { class: "win-hyperlink", href: "mailto:2352240265@qq.com", text: "2352240265@qq.com" }),
          ]),
          el("dt", { text: "系统" }), el("dd", { text: state.info.system || "—" }),
          el("dt", { text: "窗口材质" }), el("dd", { text: material }),
          el("dt", { text: "宿主" }), el("dd", { text: { webview2: "WPF + WebView2", qtwebengine: "PySide6 + QWebEngineView" }[host.HOST] || "浏览器预览" }),
        ]),
        state.settings.block_update_on_source
          ? el("div", { style: { marginTop: "14px" } }, [
              infoBar({
                severity: "warning",
                title: "源码运行 · 自动更新已跳过",
                message: "检测到本地主入口源码，更新前会先提醒备份。",
              }),
            ])
          : null,
        el("div", { style: { marginTop: "16px" } }, [
          button("检查更新", { accent: true, icon: "sync", onClick: async (e) => {
            const btn = e.currentTarget;
            btn.disabled = true;
            const result = await host.invoke("update.check");
            btn.disabled = false;
            if (!result) return;
            if (result.hasUpdate) {
              toast("about", "success", "发现新版本 " + result.latest, "当前版本 " + result.current + "。");
            } else if (result.message) {
              // 宿主自己拉了更新器（.NET 的更新是独立进程，拿不到远端版本号）→ 如实转达
              toast("about", "info", "检查更新", result.message);
            } else {
              toast("about", "info", "已是最新版本", "当前版本 " + result.current + "。");
            }
          } }),
        ]),
      ]),
    ]);

    root.appendChild(el("section", { class: "card-group" }, [card]));
  }

  const PAGES = {
    general: pageGeneral,
    appearance: pageAppearance,
    island: pageIsland,
    schedule: pageSchedule,
    homework: pageHomework,
    plugins: pagePlugins,
    advanced: pageAdvanced,
    about: pageAbout,
  };

  // =====================================================================
  //  启动
  // =====================================================================

  async function boot() {
    // 深链接：宿主 / 快捷方式可带 ?page=island&theme=dark 直接打开某一页
    //（比如托盘菜单点「灵动岛设置」）。只影响本次显示，不回写设置。
    const params = new URLSearchParams(location.search);
    const wantedPage = params.get("page");
    const wantedTheme = params.get("theme");

    // 宿主保留了原生窗口标题栏（?chrome=native）时，页内那条标题栏就重复了
    if (params.get("chrome") === "native") document.body.dataset.nativeChrome = "true";

    // ★ 顺序很重要：先把外壳挂上，再去问宿主拿数据。
    //   反过来做会有一个致命后果：只要任一 RPC 失败，body 就是空的 ——
    //   用户看到的就是「一片白」。.NET 端报过的白屏就是这么来的。
    applyTheme(wantedTheme || "system", false);   // 启动首帧不做过场
    mountShell();

    try {
      await host.ready;
      state.settings = (await host.invoke("settings.getAll")) || {};
      state.info = (await host.invoke("app.getVersion")) || {};
      if (state.info.platform) document.body.dataset.platform = state.info.platform;

      // 窗口按钮要靠 window.controls 才知道画不画，而外壳是先挂上去的 —— 补画一次
      refreshTitlebar();
      if (state.info.window && state.info.window.frame === "none") {
        document.body.dataset.frameless = "true";
        // 只有宿主明说自己没有调整边框时，才由页面算边去请求缩放
        if (state.info.window.resize === "js") installResizeEdges();
      }

      if (wantedPage && PAGES[wantedPage]) state.page = wantedPage;

      // ★ URL 上的 theme 优先于设置里的 theme_mode —— 它本来就写着「只影响本次显示，
      //   不回写设置」，拿它拍照 / 做自检才拍得到深色。
      applyTheme(wantedTheme || state.settings.theme_mode || "system", false);
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
        if ((state.settings.theme_mode || "system") === "system") applyTheme("system");
      });
    } catch (err) {
      // 拿不到数据也要有界面：下面 renderPage 会用默认值画出来，
      // 并在页面顶部挂一条说明原因的提示条。
      state.bootError = (err && err.message) ? err.message : String(err);
      host.notify("ui.error", { phase: "boot", message: state.bootError });
    }

    renderNav();
    renderPage(state.page);

    // 告诉宿主界面已经起来了：撤掉「正在加载」、停掉启动超时计时。
    host.notify("ui.ready", { page: state.page, bootError: state.bootError || null });

    // 深链接到某个二级对话框（?dialog=holidays），和 ?page= 一个性质。
    const wantedDialog = params.get("dialog");
    if (wantedDialog && window.CDLDialogs) window.CDLDialogs.open(wantedDialog);
  }

  /** 挂外壳（标题栏 + 左侧导航 + 内容区）。挂完 navHost / pageHost 才可用。 */
  function mountShell() {
    const shell = el("div", { class: "app-shell" }, [
      titlebar(),
      el("div", { class: "app-body" }, [
        el("nav", { class: "nav-pane" }, [
          // 品牌区：渐变 logo 磁贴 + 名称 + 版本（版本等 app.getVersion 到了再补）
          el("div", { class: "side-brand" }, [
            el("div", { class: "brand-logo", text: "CD" }),
            el("div", {}, [
              el("div", { class: "brand-name", text: "Class Daily Land" }),
              el("div", { class: "brand-sub", text: "设置" }),
            ]),
          ]),
          el("div", { class: "nav-search" }, [
            (() => {
              const input = el("input", {
                type: "search", placeholder: "搜索设置",
                "aria-label": "搜索设置",
                oninput: (e) => { state.query = e.target.value; renderNav(); },
              });
              return el("label", { class: "win-textbox" }, [iconEl("search", "i16"), input]);
            })(),
          ]),
          el("div", { class: "nav-scroll" }),
        ]),
        el("main", { class: "content-pane" }),
      ]),
    ]);

    document.body.replaceChildren(shell);
    navHost = shell.querySelector(".nav-scroll");
    pageHost = shell.querySelector(".content-pane");
  }

  // 供宿主注入：宿主可以调它切页，比如从托盘直接打开「灵动岛」设置
  window.settingsApp = {
    goto: (id) => { if (PAGES[id]) go(id); },
    reload: async () => {
      try {
        state.settings = (await host.invoke("settings.getAll")) || {};
        state.bootError = null;
      } catch (err) {
        state.bootError = (err && err.message) ? err.message : String(err);
      }
      renderPage(state.page);
    },
  };

  boot();
})();
