import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import RinUI
import "../components"

// 课表编辑器（完整版）：
//   选表 / 新建 / 复制 / 重命名 / 删除 / 设为当前
//   节次编辑（增删行、改名称与起止时间）+ 每日课程编辑
//   导出 JSON / CSV（表头与编码由主程序 schedule 模块决定，与原版同源）
//   导入（文件 / 粘贴文本，先预览再合并或替换）
//   临时调课（日期 + 当日课程串）
//
// 数据全走 TimetableStore（委托主程序 ScheduleManager），写入前在 Python
// 侧过 normalize_timetable 校验 —— 界面不做格式裁剪，不另立规则。
SubPage {

    // 左侧导航只列顶层页（见 Settings.qml 的说明），子页靠这个面包屑定位 + 返回
    contentHeader: PageHeader {
        rootTitle: "设置"
        parentTitle: "课表与提醒"
        currentTitle: "课表管理"
        description: "当前课表、节次时间与导入导出"
        onRootClicked: settingsWindow.gotoTitle("首页")
        onParentClicked: settingsWindow.gotoTitle("课表与提醒")
    }
    id: root

    property var tables: []
    property string currentName: ""
    property var editPeriods: []          // [{name,start,end}]
    property var editTimetable: ({})      // {"0": [...], ...}
    property string tipText: ""
    property bool tipIsError: true

    // ---- 周末课表（独立数据，不属于任何一张日常课表）----
    property var weekendSplit: "12:00"
    property var weekendAfternoon: []       // [{name,start,end}]
    property var weekendCourses: []         // ["数学", ...]
    property int weekendPeriodCount: 0
    property bool weekendAvailable: false

    // ★ 只留周一~周五 —— 周末课表是**另一套数据**（ScheduleManager.data["weekend"]：
    //   上下午分界 + 下午专属节次 + 一份共用课程），不走 timetable 的5/6 两列。
    //   以前这里硬塞 7 天、周末写进 timetable，而后端读 weekend.courses，
    //   两套数据互不相通 → 填了周末课灵动岛还是「今日无课」。
    readonly property var dayNames: ["周一", "周二", "周三", "周四", "周五"]
    readonly property int cellWidth: 110

    Component.onCompleted: {
        if (TimetableStore.isAvailable()) {
            tables = TimetableStore.list()
            var hit = tables.length ? (tables.find(t => t.active) || tables[0]) : null
            loadDetail(hit ? TimetableStore.detail(hit.name) : {})
        } else {
            tables = []
        }
        loadWeekend()
    }

    function loadDetail(doc) {
        editPeriods = (doc && doc.periods) ? doc.periods.map(function (p) {
            return { name: p.name || "", start: p.start || "", end: p.end || "" }
        }) : []
        var tt = {}
        for (var d = 0; d < 5; d++) tt[String(d)] = []   // 只周一~周五，周末另设
        if (doc && doc.timetable) {
            for (var key in doc.timetable) tt[key] = doc.timetable[key].slice()
        }
        editTimetable = tt
        currentName = (doc && doc.name) ? doc.name : ""
    }

    function refreshList(keepName) {
        tables = TimetableStore.list()
        var target = keepName || currentName
        var hit = tables.find(t => t.name === target) || tables.find(t => t.active)
        loadDetail(hit ? TimetableStore.detail(hit.name) : {})
    }

    function setTip(text, isError) {
        tipText = text
        tipIsError = isError !== false
    }

    function loadWeekend() {
        if (!TimetableStore.isAvailable()) {
            weekendAvailable = false
            return
        }
        var w = TimetableStore.weekend()
        weekendAvailable = w.available === true
        weekendSplit = w.morningSplit || "12:00"
        weekendAfternoon = (w.afternoonPeriods || []).map(function (p) {
            return { name: p.name || "", start: p.start || "", end: p.end || "" }
        })
        weekendCourses = (w.courses || []).slice()
        weekendPeriodCount = w.periodCount || 0
    }

    function saveWeekend() {
        var result = TimetableStore.saveWeekend(
            weekendSplit, weekendAfternoon, weekendCourses)
        setTip(result.ok ? "已保存周末课表" : (result.error || "保存失败"),
               result.ok)
        if (result.ok) loadWeekend()
    }

    function addWeekendPeriod() {
        var list = weekendAfternoon.slice()
        list.push({ name: "下午" + (list.length + 1), start: "", end: "" })
        weekendAfternoon = list
    }

    function removeWeekendPeriod(index) {
        var list = weekendAfternoon.slice()
        list.splice(index, 1)
        weekendAfternoon = list
    }

    function addWeekendCourse() {
        var list = weekendCourses.slice()
        list.push("")
        weekendCourses = list
    }

    function removeWeekendCourse(index) {
        var list = weekendCourses.slice()
        list.splice(index, 1)
        weekendCourses = list
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        InfoBar {
            Layout.fillWidth: true
            severity: TimetableStore.isAvailable() ? Severity.Info : Severity.Warning
            title: TimetableStore.isAvailable()
                   ? "改动直接落盘到 settings/schedule.json（与主窗 / 灵动岛共用）"
                   : "课表服务不可用"
            text: TimetableStore.isAvailable()
                  ? "导入 / 导出的文件格式与原版一致（JSON 带格式版本；CSV 表头相同、Excel 直开不乱码）。"
                  : "独立演示模式下没找到 ClassDailyLand-Py。用 --py-root 指定项目目录，"
                    + "或直接从主程序里打开设置。"
        }

        Text {
            visible: tipText.length > 0
            color: tipIsError ? Theme.currentTheme.colors.systemCautionColor
                              : Theme.currentTheme.colors.systemSuccessColor
            text: tipText
        }

        // ================= 选表与管理 =================
        Text { typography: Typography.BodyStrong; text: "课表" }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 108
            padding: 16

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    ComboBox {
                        id: tablePicker
                        Layout.preferredWidth: 220
                        textRole: "name"
                        model: root.tables
                        enabled: root.tables.length > 0

                        onActivated: function (index) {
                            var hit = root.tables[index]
                            if (hit) loadDetail(TimetableStore.detail(hit.name))
                        }
                    }

                    Button {
                        text: "设为当前"
                        enabled: currentName.length > 0 && !isCurrentActive
                        onClicked: {
                            if (TimetableStore.switch(currentName)) {
                                setTip("已把「" + currentName + "」设为当前课表", false)
                                refreshList(currentName)
                            } else {
                                setTip("设置失败", true)
                            }
                        }

                        property bool isCurrentActive: {
                            var hit = root.tables.find(t => t.name === currentName)
                            return hit ? hit.active : false
                        }
                    }

                    Button { text: "新建"; onClicked: namePanel.openFor("", "new") }

                    Button {
                        text: "复制"
                        enabled: currentName.length > 0
                        onClicked: namePanel.openFor(currentName, "copy")
                    }

                    Button {
                        text: "重命名"
                        enabled: currentName.length > 0
                        onClicked: namePanel.openFor(currentName, "rename")
                    }

                    Button {
                        text: "删除"
                        enabled: currentName.length > 0
                        onClicked: {
                            var result = TimetableStore.delete(currentName)
                            setTip(result.ok ? "已删除「" + currentName + "」"
                                             : (result.error || "删除失败"),
                                   result.ok)
                            refreshList()
                        }
                    }
                }

                Text {
                    color: Theme.currentTheme.colors.textSecondaryColor
                    typography: Typography.Caption
                    text: {
                        var hit = root.tables.find(t => t.name === currentName)
                        if (!hit) return "还没有可编辑的课表"
                        return hit.periods + " 节 · " + hit.courses + " 门课"
                             + (hit.active ? " · 当前使用" : "")
                    }
                }
            }
        }

        // ================= 编辑当前课表 =================
        Text { typography: Typography.BodyStrong; text: "编辑「" + currentName + "」" }

        Text { typography: Typography.Body; text: "节次" }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(64, root.editPeriods.length * 48 + 84)
            padding: 8

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                Repeater {
                    model: root.editPeriods.length

                    delegate: RowLayout {
                        required property int index
                        Layout.fillWidth: true
                        Layout.preferredHeight: 44
                        spacing: 6

                        Text {
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: (index + 1) + "."
                        }

                        TextField {
                            Layout.preferredWidth: 120
                            text: root.editPeriods[index].name
                            placeholderText: "第" + (index + 1) + "节"
                            onTextEdited: root.editPeriods[index].name = text
                        }
                        TextField {
                            Layout.preferredWidth: 90
                            text: root.editPeriods[index].start
                            placeholderText: "08:00"
                            onTextEdited: root.editPeriods[index].start = text
                        }
                        TextField {
                            Layout.preferredWidth: 90
                            text: root.editPeriods[index].end
                            placeholderText: "08:45"
                            onTextEdited: root.editPeriods[index].end = text
                        }
                        Button {
                            text: "删这节"
                            onClicked: {
                                var list = root.editPeriods.slice()
                                list.splice(index, 1)
                                root.editPeriods = list
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Button {
                        text: "加一节"
                        onClicked: {
                            var list = root.editPeriods.slice()
                            list.push({ name: "第" + (list.length + 1) + "节",
                                        start: "", end: "" })
                            root.editPeriods = list
                        }
                    }

                    Button {
                        text: "保存节次与课程"
                        highlighted: true
                        enabled: currentName.length > 0
                        onClicked: {
                            var result = TimetableStore.update(
                                currentName, root.editPeriods, root.editTimetable)
                            setTip(result.ok ? "已保存「" + currentName + "」"
                                             : (result.error || "保存失败"), result.ok)
                            if (result.ok) refreshList(currentName)
                        }
                    }

                    Text {
                        visible: root.editPeriods.length === 0
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: "这张课表还没有节次，点「加一节」开始"
                    }
                }
            }
        }

        Text { typography: Typography.Body; text: "周一至周五课程（一列一天，按节次顺序从上往下）" }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(root.editPeriods.length * 72 + 68, 420)
            padding: 8

            Flickable {
                anchors.fill: parent
                contentWidth: 5 * (root.cellWidth + 6) + 36
                contentHeight: root.editPeriods.length * 72 + 44
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    x: 12; y: 4
                    spacing: 4

                    RowLayout {
                        spacing: 6
                        Repeater {
                            model: 5
                            delegate: Text {
                                required property int index
                                Layout.preferredWidth: root.cellWidth
                                horizontalAlignment: Text.AlignHCenter
                                color: Theme.currentTheme.colors.textSecondaryColor
                                typography: Typography.Caption
                                text: root.dayNames[index]
                            }
                        }
                    }

                    Repeater {
                        model: root.editPeriods.length

                        delegate: RowLayout {
                            id: rowDel
                            required property int index
                            readonly property int rowIdx: index
                            spacing: 6

                            Repeater {
                                model: 5

                                delegate: TextField {
                                    required property int index
                                    readonly property int day: index
                                    Layout.preferredWidth: root.cellWidth
                                    Layout.preferredHeight: 64
                                    selectByMouse: true
                                    text: {
                                        var list = root.editTimetable[String(day)] || []
                                        return list[rowDel.rowIdx] || ""
                                    }

                                    onTextEdited: {
                                        var key = String(day)
                                        var list = (root.editTimetable[key] || []).slice()
                                        while (list.length <= rowDel.rowIdx) list.push("")
                                        list[rowDel.rowIdx] = text
                                        var tt = Object.assign({}, root.editTimetable)
                                        tt[key] = list
                                        root.editTimetable = tt
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ================= 周末课表 =================
        //  周末走的是ScheduleManager.data["weekend"]，跟上面任何一张日常课表无关，
        //  所以单独成块、单独保存。上午节次沿用当前课表（按分界时间切分），
        //  下午节次在这里单独加 —— 周末通常只上半天。
        Text { typography: Typography.BodyStrong; text: "周末课表" }

        Text {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            typography: Typography.Caption
            color: Theme.currentTheme.colors.textSecondaryColor
            text: root.weekendAvailable
                  ? "周六周日共用一份课程。上午沿用当前课表的节次（按下面的分界时间切成上午/下午），下午用下面单独设的节次。当前周末共 " + root.weekendPeriodCount + " 节。"
                  : "课表服务不可用，周末课表无法读取或保存。"
        }

        Frame {
            Layout.fillWidth: true
            padding: 16
            visible: root.weekendAvailable

            ColumnLayout {
                anchors.fill: parent
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "上下午分界"
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }

                    ComboBox {
                        id: weekendSplitBox
                        Layout.preferredWidth: 110
                        // 常见分界点；实际值以保存的为准，不在列表里也能显示
                        model: ["11:00", "11:30", "12:00", "12:30", "13:00", "14:00"]
                        editable: true
                        currentValue: root.weekendSplit
                        onAccepted: root.weekendSplit = currentValue
                        onActivated: root.weekendSplit = currentValue
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: "分界之前算上午，之后算下午"
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                }

                // ---- 下午专属节次 ----
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: "下午节次"
                        Layout.preferredWidth: 72
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }

                    Text {
                        Layout.fillWidth: true
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: root.weekendAfternoon.length === 0
                              ? "没设额外的下午节次 —— 周末只上午上课。"
                              : "共 " + root.weekendAfternoon.length + " 节"
                    }

                    Button {
                        text: "加一节"
                        onClicked: root.addWeekendPeriod()
                    }
                }

                Repeater {
                    model: root.weekendAfternoon

                    delegate: RowLayout {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        spacing: 6

                        Text {
                            Layout.preferredWidth: 24
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: (index + 1) + "."
                        }

                        TextField {
                            Layout.preferredWidth: 120
                            text: modelData.name
                            placeholderText: "下午" + (index + 1)
                            onTextEdited: {
                                var list = root.weekendAfternoon.slice()
                                var item = Object.assign({}, list[index])
                                item.name = text
                                list[index] = item
                                root.weekendAfternoon = list
                            }
                        }

                        TextField {
                            Layout.preferredWidth: 90
                            text: modelData.start
                            placeholderText: "14:00"
                            onTextEdited: {
                                var list = root.weekendAfternoon.slice()
                                var item = Object.assign({}, list[index])
                                item.start = text
                                list[index] = item
                                root.weekendAfternoon = list
                            }
                        }

                        TextField {
                            Layout.preferredWidth: 90
                            text: modelData.end
                            placeholderText: "14:45"
                            onTextEdited: {
                                var list = root.weekendAfternoon.slice()
                                var item = Object.assign({}, list[index])
                                item.end = text
                                list[index] = item
                                root.weekendAfternoon = list
                            }
                        }

                        Item { Layout.fillWidth: true }

                        Button {
                            text: "删这节"
                            onClicked: root.removeWeekendPeriod(index)
                        }
                    }
                }

                // ---- 周末课程 ----
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Layout.topMargin: 6

                    Text {
                        text: "周末课程"
                        Layout.preferredWidth: 72
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }

                    Text {
                        Layout.fillWidth: true
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: root.weekendCourses.length === 0
                              ? "还没填周末课程 —— 不填的话周末就是无课。"
                              : "共 " + root.weekendCourses.length + " 节，从上往下对应上面的节次"
                    }

                    Button {
                        text: "加一节"
                        onClicked: root.addWeekendCourse()
                    }
                }

                Repeater {
                    model: root.weekendCourses

                    delegate: RowLayout {
                        required property string modelData
                        required property int index
                        Layout.fillWidth: true
                        spacing: 6

                        Text {
                            Layout.preferredWidth: 24
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: (index + 1) + "."
                        }

                        TextField {
                            Layout.fillWidth: true
                            text: modelData
                            placeholderText: "课程名"
                            onTextEdited: {
                                var list = root.weekendCourses.slice()
                                list[index] = text
                                root.weekendCourses = list
                            }
                        }

                        Button {
                            text: "删这节"
                            onClicked: root.removeWeekendCourse(index)
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 6

                    Item { Layout.fillWidth: true }

                    Button {
                        text: "保存周末课表"
                        highlighted: true
                        enabled: root.weekendAvailable
                        onClicked: root.saveWeekend()
                    }
                }
            }
        }

        // ================= 导入 / 导出 =================
        Text { typography: Typography.BodyStrong; text: "导入 / 导出" }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 170
            padding: 16

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Button {
                        text: "导出 JSON"
                        enabled: currentName.length > 0
                        onClicked: exportFolder.openFor("json")
                    }
                    Button {
                        text: "导出 CSV"
                        enabled: currentName.length > 0
                        onClicked: exportFolder.openFor("csv")
                    }
                    Button { text: "从文件导入…"; onClicked: importDialog.open() }
                    Button {
                        text: "预览粘贴内容"
                        enabled: pasteArea.text.length > 0
                        onClicked: importPreview.showPreview(
                            TimetableStore.previewImport(pasteArea.text, "粘贴的文本"))
                    }
                }

                TextArea {
                    id: pasteArea
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    placeholderText: "把课表 JSON / CSV 文本粘到这里（也可以直接用「从文件导入」）"
                    wrapMode: TextArea.Wrap
                }
            }
        }

        // 导入预览
        Frame {
            id: importPreview
            Layout.fillWidth: true
            visible: false
            padding: 16
            Layout.preferredHeight: previewColumn.implicitHeight + 32

            property bool canReplaceFull: false

            function showPreview(result) {
                if (!result || result.error) {
                    setTip("解析失败：" + (result && result.error ? result.error
                                                    : "内容不像课表"), true)
                    visible = false
                    return
                }
                previewModel.clear()
                var rows = result.timetables || []
                for (var i = 0; i < rows.length; i++) {
                    previewModel.append({
                        tname: rows[i].name,
                        periods: rows[i].periods,
                        courses: rows[i].courses,
                        exists: rows[i].exists
                    })
                }
                canReplaceFull = result.can_replace_full === true
                visible = true
            }

            ColumnLayout {
                id: previewColumn
                anchors.fill: parent
                spacing: 6

                Text { typography: Typography.BodyStrong; text: "导入预览" }

                Repeater {
                    model: ListModel { id: previewModel }

                    delegate: RowLayout {
                        required property string tname
                        required property int periods
                        required property int courses
                        required property bool exists

                        Text {
                            text: tname + "：" + periods + " 节 / " + courses + " 门课"
                                  + (exists ? "（已存在同名）" : "")
                        }
                    }
                }

                RowLayout {
                    spacing: 8

                    Button {
                        text: "合并导入（同名自动改名）"
                        highlighted: true
                        onClicked: {
                            root.applyImport(TimetableStore.importText(
                                pasteArea.text, "merge", "粘贴的文本"))
                            importPreview.visible = false
                        }
                    }

                    Button {
                        text: "替换导入"
                        visible: importPreview.canReplaceFull
                        onClicked: {
                            root.applyImport(TimetableStore.importText(
                                pasteArea.text, "replace", "粘贴的文本"))
                            importPreview.visible = false
                        }
                    }
                }
            }
        }

        // ================= 临时调课 =================
        Text { typography: Typography.BodyStrong; text: "临时调课" }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 132
            padding: 16

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    color: Theme.currentTheme.colors.textSecondaryColor
                    typography: Typography.Caption
                    text: "指定某一天按别的安排上课（比如考试周）。课程用逗号分隔，按当天节次顺序；"
                          + "当前："
                          + (TimetableStore.tempAdjust().date.length
                             ? TimetableStore.tempAdjust().date + " → "
                               + TimetableStore.tempAdjust().courses.join("、")
                             : "无")
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    TextField {
                        id: tempDate
                        Layout.preferredWidth: 150
                        placeholderText: "2026-10-15"
                    }
                    TextField {
                        id: tempCourses
                        Layout.fillWidth: true
                        placeholderText: "语文, 数学, 英语, …（按节次顺序）"
                    }
                    Button {
                        text: "设定"
                        onClicked: {
                            if (tempDate.text.trim().length === 0) {
                                setTip("日期要填（形如 2026-10-15）", true)
                                return
                            }
                            var result = TimetableStore.setTempAdjust(
                                tempDate.text.trim(), tempCourses.text.split(/[，,]/))
                            setTip(result.ok ? "临时调课已生效（" + tempDate.text.trim() + "）"
                                             : (result.error || "失败"), result.ok)
                        }
                    }
                    Button {
                        text: "清除"
                        onClicked: {
                            var result = TimetableStore.clearTempAdjust()
                            setTip(result.ok ? "已清除临时调课" : "清除失败", result.ok)
                        }
                    }
                }
            }
        }
    }

    // 新建 / 复制 / 重命名共用的小面板
    Frame {
        id: namePanel
        visible: false
        Layout.fillWidth: true
        Layout.preferredHeight: 108
        padding: 16

        property string mode: "new"
        property string source: ""
        property string label: ""

        function openFor(source, mode) {
            namePanel.mode = mode
            namePanel.source = source
            nameInput.text = mode === "copy" ? source + " 副本"
                          : mode === "rename" ? source : ""
            label = mode === "new" ? "新建空课表"
                  : mode === "copy" ? "复制「" + source + "」（含节次与课程）"
                  : "重命名「" + source + "」"
            visible = true
            nameInput.forceActiveFocus()
        }

        function confirm() {
            var name = nameInput.text.trim()
            if (name.length === 0) { setTip("名字不能为空", true); return }
            var result
            if (mode === "new") result = TimetableStore.create(name, "")
            else if (mode === "copy") result = TimetableStore.create(name, source)
            else result = TimetableStore.rename(source, name)
            if (result.ok) {
                visible = false
                setTip("完成：" + name, false)
                refreshList(result.name || name)
            } else {
                setTip(result.error || "失败", true)
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 8

            Text { text: namePanel.label; typography: Typography.Body }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                TextField {
                    id: nameInput
                    Layout.fillWidth: true
                    placeholderText: "课表名称"
                    onAccepted: namePanel.confirm()
                }
                Button { text: "确定"; highlighted: true; onClicked: namePanel.confirm() }
                Button { text: "取消"; onClicked: namePanel.visible = false }
            }
        }
    }

    FolderDialog {
        id: exportFolder
        property string exportFmt: "json"
        function openFor(fmt) { exportFmt = fmt; open() }
        onAccepted: {
            var result = TimetableStore.export(
                currentName, exportFolder.exportFmt, selectedFolder)
            setTip(result.ok ? "已导出：" + result.path
                             : (result.error || "导出失败"), result.ok)
        }
    }

    FileDialog {
        id: importDialog
        nameFilters: ["课表文件 (*.json *.csv)", "全部文件 (*)"]
        onAccepted: {
            importPreview.showPreview(TimetableStore.previewFile(selectedFile))
        }
    }

    function applyImport(result) {
        if (!result || !result.ok) {
            setTip("导入失败：" + (result && result.error ? result.error : ""), true)
            return
        }
        var parts = []
        if (result.added && result.added.length) parts.push("新增 " + result.added.length + " 张")
        if (result.replaced && result.replaced.length)
            parts.push("替换 " + result.replaced.length + " 张")
        if (result.removed && result.removed.length)
            parts.push("移除 " + result.removed.length + " 张")
        setTip("导入完成：" + parts.join("，") + "，当前课表：" + result.active, false)
        refreshList(result.active)
    }
}
