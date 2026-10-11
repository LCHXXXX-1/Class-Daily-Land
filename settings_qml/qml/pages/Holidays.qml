import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 假期与调休：增删列表，落到 data/settings/holidays.json。
// 演示「QML 列表 + Python 桥 + 原子写盘」这条完整链路。
SubPage {

    // 左侧导航只列顶层页（见 Settings.qml 的说明），子页靠这个面包屑定位 + 返回
    contentHeader: PageHeader {
        rootTitle: "设置"
        parentTitle: "课表与提醒"
        currentTitle: "假期与调休"
        description: "假期区间与调休上课日"
        onRootClicked: settingsWindow.gotoTitle("首页")
        onParentClicked: settingsWindow.gotoTitle("课表与提醒")
    }

    property var items: ListStore.items("holidays")
    property string draftStart: ""
    property string draftEnd: ""
    property string draftName: ""

    function refresh() {
        items = ListStore.items("holidays")
    }

    function addItem() {
        if (draftStart.length === 0 || draftEnd.length === 0) {
            tip.text = "开始与结束日期都要填（形如 2026-10-01）"
            return
        }
        ListStore.add("holidays", {
            start: draftStart,
            end: draftEnd,
            name: draftName
        })
        draftStart = ""
        draftEnd = ""
        draftName = ""
        tip.text = ""
        refresh()
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "新增假期"
        }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 120
            padding: 16

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    TextField {
                        Layout.preferredWidth: 150
                        Layout.fillHeight: true
                        placeholderText: "开始 2026-10-01"
                        onTextChanged: draftStart = text
                    }
                    TextField {
                        Layout.preferredWidth: 150
                        Layout.fillHeight: true
                        placeholderText: "结束 2026-10-07"
                        onTextChanged: draftEnd = text
                    }
                    TextField {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        placeholderText: "名称（如 国庆）"
                        onTextChanged: draftName = text
                    }
                    Button {
                        Layout.preferredWidth: 80
                        text: "加上"
                        highlighted: true
                        onClicked: addItem()
                    }
                }

                Text {
                    id: tip
                    color: Theme.currentTheme.colors.systemCautionColor
                    visible: text.length > 0
                }
            }
        }

        Text {
            typography: Typography.BodyStrong
            text: "已设置 " + items.length + " 段假期"
        }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(64, items.length * 52)
            padding: 0

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Repeater {
                    model: items

                    delegate: RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 52
                        Layout.leftMargin: 18
                        Layout.rightMargin: 12
                        spacing: 12

                        IconWidget {
                            Layout.preferredWidth: 20
                            Layout.preferredHeight: 20
                            icon: "ic_fluent_calendar_20_regular"
                            size: 20
                        }

                        Text {
                            Layout.fillWidth: true
                            text: (modelData.name ? modelData.name + "：" : "")
                                  + modelData.start + " ～ " + modelData.end
                            elide: Text.ElideRight
                        }

                        Button {
                            text: "删除"
                            onClicked: {
                                ListStore.remove("holidays", index)
                                refresh()
                            }
                        }
                    }
                }

                Text {
                    visible: items.length === 0
                    Layout.alignment: Qt.AlignHCenter
                    Layout.margins: 20
                    color: Theme.currentTheme.colors.textSecondaryColor
                    text: "还没有假期，上面加一段试试"
                }
            }
        }
    }
}
