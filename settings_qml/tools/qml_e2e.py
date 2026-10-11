"""QML 层端到端：真实引擎里验证周末课表区块与插件设置页点击。

离屏 software 后端**不渲染文字**（字体光栅化缺失），所以这里不做像素断言，
改为：
  1) 读 QML 侧对象的属性值（editableCourses 等）—— 证明绑定和初始化通了
  2) 直接调 QML 函数保存，再从 Python 侧断言落盘与get_status 生效
  3) 找到插件行的 ClipItem，触发它的 activated()，断言 open() 被调用
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

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import paths as py_paths  # noqa: E402
from plugin_manager import PluginManager  # noqa: E402
from schedule import ScheduleManager  # noqa: E402
from settings_manager import SettingsManager  # noqa: E402

from app.services import Services  # noqa: E402
from app.window import SettingsApp  # noqa: E402

BACKUP = ROOT / "settings" / "schedule.json.bak_qml"
FAILS: list[str] = []


def check(label, cond, extra=""):
    print(f"    {'✓' if cond else '✗'} {label} {extra}")
    if not cond:
        FAILS.append(label)


def find_page(sa, name):
    """在视觉树里找objectName 为 name 的 StackView 当前页。"""
    def walk(item):
        for c in item.childItems():
            if c.objectName() == name or name.lower() in c.objectName().lower():
                return c
            r = walk(c)
            if r is not None:
                return r
        return None
    return walk(sa.root.contentItem())


def main() -> int:  # noqa: C901
    app = QApplication(sys.argv)
    src = Path(py_paths.CONFIG_DIR) / "schedule.json"
    BACKUP.write_bytes(src.read_bytes())

    plugins_dir = str(ROOT / "plugins")
    py_paths.PLUGINS_DIR = plugins_dir
    pm = PluginManager(plugins_dir, settings=SettingsManager(py_paths.CONFIG_DIR))
    pm.load_all()
    svc = Services(plugin_manager=pm,
                   settings=SettingsManager(py_paths.CONFIG_DIR),
                   plugins_dir=Path(plugins_dir),
                   config_dir=Path(py_paths.CONFIG_DIR))

    sa = SettingsApp(ROOT / "settings_qml" / "qml" / "Settings.qml", services=svc)
    sa.show(1180, 900)

    def step1() -> None:
        print("[1] 课表管理页：周末区块的属性绑定")
        sa.root.openPage("pages/Timetable.qml")

        def probe() -> None:
            _probe_weekend(page_of(sa))

        QTimer.singleShot(700, probe)

    def page_of(app_):
        return find_page(app_, "Timetable")

    def _probe_weekend(page) -> None:
        if page is None:
            check("找到 Timetable 页", False)
            names = []
            def walk2(it):
                for c in it.childItems():
                    if c.objectName():
                        names.append(c.objectName())
                    walk2(c)
            walk2(sa.root.contentItem())
            print("视觉树里的 objectName:", sorted(set(names)))
            sa.root.grabWindow().save(str(
                ROOT / "settings_qml" / "_shots" / "timetable.png"))
            return step3()
        check("找到 Timetable 页", True)
        check("weekendAvailable", page.property("weekendAvailable") is True,
              f"= {page.property('weekendAvailable')}")
        check("weekendSplit", bool(page.property("weekendSplit")),
              f"= {page.property('weekendSplit')}")
        check("weekendCourses 已加载(数组)",
              isinstance(page.property("weekendCourses"), (list, type([]))),
              f"= {page.property('weekendCourses')}")
        check("weekendPeriodCount", int(page.property("weekendPeriodCount")) > 0,
              f"= {page.property('weekendPeriodCount')}")

        # 调 QML 侧的函数写入，再存
        print("[2] 经 QML 函数写入并保存")
        from PySide6.QtCore import QMetaObject, Qt

        def call(name):
            QMetaObject.invokeMethod(page, name, Qt.ConnectionType.DirectConnection)

        call("addWeekendCourse")
        call("addWeekendCourse")
        # 直接把内容塞进去再存
        courses = page.property("weekendCourses")
        courses = ["物理", "化学"]
        page.setProperty("weekendCourses", courses)
        page.setProperty("weekendSplit", "11:30")
        call("saveWeekend")

        mgr = ScheduleManager(py_paths.CONFIG_DIR)
        w = mgr.get_weekend()
        check("落盘 split=11:30", w.get("morning_split") == "11:30",
              f"= {w.get('morning_split')}")
        check("落盘 courses", list(w.get("courses") or []) == ["物理", "化学"],
              f"= {w.get('courses')}")

        print("[2b] 真的生效于周末 get_status")
        st = mgr.get_status(datetime(2026, 10, 10, 9, 0))
        print(f"    周六 status = {st}")
        check("周六能读到课程", st.get("status") != "none", f"→ {st.get('status')}")

    def step3() -> None:
        print("[3] 插件设置页：点插件名是否真的触发 open")
        check("桥列出插件", sa.plugin_pages.count() > 0,
              f"count={sa.plugin_pages.count()}")
        sa.root.openPage("pages/PluginHub.qml")

        def grab() -> None:
            page = find_page(sa, "PluginHub") or find_page(sa, "PluginSettings")
            if page is None:
                check("找到 PluginHub 页", False)
                return app.quit()
            check("找到 PluginHub 页", True)
            pages = page.property("pages")
            n = len(pages) if isinstance(pages, list) else -1
            check("页内 pages 已填充", n > 0, f"= {n}")

            # 找到插件行里的 ClipItem，触发 activated
            from PySide6.QtCore import QMetaObject, Qt

            hit = []

            def walk(item):
                for c in item.childItems():
                    if type(c).__name__ == "QQuickItem" and \
                            hasattr(c, "activated") and c.property("title"):
                        hit.append(c)
                    walk(c)

            walk(page.childItems() and sa.root.contentItem() or sa.root.contentItem())
            titled = [h for h in hit if str(h.property("title") or "")]
            check("插件行渲染出来了", len(titled) > 0,
                  f"→ {[h.property('title') for h in titled][:4]}")
            if titled:
                opened = []
                orig = sa.plugin_pages._present
                sa.plugin_pages._present = lambda *a: opened.append(a) or None
                # 触发点击
                for h in titled:
                    try:
                        # ClipItem.activated 是 native Qt 信号，不能当方法调，
                        # 要用 QMetaObject 触发
                        QMetaObject.invokeMethod(
                            h, "activated", Qt.ConnectionType.DirectConnection)
                        break
                    except Exception as exc:
                        print(f"    触发 activated 失败: {exc}")
                sa.plugin_pages._present = orig
                check("点击后打开了设置页", len(opened) > 0,
                      f"→ {[(o[0], type(o[1]).__name__) for o in opened]}")
            app.quit()

        QTimer.singleShot(700, grab)

    QTimer.singleShot(1400, step1)
    QTimer.singleShot(2000, step3)
    QTimer.singleShot(4500, app.quit)
    rc = app.exec()

    src.write_bytes(BACKUP.read_bytes())
    BACKUP.unlink(missing_ok=True)
    print("\n[还原] schedule.json 已恢复")
    print("\n" + ("全部通过" if not FAILS else f"失败 {len(FAILS)} 项: {FAILS}"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())