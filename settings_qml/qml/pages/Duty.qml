import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 值日生名单：增删姓名，落到 data/settings/name.json（与源项目同名同格式）。
SubPage {

    // 左侧导航只列顶层页（见 Settings.qml 的说明），子页靠这个面包屑定位 + 返回
    contentHeader: PageHeader {
        rootTitle: "设置"
        parentTitle: "课表与提醒"
        currentTitle: "值日生名单"
        description: "值日轮流安排"
        onRootClicked: settingsWindow.gotoTitle("首页")
        onParentClicked: settingsWindow.gotoTitle("课表与提醒")
    }

    property var names: ListStore.items("duty")
    property string draft: ""

    function refresh() {
        names = ListStore.items("duty")
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        InfoBar {
            Layout.fillWidth: true
            severity: Severity.Info
            title: "名单轮流值日"
            text: "名单顺序就是值日轮流的顺序；每天自动往后推一位。"
        }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            padding: 16

            RowLayout {
                anchors.fill: parent

                TextField {
                    Layout.fillWidth: true
                    placeholderText: "输入姓名，回车或点「加上」"
                    text: draft
                    onTextChanged: draft = text
                    onAccepted: addName()
                }

                Button {
                    Layout.preferredWidth: 80
                    text: "加上"
                    highlighted: true
                    onClicked: addName()
                }
            }
        }

        Text {
            typography: Typography.BodyStrong
            text: "共 " + names.length + " 人"
        }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(64, names.length * 48)
            padding: 0

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Repeater {
                    model: names

                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 48
                        Layout.leftMargin: 18
                        Layout.rightMargin: 12
                        spacing: 12

                        Text {
                            Layout.preferredWidth: 32
                            color: Theme.currentTheme.colors.textSecondaryColor
                            text: (index + 1) + "."
                        }

                        Text {
                            Layout.fillWidth: true
                            text: modelData
                            elide: Text.ElideRight
                        }

                        Button {
                            text: "删除"
                            onClicked: {
                                ListStore.remove("duty", index)
                                refresh()
                            }
                        }
                    }
                }

                Text {
                    visible: names.length === 0
                    Layout.alignment: Qt.AlignHCenter
                    Layout.margins: 20
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: "名单是空的，先加上几位同学"
                }
            }
        }
    }

    function addName() {
        if (draft.trim().length === 0) return
        ListStore.add("duty", draft)
        draft = ""
        refresh()
    }
}
