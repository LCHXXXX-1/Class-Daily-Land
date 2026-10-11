// ============================================================================
//  dialogs.js —— 二级对话框（设置中心里的浮层）
//  ---------------------------------------------------------------------------
//  这 6 个对话框在原生两端本来是独立的窗口，现在都在页面内打开。
//  逐字段的文案、列表格式、校验提示、空态都与两端原生实现对位 —— 改之前请先看
//  .NET 侧 Views/Dialogs/*.cs 或 Python 侧对应文件，别凭感觉改。
//
//  数据一律通过 host.invoke 走既有 RPC。RPC 清单见 ui/README.md。
// ============================================================================

window.CDLDialogs = (function () {

  const { el, button } = window.C;
  const E = window.E;

  /** 0=周一 … 6=周日（与两端内部约定一致） */
  const DAY_HEADERS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

  // ---------------------------------------------------------------- 小工具

  function liRow(text, actions, options) {
    options = options || {};
    return el("div", { class: "ed-li-row", style: options.indent ? { paddingLeft: options.indent } : null }, [
      el("div", { class: "ed-li-main", text: text, title: text }),
      el("div", { class: "ed-li-actions" }, actions),
    ]);
  }

  function smallButton(text, onClick) {
    return button(text, { subtle: true, onClick: onClick });
  }

  /** 把 Promise 里的失败统一变成一句人话。 */
  async function call(method, params) {
    return host.invoke(method, params);
  }

  async function guard(fn) {
    try { return await fn(); }
    catch (err) {
      await E.tell(null, (err && err.message) ? err.message : String(err), { title: "操作失败" });
      return null;
    }
  }

  // =====================================================================
  //  假期与调休
  // =====================================================================

  function openHolidays() {
    let data = { holidays: [], makeupDays: [] };

    const holidayList = E.listBox({ height: "150px", label: "假期列表", emptyText: "暂无假期" });
    const makeupList = E.listBox({ height: "130px", label: "调休列表", emptyText: "暂无调休" });

    const startBox = E.dateInput({ label: "开始日期" });
    const endBox = E.dateInput({ label: "结束日期" });
    const nameBox = E.textInput({ width: "150px", label: "假期名称" });
    nameBox.title = "起个名（可以不填，比如：国庆）";

    const makeupDate = E.dateInput({ label: "调休日期" });
    const makeupWeekday = E.selectBox({
      label: "补周几",
      value: "0",
      options: DAY_HEADERS.map((day, index) => ({ value: String(index), label: "补" + day })),
    });

    const api = E.open({
      title: "假期与调休",
      subtitle: "一个悲伤的故事",
      width: "820px",
      body: el("div", {}, [
        E.card({
          title: "放假的日期段",
          subtitle: "可以加好几段",
          body: [
            holidayList.node,
            E.row([
              E.field("开始", startBox),
              E.field("结束", endBox),
              nameBox,
              button("加上", { accent: true, onClick: () => addHoliday() }),
              button("删除选中项", { onClick: () => removeHoliday() }),
            ]),
          ],
        }),
        E.card({
          title: "要补课的日子",
          subtitle: "周末和假期也得按“补周几”来上课",
          body: [
            makeupList.node,
            E.row([
              E.field("日期", makeupDate),
              makeupWeekday,
              button("加上", { accent: true, onClick: () => addMakeup() }),
              button("删除选中项", { onClick: () => removeMakeup() }),
            ]),
          ],
        }),
      ]),
      buttons: [{ text: "关闭", primary: true, onClick: (a) => a.close() }],
    });

    async function reload() {
      const result = await guard(() => call("schedule.holidays.get"));
      if (!result) return;
      data = result;
      holidayList.setItems((result.holidays || []).map((item) => ({
        text: item.start + " ～ " + item.end + (item.name ? "（" + item.name + "）" : ""),
      })));
      makeupList.setItems((result.makeupDays || []).map((item) => ({
        text: item.date + " → 补" + DAY_HEADERS[Math.min(6, Math.max(0, item.asWeekday | 0))],
      })));
    }

    async function addHoliday() {
      const start = startBox.value;
      const end = endBox.value;
      if (!start || !end) {
        await E.tell(api.host, "请把开始和结束日期都选上。");
        return;
      }
      if (await guard(() => call("schedule.holidays.add", {
        start: start, end: end, name: nameBox.value.trim(),
      })) === null) return;

      nameBox.value = "";
      await reload();
    }

    async function removeHoliday() {
      if (holidayList.index < 0) {
        await E.tell(api.host, "请先选中要删除的假期。");
        return;
      }
      await guard(() => call("schedule.holidays.remove", { index: holidayList.index }));
      await reload();
    }

    async function addMakeup() {
      if (!makeupDate.value) {
        await E.tell(api.host, "请先选日期。");
        return;
      }
      await guard(() => call("schedule.makeup.add", {
        date: makeupDate.value, asWeekday: E.readInt(makeupWeekday.value, 0, 0, 6),
      }));
      await reload();
    }

    async function removeMakeup() {
      if (makeupList.index < 0) {
        await E.tell(api.host, "请先选中要删除的调休日。");
        return;
      }
      await guard(() => call("schedule.makeup.remove", { index: makeupList.index }));
      await reload();
    }

    const today = new Date();
    const iso = today.getFullYear() + "-" +
      String(today.getMonth() + 1).padStart(2, "0") + "-" +
      String(today.getDate()).padStart(2, "0");
    startBox.value = iso;
    endBox.value = iso;
    makeupDate.value = iso;

    reload();
  }

  // =====================================================================
  //  周末作息
  // =====================================================================

  function openWeekend() {
    let afternoon = [];

    const splitBox = E.textInput({ width: "100px", label: "上午分界点" });
    const coursesBox = E.textArea({ height: "160px", rows: 8, label: "周末课程" });
    const periodHost = el("div", { class: "ed-stack is-tight" });

    const api = E.open({
      title: "周末作息",
      subtitle: "上午沿用平日课表中开始时间早于分界点的节次；下午使用下面单独配置的节次。",
      width: "720px",
      body: el("div", {}, [
        E.row([E.field("上午分界点：", splitBox)]),
        E.card({
          title: "下午节次",
          subtitle: "留空表示周末只有上午有课",
          body: [
            button("＋ 加一节", { onClick: () => {
              afternoon.push({ name: "午" + (afternoon.length + 1), start: "13:30", end: "14:15" });
              paintPeriods();
            } }),
            el("div", { style: { marginTop: "10px" } }, [periodHost]),
          ],
        }),
        E.card({
          title: "周末课程",
          subtitle: "一行一节，与上面的节次顺序对应",
          body: [coursesBox],
        }),
      ]),
      buttons: [
        { text: "取消", onClick: (a) => a.close() },
        { text: "保存", primary: true, onClick: () => save() },
      ],
    });

    function paintPeriods() {
      periodHost.replaceChildren.apply(periodHost, afternoon.map((period, index) => {
        const nameNode = E.textInput({ width: "100px", value: period.name, label: "节次名" });
        const startNode = E.textInput({ width: "86px", value: period.start, label: "开始" });
        const endNode = E.textInput({ width: "86px", value: period.end, label: "结束" });
        nameNode.addEventListener("input", () => { period.name = nameNode.value; });
        startNode.addEventListener("input", () => { period.start = startNode.value.trim(); });
        endNode.addEventListener("input", () => { period.end = endNode.value.trim(); });

        return E.row([
          nameNode, startNode, endNode,
          button("删除", { onClick: () => { afternoon.splice(index, 1); paintPeriods(); } }),
        ]);
      }));
      if (afternoon.length === 0) periodHost.replaceChildren(E.emptyHint("还没有下午节次"));
    }

    async function save() {
      const split = splitBox.value.trim() || "12:00";
      const courses = coursesBox.value
        .replace(/\r\n/g, "\n")
        .split("\n")
        .map((line) => line.trim());

      const result = await guard(() => call("schedule.weekend.set", {
        morningSplit: split, afternoonPeriods: afternoon, courses: courses,
      }));
      if (result === null) return;
      api.close(true);
    }

    (async () => {
      const data = await guard(() => call("schedule.weekend.get"));
      if (!data) return;
      splitBox.value = data.morningSplit || "12:00";
      afternoon = (data.afternoonPeriods || []).map((p) => ({ name: p.name, start: p.start, end: p.end }));
      coursesBox.value = (data.courses || []).join("\n");
      paintPeriods();
    })();
    paintPeriods();
  }

  // =====================================================================
  //  值日生名单
  // =====================================================================

  function openDuty() {
    const nameBox = E.textInput({ width: "220px", label: "姓名" });
    const listHost = el("div", { class: "ed-scroll ed-stack is-tight ed-listbox", style: { height: "220px" } });

    const api = E.open({
      title: "值日生名单",
      width: "560px",
      body: el("div", {}, [
        E.row([
          el("span", { class: "ed-field-caption", text: "逐个添加：" }),
          nameBox,
          button("加上", { onClick: () => addSingle() }),
        ]),
        el("div", { style: { margin: "6px 0 8px" } }, [
          button("一次加多几个（用逗号隔开）", {
            onClick: () => openBatch(),
          }),
        ]),
        listHost,
      ]),
      buttons: [{ text: "关闭", onClick: (a) => a.close() }],
    });

    // 原生那个「一次加多几个」的按钮是通栏的，这里跟一下
    const batchBtn = api.body.querySelectorAll(".win-btn")[1];
    if (batchBtn) batchBtn.style.width = "100%";

    async function reload() {
      const data = await guard(() => call("duty.get"));
      if (!data) return;
      const names = data.list || [];
      if (names.length === 0) {
        listHost.replaceChildren(E.emptyHint("暂无值日生"));
        return;
      }
      listHost.replaceChildren.apply(listHost, names.map((name, index) =>
        liRow((index + 1) + ". " + name, [
          smallButton("删除", () => removeAt(index)),
        ])));
    }

    async function addSingle() {
      const name = nameBox.value.trim();
      if (!name) {
        await E.tell(api.host, "姓名不能为空");
        return;
      }
      await guard(() => call("duty.add", { name: name }));
      nameBox.value = "";
      await reload();
    }

    async function removeAt(index) {
      await guard(() => call("duty.remove", { index: index }));
      await reload();
    }

    function openBatch() {
      const area = E.textArea({ height: "130px", rows: 6, label: "姓名" });
      const batch = E.open({
        title: "批量添加值日生",
        width: "500px",
        nested: true,
        body: el("div", {}, [
          el("p", { class: "ed-message", text: "姓名（用逗号分隔）：" }),
          area,
        ]),
        buttons: [
          { text: "取消", onClick: (a) => a.close() },
          { text: "确认", primary: true, onClick: () => confirm() },
        ],
      });

      async function confirm() {
        async function splitBy(sep) {
          return area.value.split(sep).map((n) => n.trim()).filter((n) => n.length > 0);
        }

        // 与源项目一致：先按英文逗号，只切出一个再试中文逗号
        let names = await splitBy(",");
        if (names.length === 1) names = await splitBy("，");

        if (names.length === 0) {
          await E.tell(batch.host, "姓名不能为空");
          return;
        }

        const result = await guard(() => call("duty.addMany", { names: names }));
        if (result === null) return;
        batch.close(true);
        await reload();
      }
    }

    reload();
  }

  // =====================================================================
  //  作业编辑器
  //
  //  两种用法（与原生一致）：
  //    · 独立的「编辑作业」对话框 —— 带「取消 / 确认」
  //    · **内嵌**进设置中心的「作业」页 —— 没有取消/确认，改动即时生效
  //  所以外面套什么壳由 options.embedded 决定，编辑器本体只有一份。
  // =====================================================================

  function buildHomeworkEditor(options) {
    options = options || {};

    const subjectBox = E.textInput({ width: "150px", label: "科目" });
    const dateBox = E.textInput({ width: "200px", label: "提交日期" });
    const contentBox = E.textArea({ height: "70px", rows: 3, label: "作业内容" });
    const listHost = el("div", { class: "ed-scroll ed-listbox", style: { height: "280px" } });

    const body = el("div", {}, [
      E.row([E.field("科目：", subjectBox)]),
      el("div", { style: { marginTop: "8px" } }, [E.row([E.field("提交日期（可以自己填）：", dateBox)])]),
      el("div", { style: { marginTop: "8px" } }, [
        el("p", { class: "ed-field-caption", text: "作业内容：" }),
        contentBox,
      ]),
      el("div", { style: { display: "flex", justifyContent: "center", margin: "10px 0" } }, [
        button("添加作业", { onClick: () => addHomework() }),
      ]),
      listHost,
    ]);

    const api = options.embedded
      ? null
      : E.open({
          title: "编辑作业",
          width: "760px",
          body: body,
          buttons: [
            { text: "取消", onClick: (a) => a.close() },
            { text: "确认", primary: true, onClick: async (a) => {
              await guard(() => call("homework.save"));
              a.close(true);
            } },
          ],
        });

    async function reload() {
      const data = await guard(() => call("homework.get"));
      if (!data) return;

      const groups = data.groups || [];
      if (groups.length === 0) {
        listHost.replaceChildren(E.emptyHint("暂无作业"));
        return;
      }

      const nodes = [];
      for (const group of groups) {
        const title = group.subject + (group.date ? " (" + group.date + ")" : "");
        nodes.push(el("div", { class: "ed-group-head" }, [
          el("div", { class: "ed-group-title", text: title }),
          smallButton("全部清除", () => clearSubject(group.subject)),
        ]));
        for (const entry of (group.entries || [])) {
          nodes.push(liRow((entry.index + 1) + ". " + entry.content, [
            smallButton("修改", () => editItem(entry.index)),
            smallButton("删除", () => removeItem(entry.index)),
          ], { indent: "20px" }));
        }
      }
      listHost.replaceChildren.apply(listHost, nodes);
    }

    async function addHomework() {
      const subject = subjectBox.value.trim();
      const content = contentBox.value.trim();
      if (!subject || !content) {
        await E.tell(null, "科目和作业内容都不能为空。");
        return;
      }
      const result = await guard(() => call("homework.add", {
        subject: subject, content: content, date: dateBox.value.trim(),
      }));
      if (result === null) return;

      subjectBox.value = "";
      dateBox.value = "";
      contentBox.value = "";
      await reload();
    }

    async function clearSubject(subject) {
      const ok = await E.ask(null, "要清除「" + subject + "」的全部作业吗？", { okText: "清除", danger: true });
      if (!ok) return;
      await guard(() => call("homework.clearSubject", { subject: subject }));
      await reload();
    }

    async function removeItem(index) {
      await guard(() => call("homework.remove", { index: index }));
      await reload();
    }

    async function editItem(index) {
      const data = await guard(() => call("homework.get"));
      if (!data) return;
      const item = (data.items || []).find((x) => x.index === index);
      if (!item) return;

      const subject = E.textInput({ width: "180px", value: item.subject, label: "科目" });
      const date = E.textInput({ width: "180px", value: item.date, label: "提交日期" });
      const content = E.textArea({ height: "100px", value: item.content, label: "作业内容" });

      E.open({
        title: "修改作业",
        width: "520px",
        nested: true,
        body: el("div", {}, [
          E.row([E.field("科目：", subject)]),
          el("div", { style: { marginTop: "8px" } }, [E.row([E.field("提交日期：", date)])]),
          el("div", { style: { marginTop: "8px" } }, [
            el("p", { class: "ed-field-caption", text: "作业内容：" }),
            content,
          ]),
        ]),
        buttons: [
          { text: "取消", onClick: (a) => a.close() },
          { text: "确认", primary: true, onClick: async (a) => {
            const result = await guard(() => call("homework.update", {
              index: index,
              subject: subject.value.trim(),
              content: content.value.trim(),
              date: date.value.trim(),
            }));
            if (result === null) return;
            a.close(true);
            await reload();
          } },
        ],
      });
    }

    reload();
    return { node: options.embedded ? body : api.host, api: api, reload: reload };
  }

  function openHomeworkEditor() {
    buildHomeworkEditor({ embedded: false });
  }

  // ---------------------------------------------------------------- 注册表
  //  只放「已经迁到 Web」的；没登记的由 settings.js 回落到宿主的原生对话框。

  const registry = {
    holidays: { title: "假期与调休", open: openHolidays },
    weekend: { title: "周末作息", open: openWeekend },
    duty: { title: "值日生名单", open: openDuty },
    "homework-editor": { title: "编辑作业", open: openHomeworkEditor },
  };

  return {
    DAY_HEADERS: DAY_HEADERS,
    has: (id) => Object.prototype.hasOwnProperty.call(registry, id),
    title: (id) => (registry[id] ? registry[id].title : id),
    ids: () => Object.keys(registry),
    open(id) {
      const entry = registry[id];
      if (!entry) return false;
      entry.open();
      return true;
    },
    /** 作业编辑器可以内嵌进设置页（对应原生设置中心「作业」页的做法）。 */
    homeworkEditor: (options) => buildHomeworkEditor(options || {}),
  };
})();
