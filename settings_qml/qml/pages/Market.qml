import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 插件市场（完整版）：索引三源同步（官方 / GitHub / Gitee，缓存兜底）、
// 安装 / 卸载 / 启用禁用 / 批量更新、SHA-256 校验与镜像候选都在主程序
// 的 PluginMarket 里完成 —— 本页只发指令、听信号、画界面。
//
// 异步约定（与 web_settings 的 market.* 事件一致）：
//   MarketStore.sync() 之后等 syncFinished / catalogReady；
//   install / uninstall / updateAll 之后等 taskProgress / taskDone；
//   依赖包安装进度从 depProgress 来（stage/text/percent）。
SubPage {

    // 左侧导航只列顶层页（见 Settings.qml 的说明），子页靠这个面包屑定位 + 返回
    contentHeader: PageHeader {
        rootTitle: "设置"
        parentTitle: "插件"
        currentTitle: "插件市场"
        description: "从仓库索引安装 / 更新插件"
        onRootClicked: settingsWindow.gotoTitle("首页")
        onParentClicked: settingsWindow.gotoTitle("插件")
    }
    id: root

    property var entries: []
    property string lastSync: ""
    property string source: "official"
    property bool busy: false
    property string progressId: ""
    property int progressPercent: -1
    property string depText: ""
    property bool restartRequired: false

    Component.onCompleted: loadStatus()

    function loadStatus() {
        var st = MarketStore.status()
        if (!st.available) {
            entries = []
            unavailableNote.visible = true
            unavailableNote.text = st.reason || "插件市场不可用"
            return
        }
        unavailableNote.visible = false
        entries = st.entries || []
        lastSync = st.lastSync || ""
        source = st.source || "official"
        busy = st.busy === true
        sourceBox.currentIndex = sourceBox.indexOfValue(source)
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        InfoBar {
            Layout.fillWidth: true
            severity: MarketStore.isAvailable() ? Severity.Info : Severity.Warning
            title: MarketStore.isAvailable() ? "联网拉索引，失败退回本地缓存" : "插件市场不可用"
            text: MarketStore.isAvailable()
                  ? "安装包下载后会做 SHA-256 校验并原子换入；安装 / 卸载 / 更新完成后需要重启主程序生效。"
                  : "需要主程序环境（嵌入模式或 --py-root 引导）。"
        }

        Text {
            id: unavailableNote
            visible: false
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: Theme.currentTheme.colors.systemCautionColor
        }

        InfoBar {
            Layout.fillWidth: true
            visible: root.restartRequired
            severity: Severity.Success
            title: "操作完成，重启主程序后生效"
            text: "插件在启动时加载；本页的启用 / 禁用也会在下一次启动时应用。"
        }

        // ================= 工具行 =================
        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 84
            padding: 16

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    ComboBox {
                        id: sourceBox
                        Layout.preferredWidth: 160
                        textRole: "text"
                        model: [
                            { text: "官方服务器", value: "official" },
                            { text: "GitHub", value: "github" },
                            { text: "Gitee", value: "gitee" }
                        ]
                        enabled: !root.busy

                        function indexOfValue(v) {
                            for (var i = 0; i < model.length; i++)
                                if (model[i].value === v) return i
                            return 0
                        }

                        onActivated: {
                            var value = model[currentIndex].value
                            MarketStore.setSource(value)
                            root.source = value
                        }
                    }

                    Button {
                        text: "同步索引"
                        highlighted: true
                        enabled: MarketStore.isAvailable() && !root.busy
                        onClicked: {
                            root.progressId = ""
                            root.depText = ""
                            MarketStore.sync()
                        }
                    }

                    Button {
                        text: "刷新本地状态"
                        enabled: MarketStore.isAvailable() && !root.busy
                        onClicked: MarketStore.rescan()
                    }

                    Button {
                        text: "全部更新"
                        enabled: MarketStore.isAvailable() && !root.busy && hasUpdates
                        onClicked: MarketStore.updateAll()

                        property bool hasUpdates: {
                            for (var i = 0; i < root.entries.length; i++)
                                if (root.entries[i].updateAvailable) return true
                            return false
                        }
                    }

                    BusyIndicator {
                        visible: root.busy
                        width: 28; height: 28
                    }
                }

                Text {
                    color: Theme.currentTheme.colors.textSecondaryColor
                    typography: Typography.Caption
                    text: (root.entries.length ? "共 " + root.entries.length + " 个插件 · " : "")
                          + (root.lastSync.length ? "上次同步：" + root.lastSync
                                                  : "还没有同步过索引")
                }
            }
        }

        // ================= 任务进度 =================
        Frame {
            Layout.fillWidth: true
            visible: root.progressId.length > 0 || root.depText.length > 0
            Layout.preferredHeight: 76
            padding: 12

            ColumnLayout {
                anchors.fill: parent
                spacing: 4

                Text {
                    text: root.depText.length > 0
                          ? root.depText
                          : "正在处理「" + root.progressId + "」…"
                    typography: Typography.Caption
                    color: Theme.currentTheme.colors.textSecondaryColor
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                ProgressBar {
                    Layout.fillWidth: true
                    visible: root.progressPercent >= 0
                    from: 0; to: 100
                    value: Math.max(0, root.progressPercent)
                }
            }
        }

        // ================= 目录 =================
        Text {
            typography: Typography.BodyStrong
            text: "插件目录"
            visible: root.entries.length > 0
        }

        Repeater {
            model: root.entries

            delegate: Frame {
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 108
                padding: 0

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 14

                    Rectangle {
                        Layout.preferredWidth: 44
                        Layout.preferredHeight: 44
                        radius: 10
                        color: Theme.currentTheme.colors.backgroundColor
                        border.width: 1
                        border.color: Theme.currentTheme.colors.controlBorderColor

                        IconWidget {
                            anchors.centerIn: parent
                            icon: modelData.installed
                                  ? "ic_fluent_puzzle_piece_20_regular"
                                  : "ic_fluent_arrow_download_20_regular"
                            size: 22
                            color: modelData.updateAvailable
                                   ? Theme.currentTheme.colors.systemCautionColor
                                   : Theme.currentTheme.colors.primaryColor
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        RowLayout {
                            spacing: 8
                            Text {
                                typography: Typography.BodyStrong
                                text: modelData.name
                                elide: Text.ElideRight
                                Layout.maximumWidth: 260
                            }
                            InfoBadge {
                                visible: modelData.version.length > 0
                                text: "v" + modelData.version
                                severity: Severity.Info
                                solid: false
                            }
                            InfoBadge {
                                visible: modelData.updateAvailable
                                text: "可更新"
                                severity: Severity.Warning
                                solid: false
                            }
                            InfoBadge {
                                visible: modelData.disabled
                                text: "已禁用"
                                severity: Severity.Warning
                                solid: false
                            }
                            InfoBadge {
                                visible: modelData.loadError.length > 0
                                text: "加载失败"
                                severity: Severity.Error
                                solid: false
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            color: Theme.currentTheme.colors.textSecondaryColor
                            typography: Typography.Caption
                            text: modelData.loadError.length > 0
                                  ? modelData.loadError
                                  : (modelData.problem.length > 0
                                     ? modelData.problem
                                     : (modelData.author.length > 0
                                        ? modelData.author + " · " : "") + modelData.description)
                            elide: Text.ElideRight
                        }

                        Text {
                            visible: modelData.installed
                            color: Theme.currentTheme.colors.textSecondaryColor
                            typography: Typography.Caption
                            text: "已安装" + (modelData.installedVersion.length > 0
                                  ? " v" + modelData.installedVersion : "")
                        }
                    }

                    RowLayout {
                        spacing: 6

                        Button {
                            text: modelData.installed ? "更新" : "安装"
                            visible: !modelData.installed || modelData.updateAvailable
                            enabled: !root.busy
                            highlighted: true
                            onClicked: {
                                root.progressId = modelData.id
                                root.progressPercent = 0
                                MarketStore.install(modelData.id)
                            }
                        }

                        Button {
                            text: modelData.disabled ? "启用" : "禁用"
                            visible: modelData.installed
                            enabled: !root.busy
                            onClicked: MarketStore.setEnabled(
                                modelData.id, modelData.disabled)
                        }

                        Button {
                            text: "卸载"
                            visible: modelData.installed
                            enabled: !root.busy
                            onClicked: {
                                root.progressId = modelData.id
                                MarketStore.uninstall(modelData.id)
                            }
                        }
                    }
                }
            }
        }

        // ================= 日志 =================
        Text { typography: Typography.BodyStrong; text: "执行日志" }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 190
            padding: 8

            ColumnLayout {
                anchors.fill: parent
                spacing: 2

                Repeater {
                    model: ListModel { id: logModel }

                    delegate: Text {
                        required property string line
                        Layout.fillWidth: true
                        color: Theme.currentTheme.colors.textSecondaryColor
                        typography: Typography.Caption
                        text: line
                        elide: Text.ElideRight
                    }
                }

                Text {
                    visible: logModel.count === 0
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: "同步 / 安装 / 卸载的进度会写在这里"
                }
            }
        }
    }

    // 依赖包管理挂在「插件市场」下面：它是市场的后勤，不该单独占一个导航项
    // （见 Settings.qml「左侧只放顶层页」的说明）。
    ColumnLayout {
        Layout.fillWidth: true
        Layout.topMargin: 12
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "相关设置"
        }

        Clip {
            Layout.fillWidth: true
            Layout.preferredHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_cube_20_regular"
                title: "依赖包管理"
                onActivated: settingsWindow.openPage("pages/Packages.qml")
            }
        }
    }

    Connections {
        target: MarketStore

        function onLogLine(text) {
            logModel.append({ line: String(text) })
            while (logModel.count > 60) logModel.remove(0)
        }

        function onBusyChanged(isBusy) {
            root.busy = isBusy
            if (!isBusy) loadStatus()
        }

        function onSyncFinished(ok, message) {
            logModel.append({ line: (ok ? "[完成] " : "[失败] ") + message })
        }

        function onCatalogReady(items) {
            root.entries = items || []
        }

        function onTaskProgress(id, percent) {
            root.progressId = id
            root.progressPercent = percent
            if (percent < 0) root.progressPercent = -1
        }

        function onTaskDone(id, ok, message, restart) {
            root.progressId = ""
            root.progressPercent = -1
            root.depText = ""
            logModel.append({ line: (ok ? "[成功] " : "[失败] ") + id + " " + message })
            if (restart) root.restartRequired = true
            loadStatus()
        }

        function onDepProgress(ev) {
            root.progressId = ev.id || root.progressId
            root.depText = ev.text || ""
            if (ev.percent >= 0) root.progressPercent = ev.percent
        }
    }
}
