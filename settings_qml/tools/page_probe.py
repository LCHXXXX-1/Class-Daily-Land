"""新作业页 / 周末作息页的行为探针。

    python tools/page_probe.py [homework|weekend]

作业：填三个输入框（科目/日期/内容）→ 点「添加作业」→ 落盘 → 再改一条 → 再删。
周末：读上午节次、加一节下午课、填课程 → 保存 → 后端读到同样的值。
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

TMP = Path(tempfile.mkdtemp(prefix="cdlprobe-"))
shutil.copytree(PROJ / "settings", TMP / "settings", dirs_exist_ok=True)
os.environ["CDL_DATA_ROOT"] = str(TMP)

RESULTS: list[tuple[str, bool, str]] = []


def main() -> int:
    import paths as py_paths

    py_paths.CONFIG_DIR = str(TMP / "settings")
    py_paths.PLUGINS_DIR = str(PROJ / "plugins")
    py_paths.MARKET_CACHE_DIR = str(TMP / "settings" / "plugin-repo")

    from PySide6.QtCore import QObject, QTimer
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
    hw = HomeworkManager()
    sched = ScheduleManager(str(TMP / "settings"))
    changed: list[str] = []
    services = Services(
        settings=SettingsManager(str(TMP / "settings")),
        schedule=sched,
        duty=StudentOnDuty(),
        homework=hw,
        plugin_manager=pm_mod.PluginManager(str(PROJ / "plugins")),
        on_data_changed=changed.append,
    )
    win = SettingsApp((paths.QML_DIR / "Settings.qml").resolve(),
                      page="作业", services=services)
    win.show(1232, 762)
    root = win.root

    def page_item():
        for obj in root.findChildren(QObject):
            if "StackView" in obj.metaObject().className():
                cur = obj.property("currentItem")
                if cur is not None:
                    return cur
        return None

    def find_inputs(item):
        """按声明顺序找出页面里的输入控件（TextField / TextArea）。"""
        out = []

        def walk(obj):
            cls = obj.metaObject().className()
            # RinUI 自己也有 TextField/TextArea（import RinUI 在 QtQuick.Controls
            # 之后，同名类型会用它），类名是 TextField_QMLTYPE_N 而不是 QQuickTextField
            if "TextField" in cls or "TextArea" in cls:
                out.append(obj)
            for child in obj.children():
                walk(child)

        walk(item)
        return out

    def check(name, cond, detail=""):
        RESULTS.append((name, bool(cond), detail))
        print(f"  {'✓' if cond else '✗'} {name}" + (f"  {detail}" if detail else ""))

    def homework_step():
        print("\n=== 作业页 ===")
        page = page_item()
        print("  页面:", page.metaObject().className())
        inputs = find_inputs(page)
        print("  找到输入控件:", [(i.metaObject().className(), i.property("placeholderText"))
                                for i in inputs])
        if len(inputs) < 3:
            check("页面有 科目/日期/内容 三个输入", False, str(len(inputs)))
            return finish()

        by_placeholder = {str(i.property("placeholderText") or ""): i for i in inputs}
        subject = by_placeholder.get("如 数学")
        date = by_placeholder.get("可留空，如 2026-10-20")
        content = by_placeholder.get("一行一条也行，原样显示在主窗口里")
        if subject is None or date is None or content is None:
            check("找到新增区的三个输入框", False, str(list(by_placeholder)))
            return finish()
        subject.setProperty("text", "数学")
        date.setProperty("text", "2026-10-20")
        content.setProperty("text", "练习册 P12 第 3 题")

        page.metaObject().invokeMethod if False else None
        from PySide6.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(page, "addItem", Qt.ConnectionType.DirectConnection)

        items = hw.get_all_homework()
        print("  管理器:", items)
        check("添加后管理器有 1 条", len(items) == 1, str(items))
        check("科目/日期/内容都存对",
              bool(items) and items[0].get("subject") == "数学"
              and items[0].get("date") == "2026-10-20"
              and items[0].get("content") == "练习册 P12 第 3 题",
              str(items[0]) if items else "")
        check("宿主收到 homework 通知", changed.count("homework") == 1, str(changed))

        # 修改：走桥的 update（对话框里的保存按钮就是它）
        ok = win.homework.update(0, "数学", "改过的内容", "2026-10-21")
        print("  update ->", ok, hw.get_all_homework())
        check("修改生效", ok and hw.get_all_homework()[0]["content"] == "改过的内容")
        check("修改也发通知", changed.count("homework") == 2, str(changed))

        # 整组清除
        removed = win.homework.clearSubject("数学")
        check("整组清除", removed == 1 and hw.get_all_homework() == [], str(removed))
        QTimer.singleShot(200, weekend_step)

    def weekend_step():
        print("\n=== 周末作息页 ===")
        win.goto("周末作息")
        QTimer.singleShot(1400, weekend_check)

    def weekend_check():
        page = page_item()
        print("  页面:", page.metaObject().className())
        print("  available:", page.property("available"))
        morning = page.property("morning").toVariant()
        print("  上午节次:", morning)
        check("页面拿到上午节次", isinstance(morning, list) and len(morning) > 0,
              str(len(morning) if isinstance(morning, list) else morning))

        from PySide6.QtCore import QMetaObject, Qt
        QMetaObject.invokeMethod(page, "addAfternoon", Qt.ConnectionType.DirectConnection)
        after = page.property("afternoon").toVariant()
        print("  加一节下午:", after)
        check("下午节次能加", isinstance(after, list) and len(after) == 1, str(after))

        # 填课程：上午全部 + 下午那一节
        rows = int(page.property("morning").toVariant().__len__()) + 1
        courses = ["语文", "数学", "英语", "物理", "化学", "生物", "体育", "自习"][:rows]
        page.setProperty("courses", courses)
        page.setProperty("split", "12:00")

        QMetaObject.invokeMethod(page, "save", Qt.ConnectionType.DirectConnection)
        print("  tip:", page.property("tip"))
        wk = sched.get_weekend()
        print("  后端:", wk)
        check("下午节次落盘", len(wk.get("afternoon_periods") or []) == 1, str(wk))
        check("课程落盘", (wk.get("courses") or [])[:rows] == courses, str(wk.get("courses")))
        check("周末通知发给了宿主", "schedule" in changed, str(changed))
        finish()

    def finish():
        ok = all(ok for _, ok, _ in RESULTS)
        print("\n--- 汇总 ---")
        for name, good, _ in RESULTS:
            print(("PASS " if good else "FAIL ") + name)
        print("结果:", "PASS" if ok else "FAIL")
        app.exit(0 if ok else 1)

    QTimer.singleShot(2600, homework_step)
    QTimer.singleShot(24000, lambda: app.exit(9))
    code = app.exec()
    shutil.rmtree(TMP, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
