"""问 QML 自己：横向转场到底装上没。

    python settings_qml/tools/transition_check.py

在纯 Qt 的最小复现里（_probe_stackview_run.py）StackView.replace 的
x / y / opacity **都能正常动画**，所以本项目里 x 不动是环境特有的问题。
先用这个脚本把可能性收窄 —— 让 QML 自己回答：
    · findStackView() 找得到吗
    · 装上去的 replaceEnter 是不是就是 horizontalEnter 本身
    · 那个 Transition 里到底有几条动画、是不是被别的 Transition 顶掉了
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_TMP = tempfile.TemporaryDirectory(prefix="cdl-check-")
os.environ["CDL_DATA_ROOT"] = _TMP.name
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", str(os.environ.get("WINDIR", r"C:\Windows")) + r"\Fonts")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from PySide6.QtCore import QMetaObject, Qt, QTimer  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import paths  # noqa: E402
from app.window import SettingsApp  # noqa: E402


def walk(item: QQuickItem):
    if not item:
        return
    yield item
    for child in item.childItems():
        yield from walk(child)


def find_sv(item: QQuickItem) -> QQuickItem | None:
    for node in walk(item):
        if node.property("depth") is not None and node.property("currentItem") is not None:
            return node
    return None


def diag_dict(root) -> dict:
    """transitionDiag 是 JS 对象，读出来是 QJSValue，要 toVariant 才看得到内容。"""
    value = root.property("transitionDiag")
    if value is None:
        return {"_": "None"}
    try:
        variant = value.toVariant()
    except AttributeError:
        variant = value
    if isinstance(variant, dict):
        return variant
    return {"_": repr(variant)}


def main() -> int:
    app = QApplication(sys.argv)
    sa = SettingsApp((paths.APP_ROOT / "qml/Settings.qml").resolve())
    sa.show(1180, 800)

    def ask() -> None:
        print("\n=== QML 自报 ===")
        print(f"  transitionDiag = {diag_dict(sa.root)}")

        # Python 侧能找到的 StackView，看它的 replaceEnter 是不是 null
        sv = find_sv(sa.root.contentItem())
        if sv is None:
            print("  Python 侧没找到 StackView")
        else:
            meta = sv.metaObject()
            for prop in ("replaceEnter", "replaceExit", "pushEnter", "popExit"):
                idx = meta.indexOfProperty(prop)
                if idx < 0:
                    print(f"  StackView 上没有属性 {prop}")
                    continue
                info = meta.property(idx)
                print(f"  {prop}: 可写={info.isWritable()} "
                      f"类型={info.typeName()}")

        # 手动再调一次，看 diag 会不会变
        QMetaObject.invokeMethod(sa.root, "installHorizontalTransition",
                                 Qt.ConnectionType.DirectConnection)
        print(f"  手动调用后 = {diag_dict(sa.root)}")

    QTimer.singleShot(1600, ask)
    QTimer.singleShot(2400, app.quit)
    rc = app.exec()
    _TMP.cleanup()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())