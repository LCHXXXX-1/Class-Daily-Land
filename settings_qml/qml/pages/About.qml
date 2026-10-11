import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

PageShell {
    title: "关于"

    readonly property string version: AppInfo.version()

    function rows() {
        return [
            { label: "版本", value: version },
            { label: "系统", value: AppInfo.system() },
            { label: "宿主", value: AppInfo.host() },
            { label: "界面栈", value: AppInfo.uiStack() },
            { label: "云母材质", value: AppInfo.micaAvailable() ? "可用" : "不可用（系统版本不够）" },
            { label: "配置目录", value: AppInfo.configPath() }
        ]
    }

    SettingExpander {
        Layout.fillWidth: true
        title: "Class Daily Land"
        description: "一个轻量级的班级日常管理小工具 · 设置中心 QML 试水版"
        icon.name: "ic_fluent_info_20_regular"
        expanded: true

        RowLayout {
            spacing: 8
            InfoBadge {
                text: "试水版"
                severity: Severity.Warning
                solid: false
            }
            Text {
                color: Theme.currentTheme.colors.textSecondaryColor
                text: "v" + version
            }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "运行环境"
        }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: rows().length * 50
            padding: 0

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Repeater {
                    model: rows()

                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 50
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        spacing: 16

                        Text {
                            Layout.preferredWidth: 96
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: modelData.label
                        }
                        Text {
                            Layout.fillWidth: true
                            text: modelData.value
                            elide: Text.ElideMiddle
                        }
                    }
                }
            }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "更新"
        }

        InfoBar {
            Layout.fillWidth: true
            visible: Config.get("block_update_on_source", true)
            severity: Severity.Warning
            title: "源码运行 · 自动更新已跳过"
            text: "检测到本地主入口源码时不再自动更新，更新前会先提醒备份。"
        }

        InfoBar {
            Layout.fillWidth: true
            visible: updateTip.text.length > 0
            severity: Severity.Info
            title: updateTip.text
            text: updateDetail.text
        }

        SettingCard {
            id: updateCard
            Layout.fillWidth: true
            title: "检查更新"
            description: Updater.state().available
                         ? "由独立的 Launcher 完成；检测到本地源码会先提醒备份"
                         : (Updater.state().reason || "更新模块不可用")
            icon.name: "ic_fluent_arrow_sync_20_regular"

            Button {
                id: checkBtn
                text: "检查更新"
                highlighted: true
                enabled: Updater.state().available && Updater.state().launcherFound

                onClicked: {
                    checkBtn.enabled = false
                    var result = Updater.checkNow()
                    checkBtn.enabled = true
                    updateTip.text = result.ok ? "已拉起更新器" : "更新没有执行"
                    updateDetail.text = result.ok
                        ? "请看更新器窗口；下载完成后它会接管重启。"
                        : (result.error || result.message || "")
                }
            }
        }

        Text { id: updateTip; visible: false }
        Text { id: updateDetail; visible: false }

        // 源码命中明细（dev_guard 扫出来的，帮用户知道备份哪些）
        SettingCard {
            Layout.fillWidth: true
            visible: {
                var st = Updater.state()
                return st.available && st.sourceHits && st.sourceHits.length > 0
            }
            title: "检测到本地源码文件"
            description: {
                var st = Updater.state()
                return st.sourceHits.join("、")
            }
            icon.name: "ic_fluent_shield_20_regular"
        }
    }
}
