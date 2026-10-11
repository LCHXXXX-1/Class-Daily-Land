import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 状态测试（完整版）：
//   · 参数试算 —— 时间偏移 / 提前提醒 / 倒计时窗口代入 schedule.get_status()，
//     计算在 Python 侧（与主程序同一份逻辑），这里只画结果；
//   · 灵动岛样式预览 —— 胶囊 + 蓝色进度条 + 环形进度，配色取自源项目
//     test_dialog.IslandPreview（#1c1c1e 胶囊 / #0a84ff 进度 / #30d158 在上）；
//   · 情景演示 —— 嵌入主程序时驱动**真实灵动岛**跑一轮（提前 → 倒计时 →
//     上课 → 下课 → 恢复），同时本地同步演出；独立模式只演本地预览。
SubPage {

    // 左侧导航只列顶层页（见 Settings.qml 的说明），子页靠这个面包屑定位 + 返回
    contentHeader: PageHeader {
        rootTitle: "设置"
        parentTitle: "课表与提醒"
        currentTitle: "状态测试"
        description: "试算一节课的状态变化"
        onRootClicked: settingsWindow.gotoTitle("首页")
        onParentClicked: settingsWindow.gotoTitle("课表与提醒")
    }
    id: root

    property int countdown: Number(Config.get("island_countdown_sec", 60))
    property int advance: Number(Config.get("schedule_advance_minutes", 2))
    property int offset: Number(Config.get("schedule_time_offset_seconds", 0))

    property bool demoRunning: false
    property string timeText: defaultTimeText()

    // 预览状态（compute 的结果）
    property string islandState: "none"
    property string islandText: ""
    property real islandRatio: 0.0
    property real islandWidth: 0.6

    function defaultTimeText() {
        var d = new Date()
        function p(n) { return (n < 10 ? "0" : "") + n }
        return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate())
             + " " + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds())
    }

    function recompute() {
        if (demoRunning) return
        var result = StatusTester.compute(timeText, offset, advance, countdown)
        islandState = result.state || "none"
        islandText = result.text || ""
        islandRatio = result.ratio || 0.0
        islandWidth = result.width || 0.6
        detailText = (result.detail || []).join("\n")
    }

    property string detailText: ""

    Component.onCompleted: recompute()

    // ---------- 情景演示（本地演出节奏与 test_dialog._sim_tick 一致） ----------
    Timer {
        id: simTimer
        interval: 16
        running: false
        repeat: true
        onTriggered: root.simTick()
    }

    property real simStart: 0
    property real phaseA: 0
    property real phaseC: 0
    property real phaseHold: 0
    readonly property real phaseAlert: 1.0

    function startDemo() {
        if (demoRunning) return
        var speed = Number(speedBox.currentValue) || 10
        var endHoldSec = 10
        phaseA = (advance * 60) / speed
        phaseC = countdown / speed
        phaseHold = endHoldSec / speed
        simStart = Date.now() / 1000.0
        demoRunning = true
        demoBtn.enabled = false

        // 真实灵动岛（嵌入模式才有效果；返回 False 就是没驱动上）
        var drove = StatusTester.runScenario(advance * 60, countdown, endHoldSec, speed)
        demoNote.text = drove
                        ? "已同步驱动真实灵动岛（演出结束后自动恢复）"
                        : "未驱动真实灵动岛（独立演示模式没有岛），以下为本地预览演出"
        simTimer.start()
        simTick()
    }

    function simTick() {
        var elapsed = Date.now() / 1000.0 - simStart
        var a = phaseA, c = phaseC, hold = phaseHold, al = phaseAlert
        if (elapsed < a) {
            var remain = a - elapsed
            islandState = "upcoming"
            islandText = "距离上课 测试 · " + Math.round(remain) + "s"
            islandRatio = Math.max(0, Math.min(1, remain / Math.max(1.0, a)))
            islandWidth = 0.6
        } else if (elapsed < a + c) {
            var remain2 = a + c - elapsed
            islandState = "countdown"
            islandText = "下节 测试 · " + Math.round(remain2) + "s"
            islandRatio = Math.max(0, Math.min(1, remain2 / Math.max(1.0, c)))
            islandWidth = 1.0
        } else if (elapsed < a + c + al + hold) {
            islandState = "alert"
            islandText = "上课了！"
            islandRatio = 0.0
            islandWidth = 0.9
        } else if (elapsed < a + c + al + hold + al) {
            islandState = "alert"
            islandText = "下课了！"
            islandRatio = 0.0
            islandWidth = 0.9
        } else {
            simTimer.stop()
            demoRunning = false
            demoBtn.enabled = true
            recompute()
        }
    }

    function fmtSeconds(total) {
        var sign = total < 0 ? "-" : ""
        var abs = Math.abs(total)
        var m = Math.floor(abs / 60)
        var s = abs % 60
        return sign + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        InfoBar {
            Layout.fillWidth: true
            severity: StatusTester.isAvailable() ? Severity.Info : Severity.Warning
            title: StatusTester.isAvailable() ? "代入当前课表实时试算" : "课表服务不可用"
            text: StatusTester.isAvailable()
                  ? "计算在 Python 侧完成（与主程序灵动岛同一份 get_status 逻辑）。"
                    + "嵌入主程序时点「开始演示」会驱动真实灵动岛跑一轮。"
                  : "独立演示模式下没找到 ClassDailyLand-Py，无法代入真实课表。"
        }

        // ================= 参数 =================
        Text { typography: Typography.BodyStrong; text: "测试参数" }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 168
            padding: 16

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text { text: "测试时刻" }
                    TextField {
                        id: timeInput
                        Layout.preferredWidth: 200
                        text: root.timeText
                        placeholderText: "yyyy-MM-dd HH:mm:ss"
                        onEditingFinished: {
                            root.timeText = text
                            root.recompute()
                        }
                    }
                    Button {
                        text: "现在"
                        onClicked: {
                            root.timeText = root.defaultTimeText()
                            timeInput.text = root.timeText
                            root.recompute()
                        }
                    }
                }

                RowLayout {
                    spacing: 8
                    Text { text: "时间偏移" }
                    SpinBox {
                        id: offsetBox
                        from: -1800; to: 1800
                        value: root.offset
                        editable: true
                        onValueModified: { root.offset = value; root.recompute() }
                    }
                    Text { text: "秒" }
                    Text { text: "提前提醒" }
                    SpinBox {
                        id: advanceBox
                        from: 0; to: 60
                        value: root.advance
                        editable: true
                        onValueModified: { root.advance = value; root.recompute() }
                    }
                    Text { text: "分" }
                }

                RowLayout {
                    spacing: 8
                    Text { text: "倒计时窗口" }
                    SpinBox {
                        id: countdownBox
                        from: 5; to: 600
                        value: root.countdown
                        editable: true
                        onValueModified: { root.countdown = value; root.recompute() }
                    }
                    Text { text: "秒" }
                    Text { text: "演示倍速" }
                    ComboBox {
                        id: speedBox
                        Layout.preferredWidth: 110
                        textRole: "text"
                        model: [
                            { text: "1×", value: 1 },
                            { text: "5×", value: 5 },
                            { text: "10×", value: 10 },
                            { text: "20×", value: 20 },
                            { text: "30×", value: 30 }
                        ]
                        currentIndex: 2
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Button {
                        id: demoBtn
                        text: demoRunning ? "演示中…" : "▶ 开始演示"
                        highlighted: true
                        onClicked: root.startDemo()
                    }

                    Button {
                        text: "保存到设置"
                        enabled: StatusTester.isAvailable()
                        onClicked: {
                            var ok = StatusTester.saveParams(
                                root.offset, root.advance, root.countdown)
                            setTipText.text = ok ? "已保存（偏移挂课表服务，倒计时进设置）"
                                                 : "保存失败"
                        }
                    }

                    Text { id: setTipText; color: Theme.currentTheme.colors.textSecondaryColor }
                }
            }
        }

        // ================= 灵动岛预览 =================
        Text { typography: Typography.BodyStrong; text: "灵动岛预览" }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 170
            padding: 16

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                // 胶囊本体：配色取自 test_dialog.IslandPreview
                Rectangle {
                    id: capsule
                    Layout.alignment: Qt.AlignHCenter
                    width: Math.max(40, 420 * islandWidth)
                    height: 46
                    radius: height / 2
                    color: "#1c1c1e"

                    // 倒计时阶段的蓝色进度（裁在胶囊里）
                    Rectangle {
                        visible: islandState === "countdown" && islandRatio > 0
                        x: 1; y: 1
                        width: Math.max(0, (parent.width - 2) * islandRatio)
                        height: parent.height - 2
                        radius: height / 2
                        color: "#0a84ff"
                    }

                    // 环形进度（ongoing 满圈 / upcoming 无圈 / countdown 按 ratio）
                    Item {
                        x: 6; y: (parent.height - 26) / 2
                        width: 26; height: 26
                        Canvas {
                            anchors.fill: parent
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.clearRect(0, 0, width, height)
                                ctx.lineWidth = 2
                                ctx.strokeStyle = "#3a3a3c"
                                ctx.beginPath()
                                ctx.arc(width / 2, height / 2, (width - 4) / 2, 0, Math.PI * 2)
                                ctx.stroke()
                                var ratio = islandState === "ongoing" ? 1.0 : islandRatio
                                if (ratio > 0) {
                                    var color = islandState === "ongoing" ? "#30d158"
                                              : islandState === "countdown" ? "#4da3ff"
                                              : "#4da3ff"
                                    ctx.strokeStyle = color
                                    ctx.beginPath()
                                    ctx.arc(width / 2, height / 2, (width - 4) / 2,
                                            Math.PI / 2, Math.PI / 2 - Math.PI * 2 * ratio, false)
                                    ctx.stroke()
                                }
                                ctx.fillStyle = islandState === "ongoing" ? "#30d158"
                                              : islandState === "countdown" ? "#4da3ff"
                                              : islandState === "upcoming" ? "#4da3ff"
                                              : "#8a8a8e"
                                ctx.beginPath()
                                ctx.arc(width / 2, height / 2, 3, 0, Math.PI * 2)
                                ctx.fill()
                            }
                        }
                    }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 40
                        anchors.right: parent.right
                        anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        horizontalAlignment: Text.AlignLeft
                        font.pixelSize: 14
                        font.bold: true
                        // 提醒文案：上课了=绿、下课了=白（与 IslandPreview 一致），其余白字
                        color: islandState === "alert" && islandText.indexOf("下课") !== 0
                               ? "#30d158" : "#ffffff"
                        text: islandText
                        elide: Text.ElideRight
                    }
                }

                Text {
                    id: demoNote
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    color: Theme.currentTheme.colors.textSecondaryColor
                    typography: Typography.Caption
                    text: "配色与节奏照主程序的 IslandPreview 搬的；嵌入模式下「开始演示」会同时驱动真实灵动岛。"
                }
            }
        }

        // ================= 明细 =================
        Text { typography: Typography.BodyStrong; text: "试算明细" }

        Frame {
            Layout.fillWidth: true
            padding: 16
            Layout.preferredHeight: detailLines.implicitHeight + 32

            ColumnLayout {
                id: detailLines
                anchors.fill: parent
                spacing: 2

                Repeater {
                    model: root.detailText.length ? root.detailText.split("\n") : []

                    delegate: Text {
                        required property string modelData
                        Layout.fillWidth: true
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: modelData
                    }
                }
            }
        }
    }
}
