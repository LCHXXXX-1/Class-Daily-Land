"""插件设置页宿主 —— 把插件画的原生 QWidget 显示成设置里的一页。

结论先写在这里，免得后人再踩
------------------------------
插件按 `PLUGIN_API.md` 的契约返回 **QWidget**（原生控件）。要把它"放进" QML
设置窗口，能想到的三条路，前两条都试过了：

1. `QtQuick.Controls.WindowContainer`（原生子窗口）
   —— 嵌入式可行（`tools/host_probe.py` 里 parent/尺寸都对），但**定位不可靠**：
      把设置窗口挪 (160,120)，嵌入件只跟着动了 (8,-354)，直接飘到窗口外面。
      原因是它自己按 scene 坐标 + 窗口位置算绝对位置，和 RinUI 这套
      无边框窗口/背板扩展打架。所以不能用。

2. 渲染成图片 + 转发鼠标
   —— 静态页可行，但插件页里有可编辑 QComboBox（带补全）、QLineEdit、
      还有每秒刷新的 QTimer（媒体插件显示当前播放）。图片方案等于自己重造
      输入法、焦点、重绘时机，坑更深。

3. **跟着内容区走的无边框子窗**（本文件的做法）
   —— 页面仍然是原生 QWidget（活的：输入法、焦点、定时刷新全正常），
      但由 QML 把「内容区在屏幕上的矩形」喂给 `place()`，宿主把它摆过去。
      设置窗口一动，QML 的绑定重算 → 重新摆放，视觉上就是一页。
      代价：拖动窗口时跟手慢一帧（肉眼基本看不出来）。

      z 序/生命周期用 `Qt.Tool` + `setTransientParent` 管：它只会浮在设置窗口
      之上，设置窗口最小化时跟着收起来；离开这一页时 QML 调 `release()` 销毁。
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot
from PySide6.QtWidgets import (QFrame, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

# 内容列左右留白（与 PageShell 的 horizontalPadding 对齐）
MARGIN_L = 28
MARGIN_R = 28


class PluginHost(QObject):
    """承载一个插件设置页；QML 负责把内容区矩形喂给 place()。"""

    changed = Signal()          # title / error / 是否有页 变了

    def __init__(self, parent: QObject | None = None,
                 plugin_manager: Any = None, pages: Any = None) -> None:
        super().__init__(parent)
        self._pm = plugin_manager
        self._pages = pages          # pluginpages.PluginPages（目录查询）
        self._host: QWidget | None = None
        self._owner: Any = None          # 设置窗口（QWindow），做 transient parent
        self._title = ""
        self._plugin = ""
        self._error = ""
        self._theme_hooked = False
        self._scene: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    # ------------------------------------------------------------------ 属性

    @Property(str, notify=changed)
    def title(self) -> str:
        return self._title

    @Property(str, notify=changed)
    def pluginName(self) -> str:
        return self._plugin

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(bool, notify=changed)
    def ready(self) -> bool:
        return self._host is not None

    # ------------------------------------------------------------------ 查询

    def _entries(self) -> list[dict[str, Any]]:
        if self._pages is not None:
            return self._pages._entries()  # noqa: SLF001 - 同项目内部约定
        if self._pm is None:
            return []
        try:
            return list(self._pm.get_settings_pages())
        except Exception:  # noqa: BLE001
            return []

    def _entry_for(self, plugin_dir: str) -> dict[str, Any] | None:
        if self._pages is not None:
            return self._pages.entry_for(plugin_dir)
        target = str(plugin_dir or "").strip()
        if not target:
            return None
        for entry in self._entries():
            if str(entry.get("name", "")) == target:
                return entry
        return None

    @Slot(str, result=bool)
    def hasPage(self, plugin_dir: str) -> bool:
        entry = self._entry_for(plugin_dir)
        return bool(entry) and callable(entry.get("factory"))

    @Slot(result=bool)
    def isAvailable(self) -> bool:
        return self._pm is not None

    def setOwnerWindow(self, window: Any) -> None:
        """设置窗口建好之后回填：做 transient parent（z 序/最小化联动），
        并订阅它的位移与尺寸变化 —— 原生页得跟着走。"""
        self._owner = window
        if window is None:
            return
        for sig in ("xChanged", "yChanged", "widthChanged", "heightChanged"):
            try:
                getattr(window, sig).connect(self._on_owner_moved)
            except Exception:  # noqa: BLE001 - 没有这个信号就算了
                pass

    def _on_owner_moved(self, *_args) -> None:
        self._apply_geometry()

    # ------------------------------------------------------------------ 装载

    @Slot(str, result=bool)
    def prepare(self, plugin_dir: str) -> bool:
        """建好插件页（先不显示，等 place() 给坐标）。"""
        self.release()
        if self._pm is None:
            self._error = "插件管理器不可用（独立演示模式）"
            self.changed.emit()
            return False

        entry = self._entry_for(plugin_dir)
        if entry is None:
            self._error = "这个插件没有注册设置页"
            self.changed.emit()
            return False
        factory = entry.get("factory")
        if not callable(factory):
            self._error = "插件没有提供可显示的内容"
            self.changed.emit()
            return False

        try:
            content = factory(entry.get("api"))
        except Exception as exc:  # noqa: BLE001 - 插件自己的错，如实显示
            self._error = f"插件设置页加载失败：{exc}"
            self.changed.emit()
            return False
        if content is None:
            self._error = "插件没有返回任何设置内容"
            self.changed.emit()
            return False

        host = self._wrap(content)
        # 无边框工具窗：没有标题栏、不进任务栏，能接键盘焦点（输入框要用）
        host.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint
                            | Qt.NoDropShadowWindowHint)

        self._host = host
        self._title = str(entry.get("title") or "插件设置")
        self._plugin = str(entry.get("name") or "")
        self._error = ""
        self._apply_theme()
        self.changed.emit()
        return True

    def _wrap(self, content: QWidget) -> QWidget:
        """套一层带留白的容器 + 滚动区。

        样式在这里统一给：`PLUGIN_API.md` 要求插件不要自设颜色、交给宿主主题，
        所以把主程序的 `theme.dialog_qss()` 铺上去，插件页里的 QLabel /
        QComboBox / QCheckBox 会自动跟着深浅色走。
        """
        host = QWidget()
        host.setObjectName("pluginHost")
        host.setAutoFillBackground(True)

        lay = QVBoxLayout(host)
        lay.setContentsMargins(MARGIN_L, 0, MARGIN_R, 0)
        lay.setSpacing(0)

        scroll = QScrollArea(host)
        scroll.setObjectName("pluginScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        scroll.setWidget(content)
        lay.addWidget(scroll, 1)
        return host

    # ------------------------------------------------------------------ 摆放

    @Slot(float, float, float, float)
    def placeScene(self, x: float, y: float, w: float, h: float) -> None:
        """QML 侧给**场景坐标**（窗口内部的相对位置），这里加上窗口位置换成屏幕坐标。

        为什么不让 QML 直接 mapToGlobal：窗口一移动，`mapToGlobal` 的结果会变，
        但 QML 的绑定**不会因此重算**（它不知道窗口挪了），原生页就会掉队。
        拆开之后，窗口移动由 `_owner` 的 xChanged/yChanged 触发，稳定可靠。
        """
        self._scene = (float(x), float(y), float(w), float(h))
        self._apply_geometry()

    def _apply_geometry(self) -> None:
        host = self._host
        if host is None:
            return
        x, y, w, h = self._scene
        if w < 40 or h < 40:
            # 页面还没量出尺寸 / 正在切走，先别显示，免得闪一下
            if host.isVisible():
                host.hide()
            return
        ox = oy = 0
        if self._owner is not None:
            try:
                pos = self._owner.position()
                ox, oy = pos.x(), pos.y()
            except (RuntimeError, AttributeError):
                pass
        host.setGeometry(int(ox + x), int(oy + y), int(w), int(h))
        if not host.isVisible():
            host.show()
            self._adopt_owner()

    @Property("QVariant", constant=True)
    def lastArea(self) -> list[float]:
        """最近一次 QML 喂进来的场景矩形（排障用）。"""
        return list(self._scene)

    def _adopt_owner(self) -> None:
        """挂成设置窗口的附属窗：只会浮在它上面，跟着它最小化。"""
        host = self._host
        if host is None or self._owner is None:
            return
        handle = host.windowHandle()
        if handle is None:
            return
        try:
            handle.setTransientParent(self._owner)
        except Exception:  # noqa: BLE001 - 平台不支持就算了，不影响功能
            pass

    @Slot()
    def conceal(self) -> None:
        """离开这一页时先藏起来（不销毁，回来还能复用）。"""
        if self._host is not None and self._host.isVisible():
            self._host.hide()

    # ------------------------------------------------------------------ 主题

    def _apply_theme(self) -> None:
        if self._host is None:
            return
        try:
            import theme  # noqa: PLC0415 - 只有嵌在主程序里才有

            bg = theme.color("window_bg")
            qss = theme.dialog_qss() + f"""
QWidget#pluginHost {{ background: {bg}; }}
QScrollArea#pluginScroll {{ background: {bg}; border: none; }}
QScrollArea#pluginScroll > QWidget > QWidget {{ background: {bg}; }}
"""
            self._host.setStyleSheet(qss)
        except Exception:  # noqa: BLE001 - 独立模式下没有主题模块，用系统默认
            pass

        if not self._theme_hooked:
            try:
                import theme  # noqa: PLC0415

                theme.theme_changed_connect(self._apply_theme)
                self._theme_hooked = True
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ 释放

    @Slot()
    def release(self) -> None:
        """页面离开 / 窗口关闭时调用：销毁原生页，别在背后留一个空窗。"""
        host = self._host
        self._host = None
        self._title = ""
        self._plugin = ""
        self._error = ""
        if host is not None:
            try:
                host.hide()
                host.setParent(None)
                host.deleteLater()
            except RuntimeError:
                pass
        self.changed.emit()
