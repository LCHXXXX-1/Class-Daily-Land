"""看 contentItem 与页面尺寸差多少，判断位移会不会露白。

    python settings_qml/tools/page_shift_check.py

结论已拿到一半：contentItem.x **可写**（无 anchors 托管），
但它是852 宽、页面 964 宽、左边还差 56 —— 直接整体位移会露出背景，
在 Mica 背板上就是一条明显的空白。

所以要么：
  (a) 只位移内容、背景不动（需要把位移点下沉到 container/headerContainer）
  (b) 位移整页（含背景）→ 就需要页面根的 x 可写，而实测不可写

这里把子树结构打出来，看有没有能整体包裹 header+container 的中间层。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_TMP = tempfile.TemporaryDirectory(prefix="cdl-shift-")
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

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import paths  # noqa: E402
from app.window import SettingsApp  # noqa: E402


def walk(item: QQuickItem, depth: int = 0):
    if not item:
        return
    yield depth, item
    for child in item.childItems():
        yield from walk(child, depth + 1)


def find_page(item: QQuickItem, name: str) -> QQuickItem | None:
    for _, node in walk(item):
        if node.objectName() == name:
            return node
    return None


def main() -> int:
    app = QApplication(sys.argv)
    sa = SettingsApp((paths.APP_ROOT / "qml/Settings.qml").resolve())
    sa.show(1180, 800)

    def test() -> None:
        page = find_page(sa.root.contentItem(), "PluginHub")
        print("\n=== PluginHub 子树（前几层）===")
        if page is None:
            print("  没找到页面")
            app.quit()
            return
        print(f"  页面: w={page.property('width')} x={page.property('x')}")
        for depth, node in walk(page):
            if depth > 3:
                continue
            try:
                w = float(node.property("width"))
                x = float(node.property("x"))
            except (TypeError, ValueError):
                w = x = -1.0
            cls = type(node).__name__
            obj = node.objectName()
            # 只打印容器类，跳过 Text / 控件的细节
            if cls in ("QQuickText", "QQuickImage", "QQuickRectangle"):
                continue
            print(f"  {'  ' * depth}{obj or '-':<14} {cls:<16} "
                  f"x={x:7.1f} w={w:7.1f}")
        app.quit()

    QTimer.singleShot(1400, lambda: sa.goto("插件管理"))
    QTimer.singleShot(2800, test)
    QTimer.singleShot(9000, app.quit)
    rc = app.exec()
    _TMP.cleanup()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())