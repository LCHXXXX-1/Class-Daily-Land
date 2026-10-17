"""量左侧强调条有没有跟导航行对齐（不靠肉眼）。

做法：抓窗口图，只找强调条（主题强调色，出现在导航栏最左 6px），
再和 QML 报上来的「高亮项中心」比。

    python tools/marker_check.py [页面标题]

★ 别用「扫一列找高亮底色」的办法判断行位置：导航行底色是很淡的灰，
  和 Mica 背景只差几个色阶，阈值稍一松动就会把文字当成行边界（试过，量出来差 118px）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CDL_DATA_ROOT", str(ROOT / "data"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app import paths  # noqa: E402
from app.window import SettingsApp  # noqa: E402

PAGE = sys.argv[1] if len(sys.argv) > 1 else "通用"
OUT = ROOT / "_shots" / "nav_marker.png"

app = QApplication(sys.argv[:1])
sa = SettingsApp((paths.QML_DIR / "Settings.qml").resolve())
sa.show(1232, 762)
root = sa.root


def is_accent(c: QColor) -> bool:
    """强调色：蓝明显高于红绿。"""
    return c.blue() > 120 and c.blue() - c.red() > 30 and c.blue() - c.green() > 60


def analyze() -> bool:
    img = root.grabWindow()
    if img.isNull():
        print("FAIL 抓不到窗口")
        return False
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(OUT))

    rows = []
    for x in range(0, 6):
        for y in range(30, img.height()):
            if is_accent(img.pixelColor(x, y)):
                rows.append(y)
    if not rows:
        print("FAIL 没找到强调条（当前页可能不是顶层页）")
        return False
    bar_top, bar_bottom = min(rows), max(rows)
    bar_c = (bar_top + bar_bottom) / 2

    item_top = float(root.property("navItemTop"))
    item_h = float(root.property("navItemHeight"))
    item_c = item_top + item_h / 2
    print(f"强调条 像素 y={bar_top}~{bar_bottom} 中心 {bar_c:.1f} 高 {bar_bottom - bar_top + 1}")
    print(f"高亮项 QML top={item_top:.1f} h={item_h:.1f} 中心 {item_c:.1f}")
    print(f"差值 {bar_c - item_c:+.1f} px（容差 4）")
    ok = abs(bar_c - item_c) <= 4.0
    print("PASS" if ok else "FAIL 强调条没对齐")
    return ok


def step() -> None:
    app.exit(0 if analyze() else 1)


def go() -> None:
    sa.goto(PAGE)
    QTimer.singleShot(900, step)


QTimer.singleShot(2600, go)
QTimer.singleShot(20000, lambda: app.exit(9))
app.exec()
os._exit(0)
