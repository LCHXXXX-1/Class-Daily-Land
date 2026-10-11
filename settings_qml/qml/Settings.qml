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
    width: 1180
    height: 800
    minimumWidth: 900
    minimumHeight: 620

    // 转场接管要等NavigationView 把 StackView 建出来，
    // 所以推迟一拍（见 installHorizontalTransition 的说明）。
    Component.onCompleted: Qt.callLater(installHorizontalTransition)

    /// 用于页面入口的面包屑和旧调用方的标题直达。
    readonly property var pageTable: [
        { title: "课表管理", parent: "课表与提醒", page: Paths.qml("pages/Timetable.qml") },
        { title: "假期与调休", parent: "课表与提醒", page: Paths.qml("pages/Holidays.qml") },
        { title: "值日生名单", parent: "课表与提醒", page: Paths.qml("pages/Duty.qml") },
        { title: "状态测试", parent: "课表与提醒", page: Paths.qml("pages/StatusTest.qml") },
        { title: "本地插件", parent: "插件", page: Paths.qml("pages/Plugins.qml") },
        { title: "插件设置", parent: "插件", page: Paths.qml("pages/PluginHub.qml") },
        { title: "插件市场", parent: "插件", page: Paths.qml("pages/Market.qml") },
        { title: "依赖包管理", parent: "插件", page: Paths.qml("pages/Packages.qml") }
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
        transitionDiag.installed = true
        transitionDiag.sameEnter = (sv.replaceEnter === horizontalEnter)
        transitionDiag.sameExit = (sv.replaceExit === horizontalExit)
    }

    /// 转场安装状态的自检出口（给 tools/transition_probe.py 读）。
    /// 为什么需要它：Transition 装没装上、装的是不是同一个对象，
    /// 从 Python 侧看全是 undefined，只能让 QML 自己回答。
    property var transitionDiag: ({ installed: false, sameEnter: false, sameExit: false })

    /// 新页从右侧推进来。
    ///
    /// ★ 这里动画的是 `slideIn`（SubPage 上的自定义属性），**不是 x**。
    ///   直接动画 x 无效：RinUI 的 FluentPage 在 StackView 里由布局托管，
    ///   外部写进去的 x 会被布局覆盖回0（字面常量、StackView.view.width
    ///   都试过，一律不动）。改为驱动页面自己的进度属性，再由 SubPage
    ///   把进度换算成内部 contentItem.x —— 那里的 x 是可写的。
    ///   详见 components/SubPage.qml 顶部的注释。
    readonly property Transition horizontalEnter: Transition {
        SequentialAnimation {
            PropertyAction { property: "slideIn"; value: 1 }
            PropertyAnimation {
                property: "slideIn"
                from: 1
                to: 0
                duration: 260
                easing.type: Easing.OutCubic
            }
        }
        SequentialAnimation {
            PropertyAction { property: "slideOut"; value: 0 }
            PropertyAction { property: "opacity"; value: 0 }
            PauseAnimation { duration: 60 }
            PropertyAnimation {
                property: "opacity"
                from: 0
                to: 1
                duration: 190
                easing.type: Easing.OutCubic
            }
        }
    }

    /// 旧页向左让位并淡出 —— 与新页成对，才有「推进」而不是「浮现」的感觉。
    readonly property Transition horizontalExit: Transition {
        SequentialAnimation {
            PropertyAction { property: "slideOut"; value: 0 }
            PropertyAnimation {
                property: "slideOut"
                from: 0
                to: 1
                duration: 260
                easing.type: Easing.OutCubic
            }
        }
        SequentialAnimation {
            PropertyAction { property: "opacity"; value: 1 }
            PauseAnimation { duration: 50 }
            PropertyAnimation {
                property: "opacity"
                from: 1
                to: 0
                duration: 200
                easing.type: Easing.InCubic
            }
        }
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
        {
            title: "课表与提醒",
            icon: "ic_fluent_alert_badge_20_regular",
            page: Paths.qml("pages/Schedule.qml"),
            expanded: true,
            subItems: [
                {
                    title: "课表管理",
                    page: Paths.qml("pages/Timetable.qml"),
                    icon: "ic_fluent_calendar_20_regular"
                },
                {
                    title: "假期与调休",
                    page: Paths.qml("pages/Holidays.qml"),
                    icon: "ic_fluent_weather_sunny_20_regular"
                },
                {
                    title: "值日生名单",
                    page: Paths.qml("pages/Duty.qml"),
                    icon: "ic_fluent_people_20_regular"
                },
                {
                    title: "状态测试",
                    page: Paths.qml("pages/StatusTest.qml"),
                    icon: "ic_fluent_beaker_20_regular"
                }
            ]
        },
        {
            title: "作业",
            icon: "ic_fluent_book_20_regular",
            page: Paths.qml("pages/Homework.qml")
        },
        {
            title: "插件",
            icon: "ic_fluent_apps_add_in_20_regular",
            page: Paths.qml("pages/Plugins.qml"),
            expanded: true,
            subItems: [
                {
                    title: "插件设置",
                    page: Paths.qml("pages/PluginHub.qml"),
                    icon: "ic_fluent_puzzle_piece_20_regular"
                },
                {
                    title: "插件市场",
                    page: Paths.qml("pages/Market.qml"),
                    icon: "ic_fluent_cart_20_regular"
                },
                {
                    title: "依赖包管理",
                    page: Paths.qml("pages/Packages.qml"),
                    icon: "ic_fluent_cube_20_regular"
                }
            ]
        },
        {
            title: "关于",
            icon: "ic_fluent_info_20_regular",
            page: Paths.qml("pages/About.qml"),
            position: Position.Bottom
        }
    ]
}