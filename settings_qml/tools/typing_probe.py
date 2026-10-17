"""键盘输入探针：点进输入框、真的敲字，确认页面能编辑。

    python tools/typing_probe.py

page_probe 是直接往 `text` 属性里塞值，绕过了输入链路；
这一支用真实的鼠标/键盘事件，能查出「输入框收不到焦点」这类问题 ——
那种情况下滑鼠点得动、但一个字也打不进去，看着就是"功能坏了"。
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

TMP = Path(tempfile.mkdtemp(prefix="cdltype-"))
shutil.copytree(PROJ / "settings", TMP / "settings", dirs_exist_ok=True)
os.environ["CDL_DATA_ROOT"] = str(TMP)


def main() -> int:
    import paths as py_paths

    py_paths.CONFIG_DIR = str(TMP / "settings")
    py_paths.PLUGINS_DIR = str(PROJ / "plugins")
    py_paths.MARKET_CACHE_DIR = str(TMP / "settings" / "plugin-repo")

    from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QTimer, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from app import paths
    from app.services import Services
    from app.window import SettingsApp
    from settings_manager import SettingsManager
    from schedule import ScheduleManager
    from homework import HomeworkManager

    app = QApplication(sys.argv[:1])
    win = SettingsApp(
        (paths.QML_DIR / "Settings.qml").resolve(), page="作业",
        services=Services(settings=SettingsManager(str(TMP / "settings")),
                          schedule=ScheduleManager(str(TMP / "settings")),
                          homework=HomeworkManager()))
    win.show(1232, 762)
    root = win.root

    def page_item():
        for obj in root.findChildren(QObject):
            if "StackView" in obj.metaObject().className():
                cur = obj.property("currentItem")
                if cur is not None:
                    return cur
        return None

    def inputs(item):
        # RinUI 自己也有 TextField/TextArea，类名是 TextField_QMLTYPE_N；
        # 而 QtQuick.Controls 的是 QQuickTextField。两种都要认。
        out: list = []

        def walk(obj):
            cls = obj.metaObject().className()
            if "TextField" in cls or "TextArea" in cls:
                out.append(obj)
            for child in obj.children():
                walk(child)

        walk(item)
        return out

    def click(item):
        center = item.mapToScene(QPointF(item.property("width") / 2,
                                         item.property("height") / 2))
        QTest.mouseClick(root, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier,
                         QPoint(int(center.x()), int(center.y())))
        QTest.qWait(150)

    def type_text(text):
        for ch in text:
            for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                app.sendEvent(root, QKeyEvent(kind, 0,
                                              Qt.KeyboardModifier.NoModifier, ch))
        QTest.qWait(100)

    def step():
        page = page_item()
        fields = {str(i.property("placeholderText") or ""): i for i in inputs(page)}
        subject = fields.get("如 数学")
        content = fields.get("一行一条也行，原样显示在主窗口里")
        if subject is None or content is None:
            print("FAIL 找不到输入框:", list(fields))
            return finish(1)

        click(subject)
        focused = root.activeFocusItem()
        print("焦点落到:", focused.metaObject().className() if focused else None)
        type_text("数学")
        print("科目框 =", repr(subject.property("text")))

        click(content)
        type_text("练习册")
        print("内容框 =", repr(content.property("text")))

        ok = (subject.property("text") == "数学"
              and content.property("text") == "练习册")
        return finish(0 if ok else 1)

    def finish(code: int) -> None:
        print("结果:", "PASS" if code == 0 else "FAIL")
        app.exit(code)

    QTimer.singleShot(2600, step)
    QTimer.singleShot(20000, lambda: app.exit(9))
    code = app.exec()
    shutil.rmtree(TMP, ignore_errors=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
