import QtQuick
import RinUI

// PageShell —— 所有设置页的公共基类：**只负责横向转场**，不管长什么样。
//
// 为什么要有这一层（也是踩出来的）：
//   起初把转场逻辑写在 SubPage 里（SubPage = FluentPage 子类 + 面包屑）。
//   结果只有 6 个子页有横向转场，另外 10 个顶层页（Home / General / Plugins …）
//   全是 FluentPage，**出场的旧页没有 slideOut 属性**，转场动画写了个寂寞 ——
//   而且是**静默失效**：写到一个不存在的属性，Qt 不报错，页面只是不动。
//
//   所以把「转场」和「面包屑」拆开：
//     PageShell —— 转场（所有页面都要）
//     SubPage   —— PageShell + 「设置 › 父 › 子」面包屑（只有子页要）
//
// ★★ 转场为什么不能直接动画 x（别再改回去）：
//   RinUI 的 FluentPage 在 StackView 里由布局托管，外部写进去的 x 会被
//   布局覆盖回 0。字面常量、加/不加 PropertyAction、StackView.view.width
//   全试过，一律不动；而同一批动画里的 opacity 照常变化，所以极具迷惑性。
//   （纯 Qt 的 StackView 上 x 是能动的，见仓库根 _probe_stackview_run.py。）
//
//   链路反过来：StackView 的转场驱动**本页的 slideIn / slideOut**，
//   再由本组件换算成内部 contentItem.x —— 那里的 x 没有 anchors 托管，可写。
//
// ★★ 透明度一律交给容器层，本组件不碰 opacity。
//   之前 SubPage 自己淡入一次、转场又淡入一次，两次抢同一个属性，
//   实测新页透明度非单调（0.40 → 0.16 → 0.58，看着像闪烁）。
FluentPage {
    id: shell

    // ---- 转场进度：由 Settings.qml 的横向转场驱动，别在别处赋值 ----

    /// 进场位移进度：1 = 还在右侧，0 = 已归位。转场把它从 1 动画到 0。
    property real slideIn: 0

    /// 出场位移进度：0 = 还在原位，1 = 已退到左侧。转场把它从 0 动画到 1。
    property real slideOut: 0

    /// 进场起点（相对页宽的比例）。Win11 设置里大概是页宽的 1/4 略多。
    readonly property real enterShiftRatio: 0.26

    /// 出场退场幅度（相对页宽的比例）。比进场小 —— 旧页只是「让位」不该抢戏，
    /// 否则整屏都在动，看着晕。
    readonly property real exitShiftRatio: 0.16

    /// contentItem 的原始 x。RinUI 把它摆到 horizontalPadding 处（约 56），
    /// 位移要叠加在这个基准上；直接归零会让整页内容往左跳一截。
    property real contentBaseX: 0

    /// 是否播动画。跟随系统「动画效果」开关
    ///（Qt 6.5+ 关掉后 styleHints().animationDurationScale() 为 0）。
    /// RinUI 的 theme / appearance 里没有这类开关，值由 AppInfo 提供，
    /// 不去读不存在的主题属性。
    readonly property bool motionEnabled: {
        try {
            return AppInfo.motionEnabled !== false
        } catch (e) {
            return true
        }
    }

    Component.onCompleted: {
        if (shell.contentItem) {
            shell.contentBaseX = shell.contentItem.x
        }
        // 兜底：不管动不动画、也不管容器层转场有没有跑，最终一定归位。
        // 否则页面会一直停在右侧，屏幕上永远带一条空白。
        // 时长给得比 Settings.qml 那条转场（260ms）宽裕，避免动画还在跑就被抢走属性。
        settleGuard.restart()
    }

    onSlideInChanged: {
        if (!shell.contentItem) return
        shell.contentItem.x = shell.contentBaseX
            + shell.width * shell.enterShiftRatio * shell.slideIn
    }

    onSlideOutChanged: {
        if (!shell.contentItem) return
        shell.contentItem.x = shell.contentBaseX
            - shell.width * shell.exitShiftRatio * shell.slideOut
    }

    Timer {
        id: settleGuard
        interval: 700
        onTriggered: {
            shell.slideIn = 0
            if (shell.contentItem) {
                shell.contentItem.x = shell.contentBaseX
            }
        }
    }
}