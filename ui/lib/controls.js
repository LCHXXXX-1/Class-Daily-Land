// ============================================================================
//  controls.js —— Fluent / RinUI 构件的 DOM 构造器
//  每个函数返回一个元素；事件回调把「用户改成了什么」回给页面。
//  这些构件与宿主无关 —— 换成 WebView2 还是 QWebEngineView 都不改一行。
//
//  几何全部照 RinUI 源码（见 styles/tokens.css 顶部的来源说明），
//  构件的分层也照 Class Widgets 2 的用法：
//    group()       分区（Text BodyStrong 标题 + 若干卡片）
//    settingCard() 一张卡一项设置（图标 22 + 标题 Body + 描述 Caption + 右侧动作）
//    settingItem() 卡内密集行（≥50 高、可选箭头、可点）
//    clipRow()     64 高的行（图标 + 标题 + 右侧动作 + 箭头）
//    expander()    可展开卡片（标题栏带实时控件，展开体放子项）
// ============================================================================

window.C = (function () {

  function el(tag, props, children) {
    const node = document.createElement(tag);
    if (props) {
      for (const key of Object.keys(props)) {
        const value = props[key];
        if (value === undefined || value === null) continue;
        if (key === "class") node.className = value;
        else if (key === "text") node.textContent = value;
        else if (key === "html") node.innerHTML = value;
        else if (key.startsWith("on")) node.addEventListener(key.slice(2).toLowerCase(), value);
        else if (key === "style" && typeof value === "object") {
          // 自定义属性必须走 setProperty，直接赋值挂不到 CSS 上
          for (const [prop, val] of Object.entries(value)) {
            if (prop.startsWith("--")) node.style.setProperty(prop, val);
            else node.style[prop] = val;
          }
        }
        else node.setAttribute(key, value);
      }
    }
    // children 里可能嵌套数组（来自 .map()），必须摊平 —— 数组直接传给
    // appendChild/replaceChildren 会被当成字符串，变成 [object HTMLDivElement]
    for (const child of (children || []).flat(Infinity)) {
      if (child === null || child === undefined || child === false) continue;
      node.appendChild(typeof child === "object" ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  /** 摊平 + 过滤空值，供 replaceChildren 之类的场景使用。 */
  function nodes(children) {
    return (children || []).flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false);
  }

  /** 图标（icons.js 提供的全局 iconEl），size 用 i16 / i18 / i19 / i20 / i22 / i24 / i32。 */
  function icon(name, size) {
    return iconEl(name || "info", size || "i20");
  }

  // ---------------------------------------------------------------- 按钮
  function button(label, options) {
    options = options || {};
    const node = el("button", {
      class: "win-btn" + (options.accent ? " is-accent" : "") +
        (options.subtle ? " is-subtle" : "") + (options.danger ? " is-danger" : ""),
      type: "button",
      title: options.title || "",
      onclick: options.onClick,
      disabled: options.disabled ? "" : null,
    });
    if (options.icon) node.appendChild(icon(options.icon, "i16"));
    if (label) node.appendChild(el("span", { text: label }));
    if (options.trailingIcon) node.appendChild(icon(options.trailingIcon, "i16"));
    return node;
  }

  function progressRing() {
    return el("div", {
      class: "win-progressring",
      html: '<svg viewBox="0 0 20 20" width="20" height="20"><circle cx="10" cy="10" r="7.4"/></svg>',
    });
  }

  // ------------------------------------------------------------ 开关
  function toggle(checked, onChange, options) {
    options = options || {};
    const knob = el("span", { class: "knob" });
    const node = el("button", {
      class: "win-toggle",
      type: "button",
      role: "switch",
      "aria-checked": checked ? "true" : "false",
      "aria-label": options.label || "开关",
      disabled: options.disabled ? "" : null,
    }, [knob]);
    node.addEventListener("click", () => {
      const next = node.getAttribute("aria-checked") !== "true";
      node.setAttribute("aria-checked", next ? "true" : "false");
      if (onChange) onChange(next);
    });
    return node;
  }

  // ------------------------------------------------------------ 滑块
  //  v 一律是「显示值」；换算成设置里的真实值由调用方在 onChange 里做。
  //  外观由 DOM 画：4px 轨道 + 强调色填充段 + 「浅色外圈 + 强调色内点」的双层圆点。
  //  真正的 <input type=range> 退成交互层（透明、铺满、盖在最上面），
  //  拖动 / 点击跳转 / 方向键 / 无障碍语义仍然由它负责。
  function slider(cfg) {
    const min = cfg.min, max = cfg.max, step = cfg.step || 1;
    const toDisplay = (v) => String(cfg.format ? cfg.format(v) : v) + (cfg.suffix || "");

    const rail = el("div", { class: "win-slider-rail" }, [
      el("div", { class: "win-slider-track" }),
      el("div", { class: "win-slider-fill" }),
      el("div", { class: "win-slider-thumb" }, [el("span", { class: "win-slider-dot" })]),
    ]);

    let pending = 0;

    const input = el("input", {
      class: "win-slider",
      type: "range",
      min: String(min), max: String(max), step: String(step),
      value: String(cfg.value),
      "aria-label": cfg.label || "滑块",
      oninput: (e) => {
        const v = Number(e.target.value);
        paint(v);
        value.textContent = toDisplay(v);
        if (cfg.onInput) cfg.onInput(v);
        // 拖动过程里合并回写，避免每一像素都打一次宿主
        clearTimeout(pending);
        pending = setTimeout(() => { if (cfg.onChange) cfg.onChange(v); }, 150);
      },
      onchange: (e) => {
        clearTimeout(pending);
        if (cfg.onChange) cfg.onChange(Number(e.target.value));
      },
    });

    const field = el("div", { class: "win-slider-field" }, [input, rail]);
    const value = el("span", { class: "win-slider-value", text: toDisplay(cfg.value) });
    const wrap = el("div", { class: "win-slider-wrap" }, [field, value]);

    // 只写这一个自定义属性。填充段宽度与圆点位置都由 CSS 的
    // calc((100% - 22px) * var(--pct)) 算出来 —— JS 不必知道控件有多宽，
    // 两个盒子又都是绝对定位，所以拖动时不会牵动任何布局。
    function paint(v) {
      const ratio = max === min ? 0 : (v - min) / (max - min);
      field.style.setProperty("--pct", Math.max(0, Math.min(1, ratio)).toFixed(4));
    }

    paint(cfg.value);
    return wrap;
  }

  // --------------------------------------------------- 数字框（带微调）
  function numberBox(cfg) {
    const min = cfg.min, max = cfg.max, step = cfg.step || 1;
    const clamp = (v) => Math.min(max, Math.max(min, v));
    const input = el("input", {
      type: "text",
      inputmode: "numeric",
      value: String(cfg.value),
      "aria-label": cfg.label || "数值",
      onchange: () => commit(Number(input.value)),
      onblur: () => commit(Number(input.value)),
      onkeydown: (e) => {
        if (e.key === "ArrowUp") { e.preventDefault(); commit(Number(input.value) + step); }
        if (e.key === "ArrowDown") { e.preventDefault(); commit(Number(input.value) - step); }
        if (e.key === "Enter") input.blur();
      },
    });
    function commit(v) {
      if (!Number.isFinite(v)) v = cfg.value;
      v = clamp(Math.round(v / step) * step);
      input.value = String(v);
      if (cfg.onChange) cfg.onChange(v);
    }
    const up = el("button", { type: "button", text: "\u25B2", tabindex: "-1", onclick: () => commit(Number(input.value) + step) });
    const down = el("button", { type: "button", text: "\u25BC", tabindex: "-1", onclick: () => commit(Number(input.value) - step) });
    return el("div", { class: "win-numberbox", title: cfg.hint || "" }, [
      input,
      el("div", { class: "spin" }, [up, down]),
      cfg.suffix ? el("span", { class: "caption", style: { paddingRight: "8px" }, text: cfg.suffix.trim() }) : null,
    ]);
  }

  // ------------------------------------------------------------ 下拉框
  function combo(cfg) {
    const root = el("div", { class: "win-combo" });
    const label = el("span", { text: "" });
    const trigger = el("button", { type: "button", "aria-haspopup": "listbox" }, [
      label, el("span", { class: "chev" }),
    ]);
    const popup = el("div", { class: "popup", role: "listbox" });

    function setValue(value, notify) {
      cfg.value = value;
      const hit = cfg.options.find((o) => o.value === value) || cfg.options[0];
      label.textContent = hit ? hit.label : "";
      popup.querySelectorAll("button").forEach((b) => {
        b.setAttribute("aria-selected", b.dataset.value === value ? "true" : "false");
      });
      if (notify && cfg.onChange) cfg.onChange(value);
    }

    cfg.options.forEach((option) => {
      const item = el("button", {
        type: "button", role: "option", "data-value": option.value, text: option.label,
        onclick: () => { setValue(option.value, true); root.classList.remove("is-open"); },
      });
      popup.appendChild(item);
    });

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      document.querySelectorAll(".combo.is-open").forEach((c) => { if (c !== root) c.classList.remove("is-open"); });
      root.classList.toggle("is-open");
    });

    document.addEventListener("click", () => root.classList.remove("is-open"));
    setValue(cfg.value, false);
    root.appendChild(trigger);
    root.appendChild(popup);
    return root;
  }

  // ------------------------------------------- 分段控件（Segmented）
  function segmented(cfg) {
    const root = el("div", { class: "win-segmented", role: "tablist", "aria-label": cfg.label || "" });
    cfg.options.forEach((option) => {
      const item = el("button", {
        type: "button", role: "tab", text: option.label, "data-value": option.value,
        "aria-selected": option.value === cfg.value ? "true" : "false",
        onclick: () => {
          root.querySelectorAll("button").forEach((b) =>
            b.setAttribute("aria-selected", b.dataset.value === option.value ? "true" : "false"));
          if (cfg.onChange) cfg.onChange(option.value);
        },
      });
      root.appendChild(item);
    });
    return root;
  }

  // ------------------------------- 下划线选项卡（SelectorBar，视觉更轻）
  function selectorBar(cfg) {
    const root = el("div", { class: "win-selectorbar", role: "tablist", "aria-label": cfg.label || "" });
    cfg.options.forEach((option) => {
      const item = el("button", {
        type: "button", role: "tab", text: option.label, "data-value": option.value,
        "aria-selected": option.value === cfg.value ? "true" : "false",
        onclick: () => {
          root.querySelectorAll("button").forEach((b) =>
            b.setAttribute("aria-selected", b.dataset.value === option.value ? "true" : "false"));
          if (cfg.onChange) cfg.onChange(option.value);
        },
      });
      root.appendChild(item);
    });
    return root;
  }

  // ------------------------------------------------------------ 文本框
  function textbox(cfg) {
    cfg = cfg || {};
    const input = el("input", {
      type: cfg.type || "search",
      value: cfg.value || "",
      placeholder: cfg.placeholder || "",
      "aria-label": cfg.label || cfg.placeholder || "",
      oninput: cfg.onInput,
      onkeydown: cfg.onKeyDown,
    });
    return el("label", { class: "win-textbox" }, [
      cfg.icon ? icon(cfg.icon, "i16") : null,
      input,
    ]);
  }

  // -------------------------------------------------------------- 提示条
  function infoBar(cfg) {
    const iconName = { success: "success", warning: "warning", error: "error" }[cfg.severity] || "info";
    const node = el("div", { class: "win-infobar" + (cfg.severity ? " is-" + cfg.severity : "") }, [
      el("span", { class: "bar-icon" }, [icon(iconName, "i20")]),
      el("div", { class: "bar-body" }, [
        cfg.title ? el("div", { class: "bar-title", text: cfg.title }) : null,
        cfg.message ? el("div", { class: "bar-msg", html: cfg.html ? cfg.message : null, text: cfg.html ? null : cfg.message }) : null,
      ]),
      cfg.onClose ? button("", { subtle: true, icon: "close", title: "关闭", onClick: () => node.remove() }) : null,
    ]);
    return node;
  }

  // ------------------------------------------------------------- 徽标
  function badge(text, variant) {
    return el("span", { class: "win-badge" + (variant ? " is-" + variant : "") }, [
      variant === "ok" || variant === "warn" ? el("span", { class: "win-dot" }) : null,
      el("span", { text: text }),
    ]);
  }

  /** 内联小徽标（InfoBadge）：高 16 全圆角，用于「内置」「不兼容」这类短标记。 */
  function infoBadge(text, variant) {
    return el("span", {
      class: "win-infobadge" + (variant ? " is-" + variant : ""),
      text: text,
    });
  }

  // ------------------------------------------------------------- 进度条
  function progressBar(cfg) {
    cfg = cfg || {};
    const fill = el("i");
    const node = el("div", { class: "win-progressbar" + (cfg.indeterminate ? " is-indeterminate" : "") }, [fill]);
    if (!cfg.indeterminate) {
      const pct = Math.max(0, Math.min(1, Number(cfg.value) || 0)) * 100;
      fill.style.width = pct + "%";
    }
    node.setFill = (v) => {
      const pct = Math.max(0, Math.min(1, Number(v) || 0)) * 100;
      fill.style.width = pct + "%";
    };
    return node;
  }

  // ================================================== 分区与设置行 ==========

  /** 分区标题（CW2 用 Typography.BodyStrong）。 */
  function groupHead(title) {
    return el("h2", { class: "group-head", text: title });
  }

  /**
   * 一个分区：标题 + 内容。
   * cfg = { title, note, children }
   */
  function group(cfg) {
    const parts = [];
    if (cfg.title) parts.push(groupHead(cfg.title));
    (cfg.children || []).forEach((child) => {
      if (child === null || child === undefined || child === false) return;
      parts.push(child);
    });
    if (cfg.note) parts.push(el("p", { class: "group-note", text: cfg.note }));
    return el("section", { class: "group" }, parts);
  }

  /**
   * SettingCard —— 一张卡一项设置。
   * cfg = { title, hint, icon, control, disabled, onClick, clickable, note }
   */
  function settingCard(cfg) {
    cfg = cfg || {};
    const row = el("div", {
      class: "scard" + (cfg.disabled ? " is-disabled" : "") + (cfg.clickable ? " is-clickable" : ""),
      onclick: cfg.clickable ? cfg.onClick : null,
    }, [
      el("div", { class: "scard-main" }, [
        cfg.icon ? el("span", { class: "scard-icon" }, [icon(cfg.icon, "i22")]) : null,
        el("div", { class: "scard-text" }, [
          el("div", { class: "scard-title", text: cfg.title || "" }),
          cfg.hint ? el("div", { class: "scard-desc", text: cfg.hint }) : null,
        ]),
      ]),
      el("div", { class: "scard-action" }, cfg.control ? [].concat(cfg.control) : []),
    ]);
    return el("div", { class: "card" }, [row, cfg.note ? el("p", { class: "group-note card-pad", text: cfg.note }) : null]);
  }

  /**
   * SettingItem —— 卡内密集行（无外框，靠分隔线分）。
   * cfg = { title, hint, control, disabled, clickable, onClick, chevron, first, flat }
   */
  function settingItem(cfg) {
    cfg = cfg || {};
    return el("div", {
      class: "sitem" +
        (cfg.disabled ? " is-disabled" : "") +
        (cfg.clickable ? " is-clickable" : "") +
        (cfg.flat ? " is-flat" : "") +
        (cfg.first ? " is-first" : ""),
      onclick: cfg.clickable ? cfg.onClick : null,
    }, [
      el("div", { class: "sitem-main" }, [
        el("div", { class: "sitem-title", text: cfg.title || "" }),
        cfg.hint ? el("div", { class: "sitem-desc", text: cfg.hint }) : null,
      ]),
      el("div", { class: "sitem-action" }, [
        [].concat(cfg.control || []),
        cfg.chevron ? el("span", { class: "chev" }) : null,
      ]),
    ]);
  }

  /**
   * ClipRow —— CW2 的 ClipItem：固定 64 高、顶部 1px 分隔线、悬停有底色。
   * cfg = { title, hint, icon, control, onClick, chevron, disabled, first }
   */
  function clipRow(cfg) {
    cfg = cfg || {};
    return el("button", {
      class: "crow" +
        (cfg.disabled ? " is-disabled" : "") +
        (cfg.first ? " is-first" : ""),
      type: "button",
      disabled: cfg.disabled ? "" : null,
      onclick: cfg.onClick,
    }, [
      cfg.icon ? el("span", { class: "crow-icon" }, [icon(cfg.icon, "i22")]) : null,
      el("span", { class: "crow-title", text: cfg.title || "" }),
      cfg.control ? el("span", { class: "crow-action" }, [].concat(cfg.control)) : null,
      cfg.chevron ? el("span", { class: "chev" }) : null,
    ]);
  }

  /** 二级入口（图标磁贴 + 标题 + 说明 + 箭头），观感比 clipRow 更「大卡」。 */
  function linkRow(cfg) {
    return el("button", {
      class: "win-linkrow",
      type: "button",
      style: cfg.tileColor ? { "--tile-color": cfg.tileColor } : undefined,
      onclick: cfg.onClick,
    }, [
      el("span", { class: "tile" }, [icon(cfg.icon || "external", "i20")]),
      el("span", {}, [
        el("div", { class: "row-title", text: cfg.title }),
        cfg.hint ? el("div", { class: "row-hint", text: cfg.hint }) : null,
      ]),
      el("span", { class: "chev" }),
    ]);
  }

  /**
   * 可展开卡片（SettingExpander）。
   * 标题栏左侧是图标 + 标题 + 说明，右侧是实时控件（action）与展开箭头；
   * 展开体放子行。动画 333ms（RinUI animationSpeedExpander）。
   * cfg = { title, hint, icon, action, children, open }
   */
  function expander(cfg) {
    cfg = cfg || {};
    const body = el("div", { class: "card" }, nodes(cfg.children));
    const node = el("section", { class: "exp" + (cfg.open ? " is-open" : "") });

    const head = el("button", {
      class: "exp-head",
      type: "button",
      "aria-expanded": cfg.open ? "true" : "false",
      onclick: () => {
        const open = !node.classList.contains("is-open");
        node.classList.toggle("is-open", open);
        head.setAttribute("aria-expanded", open ? "true" : "false");
      },
    }, [
      el("span", { class: "exp-main" }, [
        cfg.icon ? el("span", { class: "scard-icon" }, [icon(cfg.icon, "i22")]) : null,
        el("span", { class: "scard-text" }, [
          el("span", { class: "scard-title", text: cfg.title || "" }),
          cfg.hint ? el("span", { class: "scard-desc", text: cfg.hint }) : null,
        ]),
      ]),
      el("span", { class: "exp-action" }, cfg.action ? [].concat(cfg.action) : []),
      el("span", { class: "exp-chev" }, [el("span", { class: "chev" })]),
    ]);

    node.appendChild(head);
    node.appendChild(el("div", { class: "exp-body" }, [el("div", {}, [body])]));
    return node;
  }

  // ------------------------------------------------- 旧接口（保持兼容） ----
  /** 旧的行式设置行；现在映射到 settingItem 的横排版本 .row。 */
  function settingRow(cfg) {
    return el("div", { class: "row" + (cfg.disabled ? " is-disabled" : "") }, [
      el("div", {}, [
        el("div", { class: "row-title", text: cfg.title }),
        cfg.hint ? el("div", { class: "row-hint", text: cfg.hint }) : null,
      ]),
      el("div", { class: "row-control" }, cfg.control ? [].concat(cfg.control) : []),
    ]);
  }

  /** 旧的「卡片包多行」分组；市场页等仍在用，保留。 */
  function cardGroup(cfg) {
    const card = el("div", { class: "card" }, cfg.rows);
    return el("section", { class: "group" }, [
      cfg.title ? el("h3", { class: "group-head", text: cfg.title }) : null,
      card,
      cfg.note ? el("p", { class: "group-note", text: cfg.note }) : null,
    ]);
  }

  // ------------------------------------------------------------ 对话框
  function dialog(cfg) {
    const host = el("div", { class: "win-dialog-host" });
    const box = el("div", { class: "win-dialog", role: "dialog", "aria-modal": "true" }, [
      el("h3", { text: cfg.title }),
      el("p", { text: cfg.message || "" }),
      el("div", { class: "actions" }, [
        button(cfg.closeText || "取消", { onClick: () => host.remove() }),
        cfg.primaryText
          ? button(cfg.primaryText, {
              accent: !cfg.danger, danger: !!cfg.danger,
              onClick: () => { host.remove(); if (cfg.onPrimary) cfg.onPrimary(); },
            })
          : null,
      ]),
    ]);
    host.appendChild(box);
    host.addEventListener("click", (e) => { if (e.target === host) host.remove(); });
    document.addEventListener("keydown", function onKey(e) {
      if (e.key === "Escape") { host.remove(); document.removeEventListener("keydown", onKey); }
    });
    return host;
  }

  return {
    // 基础
    el, nodes, icon, button, progressRing,
    // 输入控件
    toggle, slider, numberBox, combo, segmented, selectorBar, textbox,
    // 反馈
    infoBar, badge, infoBadge, progressBar,
    // 行 / 卡片 / 分区
    groupHead, group, settingCard, settingItem, clipRow, linkRow, expander,
    // 旧接口
    settingRow, cardGroup, dialog,
  };
})();
