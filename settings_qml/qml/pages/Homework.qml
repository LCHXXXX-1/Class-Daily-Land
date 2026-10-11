import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 作业：增删条目 + 按科目分组，落到 data/settings/homework.json。
FluentPage {
    title: "作业"

    property var items: HomeworkStore.items()
    property string draftSubject: ""
    property string draftContent: ""

    function refresh() {
        items = HomeworkStore.items()
    }

    /** 按科目分组；空科目归一成「未分类」（与源项目两个宿主的约定一致）。 */
    function grouped() {
        var groups = []
        for (var i = 0; i < items.length; i++) {
            var subject = items[i].subject || "未分类"
            var hit = null
            for (var j = 0; j < groups.length; j++) {
                if (groups[j].subject === subject) {
                    hit = groups[j]
                    break
                }
            }
            if (hit === null) {
                hit = { subject: subject, entries: [] }
                groups.push(hit)
            }
            hit.entries.push({ index: i, content: items[i].content, date: items[i].date })
        }
        return groups
    }

    function addItem() {
        if (draftContent.trim().length === 0) {
            hint.text = "作业内容不能为空"
            return
        }
        HomeworkStore.add(draftSubject, draftContent, "")
        draftSubject = ""
        draftContent = ""
        hint.text = ""
        refresh()
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        Text {
            typography: Typography.BodyStrong
            text: "新增作业"
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
                        Layout.preferredWidth: 140
                        Layout.fillHeight: true
                        placeholderText: "科目（如 数学）"
                        onTextChanged: draftSubject = text
                    }
                    TextField {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        placeholderText: "作业内容"
                        onTextChanged: draftContent = text
                        onAccepted: addItem()
                    }
                    Button {
                        Layout.preferredWidth: 80
                        text: "加上"
                        highlighted: true
                        onClicked: addItem()
                    }
                }

                Text {
                    id: hint
                    color: Theme.currentTheme.colors.systemCautionColor
                    visible: text.length > 0
                }
            }
        }

        Text {
            typography: Typography.BodyStrong
            text: "共 " + items.length + " 条作业"
        }

        Repeater {
            model: grouped()

            delegate: ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        typography: Typography.BodyStrong
                        text: modelData.subject + " (" + modelData.entries.length + ")"
                    }
                    Item { Layout.fillWidth: true }
                    Button {
                        text: "整组清除"
                        onClicked: {
                            HomeworkStore.clearSubject(modelData.subject)
                            refresh()
                        }
                    }
                }

                Frame {
                    Layout.fillWidth: true
                    Layout.preferredHeight: modelData.entries.length * 48
                    padding: 0

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        Repeater {
                            model: modelData.entries

                            delegate: RowLayout {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 48
                                Layout.leftMargin: 18
                                Layout.rightMargin: 12
                                spacing: 12

                                Text {
                                    Layout.preferredWidth: 34
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: (modelData.index + 1) + "."
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: modelData.content
                                    elide: Text.ElideRight
                                }
                                Text {
                                    visible: modelData.date.length > 0
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: modelData.date
                                }
                                Button {
                                    text: "删除"
                                    onClicked: {
                                        HomeworkStore.remove(modelData.index)
                                        refresh()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Text {
            visible: items.length === 0
            Layout.alignment: Qt.AlignHCenter
            Layout.margins: 24
            color: Theme.currentTheme.colors.textSecondaryColor
            text: "还没有作业，上面加一条试试"
        }
    }
}
