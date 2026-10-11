"""设置项清单 —— 键名、默认值、类型与取值范围的**单一事实来源**。

键名沿用 AppSettings 的 snake_case，与两个项目现有的 settings/settings.json 一致，
所以这份配置能跟 .NET 版 / 现有 Python 版互读。

QML 侧只负责界面文案（标题、说明、图标），数值约束全部来自这里：
`Config.set()` 会按 schema 做类型校验与范围夹取，越界值当场夹回 ——
这一点是照源项目的教训做的（`set_time_offset_seconds` 漏了夹取，
一份越界值静默生效，导致课表编辑器与灵动岛差了 4 小时 24 分）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Field:
    key: str
    default: Any
    kind: str = "bool"          # bool | int | float | str | list
    low: float | None = None
    high: float | None = None
    step: float | None = None

    def coerce(self, value: Any) -> Any:
        """按 kind 校验并夹取；类型不符就返回默认值（不让一个坏值带崩整份配置）。"""
        try:
            if self.kind == "bool":
                return bool(value)
            if self.kind == "int":
                return self._clamp(int(round(float(value))))
            if self.kind == "float":
                return self._clamp(float(value))
            if self.kind == "str":
                return str(value)
            if self.kind == "list":
                return list(value) if isinstance(value, (list, tuple)) else list(self.default)
        except (TypeError, ValueError):
            return self.default
        return self.default

    def _clamp(self, number: float) -> float:
        if self.low is not None:
            number = max(self.low, number)
        if self.high is not None:
            number = min(self.high, number)
        return number

    def is_out_of_range(self, value: Any) -> bool:
        if self.kind not in ("int", "float"):
            return False
        try:
            number = float(value)
        except (TypeError, ValueError):
            return True
        if self.low is not None and number < self.low:
            return True
        if self.high is not None and number > self.high:
            return True
        return False


FIELDS: tuple[Field, ...] = (
    # ---------------------------------------------------------- 通用 · 主窗口
    # 注意：theme_mode / main_width_ratio 的默认值与 ClassDailyLand-Py 的
    # settings_manager.DEFAULTS 对齐（那才是两端共用的契约）；嵌入主程序时
    # 真实默认值本来就来自 SettingsManager，这里的值只影响独立演示模式。
    Field("show_main_window", True),
    Field("main_width_ratio", 0.25, "float", 0.15, 0.50),
    Field("main_opacity", 1.0, "float", 0.0, 1.0),
    Field("main_font_size", 14, "int", 8, 30, 1),
    # ---------------------------------------------------------- 通用 · 作业滚动
    Field("main_auto_scroll", True),
    Field("main_scroll_interval", 50, "int", 20, 200, 1),
    Field("main_scroll_step", 1, "int", 1, 10, 1),
    Field("main_scroll_pause", 60, "int", 0, 200, 1),
    # ---------------------------------------------------------- 通用 · 启动与更新
    Field("check_update_on_start", True),
    Field("block_update_on_source", True),
    # ---------------------------------------------------------- 外观
    Field("theme_mode", "system", "str"),
    Field("settings_mica", True),
    Field("anim_fade_window", True),
    Field("anim_fade_panel", True),
    Field("anim_fade_text", True),
    Field("anim_duration", 320, "int", 100, 2000, 1),
    # ---------------------------------------------------------- 灵动岛 · 主岛
    Field("show_island", True),
    Field("island_top_margin", 6, "int", 0, 100, 1),
    Field("island_alert_width", 300, "int", 200, 800, 1),
    Field("island_alert_hold_ms", 600, "int", 100, 5000, 1),
    Field("island_hide_on_fullscreen", True),
    Field("island_show_wakeup_anim", True),
    # ---------------------------------------------------------- 灵动岛 · 副岛
    Field("show_sub_island", True),
    Field("sub_island_collapsed", False),
    Field("sub_island_auto_collapse_sec", 5, "int", 0, 120, 1),
    # ---------------------------------------------------------- 课表与提醒
    Field("island_countdown_sec", 60, "int", 5, 600, 1),
    Field("schedule_advance_minutes", 2, "int", 0, 60, 1),
    Field("schedule_time_offset_seconds", 0, "int", -1800, 1800, 1),
    # ---------------------------------------------------------- 作业 / 插件
    # ↓ 这两个键是 QML 演示版自有的，**不在**主程序的 settings_manager.DEFAULTS 里。
    #   嵌入主程序时 Config.set 会拒绝它们（isManaged() 返回 False，界面上如实标出），
    #   不会把演示专属键写进两端共用的 settings.json。
    Field("homework_auto_scroll", True),
    # ---------------------------------------------------------- 插件
    Field("market_source", "official", "str"),
    Field("packages_source", "gitee", "str"),
    Field("packages_base_url", "", "str"),
    Field("plugins_auto_check_update", True),
    # ---------------------------------------------------------- 高级
    Field("disabled_plugins", [], "list"),
)

BY_KEY: dict[str, Field] = {f.key: f for f in FIELDS}


def defaults() -> dict[str, Any]:
    return {f.key: f.default for f in FIELDS}


def missing_defaults() -> list[str]:
    """自检用：schema 里默认值的类型是否与 kind 相符。"""
    problems: list[str] = []
    for f in FIELDS:
        coerced = f.coerce(f.default)
        if coerced != f.default:
            problems.append(f"{f.key}: default {f.default!r} → coerced {coerced!r}")
    return problems
