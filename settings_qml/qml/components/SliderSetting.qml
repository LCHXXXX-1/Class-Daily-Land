import QtQuick
import QtQuick.Layouts
import RinUI

// 滑块设置行。存储值与显示值分离（scale）。
//
// ★ 为什么交互要自己写：
//
//   RinUI 0.4.4.1 的 Slider 只画不接鼠标 —— 它重写了 Basic 样式的 `handle:`，
//   把 QtQuick.Controls.Basic.Slider 里负责交互的 MouseArea 顶掉了。
//   实测（离屏发真实鼠标事件）：点在滑块 75% 处，值会被设成**最小值**，
//   拖动毫无反应 —— 也就是「拉不动」。
//   所以现在让它只负责画（interactive: false），交互由外面一层 MouseArea 做：
//   x 坐标 → 值、按 stepSize 对齐、拖动实时跟手、松手落盘。
SettingCard {
    id: root

    property string settingKey: ""
    property string suffix: ""
    property real scale: 1
    property int sliderWidth: 220
    property int decimals: 0
    readonly property var meta: Config.meta(root.settingKey)

    property real value: Number(Config.get(root.settingKey, defaultOf()))
    readonly property bool locked: Config.isKeyLocked(root.settingKey)

    Layout.fillWidth: true

    function defaultOf() {
        return (meta && meta.default !== undefined) ? meta.default : 0
    }
    function lowOf() {
        if (!meta || meta.low === null || meta.low === undefined) return -100
        return meta.low * scale
    }
    function highOf() {
        if (!meta || meta.high === null || meta.high === undefined) return 100
        return meta.high * scale
    }
    function stepOf() {
        // schema 里给了 step 就按它换算到显示单位
        if (meta && meta.hasStep && meta.step) {
            var scaled = meta.step * scale
            return scaled >= 1 ? Math.round(scaled) : scaled
        }
        // ★ schema 没给 step 时（main_width_ratio / main_opacity 就是这样），
        //   原来这里返回 1（存储单位），再被 scale=100 乘一遍变成 **100** ——
        //   而整个行程才 35，于是每一格都吸附到端点，滑块永远停在最小值，
        //   表现就是「拉不动」。现在按「1% 一档」在显示单位里推导。
        return Math.max(1, Math.round((highOf() - lowOf()) / 100))
    }
    function display(stored) {
        var d = stored * scale
        var text = root.decimals > 0 ? d.toFixed(root.decimals) : String(Math.round(d))
        return root.suffix.length > 0 ? text + root.suffix : text
    }

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

    // ★ 兜底：动画计时器万一没推进（离屏渲染 / 窗口最小化 / 软件后端），
    //   设置行就永远停在 opacity 0 —— 既看不见也点不到，比没有动画糟得多。
    Timer {
        id: appearGuard
        interval: 700 + Math.min(root.appearIndex, 8) * 34
        onTriggered: {
            // ★ 必须先 stop：还在跑的动画对属性有更高优先级，
            //   直接赋值会被它盖回去（实测离屏下就是这样卡在透明）。
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

    RowLayout {
        spacing: 12

        Item {
            id: box
            Layout.preferredWidth: root.sliderWidth
            Layout.preferredHeight: 32

            // 只负责画：值由下面的 MouseArea 驱动，输入关掉免得抢事件
            //（RinUI 的画法用的是显式主题色，enabled: false 不会让它变灰）
            Slider {
                id: visual
                anchors.fill: parent
                from: root.lowOf()
                to: root.highOf()
                stepSize: root.stepOf()
                snapMode: Slider.SnapAlways
                enabled: false
                value: root.value * root.scale
                toolTip.visible: false
            }

            MouseArea {
                id: area
                anchors.fill: parent
                hoverEnabled: true
                enabled: !root.locked
                cursorShape: Qt.PointingHandCursor

                // x 坐标 → 值（按 stepSize 对齐，夹在 [from, to] 内）
                function valueAtX(mx) {
                    var w = Math.max(1, width)
                    var t = Math.max(0, Math.min(1, mx / w))
                    var raw = visual.from + (visual.to - visual.from) * t
                    var step = visual.stepSize > 0 ? visual.stepSize : 0
                    if (step > 0) {
                        raw = Math.round(raw / step) * step
                    }
                    return Math.max(visual.from, Math.min(visual.to, raw))
                }

                function apply(x) {
                    // 存回 3 位小数：避免 0.22000000000000003 这种浮点噪声进配置文件
                    root.value = Math.round((valueAtX(x) / root.scale) * 1000) / 1000
                    commit.restart()
                }

                // 点一下直接跳过去
                onPressed: (mouse) => apply(mouse.x)
                // 拖动实时跟手
                onPositionChanged: (mouse) => {
                    if (pressed) apply(mouse.x)
                }
                // 松手立刻落盘（拖到某个位置停住不动时也要写进去）
                onReleased: commit.restart()
            }
        }

        Text {
            Layout.preferredWidth: 52
            horizontalAlignment: Text.AlignRight
            text: root.display(root.value)
        }
    }

    // 150ms 去抖落盘。拖动时每一格都 Config.set 的话，一次 set =
    // 原子写 settings.json + controller.apply_settings()（主窗重建作业列表 /
    // 灵动岛 / 托盘），主线程被反复占住，手感会卡。
    Timer {
        id: commit
        interval: 150
        onTriggered: Config.set(root.settingKey, root.value)
    }
}