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

    // ---- 内容区栅格：照 Windows 11「设置」的量法 ----
    //
    //   窗口 1232 宽、导航 288 → 页面宽 944。Win11 里内容列左边距 28、
    //   标题与卡片同一条竖线。RinUI 默认 horizontalPadding 是 56（比系统宽一倍），
    //   看起来就是"卡片离导航栏太远、右半边空一大块"。
    //   wrapperWidth 给 900：页面宽 944 时内容列 = 944-56 = 888 < 900，
    //   于是正好铺满并停在左边距 28 上，和 Win11 对齐。
    horizontalPadding: 28
    wrapperWidth: 900

    // ---- 转场进度：由 Settings.qml 的横向转场驱动，别在别处赋值 ----

    /// 进场位移进度：1 = 还在右侧，0 = 已归位。转场把它从 1 动画到 0。
    property real slideIn: 0

    /// 出场位移进度：0 = 还在原位，1 = 已退到左侧。转场把它从 0 动画到 1。
    property real slideOut: 0

    /// 进/退场幅度（相对页面尺寸）。0.92 ≈ 整段移出去，只留一点重叠 ——
    /// 中间那一帧不会出现两条空白。
    /// 进场：新页从方向的反侧移进来；出场：旧页往同侧移出去。
    readonly property real enterShiftRatio: 0.92
    readonly property real exitShiftRatio: 0.92
    readonly property real enterShiftRatioY: 0.92
    readonly property real exitShiftRatioY: 0.92

    /// contentItem 的原始 x。RinUI 把它摆到 horizontalPadding 处（约 28），
    /// 位移要叠加在这个基准上；直接归零会让整页内容往左跳一截。
    property real contentBaseX: 0

    /// contentItem 的原始 y（同理，位移要叠在基准上）
    property real contentBaseY: 0

    /// 本次转场的方向：forward / back / down / up。
    ///
    /// 不在创建时算死，而是每帧现算 —— 因为**出门的那一页**也要知道方向，
    /// 而它是早就建好的。转场期间 `lastPages` 的最后一项是"上一页"、
    /// `currentPage` 是"这一页"，两者都稳定，所以进出两页算出来必然一致。
    function motion() {
        var prev = ""
        try {
            var lp = navigationView.lastPages
            if (lp && lp.length > 0) prev = String(lp[lp.length - 1])
        } catch (e) {
            prev = ""
        }
        var next = ""
        try {
            next = String(navigationView.currentPage)
        } catch (e) {
            next = ""
        }
        return settingsWindow.motionBetween(prev, next)
    }

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
            shell.contentBaseY = shell.contentItem.y
        }
        // 兜底：不管动不动画、也不管容器层转场有没有跑，最终一定归位。
        // 否则页面会一直停在右侧，屏幕上永远带一条空白。
        settleGuard.restart()
    }

    /// 进场：新页从方向的反侧移进来（forward 从右、back 从左、down 从上、up 从下）
    onSlideInChanged: {
        if (!shell.contentItem) return
        var m = shell.motion()
        var dx = m === "forward" ? 1 : (m === "back" ? -1 : 0)
        var dy = m === "down" ? 1 : (m === "up" ? -1 : 0)
        shell.contentItem.x = shell.contentBaseX
            + dx * shell.width * shell.enterShiftRatio * shell.slideIn
        shell.contentItem.y = shell.contentBaseY
            + dy * shell.height * shell.enterShiftRatioY * shell.slideIn
    }

    /// 退场：旧页往同侧移出去（forward 往左、back 往右、down 往上、up 往下）
    onSlideOutChanged: {
        if (!shell.contentItem) return
        var m = shell.motion()
        var dx = m === "forward" ? 1 : (m === "back" ? -1 : 0)
        var dy = m === "down" ? 1 : (m === "up" ? -1 : 0)
        shell.contentItem.x = shell.contentBaseX
            - dx * shell.width * shell.exitShiftRatio * shell.slideOut
        shell.contentItem.y = shell.contentBaseY
            - dy * shell.height * shell.exitShiftRatioY * shell.slideOut
        // 报给窗口：`sv.get(0)` 拿不到正在退场的页（replace 时它已不在栈里），
        // 探针只能靠这组值来验"旧页到底有没有移出去"。
        try {
            settingsWindow.navExitX = shell.contentItem.x - shell.contentBaseX
            settingsWindow.navExitY = shell.contentItem.y - shell.contentBaseY
        } catch (e) {
            // 独立渲染页面时没有 settingsWindow，忽略
        }
    }

    Timer {
        id: settleGuard
        interval: 700
        onTriggered: {
            shell.slideIn = 0
            // ★ slideOut 也要归零。它只在「旧页退场」时被动画到 1；
            //   万一这次转场没跑完（窗口不可见、栈正忙、页面被提前替换），
            //   它会一直停在 1，contentItem.x 就被顶到 base - 页宽*0.16 ——
            //   整页内容左移一百多像素、左边被切掉，而**不会有任何报错**。
            //   （插件页按场景坐标摆原生控件时，就是被这个坑到：算出来的
            //   x 比实际少了 151px。）
            shell.slideOut = 0
            if (shell.contentItem) {
                shell.contentItem.x = shell.contentBaseX
                shell.contentItem.y = shell.contentBaseY
            }
        }
    }
}