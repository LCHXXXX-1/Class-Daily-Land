"""插件设置页目录 —— 只负责「有哪些插件注册了设置页」「它们叫什么」。

展示由 `pluginhome.PluginHost` 负责（把原生 QWidget 摆进设置窗口的内容区）。

历史
----
这里原本还有一个 `_present()`：把插件页塞进一个 **QDialog** 弹出来。功能可用，
但用户看到的是「设置里点一下，蹦出另一个窗口」，和系统设置那种右侧换页差得远，
已经废弃。顺带修掉的老 bug：`_present()` 曾把 `RinUIWindow.root_window`
（QWindow）当 QDialog 的父窗口传，PySide6 直接抛 TypeError，被 except 吞掉后
表现为「点了插件没反应」。
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Slot

# 插件可以给的图标名 → QML 用的 Fluent 图标名。
# 插件侧的图标是 emoji 或内置名（见 plugin_manager.add_settings_page），
# 这里做一次映射，让 QML 目录能显示得像样的图标而不是方框。
# 名字都必须在 RinUI 的 FluentSystemIcons 索引里（写错会静默渲染成乱码）。
_ICON_MAP = {
    # 内置名
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
    # emoji（插件里最常见的那几个）
    "🎵": "ic_fluent_music_note_2_20_regular",
    "🎶": "ic_fluent_music_note_2_20_regular",
    "🔊": "ic_fluent_sound_source_20_regular",
    "🔈": "ic_fluent_sound_source_20_regular",
    "🎧": "ic_fluent_headphones_sound_wave_20_regular",
    "⚠️": "ic_fluent_alert_20_regular",
    "⚠": "ic_fluent_alert_20_regular",
    "🚨": "ic_fluent_alert_urgent_20_regular",
    "🔔": "ic_fluent_alert_20_regular",
    "🌍": "ic_fluent_globe_20_regular",
    "🌐": "ic_fluent_globe_20_regular",
    "🛰️": "ic_fluent_globe_20_regular",
    "🗺️": "ic_fluent_map_20_regular",
    "📍": "ic_fluent_map_pin_20_regular",
    "🧩": "ic_fluent_puzzle_piece_20_regular",
    "⚙️": "ic_fluent_options_20_regular",
    "🔧": "ic_fluent_build_20_regular",
    "🎨": "ic_fluent_paint_brush_sparkle_20_regular",
    "📚": "ic_fluent_book_20_regular",
    "📅": "ic_fluent_calendar_20_regular",
    "👥": "ic_fluent_people_20_regular",
    "📦": "ic_fluent_cube_20_regular",
    "🛒": "ic_fluent_cart_20_regular",
    "☀️": "ic_fluent_weather_sunny_20_regular",
    "⏰": "ic_fluent_clock_20_regular",
    "🏫": "ic_fluent_building_20_regular",
}
_DEFAULT_ICON = "ic_fluent_puzzle_piece_20_regular"


def _map_icon(raw: Any) -> str:
    """插件给的图标（emoji / 内置名）→ Fluent 图标名；认不出就用默认的。"""
    name = str(raw or "").strip()
    return _ICON_MAP.get(name, _DEFAULT_ICON)


class PluginPages(QObject):
    """插件注册的设置页目录（含三级子页），供 QML 列表与 PluginHost 查询。"""

    def __init__(self, parent: QObject | None = None,
                 plugin_manager: Any = None) -> None:
        super().__init__(parent)
        self._pm = plugin_manager

    def _entries(self) -> list[dict[str, Any]]:
        """取插件管理器登记的设置页；出问题时如实返回空列表。"""
        if self._pm is None:
            return []
        try:
            getter = getattr(self._pm, "get_settings_pages", None)
            return list(getter()) if callable(getter) else []
        except Exception:  # noqa: BLE001 - 插件页出问题不该拖垮设置中心
            return []

    def entry_for(self, plugin_dir: str) -> dict[str, Any] | None:
        """按插件目录名找登记项（PluginHost 用它拿 factory / api）。"""
        target = str(plugin_dir or "").strip()
        if not target:
            return None
        for entry in self._entries():
            if str(entry.get("name", "")) == target:
                return entry
        return None

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
                "plugin": str(entry.get("name", "")),
                "title": str(entry.get("title", "插件设置")),
                "icon": _map_icon(entry.get("icon")),
                "hasPage": callable(factory),
                "children": children,
            })
        return result

    @Slot(str, result=bool)
    def hasPageFor(self, plugin_dir: str) -> bool:
        """这个插件有没有注册设置页（插件管理页据此决定箭头与可点状态）。"""
        entry = self.entry_for(plugin_dir)
        return bool(entry) and callable(entry.get("factory"))
