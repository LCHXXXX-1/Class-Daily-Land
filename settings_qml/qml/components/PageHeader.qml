import QtQuick
import QtQuick.Layouts
import RinUI

// PageHeader —— 子页面顶部的面包屑 + 说明。
//
// 参照 Windows 11 设置的层级写法：顶上一行「设置 › 父项 › 当前页」，
// 左边一个返回箭头。最左边固定是「设置」（= 首页），点它回首页。
//
// 为什么需要它：左侧导航只列顶层页（Win11 设置就是这样：导航里只有「系统」，
// 子页在内容区顶部用面包屑表示位置）。从父页面点入口行进入子页后，
// 靠它告诉用户「你在哪、怎么回去」。
//
// 时长用字面量 —— RinUI 的 appearance 里没有 animationDuration
//（只有 buttonRadius / windowTitleBarHeight 那些），
// 写 Theme.currentTheme.appearance.animationDuration 会拿到 undefined。
Item {
    id: root

    /// 根标题，永远是「设置」，点它回首页。
    property string rootTitle: "设置"

    /// 父页面标题（如「课表与提醒」）；为空就只显示「设置 › 当前页」。
    property string parentTitle: ""

    /// 当前页标题。
    property string currentTitle: ""

    /// 可选的一句话说明，显示在面包屑下面。
    property string description: ""

    readonly property int appearDuration: 340
    readonly property int hoverDuration: 180

    signal parentClicked()
    signal rootClicked()

    //★ 必须显式给宽度。
    //
    //   contentHeader 挂的是 FluentPage 里那个** Row**（headerContainer），
    //   Row 不用 Layout 管子项，它按子项的 implicitWidth 排布 —— 不给宽度就是 0 宽，
    //   整块面包屑虽然建出来了但一个字也看不见（页面顶部直接空一截）。
    //   Row 的宽度就是页面宽度（fluentPage.width），照它铺满即可。
    implicitWidth: parent ? parent.width : 0
    width: parent ? parent.width : implicitWidth
    implicitHeight: crumbs.implicitHeight
        + (descLabel.visible ? descLabel.implicitHeight + 4 : 0)
    Layout.fillWidth: true

    RowLayout {
        id: row
        width: parent.width
        spacing: 6

        //面包屑各级之间不要被Layout 拉散：整行靠左，文字紧挨着分隔符。
        //（RowLayout 默认把剩余空间分给 fillWidth 的子项，这里没有任何子项
        //  设 fillWidth，所以行本身是紧贴的；显式写出来是为了防止以后有人
        //  给某一级加了 fillWidth 就把「设置 › 插件 › 插件管理」撑成一行大字。）
        RowLayout {
            id: crumbs
            Layout.alignment: Qt.AlignLeft | Qt.AlignBottom
            spacing: 6

        // 返回箭头（只有父页才显示）
        Rectangle {
            id: backBox
            visible: root.parentTitle.length > 0
            Layout.preferredWidth: 30
            Layout.preferredHeight: 30
            radius: 6
            color: backArea.containsMouse
                   ? Theme.currentTheme.colors.subtleFillColorSecondary
                   : "transparent"

            Behavior on color {
                ColorAnimation { duration: root.hoverDuration }
            }

            IconWidget {
                anchors.centerIn: parent
                icon: "ic_fluent_arrow_left_20_regular"
                size: 18
                color: Theme.currentTheme.colors.textColorPrimary
            }

            MouseArea {
                id: backArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.parentClicked()
            }

            ToolTip.visible: backArea.containsMouse
            ToolTip.text: "返回「" + root.parentTitle + "」"
            ToolTip.delay: 600
        }

        // 「设置 ›」 —— 永远是根，点它回首页
        Text {
            id: rootLink
            visible: root.rootTitle.length > 0
            text: root.rootTitle
            typography: Typography.Title
            color: Theme.currentTheme.colors.textColorPrimary
            Layout.alignment: Qt.AlignBottom
            font.weight: Font.Medium

            Rectangle {
                id: rootUnderline
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.currentTheme.colors.textColorPrimary
                opacity: rootArea.containsMouse ? 0.6 : 0
                Behavior on opacity {
                    NumberAnimation { duration: root.hoverDuration }
                }
            }

            MouseArea {
                id: rootArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.rootClicked()
            }
        }

        IconWidget {
            visible: root.rootTitle.length > 0 && root.parentTitle.length > 0
            // RinUI 的图标索引里只有 20 规格的 chevron，用20 的图按 16 显示
            icon: "ic_fluent_chevron_right_20_regular"
            size: 16
            Layout.alignment: Qt.AlignBottom
            Layout.bottomMargin: 3
            color: Theme.currentTheme.colors.textTertialyColor
            opacity: 0.7
        }

        // 父项
        Text {
            id: parentLink
            visible: root.parentTitle.length > 0
            text: root.parentTitle
            typography: Typography.Title
            color: root.parentTitle === root.currentTitle
                   ? Theme.currentTheme.colors.textColorPrimary
                   : Theme.currentTheme.colors.textColorSecondaryColor
            font.weight: root.parentTitle === root.currentTitle ? Font.Medium : Font.Normal
            Layout.alignment: Qt.AlignBottom

            Behavior on color {
                ColorAnimation { duration: root.hoverDuration }
            }

            Rectangle {
                id: underline
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.currentTheme.colors.textColorPrimary
                opacity: 0
                Behavior on opacity {
                    NumberAnimation { duration: root.hoverDuration }
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
                && root.parentTitle !== root.currentTitle
            icon: "ic_fluent_chevron_right_20_regular"
            size: 16
            Layout.alignment: Qt.AlignBottom
            Layout.bottomMargin: 3
            color: Theme.currentTheme.colors.textTertialyColor
            opacity: 0.7
        }

        // 当前页
        Text {
            text: root.currentTitle
            typography: Typography.Title
            color: Theme.currentTheme.colors.textColorPrimary
            font.weight: Font.Medium
            Layout.alignment: Qt.AlignBottom
        }
        }   // ← crumbs

        // 让外层 row 的高度跟着 crumbs 走（外层只是为了撑满宽度）
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
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
    //  初始位移放在 Component.onCompleted 里设：动画只是锦上添花，
    //  绝不能决定「内容看不看得见」。
    Component.onCompleted: {
        var win = root.Window.window
        if (win && win.visible) {
            appearShift.y = 8
            opacity = 0
            appear.start()
        }
        // 兜底无条件挂上：不管动不动画，超时后都把位移与透明度收回
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
            root.opacity = 1
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