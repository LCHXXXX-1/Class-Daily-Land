import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

PageShell {
    title: "外观"

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "颜色主题"
        }

        ComboSetting {
            settingKey: "theme_mode"
            title: "颜色模式"
            description: "跟随系统时会随 Windows 的浅色 / 深色实时切换"
            icon.name: "ic_fluent_color_20_regular"
            options: [
                { text: "跟随系统", value: "system" },
                { text: "浅色", value: "light" },
                { text: "深色", value: "dark" }
            ]
            onValueChanged: ThemeManager.toggle_theme(
                value === "dark" ? "Dark" : value === "light" ? "Light" : "Auto"
            )
        }

        SwitchSetting {
            settingKey: "settings_mica"
            title: "云母材质（Mica）"
            description: AppInfo.micaAvailable
                ? "Windows 11 的半透明云母背板，会跟着系统明暗变"
                : "云母材质需要 Windows 11 22H2 及以上，当前系统自动降级为亚克力"
            icon.name: "ic_fluent_paint_brush_20_regular"
        }

        SwitchSetting {
            settingKey: "settings_mica"
            visible: false
            Layout.preferredHeight: 0
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "淡入淡出"
        }

        SwitchSetting {
            settingKey: "anim_fade_window"
            title: "窗口打开时渐显"
            description: "主窗口出现时淡入，而不是一下子跳出来"
            icon.name: "ic_fluent_window_20_regular"
        }

        SwitchSetting {
            settingKey: "anim_fade_panel"
            title: "面板展开时渐显"
            description: "灵动岛下拉面板展开时淡入"
            icon.name: "ic_fluent_panel_bottom_20_regular"
        }

        SwitchSetting {
            settingKey: "anim_fade_text"
            title: "文字变化时渐显"
            description: "灵动岛上的文字切换时淡入淡出"
            icon.name: "ic_fluent_text_font_20_regular"
        }

        NumberSetting {
            settingKey: "anim_duration"
            title: "动画时长"
            description: "淡入淡出的持续时间"
            icon.name: "ic_fluent_timer_20_regular"
            suffix: "ms"
            controlWidth: 160
        }
    }
}
