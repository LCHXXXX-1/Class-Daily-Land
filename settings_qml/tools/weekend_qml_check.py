"""单独实例化 Timetable.qml，验证周末课表区块的绑定与保存链路。

绕开 NavigationView 的 push 时序（pushInProgress 会让首次 push 被推迟），
直接把页面挂到窗口上，属性该怎么绑还是怎么绑。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "settings_qml"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import Q_ARG, QMetaObject, QTimer, Qt, QUrl  # noqa: E402
from PySide6.QtQml import QQmlComponent  # noqa: E402
from PySide6.QtQuick import QQuickView  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import paths as py_paths  # noqa: E402
from schedule import ScheduleManager  # noqa: E402
from settings_manager import SettingsManager  # noqa: E402

from app.services import Services  # noqa: E402
from app.window import SettingsApp  # noqa: E402

BACKUP = ROOT / "settings" / "schedule.json.bak_wkqml"
FAILS: list[str] = []


def check(label, cond, extra=""):
    print(f"    {'✓' if cond else '✗'} {label} {extra}")
    if not cond:
        FAILS.append(label)


def js(v):
    """QML 属性回读拿到的是 QJSValue，要 toVariant 才是 Python 对象。"""
    return v.toVariant() if hasattr(v, "toVariant") else v


def call(obj, name, *args):
    # removeWeekendCourse(index) 这类带参函数，探针必须显式传参，
    # 不然 index 是 undefined，splice(undefined,1) 等于不删
    if args:
        QMetaObject.invokeMethod(obj, name, Qt.ConnectionType.DirectConnection,
                                 Q_ARG("QVariant", args[0]))
    else:
        QMetaObject.invokeMethod(obj, name, Qt.ConnectionType.DirectConnection)


def main() -> int:
    app = QApplication(sys.argv)
    src = Path(py_paths.CONFIG_DIR) / "schedule.json"
    BACKUP.write_bytes(src.read_bytes())

    mgr = ScheduleManager(py_paths.CONFIG_DIR)
    sa = SettingsApp(ROOT / "settings_qml" / "qml" / "Settings.qml",
                     services=Services(settings=SettingsManager(py_paths.CONFIG_DIR),
                                       schedule=mgr,
                                       config_dir=Path(py_paths.CONFIG_DIR)))
    sa.show(1180, 900)

    # ★ 用**同一个 engine** 直接 create：另起 QQuickView 会有一套独立的
    #   引擎与上下文属性，TimetableStore 之类的桥全都拿不到。
    engine = sa.window.engine
    ctx = engine.rootContext()
    comp = QQmlComponent(engine,
                         QUrl.fromLocalFile(
                             str(ROOT / "settings_qml" / "qml" / "pages"
                                 / "Timetable.qml")))
    errs = [e.toString() for e in comp.errors()]
    if errs:
        print("    ✗ 编译失败:", errs)
        return 1
    page = comp.create(ctx)
    if page is None:
        print("    ✗ 实例化失败")
        return 1

    def probe() -> None:
        print("[1] 周末区块的属性绑定")
        check("weekendAvailable", page.property("weekendAvailable") is True,
              f"= {page.property('weekendAvailable')}")
        check("weekendSplit 非空", bool(page.property("weekendSplit")),
              f"= {page.property('weekendSplit')}")
        check("weekendPeriodCount > 0",
              int(page.property("weekendPeriodCount")) > 0,
              f"= {page.property('weekendPeriodCount')}")
        courses = js(page.property("weekendCourses"))
        check("weekendCourses 是数组", isinstance(courses, list),
              f"= {courses}")

        print("[2] 增删行（QML 函数）")
        n0 = len(js(page.property("weekendCourses")) or [])
        call(page, "addWeekendCourse")
        n1 = len(js(page.property("weekendCourses")) or [])
        check("加一节生效", n1 == n0 + 1, f"{n0} → {n1}")
        call(page, "removeWeekendCourse", 0)
        n2 = len(js(page.property("weekendCourses")) or [])
        check("删一节生效", n2 == n0, f"{n1} → {n2}")

        p0 = len(js(page.property("weekendAfternoon")) or [])
        call(page, "addWeekendPeriod")
        p1 = len(js(page.property("weekendAfternoon")) or [])
        check("加下午节次生效", p1 == p0 + 1, f"{p0} → {p1}")

        print("[3] 写入内容并保存")
        page.setProperty("weekendSplit", "11:30")
        page.setProperty("weekendCourses", ["物理", "化学", ""])
        aft = [{"name": "下午1", "start": "14:00", "end": "14:45"}]
        page.setProperty("weekendAfternoon", aft)
        call(page, "saveWeekend")

        w = ScheduleManager(py_paths.CONFIG_DIR).get_weekend()
        check("分界落盘", w.get("morning_split") == "11:30",
              f"= {w.get('morning_split')}")
        check("课程落盘且去空串", list(w.get("courses") or []) == ["物理", "化学"],
              f"= {w.get('courses')}")
        check("下午节次落盘", len(w.get("afternoon_periods") or []) == 1,
              f"= {w.get('afternoon_periods')}")

        print("[4] 真的生效于周末 get_status")
        m2 = ScheduleManager(py_paths.CONFIG_DIR)
        st = m2.get_status(datetime(2026, 10, 10, 9, 0))
        print(f"    周六 status = {st}")
        check("周六不再是无课", st.get("status") != "none", f"→ {st.get('status')}")
        st2 = m2.get_status(datetime(2026, 10, 11, 14, 10))
        print(f"    周日 status = {st2}")
        check("周日能识别", st2.get("status") != "none", f"→ {st2.get('status')}")

        print("[5] 非法输入被拒")
        page.setProperty("weekendAfternoon",
                         [{"name": "x", "start": "25:00", "end": "14:00"}])
        call(page, "saveWeekend")
        w2 = ScheduleManager(py_paths.CONFIG_DIR).get_weekend()
        check("坏时间没写进去",
              w2.get("afternoon_periods") != [{"name": "x", "start": "25:00",
                                                "end": "14:00"}],
              f"= {w2.get('afternoon_periods')}")

        page.deleteLater()
        app.quit()

    QTimer.singleShot(1400, probe)
    QTimer.singleShot(6000, app.quit)
    rc = app.exec()
    src.write_bytes(BACKUP.read_bytes())
    BACKUP.unlink(missing_ok=True)
    print("\n[还原] schedule.json 已恢复")
    print("结果：" + ("全部通过" if not FAILS else f"失败 {FAILS}"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())