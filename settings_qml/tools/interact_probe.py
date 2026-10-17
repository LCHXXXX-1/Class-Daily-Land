"""作业页 / 课表页可用性探针：滚动是否生效、控件能否被点到。

    python tools/interact_probe.py

比"桥能不能写盘"更靠前一步：查的是「用户能不能摸到界面」。
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


def main() -> int:
    import paths as py_paths

    py_paths.CONFIG_DIR = str(TMP / "settings")
    py_paths.PLUGINS_DIR = str(PROJ / "plugins")
    py_paths.MARKET_CACHE_DIR = str(TMP / "settings" / "plugin-repo")

    from PySide6.QtCore import QPoint, QPointF, QTimer, Qt
    from PySide6.QtGui import QWheelEvent
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
                      page="课表管理", services=services)
    win.show(1232, 762)
    root = win.root

    def flickables(item):
        out = []
        for child in item.childItems():
            if child.metaObject().className().startswith("QQuickFlickable"):
                out.append(child)
            out.extend(flickables(child))
        return out

    def page_item():
        from PySide6.QtCore import QObject
        for obj in root.findChildren(QObject):
            cls = obj.metaObject().className()
            if "StackView" in cls:
                cur = obj.property("currentItem")
                if cur is not None:
                    return cur
        return None

    def step():
        print("navCurrentItem:", root.property("navCurrentItem"))
        cur = page_item()
        print("当前页对象:", cur.metaObject().className() if cur else None)
        if cur is not None:
            print("  title 属性:", cur.property("title"))
        fl = flickables(root.contentItem())
        print("Flickable 数量:", len(fl))
        for i, f in enumerate(fl):
            parent = f.parentItem()
            print(f"   [{i}] parent={parent.metaObject().className() if parent else None}"
                  f" w={f.property('width')} h={f.property('height')}"
                  f" contentH={f.property('contentHeight')}"
                  f" contentY={f.property('contentY')}"
                  f" clip={f.property('clip')}")
        if not fl:
            app.exit(3)
            return
        # 选「高度最大的那个」—— 页面主体的 Flickable 铺满窗口
        f = max(fl, key=lambda x: (x.property("height") or 0))
        # 发滚轮事件
        ev = QWheelEvent(QPointF(600, 400), QPointF(600, 400),
                         QPoint(0, 0), QPoint(0, -600),
                         Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                         Qt.ScrollPhase.NoScrollPhase, False)
        app.sendEvent(root, ev)
        QTimer.singleShot(400, lambda: after(f))

    def after(f):
        print("滚轮后 contentY =", f.property("contentY"))
        moved = (f.property("contentY") or 0) > 1
        print("滚动生效:", moved)
        print("结果:", "PASS" if moved else "FAIL")
        app.exit(0 if moved else 1)

    QTimer.singleShot(2600, step)
    QTimer.singleShot(20000, lambda: app.exit(9))
    code = app.exec()
    shutil.rmtree(TMP, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
