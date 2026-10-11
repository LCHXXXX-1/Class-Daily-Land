// ============================================================================
//  market.js —— 设置中心「插件」页（插件市场 + 第三方包 + 本地插件 + 运行日志）
//  ---------------------------------------------------------------------------
//  布局照 Python 版的 market_page.py / package_page.py 来：一个插件一张卡片，
//  卡片上有状态徽章、版本变化、作者、说明、⚠ 原因、进度条、临时提示，以及
//  按状态决定显隐的操作按钮。
//
//  ★ 但**更新逻辑不进这一层** —— 两端本来就不一样：
//      · .NET  索引固定走 by-net 仓库的 plugin 分支（raw → jsDelivr → github），
//              没有「选源」这回事；
//      · Python 有 market_source / packages_source，可选 官方服务器 / GitHub / Gitee。
//    所以「索引来源」这个下拉是**宿主驱动**的：宿主给了 sourceOptions 才画，
//    给几个画几个；没给就整行不出现。切换源也是交给宿主（market.setSource）。
//    页面只负责把宿主说的显示出来，不替任何一端做决定。
//
//  实时性靠宿主推事件（host.on）：日志、进度、完成、依赖下载、忙闲。
// ============================================================================

window.CDLMarket = (function () {

  const { el, nodes, button, badge, progressRing } = window.C;
  const E = window.E;

  /** 状态 → 中文标签。与 Python 版 market_page.py 的 STATUS_TEXT 逐字一致。 */
  const STATUS_TEXT = {
    not_installed: "未安装",
    installed: "已安装",
    update: "可更新",
    disabled: "已禁用",
    failed: "加载失败",
    invalid: "装不了",
  };

  /** 状态 → 徽章色调（见 components.css 的 .win-badge）。 */
  const STATUS_TONE = {
    not_installed: "",
    installed: "ok",
    update: "accent",
    disabled: "warn",
    failed: "danger",
    invalid: "danger",
  };

  const statusBadge = (status) =>
    badge(STATUS_TEXT[status] || status, STATUS_TONE[status] || "");

  // =====================================================================
  //  插件市场的一张卡片
  // =====================================================================

  function marketCard(entry, page) {
    const nameLabel = el("span", { class: "mc-name", text: "" });
    const badgeHost = el("span", { class: "mc-badge" });
    const verLabel = el("span", { class: "mc-ver", text: "" });

    const idLabel = el("div", { class: "mc-id", text: "" });
    const descLabel = el("div", { class: "mc-desc", text: "" });
    const warnLabel = el("div", { class: "mc-warn", text: "" });
    const msgLabel = el("div", { class: "mc-msg", text: "" });
    const bar = el("div", { class: "mc-progress" }, [el("div", { class: "mc-progress-fill" })]);

    const btnInstall = button("装上", { onClick: () => page.install(entryRef.id) });
    const btnUpdate = button("更新", { onClick: () => page.install(entryRef.id) });
    const btnEnable = button("启用", { onClick: () => page.setEnabled(entryRef.id, true) });
    const btnDisable = button("禁用", { onClick: () => page.setEnabled(entryRef.id, false) });
    const btnUninstall = button("卸掉", { onClick: () => page.uninstall(entryRef.id) });

    const node = el("div", { class: "market-card" }, [
      el("div", { class: "mc-head" }, [nameLabel, badgeHost, el("span", { class: "spacer" }), verLabel]),
      idLabel,
      descLabel,
      warnLabel,
      bar,
      msgLabel,
      el("div", { class: "mc-actions" }, [btnInstall, btnUpdate, btnEnable, btnDisable, btnUninstall]),
    ]);

    // 按钮闭包里要拿「最新的」entry，所以留一个可变引用
    let entryRef = entry;
    let flashTimer = 0;

    function update(next) {
      entryRef = next;
      const status = next.status || "not_installed";

      nameLabel.textContent = next.name || next.id || "";
      badgeHost.replaceChildren(statusBadge(status));

      const remote = next.version || "";
      const local = next.installedVersion || "";
      verLabel.textContent = (next.installed && local && remote && local !== remote)
        ? "v" + local + " → v" + remote
        : (remote ? "v" + remote : "版本未知");

      idLabel.textContent = "id: " + (next.id || "") + "    作者: " + (next.author || "?");

      const desc = next.description ? String(next.description).trim() : "";
      descLabel.textContent = desc;
      descLabel.hidden = !desc;

      setWarning(next.problem || next.loadError || "");

      // 记录有问题也留退路：真装了还能卸
      const has = status === "installed" || status === "update"
        || status === "disabled" || status === "failed";
      const installedNow = !!next.installed;

      btnInstall.hidden = status !== "not_installed";
      btnUpdate.hidden = status !== "update";
      btnUninstall.hidden = !(has || installedNow);
      btnEnable.hidden = status !== "disabled";
      btnDisable.hidden = !(has && status !== "disabled");
    }

    function setWarning(reason) {
      const text = String(reason || "").trim();
      warnLabel.textContent = text ? "⚠ " + text : "";
      warnLabel.hidden = !text;
    }

    function setProgress(percent) {
      if (percent < 0) {
        bar.hidden = true;
        bar.firstChild.style.width = "0%";
      } else {
        bar.hidden = false;
        bar.firstChild.style.width = Math.max(0, Math.min(100, percent)) + "%";
      }
    }

    /** 临时提示，8 秒后自己收起来（与 Python 版一致）。 */
    function flash(text, ok) {
      msgLabel.textContent = text;
      msgLabel.className = "mc-msg " + (ok ? "is-ok" : "is-bad");
      msgLabel.hidden = false;
      clearTimeout(flashTimer);
      flashTimer = setTimeout(() => { msgLabel.hidden = true; }, 8000);
    }

    /** 依赖下载进度：进度条 + 实时文案。 */
    function showDep(ev) {
      const stage = String((ev && ev.stage) || "");
      const text = String((ev && ev.text) || "");
      const percent = Number((ev && ev.percent) != null ? ev.percent : -1);

      // 收尾就收进度条；中间过程按宿主给的百分比画
      if (stage === "done" || stage === "failed") setProgress(-1);
      else setProgress(percent >= 0 ? percent : 0);

      if (text) {
        msgLabel.textContent = text;
        msgLabel.className = "mc-msg " + (stage === "failed" ? "is-bad" : "");
        msgLabel.hidden = false;
      }
    }

    update(entry);
    setProgress(-1);
    msgLabel.hidden = true;

    return { node, update, setWarning, setProgress, flash, showDep, get entry() { return entryRef; } };
  }

  // =====================================================================
  //  第三方包的一张卡片
  // =====================================================================

  function packageCard(entry, page) {
    const nameLabel = el("span", { class: "mc-name", text: "" });
    const badgeHost = el("span", { class: "mc-badge" });
    const verLabel = el("span", { class: "mc-ver", text: "" });
    const useLabel = el("div", { class: "mc-desc", text: "" });
    const bar = el("div", { class: "mc-progress" }, [el("div", { class: "mc-progress-fill" })]);

    const btnInstall = button("安装", { onClick: () => page.install(entryRef.name) });
    const btnUpdate = button("更新", { onClick: () => page.install(entryRef.name) });
    const btnUninstall = button("删除", { onClick: () => page.uninstall(entryRef.name) });

    const node = el("div", { class: "market-card" }, [
      el("div", { class: "mc-head" }, [nameLabel, badgeHost, el("span", { class: "spacer" }), verLabel]),
      useLabel,
      bar,
      el("div", { class: "mc-actions" }, [btnInstall, btnUpdate, btnUninstall]),
    ]);

    let entryRef = entry;
    let flashTimer = 0;

    function update(next) {
      entryRef = next;
      const status = next.status || "not_installed";
      nameLabel.textContent = next.name || "";

      let text = STATUS_TEXT[status] || status;
      if (status === "installed" && next.manual) text = "已安装 · 手动";
      badgeHost.replaceChildren(badge(text, STATUS_TONE[status] || ""));

      const remote = next.version || "";
      const local = next.installedVersion || "";
      if (next.installed && local && remote && local !== remote) verLabel.textContent = "v" + local + " → v" + remote;
      else if (local) verLabel.textContent = "v" + local;
      else if (remote) verLabel.textContent = "v" + remote;
      else verLabel.textContent = "版本未知";

      const users = next.usedBy || [];
      if (users.length) useLabel.textContent = "被插件使用：" + users.join("、");
      else if (next.installed) useLabel.textContent = "当前没有插件使用它";
      else useLabel.textContent = "暂无插件声明此依赖";

      btnInstall.hidden = status !== "not_installed";
      btnUpdate.hidden = status !== "update";
      btnUninstall.hidden = !next.installed;
    }

    function setProgress(percent) {
      if (percent < 0) { bar.hidden = true; bar.firstChild.style.width = "0%"; }
      else { bar.hidden = false; bar.firstChild.style.width = Math.max(0, Math.min(100, percent)) + "%"; }
    }

    function flash(text, ok) {
      useLabel.textContent = text;
      useLabel.className = "mc-desc " + (ok ? "is-ok" : "is-bad");
      clearTimeout(flashTimer);
      flashTimer = setTimeout(() => { useLabel.className = "mc-desc"; update(entryRef); }, 8000);
    }

    update(entry);
    setProgress(-1);

    return { node, update, setProgress, flash, get entry() { return entryRef; } };
  }

  // =====================================================================
  //  整页
  // =====================================================================

  function pluginsPage(root) {
    root.appendChild(el("h1", { class: "page-title", text: "插件" }));

    // ---------------- 运行日志（整页共用一份） ----------------

    const logBox = el("pre", { class: "market-log", text: "尚未同步。" });
    const logLines = [];

    function log(text) {
      const stamp = new Date().toTimeString().slice(0, 8);
      logLines.push("[" + stamp + "] " + text);
      if (logLines.length > 400) logLines.splice(0, logLines.length - 400);
      logBox.textContent = logLines.join("\n");
      logBox.scrollTop = logBox.scrollHeight;
    }

    // ---------------- 重启提示横幅 ----------------

    const bannerText = el("span", { class: "banner-text" });
    const banner = el("div", { class: "market-banner" }, [
      bannerText,
      button("✕", { subtle: true, onClick: () => { banner.hidden = true; } }),
    ]);
    banner.hidden = true;

    // ---------------- 工具栏 ----------------

    const spinner = progressRing();
    spinner.style.display = "none";
    const syncLabel = el("span", { text: "检查更新" });
    const syncBtn = el("button", { class: "win-btn is-accent", type: "button" }, [spinner, syncLabel]);
    const rescanBtn = button("刷新一下", { onClick: () => doSync("market.rescan", "刷新本地状态") });
    const updateAllBtn = button("⬆ 全部更新", { onClick: () => updateAll() });
    const openDirBtn = button("打开插件文件夹", { onClick: () => host.invoke("app.openFolder", { id: "plugins" }) });

    const sourceLabel = el("span", { class: "caption", text: "索引来源：" });
    const sourceSelect = el("select", { class: "ed-select", "aria-label": "索引来源", onchange: () => changeSource(sourceSelect.value) });
    const sourceRow = el("div", { class: "market-source" }, [sourceLabel, sourceSelect]);

    const statusLine = el("div", { class: "market-status", text: "还没同步过" });

    // ---------------- 市场列表 ----------------

    const marketList = el("div", { class: "market-list" });
    const marketEmpty = el("div", { class: "empty", text: "暂无插件\n\n点击上方「检查更新」从插件索引拉取插件列表" });
    const marketCards = new Map();

    // ---------------- 第三方包 ----------------

    const packList = el("div", { class: "market-list" });
    const packEmpty = el("div", { class: "empty", text: "还没有依赖包。插件声明的依赖会在安装时自动准备。" });
    const packCards = new Map();
    const packSyncBtn = button("刷新列表", { accent: true, onClick: () => doSync("packages.sync", "刷新依赖包列表") });
    const packSourceLabel = el("span", { class: "caption", text: "下载源：" });
    const packSourceSelect = el("select", { class: "ed-select", "aria-label": "下载源", onchange: () => changePackageSource(packSourceSelect.value) });
    const packSourceRow = el("div", { class: "market-source" }, [packSourceLabel, packSourceSelect]);
    const manualName = E.textInput({ width: "200px", label: "包名" });
    const packStatus = el("div", { class: "market-status", text: "还没刷新过" });

    // ---------------- 本地已安装插件 ----------------

    const localList = el("div", { class: "market-list" });

    // ================================================================
    //  渲染
    // ================================================================

    let busy = false;

    function setBusy(next) {
      busy = !!next;
      syncBtn.disabled = busy;
      rescanBtn.disabled = busy;
      updateAllBtn.disabled = busy || updateCount === 0;
      spinner.style.display = busy ? "" : "none";
      if (busy) statusLine.textContent = "正在忙…";
    }

    let updateCount = 0;

    function renderMarket(status) {
      const entries = (status && status.entries) || [];
      const options = (status && status.sourceOptions) || [];

      // 索引来源：宿主给了选项才画（.NET 是固定源，整行都不出现）
      if (options.length > 1) {
        sourceRow.hidden = false;
        sourceSelect.replaceChildren.apply(sourceSelect, options.map((opt) =>
          el("option", { value: String(opt.value), text: opt.label, selected: String(opt.value) === String(status.source) ? "" : null })));
      } else {
        sourceRow.hidden = true;
      }

      statusLine.textContent = status && status.lastSync
        ? "上次检查：" + status.lastSync + " · " + (status.sourceLabel || status.source || "")
        : "还没同步过";

      updateCount = entries.filter((e) => e.updateAvailable).length;
      updateAllBtn.textContent = updateCount ? "⬆ 全部更新(" + updateCount + ")" : "⬆ 全部更新";
      updateAllBtn.disabled = busy || updateCount === 0;

      marketEmpty.hidden = entries.length > 0;

      // 按 id 复用已有卡片，别整块重建 —— 否则进度条跟临时提示会被刷掉
      const seen = new Set();
      const nextNodes = [];
      for (const entry of entries) {
        const key = String(entry.id || "") || ("?" + nextNodes.length);
        seen.add(key);
        let card = marketCards.get(key);
        if (!card) {
          card = marketCard(entry, marketApi);
          marketCards.set(key, card);
        } else {
          card.update(entry);
        }
        nextNodes.push(card.node);
      }
      for (const key of [...marketCards.keys()]) {
        if (!seen.has(key)) marketCards.delete(key);
      }
      marketList.replaceChildren.apply(marketList, nextNodes);
    }

    function renderPackages(status) {
      const entries = (status && status.entries) || [];
      const options = (status && status.sourceOptions) || [];

      if (options.length > 1) {
        packSourceRow.hidden = false;
        packSourceSelect.replaceChildren.apply(packSourceSelect, options.map((opt) =>
          el("option", { value: String(opt.value), text: opt.label, selected: String(opt.value) === String(status.source) ? "" : null })));
      } else {
        packSourceRow.hidden = true;
      }

      packStatus.textContent = status && status.lastSync
        ? "上次刷新：" + status.lastSync + " · " + (status.sourceLabel || status.source || "")
        : "还没刷新过";

      packEmpty.hidden = entries.length > 0;

      const seen = new Set();
      const nextNodes = [];
      for (const entry of entries) {
        const key = String(entry.name || "");
        seen.add(key);
        let card = packCards.get(key);
        if (!card) { card = packageCard(entry, packageApi); packCards.set(key, card); }
        else card.update(entry);
        nextNodes.push(card.node);
      }
      for (const key of [...packCards.keys()]) if (!seen.has(key)) packCards.delete(key);
      packList.replaceChildren.apply(packList, nextNodes);
    }

    async function renderLocal() {
      const result = await host.invoke("plugins.list").catch(() => null);
      const plugins = (result && result.plugins) || [];
      if (plugins.length === 0) {
        localList.replaceChildren(el("div", { class: "empty", text: "还没有安装任何插件。把插件文件夹放进 plugins/ 目录，或用上面的市场装上。" }));
        return;
      }
      localList.replaceChildren.apply(localList, plugins.map((plugin) =>
        el("div", { class: "market-card" }, [
          el("div", { class: "mc-head" }, [
            el("span", { class: "mc-name", text: plugin.name || plugin.id }),
            plugin.loaded ? badge("已加载", "ok") : badge("未加载", "warn"),
            el("span", { class: "spacer" }),
            el("span", { class: "mc-ver", text: plugin.version ? "v" + plugin.version : "" }),
          ]),
          el("div", { class: "mc-id", text: plugin.id || "" }),
          plugin.desc ? el("div", { class: "mc-desc", text: plugin.desc }) : null,
          plugin.failure ? el("div", { class: "mc-warn", text: "⚠ " + plugin.failure }) : null,
          plugin.requires && plugin.requires.length
            ? el("div", { class: "mc-desc", text: "依赖：" + plugin.requires.join("、") })
            : null,
        ])));
    }

    // ================================================================
    //  操作
    // ================================================================

    async function doSync(method, what) {
      log("开始" + what + " …");
      setBusy(true);
      try {
        const result = await host.invoke(method);
        if (result && result.log) for (const line of result.log) log(line);
        if (method === "market.rescan" || method === "market.sync") renderMarket(result);
        else renderPackages(result);
        if (result && result.error) log("失败：" + result.error);
      } catch (err) {
        log("失败：" + (err && err.message ? err.message : err));
      } finally {
        setBusy(false);
      }
    }

    async function changeSource(value) {
      log("已切换索引来源：" + value);
      setBusy(true);
      try { await host.invoke("market.setSource", { source: value }); } catch (err) { log(String(err)); }
      finally { setBusy(false); }
      await doSync("market.sync", "同步索引");
    }

    async function changePackageSource(value) {
      log("已切换下载源：" + value);
      setBusy(true);
      try { await host.invoke("packages.setSource", { source: value }); } catch (err) { log(String(err)); }
      finally { setBusy(false); }
      await doSync("packages.sync", "刷新依赖包列表");
    }

    async function updateAll() {
      log("开始全部更新 …");
      setBusy(true);
      try {
        const result = await host.invoke("market.updateAll");
        if (result && result.log) for (const line of result.log) log(line);
        for (const item of (result && result.items) || []) {
          log((item.success ? "✓ " : "✗ ") + item.name + "：" + (item.message || ""));
          if (item.id && marketCards.has(item.id)) marketCards.get(item.id).flash((item.success ? "✓ " : "✗ ") + (item.message || ""), item.success);
        }
        if (result && result.restartRequired) showBanner();
        await doSync("market.rescan", "刷新本地状态");
      } catch (err) {
        log("失败：" + (err && err.message ? err.message : err));
      } finally {
        setBusy(false);
      }
    }

    function showBanner() {
      bannerText.textContent = "更新 / 卸载 / 启用 / 禁用等改动需重启程序后生效";
      banner.hidden = false;
    }

    const marketApi = {
      install: (id) => runTask("market.install", { id: id }, id),
      uninstall: (id) => runTask("market.uninstall", { id: id }, id),
      setEnabled: (id, enabled) => runTask("market.setEnabled", { id: id, enabled: enabled }, id),
    };

    const packageApi = {
      install: (name) => runTask("packages.install", { name: name }, name),
      uninstall: async (name) => {
        const ok = await E.ask(null, "确定删除依赖包「" + name + "」吗？", { okText: "删除", danger: true });
        if (!ok) return;
        await runTask("packages.uninstall", { name: name }, name);
      },
    };

    async function runTask(method, params, key) {
      log(method + " → " + (params.id || params.name));

      const marketTarget = marketCards.get(key);
      const packageTarget = packCards.get(key);
      const target = params.id ? marketTarget : packageTarget;

      try {
        const result = await host.invoke(method, params);
        const ok = !!(result && result.ok);
        const message = (result && (result.message || result.reason)) || "";

        // 宿主把活儿丢给工作线程时会回 pending —— 这时候**不能**下结论说「✓ 完成」，
        // 真正的结果由 xxx.done 事件带回来（Python 侧的安装 / 卸载 / 批量更新就是这种）。
        if (result && result.pending) {
          if (target && target.flash) target.flash(message || "正在处理…", true);
          if (message) log(message);
          return;
        }

        if (target) {
          target.flash((ok ? "✓ " : "✗ ") + (message || (ok ? "完成" : "失败")), ok);
          // 失败原因常驻，别只闪 8 秒就没了
          if (!ok && target.setWarning) target.setWarning(message);
          target.setProgress(-1);
        }
        if (message) log((ok ? "✓ " : "✗ ") + message);

        if (ok && result && result.restartRequired) showBanner();
        refreshSoon(method.startsWith("market.") ? "market" : "packages");
      } catch (err) {
        const text = err && err.message ? err.message : String(err);
        if (target) { target.flash("✗ " + text, false); if (target.setWarning) target.setWarning(text); }
        log("✗ " + text);
      }
    }

    // 去抖：一个操作可能同时触发「RPC 回来」和「宿主推 done」两条路径，
    // 两边都想刷新列表 —— 合成一次就够。
    let refreshTimers = { market: 0, packages: 0 };
    function refreshSoon(which) {
      clearTimeout(refreshTimers[which]);
      refreshTimers[which] = setTimeout(() => {
        if (which === "market") doSync("market.rescan", "刷新本地状态");
        else doSync("packages.sync", "刷新依赖包列表");
      }, 300);
    }

    // ================================================================
    //  宿主推来的事件
    // ================================================================

    host.on("market.log", (payload) => { if (payload && payload.text) log(String(payload.text)); });
    host.on("market.busy", (payload) => setBusy(!!(payload && payload.busy)));

    host.on("market.progress", (payload) => {
      const id = String((payload && payload.id) || "");
      const card = marketCards.get(id);
      if (card) card.setProgress(Number(payload.percent));
    });

    host.on("market.done", (payload) => {
      const id = String((payload && payload.id) || "");
      const card = marketCards.get(id);
      const ok = !!(payload && payload.ok);
      const message = (payload && payload.message) || "";
      if (card) {
        card.flash((ok ? "✓ " : "✗ ") + message, ok);
        if (!ok) card.setWarning(message);
        card.setProgress(-1);
      }
      if (message) log((ok ? "✓ " : "✗ ") + message);
      if (ok && payload && payload.restartRequired) showBanner();
      refreshSoon("market");
    });

    host.on("market.dep", (payload) => {
      const id = String((payload && payload.id) || "");
      const card = marketCards.get(id);
      if (card) card.showDep(payload);
      if (payload && payload.text) log(String(payload.text));
    });

    host.on("market.changed", () => refreshSoon("market"));

    host.on("packages.log", (payload) => { if (payload && payload.text) log(String(payload.text)); });
    host.on("packages.busy", (payload) => setBusy(!!(payload && payload.busy)));

    host.on("packages.progress", (payload) => {
      const card = packCards.get(String((payload && payload.name) || ""));
      if (card) card.setProgress(Number(payload.percent));
    });

    host.on("packages.done", (payload) => {
      const card = packCards.get(String((payload && payload.name) || ""));
      const ok = !!(payload && payload.ok);
      const message = (payload && payload.message) || "";
      if (card) card.flash((ok ? "✓ " : "✗ ") + message, ok);
      if (message) log((ok ? "✓ " : "✗ ") + message);
      refreshSoon("packages");
    });

    // ================================================================
    //  骨架
    // ================================================================

    root.appendChild(el("section", { class: "card-group" }, [
      el("div", { class: "card" }, [
        el("div", { class: "card-pad" }, [
          el("div", { class: "hstack" }, [syncBtn, rescanBtn, updateAllBtn, openDirBtn]),
          sourceRow,
          statusLine,
        ]),
        banner,
      ]),
      el("h3", { class: "group-title is-section", text: "插件市场" }),
      marketEmpty,
      marketList,
    ]));

    root.appendChild(el("section", { class: "card-group" }, [
      el("h3", { class: "group-title is-section", text: "已安装的插件" }),
      localList,
    ]));

    root.appendChild(el("section", { class: "card-group" }, [
      el("h3", { class: "group-title is-section", text: "第三方包管理" }),
      el("p", { class: "group-note", text: "第三方依赖由插件在 plugin.json 的 requires 中声明，安装插件时会自动准备。" }),
      el("div", { class: "card" }, [
        el("div", { class: "card-pad" }, [
          el("div", { class: "hstack" }, [packSyncBtn, packSourceRow]),
          el("div", { class: "hstack", style: { marginTop: "8px" } }, [
            el("span", { class: "caption", text: "手动安装：" }),
            manualName,
            button("安装此包", { onClick: () => installManual() }),
          ]),
          packStatus,
        ]),
      ]),
      packEmpty,
      packList,
    ]));

    root.appendChild(el("section", { class: "card-group" }, [
      el("h3", { class: "group-title is-section", text: "运行日志" }),
      logBox,
    ]));

    async function installManual() {
      const name = manualName.value.trim();
      if (!name) { await E.tell(null, "请先填包名。"); return; }
      await runTask("packages.install", { name: name, manual: true }, name);
      manualName.value = "";
    }

    syncBtn.addEventListener("click", () => doSync("market.sync", "同步索引"));

    // ---------------- 首屏：先画骨架，再拉数据 ----------------
    //  （顺序不能反：任一 RPC 失败也不该让整页空着）

    (async () => {
      try {
        renderMarket(await host.invoke("market.status"));
      } catch (err) {
        log("读取索引失败：" + (err && err.message ? err.message : err));
        renderMarket({ entries: [] });
      }
      try {
        renderPackages(await host.invoke("packages.status"));
      } catch (err) {
        log("读取依赖包失败：" + (err && err.message ? err.message : err));
        renderPackages({ entries: [] });
      }
      await renderLocal();
    })();
  }

  return { pluginsPage, STATUS_TEXT, STATUS_TONE, marketCard, packageCard };
})();
