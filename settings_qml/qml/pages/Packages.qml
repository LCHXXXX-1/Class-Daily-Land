import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 依赖包管理（完整版）：插件声明的第三方依赖（plugins/packages/ 下的包）。
// 列表 = 远端目录（按当前下载源）+ 本地安装状态 + 「谁在用」；下载源在
// 「本地插件」页设置。安装走主程序 PackageStore（校验 / 原子换入同源）。
FluentPage {
    title: ""

    // 左侧导航只列顶层页（见 Settings.qml 的说明），子页靠这个面包屑定位 + 返回
    contentHeader: PageHeader {
        parentTitle: "插件"
        currentTitle: "Packages"
        description: "插件依赖的第三方包"
        onParentClicked: settingsWindow.gotoTitle("插件")
    }
    id: root

    property var entries: []
    property string source: ""
    property var baseUrls: []
    property bool busy: false

    Component.onCompleted: loadStatus()

    function loadStatus() {
        var st = PackageBridge.status()
        if (!st.available) {
            entries = []
            unavailableNote.visible = true
            unavailableNote.text = st.reason || "依赖包管理不可用"
            return
        }
        unavailableNote.visible = false
        entries = st.entries || []
        source = st.source || ""
        baseUrls = st.baseUrls || []
        busy = st.busy === true
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        InfoBar {
            Layout.fillWidth: true
            severity: PackageBridge.isAvailable() ? Severity.Info : Severity.Warning
            title: PackageBridge.isAvailable() ? "第三方依赖包" : "依赖包管理不可用"
            text: PackageBridge.isAvailable()
                  ? "插件清单里声明 requires 时会从这里取包。包落在 plugins/packages/，"
                    + "主程序启动时统一加进 sys.path。"
                  : "需要主程序环境（嵌入模式或 --py-root 引导）。"
        }

        Text {
            id: unavailableNote
            visible: false
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: Theme.currentTheme.colors.systemCautionColor
        }

        // ================= 工具行 =================
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

                    Button {
                        text: "刷新列表"
                        highlighted: true
                        enabled: PackageBridge.isAvailable() && !root.busy
                        onClicked: PackageBridge.refresh()
                    }

                    BusyIndicator {
                        visible: root.busy
                        width: 28; height: 28
                    }
                }

                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    color: Theme.currentTheme.colors.textSecondaryColor
                    typography: Typography.Caption
                    text: "下载源：" + source
                          + "（改源在「本地插件」页；自定义地址也认 settings 里的 packages_base_url）"
                }

                Text {
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    color: Theme.currentTheme.colors.textSecondaryColor
                    typography: Typography.Caption
                    text: root.entries.length
                          ? "共 " + root.entries.length + " 个包 · 已安装 "
                            + root.entries.filter(e => e.installed).length + " 个"
                          : "列表为空：点「刷新列表」从下载源拉取，或插件还没声明依赖"
                }
            }
        }

        // ================= 包列表 =================
        Repeater {
            model: root.entries

            delegate: Frame {
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 96
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
                                  ? "ic_fluent_checkmark_circle_20_regular"
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
                            }
                            InfoBadge {
                                visible: modelData.installedVersion.length > 0
                                text: "v" + modelData.installedVersion
                                severity: Severity.Info
                                solid: false
                            }
                            InfoBadge {
                                visible: modelData.updateAvailable
                                text: "可更新"
                                severity: Severity.Warning
                                solid: false
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            color: Theme.currentTheme.colors.textSecondaryColor
                            typography: Typography.Caption
                            text: modelData.problem.length > 0
                                  ? modelData.problem
                                  : (modelData.usedBy.length
                                     ? "被使用：" + modelData.usedBy.join("、")
                                     : "暂无插件声明使用这个包")
                            elide: Text.ElideRight
                        }
                    }

                    RowLayout {
                        spacing: 6

                        Button {
                            text: modelData.installed ? "重装" : "安装"
                            enabled: !root.busy
                            highlighted: !modelData.installed
                            onClicked: PackageBridge.install(modelData.name)
                        }

                        Button {
                            text: "卸载"
                            visible: modelData.installed
                            enabled: !root.busy
                            onClicked: PackageBridge.uninstall(modelData.name)
                        }
                    }
                }
            }
        }

        // ================= 日志 =================
        Text { typography: Typography.BodyStrong; text: "执行日志" }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 170
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
                    text: "安装 / 卸载 / 下载进度会写在这里"
                }
            }
        }
    }

    Connections {
        target: PackageBridge

        function onLogLine(text) {
            logModel.append({ line: String(text) })
            while (logModel.count > 60) logModel.remove(0)
        }

        function onBusyChanged(isBusy) {
            root.busy = isBusy
            if (!isBusy) loadStatus()
        }

        function onCatalogReady(items) {
            root.entries = items || []
        }

        function onTaskProgress(name, percent) {
            if (percent >= 0)
                logModel.append({ line: name + " " + percent + "%" })
        }

        function onTaskDone(name, ok, message) {
            logModel.append({ line: (ok ? "[成功] " : "[失败] ") + name + " " + message })
            loadStatus()
        }
    }
}
