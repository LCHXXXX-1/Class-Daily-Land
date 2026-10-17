import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 插件管理 —— 列出已安装插件，**点某个插件就进入它自己注册的设置页**。
//
// 插件的设置页是插件用 api.add_settings_page(title, factory) 注册出来的，
// factory 返回的是原生 QWidget（PLUGIN_API.md 的契约）。
// 点一行 → PluginHost.prepare(目录名) 把原生页建好 → 推进 pages/PluginPage.qml
// 那个子页里显示（不再是弹窗，见 app/pluginhome.py 的模块说明）。
//
// ★ 这里只负责「目录 + 点击」，不执行任何插件代码：
//   有没有设置页由 PluginHost.hasPage() 回答，点击才真正调用 factory。
SubPage {
    id: root

    contentHeader: PageHeader {
        rootTitle: "设置"
        parentTitle: "插件"
        currentTitle: "插件管理"
        description: "点插件名字即载入它自己的设置项"
        onRootClicked: settingsWindow.gotoTitle("首页")
        onParentClicked: settingsWindow.gotoTitle("插件")
    }

    property var plugins: PluginStore.list()
    property string note: ""
    property bool noteIsError: false

    // 插件设置页加载失败时，原因写在这一行里（别让它变成「点了没反应」）
    Connections {
        target: PluginHost
        function onChanged() {
            if (PluginHost.error.length > 0) {
                root.noteIsError = true
                root.note = PluginHost.error
            }
        }
    }

    function openPlugin(item) {
        if (!PluginHost.isAvailable()) {
            root.noteIsError = true
            root.note = "插件管理器不可用（独立演示模式请从主程序打开设置）"
            return
        }
        var dir = String(item.id || "")
        if (!PluginHost.hasPage(dir)) {
            root.noteIsError = true
            root.note = "「" + item.name + "」没有注册设置页 —— "
                        + "插件里调用 api.add_settings_page(\"标题\", factory) 之后才会出现在这里"
            return
        }
        root.note = ""
        root.noteIsError = false
        // 先把原生控件建好（要先有 winId 才能交给 WindowContainer），
        // 再把设置页推到这个子页里 —— 不再弹独立窗口。
        if (!PluginHost.prepare(dir)) {
            root.noteIsError = true
            root.note = PluginHost.error
            return
        }
        settingsWindow.openPage("pages/PluginPage.qml")
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        InfoBar {
            Layout.fillWidth: true
            severity: Severity.Info
            title: "这里的每一项由插件自己提供"
            text: "点插件名字进入它自己的设置页（就在这个设置窗口里，不会再弹新窗口）。"
        }

        Text {
            Layout.fillWidth: true
            visible: root.note.length > 0
            wrapMode: Text.WordWrap
            color: root.noteIsError
                   ? Theme.currentTheme.colors.systemCautionColor
                   : Theme.currentTheme.colors.textSecondaryColor
            text: root.note
        }

        Text {
            Layout.topMargin: 8
            typography: Typography.BodyStrong
            text: "已安装插件（" + root.plugins.length + "）"
        }

        Repeater {
            model: root.plugins

            delegate: Clip {
                id: pluginRow
                required property var modelData

                Layout.fillWidth: true
                Layout.preferredHeight: 72
                padding: 0
                hoverable: true
                onClicked: root.openPlugin(modelData)

                // 有设置页才画箭头，没有就明说「无设置项」
                readonly property bool hasPage: PluginHost.hasPage(String(modelData.id || ""))

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 16
                    spacing: 14

                    Rectangle {
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                        radius: 8
                        color: Theme.currentTheme.colors.controlAltSecondaryColor

                        IconWidget {
                            anchors.centerIn: parent
                            icon: pluginRow.modelData.ok
                                  ? "ic_fluent_puzzle_piece_20_regular"
                                  : "ic_fluent_warning_20_regular"
                            size: 20
                            color: pluginRow.modelData.ok
                                   ? Theme.currentTheme.colors.primaryColor
                                   : Theme.currentTheme.colors.systemCriticalColor
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        RowLayout {
                            spacing: 8

                            Text {
                                typography: Typography.BodyStrong
                                text: pluginRow.modelData.name
                                elide: Text.ElideRight
                            }

                            InfoBadge {
                                visible: String(pluginRow.modelData.version || "").length > 0
                                text: "v" + pluginRow.modelData.version
                                severity: Severity.Info
                                solid: false
                            }

                            // 内置功能（原本是插件，现在编进主程序）—— 标一下，
                            // 免得用户以为可以像第三方插件那样卸载
                            InfoBadge {
                                visible: pluginRow.modelData.builtin === true
                                text: "内置"
                                severity: Severity.Success
                                solid: false
                            }

                            InfoBadge {
                                visible: pluginRow.hasPage
                                text: "可设置"
                                severity: Severity.Success
                                solid: false
                            }

                            InfoBadge {
                                visible: !pluginRow.modelData.ok
                                text: "加载失败"
                                severity: Severity.Critical
                                solid: false
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            color: Theme.currentTheme.colors.textSecondaryColor
                            typography: Typography.Caption
                            elide: Text.ElideRight
                            text: pluginRow.modelData.ok
                                  ? (pluginRow.modelData.author
                                     ? pluginRow.modelData.author + " · " : "")
                                    + pluginRow.modelData.desc
                                  : (pluginRow.modelData.failure || "未加载")
                        }
                    }

                    Text {
                        visible: !pluginRow.hasPage
                        color: Theme.currentTheme.colors.textTertialyColor
                        typography: Typography.Caption
                        text: "无设置项"
                    }

                    IconWidget {
                        Layout.preferredWidth: 18
                        Layout.preferredHeight: 18
                        visible: pluginRow.hasPage
                        icon: "ic_fluent_chevron_right_20_regular"
                        size: 18
                        opacity: 0.85
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.topMargin: 16
            Layout.alignment: Qt.AlignHCenter
            visible: root.plugins.length === 0
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            color: Theme.currentTheme.colors.textSecondaryColor
            text: "plugins/ 目录里还没有插件。\n去「插件市场」装一个，或把插件文件夹放进 plugins/ 后重启。"
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.topMargin: 12
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "其他"
        }

        Clip {
            Layout.fillWidth: true
            Layout.preferredHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_folder_open_20_regular"
                title: "打开插件文件夹"
                onActivated: Folders.open("plugins")
            }
        }

        Clip {
            Layout.fillWidth: true
            Layout.preferredHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_cart_20_regular"
                title: "插件市场"
                onActivated: settingsWindow.openPage("pages/Market.qml")
            }
        }
    }
}
