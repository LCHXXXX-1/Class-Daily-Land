"""窗口装配：把 Python 侧的桥挂到 QML 引擎上，再加载 Settings.qml。

★ 两个必须记住的点（都踩过）：

1. **上下文属性要在 engine.load() 之前挂好**。QML 在加载那一刻就要对
   `navigationItems` 求值（里面要调 `Paths.qml(...)`），属性晚一步就是 null。
   而 RinUIWindow 自己在 `load()` 里就调了 `engine.load()`，所以这里先建一个
   「不加载」的窗口（`qml_path=None`），挂完属性再手动 `load()`。

2. **上下文属性必须自己持住引用**。`setContextProperty` 不接管所有权，
   写成临时对象的话 Python 侧立刻回收，QML 里读到的就是 null ——
   报错长得像「路径助手没写对」（`Cannot call method 'qml' of null`），
   实际是生命周期问题。所以下面的桥对象全部挂在 self 上。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

import RinUI

from . import paths
from .bridge import AppInfo, Config, Folders, Homework, ListStore, Plugins, ScheduleInfo
from .extra import MarketStore, PackageBridge, StatusTester, TimetableStore, UpdaterBridge
from .services import Services

# 配置里的 theme_mode → RinUI ThemeManager 的三档（注意是 Auto，不是 System）
THEME_TO_RINUI = {"system": "Auto", "light": "Light", "dark": "Dark"}

# QML 上下文属性名 → SettingsApp 实例上的属性名。
#
# ★★ 属性名**不能**和任何 QML 组件（也就是 .qml 文件名）同名！
#
#   QML 解析一个标识符时，**本地类型优先于上下文属性**。所以 pages/Homework.qml
#   里写 `Homework.items()`，`Homework` 会被解析成「它自己这个组件」而不是我们注册的
#   桥对象 —— 页面安静地拿到 undefined，列表永远是空的，**一句报错都没有**。
#   （同一批踩的还有 Plugins.qml / Schedule.qml / Timetable.qml。）
#
#   工具里的 selftest 有一条专门盯这个撞名，别再踩第二次。
CONTEXT_PROPERTIES: tuple[tuple[str, str], ...] = (
    ("Paths", "paths_helper"),
    ("Config", "config"),
    ("AppInfo", "app_info"),
    ("Folders", "folders"),
    ("PluginStore", "plugins"),
    ("HomeworkStore", "homework"),
    ("ScheduleStore", "schedule"),
    ("ListStore", "list_store"),
    # 完整版的五个新桥（名字同样避开所有 QML 组件文件名：
    # 页面里有 Timetable.qml / StatusTest.qml / Market.qml / Packages.qml，
    # 所以桥叫 TimetableStore / StatusTester / MarketStore / PackageBridge）
    ("TimetableStore", "timetable_store"),
    ("StatusTester", "status_tester"),
    ("MarketStore", "market_store"),
    ("PackageBridge", "package_bridge"),
    ("Updater", "updater"),
)


class SettingsApp:
    """一次设置窗口的装配与生命周期。

    services 为 None → 演示模式（独立 run.py / 自检）；
    services.settings 不为 None → 嵌入模式，读写穿透到主程序的真实服务。
    """

    def __init__(
        self,
        qml_path: Path,
        page: str | None = None,
        theme: str | None = None,
        services: Services | None = None,
    ) -> None:
        services = services or Services()
        if not services.embedded:
            paths.ensure_dirs()

        self.qml_path = qml_path
        self.start_page = page
        self.force_theme = theme
        self.services = services

        # 桥对象：全部持住引用（见模块 docstring 第 2 点）
        self.config = Config(
            settings=services.settings,
            schedule=services.schedule,
            on_setting_changed=services.on_setting_changed,
            on_theme_changed=services.on_theme_changed,
        )
        self.app_info = AppInfo(
            version=services.version,
            config_path=services.config_dir,
            plugins_path=services.plugins_dir,
        )
        self.folders = Folders(
            config_dir=services.config_dir,
            plugins_dir=services.plugins_dir,
            data_dir=services.data_dir,
        )
        self.plugins = Plugins(plugin_manager=services.plugin_manager,
                               settings=services.settings)
        self.homework = Homework(homework=services.homework)
        self.list_store = ListStore(duty=services.duty, schedule=services.schedule)
        self.schedule = ScheduleInfo(schedule=services.schedule)
        self.timetable_store = TimetableStore(schedule=services.schedule)
        self.status_tester = StatusTester(
            schedule=services.schedule, settings=services.settings,
            controller=services.controller)
        self.market_store = MarketStore(settings=services.settings,
                                        plugin_manager=services.plugin_manager)
        self.package_bridge = PackageBridge(settings=services.settings,
                                            plugin_manager=services.plugin_manager)
        self.updater = UpdaterBridge()
        self.paths_helper = paths.Paths()

        # 先建「不加载」的窗口，拿到引擎
        self.window = RinUI.RinUIWindow(None, shared_engine=True)
        context = self.window.engine.rootContext()
        for name, attr in CONTEXT_PROPERTIES:
            context.setContextProperty(name, getattr(self, attr))
        assert context.contextProperty("Paths") is not None

        self.window.load(self.qml_path)
        self.root = self.window.root_window

        # ★ 页面里也要能拿到「导航出口」。
        #
        #   RinUI 的 NavigationView 用 Qt.createComponent(url) 动态建页面 ——
        #   那些页面是**独立编译**的，编译期看不到 Settings.qml 里的 id，
        #   所以页面里写 `settingsWindow.openPage(...)` 拿到的是 undefined
        #   （症状：点「课表管理」那几行毫无反应，也不报错）。
        #   上下文属性是全局的，动态创建的页面一样能看见，所以把窗口本身
        #   再挂一个同名上下文属性：Settings.qml 内部 id 优先（同一个对象），
        #   其它页面走上下文属性，两条路指向同一个窗口。
        #   必须在 load() 之后设 —— root_window 这时才存在。
        try:
            self.window.engine.rootContext().setContextProperty("settingsWindow", self.root)
        except Exception:  # noqa: BLE001 - 挂不上就退回「只有外壳里的 id 能用」
            pass

    # ------------------------------------------------------------ 主题

    def apply_theme(self) -> None:
        mode = self.force_theme or self.config.get("theme_mode", "system")
        self.window.theme_manager.toggle_theme(THEME_TO_RINUI.get(mode, "Light"))
        # 云母背板：关掉设置项就明确要求 none，否则用 RinUI 自己的默认
        #（Win11 默认 mica、Win10 默认 acrylic，它内部会按系统降级）
        if not self.config.get("settings_mica", True):
            self.window.theme_manager.apply_backdrop_effect("none")

    def shutdown(self) -> None:
        """窗口关闭时调用：等市场 / 依赖包的后台线程收尾，别向已析构对象发信号。"""
        for name in ("market_store", "package_bridge"):
            bridge = getattr(self, name, None)
            if bridge is not None:
                try:
                    bridge.shutdown()
                except Exception:  # noqa: BLE001
                    pass

    def goto(self, page: str) -> bool:
        """按导航标签切页（含子项）。

        走 QML 侧的 gotoTitle()，而不是直接写 currentPage ——
        后者只改属性，NavigationView 不会真的 push 页面（加载页面的是 safePush）。
        """
        try:
            return bool(self.root.gotoTitle(page))
        except (AttributeError, TypeError):
            from PySide6.QtCore import Q_ARG, QMetaObject, Qt  # noqa: PLC0415

            QMetaObject.invokeMethod(
                self.root, "gotoTitle", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", page)
            )
            return True

    def show(self, width: int, height: int, modal: bool = False) -> None:
        self.apply_theme()
        if modal:
            # 模态必须在 show 之前设置（QWindow 的规矩）
            self.root.setModality(Qt.ApplicationModal)
        self.root.resize(width, height)
        self.root.show()
        if self.start_page:
            # 导航项是加载后才建好的，切页推迟一拍
            QTimer.singleShot(0, lambda: self.goto(self.start_page))


def main(
    qml_file: str = "qml/Settings.qml",
    page: str | None = None,
    theme: str | None = None,
    shot: str | None = None,
    size: tuple[int, int] = (1180, 800),
    wait: int = 1800,
    quiet: bool = False,
    services: Services | None = None,
) -> int:
    app = QApplication(sys.argv)

    qml_path = (paths.APP_ROOT / qml_file).resolve()
    if not qml_path.exists():
        print(f"找不到 QML：{qml_path}", file=sys.stderr)
        return 2

    settings_app = SettingsApp(qml_path, page=page, theme=theme, services=services)
    settings_app.show(*size)

    if shot:
        out = Path(shot).resolve()

        def grab() -> None:
            image = settings_app.root.grabWindow()
            if image.isNull() or image.width() == 0:
                print(f"抓到空图 {image.width()}x{image.height()}", file=sys.stderr)
                app.exit(2)
                return
            out.parent.mkdir(parents=True, exist_ok=True)
            ok = image.save(str(out))
            if not quiet:
                print(f"{'OK  ' if ok else 'FAIL'} {out}  {image.width()}x{image.height()}")
            app.exit(0 if ok else 1)

        QTimer.singleShot(wait, grab)

    return app.exec()
