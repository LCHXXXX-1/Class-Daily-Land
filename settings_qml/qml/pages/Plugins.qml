import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 插件 —— 顶层页，只放两个板块的入口（照 Win11「系统 → 屏幕/声音」的做法）。
//
// ★ 左侧导航不再有可展开的子项（见 Settings.qml 的说明），
//   所以「插件管理」「插件市场」都是这一页里的入口行，点进去是右侧子页。
PageShell {
    id: root
    title: "插件"

    property var plugins: PluginStore.list()

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "插件"
        }

        Clip {
            Layout.fillWidth: true
            Layout.preferredHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_puzzle_piece_20_regular"
                title: "插件管理"
                onActivated: settingsWindow.openPage("pages/PluginManage.qml")

                // ★ 必须写 content:。ClipItem 的 content 是 `property alias`，
                //   **不是 default 属性** —— 直接塞个子项进去会变成 Item 的普通
                //   children，坐标停在 (0,0)，于是文字压在卡片外面（就是那种
                //   「凸出来一小块」）。要进右侧槽位只能显式赋给 content。
                content: Text {
                    color: Theme.currentTheme.colors.textSecondaryColor
                    typography: Typography.Caption
                    text: root.plugins.length + " 个已装"
                }
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

                content: Text {
                    color: Theme.currentTheme.colors.textSecondaryColor
                    typography: Typography.Caption
                    text: "搜索 / 安装 / 更新"
                }
            }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.topMargin: 8
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "本地插件"
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
    }

    ColumnLayout {
        Layout.fillWidth: true
        Layout.topMargin: 8
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
