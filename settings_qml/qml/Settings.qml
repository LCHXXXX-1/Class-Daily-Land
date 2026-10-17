import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI

// Adapted from Class Widgets 2's FluentWindow settings shell. CDL keeps its
// own pages and service bindings while using the upstream navigation pattern.
FluentWindow {
    id: settingsWindow

    icon: Paths.asset("images/icons/cw2_settings.png")
    title: "设置 · Class Daily Land"

    // 默认尺寸对齐 Windows 11 的「设置」窗口（1232 × 762）。
    // Win11 的导航栏在 1232 宽下是 288，内容区左边距 28 —— 这套数字直接照抄，
    // 换尺寸时三处要一起调（这里 / navigationView.navExpandWidth / PageShell）。
    width: 1232
    height: 762
    minimumWidth: 960
    minimumHeight: 640

    // 导航栏宽度 + 首屏修尾都由宿主在 show() 之后触发（见 unstickNavigation）：
    // 首屏那次 push 是在窗口显示前发起的，动画不会推进，busy/pushInProgress
    // 会一起卡住 —— 必须等窗口真的可见了再收尾。
    Component.onCompleted: {
        // 导航栏固定 288 宽（RinUI 默认按文字长度动态算，只有 200 上下，
        // 比 Win11 窄一大截，左栏看着就"不像系统设置"）。
        navigationView.navExpandWidth = 288
    }

    /// 宿主在 show() 之后调用：把首屏那次卡住的转场收尾，再换上横向转场。
    ///
    /// ★ 不能在 Component.onCompleted 里做：那时窗口还不可见，转场动画不推进，
    ///   `completeTransition()` 也没法把状态机推到终点。推迟到真正显示之后，
    ///   调用一次就能让 busy 与 pushInProgress 一起归位。
    function unstickNavigation() {
        navigationView.navExpandWidth = 288
        var sv = findStackView()
        if (sv !== null && sv.busy) {
            try {
                sv.completeTransition()
            } catch (e) {
                console.warn("[settings] completeTransition 不可用：", e)
            }
        }
        navigationView.setPushInProgress(false)
        // ★ 立刻装，别等"栈不忙"。
        //   busy 会一直挂到首屏那次转场结束（实测 2 秒多），等它等于让用户
        //   头两秒用的都是 RinUI 自带的纵向浮动 + 淡入 —— 看起来就是"有淡化"。
        //   赋值转场本身没有副作用，忙的时候装也只影响下一次转场。
        Qt.callLater(installHorizontalTransition)
    }


    /// 首屏。宿主可以用 Paths.setStartPage("灵动岛") 指定，**在加载前**生效：
    /// NavigationView 的首次 push 直接落到这一页，省掉「显示后再导航」的竞态。
    defaultPage: {
        var want = Paths.startPage()
        if (!want) return ""
        var hit = findPage(navigationItems, want)
        if (hit) return hit
        for (var i = 0; i < pageTable.length; i++) {
            if (pageTable[i].title === want) return pageTable[i].page
        }
        return ""
    }

    /// 用于页面入口的面包屑和旧调用方的标题直达。
    readonly property var pageTable: [
        { title: "课表管理", parent: "课表与提醒", page: Paths.qml("pages/Timetable.qml") },
        { title: "周末作息", parent: "课表与提醒", page: Paths.qml("pages/Weekend.qml") },
        { title: "假期与调休", parent: "课表与提醒", page: Paths.qml("pages/Holidays.qml") },
        { title: "值日生名单", parent: "课表与提醒", page: Paths.qml("pages/Duty.qml") },
        { title: "状态测试", parent: "课表与提醒", page: Paths.qml("pages/StatusTest.qml") },
        { title: "插件管理", parent: "插件", page: Paths.qml("pages/PluginManage.qml") },
        { title: "插件设置", parent: "插件管理", page: Paths.qml("pages/PluginPage.qml") },
        { title: "插件市场", parent: "插件", page: Paths.qml("pages/Market.qml") },
        { title: "依赖包管理", parent: "插件市场", page: Paths.qml("pages/Packages.qml") }
    ]

    /// 在导航树里按标题找页面 URL。
    function findPage(items, title) {
        for (var i = 0; i < (items ? items.length : 0); i++) {
            var item = items[i]
            if (item.title === title && item.page) return item.page
            var hit = findPage(item.subItems, title)
            if (hit) return hit
        }
        return null
    }

    /// 按导航标签切页。宿主 / 命令行靠它做「按页直达」，
    /// 例如托盘菜单点「灵动岛设置」；子页在 pageTable 里。
    ///
    /// 注意不能直接写 `currentPage = url` —— 那只是改了属性，
    /// NavigationView 不会去 push 页面（真正加载页面的是 safePush）。
    function gotoTitle(title) {
        var aliases = {
            "外观": "个性化",
            "高级": "交互",
            "Advanced": "交互",
            "Home": "首页",
            "General": "通用",
            "Widgets": "灵动岛",
            "Interactions": "交互",
            "Personalization": "个性化",
            "Notification & Time": "课表与提醒",
            "Plugins": "插件",
            "本地插件": "插件",
            // 「插件设置」现在是真实存在的页（内嵌插件自己的设置页），不再是
            // 「插件管理」的别名；只保留旧名字 PluginHub → 插件管理。
            "PluginHub": "插件管理",
            "About": "关于",
            "Update": "关于"
        }
        var targetTitle = aliases[title] || title
        var target = findPage(navigationItems, targetTitle)
        if (!target) {
            for (var i = 0; i < pageTable.length; i++) {
                if (pageTable[i].title === targetTitle) {
                    target = pageTable[i].page
                    break
                }
            }
        }
        if (target) {
            navigationView.safePush(target, false, false, {})
        }
        return target !== null
    }

    /// 等导航栈就绪再切页。给宿主/命令行「打开设置直接跳到某一页」用。
    ///
    /// ★ 为什么不能直接 gotoTitle：
    ///   窗口 show() 的那一拍，NavigationView 自己还在 push 首页 ——
    ///   此时 stackView.currentItem 还是 null，`stackView.replace(null, ...)`
    ///   拿不到可替换的 item，直接放弃 —— 也会把 pushInProgress 卡在 true。
    ///   所以这里只等 currentItem 出现，**不等 pushInProgress**：
    ///   那把锁由看门狗负责解开，等它等于白等（实测能卡一秒以上）。
    ///
    /// ★ 重试必须用**真定时器**，不能用 Qt.callLater：
    ///   callLater 只是排到本轮事件循环末尾，20 次加起来可能还不到 20ms，
    ///   首屏 push 根本还没完成就放弃了 —— 表现是「宿主指定了起始页却没跳」。
    property string _pendingTitle: ""
    property int _pendingTries: 0

    function gotoTitleWhenReady(title, tries) {
        if (tries === undefined) tries = 0
        var sv = findStackView()
        if (sv !== null && sv.currentItem === null && tries < 25) {
            _pendingTitle = title
            _pendingTries = tries
            readyTimer.restart()
            return false
        }
        _pendingTitle = ""
        return gotoTitle(title)
    }

    Timer {
        id: readyTimer
        interval: 60
        repeat: false
        onTriggered: {
            if (settingsWindow._pendingTitle.length > 0) {
                settingsWindow.gotoTitleWhenReady(settingsWindow._pendingTitle,
                                                  settingsWindow._pendingTries + 1)
            }
        }
    }

    /// ★ pushInProgress 看门狗。
    ///
    ///   RinUI 的 asyncPush 用 `setPushInProgress(false)` 解开这把锁，而它挂在
    ///   `stackView.busyChanged` 上等转场结束。窗口显示之前发起的首屏 push
    ///   动画根本不会推进，`busyChanged` 也就不会发 —— 锁于是永远举着，
    ///   之后每一次 safePush 都只会 Qt.callLater 重试，**点导航看起来毫无反应**。
    ///
    ///   这里每 200ms 收一次尾：连着两次（约 400ms）还举着就直接放掉。
    ///   正常一次转场 260ms 左右，400ms 的阈值不会打断它。
    Timer {
        id: pushLockWatchdog
        property int stuck: 0
        interval: 200
        repeat: true
        running: true
        onTriggered: {
            var sv = findStackView()
            if (sv === null || !navigationView.pushInProgress) {
                stuck = 0
                return
            }
            stuck += 1
            if (stuck >= 2) {
                if (sv.busy) {
                    try {
                        sv.completeTransition()
                    } catch (e) {
                        // 老版本没有这个方法就只放锁
                    }
                }
                navigationView.setPushInProgress(false)
                stuck = 0
            }
        }
    }

    /// 导航项在 navigationItems 里的下标；不是顶层页就返回 -1。
    function navIndexOf(url) {
        if (!url) return -1
        for (var i = 0; i < navigationItems.length; i++) {
            if (String(navigationItems[i].page) === String(url)) return i
        }
        return -1
    }

    /// 这一跳该往哪个方向动。PageShell 每帧调它来算位移。
    ///
    ///   forward：顶层 → 子页（新页从右边推进来）
    ///   back   ：子页 → 顶层（新页从左边滑回来）
    ///   down   ：两个顶层页之间，目标在下方
    ///   up     ：两个顶层页之间，目标在上方
    function motionBetween(prev, next) {
        if (!prev) return "forward"              // 首屏，没有"上一页"
        var a = navIndexOf(prev)
        var b = navIndexOf(next)
        if (a >= 0 && b >= 0) {
            if (a === b) return "forward"
            return b > a ? "down" : "up"
        }
        if (a < 0 && b >= 0) return "back"       // 子页 → 顶层
        return "forward"                          // 顶层 → 子页 / 子页 → 子页
    }

    // ---- 左侧导航的强调条 ----------------------------------------------------
    //
    // RinUI 的 Indicator 是**每个条目各自一条**：切页时旧的消失、新的出现，
    // 没有位移，看着就是"小蓝条不会上下动"。这里自己画一条会滑的，并把
    // RinUI 那几条关掉（`visible = false` 会把绑定打断，等于永久隐藏）。
    Rectangle {
        id: navMarker
        width: 3
        height: 17
        radius: 1.5
        color: Theme.currentTheme.colors.primaryColor
        x: 0
        y: 0
        visible: false
        z: 1000

        Behavior on y {
            NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
        }
        Behavior on opacity {
            NumberAnimation { duration: 140 }
        }
    }

    /// 深度遍历（QML 拿不到 NavigationBar 内部的 id，只能走视觉树）
    function walkItems(node, visit) {
        var kids = node ? node.children : null
        if (!kids) return
        for (var i = 0; i < kids.length; i++) {
            var child = kids[i]
            try {
                visit(child)
            } catch (e) {
                // 某些子项属性读不到就跳过，不能让一条坏节点拖垮整轮
            }
            walkItems(child, visit)
        }
    }

    /// 把强调条挪到当前高亮项上
    function syncNavMarker() {
        var bar = navigationView ? navigationView.navigationBar : null
        if (!bar) return
        var items = []
        walkItems(bar, function (c) {
            if (c && c.itemData !== undefined && c.highlighted !== undefined) {
                items.push(c)
            }
        })
        var hit = null
        for (var i = 0; i < items.length; i++) {
            if (items[i].highlighted) hit = items[i]
        }
        navHighlightedTitle = hit ? String(hit.itemData.title) : ""
        if (!hit) {
            navMarker.visible = false
            return
        }
        // 首次同步时把 RinUI 自带的那几条关掉（每个条目一条，宽 3、圆角 10）
        for (var j = 0; j < items.length; j++) {
            walkItems(items[j], function (c) {
                if (c && c.radius !== undefined && c.width === 3 && c.height > 0
                        && c.height < 40 && c.visible === true) {
                    c.visible = false
                }
            })
        }
        // ★ 映射到**它自己的父级**，不是 contentItem。
        //
        //   之前写成 mapToItem(contentItem) 再直接赋给 navMarker.y，结果整条
        //   低了整整一行（40px）—— 因为 navMarker 并不是 contentItem 的直接
        //   子项（它落在 FluentWindow 的 freeContainter 里，那层有自己的偏移）。
        //   用 parent 当坐标系就没有这个假设了：父级怎么挪，它都对。
        navItemTop = hit.mapToItem(settingsWindow.contentItem, 0, 0).y
        navItemHeight = hit.height
        var p = hit.mapToItem(navMarker.parent, 0, 0)
        if (!navMarker.visible) navMarker.opacity = 0
        navMarker.y = p.y + (hit.height - navMarker.height) / 2
        navMarker.visible = true
        navMarker.opacity = 1
    }

    /// 当前页内容相对基准的偏移（自检用：转场时它会动，停稳后应回到基准）
    readonly property var navContentOffset: {
        var sv = findStackView()
        var item = sv ? sv.currentItem : null
        if (!item || !item.contentItem) return Qt.point(0, 0)
        return Qt.point(item.contentItem.x, item.contentItem.y)
    }

    /// 转场是否装上 / 当前页的位移进度（自检用）
    readonly property string navTransitionState: JSON.stringify(transitionDiag)
    readonly property real navCurSlideIn: {
        var sv = findStackView()
        var it = sv ? sv.currentItem : null
        return (it && it.slideIn !== undefined) ? it.slideIn : -99
    }
    readonly property real navCurSlideOut: {
        var sv = findStackView()
        var it = sv ? sv.currentItem : null
        return (it && it.slideOut !== undefined) ? it.slideOut : -99
    }

    /// 正在**退场**的那一页相对基准的偏移（自检用，由 PageShell 在
    /// slideOut 变化时写进来）。停稳后回到 0。
    property real navExitX: 0
    property real navExitY: 0

    /// 当前被高亮的导航项标题（自检/排障用；空串=没有任何项高亮）
    property string navHighlightedTitle: ""

    /// 高亮项的落点（自检用：和强调条的中心对一下就知道有没有错位）
    property real navItemTop: -1
    property real navItemHeight: 0

    /// 强调条位置（自检/排障用，见 tools/ui_probe.py）
    readonly property real navMarkerY: navMarker.y
    readonly property bool navMarkerShown: navMarker.visible

    /// 各顶层页的 URL（顺序即导航顺序），自检拿它当 motionBetween 的输入
    readonly property var navPages: {
        var out = []
        for (var i = 0; i < navigationItems.length; i++) {
            out.push(String(navigationItems[i].page))
        }
        return out
    }

    /// 自检用：算一次方向并记下来。
    /// 为什么需要它：`QMetaObject.invokeMethod` 调 QML 函数**拿不到返回值**
    /// （只回一个"调用成功"的 bool），所以把结果落在属性上让 Python 读。
    property string motionProbe: ""

    function probeMotion(prev, next) {
        motionProbe = motionBetween(prev, next)
        return motionProbe
    }

    Connections {
        target: navigationView
        function onCurrentPageChanged() {
            Qt.callLater(settingsWindow.syncNavMarker)
        }
    }

    onWidthChanged: Qt.callLater(settingsWindow.syncNavMarker)
    onHeightChanged: Qt.callLater(settingsWindow.syncNavMarker)

    /// 侧栏可以滚动 / 折叠，绑不到信号，用低频轮询兜底（成本可忽略）
    Timer {
        interval: 400
        repeat: true
        running: true
        onTriggered: settingsWindow.syncNavMarker()
    }

    /// 某个子页的父页面标题（面包屑用；不是子页就返回空串）。
    function parentOf(title) {
        for (var i = 0; i < pageTable.length; i++) {
            if (pageTable[i].title === title) return pageTable[i].parent
        }
        return ""
    }

    /// 从页面内跳到另一页。
    /// relative 是相对 qml/ 的路径，例如 "pages/Timetable.qml"。
    function openPage(relative) {
        navigationView.push(Paths.qml(relative))
    }

    /// 重新推一遍当前页。
    /// 「恢复全部默认」之后必须调它 —— 否则页面上的控件还抱着旧值，
    /// 看着像没生效（reload=true 会让 NavigationView 丢掉组件缓存重新建）。
    function reloadCurrent() {
        navigationView.safePush(navigationView.currentPage, true, false, {})
    }

    /// ★ 把 StackView 的转场换成Windows 11 设置那种「横向推进」。
    ///
    /// RinUI 自带的 replaceEnter / replaceExit 是**纵向**的：新页从
    /// pushEnterFromY（半屏高）往上浮、旧页原地淡出 —— 像模态对话框，
    ///不像系统设置里那种「点子项，右边那页推进来，左边这页往左退掉」。
    ///
    /// stackView 是 NavigationView 的内部 id（id: stackView），没有对外暴露，
    /// 只能从子对象里捞。它是 NavigationView 视觉树里唯一同时有
    /// depth / currentItem 的那个，靠这两条确认捞对了。
    ///
    /// 注意：转场里的动画**不写 target** —— Transition 里这是标准惯用法，
    /// Qt 会自动作用到「本次被替换的那个 item」上。写了 target 反而容易
    /// 指错对象（新页/旧页是两个 item）。
    ///
    /// 页面自身（SubPage）那层只留内容淡入，位移全交给这里 —— 两层都做位移会晃。
    function installHorizontalTransition() {
        var sv = findStackView()
        if (sv === null) {
            console.warn("[settings] 没找到 StackView，沿用默认转场")
            return
        }
        sv.replaceEnter = horizontalEnter
        sv.replaceExit = horizontalExit
        // push / pop 目前都走 safePush → stackView.replace，上面两个已覆盖；
        // 一并设上是为了万一以后走了别的路径又变回纵向。
        sv.pushEnter = horizontalEnter
        sv.popExit = horizontalExit
        // 整体替换，别改字段：`property var` 里就地改属性不会发变更通知，
        // 读出来永远是初始的 false（害我追了一轮"转场没装上"）。
        transitionDiag = {
            installed: true,
            sameEnter: (sv.replaceEnter === horizontalEnter),
            sameExit: (sv.replaceExit === horizontalExit)
        }
    }

    /// 转场安装状态的自检出口（给 tools/transition_probe.py 读）。
    /// 为什么需要它：Transition 装没装上、装的是不是同一个对象，
    /// 从 Python 侧看全是 undefined，只能让 QML 自己回答。
    property var transitionDiag: ({ installed: false, sameEnter: false, sameExit: false })

    /// 导航栈现况（自检 / 排障用）。「切了高亮没切页面」这类问题只能这么查。
    readonly property bool navPushInProgress: navigationView.pushInProgress
    readonly property string navCurrentPage: String(navigationView.currentPage)
    readonly property string navBarPage: String(navigationView.navigationBar.currentPage)
    readonly property int navDepth: {
        var sv = findStackView()
        return sv ? sv.depth : -1
    }
    readonly property bool navBusy: {
        var sv = findStackView()
        return sv ? sv.busy : false
    }
    readonly property string navCurrentItem: {
        var sv = findStackView()
        return sv && sv.currentItem ? String(sv.currentItem.objectName) : "null"
    }

    /// 新页：从方向的反侧**整段移进来**，不做任何淡化。
    ///
    /// 用户明确要的是「旧 UI 直接移出去、新 UI 直接移进来」——
    /// 淡入淡出会让两个页面同时半透明地叠着，那种"糊在一起"的观感不对。
    /// 所以这里只动位移动画，`opacity` 用 PropertyAction 钉死在 1。
    readonly property Transition horizontalEnter: Transition {
        SequentialAnimation {
            PropertyAction { property: "slideIn"; value: 1 }
            PropertyAnimation {
                property: "slideIn"
                from: 1
                to: 0
                duration: 280
                easing.type: Easing.OutCubic
            }
        }
        PropertyAction { property: "slideOut"; value: 0 }
        PropertyAction { property: "opacity"; value: 1 }
    }

    /// 旧页：往同侧整段移出去（forward 往左、back 往右、down 往上、up 往下）。
    ///
    /// 位移方向由 PageShell.motion() 决定，这里只管把 `slideOut` 从 0 推到 1。
    /// 同样**不淡化** —— 两页交替靠干净的平移完成。
    readonly property Transition horizontalExit: Transition {
        SequentialAnimation {
            PropertyAction { property: "slideOut"; value: 0 }
            PropertyAnimation {
                property: "slideOut"
                from: 0
                to: 1
                duration: 280
                easing.type: Easing.OutCubic
            }
        }
        PropertyAction { property: "slideIn"; value: 0 }
        PropertyAction { property: "opacity"; value: 1 }
    }

    /// 在 NavigationView 里找到那个 StackView。
    ///
    /// 路径是确定的，不用遍历视觉树：
    ///     NavigationView ── alias navigationBar ──> NavigationBar
    ///                   ── stackView 属性 ─────> StackView
    /// （NavigationBar 那一行是 `stackView: stackView`，RinUI 自己把它透出来的。）
    ///
    /// ★ 之前这里是「递归 childItems 找同时有 depth/currentItem 的节点」，
    ///   结果**永远返回 null**，installHorizontalTransition() 第一行就 return 了，
    ///   横向转场根本没装上—— 而外观上却「看不出异常」，因为 RinUI 自带的
    ///   纵向转场和 SubPage 自己的淡入照常在跑，opacity 曲线完全正常。
    ///   也就是说：这套转场代码空跑了很久，是靠属性探针（tools/transition_check.py）
    ///   让 QML 自报 installed=false 才查出来的。教训是**别用启发式遍历找对象**。
    function findStackView() {
        var bar = navigationView ? navigationView.navigationBar : null
        var sv = bar ? bar.stackView : null
        if (!sv) console.warn("[settings] navigationBar.stackView 取不到，转场装不上")
        return sv || null
    }

    navigationItems: [
        {
            title: "首页",
            page: Paths.qml("pages/Home.qml"),
            icon: "ic_fluent_board_20_regular",
            position: Position.Top
        },
        {
            title: "通用",
            icon: "ic_fluent_settings_20_regular",
            page: Paths.qml("pages/General.qml")
        },
        {
            title: "灵动岛",
            icon: "ic_fluent_apps_20_regular",
            page: Paths.qml("pages/Island.qml")
        },
        {
            title: "交互",
            icon: "ic_fluent_hand_draw_20_regular",
            page: Paths.qml("pages/Advanced.qml")
        },
        {
            title: "个性化",
            icon: "ic_fluent_paint_brush_sparkle_20_regular",
            page: Paths.qml("pages/Appearance.qml")
        },
        // ★ 左侧导航只放顶层页，**不再有可展开的子项**。
        //
        //   原先「课表与提醒」「插件」带 subItems，NavigationItem 会给它们画一个
        //   下拉箭头（chevron_down）。Win11 的「设置」导航里没有这种东西：
        //   子页一律从右侧页面的入口行点进去，面包屑负责告诉你现在在哪。
        //   所以这里去掉 subItems，子页入口全部落在 Schedule.qml / Plugins.qml 里，
        //   仍可用 gotoTitle("课表管理") 直达（走 pageTable）。
        {
            title: "课表与提醒",
            icon: "ic_fluent_alert_badge_20_regular",
            page: Paths.qml("pages/Schedule.qml")
        },
        {
            title: "作业",
            icon: "ic_fluent_book_20_regular",
            page: Paths.qml("pages/Homework.qml")
        },
        {
            title: "插件",
            icon: "ic_fluent_apps_add_in_20_regular",
            page: Paths.qml("pages/Plugins.qml")
        },
        {
            title: "关于",
            icon: "ic_fluent_info_20_regular",
            page: Paths.qml("pages/About.qml"),
            position: Position.Bottom
        }
    ]
}