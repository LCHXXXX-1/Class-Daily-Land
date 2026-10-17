import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 作业 —— 对齐主窗口右键「编辑作业」那个原生对话框（menu.HomeworkEditor）：
//
//   原生那一套是：科目 + 提交日期 + 多行内容 → 「添加作业」；
//   下面按**科目分组**列出来，组标题带日期、右边「全部清除」，
//   每条右边「修改」「删除」。增删改之后立刻 app.update_display() 刷主窗口。
//
//   之前这一页少了「提交日期」「修改」和多行内容，还只在内存里刷新，
//   主窗口看不到变化 —— 所以看着像"根本用不了"。现在逐项补齐。
//
// 数据仍然走 Homework 桥（嵌入模式直接写 HomeworkManager 的 homework.json）。
PageShell {
    title: "作业"

    property var items: []
    property var groups: []
    property bool hintIsError: true
    property string hint: ""

    // 修改对话框的暂存
    property int editIndex: -1

    Component.onCompleted: refresh()

    /// 重新读一遍并分组。
    /// 分组规则与原生 get_grouped_homework() 完全一致：按科目聚合，
    /// 组日期取该科目**第一条非空**的日期。
    function refresh() {
        items = HomeworkStore.items()
        var out = []
        for (var i = 0; i < items.length; i++) {
            var it = items[i] || {}
            var subject = String(it.subject || "").trim() || "未分类"
            var hit = null
            for (var j = 0; j < out.length; j++) {
                if (out[j].subject === subject) { hit = out[j]; break }
            }
            if (hit === null) {
                hit = { subject: subject, date: "", entries: [] }
                out.push(hit)
            }
            if (!hit.date && it.date) hit.date = String(it.date)
            hit.entries.push({
                index: i,
                content: String(it.content || ""),
                date: String(it.date || "")
            })
        }
        groups = out
    }

    function setHint(text, isError) {
        hint = text
        hintIsError = isError !== false
    }

    function addItem() {
        var content = String(contentArea.text || "").trim()
        if (content.length === 0) {
            setHint("作业内容不能为空", true)
            return
        }
        var ok = HomeworkStore.add(String(subjectField.text || "").trim(),
                                   content,
                                   String(dateField.text || "").trim())
        if (!ok) {
            setHint("保存失败：看看主程序的作业文件能不能写", true)
            return
        }
        contentArea.text = ""
        dateField.text = ""
        setHint("已添加", false)
        refresh()
    }

    function openEdit(entry) {
        var it = items[entry.index] || {}
        editIndex = entry.index
        editSubjectField.text = String(it.subject || "")
        editDateField.text = String(it.date || "")
        editContentArea.text = String(it.content || "")
        editDialog.open()
    }

    function applyEdit() {
        var content = String(editContentArea.text || "").trim()
        if (content.length === 0) return
        var ok = HomeworkStore.update(editIndex,
                                      String(editSubjectField.text || "").trim(),
                                      content,
                                      String(editDateField.text || "").trim())
        if (ok) {
            editDialog.close()
            setHint("已修改", false)
            refresh()
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        // ---------------- 新增 ----------------
        Text {
            typography: Typography.BodyStrong
            text: "新增作业"
        }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 216
            padding: 16

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        text: "科目"
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                    TextField {
                        id: subjectField
                        Layout.preferredWidth: 150
                        placeholderText: "如 数学"
                    }

                    Text {
                        text: "提交日期"
                        color: Theme.currentTheme.colors.textSecondaryColor
                    }
                    TextField {
                        id: dateField
                        Layout.preferredWidth: 190
                        placeholderText: "可留空，如 2026-10-20"
                    }

                    Item { Layout.fillWidth: true }
                }

                Text {
                    text: "作业内容"
                    color: Theme.currentTheme.colors.textSecondaryColor
                }

                TextArea {
                    id: contentArea
                    Layout.fillWidth: true
                    Layout.preferredHeight: 76
                    placeholderText: "一行一条也行，原样显示在主窗口里"
                    wrapMode: TextArea.Wrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        visible: hint.length > 0
                        color: hintIsError
                               ? Theme.currentTheme.colors.systemCautionColor
                               : Theme.currentTheme.colors.systemSuccessColor
                        text: hint
                    }

                    // 提示为空时它顶住，按钮才会停在右边（visible=false 的
                    // Text 在 RowLayout 里宽度为 0，fillWidth 也撑不开）
                    Item { Layout.fillWidth: true }

                    Button {
                        text: "添加作业"
                        highlighted: true
                        onClicked: addItem()
                    }
                }
            }
        }

        // ---------------- 列表 ----------------
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 8

            Text {
                typography: Typography.BodyStrong
                text: "共 " + items.length + " 条作业"
                       + (groups.length > 0 ? "（" + groups.length + " 个科目）" : "")
            }
            Item { Layout.fillWidth: true }
            Button {
                visible: items.length > 0
                text: "全部清空"
                onClicked: clearAllDialog.open()
            }
        }

        Repeater {
            model: groups

            delegate: ColumnLayout {
                id: groupBlock
                required property var modelData
                Layout.fillWidth: true
                spacing: 2

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    spacing: 8

                    Text {
                        typography: Typography.BodyStrong
                        text: groupBlock.modelData.subject
                              + (groupBlock.modelData.date.length > 0
                                 ? "  " + groupBlock.modelData.date : "")
                    }
                    Text {
                        color: Theme.currentTheme.colors.textSecondaryColor
                        text: groupBlock.modelData.entries.length + " 条"
                    }
                    Item { Layout.fillWidth: true }
                    Button {
                        text: "整组清除"
                        onClicked: {
                            HomeworkStore.clearSubject(groupBlock.modelData.subject)
                            refresh()
                        }
                    }
                }

                Frame {
                    Layout.fillWidth: true
                    Layout.preferredHeight: groupBlock.modelData.entries.length * 52
                    padding: 0

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0

                        Repeater {
                            model: groupBlock.modelData.entries

                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 52
                                Layout.leftMargin: 18
                                Layout.rightMargin: 12
                                spacing: 12

                                Text {
                                    Layout.preferredWidth: 30
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: (modelData.index + 1) + "."
                                }

                                Text {
                                    Layout.fillWidth: true
                                    wrapMode: Text.WrapAnywhere
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                    text: modelData.content
                                }

                                Text {
                                    visible: modelData.date.length > 0
                                    color: Theme.currentTheme.colors.textSecondaryColor
                                    text: modelData.date
                                }

                                Button {
                                    text: "修改"
                                    onClicked: openEdit(modelData)
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
            Layout.margins: 28
            color: Theme.currentTheme.colors.textSecondaryColor
            text: "暂无作业 —— 上面填一条试试"
        }
    }

    // ---------------- 对话框 ----------------

    Dialog {
        id: editDialog
        title: "修改作业"
        width: 560
        modal: true

        Text { text: "科目" }
        TextField {
            id: editSubjectField
            Layout.fillWidth: true
            placeholderText: "留空算未分类"
        }

        Text { text: "提交日期" }
        TextField {
            id: editDateField
            Layout.fillWidth: true
            placeholderText: "可以留空"
        }

        Text { text: "作业内容" }
        TextArea {
            id: editContentArea
            Layout.fillWidth: true
            Layout.preferredHeight: 120
            wrapMode: TextArea.Wrap
        }

        footer: DialogButtonBox {
            Button {
                text: "取消"
                onClicked: editDialog.close()
            }
            Button {
                text: "保存"
                highlighted: true
                onClicked: applyEdit()
            }
        }
    }

    Dialog {
        id: clearAllDialog
        title: "清空全部作业"
        width: 440
        modal: true

        Text {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: "会把 " + items.length + " 条作业全部删掉，主窗口的作业列表也会一起清空。"
        }

        footer: DialogButtonBox {
            Button {
                text: "取消"
                onClicked: clearAllDialog.close()
            }
            Button {
                text: "全部清空"
                highlighted: true
                onClicked: {
                    clearAllDialog.close()
                    for (var i = items.length - 1; i >= 0; i--) {
                        HomeworkStore.remove(i)
                    }
                    setHint("已清空", false)
                    refresh()
                }
            }
        }
    }
}
