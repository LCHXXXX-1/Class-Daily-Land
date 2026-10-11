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

    /// 用于页面入口的面包屑和旧调用方的标题直达。
    readonly property var pageTable: [
        { title: "课表管理", parent: "课表与提醒", page: Paths.qml("pages/Timetable.qml") },
        { title: "假期与调休", parent: "课表与提醒", page: Paths.qml("pages/Holidays.qml") },
        { title: "值日生名单", parent: "课表与提醒", page: Paths.qml("pages/Duty.qml") },
        { title: "状态测试", parent: "课表与提醒", page: Paths.qml("pages/StatusTest.qml") },
        { title: "本地插件", parent: "插件", page: Paths.qml("pages/Plugins.qml") },
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