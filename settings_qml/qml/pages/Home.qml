import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

FluentPage {
    title: "首页"

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 8

        Text {
            typography: Typography.Title
            text: "Class Daily Land"
        }

        Text {
            Layout.fillWidth: true
            typography: Typography.Body
            color: Theme.currentTheme.colors.textSecondaryColor
            text: "管理班级日常、课表、作业与桌面灵动岛。选择一个设置类别开始。"
            wrapMode: Text.Wrap
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "设置"
        }

        Repeater {
            model: [
                { title: "通用", icon: "ic_fluent_settings_20_regular" },
                { title: "灵动岛", icon: "ic_fluent_apps_20_regular" },
                { title: "个性化", icon: "ic_fluent_paint_brush_sparkle_20_regular" },
                { title: "课表与提醒", icon: "ic_fluent_calendar_20_regular" },
                { title: "作业", icon: "ic_fluent_book_20_regular" },
                { title: "插件", icon: "ic_fluent_apps_add_in_20_regular" }
            ]

            delegate: Clip {
                Layout.fillWidth: true
                Layout.minimumHeight: 64

                ClipItem {
                    anchors.fill: parent
                    iconName: modelData.icon
                    title: modelData.title
                    onActivated: settingsWindow.gotoTitle(modelData.title)
                }
            }
        }
    }
}
