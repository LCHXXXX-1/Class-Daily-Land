import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

PageShell {
    title: "灵动岛"

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "主岛"
        }

        // 可展开卡片：标题栏放一个实时开关（action），展开体放同组的密集行。
        // 这是 CW2 用得最多的一种组织方式 —— 折叠时也能看到/改到那一项最关键的值。
        SettingExpander {
            Layout.fillWidth: true
            title: "主岛"
            description: "屏幕顶部居中的悬浮胶囊"
            icon.name: "ic_fluent_apps_20_regular"
            expanded: true      // 主岛这一组默认展开：最常改的就是它

            action: Switch {
                checked: Config.get("show_island", true)
                checkedText: ""
                uncheckedText: ""
                onToggled: Config.set("show_island", checked)
            }

            SettingItem {
                title: "距屏幕顶部距离"
                description: "胶囊离屏幕上边缘多少像素"
                action: SpinBox {
                    Layout.preferredWidth: 140
                    from: 0; to: 100; stepSize: 1
                    value: Config.get("island_top_margin", 6)
                    textFromValue: function (v) { return v + " px" }
                    onValueModified: Config.set("island_top_margin", value)
                }
            }

            SettingItem {
                title: "提醒条宽度"
                description: "「上课了 / 放假啦」提醒条展开后的宽度"
                action: SpinBox {
                    Layout.preferredWidth: 140
                    from: 200; to: 800; stepSize: 1
                    value: Config.get("island_alert_width", 300)
                    textFromValue: function (v) { return v + " px" }
                    onValueModified: Config.set("island_alert_width", value)
                }
            }

            SettingItem {
                title: "提醒条停留"
                description: "提醒条展示多久后收起"
                action: SpinBox {
                    Layout.preferredWidth: 140
                    from: 100; to: 5000; stepSize: 50
                    value: Config.get("island_alert_hold_ms", 600)
                    textFromValue: function (v) { return v + " ms" }
                    onValueModified: Config.set("island_alert_hold_ms", value)
                }
            }

            SettingItem {
                title: "仅全屏时隐藏"
                description: "全屏看视频 / 演示时自动让位"
                action: Switch {
                    checked: Config.get("island_hide_on_fullscreen", true)
                    checkedText: ""
                    uncheckedText: ""
                    onToggled: Config.set("island_hide_on_fullscreen", checked)
                }
            }

            SettingItem {
                title: "启用唤醒动画"
                description: "收起时为圆形，展开后为胶囊"
                action: Switch {
                    checked: Config.get("island_show_wakeup_anim", true)
                    checkedText: ""
                    uncheckedText: ""
                    onToggled: Config.set("island_show_wakeup_anim", checked)
                }
            }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "副岛"
        }

        SettingExpander {
            Layout.fillWidth: true
            title: "副岛"
            description: "主岛右侧的插件内容区"
            icon.name: "ic_fluent_panel_right_20_regular"

            action: Switch {
                checked: Config.get("show_sub_island", true)
                checkedText: ""
                uncheckedText: ""
                onToggled: Config.set("show_sub_island", checked)
            }

            SettingItem {
                title: "默认收成圆形"
                description: "启动时先折叠，鼠标靠近再展开"
                action: Switch {
                    checked: Config.get("sub_island_collapsed", false)
                    checkedText: ""
                    uncheckedText: ""
                    onToggled: Config.set("sub_island_collapsed", checked)
                }
            }

            SettingItem {
                title: "无内容自动收起"
                description: "设为 0 表示不自动收起"
                action: SpinBox {
                    Layout.preferredWidth: 140
                    from: 0; to: 120; stepSize: 1
                    value: Config.get("sub_island_auto_collapse_sec", 5)
                    textFromValue: function (v) { return v + " 秒" }
                    onValueModified: Config.set("sub_island_auto_collapse_sec", value)
                }
            }
        }
    }
}
