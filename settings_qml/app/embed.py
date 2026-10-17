"""ClassDailyLand-Py 的接入口：把 QML 设置中心做成主程序能直接用的模态窗口。

主程序侧（gui.py）只需要：

    import qml_bridge                      # Py 项目里的薄壳，负责定位本项目
    if qml_bridge.is_available():
        dlg = qml_bridge.create_dialog(self, settings=..., ...)
    # dlg 为 None 就走原生 v4 设置窗口回退

设计要点（都踩过或推演过）：

* **不塞 QWidget 容器。** RinUI 的窗口背板（Mica / Acrylic）是靠原生事件
  过滤器挂在**顶层窗口**的 HWND 上的；createWindowContainer 会把
  QQuickWindow 变成子 HWND，背板就挂不上了。所以这里保持顶层窗口，
  用 QEventLoop 模拟 QDialog.exec() 的模态语义（ApplicationModal）。
* **复用主程序的 QApplication。** SettingsApp 不建 app；RinUI 在
  import 时想设 HiDPI 策略，Qt 6 默认就是 PassThrough，晚了也无害。
* **起不来就返回 None。** 缺 RinUI / 缺 QtQuick / QML 加载失败（缺 GPU 等）
  都在这一层消化，调用方拿到 None 走原生设置窗口回退，任何一层不允许白屏。
"""
from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import QEventLoop, QObject, Qt
from PySide6.QtWidgets import QApplication

from . import paths
from .services import Services
from .window import SettingsApp

WINDOW_SIZE = (1232, 762)


