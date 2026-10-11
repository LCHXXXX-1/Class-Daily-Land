import QtQuick
import QtQuick.Layouts
import RinUI
import "../components"

// 插件设置 —— 插件自己注册的设置页目录。
//
// 结构照 Windows 11 设置：一个「插件」顶层页 + 「插件设置」子页，
// 列表里每个插件一行，**点插件名字就进它的设置页**。
//
// 为什么要单独一页：插件的设置项来自各插件自己（api.add_settings_page），
// 数量与内容都不固定，塞进固定的设置页布局里既放不下也没法导航。
//
// 渲染方式：插件的 factory 返回的是**原生 QWidget**（PLUGIN_API.md 的契约），
// 常规做法是 QQuickWidget / createWindowContainer，但那两个都会把 RinUI 窗口
// 降成子窗口、Mica 背板挂不上（见 app/embed.py 的模块说明）。
// 所以这里 QML 只做目录，点进去由 PluginPages 弹原生设置对话框 ——
// 效果与 v4 原生设置中心完全一致，插件拿到的也是它熟悉的环境。
SubPage {
    // ★ 必须有 id。整页的 root.xxx 都指向它 —— 漏掉时 QML 不报错，
    //   root.pages 变成 undefined、列表空、点击也没反应，纯静默失效。
    id: root

    contentHeader: PageHeader {
        rootTitle: "设置"
        parentTitle: "插件"
        currentTitle: "插件设置"
        description: "各插件注册的设置项，点插件名字打开它的设置页"
        onRootClicked: settingsWindow.gotoTitle("首页")
        onParentClicked: settingsWindow.gotoTitle("插件")
    }

    property var pages: PluginPages.isAvailable() ? PluginPages.list() : []
    property string openError: ""

    // ★ 必须接。Python侧 openFailed 只发信号，没人接就等于没有 ——
    //   插件页加载失败时既不弹窗也不显示错误，表现为「点了没反应」。
    Connections {
        target: PluginPages
        function onOpenFailed(title, message) {
            root.openError = "「" + title + "」" + message
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 4

        InfoBar {
            Layout.fillWidth: true
            severity: PluginPages.isAvailable() ? Severity.Info : Severity.Warning
            title: PluginPages.isAvailable()
                   ? "这里只列出插件自己注册的设置页（插件启动时调用 api.add_settings_page 添加）"
                   : "插件管理器不可用"
            text: PluginPages.isAvailable()
                  ? "点插件名字会打开它的设置页；页面内容由插件自己画的原生控件，与原生版设置中心一致。"
                  : "当前是独立演示模式，没有主程序的插件管理器。"
        }

        Text {
            Layout.fillWidth: true
            visible: root.openError.length > 0
            wrapMode: Text.Wrap
            color: Theme.currentTheme.colors.systemCautionColor
            text: root.openError
        }

        Text {
            typography: Typography.BodyStrong
            text: "插件设置页（" + root.pages.length + "）"
        }

        Repeater {
            model: root.pages

            delegate: Clip {
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 64

                ClipItem {
                    anchors.fill: parent
                    iconName: modelData.icon
                    title: modelData.title
                    showArrow: modelData.hasPage

                    // 副标题：插件名 + 子页数量
                    RowLayout {
                        spacing: 8

                        Text {
                            visible: modelData.plugin.length > 0
                            color: Theme.currentTheme.colors.textSecondaryColor
                            typography: Typography.Caption
                            text: modelData.plugin
                        }

                        InfoBadge {
                            visible: modelData.children.length > 0
                            text: modelData.children.length + " 个子页"
                            severity: Severity.Info
                            solid: false
                        }
                    }

                    onActivated: {
                        if (!modelData.hasPage) {
                            root.openError = "「" + modelData.title + "」没有可显示的内容"
                            return
                        }
                        root.openError = ""
                        PluginPages.open(modelData.index)
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            Layout.margins: 28
            visible: root.pages.length === 0
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            color: Theme.currentTheme.colors.textSecondaryColor
            text: PluginPages.isAvailable()
                  ? "还没有插件注册设置页。\n插件里调用 api.add_settings_page(\"我的插件\", factory) 就会出现在这里。"
                  : "插件管理器不可用"
        }

        // ---- 已安装了哪些插件 ----
        Text {
            Layout.fillWidth: true
            Layout.topMargin: 18
            typography: Typography.BodyStrong
            text: "已安装插件"
        }

        Frame {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            padding: 0

            ClipItem {
                anchors.fill: parent
                iconName: "ic_fluent_folder_open_20_regular"
                title: "打开插件文件夹"
                showArrow: false
                onActivated: Folders.open("plugins")
            }
        }

        Repeater {
            model: PluginStore.list()

            delegate: Frame {
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 68
                padding: 0

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 14

                    IconWidget {
                        Layout.preferredWidth: 24
                        Layout.preferredHeight: 24
                        icon: modelData.ok
                              ? "ic_fluent_puzzle_piece_20_regular"
                              : "ic_fluent_warning_20_regular"
                        size: 22
                        color: modelData.ok
                               ? Theme.currentTheme.colors.primaryColor
                               : Theme.currentTheme.colors.systemCriticalColor
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        RowLayout {
                            spacing: 8
                            Text {
                                typography: Typography.Body
                                text: modelData.name
                                elide: Text.ElideRight
                            }
                            InfoBadge {
                                visible: modelData.version.length > 0
                                text: "v" + modelData.version
                                severity: Severity.Info
                                solid: false
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            color: Theme.currentTheme.colors.textSecondaryColor
                            typography: Typography.Caption
                            text: modelData.ok
                                  ? (modelData.author ? modelData.author + " · " : "") + modelData.desc
                                  : (modelData.failure || modelData.desc)
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }
    }
}