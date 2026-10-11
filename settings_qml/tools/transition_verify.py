"""验证横向转场：读每个页面的 slideIn / slideOut / contentItem.x。

    python settings_qml/tools/transition_verify.py

判据（对应「新页从右推进+ 旧页向左让位淡出」）：
  · 进入中的页 contentItem.x 应从 基准+页宽*0.26 单调回到基准
  · 退出的页 contentItem.x 应从基准走到 基准-页宽*0.16，opacity降到 0

只读属性不抓像素：offscreen + 软件渲染下 grabWindow 不会帧间重绘
（实测连拍 8 帧 md5 全同），像素验证不了动画。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_TMP = tempfile.TemporaryDirectory(prefix="cdl-verify-")
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

INTERVAL_MS = 30
SAMPLES = 16


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


def main() -> int:
    app = QApplication(sys.argv)
    sa = SettingsApp((paths.APP_ROOT / "qml/Settings.qml").resolve())
    sa.show(1180, 800)

    rows: list[str] = []

    def sample() -> None:
        sv = find_sv(sa.root.contentItem())
        if sv is None:
            rows.append("没找到 StackView")
            return
        cells = []
        for page in sv.childItems():
            name = page.objectName() or "-"
            ci = page.property("contentItem")
            x = float(ci.property("x")) if ci is not None else float("nan")
            base = float(page.property("contentBaseX") or 0)
            cells.append(
                f"{name}: slideIn={float(page.property('slideIn') or 0):.2f} "
                f"slideOut={float(page.property('slideOut') or 0):.2f} "
                f"ciX={x:7.1f}(基准{base:.0f}) op={float(page.property('opacity')):.2f}"
            )
        rows.append(" | ".join(cells))

    timer = QTimer()
    timer.setInterval(INTERVAL_MS)
    timer.timeout.connect(sample)
    count = {"n": 0}

    def on_tick() -> None:
        count["n"] += 1
        if count["n"] >= SAMPLES:
            timer.stop()
            QTimer.singleShot(150, app.quit)

    timer.timeout.connect(on_tick)

    def fire() -> None:
        sa.goto("插件管理")
        timer.start()

    QTimer.singleShot(1500, lambda: sa.goto("插件"))
    QTimer.singleShot(2800, fire)
    QTimer.singleShot(8000, app.quit)
    rc = app.exec()

    print(f"\n=== 切页后每 {INTERVAL_MS}ms 采样 ===")
    for i, row in enumerate(rows):
        print(f"  [{i:02d}] {row}")
    _TMP.cleanup()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())