def _reconfigure_stdio() -> None:
    """RinUI 启动会 print("✨ …")，GBK 控制台抛 UnicodeEncodeError 会打断建窗。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 环境不支持就算了
            pass


def is_available() -> bool:
    """QML 设置中心在当前进程里能不能起。不做任何有副作用的装配。"""
    if not (paths.QML_DIR / "Settings.qml").exists():
        print(f"[qml-settings] Settings.qml not found: {paths.QML_DIR / 'Settings.qml'}")
        return False
    try:
        import RinUI  # noqa: F401, PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"[qml-settings] RinUI is unavailable: {exc}")
        return False
    try:
        import PySide6.QtQuick  # noqa: F401, PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"[qml-settings] QtQuick is unavailable: {exc}")
        return False
    return True


def _make_callbacks(services: Services) -> None:
    """把主程序传进来的 controller / app 包装成 Config 要的两个回调。"""
    controller = getattr(services, "_controller", None)
    app = getattr(services, "_app", None)

    def apply_theme() -> None:
        try:
            import theme  # noqa: PLC0415 - 主程序的主题模块，只有嵌入时可用

            theme.apply_theme(QApplication.instance())
        except Exception:  # noqa: BLE001
            pass

    def apply_settings() -> None:
        if controller is not None:
            try:
                controller.apply_settings()
                return
            except Exception:  # noqa: BLE001
                pass
        apply_main = getattr(app, "apply_main_settings", None)
        if callable(apply_main):
            try:
                apply_main()
            except Exception:  # noqa: BLE001
                pass

    services.on_theme_changed = apply_theme
    services.on_setting_changed = apply_settings

    def data_changed(what: str) -> None:
        """作业 / 课表落盘后刷新主界面。

        为什么必须有：原生「编辑作业」「周末作息」两个对话框在自己里头
        调 `app.update_display()` / `_notify_island()`，改完主窗口立刻变。
        QML 设置中心拿不到 app 引用，不补这一手就会出现
        「在设置里加了作业，主窗口还写着暂无作业」—— 看着像功能坏了。
        """
        if what == "homework":
            update = getattr(app, "update_display", None)
            if callable(update):
                try:
                    update()
                except Exception:  # noqa: BLE001
                    pass
        # 课表 / 周末作息改了，主窗口和灵动岛都得重算（原生是 _notify_island）
        notify = getattr(app, "_notify_island", None)
        if callable(notify):
            try:
                notify()
            except Exception:  # noqa: BLE001
                pass
        elif controller is not None:
            try:
                controller.notify_island_dirty()
            except Exception:  # noqa: BLE001
                pass

    services.on_data_changed = data_changed


def create_settings_dialog(
    parent: QObject | None = None,
    *,
    settings: Any = None,
    schedule_manager: Any = None,
    duty_manager: Any = None,
    homework_manager: Any = None,
    plugin_manager: Any = None,
    controller: Any = None,
    app: Any = None,
    start_page: str | None = None,
) -> "QmlSettingsDialog | None":
    """构建模态的 QML 设置窗口；起不来返回 None（调用方走下一层回退）。"""
    _reconfigure_stdio()
    if not is_available():
        return None

    config_dir = paths.Path(settings.path).parent if settings is not None else None
    version = ""
    try:
        import about  # noqa: PLC0415 - 主程序的版本号来源

        version = str(about.get_version())
    except Exception:  # noqa: BLE001
        pass
    services = Services(
        settings=settings,
        schedule=schedule_manager,
        duty=duty_manager,
        homework=homework_manager,
        plugin_manager=plugin_manager,
        controller=controller,
        version=version,
        config_dir=config_dir,
        plugins_dir=paths.Path(plugin_manager.plugins_dir) if plugin_manager is not None else None,
        # 主程序的可写数据根就是 settings/ 的上一级（作业 / config.json 都在那）
        data_dir=config_dir.parent if config_dir is not None else None,
    )
    # controller / app 不放进 dataclass 字段（它们只用于回调），挂在私有属性上
    services._controller = controller  # noqa: SLF001 - 本模块内约定
    services._app = app                # noqa: SLF001
    _make_callbacks(services)

    try:
        qml_path = (paths.QML_DIR / "Settings.qml").resolve()
        settings_app = SettingsApp(qml_path, page=start_page, services=services)
        if settings_app.root is None:
            return None
        return QmlSettingsDialog(settings_app, parent=parent)
    except Exception as exc:  # noqa: BLE001 - 任何装配失败都走回退，不允许白屏
        print(f"[qml-settings] QML 设置中心装配失败，将回退下一层：{exc}")
        return None


class QmlSettingsDialog(QObject):
    """给 gui.py 用的适配器：形状像 QDialog（exec / showNormal / deleteLater）。

    模态语义靠 ApplicationModal + 局部事件循环实现：窗口关闭（visible 变 False）
    或应用退出时 exec 返回。
    """

    def __init__(self, settings_app: SettingsApp, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = settings_app

    # ---- gui.py 单例分支用到（QWindow 同名方法，直接代理） ----

    def showNormal(self) -> None:
        self._root().showNormal()

    def raise_(self) -> None:
        self._root().raise_()

    def activateWindow(self) -> None:
        self._root().requestActivate()

    def isVisible(self) -> bool:
        return self._root().isVisible()

    # ---- 模态 ----

    def exec(self) -> int:  # noqa: A003 - 有意对齐 QDialog.exec
        root = self._root()
        application = QApplication.instance()
        if application is None:
            raise RuntimeError("QmlSettingsDialog 需要已存在的 QApplication")

        loop = QEventLoop()

        def on_visible(visible: bool) -> None:
            if not visible:
                loop.quit()

        root.visibleChanged.connect(on_visible)
        application.aboutToQuit.connect(loop.quit)
        try:
            if not root.isVisible():
                self._app.show(*WINDOW_SIZE, modal=True)
            loop.exec()
        finally:
            try:
                root.visibleChanged.disconnect(on_visible)
            except (RuntimeError, TypeError):
                pass
        return 1  # QDialog.Accepted

    # ---- 收尾 ----

    def deleteLater(self) -> None:  # noqa: N802 - 对齐 QObject.deleteLater 的调用方写法
        try:
            if self._app is not None:
                self._app.shutdown()   # 市场 / 依赖包后台线程收尾
                root = self._app.root
                if root is not None:
                    root.close()
                    root.deleteLater()
        except RuntimeError:
            pass
        self._app = None      # 放掉全部桥对象
        super().deleteLater()

    def _root(self):
        if self._app is None or self._app.root is None:
            raise RuntimeError("QML 设置窗口已经关闭")
        return self._app.root
