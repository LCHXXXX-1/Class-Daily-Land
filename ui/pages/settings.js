// ============================================================================
//  pages/settings.js —— 设置中心（Fluent / RinUI 观感，照 Class Widgets 2 的构图）
//  ---------------------------------------------------------------------------
//  页面结构与字段完全照两个项目的真实实现来：
//    · .NET  src/ClassDailyLand.App/Views/SettingsWindow*.cs
//    · Python settings_dialog_v4.py
//  键名用 AppSettings 的 snake_case，宿主实现 RPC 时直接透传即可。
//
//  本版把构图换成 CW2 / RinUI 那一套（几何与时长见 styles/tokens.css 的来源说明）：
//    · 导航栏分组，父项可展开子项（子项不再是页面，而是二级对话框入口）
//    · 分区 = Text BodyStrong 标题 + 若干卡片
//    · 一项设置一张卡（SettingCard）：图标 22 + 标题 Body + 说明 Caption + 右侧控件
//    · 密集型分组用可展开卡片（SettingExpander）+ 卡内密集行（SettingItem）
//    · 首屏带英雄区（主题色薄雾 + 大标题），底部向内容渐隐
// ============================================================================

(function () {

  const { el, nodes, icon, button, toggle, slider, numberBox, combo, segmented, selectorBar,
          textbox, infoBar, badge, infoBadge, progressBar,
          group, settingCard, settingItem, clipRow, linkRow, expander, dialog, progressRing } = C;

  // ---------------------------------------------------------------- 导航模型
  //  children 里的 id 对应二级对话框（openDialog）。父项自己仍是设置页 ——
  //  与 CW2 的「Notification & Time」那种「有子项也有正文」的分组同构。
  const NAV = [
    { id: "general",    label: "通用",       icon: "gear" },
    { id: "appearance", label: "外观",       icon: "palette" },
    { id: "island",     label: "灵动岛",     icon: "island" },
    {
      id: "schedule", label: "课表与提醒", icon: "calendar",
      children: [
        { id: "timetable",  label: "课表管理",   icon: "calendar" },
        { id: "weekend",    label: "周末作息",   icon: "clock" },
        { id: "holidays",   label: "假期与调休", icon: "calendar" },
        { id: "duty",       label: "值日生名单", icon: "home" },
        { id: "statustest", label: "状态测试",   icon: "sync" },
      ],
    },
    { id: "homework",   label: "作业",       icon: "book" },
    { id: "plugins",    label: "插件",       icon: "puzzle" },
    { id: "advanced",   label: "高级",       icon: "tune" },
    { id: "about",      label: "关于",       icon: "info" },
  ];

  // 来源文案：宿主可以用 market.status / packages.status 的 sourceLabel 覆盖
  //（Python 版的索引还在旧仓库上，不能照抄 .NET 这句）。
  const DEFAULT_SOURCE_LABEL = "GitHub · Class-Daily-Land-by-net（plugin 分支）";

  const state = {
    page: "general",
    settings: {},
    info: {},          // app.getVersion 的返回
    query: "",
    plugins: [],
    market: null,
    packages: null,
    marketSynced: false,   // 同步过一次之后才允许显示「暂无插件」
    bootError: null,   // 启动时某次 RPC 失败的原因（界面照常显示，只在顶部说明一下）
    windowMaximized: false,  // 无边框窗口下，标题栏那颗按钮要显示「最大化」还是「还原」
    openGroups: { schedule: true },   // 导航里展开着哪些分组
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

  /** 页面开头：英雄区（首屏 / 关于）或普通页头。两处都带 .page-title。 */
  function pageHead(title, sub, options) {
    options = options || {};
    if (options.hero) {
      return el("header", { class: "hero" }, [
        el("h1", { class: "page-title hero-title", text: title }),
        sub ? el("p", { class: "hero-sub", text: sub }) : null,
      ]);
    }
    return el("header", { class: "page-head" }, [
      el("h1", { class: "page-title", text: title }),
      sub ? el("div", { class: "page-head-sub", text: sub }) : null,
    ]);
  }

  // ------------------------------------------------------------------ 主题

  /**
   * 换主题。`animate` 为 false 时不做过场 —— 只在**启动时**这么用：
   * 界面还没画出来就淡入一次，看着像是闪了一下。
   *
   * 做法见 styles/tokens.css 的「深浅色交叉淡入」：切换的瞬间给 <html> 挂上
   * data-theme-anim，让所有元素的颜色类属性按 187ms OutQuart 过渡，240ms 后摘掉。
   * 这样换肤是「整屏一起呼吸」，而不是所有颜色硬切。
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
      themeAnimTimer = setTimeout(() => { delete root.dataset.themeAnim; }, 240);
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
      }, [icon("back", "i16")]),
      el("span", { class: "tb-title", text: "设置" }),
      el("span", { class: "spacer" }),
      badge(hostName, host.HOST === "browser" ? "" : "accent"),
      controls.indexOf("minimize") >= 0
        ? el("button", {
            class: "tb-win", type: "button", title: "最小化", "aria-label": "最小化",
            onclick: () => host.invoke("window.minimize").catch(() => {}),
          }, [icon("minimize", "i16")])
        : null,
      controls.indexOf("maximize") >= 0
        ? el("button", {
            class: "tb-win", type: "button", title: "最大化", "aria-label": "最大化",
            "data-win-maximize": "true",
            onclick: (e) => toggleMaximize(e.currentTarget),
          }, [icon(state.windowMaximized ? "restore" : "maximize", "i16")])
        : null,
      controls.indexOf("close") >= 0
        ? el("button", {
            class: "tb-win is-close", type: "button", title: "关闭", "aria-label": "关闭",
            onclick: () => host.invoke("window.close").catch(() => {}),
          }, [icon("close", "i16")])
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
      button.replaceChildren(icon(state.windowMaximized ? "restore" : "maximize", "i16"));
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

  // ------------------------------------------------------------ 导航渲染

  function matches(entry, query) {
    if (!query) return true;
    if (entry.label.toLowerCase().includes(query)) return true;
    return (entry.children || []).some((c) => c.label.toLowerCase().includes(query));
  }

  function navItem(entry, query) {
    const hasChildren = !!(entry.children && entry.children.length);
    const open = hasChildren && (query ? true : !!state.openGroups[entry.id]);

    const chevron = hasChildren
      ? el("span", {
          class: "nav-chev", role: "button", tabindex: "0",
          "aria-label": (open ? "收起" : "展开") + entry.label,
          onclick: (e) => {
            e.stopPropagation();                      // 点箭头只展开，不跳页
            state.openGroups[entry.id] = !state.openGroups[entry.id];
            renderNav();
            focusNav(entry.id);
          },
        })
      : null;

    const node = el("button", {
      class: "nav-item" + (state.page === entry.id ? " is-active" : "") +
        (open ? " is-open" : ""),
      type: "button", "data-nav": entry.id,
      "aria-current": state.page === entry.id ? "page" : null,
      "aria-expanded": hasChildren ? (open ? "true" : "false") : null,
      onclick: () => go(entry.id),
    }, [
      el("span", { class: "nav-icon" }, [icon(entry.icon, "i19")]),
      el("span", { class: "nav-label", text: entry.label }),
      chevron,
    ]);

    if (!hasChildren || !open) return [node];

    // 子项：不是页面，而是二级对话框入口（课表管理 / 假期与调休 …）
    const children = entry.children
      .filter((c) => !query || c.label.toLowerCase().includes(query) || entry.label.toLowerCase().includes(query))
      .map((c) => el("button", {
        class: "nav-sub-item", type: "button", "data-nav": c.id,
        onclick: () => openDialog(c.id, c.label),
      }, [
        el("span", { class: "nav-icon" }, [icon(c.icon, "i19")]),
        el("span", { class: "nav-label", text: c.label }),
      ]));

    return [node, el("div", { class: "nav-sub is-open" }, children)];
  }

  /** 重新渲染导航后把焦点还给刚才点的那一项，键盘用户不会「掉焦点」。 */
  function focusNav(id) {
    const again = navHost.querySelector('.nav-item[data-nav="' + id + '"]');
    if (again) again.focus();
  }

  function renderNav() {
    navHost.replaceChildren();
    const query = state.query.trim().toLowerCase();
    const hits = NAV.filter((n) => matches(n, query));

    if (hits.length === 0) {
      navHost.appendChild(el("div", { class: "empty", text: "没有匹配的设置页" }));
      return;
    }
    hits.forEach((entry) => navItem(entry, query).forEach((n) => navHost.appendChild(n)));
  }

  function go(id) {
    if (state.page === id && pageHost.childElementCount > 0) return;
    state.page = id;
    navHost.querySelectorAll(".nav-item").forEach((n) =>
      n.setAttribute("aria-current", n.dataset.nav === id ? "page" : null));
    navHost.querySelectorAll(".nav-item").forEach((n) =>
      n.classList.toggle("is-active", n.dataset.nav === id));
    renderPage(id);
  }

  function renderPage(id) {
    clearToasts();

    const inner = el("div", { class: "content-inner" });
    // 提示条插槽必须在页面内容之前 —— 既符合「顶部说明」的观感，也让
    // 「.page-title ~ *」这类「页内是否混进了提示条」的判断保持为假。
    inner.appendChild(el("div", { "data-toast-slot": "" }));

    // 先挂到 DOM 再画内容：页面里如果直接调 toast()，它按 [data-toast-slot] 查找，
    // 没挂上的话会落到上一页那个槽里，然后被这次 replaceChildren 一起扔掉。
    pageHost.replaceChildren(inner);
    pageHost.scrollTop = 0;

    PAGES[id](inner);

    // 启动时没从宿主读到设置：页面照常可用（走默认值），但必须说清楚，
    // 否则用户会以为「设置怎么全变了」而不知道是没读上。
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
  //  通用
  // =====================================================================

  function pageGeneral(root) {
    root.appendChild(pageHead("通用", "主窗口、作业滚动与启动更新", { hero: true }));

    root.appendChild(group({
      title: "主窗口",
      children: [
        settingCard({
          title: "显示班级日常窗口", hint: "关掉之后，托盘菜单里还能再打开", icon: "window",
          control: toggle(state.settings.show_main_window, (v) => patch("show_main_window", v), { label: "显示班级日常窗口" }),
        }),
        settingCard({
          title: "窗口宽度", hint: "占屏幕宽度的百分之多少", icon: "resize",
          control: slider({
            min: 15, max: 50, step: 1, suffix: "%", label: "窗口宽度",
            value: Math.round((state.settings.main_width_ratio || 0.28) * 100),
            onChange: (v) => patch("main_width_ratio", +(v / 100).toFixed(2)),
          }),
        }),
        settingCard({
          title: "窗口透明度", hint: "设为 0 表示完全透明", icon: "palette",
          control: slider({
            min: 0, max: 100, step: 1, suffix: "%", label: "窗口透明度",
            value: Math.round((state.settings.main_opacity ?? 0.94) * 100),
            onChange: (v) => patch("main_opacity", +(v / 100).toFixed(2)),
          }),
        }),
        settingCard({
          title: "正文字号", icon: "text",
          control: numberBox({
            min: 8, max: 30, step: 1, suffix: " px", label: "正文字号",
            value: state.settings.main_font_size,
            onChange: (v) => patch("main_font_size", v),
          }),
        }),
      ],
    }));

    root.appendChild(group({
      title: "作业滚动",
      children: [
        settingCard({
          title: "自动滚动作业", icon: "scroll",
          control: toggle(!!state.settings.main_auto_scroll, (v) => patch("main_auto_scroll", v), { label: "自动滚动作业" }),
        }),
        settingCard({
          title: "滚动间隔", icon: "clock",
          control: numberBox({
            min: 20, max: 200, step: 1, suffix: " ms",
            value: state.settings.main_scroll_interval,
            onChange: (v) => patch("main_scroll_interval", v),
          }),
        }),
        settingCard({
          title: "每步滚动距离", icon: "resize",
          control: numberBox({
            min: 1, max: 10, step: 1, suffix: " px",
            value: state.settings.main_scroll_step,
            onChange: (v) => patch("main_scroll_step", v),
          }),
        }),
        settingCard({
          title: "到底暂停", icon: "clock",
          control: numberBox({
            min: 0, max: 200, step: 1, suffix: " 次",
            value: state.settings.main_scroll_pause,
            onChange: (v) => patch("main_scroll_pause", v),
          }),
        }),
      ],
    }));

    root.appendChild(group({
      title: "启动与更新",
      children: [
        settingCard({
          title: "启动时检查更新", hint: "由独立更新器处理，可随时手动检查", icon: "sync",
          control: toggle(!!state.settings.check_update_on_start, (v) => patch("check_update_on_start", v), { label: "启动时检查更新" }),
        }),
        settingCard({
          title: "源码运行保护更新", hint: "检测到本地主入口源码时不再自动更新，改前先提醒备份", icon: "shield",
          control: toggle(!!state.settings.block_update_on_source, (v) => patch("block_update_on_source", v), { label: "源码运行保护更新" }),
        }),
      ],
    }));
  }

  // =====================================================================
  //  外观
  // =====================================================================

  /** 主题预览磁贴（照 CW2 Personalization 的主题网格）。 */
  function themeTiles() {
    const current = state.settings.theme_mode || "system";
    const tiles = [
      { value: "light",  label: "浅色",     sub: "始终使用浅色界面",   icon: "sun",      a: "#fafafa", b: "#e9e9e9" },
      { value: "dark",   label: "深色",     sub: "始终使用深色界面",   icon: "moon",     a: "#2d2d2d", b: "#1b1b1b" },
      { value: "system", label: "跟随系统", sub: "随 Windows 明暗切换", icon: "contrast", a: "#fafafa", b: "#242424" },
    ];

    const pick = (value) => {
      patch("theme_mode", value);
      applyTheme(value);
      renderPage("appearance");     // 磁贴与分段控件的选中态一起刷新
    };

    return el("div", { class: "theme-grid" }, tiles.map((t) =>
      el("button", {
        class: "theme-tile" + (current === t.value ? " is-selected" : ""),
        type: "button", "data-mode": t.value,
        title: t.sub,
        style: { "--tile-a": t.a, "--tile-b": t.b },
        onclick: () => pick(t.value),
      }, [
        el("span", { class: "theme-tile-swatch" }),
        el("span", { class: "theme-check" }, [icon("check", "i16")]),
        el("span", { class: "theme-tile-meta" }, [
          el("span", { class: "theme-tile-name", text: t.label }),
          el("span", { class: "theme-tile-sub", text: t.sub }),
        ]),
      ])));
  }

  function pageAppearance(root) {
    root.appendChild(pageHead("外观", "颜色主题、淡入淡出与窗口材质"));

    const micaCard = isWin11()
      ? settingCard({
          title: "云母材质（Mica）", hint: "Windows 11 的半透明云母背板，会跟着系统明暗变", icon: "palette",
          control: toggle(!!state.settings.settings_mica, (v) => patch("settings_mica", v), { label: "云母材质" }),
        })
      : settingCard({
          title: "云母材质（Mica）", hint: "云母材质需要 Windows 11，当前系统使用普通窗口。", icon: "palette",
          disabled: true,
          control: badge("当前系统不支持", "neutral"),
        });

    root.appendChild(group({
      title: "颜色主题",
      children: [
        el("div", { class: "card" }, [el("div", { class: "mcard-pad" }, [themeTiles()])]),
        settingCard({
          title: "颜色模式", hint: "跟随系统时会随 Windows 的浅色 / 深色实时切换", icon: "contrast",
          control: selectorBar({
            label: "颜色模式",
            value: state.settings.theme_mode || "system",
            options: [
              { value: "system", label: "跟随系统" },
              { value: "light",  label: "浅色" },
              { value: "dark",   label: "深色" },
            ],
            onChange: (v) => { patch("theme_mode", v); applyTheme(v); renderPage("appearance"); },
          }),
        }),
      ],
    }));

    root.appendChild(group({
      title: "淡入淡出",
      children: [
        settingCard({
          title: "窗口打开时渐显", icon: "window",
          control: toggle(!!state.settings.anim_fade_window, (v) => patch("anim_fade_window", v), { label: "窗口打开时渐显" }),
        }),
        settingCard({
          title: "面板展开时渐显", icon: "layers",
          control: toggle(!!state.settings.anim_fade_panel, (v) => patch("anim_fade_panel", v), { label: "面板展开时渐显" }),
        }),
        settingCard({
          title: "文字变化时渐显", icon: "text",
          control: toggle(!!state.settings.anim_fade_text, (v) => patch("anim_fade_text", v), { label: "文字变化时渐显" }),
        }),
        settingCard({
          title: "动画时长", icon: "clock",
          control: numberBox({
            min: 100, max: 2000, step: 50, suffix: " ms",
            value: state.settings.anim_duration,
            onChange: (v) => patch("anim_duration", v),
          }),
        }),
      ],
    }));

    root.appendChild(group({
      title: "窗口材质",
      note: "当前系统：" + (state.info.system || "未知"),
      children: [micaCard],
    }));
  }

  // =====================================================================
  //  灵动岛
  // =====================================================================

  function pageIsland(root) {
    root.appendChild(pageHead("灵动岛", "主岛与副岛的外观与行为"));

    root.appendChild(group({
      title: "主岛",
      children: [
        expander({
          title: "主岛", hint: "顶部居中的悬浮胶囊", icon: "capsule", open: true,
          children: [
            settingItem({
              title: "显示灵动岛",
              control: toggle(!!state.settings.show_island, (v) => patch("show_island", v), { label: "显示灵动岛" }),
            }),
            settingItem({
              title: "距屏幕顶部距离",
              control: numberBox({
                min: 0, max: 100, step: 1, suffix: " px",
                value: state.settings.island_top_margin,
                onChange: (v) => patch("island_top_margin", v),
              }),
            }),
            settingItem({
              title: "提醒条宽度",
              control: numberBox({
                min: 200, max: 800, step: 1, suffix: " px",
                value: state.settings.island_alert_width,
                onChange: (v) => patch("island_alert_width", v),
              }),
            }),
            settingItem({
              title: "提醒条停留",
              control: numberBox({
                min: 100, max: 5000, step: 50, suffix: " ms",
                value: state.settings.island_alert_hold_ms,
                onChange: (v) => patch("island_alert_hold_ms", v),
              }),
            }),
            settingItem({
              title: "仅全屏时隐藏", hint: "全屏看视频 / 演示时自动让位",
              control: toggle(!!state.settings.island_hide_on_fullscreen, (v) => patch("island_hide_on_fullscreen", v), { label: "仅全屏时隐藏" }),
            }),
            settingItem({
              title: "启用唤醒动画", hint: "收起时为圆形，展开后为胶囊",
              control: toggle(!!state.settings.island_show_wakeup_anim, (v) => patch("island_show_wakeup_anim", v), { label: "启用唤醒动画" }),
            }),
          ],
        }),
      ],
    }));

    root.appendChild(group({
      title: "副岛",
      children: [
        expander({
          title: "副岛", hint: "主岛右侧的插件扩展区", icon: "layers", open: true,
          children: [
            settingItem({
              title: "显示副岛", hint: "显示在主岛右侧",
              control: toggle(!!state.settings.show_sub_island, (v) => patch("show_sub_island", v), { label: "显示副岛" }),
            }),
            settingItem({
              title: "默认收成圆形",
              control: toggle(!!state.settings.sub_island_collapsed, (v) => patch("sub_island_collapsed", v), { label: "默认收成圆形" }),
            }),
            settingItem({
              title: "无内容自动收起", hint: "设为 0 表示不自动收起",
              control: numberBox({
                min: 0, max: 120, step: 1, suffix: " 秒",
                value: state.settings.sub_island_auto_collapse_sec,
                onChange: (v) => patch("sub_island_auto_collapse_sec", v),
              }),
            }),
          ],
        }),
      ],
    }));
  }

  // =====================================================================
  //  课表与提醒
  // =====================================================================

  const SCHEDULE_LINKS = [
    { id: "timetable",  title: "课表管理",   hint: "切换、备份与导入导出课表", icon: "calendar", color: "#107C10" },
    { id: "weekend",    title: "周末作息",   hint: "单独设置周末上课时间",     icon: "clock",    color: "#8661C5" },
    { id: "holidays",   title: "假期与调休", hint: "设置假期与调休日",         icon: "calendar", color: "#F7630C" },
    { id: "duty",       title: "值日生名单", hint: "设置值日轮流安排",         icon: "home",     color: "#038387" },
    { id: "statustest", title: "状态测试",   hint: "完整演示一节课的状态变化", icon: "sync",     color: "#5B5FC7" },
  ];

  function pageSchedule(root) {
    root.appendChild(pageHead("课表与提醒", "上课提醒与课表、值日的二级入口"));

    root.appendChild(group({
      title: "上课提醒",
      children: [
        settingCard({
          title: "倒计时时长", hint: "上课前显示蓝色倒计时", icon: "clock",
          control: numberBox({
            min: 5, max: 600, step: 1, suffix: " 秒",
            value: state.settings.island_countdown_sec,
            onChange: (v) => patch("island_countdown_sec", v),
          }),
        }),
        settingCard({
          title: "提前提醒", hint: "整体提前几分钟进上课状态（下课时间不变）", icon: "bell",
          control: numberBox({
            min: 0, max: 60, step: 1, suffix: " 分钟",
            value: state.settings.schedule_advance_minutes ?? 0,
            onChange: (v) => patch("schedule_advance_minutes", v),
          }),
        }),
        settingCard({
          title: "时间偏移", hint: "负数为提前，正数为延后", icon: "clock",
          control: numberBox({
            min: -1800, max: 1800, step: 1, suffix: " 秒",
            value: state.settings.schedule_time_offset_seconds ?? 0,
            onChange: (v) => patch("schedule_time_offset_seconds", v),
          }),
        }),
      ],
    }));

    root.appendChild(group({
      title: "课表与值日",
      children: SCHEDULE_LINKS.map((link) => linkRow({
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
    root.appendChild(pageHead("作业", "按科目分组，改动即时生效"));

    // 编辑器整块嵌在这里 —— 对应原生设置中心「作业」页的做法：不带「取消 / 确认」，
    // 改动即时生效。独立的「编辑作业」对话框用的是同一个编辑器（见 pages/dialogs.js）。
    const editor = window.CDLDialogs.homeworkEditor({ embedded: true });

    root.appendChild(group({
      title: "作业编辑器",
      children: [
        el("div", { class: "card" }, [
          el("div", { class: "card-pad stack" }, [
            editor.node,
            el("div", { class: "hstack" }, [
              button("打开作业文件夹", { icon: "folder", onClick: () => host.invoke("app.openFolder", { id: "homework" }) }),
            ]),
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
   * 「索引来源」由宿主推 sourceOptions 决定画不画、画几个。
   * 具体实现在 pages/market.js —— 它自己带页标题，这里不再叠一个。
   */
  function pagePlugins(root) {
    window.CDLMarket.pluginsPage(root);
  }

  // =====================================================================
  //  高级
  // =====================================================================

  function pageAdvanced(root) {
    root.appendChild(pageHead("高级", "本地插件与日常维护"));

    root.appendChild(group({
      title: "本地插件",
      note: "程序启动时会加载这些插件",
      children: [
        linkRow({
          title: "安装本地插件…", hint: "从 .cblplugin 文件安装", icon: "download", color: "#0F6CBD",
          onClick: () => openDialog("install-local", "安装本地插件"),
        }),
        linkRow({
          title: "打开插件文件夹", hint: "在文件资源管理器中打开", icon: "folder", color: "#B146C2",
          onClick: () => host.invoke("app.openFolder", { id: "plugins" }),
        }),
      ],
    }));

    root.appendChild(group({
      title: "日常维护",
      children: [
        linkRow({
          title: "打开配置文件夹", hint: "查看 settings.json 等配置文件", icon: "folder", color: "#038387",
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
          el("span", { class: "tile" }, [icon("restart", "i20")]),
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
    root.appendChild(pageHead("关于", "版本、运行环境与更新", { hero: true }));

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

    root.appendChild(group({ children: [card] }));
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

    // 宿主保留了原生窗口标题栏（.NET / Qt 都会带 ?chrome=native）时，
    // 页内那条标题栏就重复了 —— 交给 CSS 隐藏，布局随之收成单行网格。
    if (params.get("chrome") === "native") document.body.dataset.nativeChrome = "true";

    // ★ 顺序很重要：先把外壳挂上，再去问宿主拿数据。
    //
    //   反过来做（先 await 两次 RPC 再挂外壳）会有一个致命后果：只要任一 RPC
    //   失败、超时或宿主那边抛异常，body 就是空的 —— 而 body 的底色是
    //   --solid-background-fill-color-base（浅色下 #F3F3F3），于是用户看到的
    //   就是「一片白」，还完全不知道发生了什么。.NET 端报过的白屏就是这么来的。
    // 启动首帧不做过场（is-booting 也让首屏的入场动画闭嘴）
    document.body.classList.add("is-booting");
    applyTheme(wantedTheme || "system", false);
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
      //   不回写设置」，拿它拍照 / 做自检才拍得到深色。写成 settings 优先的话，
      //   只要 theme_mode 有值（默认就是 system），这个参数就永远无效。
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
    document.body.classList.remove("is-booting");

    // 告诉宿主界面已经起来了：撤掉「正在加载」、停掉启动超时计时。
    // 顺带把 bootError 带上，宿主想记诊断日志时不用再问一次。
    host.notify("ui.ready", { page: state.page, bootError: state.bootError || null });

    // 深链接到某个二级对话框（?dialog=holidays），和 ?page= 一个性质：
    // 只影响本次显示。文档截图与自测都靠它。
    const wantedDialog = params.get("dialog");
    if (wantedDialog && window.CDLDialogs) window.CDLDialogs.open(wantedDialog);
  }

  /** 挂外壳（标题栏 + 左侧导航 + 内容区）。挂完 navHost / pageHost 才可用。 */
  function mountShell() {
    const shell = el("div", { class: "app-shell" }, [
      titlebar(),
      el("div", { class: "app-body" }, [
        el("nav", { class: "nav-pane" }, [
          el("div", { class: "nav-search" }, [
            textbox({
              icon: "search", placeholder: "搜索设置", label: "搜索设置",
              onInput: (e) => { state.query = e.target.value; renderNav(); },
            }),
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
