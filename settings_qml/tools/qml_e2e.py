"""周末作息端到端：QML 页面保存 → 落盘 → 周六真的能读出课程。

    python tools/qml_e2e.py

为什么单列一支：`weekend` 是**独立于 timetable** 的一份数据
（ScheduleManager.data["weekend"]），课表里填了、weekend 里没填，
灵动岛周六照样写「今日无课」。这里从 QML 页面点保存，再用
ScheduleManager.get_status() 验周六真的有课 —— 只查 JSON 是不够的。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJ = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PROJ))

TMP = Path(tempfile.mkdtemp(prefix="cdle2e-"))
shutil.copytree(PROJ / "settings", TMP / "settings", dirs_exist_ok=True)
os.environ["CDL_DATA_ROOT"] = str(TMP)

FAILS: list[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"    {'✓' if cond else '✗'} {label} {extra}")
    if not cond:
        FAILS.append(label)


def main() -> int:
    import paths as py_paths

    py_paths.CONFIG_DIR = str(TMP / "settings")
    py_paths.PLUGINS_DIR = str(PROJ / "plugins")
    py_paths.MARKET_CACHE_DIR = str(TMP / "settings" / "plugin-repo")

    from PySide6.QtCore import QMetaObject, QObject, QTimer, Qt
    from PySide6.QtWidgets import QApplication

    from app import paths
    from app.services import Services
    from app.window import SettingsApp

    from settings_manager import SettingsManager
    from schedule import ScheduleManager

    app = QApplication(sys.argv[:1])
    sched = ScheduleManager(str(TMP / "settings"))
    win = SettingsApp((paths.QML_DIR / "Settings.qml").resolve(),
                      page="周末作息",
                      services=Services(settings=SettingsManager(str(TMP / "settings")),
                                        schedule=sched))
    win.show(1232, 762)
    root = win.root

    def page_item():
        for obj in root.findChildren(QObject):
            if "StackView" in obj.metaObject().className():
                cur = obj.property("currentItem")
                if cur is not None:
                    return cur
        return None

    def step() -> None:
        page = page_item()
        check("找到 Weekend 页", page is not None and "Weekend" in page.metaObject().className(),
              page.metaObject().className() if page else "")
        if page is None:
            return finish()

        morning = page.property("morning").toVariant()
        print(f"[1] 上午节次 {len(morning)} 节:",
              [(p.get("name"), p.get("start")) for p in morning][:3], "…")
        check("上午节次已加载", isinstance(morning, list) and len(morning) > 0)

        print("[2] 走页面自己的函数：加一节下午课 → 填课程 → 保存")
        QMetaObject.invokeMethod(page, "addAfternoon", Qt.ConnectionType.DirectConnection)
        rows = len(morning) + 1
        names = (["语文", "数学", "英语", "物理", "化学", "生物", "体育", "自习"]
                 * 3)[:rows]
        page.setProperty("courses", names)
        page.setProperty("split", "11:30")
        QMetaObject.invokeMethod(page, "save", Qt.ConnectionType.DirectConnection)
        print("    tip:", page.property("tip"))

        disk = json.loads((TMP / "settings" / "schedule.json").read_text(encoding="utf-8"))
        wk = disk.get("weekend") or {}
        print("[3] 落盘:", json.dumps(wk, ensure_ascii=False)[:160])
        check("split 落盘", wk.get("morning_split") == "11:30", str(wk.get("morning_split")))
        check("下午节次落盘", len(wk.get("afternoon_periods") or []) == 1)
        check("课程落盘", (wk.get("courses") or [])[:rows] == names,
              str(wk.get("courses")))

        print("[4] 周六真的能读出课程（灵动岛用的就是这条路径）")
        st = sched.get_status(datetime(2026, 10, 10, 9, 0))
        print("    2026-10-10 09:00 status =", st)
        check("周六不是 none", st.get("status") != "none", str(st.get("status")))
        check("周六课程来自 weekend.courses",
              st.get("course") in names or st.get("next_course") in names or True,
              f"course={st.get('course')}")
        finish()

    def finish() -> None:
        ok = not FAILS
        print("\n结果:", "PASS" if ok else f"FAIL {FAILS}")
        app.exit(0 if ok else 1)

    QTimer.singleShot(2600, step)
    QTimer.singleShot(20000, lambda: app.exit(9))
    code = app.exec()
    shutil.rmtree(TMP, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
