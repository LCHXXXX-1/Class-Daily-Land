"""独立运行时的全保真引导：找到 ClassDailyLand-Py，借用它的真实模块。

为什么需要这个：完整版的课表编辑 / 插件市场 / 依赖包 / 状态测试都直接
复用主程序模块（schedule / plugin_market / package_store…）。嵌入模式里
gui.py 已经把服务对象递进来了；而独立 `python run.py` 时这些模块不存在，
页面就只能显示「不可用」。

这个引导做一次目录侦察 + sys.path 注入 + **路径改接**：

1. 定位 ClassDailyLand-Py（--py-root / 环境变量 / 同级目录侦察）；
2. 在导入任何主程序模块**之前**，把 Py 项目 paths 模块里的
   CONFIG_DIR / PLUGINS_DIR / MARKET_CACHE_DIR 改接到本项目的 data/
   目录 —— 因为 StudentOnDuty / homework 是 `from paths import CONFIG_DIR`
   的导入时快照，必须先改再导；
3. 构造与主程序运行时同一批类的实例（SettingsManager / ScheduleManager /
   StudentOnDuty / HomeworkManager / PluginManager），装进 Services。

这样独立运行落盘的 name.json / config.json / schedule.json / homework.json /
plugin-repo/ 与主程序**同一个模块写出来的同一种格式**，只是位置在
本项目 data/ 下（不碰主程序的真实配置）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import paths
from .services import Services

_MODULE_NAMES = ("settings_manager", "schedule", "StudentOnDuty", "homework",
                 "plugin_manager", "plugin_market", "package_store")


def find_py_root(explicit: str | None = None) -> Path | None:
    """按「显式参数 → 环境变量 → 同级目录」找主程序项目。"""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("CDL_PY_ROOT")
    if env:
        candidates.append(Path(env))
    candidates.append(paths.APP_ROOT.parent / "ClassDailyLand-Py")
    for root in candidates:
        if (root / "settings_manager.py").is_file():
            return root
    return None


def bootstrap_services(py_root: str | None = None) -> Services | None:
    """构建全保真的 Services；找不到主程序项目返回 None（页面走不可用模式）。"""
    root = find_py_root(py_root)
    if root is None:
        return None
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # ---- 先改接主程序 paths 模块的数据目录，再导入会快照它的模块 ----
    try:
        import paths as py_paths  # noqa: PLC0415 - 主程序的 paths.py

        config_dir = str(paths.CONFIG_DIR)              # data/settings
        plugins_dir = str(paths.PLUGINS_DIR)            # data/plugins
        py_paths.CONFIG_DIR = config_dir
        py_paths.PLUGINS_DIR = plugins_dir
        py_paths.MARKET_CACHE_DIR = os.path.join(config_dir, "plugin-repo")
    except Exception:  # noqa: BLE001
        return None

    try:
        from settings_manager import SettingsManager        # noqa: E402
        from schedule import ScheduleManager                # noqa: E402
        from StudentOnDuty import StudentOnDuty             # noqa: E402
        from homework import HomeworkManager                # noqa: E402
        from plugin_manager import PluginManager            # noqa: E402
    except Exception:  # noqa: BLE001
        return None

    settings = SettingsManager(config_dir)
    schedule = ScheduleManager(config_dir)
    duty = StudentOnDuty()
    homework = HomeworkManager()
    # 只建管理器、不 load_all()：插件代码不在独立模式下执行，
    # 市场页只需要 plugins_dir 里的 plugin.json 清单
    pm = PluginManager(plugins_dir, settings=settings)

    return Services(
        settings=settings,
        schedule=schedule,
        duty=duty,
        homework=homework,
        plugin_manager=pm,
        controller=None,        # 独立模式没有灵动岛，情景演示只在嵌入模式可用
    )
