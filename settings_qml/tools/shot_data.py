"""带数据截两张图：作业页（有分组列表）与周末作息页（有下午节次）。

    python tools/shot_data.py

数据放在临时目录，不碰用户的真实配置。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PROJ))

TMP = Path(tempfile.mkdtemp(prefix="cdlshot-"))
shutil.copytree(PROJ / "settings", TMP / "settings", dirs_exist_ok=True)
os.environ["CDL_DATA_ROOT"] = str(TMP)


def seed() -> None:
    cfg = TMP / "settings"
    (cfg / "homework.json").write_text(json.dumps([
        {"subject": "数学", "content": "练习册 P12 第 3、4 题，明天讲评", "date": "2026-10-20"},
        {"subject": "数学", "content": "订正月考卷（第 II 卷）", "date": "2026-10-20"},
        {"subject": "语文", "content": "背诵《赤壁赋》全文", "date": ""},
        {"subject": "英语", "content": "Unit 4 单词抄写一遍 + 听力第 2 段", "date": "2026-10-21"},
    ], ensure_ascii=False, indent=2), encoding="utf-8")

    sched_path = cfg / "schedule.json"
    data = json.loads(sched_path.read_text(encoding="utf-8"))
    data["weekend"] = {
        "morning_split": "12:00",
        "afternoon_periods": [
            {"name": "第5节", "start": "14:00", "end": "14:45"},
            {"name": "第6节", "start": "14:55", "end": "15:40"},
        ],
        "courses": ["语文", "数学", "英语", "物理", "化学", "生物"],
    }
    sched_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def main() -> int:
    seed()

    import paths as py_paths

    py_paths.CONFIG_DIR = str(TMP / "settings")
    py_paths.PLUGINS_DIR = str(PROJ / "plugins")
    py_paths.MARKET_CACHE_DIR = str(TMP / "settings" / "plugin-repo")

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from app import paths
    from app.services import Services
    from app.window import SettingsApp

    from settings_manager import SettingsManager
    from schedule import ScheduleManager
    from StudentOnDuty import StudentOnDuty
    from homework import HomeworkManager
    import plugin_manager as pm_mod

    app = QApplication(sys.argv[:1])
    services = Services(
        settings=SettingsManager(str(TMP / "settings")),
        schedule=ScheduleManager(str(TMP / "settings")),
        duty=StudentOnDuty(),
        homework=HomeworkManager(),
        plugin_manager=pm_mod.PluginManager(str(PROJ / "plugins")),
    )
    win = SettingsApp((paths.QML_DIR / "Settings.qml").resolve(),
                      page="作业", services=services)
    win.show(1232, 762)
    root = win.root
    out = ROOT / "_shots"
    out.mkdir(exist_ok=True)

    def grab(name: str) -> None:
        img = root.grabWindow()
        path = out / name
        ok = not img.isNull() and img.save(str(path))
        print(f'{"OK  " if ok else "FAIL"} {path}')

    def step_home() -> None:
        grab("homework-data.png")
        QTimer.singleShot(200, step_weekend)

    def step_weekend() -> None:
        win.goto("周末作息")
        QTimer.singleShot(1500, lambda: (grab("weekend-data.png"), finish()))

    def finish() -> None:
        app.exit(0)

    QTimer.singleShot(2400, step_home)
    QTimer.singleShot(20000, lambda: app.exit(9))
    code = app.exec()
    shutil.rmtree(TMP, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
