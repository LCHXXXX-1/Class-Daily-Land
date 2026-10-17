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

    # 业务数据（作业 / 课表）落盘后的回调。参数是来源：
    #   "homework" → 主窗口要重排作业列表
    #   "schedule" → 主窗口与灵动岛都要重算「今天上什么课」
    # 原生界面里这一步是每个对话框自己调 app.update_display() /
    # _notify_island() 做的；QML 侧没有 app 引用，只能由宿主回填。
    on_data_changed: Callable[[str], None] | None = None

    @property
    def embedded(self) -> bool:
        return self.settings is not None
