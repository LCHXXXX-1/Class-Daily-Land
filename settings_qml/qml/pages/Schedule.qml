import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

FluentPage {
    title: "课表与提醒"

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "上课提醒"
        }

        NumberSetting {
            settingKey: "island_countdown_sec"
            title: "倒计时时长"
            description: "上课前多久开始显示蓝色倒计时"
            icon.name: "ic_fluent_timer_20_regular"
            suffix: "秒"
            controlWidth: 160
        }

        NumberSetting {
            settingKey: "schedule_advance_minutes"
            title: "提前提醒"
            description: "整体提前几分钟进上课状态（下课时间不变）"
            icon.name: "ic_fluent_alert_20_regular"
            suffix: "分钟"
            controlWidth: 160
        }

        NumberSetting {
            settingKey: "schedule_time_offset_seconds"
            title: "时间偏移"
            description: "负数为提前、正数为延后，用来对齐学校的铃声"
            icon.name: "ic_fluent_history_20_regular"
            suffix: "秒"
            controlWidth: 170
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "课表与值日"
        }

        // CW2 的 ClipItem：64 高的行，图标 + 标题 + 右侧动作 + 箭头。
        // 二级入口用这种行，跟 SettingCard（一张卡一项设置）分工不同。
        Clip {
            Layout.fillWidth: true
            Layout.minimumHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_calendar_20_regular"
                title: "课表管理"
                onActivated: settingsWindow.openPage("pages/Timetable.qml")
            }
        }

        Clip {
            Layout.fillWidth: true
            Layout.minimumHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_weather_sunny_20_regular"
                title: "假期与调休"
                onActivated: settingsWindow.openPage("pages/Holidays.qml")
            }
        }

        Clip {
            Layout.fillWidth: true
            Layout.minimumHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_people_20_regular"
                title: "值日生名单"
                onActivated: settingsWindow.openPage("pages/Duty.qml")
            }
        }

        Clip {
            Layout.fillWidth: true
            Layout.minimumHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_beaker_20_regular"
                title: "状态测试"
                onActivated: settingsWindow.openPage("pages/StatusTest.qml")
            }
        }
    }
}
