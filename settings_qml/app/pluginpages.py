"""插件设置页桥 —— 把插件注册的原生设置页接进 QML 设置中心。

背景
----
插件通过 `api.add_settings_page(title, factory, icon=..., children=[...])`
注册设置页，`factory(api)` 返回一个 **QWidget**（原生控件），这是
`PLUGIN_API.md` 定的契约，几百个在野插件都这么写，不能要求插件改。

而设置中心这一版是 QML（RinUI）。要在 QML 页面里显示一个原生 QWidget，
常规做法是 `QQuickWidget` 或 `createWindowContainer` —— 但这两个都会把
QML 窗口从顶层降成子窗口，**RinUI 的 Mica 背板就挂不上了**
（见 embed.py 模块 docstring 第1 点）。

所以这里选第三条路：**插件页在原生子对话框里打开**。
QML 侧只负责「插件管理」目录页与插件列表（这部分是纯界面，好看），
点某个插件就弹出它的原生设置页 —— 插件拿到的是它熟悉的环境，
效果与 v4 原生设置中心完全一致，且不破坏背板。

对外接口
--------
    PluginPages.list()            → 有设置页的插件目录（含子页）
    PluginPages.open(index)       → 打开第 index 个插件页的设置对话框
    PluginPages.openChild(index, childIndex)
    PluginPages.count()           → 设置页总数（QML 做空态提示用）
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QScrollArea, QVBoxLayout, QWidget

# 插件可以给的图标名 → QML 用的 Fluent 图标名。
# 插件侧的图标是 emoji 或内置矢量名（见 plugin_manager.add_settings_page），
# 这里做一次映射，让QML 目录能显示得像样的图标而不是方框。
_ICON_MAP = {
    "gear": "ic_fluent_options_20_regular",
    "palette": "ic_fluent_paint_brush_sparkle_20_regular",
    "island": "ic_fluent_apps_20_regular",
    "calendar": "ic_fluent_calendar_20_regular",
    "market": "ic_fluent_cart_20_regular",
    "box": "ic_fluent_cube_20_regular",
    "wrench": "ic_fluent_build_20_regular",
    "plugin": "ic_fluent_puzzle_piece_20_regular",
    "info": "ic_fluent_info_20_regular",
    "book": "ic_fluent_book_20_regular",
    "pencil": "ic_fluent_edit_20_regular",
    "list": "ic_fluent_list_20_regular",
    "people": "ic_fluent_people_20_regular",
    "sun": "ic_fluent_weather_sunny_20_regular",
    "play": "ic_fluent_play_20_regular",
    "clock": "ic_fluent_clock_20_regular",
    "back": "ic_fluent_arrow_left_20_regular",
}
_DEFAULT_ICON = "ic_fluent_puzzle_piece_20_regular"


def _map_icon(raw: Any) -> str:
    """插件给的图标（emoji / 内置名）→ Fluent 图标名；认不出就用默认的。"""
    name = str(raw or "").strip()
    return _ICON_MAP.get(name, _DEFAULT_ICON)


class PluginPages(QObject):
    """列出插件注册的设置页，并在原生对话框里打开它们。"""

    openFailed = Signal(str, str)   # (插件名, 原因)

    def __init__(self, parent: QObject | None = None,
                 plugin_manager: Any = None, parent_window: Any = None) -> None:
        super().__init__(parent)
        self._pm = plugin_manager
        # RinUI 窗口是 QWindow，用它做对话框的 parent 才有正确的模态归属
        self._parent_window = parent_window

    # ------------------------------------------------------------------ 列表

    def setParentWindow(self, window: Any) -> None:
        """设置窗口load 完之后回填顶层窗口（弹插件设置页时要当父窗口）。"""
        self._parent_window = window

    def _entries(self) -> list[dict[str, Any]]:
        """取插件管理器登记的设置页；出问题时如实返回空列表。"""
        if self._pm is None:
            return []
        try:
            getter = getattr(self._pm, "get_settings_pages", None)
            return list(getter()) if callable(getter) else []
        except Exception:  # noqa: BLE001 - 插件页出问题不该拖垮设置中心
            return []

    @Slot(result=bool)
    def isAvailable(self) -> bool:
        return self._pm is not None

    @Slot(result=int)
    def count(self) -> int:
        return len(self._entries())

    @Slot(result="QVariantList")
    def list(self) -> list[dict[str, Any]]:  # noqa: A003 - 与其它桥的 API 对齐
        """插件设置页目录。子页拍平成 children 数组，QML 侧只渲染一层。"""
        result: list[dict[str, Any]] = []
        for entry in self._entries():
            children = []
            for child in (entry.get("children") or ()):
                if not isinstance(child, dict):
                    continue
                children.append({
                    "title": str(child.get("title", "子页面")),
                    "icon": _map_icon(child.get("icon")),
                    "hasPage": callable(child.get("factory")),
                })
            factory = entry.get("factory")
            result.append({
                # index 是打开时用的句柄：list() 的顺序与 _entries() 一致
                "index": len(result),
                "plugin": str(entry.get("name", "")),
                "title": str(entry.get("title", "插件设置")),
                "icon": _map_icon(entry.get("icon")),
                "hasPage": callable(factory),
                "children": children,
            })
        return result

    # ------------------------------------------------------------------ 打开

    @Slot(int, result=bool)
    def open(self, index: int) -> bool:  # noqa: A003
        """打开第 index 个插件的设置页（模态）。"""
        entries = self._entries()
        if not (0 <= int(index) < len(entries)):
            return False
        return self._show(entries[int(index)], None)

    @Slot(int, int, result=bool)
    def openChild(self, index: int, child_index: int) -> bool:
        """打开某插件的第 child_index 个子页。子页的 api 用父插件的（见 v4）。"""
        entries = self._entries()
        if not (0 <= int(index) < len(entries)):
            return False
        entry = entries[int(index)]
        children = entry.get("children") or ()
        if not (0 <= int(child_index) < len(children)):
            return False
        return self._show(entry, children[int(child_index)])

    def _show(self, entry: dict[str, Any], child: dict[str, Any] | None) -> bool:
        """把factory 产出的 QWidget 装进一个滚动对话框并模态弹出。"""
        factory = (child or entry).get("factory")
        if not callable(factory):
            self.openFailed.emit(str(entry.get("title", "插件设置")),
                                 "这个页面没有可显示的内容")
            return False

        plugin_name = str(entry.get("name", ""))
        title = str((child or entry).get("title") or entry.get("title") or "插件设置")
        try:
            content = factory(entry.get("api"))
        except Exception as exc:  # noqa: BLE001 - 插件自己的错，如实显示
            self.openFailed.emit(title, f"插件设置加载失败：{exc}")
            return False

        if content is None:
            self.openFailed.emit(title, "插件没有返回任何设置内容")
            return False

        try:
            self._present(title, content, plugin_name)
        except Exception as exc:  # noqa: BLE001
            self.openFailed.emit(title, f"打开失败：{exc}")
            return False
        return True

    def _present(self, title: str, content: QWidget, plugin_name: str) -> None:
        """套一层滚动区 + 关闭按钮，避免插件页内容过高时显示不全。"""
        parent = self._parent_window
        dlg = QDialog(parent)
        dlg.setWindowTitle(f"{title} · {plugin_name}" if plugin_name else title)
        dlg.setModal(True)
        dlg.resize(560, 520)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content.setParent(scroll)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        if content.layout() is None:
            # 插件返回的是裸控件（如 QLabel），给个默认布局免得贴边
            holder = QWidget(scroll)
            row = QVBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(content)
            scroll.setWidget(holder)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)

        dlg.exec()
        # 对话框关掉后顺手清掉临时父子关系，让插件页能安全地被重建
        try:
            content.setParent(None)
            content.deleteLater()
        except Exception:  # noqa: BLE001
            pass
        dlg.deleteLater()