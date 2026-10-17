import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 周末作息 —— 对齐主窗口右键「周末作息」（menu.WeekendScheduleDialog）。
//
// 原生的表格就是一张 4 列清单：
//     节次 | 开始 | 结束 | 课程
// 上半段是「日常课表里早于分界时间」的节次 —— 只读、灰底，跟着工作日自动变；
// 下半段是周末专属的下午节次，可以增、可以删、可以改时间；
// 最右一列课程，周六周日共用一份，行数 = 上午节数 + 下午节数。
//
// 后端读的是 ScheduleManager.data["weekend"]（morning_split /
// afternoon_periods / courses），不是 timetable 的 5、6 两列 ——
// 所以这一页保存完必须让灵动岛重算，否则「填了周末课，岛还写今日无课」。
SubPage {

    contentHeader: PageHeader {
        rootTitle: "设置"
        parentTitle: "课表与提醒"
        currentTitle: "周末作息"
        description: "上午跟着工作日、下午单独设，周六日共用"
        onRootClicked: settingsWindow.gotoTitle("首页")
        onParentClicked: settingsWindow.gotoTitle("课表与提醒")
    }

    id: root

    property bool available: false
    property string split: "12:00"
    property var morning: []        // [{name,start,end}] 只读
    property var afternoon: []      // [{name,start,end}] 可编辑
    property var courses: []        // 与「上午 + 下午」行数对齐
    property string tip: ""
    property bool tipIsError: true

    /// 行数 = 上午 + 下午
    readonly property int rowCount: morning.length + afternoon.length

    function setTip(text, isError) {
        tip = text
        tipIsError = isError !== false
    }

    /// 从后端把三块数据读回来，并把 courses 补齐到行数。
    /// 补齐是必要的：课表节次一改，上午行数就会变，
    /// 而 weekend.courses 是上一次保存的长度，短了会读越界。
    function load() {
        if (!TimetableStore.isAvailable()) {
            available = false
            setTip("课表服务不可用，周末作息无法读取或保存", true)
            return
        }
        var w = TimetableStore.weekend()
        available = w.available === true
        split = w.morningSplit || "12:00"
        morning = (w.morningPeriods || []).map(function (p) {
            return { name: p.name || "", start: p.start || "", end: p.end || "" }
        })
        afternoon = (w.afternoonPeriods || []).map(function (p) {
            return { name: p.name || "", start: p.start || "", end: p.end || "" }
        })
        var loaded = (w.courses || []).slice()
        var rows = morning.length + afternoon.length
        var full = []
        for (var i = 0; i < rows; i++) full.push(i < loaded.length ? loaded[i] : "")
        courses = full
        if (rows > loaded.length && loaded.length > 0) {
            setTip("课程比节次少 " + (rows - loaded.length) + " 项，已留空补齐", true)
        }
    }

    function setCourse(index, text) {
        var list = courses.slice()
        while (list.length <= index) list.push("")
        list[index] = text
        courses = list
    }

    function addAfternoon() {
        var list = afternoon.slice()
        var start = "14:00"
        if (list.length > 0) {
            var last = list[list.length - 1]
            if (last.end && last.end.length === 5) {
                // 接着上一节往后排 10 分钟，省得每次都手改
                var h = parseInt(last.end.substring(0, 2), 10)
                var m = parseInt(last.end.substring(3, 5), 10) + 10
                if (m >= 60) { h += 1; m -= 60 }
                if (h < 24) {
                    start = (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m
                }
            }
        }
        var startMin = parseInt(start.substring(3, 5), 10)
        var endHour = parseInt(start.substring(0, 2), 10)
        var endMin = startMin + 45
        if (endMin >= 60) { endHour += 1; endMin -= 60 }
        var end = (endHour < 10 ? "0" : "") + endHour + ":" + (endMin < 10 ? "0" : "") + endMin
        list.push({ name: "下午" + (list.length + 1), start: start, end: end })
        afternoon = list
        courses = courses.concat([""])
    }

    function removeAfternoon(index) {
        var list = afternoon.slice()
        list.splice(index, 1)
        afternoon = list
        // 课程是「按行」排的：删下午行就要删掉对应那一格（位置在上午之后）
        var coursesList = courses.slice()
        coursesList.splice(morning.length + index, 1)
        courses = coursesList
    }

    function setAfternoonField(index, key, text) {
        var list = afternoon.slice()
        var item = Object.assign({}, list[index])
        item[key] = text
        list[index] = item
        afternoon = list
    }

    function save() {
        var result = TimetableStore.saveWeekend(split, afternoon, courses)
        if (result.ok) {
            // 先重读（load 会把"课程比节次少"之类的提示冲掉），再报成功
            load()
            setTip("已保存，主窗口和灵动岛都按新的周末作息走", false)
        } else {
            setTip(result.error || "保存失败", true)
        }
    }

    Component.onCompleted: load()

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        InfoBar {
            Layout.fillWidth: true
            severity: root.available ? Severity.Info : Severity.Warning
            title: root.available
                   ? "周六周日共用一份课程"
                   : "课表服务不可用"
            text: root.available
                  ? "上午的节次直接从日常课表里取（早于分界时间的那些），改课表就跟着变；下午在这里单独加。共 " + root.rowCount + " 节。"
                  : "独立运行且找不到主程序时无法读写课表；从主程序打开设置才有。"
        }

        // ---- 上下午分界 ----
        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 76
            padding: 16

            RowLayout {
                anchors.fill: parent
                spacing: 10

                Text { text: "上午上到几点" }

                TextField {
                    id: splitField
                    Layout.preferredWidth: 110
                    text: root.split
                    placeholderText: "12:00"
                    onTextEdited: root.split = text
                }

                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: "比这个早的算上午，自动跟工作日一样（HH:MM）"
                }
            }
        }

        // ---- 表头 ----
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 10
            spacing: 8

            Text {
                Layout.preferredWidth: 72
                color: Theme.currentTheme.colors.textSecondaryColor
                text: "节次"
            }
            Text {
                Layout.preferredWidth: 90
                color: Theme.currentTheme.colors.textSecondaryColor
                text: "开始"
            }
            Text {
                Layout.preferredWidth: 90
                color: Theme.currentTheme.colors.textSecondaryColor
                text: "结束"
            }
            Text {
                Layout.fillWidth: true
                color: Theme.currentTheme.colors.textSecondaryColor
                text: "课程"
            }
            Item { Layout.preferredWidth: 76 }
        }

        // ---- 上午（只读）----
        Repeater {
            model: root.morning

            delegate: Frame {
                required property var modelData
                required property int index
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                padding: 0

                Rectangle {
                    anchors.fill: parent
                    color: Theme.currentTheme.colors.controlFillSecondaryColor
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 8

                    Text {
                        Layout.preferredWidth: 64
                        elide: Text.ElideRight
                        text: modelData.name || ("第" + (index + 1) + "节")
                    }
                    Text {
                        Layout.preferredWidth: 90
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: modelData.start
                    }
                    Text {
                        Layout.preferredWidth: 90
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: modelData.end
                    }
                    TextField {
                        Layout.fillWidth: true
                        text: root.courses[index] !== undefined ? root.courses[index] : ""
                        placeholderText: "课程名"
                        onTextEdited: root.setCourse(index, text)
                    }
                    Item { Layout.preferredWidth: 76 }
                }
            }
        }

        // ---- 下午（可编辑）----
        Repeater {
            model: root.afternoon

            delegate: Frame {
                id: afternoonRow
                required property var modelData
                required property int index
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                padding: 0

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 8
                    spacing: 8

                    TextField {
                        Layout.preferredWidth: 64
                        text: afternoonRow.modelData.name
                        placeholderText: "下午" + (afternoonRow.index + 1)
                        onTextEdited: root.setAfternoonField(
                                          afternoonRow.index, "name", text)
                    }
                    TextField {
                        Layout.preferredWidth: 90
                        text: afternoonRow.modelData.start
                        placeholderText: "14:00"
                        onTextEdited: root.setAfternoonField(
                                          afternoonRow.index, "start", text)
                    }
                    TextField {
                        Layout.preferredWidth: 90
                        text: afternoonRow.modelData.end
                        placeholderText: "14:45"
                        onTextEdited: root.setAfternoonField(
                                          afternoonRow.index, "end", text)
                    }
                    TextField {
                        Layout.fillWidth: true
                        text: root.courses[root.morning.length + afternoonRow.index] !== undefined
                              ? root.courses[root.morning.length + afternoonRow.index] : ""
                        placeholderText: "课程名"
                        onTextEdited: root.setCourse(
                                          root.morning.length + afternoonRow.index, text)
                    }
                    Button {
                        Layout.preferredWidth: 76
                        text: "删这节"
                        onClicked: root.removeAfternoon(afternoonRow.index)
                    }
                }
            }
        }

        Text {
            visible: root.available && root.morning.length === 0 && root.afternoon.length === 0
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            Layout.margins: 20
            horizontalAlignment: Text.AlignHCenter
            color: Theme.currentTheme.colors.textSecondaryColor
            text: "当前课表里还没有节次 —— 先去「课表管理」把作息填上"
        }

        // ---- 操作 ----
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 10
            spacing: 10

            Button {
                text: "添加下午课节"
                onClicked: root.addAfternoon()
            }

            Item { Layout.fillWidth: true }

            Text {
                Layout.maximumWidth: 420
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignRight
                visible: root.tip.length > 0
                color: root.tipIsError
                       ? Theme.currentTheme.colors.systemCautionColor
                       : Theme.currentTheme.colors.systemSuccessColor
                text: root.tip
            }

            Button {
                text: "保存"
                highlighted: true
                onClicked: root.save()
            }
        }
    }
}
