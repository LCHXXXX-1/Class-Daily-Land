import QtQuick
import QtQuick.Layouts
import RinUI

// PageHeader —— 子页面顶部的「父项 › 当前页」面包屑。
//
// 为什么需要它：左侧导航只列顶层页（Win11 设置就是这样：导航里只有「系统」，
// 子页在内容区顶部用面包屑表示位置）。从父页面点入口行进入子页后，
// 靠它告诉用户「你在哪、怎么回去」——点父项即回父页面。
//
// 视觉量取自 RinUI：当前页 Typography.Title（与 FluentPage 自带标题同级），
// 父项次级文字色 + 悬停下划线。时长用字面量 —— RinUI 的 appearance 里
// 没有 animationDuration（只有 buttonRadius / windowTitleBarHeight 那些），
// 写 Theme.currentTheme.appearance.animationDuration 会拿到 undefined。
Item {
    id: root

    /// 父页面标题（如「课表与提醒」）；为空就只显示当前页标题。
    property string parentTitle: ""
    property string currentTitle: ""
    /// 可选的一句话说明，显示在面包屑下面。
    property string description: ""

    // 与 settings/components 里那套错峰进场一致的时长
    readonly property int appearDuration: 340
    readonly property int hoverDuration: 180

    signal parentClicked()

    implicitHeight: row.implicitHeight + (descLabel.visible ? descLabel.implicitHeight + 4 : 0)
    Layout.fillWidth: true

    RowLayout {
        id: row
        width: parent.width
        spacing: 6

        Text {
            id: parentLink
            visible: root.parentTitle.length > 0
            text: root.parentTitle
            typography: Typography.Title
            color: Theme.currentTheme.colors.textColorSecondaryColor
            Layout.alignment: Qt.AlignBottom

            Behavior on color {
                ColorAnimation {
                    duration: root.hoverDuration
                }
            }

            Rectangle {
                id: underline
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.currentTheme.colors.textColorPrimary
                opacity: 0
                Behavior on opacity {
                    NumberAnimation {
                        duration: root.hoverDuration
                    }
                }
            }

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onEntered: underline.opacity = 0.5
                onExited: underline.opacity = 0
                onClicked: root.parentClicked()
            }
        }

        IconWidget {
            visible: root.parentTitle.length > 0
            // RinUI 的图标索引里只有 20 规格的 chevron（16 那个名字不存在），
            // 这里用 20 的图按 16 显示
            icon: "ic_fluent_chevron_right_20_regular"
            size: 16
            Layout.alignment: Qt.AlignBottom
            Layout.bottomMargin: 3
            color: Theme.currentTheme.colors.textTertialyColor
            opacity: 0.7
        }

        Text {
            text: root.currentTitle
            typography: Typography.Title
            color: Theme.currentTheme.colors.textColorPrimary
            Layout.alignment: Qt.AlignBottom
        }
    }

    Text {
        id: descLabel
        visible: root.description.length > 0
        text: root.description
        typography: Typography.Body
        color: Theme.currentTheme.colors.textColorSecondaryColor
        anchors.top: row.bottom
        anchors.topMargin: 4
        width: parent.width
        wrapMode: Text.WordWrap
    }

    // ---- 进场：淡入 + 轻微上移 ----
    //  初始位移放在 Component.onCompleted 里设（见各设置行里的同款说明）：
    //  动画只是锦上添花，绝不能决定「内容看不看得见」。
    Component.onCompleted: {
        // 窗口可见才做上浮动画；页面可能是在窗口显示前就建好的
        var win = root.Window.window
        if (win && win.visible) {
            appearShift.y = 8
            appear.start()
        }
        // 兜底无条件挂上：不管动不动画，超时后都把位移收回 0
        appearGuard.restart()
    }

    // ★ 兜底：动画计时器没推进时把 8px 位移收回（实测不推进时动画会停在中途）
    Timer {
        id: appearGuard
        interval: 620
        onTriggered: {
            // ★ 先 stop：还在跑的动画对属性有更高优先级，直接赋值会被它盖回去
            appear.stop()
            appearShift.y = 0
        }
    }

    // 用 per-property transform（Qt 6.9 起 Transform 元素已被移除）
    transform: Translate {
        id: appearShift
        y: 8
    }

    ParallelAnimation {
        id: appear
        NumberAnimation {
            target: root
            property: "opacity"
            to: 1
            duration: root.appearDuration
            easing.type: Easing.OutQuart
        }
        NumberAnimation {
            target: appearShift
            property: "y"
            to: 0
            duration: root.appearDuration + 40
            easing.type: Easing.OutQuart
        }
    }
}