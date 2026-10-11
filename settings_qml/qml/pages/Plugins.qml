import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

FluentPage {
    title: "插件"

    property var plugins: PluginStore.list()

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "插件市场与依赖"
        }

        // 左侧导航只列顶层页（见 Settings.qml），子页从这一页的入口行进
        Clip {
            Layout.fillWidth: true
            Layout.minimumHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_cart_20_regular"
                title: "插件市场"
                onActivated: settingsWindow.openPage("pages/Market.qml")
            }
        }

        Clip {
            Layout.fillWidth: true
            Layout.minimumHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_cube_20_regular"
                title: "依赖包管理"
                onActivated: settingsWindow.openPage("pages/Packages.qml")
            }
        }

        Text {
            typography: Typography.BodyStrong
            text: "本地插件"
        }

        Clip {
            Layout.fillWidth: true
            Layout.minimumHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_folder_open_20_regular"
                title: "打开插件文件夹"
                onActivated: Folders.open("plugins")
            }
        }

        SwitchSetting {
            settingKey: "plugins_auto_check_update"
            // 这一项是 QML 演示版自有的键，主程序的 settings.json 里没有 ——
            // 嵌入模式下禁用并如实说明，不让用户改一个不会保存的值。
            enabled: Config.isManaged("plugins_auto_check_update")
            title: "自动检查插件更新"
            description: Config.isManaged("plugins_auto_check_update")
                         ? "启动后到插件索引里比对版本"
                         : "嵌入主程序模式下暂未提供这项设置"
            icon.name: "ic_fluent_arrow_sync_20_regular"
        }

        Text {
            typography: Typography.BodyStrong
            text: "已安装 " + plugins.length + " 个插件"
        }

        Repeater {
            model: plugins

            delegate: Frame {
                Layout.fillWidth: true
                Layout.preferredHeight: 76
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
                            icon: modelData.ok
                                  ? "ic_fluent_puzzle_piece_20_regular"
                                  : "ic_fluent_warning_20_regular"
                            size: 22
                            color: modelData.ok
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
                                text: modelData.name
                                elide: Text.ElideRight
                            }
                            InfoBadge {
                                visible: modelData.version.length > 0
                                text: "v" + modelData.version
                                severity: Severity.Info
                                solid: false
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            color: Theme.currentTheme.colors.textSecondaryColor
                            typography: Typography.Caption
                            text: modelData.ok
                                  ? (modelData.author ? modelData.author + " · " : "") + modelData.desc
                                  : modelData.desc
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        Text {
            visible: plugins.length === 0
            Layout.alignment: Qt.AlignHCenter
            Layout.margins: 24
            color: Theme.currentTheme.colors.textSecondaryColor
            text: "plugins/ 目录里还没有插件"
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "更新源"
        }

        ComboSetting {
            settingKey: "market_source"
            title: "插件索引来源"
            description: "插件市场从哪个源拉索引"
            icon.name: "ic_fluent_box_multiple_20_regular"
            options: [
                { text: "官方服务器", value: "official" },
                { text: "GitHub", value: "github" },
                { text: "Gitee", value: "gitee" }
            ]
        }

        ComboSetting {
            settingKey: "packages_source"
            title: "依赖包下载源"
            description: "插件声明的第三方依赖从哪个源下载"
            icon.name: "ic_fluent_arrow_download_20_regular"
            options: [
                { text: "Gitee", value: "gitee" },
                { text: "GitHub", value: "github" },
                { text: "自定义", value: "custom" }
            ]
        }

        TextSetting {
            settingKey: "packages_base_url"
            title: "自定义下载源地址"
            description: "下载源选「自定义」时生效"
            icon.name: "ic_fluent_link_20_regular"
            placeholder: "https://example.com/packages/"
        }
    }
}
