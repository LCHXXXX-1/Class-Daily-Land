import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

FluentPage {
    title: "高级"

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

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
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "日常维护"
        }

        Clip {
            Layout.fillWidth: true
            Layout.minimumHeight: 64

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_folder_20_regular"
                title: "打开配置文件夹"
                onActivated: Folders.open("config")
            }
        }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            padding: 0

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 22
                anchors.rightMargin: 16
                spacing: 14

                IconWidget {
                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 22
                    icon: "ic_fluent_arrow_reset_20_regular"
                    size: 22
                    color: Theme.currentTheme.colors.systemCriticalColor
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    Text {
                        text: "恢复全部默认"
                        color: Theme.currentTheme.colors.systemCriticalColor
                    }
                    Text {
                        typography: Typography.Caption
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: "把所有设置恢复为默认值；插件、课表和值日名单不受影响"
                    }
                }

                Button {
                    text: "恢复默认"
                    onClicked: resetDialog.open()
                }
            }
        }
    }

    Text {
        Layout.fillWidth: true
        Layout.topMargin: 8
        typography: Typography.Caption
        color: Theme.currentTheme.colors.textSecondaryColor
        text: "配置文件位置：" + AppInfo.configPath()
    }

    InfoBar {
        id: resetDone
        Layout.fillWidth: true
        visible: false
        severity: Severity.Success
        title: "已恢复默认"
        text: "所有设置已回到初始值。"
    }

    Dialog {
        id: resetDialog
        title: "恢复全部默认"
        width: 440
        modal: true

        Text {
            Layout.fillWidth: true
            text: "所有设置都会回到默认值。已经装好的插件、课表和值日名单不受影响。"
        }

        footer: DialogButtonBox {
            Button {
                text: "取消"
                onClicked: resetDialog.close()
            }
            Button {
                text: "恢复默认"
                highlighted: true
                onClicked: {
                    resetDialog.close()
                    Config.reset()
                    resetDone.visible = true
                    // 重新推一遍当前页：否则页面上那些控件还拿着旧值
                    settingsWindow.reloadCurrent()
                }
            }
        }
    }
}
