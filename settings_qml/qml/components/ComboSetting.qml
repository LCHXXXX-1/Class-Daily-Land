import QtQuick
import QtQuick.Layouts
import RinUI

// 下拉设置行。options 用 JS 数组：[{ text: "浅色", value: "light" }, ...]
//
// 写入走 `onActivated`（只在用户真的选了才触发），而不是 `onCurrentIndexChanged` ——
// 后者在构造期设初值时也会响，容易把默认值当成用户输入写回去。
SettingCard {
    id: root

    property string settingKey: ""
    property var options: []
    property string value: Config.get(root.settingKey, "")
    property int controlWidth: 180

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

    function indexOfValue(v) {
        for (var i = 0; i < options.length; i++) {
            if (options[i].value === v) return i
        }
        return 0
    }

    ComboBox {
        Layout.preferredWidth: root.controlWidth
        textRole: "text"
        model: root.options
        currentIndex: root.indexOfValue(root.value)
        enabled: !Config.isKeyLocked(root.settingKey)

        onActivated: {
            if (currentIndex >= 0 && currentIndex < root.options.length) {
                root.value = root.options[currentIndex].value
                Config.set(root.settingKey, root.value)
            }
        }
    }
}
