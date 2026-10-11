import QtQuick
import QtQuick.Layouts
import RinUI

// 数字设置行（SpinBox）。范围来自 schema —— QML 侧不再抄一遍 min/max。
//
// `scale` 用来把「存储值」和「显示值」分开：
//   存储 main_width_ratio = 0.22  ←→  显示 22 %
// 这样 SpinBox 始终在整数上工作，浮点设置也能有干净的界面。
SettingCard {
    id: root

    property string settingKey: ""
    property string suffix: ""
    property real scale: 1
    property int controlWidth: 150
    property int decimals: 0
    readonly property var meta: Config.meta(root.settingKey)

    property real value: Number(Config.get(root.settingKey, defaultOf()))

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

    function defaultOf() {
        return (meta && meta.default !== undefined) ? meta.default : 0
    }
    function lowOf() {
        if (!meta || meta.low === null || meta.low === undefined) return -999999
        return meta.low * scale
    }
    function highOf() {
        if (!meta || meta.high === null || meta.high === undefined) return 999999
        return meta.high * scale
    }
    function stepOf() {
        var s = (meta && meta.step) ? meta.step : 1
        var scaled = s * scale
        return scaled >= 1 ? Math.round(scaled) : scaled
    }
    function toDisplay(stored) {
        var d = stored * scale
        return decimals > 0 ? d.toFixed(decimals) : String(Math.round(d))
    }
    function decorate(text) {
        return suffix.length > 0 ? text + " " + suffix : text
    }

    SpinBox {
        Layout.preferredWidth: root.controlWidth
        editable: true
        from: root.lowOf()
        to: root.highOf()
        stepSize: root.stepOf()
        value: Math.round(root.value * root.scale)
        enabled: !Config.isKeyLocked(root.settingKey)

        textFromValue: function (v) { return root.decorate(root.toDisplay(v / root.scale)) }
        valueFromText: function (t) {
            var n = parseFloat(String(t).replace(/[^\d.\-]/g, ""))
            return isNaN(n) ? root.value * root.scale : n
        }

        // valueModified 只在用户改过之后发（构造期设初值不会触发）
        onValueModified: {
            root.value = value / root.scale
            Config.set(root.settingKey, root.value)
        }
    }
}
