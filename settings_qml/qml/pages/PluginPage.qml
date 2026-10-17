import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RinUI
import "../components"

// 插件设置 —— 把插件画的原生设置页显示成设置窗口里的**一页**，不再弹新窗口。
//
// 承载方式：原生无边框工具窗 + 由这里精确喂坐标（不是 WindowContainer，
// 它的定位在这套窗口上不可靠；也不是截图转发，插件页里有输入框和每秒刷新）。
// 详见 app/pluginhome.py 的模块说明。
//
// 两个时序细节（不做就会露馅）：
//   · 进入：横向转场要 260ms，原生页不会跟着滑。所以先等转场结束再摆上去，
//     期间显示占位卡片 —— 看着像"内容加载中"，比一个不动的块强。
//   · 离开：`StackView.status` 变 Deactivating 时立刻收起原生页，
//     否则它会盖在正在滑走的旧页面上。
SubPage {
    id: root

    contentHeader: PageHeader {
        rootTitle: "设置"
        parentTitle: "插件管理"
        currentTitle: PluginHost.title.length > 0 ? PluginHost.title : "插件设置"
        description: PluginHost.pluginName.length > 0
                     ? "由插件 " + PluginHost.pluginName + " 自己绘制"
                     : ""
        onRootClicked: settingsWindow.gotoTitle("首页")
        onParentClicked: settingsWindow.gotoTitle("插件管理")
    }

    // 空槽：高度 = 页面高 -（FluentPage 标题区 80 + 面包屑约 54 + 间距 46）
    Item {
        id: slot
        Layout.fillWidth: true
        Layout.preferredHeight: Math.max(240, root.height - 190)

        /// 转场跑完之前不摆原生页
        property bool mounted: false

        /// 把槽的**场景坐标**交给宿主（它自己加上窗口位置换成屏幕坐标）。
        /// 场景坐标不含窗口位移，窗口怎么移动这里都不用重算 ——
        /// 窗口那边由 PluginHost 订阅 x/y/width/height 变化来跟。
        function feed() {
            if (!mounted) return
            var p = slot.mapToItem(null, 0, 0)
            PluginHost.placeScene(p.x, p.y, slot.width, slot.height)
        }

        onWidthChanged: feed()
        onHeightChanged: feed()
        Component.onCompleted: mountTimer.restart()

        // 横向转场 260ms，多留 60ms 余量
        Timer {
            id: mountTimer
            interval: 320
            onTriggered: {
                slot.mounted = true
                slot.feed()
            }
        }

        // 布局在一两帧内还会再动（面包屑、错峰进场动画），短定时器收尾。
        // 多喂几次没有副作用 —— placeScene 只是 setGeometry。
        Timer {
            interval: 150
            repeat: true
            running: slot.mounted
            onTriggered: slot.feed()
        }

        // 原生页还没建好 / 建失败时的占位（建好后原生窗口会盖在上面）
        Rectangle {
            anchors.fill: parent
            visible: !PluginHost.ready
            radius: Theme.currentTheme.appearance.smallRadius
            color: Theme.currentTheme.colors.cardColor
            border.width: 1
            border.color: Theme.currentTheme.colors.cardBorderColor

            IconWidget {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top
                anchors.topMargin: 56
                icon: "ic_fluent_puzzle_piece_20_regular"
                size: 32
                opacity: 0.5
            }

            Text {
                anchors.top: parent.top
                anchors.topMargin: 104
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 24
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                color: Theme.currentTheme.colors.textSecondaryColor
                text: PluginHost.error.length > 0
                      ? PluginHost.error
                      : "正在载入插件设置页…"
            }
        }
    }

    // 一开始退化就收起原生页（此时页面还在滑走，留着会露馅）
    StackView.onStatusChanged: {
        if (StackView.status === StackView.Deactivating) {
            slot.mounted = false
            PluginHost.conceal()
        }
    }

    // 真正的销毁：把原生页一起收掉，别在背后留一个空窗
    Component.onDestruction: {
        PluginHost.conceal()
        PluginHost.release()
    }
}
