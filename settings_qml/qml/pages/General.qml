import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 通用 —— 分区用 ColumnLayout(spacing 4) 包住「BodyStrong 标题 + 若干卡片」，
// 与 Class Widgets 2 的 General/Index.qml 结构一致。
PageShell {
    title: "通用"

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "主窗口"
        }

        SwitchSetting {
            settingKey: "show_main_window"
            title: "显示班级日常窗口"
            description: "关掉之后，托盘菜单里还能再打开"
            icon.name: "ic_fluent_window_20_regular"
        }

        SliderSetting {
            settingKey: "main_width_ratio"
            title: "窗口宽度"
            description: "占屏幕宽度的百分之多少"
            icon.name: "ic_fluent_resize_20_regular"
            scale: 100
            suffix: "%"
        }

        SliderSetting {
            settingKey: "main_opacity"
            title: "窗口透明度"
            description: "设为 0 表示完全透明"
            icon.name: "ic_fluent_transparency_square_20_regular"
            scale: 100
            suffix: "%"
        }

        NumberSetting {
            settingKey: "main_font_size"
            title: "正文字号"
            description: "班级日常窗口里作业与名单的字号"
            icon.name: "ic_fluent_text_font_20_regular"
            suffix: "px"
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "作业滚动"
        }

        SwitchSetting {
            settingKey: "main_auto_scroll"
            title: "自动滚动作业"
            description: "作业内容超过窗口高度时自动向上滚动"
            icon.name: "ic_fluent_arrow_sort_20_regular"
        }

        NumberSetting {
            settingKey: "main_scroll_interval"
            title: "滚动间隔"
            description: "每多少毫秒滚动一次"
            icon.name: "ic_fluent_timer_20_regular"
            suffix: "ms"
            controlWidth: 160
        }

        NumberSetting {
            settingKey: "main_scroll_step"
            title: "每步滚动距离"
            icon.name: "ic_fluent_arrow_sort_20_regular"
            suffix: "px"
            controlWidth: 160
        }

        NumberSetting {
            settingKey: "main_scroll_pause"
            title: "到底暂停"
            description: "滚到底部后停几拍再回到开头；0 表示不停"
            icon.name: "ic_fluent_timer_20_regular"
            suffix: "次"
            controlWidth: 160
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "启动与更新"
        }

        SwitchSetting {
            settingKey: "check_update_on_start"
            title: "启动时检查更新"
            description: "由独立更新器处理，可随时手动检查"
            icon.name: "ic_fluent_arrow_sync_20_regular"
        }

        SwitchSetting {
            settingKey: "block_update_on_source"
            title: "源码运行保护更新"
            description: "检测到本地主入口源码时不再自动更新，改前先提醒备份"
            icon.name: "ic_fluent_shield_20_regular"
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "右键菜单"
        }

        // 默认走本设置中心的对应页；打开它就退回老的原生 Qt 对话框。
        // 两项数据本来就是同一份（homework.json / schedule.json），
        // 这里只是选「用哪套界面改」，不会分成两份。
        SwitchSetting {
            settingKey: "right_click_native_menu"
            title: "作业 / 课表用回原生对话框"
            description: "关着时右键「编辑作业 / 课表管理 / 假期 / 周末」直接打开本设置页；"
                         + "打开则恢复原来的独立对话框"
            icon.name: "ic_fluent_cursor_click_20_regular"
        }
    }
}
