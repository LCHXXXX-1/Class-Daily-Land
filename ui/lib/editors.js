// ============================================================================
//  editors.js —— 二级对话框外壳 + 编辑控件
//  ---------------------------------------------------------------------------
//  设置中心里的二级对话框（假期与调休 / 周末作息 / 值日生名单 / 作业编辑器 /
//  课表管理 / 课表编辑器 / 状态测试）都在页面内以浮层形式打开，不另开窗口：
//  两个宿主都不需要多写一行「开窗」代码，视觉也天然一致。
//
//  这些构件与宿主无关 —— 数据一律通过 host.invoke 走既有那套 RPC。
//  逐字段的文案、列表格式、校验提示都照两端原生实现对位，不要随手改。
// ============================================================================

window.E = (function () {

  const { el, button } = window.C;

  /** 打开的对话框栈（后进先出）。ESC 只关最上面那层。 */
  const stack = [];

  /**
   * 对话框的挂载点。
   *
   * 必须**懒创建**：设置页 boot 时会 `document.body.replaceChildren(shell)`，
   * 早就写在 HTML 里的占位节点会被一起换掉。所以第一次要用的时候才建，
   * 之后就一直挂在 body 末尾。
   */
  function modalRoot() {
    let root = document.getElementById("modal-root");
    if (!root) {
      root = el("div", { id: "modal-root" });
      document.body.appendChild(root);
    }
    return root;
  }

  // ---------------------------------------------------------------- 外壳

  /**
   * 打开一个浮层对话框。
   * @param {object} cfg
   *   title      标题
   *   subtitle   标题下的一行说明（可省）
   *   body       内容节点（可省）
   *   width     面板宽度，默认 720px
   *   buttons    [{ text, primary, danger, subtle, onClick(api) }]
   *   onClose    关闭时的回调（不论怎么关都会调）
   *   nested     是否为叠在另一个对话框之上的子弹窗
   * @returns {{host:HTMLElement, panel:HTMLElement, body:HTMLElement, close:Function}}
   */
  function open(cfg) {
    const body = el("div", { class: "ed-body" }, [cfg.body || null]);

    const panel = el("div", { class: "ed-panel", style: { width: cfg.width || "720px" } }, [
      el("div", { class: "ed-head" }, [
        el("h2", { class: "ed-title", text: cfg.title || "" }),
        cfg.subtitle ? el("p", { class: "ed-subtitle", text: cfg.subtitle }) : null,
      ]),
      body,
      el("div", { class: "ed-foot" }, (cfg.buttons || []).map((spec) =>
        button(spec.text, {
          accent: !!spec.primary,
          danger: !!spec.danger,
          subtle: !!spec.subtle,
          disabled: !!spec.disabled,
          onClick: () => { if (spec.onClick) spec.onClick(api); else api.close(); },
        }))),
    ]);

    const host = el("div", {
      class: "ed-host" + (cfg.nested ? " is-nested" : ""),
      role: "dialog",
      "aria-modal": "true",
      "aria-label": cfg.title || "对话框",
    }, [panel]);

    // 点遮罩关闭（只有点在遮罩本身、不是点在面板里才算）
    host.addEventListener("mousedown", (e) => {
      if (e.target === host) cancel();
    });

    let closed = false;
    const entry = { cancel: () => cancel() };
    stack.push(entry);

    function close(result) {
      if (closed) return;
      closed = true;
      const at = stack.indexOf(entry);
      if (at >= 0) stack.splice(at, 1);
      host.remove();
      if (cfg.onClose) cfg.onClose(result);
    }

    /** 「取消」路径：给调用方一个统一的收尾点。 */
    function cancel() {
      if (cfg.onCancel && cfg.onCancel() === false) return;
      close(false);
    }

    const api = { host, panel, body, close, cancel, stack };

    modalRoot().appendChild(host);
    return api;
  }

  // 全局只挂一个 ESC：永远关最上面那层
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || stack.length === 0) return;
    e.preventDefault();
    stack[stack.length - 1].cancel();
  });

  /**
   * 一句提示（对应原生里的 MessageBox.Show(..., Information/Warning)）。
   * @returns {Promise<void>}
   */
  function tell(parentHost, message, options) {
    options = options || {};
    return new Promise((resolve) => {
      open({
        title: options.title || "提示",
        body: el("p", { class: "ed-message", text: message }),
        width: "420px",
        nested: true,
        buttons: [{ text: options.okText || "好", primary: true, onClick: (api) => { api.close(); resolve(); } }],
        onClose: () => resolve(),
      });
      void parentHost;
    });
  }

  /**
   * 确认框（对应 MessageBox OKCancel + Warning）。
   * @returns {Promise<boolean>}
   */
  function ask(parentHost, message, options) {
    options = options || {};
    return new Promise((resolve) => {
      let answered = false;
      open({
        title: options.title || "确认",
        body: el("p", { class: "ed-message", text: message }),
        width: "440px",
        nested: true,
        buttons: [
          { text: options.cancelText || "取消", onClick: (api) => { api.close(); } },
          {
            text: options.okText || "确定",
            primary: !options.danger,
            danger: !!options.danger,
            onClick: (api) => { answered = true; api.close(); },
          },
        ],
        onClose: () => resolve(answered),
      });
      void parentHost;
    });
  }

  // ---------------------------------------------------------------- 卡片

  /** 分组卡片。对应原生 ScheduleDialogParts.Card。 */
  function card(cfg) {
    return el("section", { class: "ed-card" }, [
      cfg.title ? el("h3", { class: "ed-card-title", text: cfg.title }) : null,
      cfg.subtitle ? el("p", { class: "ed-card-subtitle", text: cfg.subtitle }) : null,
      el("div", { class: "ed-card-body" }, [cfg.body || null]),
    ]);
  }

  /** 一行横向排列（不换行，超出横向滚动）。 */
  function row(children, options) {
    options = options || {};
    return el("div", { class: "ed-row" + (options.wrap ? " is-wrap" : "") }, children);
  }

  /** 「标签 + 控件」的一行。 */
  function field(caption, control) {
    return el("label", { class: "ed-field" }, [
      el("span", { class: "ed-field-caption", text: caption }),
      control,
    ]);
  }

  function emptyHint(text) {
    return el("p", { class: "ed-empty", text: text });
  }

  // ---------------------------------------------------------------- 输入控件
  //  统一返回元素本身；调用方从 .value 读值。

  function textInput(cfg) {
    cfg = cfg || {};
    const node = el("input", {
      class: "ed-input",
      type: "text",
      value: cfg.value == null ? "" : String(cfg.value),
      placeholder: cfg.placeholder || "",
      "aria-label": cfg.label || "",
      style: cfg.width ? { width: cfg.width } : null,
      oninput: cfg.onInput,
      onchange: cfg.onChange,
      onkeydown: cfg.onKeyDown,
    });
    return node;
  }

  /** 数字框：右对齐，失焦时按 min/max 夹取（对应原生的 ReadInt + Clamp）。 */
  function numberInput(cfg) {
    cfg = cfg || {};
    const node = el("input", {
      class: "ed-input is-number",
      type: "text",
      inputmode: "numeric",
      value: cfg.value == null ? "" : String(cfg.value),
      "aria-label": cfg.label || "",
      style: cfg.width ? { width: cfg.width } : null,
      oninput: cfg.onInput,
      onchange: () => {
        const v = readInt(node.value, cfg.value, cfg.min, cfg.max);
        node.value = String(v);
        if (cfg.onChange) cfg.onChange(v);
      },
    });
    return node;
  }

  function readInt(text, fallback, min, max) {
    const parsed = parseInt(String(text == null ? "" : text).trim(), 10);
    let value = Number.isFinite(parsed) ? parsed : fallback;
    if (typeof min === "number") value = Math.max(min, value);
    if (typeof max === "number") value = Math.min(max, value);
    return value;
  }

  function dateInput(cfg) {
    cfg = cfg || {};
    return el("input", {
      class: "ed-input is-date",
      type: "date",
      value: cfg.value || "",
      "aria-label": cfg.label || "",
      style: cfg.width ? { width: cfg.width } : null,
      onchange: cfg.onChange,
    });
  }

  /** 多行文本。注意 textarea 的初值必须写 .value，不能当属性挂。 */
  function textArea(cfg) {
    cfg = cfg || {};
    const node = el("textarea", {
      class: "ed-area",
      placeholder: cfg.placeholder || "",
      "aria-label": cfg.label || "",
      oninput: cfg.onInput,
    }, []);
    if (cfg.height) node.style.height = cfg.height;
    else node.rows = cfg.rows || 6;
    node.value = cfg.value == null ? "" : String(cfg.value);
    return node;
  }

  /** 下拉（原生用的 ComboBox）。options: [{ value, label }] */
  function selectBox(cfg) {
    cfg = cfg || {};
    const node = el("select", {
      class: "ed-select",
      "aria-label": cfg.label || "",
      style: cfg.width ? { width: cfg.width } : null,
      onchange: () => { if (cfg.onChange) cfg.onChange(node.value); },
    }, (cfg.options || []).map((opt) =>
      el("option", { value: String(opt.value), text: opt.label, selected: String(opt.value) === String(cfg.value) ? "" : null })));
    return node;
  }

  /**
   * 可选中列表（原生 ListBox 的对应物）。
   * items: [{ text, value }]；双击触发 onActivate。
   */
  function listBox(cfg) {
    cfg = cfg || {};
    const host = el("div", {
      class: "ed-list",
      tabindex: "0",
      role: cfg.role || "listbox",
      "aria-label": cfg.label || "",
      style: cfg.height ? { height: cfg.height } : null,
    });

    let selected = -1;
    const items = cfg.items || [];

    function paint() {
      host.replaceChildren.apply(host, items.map((item, index) =>
        el("div", {
          class: "ed-list-item" + (index === selected ? " is-selected" : ""),
          role: "option",
          "aria-selected": index === selected ? "true" : "false",
          onclick: () => { select(index); },
          ondblclick: () => { if (cfg.onActivate) cfg.onActivate(item.value, index); },
        }, [el("span", { class: "ed-list-text", text: item.text })])));
      if (items.length === 0) host.replaceChildren(emptyHint(cfg.emptyText || "（空）"));
    }

    function select(index) {
      selected = index;
      paint();
      if (cfg.onSelect) cfg.onSelect(index >= 0 ? items[index].value : null, index);
    }

    host.addEventListener("keydown", (e) => {
      if (items.length === 0) return;
      if (e.key === "ArrowDown") { e.preventDefault(); select(Math.min(items.length - 1, selected + 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); select(Math.max(0, selected - 1)); }
      else if (e.key === "Enter" && selected >= 0 && cfg.onActivate) { e.preventDefault(); cfg.onActivate(items[selected].value, selected); }
    });

    // 外部可能只想知道索引，也可能想整表重画
    const api = {
      node: host,
      setItems(next, keepIndex) {
        items.length = 0;
        for (const it of next || []) items.push(it);
        selected = keepIndex === undefined ? -1 : Math.min(keepIndex, items.length - 1);
        paint();
      },
      get index() { return selected; },
      get value() { return selected >= 0 ? items[selected].value : null; },
      select,
    };

    paint();
    return api;
  }

  return {
    open, tell, ask, card, row, field, emptyHint,
    textInput, numberInput, dateInput, textArea, selectBox, listBox, readInt,
  };
})();
