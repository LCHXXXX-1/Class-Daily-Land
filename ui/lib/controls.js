// ============================================================================
//  controls.js —— WinUI 3 控件的 DOM 构造器
//  每个函数返回一个元素；事件回调把「用户改成了什么」回给页面。
//  这些构件与宿主无关 —— 换成 WebView2 还是 QWebEngineView 都不改一行。
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
    if (options.icon) node.appendChild(iconEl(options.icon, "i16"));
    if (label) node.appendChild(el("span", { text: label }));
    if (options.trailingIcon) node.appendChild(iconEl(options.trailingIcon, "i16"));
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
  //
  //  外观由 DOM 画（几何与配色见 styles/components.css 里的 .win-slider-*）：
  //  一条 4px 轨道、一段强调色填充、一个「浅色外圆 + 强调色内点」的双层圆点。
  //  真正的 <input type=range> 退成交互层（透明、铺满、盖在最上面），
  //  拖动 / 点击跳转 / 方向键 / 无障碍语义仍然由它负责。
  //
  //  以前是直接给 input 的 ::-webkit-slider-thumb 上 transform + transition ——
  //  Chromium 下伪元素会被逐帧重新栅格化，拖动时看着一直在抖，所以改掉了。
  function slider(cfg) {
    const min = cfg.min, max = cfg.max, step = cfg.step || 1;
    const toDisplay = (v) => String(cfg.format ? cfg.format(v) : v) + (cfg.suffix || "");

    const rail = el("div", { class: "win-slider-rail" }, [
      el("div", { class: "win-slider-track" }),
      el("div", { class: "win-slider-fill" }),
      el("div", { class: "win-slider-thumb" }, [el("span", { class: "win-slider-dot" })]),
    ]);

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

    const field = el("div", { class: "win-slider-field" }, [rail, input]);
    const value = el("span", { class: "win-slider-value", text: toDisplay(cfg.value) });
    const wrap = el("div", { class: "win-slider-wrap" }, [field, value]);

    let pending = 0;

    // 只写这一个自定义属性。填充段宽度与圆点位置都由 CSS 的
    // calc((100% - 20px) * var(--pct)) 算出来 —— JS 不必知道控件有多宽，
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
      document.querySelectorAll(".win-combo.is-open").forEach((c) => { if (c !== root) c.classList.remove("is-open"); });
      root.classList.toggle("is-open");
    });

    document.addEventListener("click", () => root.classList.remove("is-open"));
    setValue(cfg.value, false);
    root.appendChild(trigger);
    root.appendChild(popup);
    return root;
  }

  // --------------------------------------------- 分段控件（SelectorBar）
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

  // -------------------------------------------------------------- 提示条
  function infoBar(cfg) {
    const iconName = { success: "success", warning: "warning", error: "error" }[cfg.severity] || "info";
    const node = el("div", { class: "win-infobar" + (cfg.severity ? " is-" + cfg.severity : "") }, [
      el("span", { class: "bar-icon" }, [iconEl(iconName, "i20")]),
      el("div", {}, [
        cfg.title ? el("div", { class: "bar-title", text: cfg.title }) : null,
        cfg.message ? el("div", { class: "bar-msg", text: cfg.message }) : null,
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

  // ------------------------------------------------------ 链接行（带图标）
  function linkRow(cfg) {
    return el("button", {
      class: "win-linkrow",
      type: "button",
      style: cfg.tileColor ? { "--tile-color": cfg.tileColor } : undefined,
      onclick: cfg.onClick,
    }, [
      el("span", { class: "tile" }, [iconEl(cfg.icon || "external", "i20")]),
      el("span", {}, [
        el("div", { class: "row-title", text: cfg.title }),
        cfg.hint ? el("div", { class: "row-hint", text: cfg.hint }) : null,
      ]),
      el("span", { class: "chev" }),
    ]);
  }

  // ------------------------------------------------------------ 设置行
  function settingRow(cfg) {
    return el("div", { class: "row" + (cfg.disabled ? " is-disabled" : "") }, [
      el("div", {}, [
        el("div", { class: "row-title", text: cfg.title }),
        cfg.hint ? el("div", { class: "row-hint", text: cfg.hint }) : null,
      ]),
      el("div", { class: "row-control" }, cfg.control ? [].concat(cfg.control) : []),
    ]);
  }

  function cardGroup(cfg) {
    const card = el("div", { class: "card" }, cfg.rows);
    return el("section", { class: "card-group" }, [
      cfg.title ? el("h3", { class: "group-title" + (cfg.section ? " is-section" : ""), text: cfg.title }) : null,
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
    el, nodes, button, toggle, slider, numberBox, combo, selectorBar,
    infoBar, badge, linkRow, settingRow, cardGroup, dialog, progressRing,
  };
})();
