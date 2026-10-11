"""嵌入 ClassDailyLand-Py 时传进来的服务包。

所有字段都可以为 None —— window.py / bridge.py 按字段是否为 None
决定走「嵌入模式」还是「演示模式」。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Services:
    """主程序注入的真实服务（对应 web_settings.WebSettingsDialog 的参数）。"""

    settings: Any = None            # settings_manager.SettingsManager
    schedule: Any = None            # schedule.ScheduleManager
    duty: Any = None                # StudentOnDuty.StudentOnDuty
    homework: Any = None            # homework.HomeworkManager
    plugin_manager: Any = None      # plugin_manager.PluginManager
    controller: Any = None          # controller.Controller（情景演示要驱动真实灵动岛）

    # 展示信息 / 目录覆盖（不给就用 QML 项目自己的）
    version: str = ""               # about.get_version()
    config_dir: Path | None = None  # 主程序 settings/ 目录
    plugins_dir: Path | None = None
    data_dir: Path | None = None

    # 设置变化后的回调（让主窗 / 灵动岛 / 主题跟上，语义同 web_settings）
    on_setting_changed: Callable[[], None] | None = None
    on_theme_changed: Callable[[], None] | None = None

    @property
    def embedded(self) -> bool:
        return self.settings is not None
