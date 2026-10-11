import QtQuick
import QtQuick.Layouts
import RinUI

// ClipItem —— 照 Class Widgets 2 的 Components/settings/ClipItem.qml 逐项对齐：
//   固定 64 高、左 22 右 16、间距 14、图标 22、箭头 18、顶部 1px 分隔线、
//   悬停叠一层极淡的 controlAltTertiaryColor（按下时更淡）。
//
// 这是「二级入口 / 文件夹跳转」这类行的原型，和 SettingCard（一张卡一项设置）分工不同。
Item {
    id: root

    property string iconName: ""
    property string title: ""
    property bool showArrow: true
    property alias content: contentSlot.data

    signal activated()

    implicitHeight: 64
    Layout.fillWidth: true

    // ---- 进场：错峰上浮（只动 transform，不动 opacity） ---------------------
    //  同一页里的设置行依次上浮（延迟按同页顺序递增，最多 8 档），
    //  比整页一起动更有「内容在装配」的感觉 —— 借的是 CW2 卡片列的观感。
    //  ★ 只动 transform，不动 opacity：动画计时器一旦不推进，位移最多差 8px
    //  （看不出来），而淡入卡住会让整页内容彻底消失。
    readonly property int appearIndex: {
        // 向上找到第一个有多个孩子的祖先，用它算顺序
        //（ClipItem 常被包在 Clip 里，直接看 parent.children 永远是 0）
        var node = root
        while (node && node.parent && node.parent.children && node.parent.children.length <= 1) {
            node = node.parent
        }
        return (node && node.parent && node.parent.children) ? node.parent.children.indexOf(node) : 0
    }

    Component.onCompleted: {
        // 窗口可见才做上浮动画；页面可能是在窗口显示前就建好的，
        // 那时动画计时器不一定推进（实测会停在中途）。
        var win = root.Window.window
        if (win && win.visible) {
            appearShift.y = 8
            appear.delay = Math.min(root.appearIndex, 8) * 34
            appear.start()
        }
        // 兜底无条件挂上：不管动不动画，超时后都把位移收回 0
        appearGuard.restart()
    }

    // ★ 兜底：动画计时器没推进时（离屏 / 窗口最小化 / 软件后端 / 页面在窗口
    //   显示前就建好）把 8px 的位移收回。动画只是锦上添花，绝不能决定
    //   「内容看不看得见」—— 所以这一版只做位移、不做淡入：
    //   实测淡入一旦卡住，整页设置行会停在 opacity 0（只剩一排空卡片外壳）。
    Timer {
        id: appearGuard
        interval: 620 + Math.min(root.appearIndex, 8) * 34
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
            target: appearShift
            property: "y"
            to: 0
            duration: 380
            easing.type: Easing.OutQuart
        }
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.currentTheme.colors.controlAltTertiaryColor
        opacity: tapHandler.pressed ? 0.15 : hoverHandler.hovered ? 0.75 : 0
    }

    Rectangle {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 1
        color: Theme.currentTheme.colors.controlBorderColor
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 22
        anchors.rightMargin: 16
        spacing: 14

        IconWidget {
            Layout.preferredWidth: 22
            Layout.preferredHeight: 22
            visible: root.iconName.length > 0
            icon: root.iconName
            size: 22
        }

        Text {
            Layout.fillWidth: true
            typography: Typography.Body
            text: root.title
            elide: Text.ElideRight
        }

        RowLayout {
            id: contentSlot
            spacing: 16
        }

        IconWidget {
            Layout.preferredWidth: 18
            Layout.preferredHeight: 18
            visible: root.showArrow
            icon: "ic_fluent_chevron_right_20_regular"
            size: 18
            opacity: 0.85
        }
    }

    HoverHandler {
        id: hoverHandler
    }

    TapHandler {
        id: tapHandler
        onTapped: root.activated()
    }
}
