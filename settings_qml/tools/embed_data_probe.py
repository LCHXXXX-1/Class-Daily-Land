"""接入口探针：走 gui.py 的真实装配链，确认改数据后主窗口会被通知。

    python tools/embed_data_probe.py

page_probe 验的是页面逻辑；这一支验的是 **embed.py 有没有把
on_data_changed 接到桥对象上** —— 少了这一环，设置里改完作业，
主窗口还是「暂无作业」。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PROJ))

TMP = Path(tempfile.mkdtemp(prefix="cdlprobe-"))
shutil.copytree(PROJ / "settings", TMP / "settings", dirs_exist_ok=True)
os.environ["CDL_DATA_ROOT"] = str(TMP)


class FakeApp:
    """替身主窗口：只记录「有没有人叫我刷新」。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def update_display(self) -> None:
        self.calls.append("update_display")

    def _notify_island(self) -> None:
        self.calls.append("_notify_island")


def main() -> int:
    import paths as py_paths

    py_paths.CONFIG_DIR = str(TMP / "settings")
    py_paths.PLUGINS_DIR = str(PROJ / "plugins")
    py_paths.MARKET_CACHE_DIR = str(TMP / "settings" / "plugin-repo")

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from settings_manager import SettingsManager
    from schedule import ScheduleManager
    from StudentOnDuty import StudentOnDuty
    from homework import HomeworkManager
    import plugin_manager as pm_mod
    import qml_bridge

    app = QApplication(sys.argv[:1])
    fake = FakeApp()
    if not qml_bridge.is_available():
        print("QML 设置中心不可用")
        return 1

    dlg = qml_bridge.create_dialog(
        None,
        settings=SettingsManager(str(TMP / "settings")),
        schedule_manager=ScheduleManager(str(TMP / "settings")),
        duty_manager=StudentOnDuty(),
        homework_manager=HomeworkManager(),
        plugin_manager=pm_mod.PluginManager(str(PROJ / "plugins")),
        app=fake,
        start_page="作业",
    )
    if dlg is None:
        print("create_dialog 返回 None")
        return 1
    dlg._app.show(1232, 762)          # noqa: SLF001 - 探针要看内部装配
    settings_app = dlg._app           # noqa: SLF001

    ok = True

    def step() -> None:
        nonlocal ok
        print("作业桥接了回调:", settings_app.homework._on_changed is not None)
        print("课表桥接了回调:", settings_app.timetable_store._on_changed is not None)
        ok = ok and settings_app.homework._on_changed is not None
        ok = ok and settings_app.timetable_store._on_changed is not None

        settings_app.homework.add("语文", "背诵《赤壁赋》", "")
        print("加了作业后主窗口收到:", fake.calls)
        ok = ok and "update_display" in fake.calls

        settings_app.timetable_store.saveWeekend("12:00", [], ["语文"])
        print("存了周末后主窗口收到:", fake.calls)
        ok = ok and "_notify_island" in fake.calls

        print("结果:", "PASS" if ok else "FAIL")
        app.exit(0 if ok else 1)

    QTimer.singleShot(2600, step)
    QTimer.singleShot(20000, lambda: app.exit(9))
    code = app.exec()
    shutil.rmtree(TMP, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
